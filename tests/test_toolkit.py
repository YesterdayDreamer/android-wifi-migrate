import gzip
import json
from pathlib import Path
import tempfile
import unittest

from fixtures import xml_record
from wifi_migrate.catalog import classify
from wifi_migrate.core import normalize, parse_settings
from wifi_migrate.errors import MigrationError
from wifi_migrate.formats import load
from wifi_migrate.vault import archive_file, archive_history, verify_archive


class ToolkitTests(unittest.TestCase):
    def test_extended_settings_do_not_cross_network_boundaries(self):
        settings = (b'<Network>' + xml_record(ssid='TEST-A')
                    + b'<IpConfiguration><string name="IpAssignment">STATIC</string>'
                    b'<string name="ProxySettings">STATIC</string></IpConfiguration>'
                    b'<WifiEnterpriseConfiguration><string name="Identity">SYNTHETIC</string>'
                    b'</WifiEnterpriseConfiguration></Network><Network>'
                    + xml_record(ssid='TEST-B') + b'</Network>')
        first, second = parse_settings(settings)
        self.assertEqual(first['ip_configuration']['IpAssignment'], 'STATIC')
        self.assertEqual(first['enterprise_configuration']['Identity'], 'SYNTHETIC')
        self.assertIn('WifiConfiguration', first['raw_wifi_configuration'])
        self.assertNotIn('ip_configuration', second)
        self.assertNotIn('enterprise_configuration', second)

    def test_gzip_manager_backup_and_truncated_input(self):
        rows = [{'ssid': 'SYNTHETIC', 'security': ['OPEN'], 'password': ''}]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'synthetic.gz'
            data = gzip.compress(json.dumps(rows).encode())
            source.write_bytes(data)
            records, _, kind = load(source)
            self.assertEqual(kind, 'json-gzip')
            self.assertEqual(records[0]['security_types'], [0])
            self.assertIn('autojoin', records[0]['missing_fields'])
            source.write_bytes(data[:-4])
            with self.assertRaises(MigrationError):
                load(source)

    def test_conflicting_passwords_remain_distinct(self):
        rows = normalize([{'ssid': 'SAME', 'security_types': [2], 'password': key}
                          for key in ['SYNTHETIC-1', 'SYNTHETIC-2']])
        self.assertEqual(set(classify(rows)), {row['id'] for row in rows})
        self.assertEqual(set(classify(rows).values()), {'密码冲突'})

    def test_archiving_verifies_original_bytes_and_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'sample.data'
            source.write_bytes(b'unchanged synthetic bytes')
            entry = archive_file(source, root / 'archive')
            self.assertEqual(len(archive_history(root / 'archive')), 1)
            directory = Path(entry['archive'])
            self.assertTrue(verify_archive(directory)['verified'])
            copy = directory / entry['file']
            self.assertEqual(copy.read_bytes(), source.read_bytes())
            copy.write_bytes(b'changed synthetic bytes')
            with self.assertRaises(MigrationError):
                verify_archive(directory)
