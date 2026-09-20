from __future__ import annotations

import argparse
import colorama
import functools
import locale
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

IS_WINDOWS = (sys.platform == 'win32')
ROOT_DIR = Path().resolve()
OUT_DIR = ROOT_DIR / 'out'
BUILD_DIR = OUT_DIR / 'build'
DEFAULT_PRESET = ('win' if IS_WINDOWS else 'lin') + '-x64-debug'
TESTS_PRESET = DEFAULT_PRESET
TESTS_EXE_NAME = 'tests'


class Color(Enum):
    BLACK = colorama.Fore.BLACK
    RED = colorama.Fore.RED
    GREEN = colorama.Fore.GREEN
    YELLOW = colorama.Fore.YELLOW
    BLUE = colorama.Fore.BLUE
    MAGENTA = colorama.Fore.MAGENTA
    CYAN = colorama.Fore.CYAN
    WHITE = colorama.Fore.WHITE
    RESET = colorama.Fore.RESET


def colored(text: str, color: Color) -> str:
    return color.value + text + colorama.Style.RESET_ALL


def print_err(text: str, **kwargs: Any) -> None:
    print(colored(text, Color.RED), file=sys.stderr, **kwargs)


def print_hr() -> None:
    SYMBOL = '-'
    WIDTH = 99
    print(SYMBOL * WIDTH)


def get_os_specific_exe_name(name: str) -> str:
    return name + ('.exe' if IS_WINDOWS else '')


def get_os_specific_script_name(name: str) -> str:
    return name + ('.bat' if IS_WINDOWS else '.sh')


class UnknownAction(Exception):
    pass


class ActionError(Exception):
    pass


class ActionCancel(Exception):
    pass


class Console:
    CONSOLE_ENCODING = 'oem' if IS_WINDOWS else locale.getpreferredencoding()

    class ShellCommandError(Exception):
        pass

    class GetEnvError(Exception):
        pass

    class ShellCommandOutput(Enum):
        DEFAULT = auto()
        SUPPRESS = auto()
        CAPTURE = auto()
        CAPTURE_COMBINED = auto()

    @dataclass
    class ShellCommandResult:
        exit_code: int
        stdout: str
        stderr: str

    @staticmethod
    def run_shell_command(
            command: str,
            *,
            cwd: Path | None = None,
            env: Mapping[str, str] | None = None,
            check_exit_code: bool = True,
            error_exception: type[Exception] = ShellCommandError,
            output: ShellCommandOutput = ShellCommandOutput.DEFAULT,
            ) -> ShellCommandResult:
        output_options: dict[str, int | None] = {}
        if output == Console.ShellCommandOutput.DEFAULT:
            output_options['stdout'] = None
            output_options['stderr'] = None
        elif output == Console.ShellCommandOutput.SUPPRESS:
            output_options['stdout'] = subprocess.DEVNULL
            output_options['stderr'] = subprocess.DEVNULL
        elif output == Console.ShellCommandOutput.CAPTURE:
            output_options['stdout'] = subprocess.PIPE
            output_options['stderr'] = subprocess.PIPE
        elif output == Console.ShellCommandOutput.CAPTURE_COMBINED:
            output_options['stdout'] = subprocess.PIPE
            output_options['stderr'] = subprocess.STDOUT
        else:
            raise ValueError(f'Unknown "output" argument value ({output})')

        completed_process = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                shell=True,
                check=False,
                encoding=Console.CONSOLE_ENCODING,
                **output_options,
                )

        stdout = completed_process.stdout or ''
        stderr = completed_process.stderr or ''

        if check_exit_code and completed_process.returncode != 0:
            msg = f'({completed_process.returncode})'
            stderr_msg = stderr.strip()
            msg += f' {stderr_msg}' if stderr_msg else ''
            raise error_exception(msg)

        return Console.ShellCommandResult(
                exit_code=completed_process.returncode,
                stdout=stdout.strip(),
                stderr=stderr.strip(),
                )

    @staticmethod
    def get_shell_script_environ(script_file: Path | str) -> dict[str, str]:
        if IS_WINDOWS:
            command = f'"{script_file}" > nul && set'
        else:
            command = f'. "{script_file}" > /dev/null && env'

        result = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                encoding=Console.CONSOLE_ENCODING,
                )
        if result.returncode != 0:
            error_message = f'Error getting environment ({result.stderr.strip()})'
            raise Console.GetEnvError(error_message)

        records = re.findall(r'^(.*?)=(.*)$', result.stdout.strip(), re.MULTILINE)
        return dict(records)

    @staticmethod
    def input_string(prompt: str, *, allow_empty: bool = True) -> str:
        while True:
            print(f'{prompt} ', end='', flush=True)
            text = input()
            if text or allow_empty:
                return text

    @staticmethod
    def input_int(prompt: str) -> int | None:
        while True:
            text = Console.input_string(prompt)
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                pass

    @staticmethod
    def choose_yn(prompt: str, *, default: bool | None = None) -> bool:
        while True:
            text = Console.input_string(prompt)
            if not text and default is not None:
                return default
            if text.lower() in ['y', 'yes']:
                return True
            if text.lower() in ['n', 'no']:
                return False

    @staticmethod
    def select(
            prompt: str,
            variants: dict[str, Any],
            ) -> Any | None:  # noqa: ANN401
        for i, variant in enumerate(variants, start=1):
            print(f'{i}: {variant}')
        while True:
            user_input = Console.input_int(prompt)
            if user_input is None:
                return None
            index = user_input - 1
            if 0 <= index < len(variants):
                values = list(variants.values())
                return values[index]

    @staticmethod
    def pause(desc: str) -> None:
        Console.input_string(f'Press Enter to {desc}...')

    @staticmethod
    def clear() -> None:
        os.system('cls' if IS_WINDOWS else 'clear')


