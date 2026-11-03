"""Source-only allowlist packager. Never relies on .gitignore to exclude private runs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

TOP = {'README.md', 'README.en.md', 'README.zh-CN.md', 'LICENSE', 'CHANGELOG.md', 'CONTRIBUTING.md', 'SECURITY.md',
       'pyproject.toml', 'requirements.txt', 'launch.py', 'Start.cmd', '.gitignore', '.gitattributes'}
DOCS = {'workflow.md', 'compatibility.md', 'cli.md', 'design.md', 'references.md', 'release-checklist.md', 'toolkit.md'}
ANDROID = {'settings.gradle.kts', 'app/build.gradle.kts', 'app/src/main/AndroidManifest.xml',
           'app/src/main/java/io/github/wifimigrate/importer/ImportActivity.java'}
EXAMPLES = {'README.md', 'synthetic-settings.xml', 'synthetic-networks.csv', 'synthetic-manager.json'}
GITHUB = {'workflows/tests.yml', 'ISSUE_TEMPLATE/compatibility.yml', 'ISSUE_TEMPLATE/bug_report.yml'}
IGNORED = {'.git', '.venv', 'runs', 'input', 'private', 'output', 'backups', 'private_data', 'build', 'dist',
           '__pycache__', '.pytest_cache', '.gradle', '.idea'}


def allowed(relative):
    parts = relative.parts
    if len(parts) == 1:
        return parts[0] in TOP
    if parts[0] == 'docs':
        return len(parts) == 2 and parts[1] in DOCS
    if parts[0] == 'android-importer':
        return Path(*parts[1:]).as_posix() in ANDROID
    if parts[0] == 'examples':
        return len(parts) == 2 and parts[1] in EXAMPLES
    if parts[0] == '.github':
        return Path(*parts[1:]).as_posix() in GITHUB
    if parts[0] == 'src':
        return len(parts) == 3 and parts[1] == 'wifi_migrate' and relative.suffix == '.py'
    if parts[0] == 'tests':
        return len(parts) == 2 and relative.suffix == '.py'
    if parts[0] == 'scripts':
        return len(parts) == 2 and parts[1] in ('package_release.py', 'Start-Windows.ps1')
    return False


def source_files(root):
    result = []
    for folder, directories, files in os.walk(root):
        for name in list(directories):
            path = Path(folder) / name
            if name in IGNORED or name.endswith('.egg-info'):
                directories.remove(name)
            elif path.is_symlink():
                raise ValueError('Source tree contains a directory link; review locally before packaging.')
        for name in files:
            path = Path(folder) / name
            relative = path.relative_to(root)
            if name in ('python-path.txt', 'local.json', 'local.properties', '.release-manifest.json', 'SOURCE_MANIFEST.json'):
                continue
            if path.is_symlink() or not allowed(relative):
                raise ValueError('Unexpected source-tree file; review locally before packaging: ' + str(relative))
            result.append(path)
    required = ['README.md', 'LICENSE', 'pyproject.toml', 'src/wifi_migrate/__init__.py', 'examples/synthetic-settings.xml']
    if any(not (root / path).is_file() for path in required):
        raise ValueError('Required release files are missing.')
    return sorted(result)


def package(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or root in output.parents:
        raise ValueError('Write the source archive outside the source tree.')
    if output.exists() or output.with_suffix(output.suffix + '.sha256').exists():
        raise ValueError('Output already exists; choose a new archive name.')
    files = source_files(root)
    manifest = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            data = file.read_bytes()
            relative = file.relative_to(root).as_posix()
            archive.writestr('wifi-migrate/' + relative, data)
            manifest.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        archive.writestr('wifi-migrate/SOURCE_MANIFEST.json', json.dumps(manifest, indent=2))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
    return {'source_files': len(files), 'archive_sha256': digest, 'archive_bytes': output.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1], args.out), indent=2))


if __name__ == '__main__':
    main()
