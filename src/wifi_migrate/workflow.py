"""Shared local conversion workflows for the desktop and command line."""
from datetime import datetime
import os
from pathlib import Path
import subprocess
from time import perf_counter

from .errors import MigrationError
from .formats import load
from .outputs import export_run


def new_run():
    return Path('runs') / datetime.now().strftime('%Y%m%d-%H%M%S-%f')


def log_failure(entrypoint, error):
    """Record a diagnostic category without input paths, SSIDs, or exception text."""
    path = Path('runs/errors.log')
    try:
        path.parent.mkdir(exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(f'{datetime.now().isoformat(timespec="seconds")} {entrypoint} {type(error).__name__}\n')
    except OSError:
        pass


def convert_run(path, output, password=None, make_qr=True):
    started = perf_counter()
    records, digest, kind = load(path, password)
    parse_seconds = round(perf_counter() - started, 3)
    return records, output, export_run(records, output, digest, kind, make_qr, parse_seconds=parse_seconds)


def windows_run(output):
    if os.name != 'nt':
        raise MigrationError('此入口仅在 Windows 上可用。')
    output = Path(output)
    if output.exists():
        raise MigrationError('输出目录已存在。')
    raw = output / 'windows-profiles'
    raw.mkdir(parents=True)
    response = subprocess.run(['netsh.exe', 'wlan', 'export', 'profile', 'key=clear', 'folder=' + str(raw.resolve())],
                              text=True, encoding='utf-8', errors='replace', capture_output=True,
                              timeout=120, shell=False, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if response.returncode:
        raise MigrationError('Windows 配置未导出，请检查无线服务及运行权限。')
    records, digest, kind = load(raw)
    result = output / 'result'
    return records, result, export_run(records, result, digest, kind)
