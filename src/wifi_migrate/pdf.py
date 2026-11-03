"""A4 QR handout generated from the existing per-network PNG files."""
import json
import os
from pathlib import Path

from .errors import MigrationError


def export_pdf(run, output, selected=None):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError as error:
        raise MigrationError('生成 PDF 需要安装 PDF 依赖（pip install ".[pdf]"）。') from error
    run, output = Path(run), Path(output)
    rows = json.loads((run / 'networks.json').read_text(encoding='utf-8'))['networks']
    images = {path.stem: path for path in (run / 'qr').glob('*.png')}
    rows = [row for row in rows if row['id'] in images and (selected is None or row['id'] in selected)]
    if not rows:
        raise MigrationError('所选记录没有可打印的二维码。')
    if output.exists():
        raise MigrationError('PDF 已存在，请选择新的文件名。')
    font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
    font = 'WiFiLabels' if font_path.is_file() else 'STSong-Light'
    pdfmetrics.registerFont(TTFont(font, str(font_path)) if font_path.is_file() else UnicodeCIDFont(font))
    width, height = A4
    pdf = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
    pdf.setTitle('WiFi Migrate - QR handout')
    for page in range(0, len(rows), 12):
        pdf.setFont('Helvetica-Bold', 16)
        pdf.drawString(32, height - 40, 'WiFi Migrate')
        pdf.setFont(font, 10)
        pdf.drawString(32, height - 57, '使用系统相机扫码。二维码包含网络凭据，请妥善保管。')
        pdf.drawRightString(width - 32, 24, f'{page // 12 + 1} / {(len(rows) + 11) // 12}')
        for index, row in enumerate(rows[page:page + 12]):
            column, line = index % 3, index // 3
            x, y = 32 + (width - 64) / 3 * (column + 0.5), height - 211 - line * 160
            pdf.drawImage(str(images[row['id']]), x - 56, y + 18, 112, 112)
            label = row['ssid'].replace('\n', ' ').replace('\r', ' ')
            while pdfmetrics.stringWidth(label, font, 10) > 156:
                label = label[:-2] + '…'
            pdf.drawCentredString(x, y + 5, label)
            pdf.setFont('Helvetica', 8)
            suffix = ' / WPA2 only' if set(row['security_types']) == {2, 4} else ''
            pdf.drawCentredString(x, y - 7, row['id'] + suffix)
            pdf.setFont(font, 10)
        pdf.showPage()
    pdf.save()
    return {'pdf': str(output), 'qr_count': len(rows), 'pages': (len(rows) + 11) // 12}
