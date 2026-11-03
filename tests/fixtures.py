"""All credentials in this module are invented test data."""
import io
import tarfile
from xml.sax.saxutils import escape, quoteattr


def xml_record(ssid='SYNTHETIC-LAB-NETWORK', password='SyntheticSecret!42', types=(2, 4), hidden=False, wep=None, tx=0, extra=''):
    content = '<WifiConfiguration>'
    content += f'<string name="SSID">{escape(chr(34)+ssid+chr(34))}</string>'
    content += f'<string name="PreSharedKey">{escape(chr(34)+password+chr(34))}</string>'
    content += f'<boolean name="HiddenSSID" value="{str(hidden).lower()}"/>'
    content += '<SecurityParamsList>' + ''.join(f'<int name="SecurityType" value="{t}"/>' for t in types) + '</SecurityParamsList>'
    if wep is not None:
        content += f'<int name="WEPTxKeyIndex" value="{tx}"/>'
        content += '<string-array name="WEPKeys">' + ''.join(f'<item value={quoteattr(key)}/>' for key in wep) + '</string-array>'
    return (content + extra + '</WifiConfiguration>').encode('utf-8')


def tar_bytes(data, member='apps/com.android.providers.settings/k/com.android.providers.settings.data', duplicate=False, filler=0):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        if filler:
            entry = tarfile.TarInfo('apps/synthetic.large/files/padding')
            entry.size = filler
            archive.addfile(entry, io.BytesIO(b'\0' * filler))
        for _ in range(2 if duplicate else 1):
            entry = tarfile.TarInfo(member)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return stream.getvalue()
