"""Bounded XLSX import; no formulas, cached values, or original-file persistence."""
import csv
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP, localcontext
from io import BytesIO, StringIO
import posixpath
import re
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
from xml.etree import ElementTree as ET

from stock_quote_fetcher.input import parse_holdings, InputValidationError, positive_decimal

FIELDS = ('ticker', 'quantity', 'buy_price')
ALIASES = dict(zip(('股票代碼', '持有股數', '平均買入價'), FIELDS))
MAX_UPLOAD = 5 * 1024 * 1024


def round_input(number):
    with localcontext() as context:
        context.prec = 32
        return number.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP).normalize()


class WebError(ValueError):
    def __init__(self, message, *, code='invalid_input', status=400, issues=None):
        super().__init__(message)
        self.status = status
        self.payload = {'code': code, 'message': message, 'issues': issues or []}


def validate_rows(rows):
    if not isinstance(rows, list) or len(rows) > 500:
        raise WebError('持股最多 500 筆。')
    if not rows:
        return ()
    stream = StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(FIELDS)
    for i, row in enumerate(rows, 2):
        if not isinstance(row, dict) or set(row) != set(FIELDS) or any(type(row[k]) is not str for k in FIELDS):
            raise WebError('每列需有三個文字欄位。')
        for field in FIELDS:
            if len(row[field]) > 64 or '\n' in row[field] or '\r' in row[field]:
                raise WebError(f'第 {i} 列 {field} 過長或含換行。')
            if field != 'ticker':
                try:
                    number = positive_decimal(row[field], field)
                    if number.adjusted() > 15:
                        raise ValueError('數值最多 16 位整數；小數超過 4 位會四捨五入。')
                    rounded = round_input(number)
                    if rounded == 0:
                        raise ValueError('四捨五入至 4 位小數後必須大於 0，請輸入至少 0.00005。')
                    if rounded.adjusted() > 15:
                        raise ValueError('四捨五入後數值最多 16 位整數。')
                except ValueError as exc:
                    raise WebError(str(exc), issues=[{'row': i, 'field': field, 'message': str(exc)}]) from None
        writer.writerow([row[k] for k in FIELDS])
    try:
        holdings = parse_holdings(stream.getvalue())
        return tuple(replace(h, quantity=round_input(h.quantity), buy_price=round_input(h.buy_price)) for h in holdings)
    except InputValidationError as exc:
        raise WebError('請修正持股資料。', issues=[{'row': x.line, 'field': 'ticker' if 'ticker' in x.message else 'quantity' if 'quantity' in x.message else 'buy_price', 'message': x.message} for x in exc.issues]) from None


def normalize(holdings):
    return [{k: getattr(h, k) if k == 'ticker' else format(getattr(h, k), 'f') for k in FIELDS} for h in holdings]


