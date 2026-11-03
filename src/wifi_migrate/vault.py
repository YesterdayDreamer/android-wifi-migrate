"""Opt-in local archive of original files, with byte-level verification."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .errors import MigrationError


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def archive_file(source, root, result=None):
    source, root = Path(source), Path(root)
    if not source.is_file():
        raise MigrationError('请选择一个要归档的原始文件。')
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.archive-', dir=root) as temporary:
        stage = Path(temporary) / 'entry'
        stage.mkdir()
        original = stage / ('original' + source.suffix.lower())
        shutil.copy2(source, original)
        digest = file_digest(original)
        if digest != file_digest(source):
            raise MigrationError('源文件在归档时发生变化，请重试。')
        now = datetime.now(timezone.utc)
        summary_file = Path(result) / 'summary.json' if result else None
        summary = json.loads(summary_file.read_text(encoding='utf-8')) if summary_file and summary_file.is_file() else {}
        manifest = {'file': original.name, 'source_name': source.name,
                    'created_utc': now.isoformat(), 'bytes': original.stat().st_size,
                    'sha256': digest, 'result': str(Path(result).resolve()) if result else None,
                    'format': summary.get('source_kind') or source.suffix.lower() or None,
                    'parse_state': 'result_linked' if summary else 'not_recorded'}
        (stage / 'archive.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        output = root / (now.strftime('%Y%m%d-%H%M%S-%f') + '-' + digest[:10])
        stage.rename(output)
    return {'archive': str(output), **manifest}


def archive_history(root):
    return [{'archive': str(path.parent), **json.loads(path.read_text(encoding='utf-8'))}
            for path in sorted(Path(root).glob('*/archive.json'), reverse=True)]


def verify_archive(directory):
    directory = Path(directory)
    metadata = json.loads((directory / 'archive.json').read_text(encoding='utf-8'))
    original = directory / metadata['file']
    if original.parent != directory or not original.name.startswith('original'):
        raise MigrationError('归档清单无效。')
    if not original.is_file() or original.stat().st_size != metadata['bytes'] or file_digest(original) != metadata['sha256']:
        raise MigrationError('归档校验失败。')
    return {'verified': True, **metadata}
