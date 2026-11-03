import json
from pathlib import Path
import shlex
from types import SimpleNamespace
import tempfile
import unittest
from wifi_migrate.adb import Adb, import_records, plan_record
from wifi_migrate.core import normalize, parse_settings
from wifi_migrate.errors import MigrationError
from fixtures import xml_record

CAPS = {'add_network_advertised': True, 'security_types': ['open', 'owe', 'wep', 'wpa2', 'wpa3'],
        'hidden_flag_advertised': True, 'disable_autojoin_flag_advertised': True}


class FakeAdb:
    def __init__(self, acknowledge=True, readback=True):
        self.calls, self.visible = [], []
        self.acknowledge, self.readback = acknowledge, readback

    def probe(self, serial):
        return dict(CAPS)

    def list_networks(self, serial):
        return self.visible if self.readback else None

    def shell(self, serial, command):
        self.calls.append(command)
        args = shlex.split(command)
        if self.acknowledge:
            aliases = {'wpa2': 'WPA_PSK/SAE^', 'wpa3': 'SAE', 'open': 'OPEN/OWE^', 'owe': 'OWE', 'wep': 'WEP'}
            self.visible.append((args[3], aliases[args[4]]))
        return SimpleNamespace(returncode=0 if self.acknowledge else 1, stdout='Save successful\n' if self.acknowledge else 'Save failed\n')


