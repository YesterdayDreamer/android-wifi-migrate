import hashlib
from pathlib import Path
import tempfile
import unittest
import zlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from wifi_migrate.archive import read_settings, SETTINGS_MEMBER
from wifi_migrate.errors import MigrationError, PasswordRequired
from fixtures import xml_record, tar_bytes


def encrypted_fixture(payload, password='Synthetic-备份-Only!42', compressed=True):
    user_salt, ck_salt = bytes(range(64)), bytes(range(64, 128))
    rounds = 1000
    user_iv, data_iv, master = bytes(range(16)), bytes(range(16, 32)), bytes(range(128, 160))
    # Independent fixture construction: signed-byte -> Java char -> UTF-8 checksum input.
    java_chars = bytes.fromhex(''.join(f'{(b - 256) & 0xffff:04x}' for b in master)).decode('utf-16-be')
    checksum = hashlib.pbkdf2_hmac('sha1', java_chars.encode('utf-8'), ck_salt, rounds, 32)
    key = hashlib.pbkdf2_hmac('sha1', password.encode('utf-8'), user_salt, rounds, 32)
    blob = bytes([16]) + data_iv + bytes([32]) + master + bytes([32]) + checksum
    blob = AES.new(key, AES.MODE_CBC, user_iv).encrypt(pad(blob, 16))
    body = zlib.compress(payload) if compressed else payload
    body = AES.new(master, AES.MODE_CBC, data_iv).encrypt(pad(body, 16))
    header = [b'ANDROID BACKUP', b'5', b'1' if compressed else b'0', b'AES-256',
              user_salt.hex().encode(), ck_salt.hex().encode(), str(rounds).encode(), user_iv.hex().encode(), blob.hex().encode()]
    return b'\n'.join(header) + b'\n' + body


class ArchiveTests(unittest.TestCase):
    def load(self, content, password=None, suffix='.adb'):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / ('synthetic' + suffix)
            file.write_bytes(content)
            return read_settings(file, password)

    def test_plain_compressed_and_uncompressed(self):
        data = xml_record()
        archive = tar_bytes(data)
        for compressed in (False, True):
            backup = b'ANDROID BACKUP\n5\n' + (b'1' if compressed else b'0') + b'\nnone\n' + (zlib.compress(archive) if compressed else archive)
            self.assertEqual(self.load(backup), data)

    def test_encrypted_modern_unicode_password(self):
        data = xml_record()
        for compressed in (False, True):
            self.assertEqual(self.load(encrypted_fixture(tar_bytes(data), compressed=compressed), 'Synthetic-备份-Only!42'), data)

    def test_encrypted_requires_password(self):
        with self.assertRaises(PasswordRequired):
            self.load(encrypted_fixture(tar_bytes(xml_record())))

    def test_wrong_password_fails_before_result(self):
        with self.assertRaises(MigrationError):
            self.load(encrypted_fixture(tar_bytes(xml_record())), 'Synthetic-Wrong!42')

    def test_truncated_zlib_after_target_not_accepted(self):
        payload = zlib.compress(tar_bytes(xml_record()))[:-3]
        with self.assertRaises(MigrationError):
            self.load(b'ANDROID BACKUP\n5\n1\nnone\n' + payload)

    def test_truncated_aes_not_accepted(self):
        with self.assertRaises(MigrationError):
            self.load(encrypted_fixture(tar_bytes(xml_record()))[:-1], 'Synthetic-备份-Only!42')

    def test_duplicate_settings_rejected(self):
        with self.assertRaises(MigrationError):
            self.load(tar_bytes(xml_record(), duplicate=True), suffix='.tar')

    def test_path_traversal_member_not_used(self):
        with self.assertRaises(MigrationError):
            self.load(tar_bytes(xml_record(), member='../' + SETTINGS_MEMBER), suffix='.tar')

    def test_large_unrelated_member_skipped(self):
        data = xml_record()
        backup = b'ANDROID BACKUP\n5\n1\nnone\n' + zlib.compress(tar_bytes(data, filler=2 * 1024 * 1024))
        self.assertEqual(self.load(backup), data)

    def test_missing_settings_not_success(self):
        with self.assertRaises(MigrationError):
            self.load(tar_bytes(b'invented', member='apps/synthetic/other'), suffix='.tar')

    def test_bad_backup_version(self):
        with self.assertRaises(MigrationError):
            self.load(b'ANDROID BACKUP\n99\n0\nnone\n' + tar_bytes(xml_record()))
