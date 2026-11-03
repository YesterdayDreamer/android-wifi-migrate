"""Optional ADB operations. Import is a dry run unless apply=True is explicit."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import time
from collections import Counter, defaultdict
from .errors import MigrationError
from .adb_runtime import discover
from .core import PORTABLE_SECURITY

WPM_PACKAGE = 'io.github.wifi_password_manager'
HELPER_PACKAGE = 'io.github.wifimigrate.importer'
WIFI_ADD_ACTION = 'android.settings.WIFI_ADD_NETWORKS'
SHIZUKU_PACKAGE = 'moe.shizuku.privileged.api'


class Adb:
    def __init__(self, executable=None, runner=None):
        self.executable = executable or discover()
        if not self.executable:
            raise MigrationError('未找到 ADB。请选择 Google Platform Tools 中的 adb，或设置 ADB_PATH。')
        self.runner = runner or subprocess.run

    def run(self, args, *, text=None, timeout=30):
        try:
            return self.runner([str(self.executable), *args], input=text, text=True,
                               encoding='utf-8', errors='replace', capture_output=True,
                               timeout=timeout, shell=False,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MigrationError('ADB 未启动或操作超时；请检查连接和手机授权。') from error

    def devices(self):
        response = self.run(['devices', '-l'])
        if response.returncode:
            raise MigrationError('无法列出 ADB 设备。')
        result = []
        for line in response.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] in ('device', 'offline', 'unauthorized'):
                details = dict(part.split(':', 1) for part in parts[2:] if ':' in part)
                transport = 'USB' if 'usb' in details else '模拟器' if parts[0].startswith('emulator-') else (
                    '网络' if ':' in parts[0] or '._adb-' in parts[0] else '未识别')
                result.append({'serial': parts[0], 'state': parts[1], 'model': details.get('model', ''),
                               'transport': transport})
        return result

    def require_device(self, serial):
        if not serial or not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]+', serial) or serial.startswith('-'):
            raise MigrationError('请明确选择一台设备。')
        if not any(row['serial'] == serial and row['state'] == 'device' for row in self.devices()):
            raise MigrationError('所选设备未连接或尚未授权 USB 调试。')

    def shell(self, serial, command, timeout=30):
        # Credentials travel through stdin, not through the host process command line.
        return self.run(['-s', serial, 'shell', 'sh'], text=command + '\n', timeout=timeout)

    def probe(self, serial):
        self.require_device(serial)
        def prop(name):
            response = self.run(['-s', serial, 'shell', 'getprop', name])
            return response.stdout.strip() if response.returncode == 0 else ''
        help_result = self.run(['-s', serial, 'shell', 'cmd', 'wifi', 'help'])
        # Some Android 12 builds return 255 even though they print valid help.
        text = help_result.stdout + '\n' + help_result.stderr
        lines = text.splitlines()
        line, options = '', ''
        for index, candidate in enumerate(lines):
            if re.match(r'^\s*add-network\s+<ssid>', candidate):
                line = candidate.strip()
                indentation = len(candidate) - len(candidate.lstrip())
                end = next((i for i in range(index + 1, len(lines))
                            if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) <= indentation), len(lines))
                options = '\n'.join(lines[index + 1:end])
                break
        return {'sdk': prop('ro.build.version.sdk'), 'android_release': prop('ro.build.version.release'),
                'model': prop('ro.product.model'),
                'add_network_advertised': bool(line),
                'security_types': sorted(set(re.findall(r'\b(open|owe|wpa2|wpa3|wep)\b', line))),
                'hidden_flag_advertised': bool(re.search(r'(?im)^\s*-h\s+-[^\n]*hidden', options)),
                'disable_autojoin_flag_advertised': bool(re.search(r'(?im)^\s*-d\s+-[^\n]*auto.?join', options)),
                'list_networks_advertised': bool(re.search(r'(?m)^\s*list-networks\s*$', text)),
                'password_export_verified': False, 'system_write_verified': False}

    def backup(self, serial, output, legacy_full=False):
        self.require_device(serial)
        output = Path(output).resolve()
        if output.exists():
            raise MigrationError('备份目标已存在，已停止，避免覆盖。')
        output.parent.mkdir(parents=True, exist_ok=True)
        flags = ['-all', '-shared', '-system', '-keyvalue'] if legacy_full else ['-keyvalue']
        packages = [] if legacy_full else ['com.android.providers.settings']
        result = self.run(['-s', serial, 'backup', *flags, '-f', str(output), *packages], timeout=900)
        if result.returncode or not output.is_file() or output.stat().st_size <= 24:
            raise MigrationError('备份未生成有效数据。检查手机确认框；当前系统也可能禁用了此通道。')
        # Contents are validated by formats.load, not by a successful command or file size.
        return output

    def migration_status(self, serial):
        result = self.probe(serial)
        shizuku = self.run(['-s', serial, 'shell', 'pm', 'path', 'moe.shizuku.privileged.api'])
        wpm = self.run(['-s', serial, 'shell', 'pm', 'path', WPM_PACKAGE])
        helper = self.run(['-s', serial, 'shell', 'pm', 'path', HELPER_PACKAGE])
        handler = self.run(['-s', serial, 'shell', 'cmd', 'package', 'resolve-activity',
                            '--brief', '-a', WIFI_ADD_ACTION])
        service = self.run(['-s', serial, 'shell', 'pidof', 'shizuku_server'])
        wireless = self.run(['-s', serial, 'shell', 'settings', 'get', 'global', 'adb_wifi_enabled'])
        return {**result, 'adb_authorized': True,
                'shizuku_package_visible': 'package:' in shizuku.stdout,
                'shizuku_server_visible': service.returncode == 0 and bool(service.stdout.strip()),
                'wpm_installed': 'package:' in wpm.stdout,
                'helper_installed': 'package:' in helper.stdout,
                'system_add_ui_visible': handler.returncode == 0 and bool(re.search(r'(?m)^\S+/\S+\s*$', handler.stdout)),
                'wireless_debugging_enabled': {'0': False, '1': True}.get(wireless.stdout.strip()),
                'app_authorization': 'check_in_app', 'legacy_backup': 'requires_actual_backup'}

    def install_helper(self, serial, apk):
        self.require_device(serial)
        response = self.run(['-s', serial, 'install', '--no-incremental', '-r', str(Path(apk).resolve())], timeout=180)
        code = re.search(r'\b(INSTALL_[A-Z_]+)\b', response.stdout + '\n' + response.stderr)
        if response.returncode or not re.search(r'(?m)^\s*Success\s*$', response.stdout + '\n' + response.stderr):
            hints = {'INSTALL_FAILED_USER_RESTRICTED': '请在手机上确认安装，检查开发者选项中的 USB 安装权限。',
                     'INSTALL_FAILED_UPDATE_INCOMPATIBLE': '手机上的同名助手签名不同，请使用原签名的 APK。',
                     'INSTALL_FAILED_VERSION_DOWNGRADE': '所选 APK 比手机上已安装的版本旧。'}
            reason = code.group(1) if code else 'ADB 未报告安装成功'
            raise MigrationError(f'助手安装失败（{reason}）。' + hints.get(reason, '请保持手机解锁并核对 APK。'))
        installed = self.run(['-s', serial, 'shell', 'pm', 'path', HELPER_PACKAGE])
        if installed.returncode or 'package:' not in installed.stdout:
            raise MigrationError('ADB 报告安装成功，但未找到本项目助手。请核对所选 APK。')

    def start_shizuku(self, serial):
        self.require_device(serial)
        def shell(*args):
            return self.run(['-s', serial, 'shell', *args])
        if shell('pidof', 'shizuku_server').stdout.strip():
            return 'Shizuku 服务已运行。请在手机打开 WiFi Password Manager 并授权。'
        package = shell('pm', 'path', SHIZUKU_PACKAGE)
        apk = next((line.removeprefix('package:') for line in package.stdout.splitlines()
                    if line.startswith('package:/') and line.endswith('/base.apk')), None)
        if not apk:
            raise MigrationError('所选手机未检测到 Shizuku。请先安装并在手机打开一次。')
        folder = PurePosixPath(apk).parent
        abi = shell('getprop', 'ro.product.cpu.abi').stdout.strip()
        arch = {'arm64-v8a': 'arm64', 'armeabi-v7a': 'arm', 'x86_64': 'x86_64', 'x86': 'x86'}.get(abi)
        starter = folder / 'lib' / arch / 'libshizuku.so' if arch else None
        script = f'/sdcard/Android/data/{SHIZUKU_PACKAGE}/start.sh'
        if starter and shell('test -x ' + shlex.quote(str(starter))).returncode == 0:
            result = shell(shlex.quote(str(starter)))
        elif shell('test -r ' + shlex.quote(script)).returncode == 0:
            result = shell('sh', script)
        else:
            raise MigrationError('找不到 Shizuku 启动文件。请打开手机 Shizuku 的「通过连接电脑启动」，使用它显示的命令。')
        if not result.returncode:
            for _ in range(4):
                if shell('pidof', 'shizuku_server').stdout.strip():
                    return 'Shizuku 服务已启动。请在手机打开 WiFi Password Manager 并授权。'
                time.sleep(0.4)
        raise MigrationError('未检测到 Shizuku 服务。请保持手机解锁，并核对 App 内的电脑启动命令。')

    def launch_helper(self, serial):
        self.require_device(serial)
        package = self.run(['-s', serial, 'shell', 'pm', 'path', HELPER_PACKAGE])
        if 'package:' not in package.stdout:
            raise MigrationError('所选手机还未安装导入助手。请先在这台手机上安装 APK。')
        self.open_activity(serial, HELPER_PACKAGE + '/.ImportActivity')

    def open_shizuku(self, serial):
        self.require_device(serial)
        response = self.run(['-s', serial, 'shell', 'cmd', 'package', 'resolve-activity', '--brief',
                             '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER',
                             SHIZUKU_PACKAGE])
        component = next((line.strip() for line in response.stdout.splitlines()
                          if line.strip().startswith(SHIZUKU_PACKAGE + '/')), None)
        if not component:
            raise MigrationError('未找到 Shizuku 界面，请在所选手机上手动打开。')
        self.open_activity(serial, component)

    def open_activity(self, serial, component):
        response = self.run(['-s', serial, 'shell', 'am', 'start', '-W', '-n', component])
        text = response.stdout + '\n' + response.stderr
        if response.returncode or not re.search(r'(?m)^Status: ok\s*$', text):
            raise MigrationError('手机未确认打开应用。请解锁所选手机，再从应用列表打开。')

    def pull_download(self, serial, filename, directory):
        self.require_device(serial)
        if not re.fullmatch(r'[^/\\\x00-\x1f]+\.(?:json|gz|gzip)', filename, re.I):
            raise MigrationError('请填写 Download 目录中的 JSON 或 GZip 文件名。')
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        output = directory / filename
        response = self.run(['-s', serial, 'pull', '/sdcard/Download/' + filename, str(output)], timeout=120)
        if response.returncode or not output.is_file():
            raise MigrationError('未能复制备份。请确认文件在旧机 Download 目录，或用电脑文件选择器打开。')
        return output

    def push_manager_json(self, serial, source, batch):
        self.require_device(serial)
        source = Path(source).resolve()
        if not source.is_file():
            raise MigrationError('找不到本次导入 JSON，请重新打开备份生成结果。')
        remote = '/sdcard/Download/WiFiMigrate-' + batch + '.json'
        response = self.run(['-s', serial, 'push', str(source), remote], timeout=60)
        if response.returncode:
            error = (response.stdout + response.stderr).lower()
            if 'permission denied' in error:
                raise MigrationError('手机拒绝写入 Download。请解锁手机并检查 ADB 或手动传输 JSON。')
            if 'no space' in error:
                raise MigrationError('手机存储空间不足，无法复制 JSON。')
            raise MigrationError('JSON 传输失败。请检查新机连接或从结果文件夹手动传输。')
        remote_size = self.run(['-s', serial, 'shell', 'wc', '-c', remote])
        if remote_size.returncode or remote_size.stdout.split()[:1] != [str(source.stat().st_size)]:
            raise MigrationError('复制命令已返回，但手机端文件大小未核对成功。请检查 Download。')
        return remote

    def list_networks(self, serial):
        response = self.run(['-s', serial, 'shell', 'cmd', 'wifi', 'list-networks'])
        if response.returncode:
            return None
        visible = []
        for line in response.stdout.splitlines():
            match = re.match(r'^\s*(\d+)\s+(.+?)\s+([A-Za-z0-9_/^\-]+)\s*$', line)
            if match:
                visible.append((match.group(2), match.group(3).upper().replace('^', '')))
        if not visible and not re.search(r'(?i)network\s+id|no saved networks', response.stdout):
            return None
        return visible

    def push_qr(self, serial, run):
        self.require_device(serial)
        files = sorted((Path(run) / 'qr').glob('*.png'))
        if not files:
            raise MigrationError('所选结果目录没有二维码。')
        batch = hashlib.sha256(str(Path(run).resolve()).encode()).hexdigest()[:12]
        remote = '/sdcard/Pictures/WiFiMigrate/' + batch
        created = self.shell(serial, 'mkdir -p ' + shlex.quote(remote))
        if created.returncode:
            raise MigrationError('无法创建手机上的二维码专用目录。')
        for file in files:
            response = self.run(['-s', serial, 'push', str(file), remote + '/' + file.name], timeout=60)
            if response.returncode:
                raise MigrationError('部分二维码传输失败，可重试；不会删除手机原有照片。')
        return {'copied': len(files), 'remote_directory': remote,
                'note': '仅复制二维码；相册是否刷新及扫码保存结果需在手机上确认。'}


def plan_record(record, capabilities):
    types = set(record['security_types'])
    if tuple(sorted(types)) not in PORTABLE_SECURITY:
        return None, 'unsupported_security'
    if types == {0, 6}:
        return None, 'owe_transition_requires_device_support'
    if record['hidden'] and not capabilities.get('hidden_flag_advertised'):
        return None, 'hidden_flag_unverified'
    if not record.get('autojoin', True) and not capabilities.get('disable_autojoin_flag_advertised'):
        return None, 'autojoin_flag_unverified'
    if any(char in record['ssid'] + record['password'] for char in ('\0', '\n', '\r')):
        return None, 'control_character_unhandled'
    kind = 'wpa2' if 2 in types else 'wep' if 1 in types else 'wpa3' if 4 in types else 'open' if 0 in types else 'owe'
    if not capabilities.get('add_network_advertised') or kind not in capabilities.get('security_types', []):
        return None, 'command_or_security_not_advertised'
    password = record['password']
    if kind in ('wpa2', 'wpa3', 'wep') and (not password or password == '*'):
        return None, 'missing_or_masked_key'
    if kind == 'wpa2' and re.fullmatch('[0-9a-fA-F]{64}', password):
        return None, 'raw_psk_not_supported_by_shell_wrapper'
    if kind == 'wpa2' and not 8 <= len(password) <= 63:
        return None, 'invalid_wpa2_passphrase_length'
    if kind == 'wep' and record.get('wep_tx_key_index', 0) != 0:
        return None, 'nonzero_wep_index_not_supported'
    if not 1 <= len(record['ssid'].encode('utf-8')) <= 32:
        return None, 'invalid_ssid_byte_length'
    # Avoid overwriting networks that differ only by leading/trailing whitespace in list output.
    if record['ssid'] != record['ssid'].strip():
        return None, 'ssid_whitespace_readback_ambiguous'
    args = ['cmd', 'wifi', 'add-network', record['ssid'], kind]
    if kind in ('wpa2', 'wpa3', 'wep'):
        args.append(password)
    if record['hidden']:
        args.append('-h')
    if not record.get('autojoin', True):
        args.append('-d')
    return (kind, args), 'wpa2_compatibility_only' if types == {2, 4} else 'ready'


def visible_as(visible, ssid, kind):
    aliases = {'wpa2': {'WPA2', 'WPA2_PSK', 'WPA_PSK', 'PSK'}, 'wpa3': {'WPA3', 'SAE'},
               'open': {'OPEN', 'NONE'}, 'owe': {'OWE'}, 'wep': {'WEP'}}
    return visible is not None and any(name == ssid and aliases[kind].intersection(security.split('/')) for name, security in visible)


def import_report_path(directory, serial):
    target_hash = hashlib.sha256(serial.encode()).hexdigest()[:12]
    return Path(directory) / f'adb-import-{target_hash}.json'


def import_records(adb, serial, records, output, *, apply=False, limit=None, resume=False,
                   first_ready=False, confirm_trial=False, source_id=None):
    capabilities = adb.probe(serial)
    selected = records[:limit] if limit is not None else records
    if limit is not None and limit < 1:
        raise MigrationError('单次条数必须大于零。')
    plan = [plan_record(record, capabilities) for record in selected]
    groups = defaultdict(list)
    for index, (record, (planned, _)) in enumerate(zip(selected, plan)):
        if planned:
            groups[(record['ssid'], planned[0])].append(index)
    for indices in groups.values():
        values = {(selected[i]['password'], selected[i]['hidden'], selected[i].get('autojoin', True)) for i in indices}
        if len(values) > 1:
            for index in indices:
                plan[index] = None, 'conflicting_same_ssid_requires_selection'
    if not apply:
        return {'mode': 'dry-run', 'planned': len(selected), 'ready': sum(item[0] is not None for item in plan),
                'skipped': sum(item[0] is None for item in plan), 'capabilities': capabilities,
                'skip_reasons': dict(Counter(reason for item, reason in plan if item is None)),
                'wpa2_compatibility_only': sum(reason == 'wpa2_compatibility_only' for _, reason in plan),
                'note': '没有写入手机。请先单条测试；帮助中有命令不代表拥有写入权限。'}
    if not capabilities.get('add_network_advertised'):
        raise MigrationError('目标手机没有声明 add-network，未进行任何写入。')
    scope = hashlib.sha256(json.dumps([source_id, selected], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if first_ready:
        index = next((i for i, (entry, _) in enumerate(plan) if entry is not None), None)
        if index is None:
            raise MigrationError('没有适合试存的网络，请重新预览或切换迁移方式。')
        selected, plan = [selected[index]], [plan[index]]
    output = Path(output)
    if output.exists() and not resume:
        raise MigrationError('导入记录已存在；请用新路径，或明确指定 resume。')
    previous = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
    target_key = hashlib.sha256(serial.encode()).hexdigest()
    if previous and previous.get('target') != target_key:
        raise MigrationError('恢复记录属于另一台设备，已停止。')
    before = adb.list_networks(serial)
    if previous.get('scope') != scope:
        previous = {}
    trial = previous.get('trial') or {}
    if not first_ready:
        record, planned = next(((row, item) for row, (item, _) in zip(selected, plan)
                                if row['id'] == trial.get('id') and item), (None, None))
        if (not confirm_trial or not planned or planned[0] != trial.get('security')
                or not visible_as(before, record['ssid'], planned[0])):
            raise MigrationError('批量保存需要同一设备和数据范围的试存回读。请重新试存，在手机核对后再确认。')
    report = {'target': target_key, 'scope': scope, 'trial': None if first_ready else trial,
              'results': dict(previous.get('results', {})), 'key_or_connectivity_verified': False}
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(output.name + '.tmp')
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(output)
    if first_ready:
        save()
    for record, (planned, reason) in zip(selected, plan):
        fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result = {'fingerprint': fingerprint, 'status': reason}
        if planned:
            kind, args = planned
            old = previous.get('results', {}).get(record['id'], {})
            if (not first_ready and old.get('fingerprint') == fingerprint
                    and old.get('status') == 'saved_list_visible' and visible_as(before, record['ssid'], kind)):
                result['status'] = 'saved_list_visible'
                result['resumed_without_write'] = True
            else:
                response = adb.shell(serial, shlex.join(args))
                if response.returncode == 0 and re.search(r'(?im)^\s*Save successful\s*$', response.stdout):
                    after = adb.list_networks(serial)
                    result['status'] = 'saved_list_visible' if visible_as(after, record['ssid'], kind) else 'save_acknowledged_unverified'
                else:
                    result['status'] = 'save_failed'
            result['selected_security'] = kind
            result['security_conversion'] = reason
            result['scope'] = 'ssid_key_security_hidden_autojoin_only'
        report['results'][record['id']] = result
        if first_ready and result['status'] == 'saved_list_visible':
            report['trial'] = {'id': record['id'], 'security': result['selected_security']}
        save()
    statuses = [report['results'][row['id']]['status'] for row in selected]
    return {'mode': 'apply', 'processed': len(statuses), 'saved_list_visible': statuses.count('saved_list_visible'),
            'save_acknowledged_unverified': statuses.count('save_acknowledged_unverified'),
            'failed': statuses.count('save_failed'), 'skipped': sum(item[0] is None for item in plan),
            'note': '列表可见不代表密码或联网已验证；连接失败时保留源数据并使用二维码路径。'}
