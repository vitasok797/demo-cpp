document.addEventListener('alpine:init', () => {
    Alpine.data('counter_demo', () => {
        // Keep browser resources outside Alpine's reactive state.
        let socket;
        let poll_timer;
        let reconnect_timer;
        let observer;
        let request;
        let stopped = false;
        let log_id = 0;
        let ws_revision = 0;

        return {
            counter: null,
            connected: false,
            http_status: 'Ожидание',
            polling: true,
            poll_seconds: 2,
            logs: [],

            init() {
                this.$nextTick(() => {
                    if (stopped) return;
                    let previous = this.$refs.counter.textContent;
                    observer = new MutationObserver(() => {
                        const current = this.$refs.counter.textContent;
                        if (current !== previous) {
                            this.log('DOM', 'Текст счётчика обновлён', `${previous} → ${current}`);
                            previous = current;
                        }
                    });
                    observer.observe(this.$refs.counter, { childList: true, characterData: true, subtree: true });
                    this.poll();
                    this.schedule_poll();
                    this.connect();
                });
            },

            schedule_poll() {
                clearInterval(poll_timer);
                if (this.polling) poll_timer = setInterval(() => this.poll(), this.poll_seconds * 1000);
            },

            toggle_polling() {
                this.polling = !this.polling;
                this.schedule_poll();
                this.log('HTTP', this.polling ? 'Опрос запущен' : 'Опрос приостановлен');
                if (this.polling) this.poll();
            },

            change_interval(delta) {
                this.poll_seconds = Math.max(1, this.poll_seconds + delta);
                this.schedule_poll();
                this.log('HTTP', 'Интервал опроса изменён', `${this.poll_seconds} с`);
            },

            log(kind, title, detail = '') {
                this.logs.unshift({ id: ++log_id, time: new Date().toLocaleTimeString('ru-RU'), kind, title, detail });
                if (this.logs.length > 200) this.logs.pop();
            },

            apply(text) {
                const data = JSON.parse(text);
                if (!Number.isSafeInteger(data.counter) || data.counter < 0) {
                    throw new Error('Ожидался JSON с целым неотрицательным counter');
                }
                if (this.counter !== data.counter) this.counter = data.counter;
            },

            async poll() {
                if (request || stopped || !this.polling) return;
                request = new AbortController();
                const timeout = setTimeout(() => request?.abort(), 5000);
                const revision = ws_revision;
                this.log('HTTP', '→ GET /data/counter.json');
                try {
                    const response = await fetch('/data/counter.json', { cache: 'no-store', signal: request.signal });
                    const text = await response.text();
                    this.log('HTTP', `← Ответ ${response.status}`, text);
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    // A late HTTP response must not overwrite a newer WebSocket result.
                    if (revision === ws_revision) this.apply(text);
                    else this.log('HTTP', 'Поздний ответ пропущен', 'После начала fetch уже получено значение по WS');
                    this.http_status = 'Работает';
                } catch (error) {
                    if (!stopped) {
                        this.http_status = 'Ошибка';
                        this.log('ERROR', 'Ошибка HTTP', error.message);
                    }
                } finally {
                    clearTimeout(timeout);
                    request = null;
                }
            },

            connect() {
                socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
                socket.onopen = () => {
                    this.connected = true;
                    this.log('WS', 'Соединение установлено', '/ws');
                    this.send('get_counter_value');
                };
                socket.onmessage = (event) => {
                    this.log('WS', '← Значение с сервера', event.data);
                    try {
                        this.apply(event.data);
                        ++ws_revision;
                    } catch (error) {
                        this.log('ERROR', 'Ошибка JSON', error.message);
                    }
                };
                socket.onerror = () => this.log('ERROR', 'Ошибка WebSocket');
                socket.onclose = () => {
                    this.connected = false;
                    if (!stopped) {
                        this.log('WS', 'Соединение закрыто', 'Повторное подключение через 2 секунды');
                        reconnect_timer = setTimeout(() => this.connect(), 2000);
                    }
                };
            },

            send(command) {
                if (socket?.readyState !== WebSocket.OPEN) return false;
                socket.send(command);
                this.log('WS', '→ Команда', command);
                return true;
            },

            increment() {
                if (this.send('increment_counter_value')) this.send('get_counter_value');
            },

            destroy() {
                stopped = true;
                clearInterval(poll_timer);
                clearTimeout(reconnect_timer);
                observer?.disconnect();
                request?.abort();
                socket?.close();
            }
        };
    });
});
