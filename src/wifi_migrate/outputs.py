"""Create private run outputs and a portable, entirely offline QR review page."""
from __future__ import annotations
import base64
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from . import __version__
from .core import app_record, qr_payload, summarize
from .errors import MigrationError


def _review(items, digest):
    payload = json.dumps(items, ensure_ascii=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>WiFi Migrate · 离线扫码清单</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f8;color:#1f2937;font:16px/1.6 system-ui,sans-serif}
main{max-width:840px;margin:36px auto;padding:24px}h1{font-size:28px;margin:0 0 8px}.hint{color:#586575}
.card{background:white;border-radius:16px;padding:28px;margin:22px 0;text-align:center;box-shadow:0 5px 24px #2434500b}
img{width:min(100%,340px);image-rendering:pixelated}button,input{font:inherit;border:1px solid #cad1da;border-radius:8px;padding:10px 16px;margin:5px}
button{cursor:pointer;background:#fff}button.primary{background:#174bb3;color:white;border-color:#174bb3}button:disabled{opacity:.4;cursor:default}
input{width:min(100%,400px)}#name{overflow-wrap:anywhere}#state{min-height:28px}#status{font-size:14px}nav{text-align:center}footer{font-size:13px;color:#586575}
</style><main><h1>离线扫码清单</h1><p class="hint">请使用新手机的系统扫码功能。只有在系统已保存网络中确认后，再标记完成。此页面不会自动操作手机。</p>
<input id="search" placeholder="搜索网络名称"><span id="count"></span><div class="card"><div id="status"></div>
<h2 id="name"></h2><img id="qr" alt="WiFi 二维码"><p id="state"></p><button id="mark" class="primary">标记为已手动确认保存</button></div>
<nav><button id="prev">上一条</button><button id="next">下一条</button></nav><footer>不连接任何服务器。进度尽可能保存在当前浏览器中；标记只代表你的人工确认，不是系统导入检测。二维码本身包含网络凭据。</footer></main>
<script>const items=__ITEMS__,storageKey='wifi-migrate-__DIGEST__';let saved={},filtered=items,index=0;
try{saved=JSON.parse(localStorage.getItem(storageKey)||'{}')}catch(e){}const $=id=>document.getElementById(id);
function show(){const row=filtered[index];$('count').textContent=' '+Object.keys(saved).length+' / '+items.length+' 条已确认';
if(!row){$('status').textContent='';$('name').textContent='没有匹配记录';$('qr').hidden=true;$('state').textContent='';$('mark').disabled=true;$('prev').disabled=true;$('next').disabled=true;return}
$('name').textContent=row.ssid;$('status').textContent=(index+1)+' / '+filtered.length+' · '+row.security;
$('qr').hidden=!row.image;if(row.image)$('qr').src='data:image/png;base64,'+row.image;
$('state').textContent=row.image?((saved[row.id]?'已由你手动确认保存':'尚未确认')+(row.reason==='wpa2_compatibility_only'?' · 仅提供 WPA2 兼容项':'')):('未生成二维码：'+row.reason);
$('mark').disabled=!row.image;$('mark').textContent=saved[row.id]?'撤销此条确认':'标记为已手动确认保存';$('prev').disabled=index===0;$('next').disabled=index>=filtered.length-1;}
$('search').oninput=()=>{filtered=items.filter(r=>r.ssid.toLowerCase().includes($('search').value.toLowerCase()));index=0;show()};
$('prev').onclick=()=>{if(index>0)index--;show()};$('next').onclick=()=>{if(index<filtered.length-1)index++;show()};
$('mark').onclick=()=>{const r=filtered[index];if(saved[r.id])delete saved[r.id];else saved[r.id]=true;try{localStorage.setItem(storageKey,JSON.stringify(saved))}catch(e){}show()};
document.onkeydown=e=>{if(document.activeElement===$('search'))return;if(e.key==='ArrowLeft')$('prev').click();if(e.key==='ArrowRight')$('next').click()};show();</script></html>'''.replace('__DIGEST__', digest[:24]).replace('__ITEMS__', payload)


def export_run(records, output, digest, source_kind, make_qr=True, *, parse_seconds=None):
    output = Path(output)
    if output.exists():
        raise MigrationError('输出目录已存在，请选择新的目录。')
    if not records:
        raise MigrationError('没有可输出的网络记录。')
    qr_error = None
    requested_qr = make_qr
    if make_qr:
        try:
            import qrcode
            from qrcode.image.pure import PyPNGImage
        except ImportError:
            make_qr = False
            qr_error = '缺少二维码依赖 qrcode 或 pypng。可运行 python -m pip install -r requirements.txt。'
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.wifi-migrate-', dir=output.parent))
    try:
        (stage / 'networks.json').write_text(json.dumps({'schema': 1, 'networks': records}, ensure_ascii=False, indent=2), encoding='utf-8')
        candidates = [item for row in records if (item := app_record(row)) is not None]
        (stage / 'wifi-password-manager.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding='utf-8')
        rows, items = [], []
        if make_qr:
            (stage / 'qr').mkdir()
        for row in records:
            payload, reason = qr_payload(row)
            filename, encoded = '', ''
            if payload and make_qr:
                image_path = stage / 'qr' / (row['id'] + '.png')
                try:
                    image = qrcode.make(payload, image_factory=PyPNGImage, error_correction=qrcode.constants.ERROR_CORRECT_M)
                    with image_path.open('wb') as image_stream:
                        image.save(image_stream)
                    encoded = base64.b64encode(image_path.read_bytes()).decode('ascii')
                    filename = image_path.name
                except (ValueError, OSError, qrcode.exceptions.DataOverflowError):
                    image_path.unlink(missing_ok=True)
                    reason = 'qr_generation_failed'
                    qr_error = '部分二维码生成失败。CSV 和 JSON 已保留，请查看 CSV 的 QRStatus。'
            elif payload and requested_qr:
                reason = 'qr_dependency_missing'
            if not requested_qr:
                reason = 'not_requested'
            rows.append({'ID': row['id'], 'SSID': row['ssid'], 'Authentication': ', '.join(row['security']),
                         'Password': row['password'], 'Hidden': row['hidden'], 'SecurityTypes': ','.join(map(str, row['security_types'])),
                         'QRStatus': reason, 'QRFile': filename})
            items.append({'id': row['id'], 'ssid': row['ssid'], 'security': '/'.join(row['security']), 'image': encoded, 'reason': reason})
        with (stage / 'wifi.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (stage / 'review.html').write_text(_review(items, digest), encoding='utf-8')
        summary = summarize(records)
        summary.update(version=__version__, source_kind=source_kind, source_content_sha256=digest,
                       qr_written=sum(bool(row['QRFile']) for row in rows), phone_import_verified=False,
                       app_records=len(candidates), app_skipped=len(records) - len(candidates),
                       app_adapter_status='experimental_schema_only')
        if parse_seconds is not None:
            summary['parse_seconds'] = parse_seconds
        if qr_error:
            summary['qr_warning'] = qr_error
        (stage / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest = []
        for file in sorted(stage.rglob('*')):
            if file.is_file():
                manifest.append({'path': file.relative_to(stage).as_posix(), 'bytes': file.stat().st_size,
                                 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        if output.exists():
            raise MigrationError('输出目录已被其他操作创建，已停止写入。')
        stage.rename(output)
        return summary
    finally:
        if stage.exists():
            shutil.rmtree(stage)
