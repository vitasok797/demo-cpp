#include <./crow.h>

#include <atomic>
#include <cstdint>
#include <string>

namespace
{

auto counter = std::atomic<int64_t>{0};

[[nodiscard]]
auto counter_json() -> crow::json::wvalue
{
    return crow::json::wvalue{
        {"counter", counter.load(std::memory_order_relaxed)}
    };
}

}  // namespace

auto main() -> int
{
    auto app = crow::SimpleApp{};

    CROW_ROUTE(app, "/")(
        []() -> crow::response
        {
            auto response = crow::response{};
            response.set_static_file_info("static/index.html");
            return response;
        });

    CROW_ROUTE(app, "/data/counter.json")(
        []() -> crow::response
        {
            auto response = crow::response{counter_json()};
            response.set_header("Cache-Control", "no-store");
            return response;
        });

    CROW_WEBSOCKET_ROUTE(app, "/ws")
        .onmessage(
            [](crow::websocket::connection& connection, const std::string& message, bool is_binary) -> void
            {
                if (is_binary) [[unlikely]]
                {
                    connection.close("Text commands required");
                    return;
                }

                if (message == "get_counter_value")
                {
                    connection.send_text(counter_json().dump());
                }
                else if (message == "increment_counter_value")
                {
                    counter.fetch_add(1, std::memory_order_relaxed);
                }
                else [[unlikely]]
                {
                    connection.close("Unknown command");
                }
            });

    // http://localhost:18080/
    app.bindaddr("127.0.0.1").port(18080).multithreaded().run();
}
