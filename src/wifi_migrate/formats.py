"""Adapters retain unknown security types instead of guessing that a network is open."""
from __future__ import annotations
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from .archive import read_settings, MAX_SETTINGS
from .core import APP_MAC_RANDOMIZATION, APP_METERED, normalize, parse_settings
from .errors import MigrationError

AUTH = {'open': 0, 'none': 0, 'nopass': 0, 'wep': 1, 'wpa': 2, 'wpa2': 2,
        'wpa2-personal': 2, 'wpapsk': 2, 'wpa2psk': 2, 'wpa3': 4,
        'wpa3-personal': 4, 'wpa3sae': 4, 'sae': 4, 'owe': 6,
        'wpa/wpa2-enterprise': 3, 'wpa-enterprise': 3, 'wpa3-enterprise': 9}

METERED_BY_NAME = {name: value for value, name in APP_METERED.items()}
MAC_RANDOMIZATION_BY_NAME = {name: value for value, name in APP_MAC_RANDOMIZATION.items()}


def security_names(value):
    if isinstance(value, list):
        return sorted({AUTH.get(str(item).lower(), -1) for item in value})
    # Legacy Authentication may be comma-separated; WPA/WPA2-Enterprise is one name.
    return sorted({AUTH.get(part.strip().lower(), -1) for part in str(value).split(',')})


def boolean(value, default=False):
    if value is None or value == '':
        return default
    if type(value) is bool:
        return value
    if str(value).lower() in ('true', 'yes', '1'):
        return True
    if str(value).lower() in ('false', 'no', '0'):
        return False
    raise MigrationError('布尔属性必须是 true/false、yes/no 或 1/0。')


def json_records(data):
    if isinstance(data, dict):
        if data.get('schema') != 1 or not isinstance(data.get('networks'), list):
            raise MigrationError('不支持该 JSON 主数据版本。')
        return normalize(data['networks'])
    if not isinstance(data, list):
        raise MigrationError('JSON 必须是网络数组或本项目的主数据。')
    records = []
    for row in data:
        if not isinstance(row, dict):
            raise MigrationError('JSON 中含无效网络记录。')
        if 'ssid' in row and 'security' in row:
            record = {'ssid': row['ssid'], 'password': row.get('password', ''),
                      'security_types': security_names(row['security']),
                      'hidden': boolean(row.get('hidden')), 'autojoin': boolean(row.get('autojoin'), True),
                      'private': boolean(row.get('private')),
                      'metered_override': METERED_BY_NAME.get(str(row.get('meteredOverride')), 0),
                      'mac_randomization_setting': MAC_RANDOMIZATION_BY_NAME.get(str(row.get('macRandomizationSetting')), 3)}
            if isinstance(row.get('note'), str):
                record['note'] = row['note']
            extra = {key: value for key, value in row.items() if key not in {
                'ssid', 'password', 'security', 'hidden', 'autojoin', 'private', 'note',
                'meteredOverride', 'macRandomizationSetting',
            }}
            if extra:
                record['unmapped_source_fields'] = extra
            record['source'] = 'wifi-password-manager-json'
            record['missing_fields'] = [
                field for field, key in (
                    ('hidden', 'hidden'), ('autojoin', 'autojoin'), ('private', 'private'),
                    ('metered_override', 'meteredOverride'), ('mac_randomization_setting', 'macRandomizationSetting'),
                ) if row.get(key) is None
            ]
        else:
            record = legacy_row(row)
        records.append(record)
    return normalize(records)


def legacy_row(row):
    password = row.get('Password', row.get('Key', ''))
    if password is None:
        password = ''
    if 'SecurityTypes' in row and row['SecurityTypes']:
        try:
            types = [int(value) for value in row['SecurityTypes'].split(',')]
        except (ValueError, AttributeError) as error:
            raise MigrationError('CSV 安全类型列无效。') from error
    else:
        # SSID/Key-only files do not contain authentication; never infer it from a password.
        types = security_names(row.get('Authentication', 'unknown'))
    return {'ssid': row.get('SSID'), 'password': password, 'security_types': types,
            'hidden': boolean(row.get('Hidden'))}


def windows_records(data):
    root = ET.fromstring(data)
    def value(name, default=''):
        node = root.find('.//{*}' + name)
        return node.text if node is not None and node.text is not None else default
    ssid_node = root.find('.//{*}SSID/{*}name')
    if ssid_node is None or not ssid_node.text:
        raise MigrationError('Windows 配置缺少文本 SSID，暂不支持仅有十六进制名称的配置。')
    auth, cipher = value('authentication').lower(), value('encryption').lower()
    if value('useOneX').lower() == 'true':
        types = [3]
    elif auth == 'open' and cipher == 'wep':
        types = [1]
    elif auth == 'open' and cipher == 'none':
        types = [0]
    else:
        types = [AUTH.get(auth, -1)]
    if root.find('.//{*}sharedKey') is not None and value('protected').lower() != 'false':
        raise MigrationError('Windows 密钥仍受保护，请使用有权限的 key=clear XML 导出，不能直接迁移加密密钥。')
    return [{'ssid': ssid_node.text, 'password': value('keyMaterial'), 'security_types': types,
             'hidden': value('nonBroadcast').lower() == 'true'}]


def load(path, password=None):
    path = Path(path)
    if path.is_dir():
        sources = sorted(path.glob('*.xml'))
        if not sources or len(sources) > 10000:
            raise MigrationError('请选择含 Windows WLAN XML 配置的目录。')
        rows, digest = [], hashlib.sha256()
        for source in sources:
            if source.stat().st_size > MAX_SETTINGS:
                raise MigrationError('XML 文件过大。')
            data = source.read_bytes()
            digest.update(data)
            rows.extend(windows_records(data))
        return normalize(rows), digest.hexdigest(), 'windows-xml-directory'
    with path.open('rb') as stream:
        magic = stream.read(2)
    if magic == b'\x1f\x8b':
        try:
            with gzip.open(path, 'rb') as stream:
                data = stream.read(MAX_SETTINGS + 1)
            if len(data) > MAX_SETTINGS:
                raise MigrationError('GZip 展开后的 JSON 过大。')
            return json_records(json.loads(data.decode('utf-8-sig'))), hashlib.sha256(data).hexdigest(), 'json-gzip'
        except (OSError, EOFError, UnicodeError, json.JSONDecodeError) as error:
            raise MigrationError('GZip 文件不完整或内容不是明文 WiFi JSON。') from error
    if path.suffix.lower() in ('.gz', '.gzip', '.enc'):
        raise MigrationError('格式无法识别。加密的 WiFi Password Manager 备份请在原 App 解密后导出明文 JSON。')
    if path.suffix.lower() in ('.json', '.csv'):
        if path.stat().st_size > MAX_SETTINGS:
            raise MigrationError('输入文件过大。')
        data = path.read_bytes()
        text = data.decode('utf-8-sig')
        if path.suffix.lower() == '.json':
            records = json_records(json.loads(text))
        else:
            records = normalize([legacy_row(row) for row in csv.DictReader(io.StringIO(text))])
        return records, hashlib.sha256(data).hexdigest(), path.suffix[1:]
    data = read_settings(path, password)
    if b'WLANProfile' in data[:4096]:
        records = normalize(windows_records(data))
        kind = 'windows-xml'
    else:
        records = normalize(parse_settings(data))
        kind = 'android-settings'
    return records, hashlib.sha256(data).hexdigest(), kind
