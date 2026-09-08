from decimal import Decimal

import pytest

from stock_quote_fetcher.input import InputValidationError, load_holdings, parse_holdings
from stock_quote_fetcher.models import Market


HEADER = "ticker,buy_price,quantity\n"


def test_normalization_and_market_rules():
    rows = parse_holdings("\ufeff" + HEADER + " 0050 , 50.001 , 200.0 \n00400a,1,1\naapl,180,2.5\n")
    assert [row.ticker for row in rows] == ["0050", "00400A", "AAPL"]
    assert [row.market for row in rows] == [Market.TW, Market.TW, Market.US]
    assert [row.currency for row in rows] == ["TWD", "TWD", "USD"]
    assert rows[0].buy_price == Decimal("50.001")
    assert rows[2].quantity == Decimal("2.5")


def test_header_order_and_numeric_notation():
    row, = parse_holdings("quantity,ticker,buy_price\n2.5,aapl,1.8e2\n")
    assert row.buy_price == Decimal("180")


@pytest.mark.parametrize("text", [
    "", HEADER, "ticker,buy_price\nAAPL,1\n", "ticker,quantity,quantity\nAAPL,1,1\n",
    "ticker,buy_price,quantity,market\nAAPL,1,1,US\n",
    HEADER + "AAPL,1\n", HEADER + "AAPL,1,1,extra\n", HEADER + "\n",
    HEADER + "AAPL,1,1\n\n", HEADER + '"AAPL,1,1\n',
])
def test_invalid_csv_structure(text):
    with pytest.raises(InputValidationError):
        parse_holdings(text)


@pytest.mark.parametrize("value", ["", "abc", "NaN", "sNaN", "Infinity", "-Infinity", "0", "-1", "1_000", "１２"])
@pytest.mark.parametrize("field", ["buy_price", "quantity"])
def test_invalid_numbers(value, field):
    row = {"ticker": "AAPL", "buy_price": "1", "quantity": "1"}
    row[field] = value
    with pytest.raises(InputValidationError) as caught:
        parse_holdings(HEADER + ",".join(row.values()))
    assert caught.value.issues[0].line == 2
    assert field in caught.value.issues[0].message


@pytest.mark.parametrize("ticker", ["", "@AAPL", "_AAPL", "２330", "台積電", "ßfoo"])
def test_non_ascii_initial_rejected(ticker):
    with pytest.raises(InputValidationError):
        parse_holdings(HEADER + f"{ticker},1,1\n")


def test_tw_fraction_rejected_but_unknown_ascii_symbol_stays_offline():
    with pytest.raises(InputValidationError, match="整數"):
        parse_holdings(HEADER + "2330,1,1.5\n")
    assert parse_holdings(HEADER + "NOTAREALSTOCK,1,0.25\n")[0].market == Market.US


def test_duplicate_and_multiple_errors_reject_whole_input():
    with pytest.raises(InputValidationError) as caught:
        parse_holdings(HEADER + "AAPL,1,1\n aapl ,2,1\n2330,0,1.5\n")
    assert [item.line for item in caught.value.issues] == [3, 4, 4]
    assert "第 2 行" in caught.value.issues[0].message
    assert not hasattr(caught.value, "holdings")


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_physical_lines_for_multiline_records(newline):
    text = newline.join(["ticker,buy_price,quantity", '"', 'AAPL",1,1', "AAPL,2,1", ""])
    with pytest.raises(InputValidationError) as caught:
        parse_holdings(text)
    assert caught.value.issues[0].line == 4
    assert "第 2 行" in caught.value.issues[0].message


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_invalid_encoding(tmp_path, bom):
    path = tmp_path / "bad.csv"
    path.write_bytes(bom + HEADER.encode() + b"\xff,1,1\n")
    with pytest.raises(InputValidationError, match="UTF-8") as caught:
        load_holdings(path)
    assert caught.value.issues[0].line == 2
