from __future__ import annotations

import os
from pathlib import Path

DIRS = ['demo_project', 'test']
EXCLUDE_SUBDIRS = []
EXTENSIONS = ['.cpp', '.h']
CLANG_FORMAT_CONFIG_PATH = None


def format_in_dir(target_dir: str) -> None:
    if not target_dir:
        raise Exception('Target dir is empty')

    target_dir = Path(target_dir)
    if not target_dir.is_dir():
        raise Exception(f'Target dir "{target_dir}" not found')

    files = []
    for ext in EXTENSIONS:
        files += target_dir.rglob(f'*{ext}')

    def path_contains_exclude_subdir(path: Path) -> bool:
        return any(path.is_relative_to(subdir) for subdir in EXCLUDE_SUBDIRS)
    files = [file for file in files if not path_contains_exclude_subdir(file)]

    for file in sorted(files):
        print(file)
        command = 'clang-format'
        if CLANG_FORMAT_CONFIG_PATH:
            command += f' --style=file:"{CLANG_FORMAT_CONFIG_PATH}"'
        command += f' -i "{file}"'
        os.system(command)


def main() -> None:
    for target_dir in DIRS:
        format_in_dir(target_dir)


if __name__ == '__main__':
    main()
