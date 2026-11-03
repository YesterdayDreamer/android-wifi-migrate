"""WiFi configuration parsing and loss-aware conversion; no device access."""
from __future__ import annotations
import collections
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from .errors import MigrationError
BackupError = MigrationError

SECURITY = {0: 'Open', 1: 'WEP', 2: 'WPA2-Personal', 3: 'WPA-Enterprise',
            4: 'WPA3-Personal', 5: 'WPA3-Enterprise-192', 6: 'OWE',
            7: 'WAPI-PSK', 8: 'WAPI-CERT', 9: 'WPA3-Enterprise',
            10: 'OSEN', 11: 'Passpoint-R1-R2', 12: 'Passpoint-R3', 13: 'DPP'}
APP_SECURITY = {0: 'OPEN', 1: 'WEP', 2: 'WPA2', 4: 'WPA3', 6: 'OWE'}
PORTABLE_SECURITY = {(0,), (1,), (2,), (4,), (6,), (0, 6), (2, 4)}
APP_METERED = {0: 'NONE', 1: 'METERED', 2: 'NOT_METERED'}
APP_MAC_RANDOMIZATION = {0: 'NONE', 1: 'PERSISTENT', 2: 'NON_PERSISTENT', 3: 'AUTO'}
NETWORK_SECTIONS = re.compile(
    rb'<(IpConfiguration|WifiEnterpriseConfiguration|NetworkStatus)\b[^>]*>.*?</\1>', re.S)

def unquote(value):
    # XML entities are already decoded by ElementTree. Preserve real whitespace.
    return value[1:-1] if len(value) >= 2 and value.startswith('"') and value.endswith('"') else value


def parse_settings(data):
    blocks = list(re.finditer(rb'<WifiConfiguration\b[^>]*>.*?</WifiConfiguration>', data, re.S))
    starts = len(re.findall(rb'<WifiConfiguration\b[^>]*>', data))
    if not blocks or len(blocks) != starts:
        raise BackupError('No complete WifiConfiguration records, or XML is truncated')
    records = []
    for index, match in enumerate(blocks, 1):
        try:
            node = ET.fromstring(match.group())
        except ET.ParseError as error:
            raise BackupError(f'Invalid XML in record {index}') from error
        values = {e.get('name'): (e.text or e.get('value') or '')
                  for e in node if e.get('name') and e.tag != 'null'}
        ssid = unquote(values.get('SSID', ''))
        if not ssid and values.get('OriSsid'):
            try:
                ssid = bytes.fromhex(values['OriSsid']).decode('utf-8')
            except (ValueError, UnicodeDecodeError):
                raise BackupError(f'Cannot decode SSID in record {index}')
        if not ssid:
            raise BackupError(f'Missing SSID in record {index}')
        types = sorted({int(e.get('value')) for e in node.iter('int') if e.get('name') == 'SecurityType'})
        wep = node.find("string-array[@name='WEPKeys']")
        wep_keys = [unquote(e.get('value', e.text or '')) for e in wep] if wep is not None else []
        wep_index = int(values.get('WEPTxKeyIndex', '0'))
        if not types:
            # Android BitSet.toByteArray uses little-endian bytes. Unknown bits stay unknown.
            raw_bits = values.get('AllowedKeyMgmt', '').strip()
            try:
                bits = int.from_bytes(bytes.fromhex(raw_bits), 'little')
            except ValueError:
                bits = 0
            known = {1: 2, 2: 3, 3: 3, 8: 4, 9: 6}
            types = sorted({kind for bit, kind in known.items() if bits & (1 << bit)})
            if bits & 1:
                types.append(1 if any(wep_keys) else 0)
            if bits & ~sum(1 << bit for bit in (0, 1, 2, 3, 8, 9)):
                types.append(-1)
            types = sorted(set(types))
        password = unquote(values.get('PreSharedKey', ''))
        if 1 in types and 0 <= wep_index < len(wep_keys):
            password = wep_keys[wep_index]
        digest = hashlib.sha256(json.dumps([index, ssid, types], ensure_ascii=False).encode()).hexdigest()[:10]
        record = {'id': f'{index:04d}-{digest}', 'ssid': ssid, 'password': password,
                  'security_types': types, 'security': [SECURITY.get(t, f'Unknown-{t}') for t in types],
                  'hidden': values.get('HiddenSSID') == 'true', 'wep_keys': wep_keys,
                  'wep_tx_key_index': wep_index, 'autojoin': values.get('AutoJoinEnabled', 'true') == 'true',
                  'private': values.get('Shared', 'true') != 'true',
                  'metered_override': int(values.get('MeteredOverride', '0')),
                  'mac_randomization_setting': int(values.get('MacRandomizationSetting', '3'))}
        record['source'] = 'android-settings'
        record['config_key'] = values.get('ConfigKey')
        record['raw_wifi_configuration'] = match.group().decode('utf-8')
        record['security_params'] = [
            {e.get('name'): e.get('value', e.text) for e in param if e.get('name')}
            for param in node.iter('SecurityParams')
        ]
        next_block = blocks[index].start() if index < len(blocks) else len(data)
        network_end = data.find(b'</Network>', match.end(), next_block)
        for section in NETWORK_SECTIONS.finditer(data, match.end(), network_end if network_end >= 0 else next_block):
            section_xml = section.group().decode('utf-8')
            key = {b'IpConfiguration': 'ip_configuration', b'WifiEnterpriseConfiguration': 'enterprise_configuration',
                   b'NetworkStatus': 'network_status'}[section.group(1)]
            record['raw_' + key] = section_xml
            record[key] = {e.get('name'): e.get('value', e.text)
                           for e in ET.fromstring(section_xml) if e.get('name')}
        record['missing_fields'] = [
            field for field, name in (
                ('autojoin', 'AutoJoinEnabled'), ('private', 'Shared'),
                ('metered_override', 'MeteredOverride'), ('mac_randomization_setting', 'MacRandomizationSetting'),
            ) if name not in values
        ]
        records.append(record)
    return records


