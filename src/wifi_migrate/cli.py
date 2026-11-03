from __future__ import annotations
import argparse
import getpass
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from . import __version__
from .adb import Adb, import_records, import_report_path
from .core import summarize
from .errors import MigrationError, PasswordRequired
from .formats import load
from .outputs import export_run
from .pdf import export_pdf
from .vault import archive_file, archive_history, verify_archive
from .workflow import convert_run, log_failure, new_run, windows_run


def read_interactive(path):
    try:
        return load(path)
    except PasswordRequired:
        return load(path, getpass.getpass('备份密码（不回显、不保存）：'))


def convert(path, output, password=None, make_qr=True):
    return convert_run(path, output, password, make_qr)[2]


def export_windows(output):
    return windows_run(output)[2]


def wizard():
    print('WiFi Migrate · 先读取资料，再选择手机保存方式。免 Root，不承诺所有系统兼容。')
    print('1. 已有备份、配置、JSON、CSV 或 Windows XML 目录\n2. 连接旧手机备份\n3. 只检测手机能力')
    choice = input('选择 [1/2/3]：').strip()
    if choice == '1':
        path = Path(input('输入文件或 Windows XML 目录：').strip().strip('"'))
        records, digest, kind = read_interactive(path)
        output = new_run()
        result = export_run(records, output, digest, kind)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('结果目录：' + str(output.resolve()))
    elif choice in ('2', '3'):
        adb = Adb()
        print(json.dumps(adb.devices(), ensure_ascii=False, indent=2))
        serial = input('明确输入设备序列号：').strip()
        if choice == '3':
            print(json.dumps(adb.probe(serial), ensure_ascii=False, indent=2))
            return
        mode = input('使用原流程全量备份？包含其他应用/共享存储，通常无需选择 [y/N]：').lower() == 'y'
        output = new_run()
        print('请在手机上确认备份，完成后会自动检查 WiFi 内容。')
        backup = adb.backup(serial, output / 'phone.adb', mode)
        records, digest, kind = read_interactive(backup)
        result = export_run(records, output / 'result', digest, kind)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('结果目录：' + str((output / 'result').resolve()))
    else:
        raise MigrationError('未选择有效步骤。')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='wifi-migrate', description='WiFi Migrate — Cross-brand Android Wi-Fi Migration Toolkit')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('gui')
    sub.add_parser('wizard')
    for name in ('inspect', 'convert'):
        cmd = sub.add_parser(name)
        cmd.add_argument('input', type=Path)
        if name == 'convert':
            cmd.add_argument('--out', type=Path)
            cmd.add_argument('--no-qr', action='store_true')
    for name in ('devices', 'probe', 'doctor', 'backup', 'push-qr', 'import-adb'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--adb')
        if name != 'devices':
            cmd.add_argument('--serial', required=True)
        if name == 'backup':
            cmd.add_argument('--out', type=Path)
            cmd.add_argument('--legacy-full', action='store_true', help='Original all/shared/system backup; may contain unrelated personal data')
        if name == 'push-qr':
            cmd.add_argument('run', type=Path)
        if name == 'import-adb':
            cmd.add_argument('input', type=Path)
            cmd.add_argument('--out', type=Path)
            cmd.add_argument('--apply', action='store_true', help='Explicitly add/update saved networks on this device')
            cmd.add_argument('--limit', type=int)
            cmd.add_argument('--trial', action='store_true', help='With --apply, try one record from this scope')
            cmd.add_argument('--confirm-trial', action='store_true', help='Confirm phone-side verification before batch apply')
            cmd.add_argument('--resume', action='store_true')
    cmd = sub.add_parser('export-windows')
    cmd.add_argument('--out', type=Path)
    cmd = sub.add_parser('qr-pdf', help='Create an A4 PDF from a generated result')
    cmd.add_argument('run', type=Path)
    cmd.add_argument('--out', required=True, type=Path)
    cmd = sub.add_parser('archive', help='Copy and checksum an original backup file')
    cmd.add_argument('source', type=Path)
    cmd.add_argument('--root', type=Path, default=Path('runs/archives'))
    cmd.add_argument('--result', type=Path)
    cmd = sub.add_parser('verify-archive')
    cmd.add_argument('directory', type=Path)
    cmd = sub.add_parser('archive-history')
    cmd.add_argument('--root', type=Path, default=Path('runs/archives'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'gui':
            from .gui import launch
            launch()
            return 0
        if args.command == 'wizard':
            wizard()
            return 0
        if args.command in ('inspect', 'convert'):
            started = perf_counter()
            records, digest, kind = read_interactive(args.input)
            result = summarize(records) if args.command == 'inspect' else export_run(
                records, args.out or new_run(), digest, kind, not args.no_qr,
                parse_seconds=round(perf_counter() - started, 3))
        elif args.command == 'export-windows':
            result = export_windows(args.out or new_run())
        elif args.command == 'qr-pdf':
            result = export_pdf(args.run, args.out)
        elif args.command == 'archive':
            result = archive_file(args.source, args.root, args.result)
        elif args.command == 'verify-archive':
            result = verify_archive(args.directory)
        elif args.command == 'archive-history':
            result = archive_history(args.root)
        else:
            adb = Adb(args.adb)
            if args.command == 'devices':
                result = adb.devices()
            elif args.command == 'probe':
                result = adb.probe(args.serial)
            elif args.command == 'doctor':
                result = adb.migration_status(args.serial)
            elif args.command == 'backup':
                output = args.out or new_run()
                print('请在旧手机确认备份；命令结束后会检查目标数据。', file=sys.stderr)
                backup = adb.backup(args.serial, output / 'phone.adb', args.legacy_full)
                records, digest, kind = read_interactive(backup)
                result = export_run(records, output / 'result', digest, kind)
            elif args.command == 'push-qr':
                result = adb.push_qr(args.serial, args.run)
            else:
                records, digest, _ = read_interactive(args.input)
                default_out = import_report_path(args.input.parent, args.serial)
                one = args.apply and args.limit == 1 and not args.confirm_trial and not args.trial
                result = import_records(adb, args.serial, records, args.out or default_out,
                                        apply=args.apply, limit=None if one else args.limit, resume=args.resume,
                                        first_ready=args.trial or one, confirm_trial=args.confirm_trial,
                                        source_id=f'{args.input.resolve()}:{digest}')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and result.get('mode') == 'apply' and any(result.get(key, 0) for key in ('failed', 'skipped', 'save_acknowledged_unverified')):
            return 2
        return 0
    except (MigrationError, OSError, ValueError, KeyError, TypeError, EOFError, subprocess.TimeoutExpired) as error:
        log_failure(args.command, error)
        message = str(error) if isinstance(error, MigrationError) else '输入格式、依赖或系统调用失败，请检查输入与运行环境。'
        print('未完成：' + message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
