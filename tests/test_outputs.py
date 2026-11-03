import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from wifi_migrate.core import normalize, parse_settings, qr_values
from wifi_migrate.formats import load
from wifi_migrate.outputs import export_run
from wifi_migrate.errors import MigrationError
from fixtures import xml_record

try:
    import zxingcpp
    from PIL import Image
except ImportError:
    zxingcpp = None


def wifi_fields(text):
    fields, buffer, escaped = {}, [], False
    for char in text[5:]:
        if escaped:
            buffer.append(char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ';':
            value = ''.join(buffer)
            if ':' in value:
                key, value = value.split(':', 1)
                fields[key] = value
            buffer = []
        else:
            buffer.append(char)
    return fields


class OutputTests(unittest.TestCase):
    def test_missing_qr_dependency_preserves_other_exports(self):
        records = normalize([{'ssid': 'SYNTHETIC', 'security_types': [0]}])
        with tempfile.TemporaryDirectory() as folder, patch.dict('sys.modules', {'qrcode': None}):
            out = Path(folder) / 'result'
            summary = export_run(records, out, 'a' * 64, 'test')
            self.assertEqual(summary['qr_written'], 0)
            self.assertIn('pypng', summary['qr_warning'])
            self.assertTrue((out / 'networks.json').is_file())
            self.assertIn('qr_dependency_missing', (out / 'wifi.csv').read_text(encoding='utf-8-sig'))

    def test_generated_app_json_does_not_modify_native_input(self):
        source = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic-manager.json'
        native = source.read_bytes()
        records, digest, kind = load(source)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result'
            summary = export_run(records, out, digest, kind, make_qr=False)
            self.assertFalse(summary['phone_import_verified'])
            self.assertEqual(summary['app_adapter_status'], 'experimental_schema_only')
            self.assertTrue((out / 'wifi-password-manager.json').is_file())
            self.assertEqual(source.read_bytes(), native)
    def rows(self):
        return normalize(parse_settings(xml_record(ssid='SYNTHETIC/A:B') + xml_record(ssid='SYNTHETIC:A/B', password='Synthetic;&\\,:"42')))

    def test_filename_collision_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result'
            summary = export_run(self.rows(), out, 'a' * 64, 'synthetic')
            self.assertEqual(summary['qr_written'], 2)
            self.assertEqual(len(list((out / 'qr').glob('*.png'))), 2)

    def test_existing_output_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(MigrationError):
                export_run(self.rows(), Path(folder), 'a' * 64, 'synthetic')

    def test_json_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result'
            rows = self.rows()
            export_run(rows, out, 'a' * 64, 'synthetic')
            for name in ('networks.json', 'wifi.csv', 'wifi-password-manager.json'):
                back, _, _ = load(out / name)
                self.assertEqual([(r['ssid'], r['password'], r['security_types']) for r in rows], [(r['ssid'], r['password'], r['security_types']) for r in back])

    def test_html_does_not_execute_input(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result'
            rows = normalize(parse_settings(xml_record(ssid='</script><img onerror=alert(1)>')))
            export_run(rows, out, 'a' * 64, 'synthetic')
            html = (out / 'review.html').read_text(encoding='utf-8')
            self.assertNotIn('</script><img', html)
            self.assertEqual(html.count('<script>'), 1)
            self.assertNotIn('https://', html)

    def test_summary_does_not_include_secret_or_name(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result'
            export_run(self.rows(), out, 'a' * 64, 'synthetic')
            summary = (out / 'summary.json').read_text(encoding='utf-8')
            self.assertNotIn('Synthetic', summary)
            self.assertNotIn('SYNTHETIC/A:B', summary)
            self.assertFalse(json.loads(summary)['phone_import_verified'])

    def test_review_preserves_ssid_that_matches_template_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result'
            rows = normalize(parse_settings(xml_record(ssid='__DIGEST__')))
            export_run(rows, out, 'a' * 64, 'synthetic', make_qr=False)
            html = (out / 'review.html').read_text(encoding='utf-8')
            self.assertIn('"ssid": "__DIGEST__"', html)
            self.assertIn('"reason": "not_requested"', html)
            self.assertIn('wifi-migrate-' + 'a' * 24, html)

    @unittest.skipIf(zxingcpp is None, 'optional independent decoder not installed')
    def test_independent_qr_decode_including_special_characters(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result'
            rows = self.rows()
            export_run(rows, out, 'a' * 64, 'synthetic')
            for row in rows:
                with Image.open(out / 'qr' / (row['id'] + '.png')) as image:
                    result = zxingcpp.read_barcode(image)
                self.assertIsNotNone(result)
                kind, ssid, password, hidden = qr_values(row)[0]
                self.assertEqual(wifi_fields(result.text), {'T': kind, 'S': ssid, 'P': password, 'H': str(hidden).lower()})
