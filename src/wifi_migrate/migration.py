"""Route recommendations and an evidence log without credential fields."""
from datetime import datetime, timezone
import json
from collections import Counter
from pathlib import Path

from .errors import MigrationError

ROUTE_LABELS = {
    'wpm': '手机 App 批量导入', 'helper': '系统确认导入助手',
    'qr': '系统扫码', 'adb': '电脑直连（高级）',
}


def recommend(capabilities, app_records, qr_count):
    if app_records and capabilities.get('wpm_installed') and capabilities.get('shizuku_server_visible'):
        return 'wpm', '检测到 App 和 Shizuku 服务。请确认 App 授权；转换生成的 JSON 仍待真机验证。'
    sdk = str(capabilities.get('sdk', ''))
    if app_records and capabilities.get('system_add_ui_visible') and sdk.isdecimal() and int(sdk) >= 30:
        return 'helper', '检测到 Android 的系统保存入口。手机会逐批请求确认。'
    if qr_count:
        return 'qr', '可直接用手机系统扫码。'
    if app_records:
        return 'wpm', '可生成手机 App 导入文件。请先在手机确认 App 和 Shizuku 可用。'
    return 'adb', '当前结果没有可用二维码或 App 条目，请检查认证类型及设备能力。'


def record_event(run, route, target, status, *, evidence, count=None, details=None):
    path = Path(run) / 'migration-results.json'
    document = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema': 1, 'events': []}
    event = {'time': datetime.now(timezone.utc).isoformat(timespec='seconds'),
             'route': route, 'target': target or None, 'state': status, 'evidence': evidence}
    if count is not None:
        event['count'] = count
    if details:
        event['details'] = details
    document['events'].append(event)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    return path


def helper_results(path, source_digest, source_count=None):
    document = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(document, dict) or document.get('format') not in ('wifi-migrate-helper-v1', 'wifi-migrate-helper-v2'):
        raise MigrationError('请选择导入助手生成的结果 JSON。')
    if document.get('source_sha256') != source_digest:
        raise MigrationError('报告与本次导入 JSON 不匹配。请打开生成该报告的同一批结果。')
    results = document.get('results')
    states = {'SYSTEM_CONFIRMED', 'ALREADY_EXISTS', 'FAILED', 'SKIPPED', 'UNKNOWN', 'NOT_STARTED'}
    if not isinstance(results, list) or (source_count is not None and len(results) != source_count):
        raise MigrationError('助手结果条数与源 JSON 不一致。')
    cancelled = document.get('cancelled_batches', 0)
    if type(cancelled) is not int or cancelled < 0:
        raise MigrationError('助手结果中的取消批次数无效。')
    version = 2 if document['format'].endswith('v2') else 1
    rows = []
    batches = Counter()
    for index, result in enumerate(results, 1):
        row = {'index': index, 'id': f'{source_digest}:{index}'}
        if version == 1:
            state = result
        else:
            if not isinstance(result, dict) or result.get('id') != row['id']:
                raise MigrationError('助手报告的记录 ID 或顺序无效。')
            state = result.get('state')
            batch = result.get('batch')
            if type(batch) is not int or batch < 0 or ((batch == 0) != (state in ('SKIPPED', 'NOT_STARTED'))):
                raise MigrationError('助手报告的批次与记录状态不符。')
            if batch:
                batches[batch] += 1
            row['batch'] = batch
            reason = result.get('reason', '')
            if reason in ('wpa2_compatibility_only', 'unsupported_or_conflicting_configuration',
                          'missing_system_result', 'system_result_0', 'system_result_1', 'system_result_2'):
                row['reason'] = reason
        if type(state) is not str or state not in states:
            raise MigrationError('助手结果包含无法识别的状态。')
        rows.append({**row, 'state': state})
    remaining = sum(row['state'] == 'NOT_STARTED' for row in rows)
    processed = len(rows) - remaining - sum(row['state'] == 'SKIPPED' for row in rows)
    if version == 2:
        cancelled_ids = document.get('cancelled_batch_ids')
        if (not isinstance(cancelled_ids, list) or len(cancelled_ids) != cancelled
                or any(type(i) is not int or i <= 0 or i in batches for i in cancelled_ids)
                or len(set(cancelled_ids)) != cancelled or any(size > 5 for size in batches.values())
                or any(type(document.get(key)) is not int or document[key] != count for key, count in
                       [('source_count', len(rows)), ('processed_count', processed), ('unprocessed_count', remaining)])):
            raise MigrationError('助手报告的总数、处理数或批次不一致。')
    return {'report_version': version, 'cancelled_batches': cancelled, 'partial': remaining > 0,
            'processed_count': processed, 'unprocessed_count': remaining, 'rows': rows}
