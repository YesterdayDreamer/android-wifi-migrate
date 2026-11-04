import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_packager', ROOT / 'scripts/package_release.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class ReleaseTests(unittest.TestCase):
    def test_private_output_directories_excluded(self):
        for directory in ('runs', 'output', 'backups', 'private_data'):
            self.assertIn(directory, packager.IGNORED)
            self.assertIn(f'/{directory}/', (ROOT / '.gitignore').read_text(encoding='utf-8'))
    def test_repository_source_allowlist(self):
        files = packager.source_files(ROOT)
        self.assertTrue(files)
        self.assertFalse(any(path.suffix in ('.adb', '.tar', '.data') for path in files))
        self.assertEqual({p.name for p in files if p.suffix == '.png'}, packager.SCREENSHOTS)
        self.assertFalse(packager.allowed(Path('docs/screenshots/personal.png')))

    def test_real_output_names_not_allowed(self):
        for name in ('networks.json', 'phone.adb', 'backup.tar', 'review.html', 'photo.png', 'private.csv'):
            self.assertFalse(packager.allowed(Path(name)))

    def test_only_registered_example_data_allowed(self):
        self.assertTrue(packager.allowed(Path('examples/synthetic-settings.xml')))
        self.assertFalse(packager.allowed(Path('examples/my-phone.xml')))
        self.assertFalse(packager.allowed(Path('examples/real-passwords.json')))

    def test_package_has_no_git_history_or_run_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'source.zip'
            result = packager.package(ROOT, output)
            self.assertGreater(result['source_files'], 0)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
            self.assertFalse(any('/.git/' in name or '/runs/' in name for name in names))
            self.assertIn('wifi-migrate/SOURCE_MANIFEST.json', names)
