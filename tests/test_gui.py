from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    import tkinter as tk
except ImportError:
    tk = None


@unittest.skipIf(tk is None, 'Tk unavailable')
class GuiTests(unittest.TestCase):
    def make_window(self):
        from wifi_migrate.gui import Workbench

        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest('Tk display unavailable: ' + type(error).__name__)
        root.withdraw()
        app = Workbench(root)
        self.addCleanup(app.close)
        return app

    def test_workbench_initial_state_does_not_start_adb(self):
        with patch('wifi_migrate.gui.Adb') as adb:
            app = self.make_window()
            self.assertIsNone(app.run_path)
            self.assertFalse(app.busy)
            adb.assert_not_called()
            self.assertEqual(app.tabs.select(), str(app.home_page))
            self.assertTrue(all(button.instate(['disabled']) for button in app.result_controls))

    def wait_for_task(self, app):
        deadline = time.monotonic() + 5
        while app.busy and time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.01)
        self.assertFalse(app.busy)

    def test_conversion_and_failed_retry_do_not_leave_stale_results(self):
        app = self.make_window()
        source = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic-networks.csv'
        with tempfile.TemporaryDirectory() as directory, patch('wifi_migrate.gui.messagebox.showerror') as error:
            output = Path(directory) / 'result'
            with patch('wifi_migrate.gui.new_run', return_value=output):
                app.read(source)
                self.assertTrue(app.busy)
                self.assertTrue(all(widget.instate(['disabled']) for widget in app.controls))
                self.wait_for_task(app)
                self.assertEqual(app.tabs.select(), str(app.catalog_page))
                self.assertEqual(app.run_path, output)
                self.assertTrue((output / 'review.html').is_file())
                app.tabs.select(0)
                app.read(source.with_name('missing.csv'))
                self.wait_for_task(app)
                error.assert_called_once()
                self.assertIsNone(app.run_path)
                self.assertTrue(all(button.instate(['disabled']) for button in app.result_controls))
                self.assertTrue((output / 'review.html').is_file())

    def test_adb_path_change_invalidates_current_device(self):
        app = self.make_window()
        app.adb_path.set('test-adb')
        app.device_ids['source'].set('old-phone')
        with patch('wifi_migrate.gui.Adb') as adb:
            adb.return_value.devices.return_value = [{'serial': 'demo-phone', 'state': 'device'}]
            adb.return_value.migration_status.return_value = {'android_release': '14'}
            app.refresh()
            self.wait_for_task(app)
            self.assertEqual(app.device_ids['target'].get(), 'demo-phone')
            self.assertEqual(app.device_ids['source'].get(), 'old-phone')
        app.adb_path.set('other-adb')
        self.assertTrue(all(not variable.get() for variable in app.device_ids.values()))
        self.assertTrue(all(not box['values'] for box in app.device_boxes.values()))
        self.assertTrue(all(button.instate(['disabled']) for button in app.phone_controls))

    def test_desktop_write_requires_preview_for_selected_device(self):
        app = self.make_window()
        app.run_path = Path('unused')
        app.records = [{'id': 'synthetic'}]
        app.device_ids['target'].set('first-device')
        self.assertTrue(all(button.instate(['disabled']) for button in app.write_controls))
        with patch('wifi_migrate.gui.Adb'), patch('wifi_migrate.gui.import_records') as operation:
            operation.return_value = {'mode': 'dry-run', 'planned': 1, 'ready': 1, 'skipped': 0}
            app.dry_run()
            self.wait_for_task(app)
            self.assertFalse(operation.call_args.kwargs['apply'])
            self.assertTrue(app.write_controls[0].instate(['!disabled']))
            self.assertTrue(app.write_controls[1].instate(['disabled']))
            with patch('wifi_migrate.gui.messagebox.askyesno', return_value=True), patch.object(app, 'log_migration'):
                app.apply_import(None)
                self.assertEqual(operation.call_count, 1)
                operation.return_value = {'saved_list_visible': 0, 'failed': 0, 'save_acknowledged_unverified': 1}
                app.apply_import(1)
                self.wait_for_task(app)
                self.assertTrue(app.write_controls[1].instate(['disabled']))
                operation.return_value = {'saved_list_visible': 1, 'failed': 0, 'save_acknowledged_unverified': 0}
                app.apply_import(1)
                self.wait_for_task(app)
                self.assertTrue(app.write_controls[1].instate(['!disabled']))
        app.device_ids['target'].set('another-device')
        self.assertTrue(all(button.instate(['disabled']) for button in app.write_controls))
        self.assertFalse(app.trial_visible)