def qr_values(record):
    types = set(record['security_types'])
    if tuple(sorted(types)) not in PORTABLE_SECURITY:
        return None, 'unsupported_security'
    if types == {0, 6}:
        return None, 'owe_transition_requires_device_support'
    if '\x00' in record['ssid'] or '\x00' in record['password']:
        return None, 'unsupported_nul_character'
    if 2 in types:
        kind, key = 'WPA', record['password']
    elif 1 in types:
        kind, key = 'WEP', record['password']
    elif 0 in types:
        kind, key = 'nopass', ''
    else:
        # Pure SAE and pure OWE need scanner-specific support. Never relabel as Open/WPA2.
        return None, 'pure_sae_or_owe_requires_device_support'
    if kind != 'nopass' and (not key or key == '*'):
        return None, 'missing_or_masked_key'
    return (kind, record['ssid'], key, record['hidden']), (
        'wpa2_compatibility_only' if types == {2, 4} else 'ready')


def escape_wifi(value):
    return ''.join('\\' + char if char in '\\;,:"' else char for char in value)


def qr_payload(record):
    values, reason = qr_values(record)
    if values is None:
        return None, reason
    kind, ssid, key, hidden = values
    return f'WIFI:T:{kind};S:{escape_wifi(ssid)};P:{escape_wifi(key)};H:{str(hidden).lower()};;', reason


def app_record(record):
    types = record['security_types']
    if tuple(sorted(types)) not in PORTABLE_SECURITY or set(types) == {0, 6}:
        return None
    if any(t in (1, 2, 4) for t in types) and (not record['password'] or record['password'] == '*'):
        return None
    # Raw 64-hex PSKs are quoted as passphrases by the app's current converter; keep these out.
    if 2 in types and re.fullmatch('[0-9a-fA-F]{64}', record['password']):
        return None
    item = {'ssid': record['ssid'], 'security': [APP_SECURITY[t] for t in types],
            'password': record['password'], 'hidden': record['hidden'],
            'autojoin': record['autojoin'], 'private': record['private'],
            'meteredOverride': APP_METERED.get(record['metered_override'], 'NONE'),
            'macRandomizationSetting': APP_MAC_RANDOMIZATION.get(record['mac_randomization_setting'], 'AUTO')}
    if isinstance(record.get('note'), str):
        item['note'] = record['note']
    return item


def summarize(records):
    return {'records': len(records), 'unique_ssids': len({r['ssid'] for r in records}),
            'security_combinations': dict(collections.Counter('/'.join(r['security']) or 'Unknown' for r in records)),
            'qr_ready': sum(qr_payload(r)[0] is not None for r in records),
            'app_format_candidates': sum(app_record(r) is not None for r in records)}


def normalize(records):
    """Validate external JSON/CSV and assign unique, password-independent record IDs."""
    if not records:
        raise MigrationError('没有找到网络记录。')
    result = []
    for index, original in enumerate(records, 1):
        if not isinstance(original, dict):
            raise MigrationError(f'第 {index} 条记录不是对象。')
        ssid, password = original.get('ssid'), original.get('password', '')
        types = original.get('security_types')
        if not isinstance(ssid, str) or not ssid or not isinstance(password, str):
            raise MigrationError(f'第 {index} 条名称或密码不是有效文本；请勿让表格软件自动转换密钥。')
        if not isinstance(types, list) or any(type(value) is not int for value in types):
            raise MigrationError(f'第 {index} 条安全类型无效。')
        hidden = original.get('hidden', False)
        if type(hidden) is not bool:
            raise MigrationError(f'第 {index} 条隐藏标志无效。')
        item = dict(original)
        types = sorted(set(types))
        digest = hashlib.sha256(json.dumps([index, ssid, types], ensure_ascii=False).encode()).hexdigest()[:10]
        item.update(id=f'{index:04d}-{digest}', ssid=ssid, password=password, security_types=types,
                    security=[SECURITY.get(t, f'Unknown-{t}') for t in types], hidden=hidden)
        for field, default in [('wep_keys', []), ('wep_tx_key_index', 0), ('autojoin', True),
                               ('private', False), ('metered_override', 0), ('mac_randomization_setting', 3)]:
            item.setdefault(field, default)
        if type(item['autojoin']) is not bool or type(item['private']) is not bool:
            raise MigrationError(f'第 {index} 条连接属性无效。')
        if type(item['metered_override']) is not int or type(item['mac_randomization_setting']) is not int:
            raise MigrationError(f'第 {index} 条连接属性无效。')
        result.append(item)
    return result


