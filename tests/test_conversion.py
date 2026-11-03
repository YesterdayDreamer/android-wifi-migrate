import csv
import json
from pathlib import Path
import tempfile
import unittest
from wifi_migrate.core import parse_settings, normalize, qr_payload, qr_values, app_record
from wifi_migrate.formats import load, windows_records
from wifi_migrate.errors import MigrationError
from fixtures import xml_record


class ConversionTests(unittest.TestCase):
    def test_open_owe_and_transition_exports(self):
        from wifi_migrate.adb import plan_record
        caps = {'add_network_advertised': True, 'security_types': ['open', 'owe', 'wpa2']}
        for types, qr_type, adb_type, app_types in [
            ([0], 'nopass', 'open', ['OPEN']),
            ([6], None, 'owe', ['OWE']),
            ([0, 6], None, None, None),
            ([2, 4], 'WPA', 'wpa2', ['WPA2', 'WPA3']),
            ([0, 2], None, None, None),
            ([127], None, None, None),
        ]:
            with self.subTest(types=types):
                row = normalize([{'ssid': 'SYNTHETIC', 'security_types': types,
                                  'password': 'SyntheticKey42' if 2 in types else ''}])[0]
                values, reason = qr_values(row)
                plan, _ = plan_record(row, caps)
                item = app_record(row)
                self.assertEqual(values[0] if values else None, qr_type)
                self.assertEqual(plan[0] if plan else None, adb_type)
                self.assertEqual(item['security'] if item else None, app_types)
                self.assertEqual(row['security_types'], types)
                if types == [2, 4]:
                    self.assertEqual(reason, 'wpa2_compatibility_only')

    def test_qr_hidden_chinese_wpa2_payload(self):
        row = normalize([{'ssid': '测试;网络', 'password': 'SyntheticKey42',
                          'security_types': [2], 'hidden': True}])[0]
        self.assertEqual(qr_payload(row), ('WIFI:T:WPA;S:测试\\;网络;P:SyntheticKey42;H:true;;', 'ready'))
    def record(self, **kwargs):
        return normalize(parse_settings(xml_record(**kwargs)))[0]

    def test_entities_quotes_and_real_whitespace(self):
        row = self.record(ssid=' SYNTHETIC-&;:网络 ', password='  Synthetic<&;\\,":42  ')
        self.assertEqual(row['ssid'], ' SYNTHETIC-&;:网络 ')
        self.assertEqual(row['password'], '  Synthetic<&;\\,":42  ')
        self.assertIn('\\;', qr_payload(row)[0])

    def test_wep_tx_index(self):
        row = self.record(types=(1,), password='', wep=['', 'ABCDEF0123', '', ''], tx=1)
        self.assertEqual(row['password'], 'ABCDEF0123')
        self.assertEqual(qr_values(row)[0][0], 'WEP')
        self.assertEqual(app_record(row)['security'], ['WEP'])

    def test_same_name_different_keys_preserved(self):
        rows = normalize(parse_settings(xml_record(password='SyntheticOne!42') + xml_record(password='SyntheticTwo!42')))
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])

    def test_unknown_enterprise_not_open(self):
        row = self.record(types=(3, 9))
        self.assertIsNone(qr_payload(row)[0])
        self.assertIsNone(app_record(row))

    def test_pure_sae_owe_not_downgraded(self):
        for kind in (4, 6):
            self.assertIsNone(qr_payload(self.record(types=(kind,)))[0])

    def test_masked_and_missing_keys(self):
        for key in ('', '*'):
            self.assertIsNone(qr_payload(self.record(password=key))[0])

    def test_raw_psk_app_omitted(self):
        self.assertIsNone(app_record(self.record(password='b' * 64, types=(2,))))

    def test_truncated_xml_stops(self):
        with self.assertRaises(MigrationError):
            parse_settings(xml_record() + b'<WifiConfiguration>')

    def test_legacy_bitset_supported(self):
        row = self.record(types=(), extra='<byte-array name="AllowedKeyMgmt" num="1">02</byte-array>')
        self.assertEqual(row['security_types'], [2])

    def test_legacy_unknown_bit_not_open(self):
        row = self.record(types=(), extra='<byte-array name="AllowedKeyMgmt" num="2">0140</byte-array>')
        self.assertIn(-1, row['security_types'])
        self.assertIsNone(qr_payload(row)[0])

    def test_json_numeric_password_rejected(self):
        with self.assertRaises(MigrationError):
            normalize([{'ssid': 'SYNTHETIC-NUMERIC', 'password': 1234, 'security_types': [2]}])

    def test_bool_string_not_silently_true(self):
        with self.assertRaises(MigrationError):
            normalize([{'ssid': 'SYNTHETIC-FLAG', 'password': '', 'security_types': [0], 'hidden': 'false'}])

    def test_csv_preserves_leading_zero_and_space(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'invented.csv'
            with file.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['SSID', 'Password', 'Authentication', 'Hidden'])
                writer.writeheader()
                writer.writerow({'SSID': ' SYNTHETIC-CSV ', 'Password': ' 001234Synthetic ', 'Authentication': 'WPA2-Personal', 'Hidden': 'false'})
            rows, _, _ = load(file)
            self.assertEqual(rows[0]['password'], ' 001234Synthetic ')
            self.assertEqual(rows[0]['ssid'], ' SYNTHETIC-CSV ')

    def test_key_only_json_preserved_without_auth_guess(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'invented.json'
            file.write_text(json.dumps([{'SSID': 'SYNTHETIC-KEY-ONLY', 'Key': 'SyntheticKey!42'}]), encoding='utf-8')
            rows, _, _ = load(file)
            self.assertEqual(rows[0]['security_types'], [-1])
            self.assertIsNone(qr_payload(rows[0])[0])

    def test_manager_json_adapter(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'invented.json'
            original = {'ssid': 'SYNTHETIC-MANAGER', 'password': 'SyntheticKey!42',
                        'security': ['WPA2', 'WPA3'], 'hidden': True, 'autojoin': False,
                        'private': True, 'meteredOverride': 'METERED',
                        'macRandomizationSetting': 'PERSISTENT', 'note': 'Synthetic note'}
            file.write_text(json.dumps([original]), encoding='utf-8')
            rows, _, _ = load(file)
            self.assertEqual(rows[0]['security_types'], [2, 4])
            self.assertEqual(app_record(rows[0]), original)

    def windows_xml(self, protected='false'):
        return f'''<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1"><name>IGNORED-PROFILE-LABEL</name>
        <SSIDConfig><SSID><name>SYNTHETIC-WINDOWS</name></SSID><nonBroadcast>true</nonBroadcast></SSIDConfig>
        <MSM><security><authEncryption><authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
        <sharedKey><keyType>passPhrase</keyType><protected>{protected}</protected><keyMaterial>SyntheticWindows!42</keyMaterial></sharedKey></security></MSM></WLANProfile>'''.encode()

    def test_windows_uses_ssid_not_profile_name(self):
        row = windows_records(self.windows_xml())[0]
        self.assertEqual(row['ssid'], 'SYNTHETIC-WINDOWS')
        self.assertTrue(row['hidden'])

    def test_windows_encrypted_material_rejected(self):
        with self.assertRaises(MigrationError):
            windows_records(self.windows_xml('true'))

    def test_windows_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'invented.xml').write_bytes(self.windows_xml())
            rows, _, kind = load(folder)
            self.assertEqual(len(rows), 1)
            self.assertEqual(kind, 'windows-xml-directory')