class BaseAction:
    PROMPT_SHORTCUT: str | None = None
    CLI_COMMAND: str | None = None
    DESC: str | None = None

    def __init__(self) -> None:
        self.manager = None

    def cli_add_subparser(self, subparsers) -> None:  # noqa: ANN001
        if not self.CLI_COMMAND:
            return
        subparser = subparsers.add_parser(self.CLI_COMMAND)
        subparser.set_defaults(func=self.execute)
        self._cli_add_args(subparser)

    def _cli_add_args(self, subparser: argparse.ArgumentParser) -> None:
        pass

    def execute(self, **kwargs: Any) -> None:
        pass


class BaseActionManager:
    def __init__(self) -> None:
        self._init_actions()
        self._init_presets()
        self._init_active_preset()

    def _init_actions(self) -> None:
        self.actions = [ActionClass() for ActionClass in BaseAction.__subclasses__()]
        for action in self.actions:
            action.manager = self

    def _init_presets(self) -> None:
        try:
            command_result = Console.run_shell_command(
                    command='cmake --list-presets=build',
                    cwd=ROOT_DIR,
                    output=Console.ShellCommandOutput.CAPTURE,
                    )
        except Console.ShellCommandError:
            sys.exit('Error: cannot get preset list')

        # pattern demo: https://regex101.com/r/WpzP7d/1
        pattern = r'(?<=")[\w-]+(?=")'
        self.presets = re.findall(pattern, command_result.stdout)
        if not self.presets:
            sys.exit('Error: presets not found')

    def _init_active_preset(self) -> None:
        if DEFAULT_PRESET in self.presets:
            self.active_preset = DEFAULT_PRESET
        else:
            self.active_preset = self.presets[0]

    def start(self) -> None:
        pass


class InteractiveActionManager(BaseActionManager):
    def start(self) -> None:
        while True:
            self._process_user_command()

    def _process_user_command(self) -> None:
        print(self._generate_prompt(), end='', flush=True)
        user_input = input()

        try:
            actions = self._get_actions_to_execute(user_input)
        except UnknownAction as ex:
            print_err(f'Unknown action "{ex}"')
            print_err('--- ERROR ---')
            return

        is_multiple_actions = len(actions) > 1
        for action in actions:
            if is_multiple_actions:
                print(f'--- {action.DESC} ---')

            try:
                action.execute()

            except ActionError as ex:  # noqa: PERF203
                error_message = str(ex)
                if error_message:
                    print_err(error_message)

                if is_multiple_actions:
                    print_err(f'--- ERROR ({action.DESC}) ---')
                else:
                    print_err('--- ERROR ---')

                return

            except ActionCancel:
                return

    def _generate_prompt(self) -> str:
        return colored(f'\n{self.active_preset}> ', Color.GREEN)

    def _get_actions_to_execute(self, user_input: str) -> list[BaseAction]:
        tokens = user_input.strip().split()
        return [self._get_action_by_shortcut(token) for token in tokens]

    def _get_action_by_shortcut(self, shortcut: str) -> BaseAction:
        for action in self.actions:
            if shortcut == action.PROMPT_SHORTCUT:
                return action
        raise UnknownAction(shortcut)


