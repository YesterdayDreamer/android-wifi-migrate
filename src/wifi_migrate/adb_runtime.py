"""Locate an existing ADB or install Google's Platform Tools on demand."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen
import zipfile

from .errors import MigrationError

PROJECT = Path(__file__).resolve().parents[2]
OFFICIAL_PAGE = 'https://developer.android.com/tools/releases/platform-tools#downloads'
GOOGLE_DOWNLOAD = 'https://dl.google.com/android/repository/platform-tools-latest-'
ADB_NAME = 'adb.exe' if os.name == 'nt' else 'adb'


def app_data():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'AndroidWiFiBackupToolkit'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'AndroidWiFiBackupToolkit'


def discover(project=PROJECT, state=None):
    project = Path(project)
    state = Path(state) if state is not None else app_data()
    try:
        settings = json.loads((state / 'adb.json').read_text(encoding='utf-8'))
        saved = settings.get('path') if isinstance(settings, dict) else None
    except (OSError, ValueError):
        saved = None
    candidates = [saved, os.environ.get('ADB_PATH')]
    nearby = (project, project.parent, project.parent.parent)
    candidates += [root / 'platform-tools' / ADB_NAME for root in nearby]
    candidates += [root / folder / ADB_NAME for root in nearby for folder in ('tools/adb', '工具/adb', 'adb')]
    candidates += [state / 'tools/platform-tools' / ADB_NAME, shutil.which('adb')]
    for name in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        if os.environ.get(name):
            candidates.append(Path(os.environ[name]) / 'platform-tools' / ADB_NAME)
    candidates += [root / 'platform-tools' / ADB_NAME for root in (
        Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Android/Sdk',
        Path.home() / 'Android/Sdk', Path.home() / 'Library/Android/sdk',
    )]
    return next((Path(path).resolve() for path in candidates
                 if isinstance(path, (str, Path)) and Path(path).is_file()), None)


def adb_version(path):
    try:
        result = subprocess.run([str(path), 'version'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=10,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MigrationError('ADB 无法运行，请选择完整的 Platform Tools 目录中的程序。') from error
    if result.returncode or 'Android Debug Bridge version' not in result.stdout:
        raise MigrationError('所选程序未通过 adb version 校验。')
    return result.stdout.splitlines()[0]


def remember(path, state=None):
    path = Path(path).resolve()
    version = adb_version(path)
    state = Path(state) if state is not None else app_data()
    state.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=state, delete=False) as stream:
        temp = Path(stream.name)
        json.dump({'path': str(path)}, stream, ensure_ascii=False)
    try:
        temp.replace(state / 'adb.json')
    finally:
        temp.unlink(missing_ok=True)
    return path, version


def unpack_platform_tools(archive, destination):
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if not entries or sum(entry.file_size for entry in entries) > 256 * 1024 * 1024:
            raise MigrationError('Platform Tools ZIP 的内容或大小不符合预期。')
        for entry in entries:
            parts = entry.filename.rstrip('/').split('/')
            if parts[0] != 'platform-tools' or any(p in ('', '.', '..') or ':' in p or '\\' in p for p in parts):
                raise MigrationError('Platform Tools ZIP 中有无效路径。')
        package.extractall(destination)
        for entry in entries:
            if not entry.is_dir():
                path = destination / entry.filename
                if entry.external_attr >> 16 & 0o111:
                    path.chmod(path.stat().st_mode | 0o111)
    executable = destination / 'platform-tools' / ADB_NAME
    if not executable.is_file():
        raise MigrationError('下载包缺少 ADB 程序。')
    return executable


def install_platform_tools(progress, state=None):
    state = Path(state) if state is not None else app_data()
    platform = {'win32': 'windows', 'darwin': 'darwin', 'linux': 'linux'}.get(sys.platform)
    if platform is None:
        raise MigrationError('当前平台请手动选择 ADB。')
    tools = state / 'tools'
    tools.mkdir(parents=True, exist_ok=True)
    target = tools / 'platform-tools'
    if target.exists():
        return remember(target / ADB_NAME, state)
    with tempfile.TemporaryDirectory(prefix='.download-', dir=tools) as folder:
        stage = Path(folder)
        archive = stage / 'platform-tools.zip'
        try:
            with urlopen(GOOGLE_DOWNLOAD + platform + '.zip', timeout=25) as response, archive.open('wb') as stream:
                total = int(response.headers.get('Content-Length') or 0)
                received = 0
                for chunk in iter(lambda: response.read(256 * 1024), b''):
                    received += len(chunk)
                    if received > 128 * 1024 * 1024:
                        raise MigrationError('Platform Tools 下载超过预期大小。')
                    stream.write(chunk)
                    progress(received, total)
            if total and received != total:
                raise MigrationError('下载不完整，请重试。')
            executable = unpack_platform_tools(archive, stage)
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            raise MigrationError('Google 下载或 ZIP 校验失败。可重试，或手动选择已解压的 ADB。') from error
        adb_version(executable)
        try:
            executable.parent.rename(target)
        except OSError:
            if not (target / ADB_NAME).is_file():
                raise
    return remember(target / ADB_NAME, state)
