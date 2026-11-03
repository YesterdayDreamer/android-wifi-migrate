import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from wifi_migrate.adb_runtime import ADB_NAME, discover, unpack_platform_tools
from wifi_migrate.errors import MigrationError
from wifi_migrate.migration import helper_results, recommend, record_event


class ProductTests(unittest.TestCase):
    def test_windows_cli_uses_shared_export(self):
        from wifi_migrate.cli import main
        with patch('wifi_migrate.cli.windows_run', return_value=([], Path('result'), {'records': 1})) as export:
            self.assertEqual(main(['export-windows', '--out', 'unused']), 0)
            export.assert_called_once_with(Path('unused'))

    def test_helper_v2_checks_counts_and_distinguishes_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            doc = {'format': 'wifi-migrate-helper-v2', 'source_sha256': 'hash',
                   'source_count': 2, 'processed_count': 1, 'unprocessed_count': 1,
                   'cancelled_batches': 1, 'cancelled_batch_ids': [1],
                   'results': [{'id': 'hash:1', 'batch': 2, 'state': 'SYSTEM_CONFIRMED'},
                               {'id': 'hash:2', 'batch': 0, 'state': 'NOT_STARTED'}]}
            path.write_text(json.dumps(doc), encoding='utf-8')
            self.assertTrue(helper_results(path, 'hash', 2)['partial'])
            with self.assertRaises(MigrationError):
                helper_results(path, 'hash', 1)
            doc['processed_count'] = 2
            path.write_text(json.dumps(doc), encoding='utf-8')
            with self.assertRaises(MigrationError):
                helper_results(path, 'hash', 2)
    def test_reuses_neighboring_tool_and_respects_saved_preference(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'ADB_PATH': ''}):
            root = Path(folder)
            project = root / 'public' / 'checkout'
            nearby = root / '工具' / 'adb' / ADB_NAME
            nearby.parent.mkdir(parents=True)
            nearby.touch()
            state = root / 'settings'
            self.assertEqual(discover(project, state), nearby.resolve())
            selected = root / ADB_NAME
            selected.touch()
            state.mkdir()
            (state / 'adb.json').write_text(json.dumps({'path': str(selected)}), encoding='utf-8')
            self.assertEqual(discover(project, state), selected.resolve())

    def test_zip_rejects_escaping_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'tools.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('platform-tools/../unexpected', 'test')
            with self.assertRaises(MigrationError):
                unpack_platform_tools(source, root / 'extract')
            self.assertFalse((root / 'unexpected').exists())

    def test_recommendation_prefers_phone_app_and_defaults_to_qr_offline(self):
        self.assertEqual(recommend({}, 3, 2)[0], 'qr')
        platform = {'sdk': '34', 'system_add_ui_visible': True}
        self.assertEqual(recommend(platform, 3, 2)[0], 'helper')
        self.assertEqual(recommend({**platform, 'wpm_installed': True, 'shizuku_server_visible': True}, 3, 2)[0], 'wpm')

    def test_helper_report_matches_payload_and_keeps_evidence_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = root / 'helper.json'
            report.write_text(json.dumps({'format': 'wifi-migrate-helper-v1', 'source_sha256': 'test',
                                          'cancelled_batches': 1, 'results': ['SYSTEM_CONFIRMED', 'SKIPPED'],
                                          'password': 'SYNTHETIC-DO-NOT-COPY'}), encoding='utf-8')
            with self.assertRaises(MigrationError):
                helper_results(report, 'different')
            result = helper_results(report, 'test')
            path = record_event(root, 'helper', 'target', 'SUBMITTED', evidence='imported_helper_report', details=result)
            record_event(root, 'helper', 'target', 'AUTO_RECONNECT_VERIFIED', evidence='user_confirmed', count=1)
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('SYNTHETIC-DO-NOT-COPY', text)
            self.assertEqual([event['evidence'] for event in json.loads(text)['events']],
                             ['imported_helper_report', 'user_confirmed'])
