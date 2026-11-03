"""Read only the settings member; never unpack a phone backup onto disk.

Android Backup v2-v5 AES-256 container support is independently implemented
from the documented AOSP format; see docs/references.md. Not an adb restore tool.
"""
from __future__ import annotations
import hashlib
import hmac
import io
from pathlib import Path
import tarfile
import zlib
from .errors import MigrationError, PasswordRequired

SETTINGS_MEMBER = 'apps/com.android.providers.settings/k/com.android.providers.settings.data'
MAX_SETTINGS = 32 * 1024 * 1024
CHUNK = 65536


def _line(stream):
    value = stream.readline(8193)
    if len(value) > 8192 or not value.endswith(b'\n'):
        raise MigrationError('备份头不完整或格式不受支持。')
    return value[:-1]


def key_checksum(key, salt, rounds):
    # AOSP casts signed Java bytes to unsigned UTF-16 code units before PBKDF2.
    text = ''.join(chr(byte if byte < 128 else 0xff00 + byte) for byte in key)
    return hashlib.pbkdf2_hmac('sha1', text.encode('utf-8'), salt, rounds, 32)


def _decryptor(stream, password, version):
    if version == 1:
        raise MigrationError('加密的 v1 备份使用旧版密码兼容模式，当前版本不支持。')
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError as error:
        raise MigrationError('缺少 pycryptodome，请重新运行安装步骤。') from error
    try:
        user_salt = bytes.fromhex(_line(stream).decode('ascii'))
        checksum_salt = bytes.fromhex(_line(stream).decode('ascii'))
        rounds = int(_line(stream))
        user_iv = bytes.fromhex(_line(stream).decode('ascii'))
        blob = bytes.fromhex(_line(stream).decode('ascii'))
        if not (1 <= rounds <= 1_000_000 and len(user_iv) == 16 and len(blob) % 16 == 0):
            raise ValueError
        user_key = hashlib.pbkdf2_hmac('sha1', password.encode('utf-8'), user_salt, rounds, 32)
        clear = unpad(AES.new(user_key, AES.MODE_CBC, user_iv).decrypt(blob), 16)
        fields, cursor = [], 0
        for _ in range(3):
            size = clear[cursor]
            cursor += 1
            fields.append(clear[cursor:cursor + size])
            cursor += size
        iv, key, checksum = fields
        if cursor != len(clear) or len(iv) != 16 or len(key) != 32 or len(checksum) != 32:
            raise ValueError
        if not hmac.compare_digest(checksum, key_checksum(key, checksum_salt, rounds)):
            raise ValueError
        aes = AES.new(key, AES.MODE_CBC, iv)
    except (ValueError, IndexError, UnicodeError) as error:
        raise MigrationError('备份密码不正确，或加密头已损坏。') from error

    def chunks():
        pending = b''
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            pending += chunk
            usable = ((len(pending) - 16) // 16) * 16
            if usable > 0:
                yield aes.decrypt(pending[:usable])
                pending = pending[usable:]
        try:
            if not pending or len(pending) % 16:
                raise ValueError
            yield unpad(aes.decrypt(pending), 16)
        except ValueError as error:
            raise MigrationError('加密备份被截断或填充无效。') from error
    return chunks()


class ChunkReader(io.RawIOBase):
    def __init__(self, chunks):
        self.chunks, self.pending, self.done = iter(chunks), bytearray(), False

    def readable(self):
        return True

    def readinto(self, target):
        while len(self.pending) < len(target) and not self.done:
            chunk = next(self.chunks, None)
            if chunk is None:
                self.done = True
            else:
                self.pending.extend(chunk)
        count = min(len(target), len(self.pending))
        target[:count] = self.pending[:count]
        del self.pending[:count]
        return count


def _inflate(chunks):
    decoder = zlib.decompressobj()
    try:
        for chunk in chunks:
            # Bound output per call even for highly compressible application data.
            while chunk:
                yield decoder.decompress(chunk, CHUNK)
                chunk = decoder.unconsumed_tail
        yield decoder.flush()
        if not decoder.eof or decoder.unused_data:
            raise MigrationError('压缩备份被截断或包含额外数据。')
    except zlib.error as error:
        raise MigrationError('备份压缩数据无效。') from error


def _from_tar(stream):
    found = None
    try:
        with tarfile.open(fileobj=stream, mode='r|') as archive:
            for member in archive:
                name = member.name[2:] if member.name.startswith('./') else member.name
                if name != SETTINGS_MEMBER:
                    continue
                if found is not None or not member.isfile() or not 0 < member.size <= MAX_SETTINGS:
                    raise MigrationError('设置文件重复、过大或类型无效。')
                found = archive.extractfile(member).read()
    except tarfile.TarError as error:
        raise MigrationError('TAR 备份格式不完整。') from error
    # Consume the remaining compressed/encrypted stream to validate EOF and padding.
    while stream.read(CHUNK):
        pass
    if found is None:
        raise MigrationError('备份中没有目标设置文件；文件大小不能证明 WiFi 备份成功。')
    return found


def encrypted(path):
    with Path(path).open('rb') as stream:
        if stream.read(15) != b'ANDROID BACKUP\n':
            return False
        _line(stream)
        _line(stream)
        return _line(stream) != b'none'


def read_settings(path, password=None):
    path = Path(path)
    with path.open('rb') as stream:
        prefix = stream.read(16)
        stream.seek(0)
        if prefix.startswith(b'ANDROID BACKUP\n'):
            _line(stream)
            try:
                version, compressed = int(_line(stream)), int(_line(stream))
            except ValueError as error:
                raise MigrationError('Android 备份版本或压缩标志无效。') from error
            if version not in (1, 2, 3, 4, 5) or compressed not in (0, 1):
                raise MigrationError('Android 备份版本不受支持。')
            encryption = _line(stream)
            if encryption == b'none':
                chunks = iter(lambda: stream.read(CHUNK), b'')
            elif encryption == b'AES-256':
                if password is None:
                    raise PasswordRequired('这是加密备份，需要输入备份时设置的密码。')
                chunks = _decryptor(stream, password, version)
            else:
                raise MigrationError('不支持该备份加密方式。')
            if compressed:
                chunks = _inflate(chunks)
            return _from_tar(io.BufferedReader(ChunkReader(chunks)))
        if path.suffix.lower() == '.tar':
            return _from_tar(stream)
        if path.stat().st_size > MAX_SETTINGS:
            raise MigrationError('设置文件过大，请选择 .adb、.tar 或实际的配置文件。')
        return stream.read()