class AdbTests(unittest.TestCase):
    def test_shizuku_uses_current_installation_and_confirms_process(self):
        apk = '/data/app/~~new/moe.shizuku.privileged.api-current/base.apk'
        observed = []
        def runner(args, **_):
            observed.append(args[1:])
            tail = args[4:]
            if tail == ['pidof', 'shizuku_server']:
                return SimpleNamespace(returncode=0, stdout='4242' if len(observed) > 5 else '')
            if tail == ['pm', 'path', 'moe.shizuku.privileged.api']:
                return SimpleNamespace(returncode=0, stdout='package:' + apk)
            if tail == ['getprop', 'ro.product.cpu.abi']:
                return SimpleNamespace(returncode=0, stdout='arm64-v8a')
            return SimpleNamespace(returncode=0, stdout='')
        adb = Adb('synthetic-adb', runner)
        adb.require_device = lambda serial: None
        self.assertIn('服务已启动', adb.start_shizuku('SYNTHETIC'))
        self.assertEqual(observed[-2], ['-s', 'SYNTHETIC', 'shell',
                                       shlex.quote(apk.removesuffix('/base.apk') + '/lib/arm64/libshizuku.so')])
        self.assertTrue(all(args[:2] == ['-s', 'SYNTHETIC'] for args in observed))

    def records(self, **kwargs):
        return normalize(parse_settings(xml_record(**kwargs)))

    def test_dry_run_performs_no_phone_write(self):
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'progress.json'
            summary = import_records(adb, 'SYNTHETIC-SERIAL', self.records(), out)
            self.assertEqual(summary['ready'], 1)
            self.assertFalse(out.exists())
            self.assertEqual(adb.calls, [])

    def test_success_requires_ack_and_readback(self):
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            summary = import_records(adb, 'SYNTHETIC-SERIAL', self.records(), Path(folder) / 'progress.json', apply=True, first_ready=True)
            self.assertEqual(summary['saved_list_visible'], 1)

    def test_batch_requires_trial_and_confirmation_for_same_source(self):
        rows = self.records()
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'progress.json'
            with self.assertRaises(MigrationError):
                import_records(adb, 'SYNTHETIC-SERIAL', rows, out, apply=True, confirm_trial=True)
            self.assertEqual(adb.calls, [])
            import_records(adb, 'SYNTHETIC-SERIAL', rows, out, apply=True, first_ready=True, source_id='file-a')
            for source_id, confirmation in [('file-a', False), ('file-b', True)]:
                with self.assertRaises(MigrationError):
                    import_records(adb, 'SYNTHETIC-SERIAL', rows, out, apply=True, resume=True,
                                   confirm_trial=confirmation, source_id=source_id)
            result = import_records(adb, 'SYNTHETIC-SERIAL', rows, out, apply=True, resume=True,
                                    confirm_trial=True, source_id='file-a')
            self.assertEqual(result['saved_list_visible'], 1)
            self.assertEqual(len(adb.calls), 1)

    def test_trial_finds_first_ready_network_after_checking_conflicts(self):
        rows = normalize([
            {'ssid': 'SYNTHETIC-CONFLICT', 'security_types': [2], 'password': 'SyntheticA1'},
            {'ssid': 'SYNTHETIC-READY', 'security_types': [2], 'password': 'SyntheticB2'},
            {'ssid': 'SYNTHETIC-CONFLICT', 'security_types': [2], 'password': 'SyntheticC3'},
        ])
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            report = import_records(adb, 'SYNTHETIC-SERIAL', rows, Path(folder) / 'progress.json',
                                    apply=True, first_ready=True)
        self.assertEqual(report['saved_list_visible'], 1)
        self.assertEqual(len(adb.calls), 1)
        self.assertEqual(shlex.split(adb.calls[0])[3], 'SYNTHETIC-READY')

    def test_ack_without_readback_is_unverified(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = import_records(FakeAdb(readback=False), 'SYNTHETIC-SERIAL', self.records(), Path(folder) / 'progress.json', apply=True, first_ready=True)
            self.assertEqual(summary['saved_list_visible'], 0)
            self.assertEqual(summary['save_acknowledged_unverified'], 1)

    def test_failed_write_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            summary = import_records(FakeAdb(acknowledge=False), 'SYNTHETIC-SERIAL', self.records(), Path(folder) / 'progress.json', apply=True, first_ready=True)
            self.assertEqual(summary['failed'], 1)

    def test_resume_only_verified_unchanged_record(self):
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'progress.json'
            records = self.records()
            import_records(adb, 'SYNTHETIC-SERIAL', records, out, apply=True, first_ready=True)
            import_records(adb, 'SYNTHETIC-SERIAL', records, out, apply=True, resume=True, confirm_trial=True)
            self.assertEqual(len(adb.calls), 1)
            records[0]['password'] = 'SyntheticUpdated!42'
            with self.assertRaises(MigrationError):
                import_records(adb, 'SYNTHETIC-SERIAL', records, out, apply=True, resume=True, confirm_trial=True)
            import_records(adb, 'SYNTHETIC-SERIAL', records, out, apply=True, resume=True, first_ready=True)
            self.assertEqual(len(adb.calls), 2)

    def test_resume_different_device_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'progress.json'
            import_records(FakeAdb(), 'SYNTHETIC-ONE', self.records(), out, apply=True, first_ready=True)
            with self.assertRaises(MigrationError):
                import_records(FakeAdb(), 'SYNTHETIC-TWO', self.records(), out, apply=True, resume=True)

    def test_missing_visible_record_is_retried(self):
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'progress.json'
            import_records(adb, 'SYNTHETIC-SERIAL', self.records(), out, apply=True, first_ready=True)
            adb.visible.clear()
            with self.assertRaises(MigrationError):
                import_records(adb, 'SYNTHETIC-SERIAL', self.records(), out, apply=True, resume=True, confirm_trial=True)
            import_records(adb, 'SYNTHETIC-SERIAL', self.records(), out, apply=True, resume=True, first_ready=True)
            self.assertEqual(len(adb.calls), 2)

    def test_conflicting_same_ssid_skipped(self):
        rows = normalize(parse_settings(xml_record(password='SyntheticFirst!42') + xml_record(password='SyntheticSecond!42')))
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            summary = import_records(adb, 'SYNTHETIC-SERIAL', rows, Path(folder) / 'progress.json')
            self.assertEqual(summary['skipped'], 2)
            self.assertEqual(adb.calls, [])

    def test_hidden_not_silently_lost(self):
        caps = dict(CAPS, hidden_flag_advertised=False)
        self.assertIsNone(plan_record(self.records(hidden=True)[0], caps)[0])

    def test_unknown_security_skipped(self):
        self.assertIsNone(plan_record(self.records(types=(3,))[0], CAPS)[0])

    def test_raw_psk_skipped(self):
        self.assertIsNone(plan_record(self.records(password='c' * 64)[0], CAPS)[0])

    def test_passphrase_option_like_text_is_still_one_argument(self):
        key = '-Synthetic;$(touch nope)`whoami`!42'
        planned, _ = plan_record(self.records(password=key)[0], CAPS)
        self.assertEqual(shlex.split(shlex.join(planned[1]))[5], key)

    def test_host_process_args_do_not_contain_password(self):
        captured = []
        def runner(args, **kwargs):
            captured.append((args, kwargs))
            return SimpleNamespace(returncode=0, stdout='Save successful\n', stderr='')
        adb = Adb('synthetic-adb', runner)
        key = 'SyntheticPrivate!42'
        adb.shell('SYNTHETIC-SERIAL', shlex.join(['cmd', 'wifi', 'add-network', 'SYNTHETIC', 'wpa2', key]))
        self.assertNotIn(key, str(captured[0][0]))
        self.assertFalse(captured[0][1]['shell'])
        self.assertIn(key, captured[0][1]['input'])

    def test_report_does_not_store_password(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'progress.json'
            import_records(FakeAdb(), 'SYNTHETIC-SERIAL', self.records(), out, apply=True, first_ready=True)
            text = out.read_text(encoding='utf-8')
            self.assertNotIn('SyntheticSecret', text)
            self.assertNotIn('SYNTHETIC-SERIAL', text)
            self.assertFalse(json.loads(text)['key_or_connectivity_verified'])

    def test_unsupported_device_never_receives_writes(self):
        adb = FakeAdb()
        adb.probe = lambda serial: dict(CAPS, add_network_advertised=False)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(MigrationError):
                import_records(adb, 'SYNTHETIC-SERIAL', self.records(), Path(folder) / 'progress.json', apply=True, first_ready=True)
            self.assertEqual(adb.calls, [])

    def test_list_parser_preserves_internal_spaces(self):
        def runner(args, **kwargs):
            return SimpleNamespace(returncode=0, stdout='Network Id SSID Security type\n7            SYNTHETIC LAB ROOM               WPA_PSK/SAE^\n', stderr='')
        self.assertEqual(Adb('synthetic-adb', runner).list_networks('SYNTHETIC-SERIAL'), [('SYNTHETIC LAB ROOM', 'WPA_PSK/SAE')])

    def test_probe_does_not_write_or_infer_permissions(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            if args[1:3] == ['devices', '-l']:
                text = 'List of devices attached\nSYNTHETIC-SERIAL device\n'
            elif args[-3:] == ['cmd', 'wifi', 'help']:
                text = ' add-network <ssid> open|owe|wpa2|wpa3|wep\n   -h - Mark the network hidden.\n list-networks\n add-suggestion\n   -d - Mark autojoin disabled.\n'
                return SimpleNamespace(returncode=255, stdout=text, stderr='')
            else:
                text = '30\n'
            return SimpleNamespace(returncode=0, stdout=text, stderr='')
        caps = Adb('synthetic-adb', runner).probe('SYNTHETIC-SERIAL')
        self.assertTrue(caps['add_network_advertised'])
        self.assertTrue(caps['hidden_flag_advertised'])
        self.assertFalse(caps['disable_autojoin_flag_advertised'])
        self.assertFalse(caps['system_write_verified'])
        self.assertTrue(all('input' not in args for args in calls))
        self.assertFalse(any('add-network' in args for args in calls))

    def test_unknown_device_rejected_before_backup(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout='List of devices attached\nSYNTHETIC-SERIAL unauthorized\n', stderr='')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(MigrationError):
                Adb('synthetic-adb', runner).backup('SYNTHETIC-SERIAL', Path(folder) / 'phone.adb')
        self.assertFalse(any('backup' in args for args in calls))

    def test_backup_defaults_to_settings_package(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            if 'backup' in args:
                target = Path(args[args.index('-f') + 1])
                target.write_bytes(b'ANDROID BACKUP\n5\n0\nnone\n' + b'SYNTHETIC-BODY')
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            return SimpleNamespace(returncode=0, stdout='List of devices attached\nSYNTHETIC-SERIAL device\n', stderr='')
        with tempfile.TemporaryDirectory() as folder:
            Adb('synthetic-adb', runner).backup('SYNTHETIC-SERIAL', Path(folder) / 'phone.adb')
        command = next(args for args in calls if 'backup' in args)
        self.assertIn('com.android.providers.settings', command)
        self.assertNotIn('-all', command)
        self.assertNotIn('-shared', command)

    def test_resume_limit_preserves_other_progress(self):
        rows = normalize(parse_settings(xml_record(ssid='SYNTHETIC-ONE') + xml_record(ssid='SYNTHETIC-TWO')))
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'progress.json'
            import_records(adb, 'SYNTHETIC-SERIAL', rows, output, apply=True, first_ready=True)
            import_records(adb, 'SYNTHETIC-SERIAL', rows, output, apply=True, resume=True, confirm_trial=True)
            with self.assertRaises(MigrationError):
                import_records(adb, 'SYNTHETIC-SERIAL', rows, output, apply=True, resume=True, limit=1, confirm_trial=True)
            self.assertEqual(len(json.loads(output.read_text())['results']), 2)

    def test_original_non_autojoin_not_silently_changed(self):
        row = self.records()[0]
        row['autojoin'] = False
        self.assertIsNone(plan_record(row, dict(CAPS, disable_autojoin_flag_advertised=False))[0])

    def test_push_only_images_no_delete(self):
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs.get('input') or ''))
            text = 'List of devices attached\nSYNTHETIC-SERIAL device\n' if 'devices' in args else ''
            return SimpleNamespace(returncode=0, stdout=text, stderr='')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'qr').mkdir()
            (path / 'qr/001.png').write_bytes(b'SYNTHETIC-TEST-IMAGE')
            (path / 'networks.json').write_text('SYNTHETIC-DO-NOT-PUSH')
            result = Adb('synthetic-adb', runner).push_qr('SYNTHETIC-SERIAL', path)
            self.assertEqual(result['copied'], 1)
        pushed = [args for args, _ in calls if 'push' in args]
        self.assertEqual(len(pushed), 1)
        self.assertTrue(pushed[0][-2].endswith('001.png'))
        self.assertFalse(any('rm ' in text for _, text in calls))