def preview_xlsx(raw, sheet=None):
    if len(raw) > MAX_UPLOAD:
        raise WebError('檔案不得超過 5 MiB。')
    try:
        with ZipFile(BytesIO(raw)) as archive:
            info = archive.infolist()
            if len(info) > 2000 or sum(x.file_size for x in info) > 50 * 1024 * 1024 or any(x.flag_bits & 1 for x in info):
                raise WebError('檔案解壓後過大、內容過多或已加密。')
            if len({x.filename for x in info}) != len(info):
                raise WebError('檔案包含重複項目。')
            def xml(name):
                data = archive.read(name)
                if b'\x00' in data or b'<!DOCTYPE' in data or b'<!ENTITY' in data:
                    raise WebError('不支援含 XML 實體宣告的檔案。')
                return ET.fromstring(data)
            content = archive.read('[Content_Types].xml')
            if b'macroEnabled' in content or b'vbaProject' in content:
                raise WebError('只接受不含巨集的 .xlsx。')
            relations = {e.attrib['Id']: e.attrib['Target'] for e in xml('xl/_rels/workbook.xml.rels') if e.attrib.get('TargetMode') != 'External'}
            sheets = {e.attrib['name']: relations[e.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']] for e in xml('xl/workbook.xml').findall('.//{*}sheet')}
            if not sheets or len(sheets) > 64:
                raise WebError('工作表數量必須介於 1–64。')
            selected = sheet or next(iter(sheets))
            if selected not in sheets:
                raise WebError('找不到工作表。')
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(e.itertext()) for e in xml('xl/sharedStrings.xml')]
            dates = set()
            if 'xl/styles.xml' in archive.namelist():
                styles = xml('xl/styles.xml')
                custom = {int(e.attrib['numFmtId']): e.attrib['formatCode'] for e in styles.findall('.//{*}numFmt')}
                for i, e in enumerate(styles.findall('./{*}cellXfs/{*}xf')):
                    fmt = int(e.attrib.get('numFmtId', 0))
                    if 14 <= fmt <= 22 or 45 <= fmt <= 47 or re.search('[ymdhs]', custom.get(fmt, ''), re.I):
                        dates.add(i)
            target = sheets[selected]
            path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
            if not path.startswith('xl/'):
                raise WebError('工作表路徑無效。')
            rows, issues = {}, []
            for row in xml(path).findall('./{*}sheetData/{*}row'):
                number = int(row.attrib['r'])
                values = {}
                for c in row.findall('{*}c'):
                    reference = c.attrib.get('r', '')
                    match = re.fullmatch(r'([A-Z]+)([0-9]+)', reference)
                    if not match:
                        raise WebError('儲存格座標無效。')
                    col = match[1]
                    kind = c.attrib.get('t', 'n')
                    value = c.findtext('{*}v', '')
                    if kind == 's':
                        value = strings[int(value)]
                    elif kind == 'inlineStr':
                        value = ''.join(c.find('{*}is').itertext())
                    bad = c.find('{*}f') is not None or kind in {'b', 'e', 'd'} or int(c.attrib.get('s', 0)) in dates
                    if value or bad:
                        values[col] = (value, kind, bad)
                if values:
                    rows[number] = values
            if not rows or max(rows) > 501:
                raise WebError('工作表需有標頭，且最多 500 筆持股。')
            header = rows.get(1, {})
            columns = {col: ALIASES.get(v[0].strip(), v[0].strip()) for col, v in header.items()}
            if len(columns) != 3 or set(columns.values()) != set(FIELDS) or any(v[2] for v in header.values()):
                raise WebError('第一列欄名需為 ticker、quantity、buy_price（或對應中文），且各一次。')
            data = []
            for number in range(2, max(rows) + 1):
                values, record = rows.get(number, {}), {}
                if set(values) - set(columns):
                    issues.append({'row': number, 'field': '', 'message': '資料含標頭以外的欄位。'})
                for col, field in columns.items():
                    value, kind, bad = values.get(col, ('', 's', False))
                    record[field] = value
                    if bad or (field == 'ticker' and kind not in {'s', 'inlineStr'}):
                        issues.append({'row': number, 'field': field, 'message': '不接受公式、日期、布林或錯誤值；股票代碼必須儲存為文字。'})
                data.append(record)
            if not issues:
                try:
                    data = normalize(validate_rows(data))
                    if not data:
                        raise WebError('至少需要一筆持股。')
                except WebError as exc:
                    issues = exc.payload['issues'] or [{'row': 2, 'field': '', 'message': str(exc)}]
            return {'sheets': list(sheets), 'sheet': selected, 'rows': data, 'issues': [dict(x, sheet=selected, code='invalid_cell') for x in issues]}
    except (BadZipFile, KeyError, ValueError, IndexError, ET.ParseError, RuntimeError) as exc:
        if isinstance(exc, WebError):
            raise
        raise WebError('無法解析檔案，請使用未加密的標準 .xlsx。') from None


def template_xlsx():
    """Small standards-based OOXML template, with explicit text ticker cells."""
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="持股" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        rows = []
        for i, values in enumerate([FIELDS, ('0050','100','50'), ('AAPL','2','150')], 1):
            cells = ''.join(f'<c r="{col}{i}" t="inlineStr"><is><t>{v}</t></is></c>' for col, v in zip('ABC', values))
            rows.append(f'<row r="{i}">{cells}</row>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(rows) + '</sheetData></worksheet>')
    return stream.getvalue()


def bounded_preview(raw, sheet=None):
    """Isolate workbook expansion and XML parsing from the HTTP service."""
    import json
    import subprocess
    import sys
    try:
        result = subprocess.run([sys.executable, '-m', __name__, sheet or ''], input=raw,
                                capture_output=True, timeout=15, check=False)
        if result.returncode:
            raise WebError('解析資源超限或檔案無效，請縮小工作表後重試。')
        data = json.loads(result.stdout)
        if 'error' in data:
            raise WebError(data['error'])
        return data
    except subprocess.TimeoutExpired:
        raise WebError('解析超過 15 秒，請縮小工作表後重試。') from None


if __name__ == '__main__':
    import json
    import sys
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    except ImportError:
        pass  # Windows still has the parent timeout and compressed/expanded limits.
    try:
        result = preview_xlsx(sys.stdin.buffer.read(MAX_UPLOAD + 1), sys.argv[1] or None)
    except (WebError, MemoryError) as exc:
        result = {'error': str(exc) or '檔案解析記憶體超限。'}
    print(json.dumps(result, ensure_ascii=False))
