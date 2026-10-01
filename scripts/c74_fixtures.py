"""C7-4 test workbooks. Fake holdings only (D5); the outputs are git-ignored xlsx.

Writes to output/c74/ and prints each file's SHA-256 for the evidence file:

  F2  errors on three sheets with Chinese names; the third sheet parses cleanly but
      holds a ticker no catalog has, so it passes preview and fails at save.
  F3  more tickers than refresh_max_tickers (27) and the chart's 15-slice limit.
  F5  exactly MAX_UPLOAD bytes, which the frontend and the Worker both accept, so the
      Worker's CPU time for a full-size body can be read from tail.
  F6  MAX_UPLOAD + 1 bytes, for the Worker's 413. The frontend refuses it before any
      request, so it can only be sent from DevTools.

F1 is the user's own 持股範本.xlsx and F4 is the site's downloaded template; neither
is generated here.
"""
import hashlib
from io import BytesIO
from pathlib import Path
import random
import sys
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from c76_probe import FIXED  # noqa: E402  step 9's fixed list, kept as the one source

from stock_quote_fetcher.web_input import MAX_UPLOAD, preview_xlsx

OUT = Path('output/c74')
MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RELS = 'http://schemas.openxmlformats.org/package/2006/relationships'
DOC_RELS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

# Well-known listed and OTC names on top of FIXED; all must resolve against the
# official catalog, or the save in C3 fails and says which one.
WIDE_EXTRA = ('2454', '2308', '2382', '2412', '2881', '2882', '2891', '1301', '1303', '2002',
              '2303', '3711', '2886', '2884', '1216', '2207', '3008', '2357', '5347', '8069', '6274')


def cell(ref, value):
    """str → inline text, int → number, ('=', text) → formula."""
    if isinstance(value, tuple):
        return f'<c r="{ref}"><f>{escape(value[1])}</f><v>0</v></c>'
    if isinstance(value, int):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'


def sheet_xml(rows):
    body = ''.join(f'<row r="{i}">' + ''.join(cell(f'{col}{i}', v) for col, v in zip('ABC', values)) + '</row>'
                   for i, values in enumerate(rows, 1))
    return f'<worksheet xmlns="{MAIN}"><sheetData>{body}</sheetData></worksheet>'


def workbook(sheets, pad_to=None):
    """pad_to grows the archive to an exact byte count with an uncompressed entry of
    random bytes, which the parser never opens. A stored entry adds exactly its length,
    so one measurement at zero padding gives the size to add."""
    if pad_to is not None:
        base = len(build(sheets, b''))
        data = build(sheets, random.Random(74).randbytes(pad_to - base))
        if len(data) != pad_to:
            raise RuntimeError(f'padded to {len(data)}, wanted {pad_to}')
        return data
    return build(sheets, None)


def put(z, name, data, compress=ZIP_DEFLATED):
    """A fixed timestamp, so the same script always yields the same bytes and the
    SHA-256 in the evidence file can be reproduced."""
    info = ZipInfo(name, date_time=(2026, 10, 1, 0, 0, 0))
    info.compress_type = compress
    z.writestr(info, data)


def build(sheets, padding):
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as z:
        overrides = ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                            for i in range(1, len(sheets) + 1))
        put(z, '[Content_Types].xml', f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>{overrides}</Types>')
        put(z, '_rels/.rels', f'<Relationships xmlns="{RELS}"><Relationship Id="r1" Type="{DOC_RELS}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        entries = ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="r{i}"/>' for i, (name, _) in enumerate(sheets, 1))
        put(z, 'xl/workbook.xml', f'<workbook xmlns="{MAIN}" xmlns:r="{DOC_RELS}"><sheets>{entries}</sheets></workbook>')
        links = ''.join(f'<Relationship Id="r{i}" Type="{DOC_RELS}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
        put(z, 'xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{RELS}">{links}</Relationships>')
        for i, (_, rows) in enumerate(sheets, 1):
            put(z, f'xl/worksheets/sheet{i}.xml', sheet_xml(rows))
        if padding is not None:
            put(z, 'xl/media/padding.bin', padding, ZIP_STORED)
    return stream.getvalue()


HEADER = ('股票代碼', '持有股數', '平均買入價')
SMALL = [HEADER, ('0050', '100', '50'), ('AAPL', '2', '150')]

FILES = {
    'F2 錯誤與工作表.xlsx': [
        ('儲存格錯誤', [HEADER, (2330, '10', '500'), ('AAPL', ('=', '1+1'), '150')]),
        ('數值錯誤', [HEADER, ('2330', '-5', '500')]),
        ('無法識別代碼', [HEADER, ('0050', '100', '50'), ('ZZZZ9', '1', '10')]),
    ],
    'F3 寬名單.xlsx': [
        ('寬名單', [HEADER] + [(t, str(10 * (i + 1)), str(20 + i)) for i, t in enumerate(FIXED + WIDE_EXTRA)]),
    ],
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    built = {name: workbook(sheets) for name, sheets in FILES.items()}
    built['F5 剛好 5 MiB.xlsx'] = workbook([('持股', SMALL)], pad_to=MAX_UPLOAD)
    built['F6 超過 5 MiB.xlsx'] = workbook([('持股', SMALL)], pad_to=MAX_UPLOAD + 1)
    for name, data in built.items():
        (OUT / name).write_bytes(data)
        print(f'{hashlib.sha256(data).hexdigest()}  {len(data):>8}  {name}')
    # Self-check against the same parser the service runs, so a fixture bug shows here
    # rather than as a surprise in the cloud.
    for name, data in built.items():
        if name.startswith('F6'):
            continue
        for sheet in (preview_xlsx(data)['sheets'] if not name.startswith('F5') else [None]):
            r = preview_xlsx(data, sheet)
            print(f'  {name} / {r["sheet"]}: {len(r["rows"])} rows, {len(r["issues"])} issues',
                  *[f'\n    row {x["row"]} {x["field"]}: {x["message"]}' for x in r['issues']])


if __name__ == '__main__':
    main()
