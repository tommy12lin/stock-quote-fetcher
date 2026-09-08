"""All-or-nothing, offline CSV parsing."""

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
import re

from stock_quote_fetcher.models import Holding, Market


FIELDS = ("ticker", "buy_price", "quantity")
ASCII_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DECIMAL_TEXT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


@dataclass(frozen=True)
class InputIssue:
    line: int
    message: str


class InputValidationError(ValueError):
    def __init__(self, issues: list[InputIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"第 {item.line} 行：{item.message}" for item in issues))


def positive_decimal(text: str, field: str) -> Decimal:
    text = text.strip()
    if not DECIMAL_TEXT.fullmatch(text):
        raise ValueError(f"{field} 必須為有限且大於零的十進位數")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{field} 不是可表示的十進位數") from None
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field} 必須為有限且大於零的十進位數")
    return value


def parse_holdings(text: str) -> tuple[Holding, ...]:
    reader = csv.reader(StringIO(text.removeprefix("\ufeff"), newline=""), strict=True)
    issues: list[InputIssue] = []
    holdings: list[Holding] = []
    seen: dict[str, int] = {}
    line = 1
    try:
        header = next(reader, None)
        if header is None or len(header) != 3 or set(header) != set(FIELDS):
            raise InputValidationError([InputIssue(1, "欄名必須為 ticker、buy_price、quantity，且各出現一次")])
        previous_line = reader.line_num
        for row in reader:
            # Line below is the first physical line of this record (including multiline CSV).
            line = previous_line + 1
            previous_line = reader.line_num
            if len(row) != 3:
                issues.append(InputIssue(line, "每列必須恰有三欄，不接受空白列"))
                continue
            values = dict(zip(header, row, strict=True))
            ticker = values["ticker"].strip().translate(ASCII_UPPER)
            row_issues: list[InputIssue] = []
            market = None
            if ticker and "0" <= ticker[0] <= "9":
                market = Market.TW
            elif ticker and "A" <= ticker[0] <= "Z":
                market = Market.US
            else:
                row_issues.append(InputIssue(line, "ticker 必須以 ASCII 數字或英文字母開頭"))
            if ticker in seen:
                row_issues.append(InputIssue(line, f"ticker 重複（首次出現在第 {seen[ticker]} 行）"))
            elif ticker:
                seen[ticker] = line
            numbers: dict[str, Decimal] = {}
            for field in ("buy_price", "quantity"):
                try:
                    numbers[field] = positive_decimal(values[field], field)
                except ValueError as exc:
                    row_issues.append(InputIssue(line, str(exc)))
            quantity = numbers.get("quantity")
            if market == Market.TW and quantity is not None and quantity != quantity.to_integral_value():
                row_issues.append(InputIssue(line, "台股 quantity 必須為整數股"))
            if row_issues:
                issues.extend(row_issues)
            else:
                assert market is not None
                holdings.append(Holding(ticker, market, numbers["buy_price"], numbers["quantity"], line))
    except csv.Error:
        issues.append(InputIssue(max(reader.line_num, 1), "CSV 結構錯誤"))
    if not holdings and not issues:
        issues.append(InputIssue(max(reader.line_num, 1), "CSV 必須至少包含一筆持股"))
    if issues:
        raise InputValidationError(issues)
    return tuple(holdings)


def load_holdings(path: Path) -> tuple[Holding, ...]:
    raw = path.read_bytes()
    try:
        # Preserve BOM bytes while decoding so Unicode error offsets match raw.
        # parse_holdings removes the decoded BOM before reading the header.
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputValidationError([
            InputIssue(raw[:exc.start].count(b"\n") + 1, "檔案必須使用 UTF-8 編碼")
        ]) from None
    return parse_holdings(text)