class CliActionManager(BaseActionManager):
    def __init__(self) -> None:
        super().__init__()
        self._init_action_subparsers()

    def _init_action_subparsers(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        for action in self.actions:
            action.cli_add_subparser(subparsers)

        self._options = parser.parse_args()

    def start(self) -> None:
        try:
            self._execute_action()

        except ActionError as ex:
            error_message = str(ex)
            if error_message:
                print_err(error_message)

            sys.exit('--- ERROR ---')

        except ActionCancel:
            sys.exit()

    def _execute_action(self) -> None:
        options = self._options.__dict__.copy()
        del options['func']
        self._options.func(**options)


class PresetArg:
    def _cli_add_args(self, subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
                '--preset',
                type=str,
                required=False,
                )


class PresetSelectAction(BaseAction):
    PROMPT_SHORTCUT = 'p'
    DESC = 'Preset select'

    def execute(self) -> None:
        variants = {self._decorate_preset(preset): preset for preset in self.manager.presets}
        selected_preset = Console.select(prompt='Select preset:', variants=variants)

        if selected_preset is None:
            raise ActionCancel

        self.manager.active_preset = selected_preset

    def _decorate_preset(self, preset: str) -> str:
        if preset == self.manager.active_preset:
            return colored(preset, Color.CYAN)
        else:
            return preset

    def _get_active_preset_num(self) -> int:
        return self.manager.presets.index(self.manager.active_preset) + 1


class PresetListAction(BaseAction):
    PROMPT_SHORTCUT = 'pl'
    CLI_COMMAND = 'presets'
    DESC = 'Preset list'

    def execute(self) -> None:
        Console.run_shell_command(
                command='cmake --list-presets=all',
                cwd=ROOT_DIR,
                error_exception=ActionError,
                )


class VcpkgLibListAction(BaseAction):
    PROMPT_SHORTCUT = 'll'
    DESC = 'VCPKG lib list'

    def execute(self) -> None:
        vcpkg_installed_dir = BUILD_DIR / self.manager.active_preset / 'vcpkg_installed'
        Console.run_shell_command(
                command=f'vcpkg list --x-install-root="{vcpkg_installed_dir}"',
                cwd=ROOT_DIR,
                error_exception=ActionError,
                )


class CleanAction(BaseAction):
    PROMPT_SHORTCUT = 'cl'
    CLI_COMMAND = 'clean'
    DESC = 'Clean'

    def execute(self) -> None:
        print('Cleaning up...')

        if not OUT_DIR.is_dir():
            return

        try:
            shutil.rmtree(OUT_DIR)
        except OSError as ex:
            error_message = f'Unable to remove out dir ({ex})'
            raise ActionError(error_message)


class BuildAction(PresetArg, BaseAction):
    PROMPT_SHORTCUT = 'b'
    CLI_COMMAND = 'build'
    DESC = 'Build'

    def execute(self, preset: str | None = None) -> None:
        preset = preset or self.manager.active_preset
        env = self._get_build_env()

        def run_command(command: str) -> None:
            Console.run_shell_command(
                    command=command,
                    cwd=ROOT_DIR,
                    env=env,
                    error_exception=ActionError,
                    )

        ninja_build_file = BUILD_DIR / preset / 'build.ninja'
        if not ninja_build_file.is_file():
            print('Configuring...')
            run_command(f'cmake --preset={preset}')

        print('Building...\n')
        run_command(f'cmake --build --preset={preset}')

    @staticmethod
    @functools.cache
    def _get_build_env() -> dict[str, str] | None:
        setvars_script_names = ('setvars.user', 'setvars')

        for script_name in setvars_script_names:
            script_file = ROOT_DIR / get_os_specific_script_name(script_name)
            if script_file.is_file():
                return BuildAction._get_env_from_setvars_script(script_file)

        return None

    @staticmethod
    def _get_env_from_setvars_script(script_file: Path) -> dict[str, str]:
        print('Activating build environment...')

        try:
            return Console.get_shell_script_environ(script_file)
        except Console.GetEnvError as ex:
            raise ActionError(str(ex))


class RebuildAction(PresetArg, BaseAction):
    PROMPT_SHORTCUT = 'rb'
    CLI_COMMAND = 'rebuild'
    DESC = 'Rebuild'

    def execute(self, preset: str | None = None) -> None:
        preset = preset or self.manager.active_preset
        CleanAction().execute()
        BuildAction().execute(preset)


class RunAction(BaseAction):
    PROMPT_SHORTCUT = 'r'
    DESC = 'Run executable'

    def execute(self) -> None:
        executables = self._find_executables()
        if not executables:
            raise ActionError('Executables not found')

        variants = {exe.name: exe for exe in sorted(executables)}
        selected_exe = Console.select(prompt='Select executable:', variants=variants)

        if selected_exe is None:
            raise ActionCancel

        print(f'Executing "{selected_exe.relative_to(BUILD_DIR)}"...')
        print_hr()
        Console.run_shell_command(
                command=f'"{selected_exe}"',
                cwd=ROOT_DIR,
                error_exception=ActionError,
                )

    def _find_executables(self) -> list[Path]:
        dir_to_search = BUILD_DIR / self.manager.active_preset

        def is_executable(item: Path) -> bool:
            if not item.is_file():
                return False
            if IS_WINDOWS:
                return item.suffix == '.exe'
            else:
                return os.access(item, os.X_OK) and item.suffix != '.so'

        executables = [item for item in dir_to_search.glob('*') if is_executable(item)]
        executables = [exe for exe in executables if
                       exe.name != get_os_specific_exe_name(TESTS_EXE_NAME)]
        return executables


class RunTestsAction(BaseAction):
    PROMPT_SHORTCUT = 't'
    CLI_COMMAND = 'tests'
    DESC = 'Run tests'

    def execute(self) -> None:
        if self.manager.active_preset != TESTS_PRESET:
            raise ActionError(f'Select preset "{TESTS_PRESET}"')

        exe = BUILD_DIR / TESTS_PRESET / get_os_specific_exe_name(TESTS_EXE_NAME)
        exe_relative_to_build_dir = exe.relative_to(BUILD_DIR)
        if not exe.is_file():
            raise ActionError(f'Tests executable "{exe_relative_to_build_dir}" not found')

        print(f'Executing "{exe_relative_to_build_dir}"...')
        print_hr()
        Console.run_shell_command(
                command=f'"{exe}"',
                cwd=ROOT_DIR,
                error_exception=ActionError,
                )


class ExitAction(BaseAction):
    PROMPT_SHORTCUT = 'x'
    DESC = 'Exit'

    def execute(self) -> None:
        sys.exit()


class HelpAction(BaseAction):
    PROMPT_SHORTCUT = '?'
    DESC = 'Show action list'

    def execute(self) -> None:
        for action in self.manager.actions:
            print(f'  {action.PROMPT_SHORTCUT:2}  {action.DESC}')


def start_interactive_mode() -> None:
    try:
        InteractiveActionManager().start()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        Console.pause('exit')
        sys.exit(1)


def start_cli_mode() -> None:
    CliActionManager().start()


def get_decorated_root_dir() -> str:
    absolute_path = ROOT_DIR

    if IS_WINDOWS:
        return str(absolute_path)

    home_dir = Path.home().resolve()

    if absolute_path == home_dir:
        return '~'

    try:
        relative_path = absolute_path.relative_to(home_dir)
        return f'~/{relative_path}'
    except ValueError:
        return str(absolute_path)


def update_console_title() -> None:
    console_title = f'Actions ({get_decorated_root_dir()})'
    print(colorama.ansi.set_title(console_title), end='', flush=True)


def main() -> None:
    if IS_WINDOWS:
        colorama.init()

    update_console_title()

    if not sys.argv[1:]:
        start_interactive_mode()
    else:
        start_cli_mode()


if __name__ == '__main__':
    main()
