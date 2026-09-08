"""Exercise the installed console entry point and its public exit-code contract."""

from importlib.metadata import version
import subprocess
import sys

import pytest


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["stock-poc", *args], capture_output=True, text=True, encoding="utf-8", check=False
    )


def test_help_lists_commands():
    result = run_cli("--help")
    assert result.returncode == 0
    for command in ("validate", "db-check", "migrate", "instruments-refresh", "resolve", "quote", "monitor", "report"):
        assert command in result.stdout


def test_installed_version():
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"stock-poc {version('stock-quote-fetcher')}"


@pytest.mark.parametrize("args", [(), ("unknown",), ("validate",)])
def test_usage_errors(args):
    assert run_cli(*args).returncode == 2


@pytest.mark.parametrize("command", ["monitor", "report"])
def test_unimplemented_commands_cannot_report_success(command, tmp_path):
    missing_input = tmp_path / "missing.csv"
    output = tmp_path / "output"
    if command == "report":
        args = ["--run-id", "example", "--output", str(output)]
    else:
        args = ["--input", str(missing_input)]
        if command != "validate":
            args += ["--config", str(tmp_path / "missing.toml"), "--output", str(output)]
    result = run_cli(command, *args)
    assert result.returncode == 1
    assert "尚未實作" in result.stderr
    assert not result.stdout
    assert not output.exists()


def test_module_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "stock_quote_fetcher", "--version"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert result.stdout == run_cli("--version").stdout


def test_validate_valid_file(tmp_path):
    path = tmp_path / "holdings.csv"
    path.write_text("ticker,buy_price,quantity\n0050,50,200\naapl,180,2.5\n", encoding="utf-8-sig")
    result = run_cli("validate", "--input", str(path))
    assert result.returncode == 0
    assert "2 筆" in result.stdout
    assert not result.stderr


def test_validate_rejects_whole_file(tmp_path):
    path = tmp_path / "holdings.csv"
    path.write_text("ticker,buy_price,quantity\nAAPL,1,1\n2330,1,1.5\n", encoding="utf-8")
    result = run_cli("validate", "--input", str(path))
    assert result.returncode == 2
    assert "第 3 行" in result.stderr
    assert not result.stdout


def test_validate_missing_file(tmp_path):
    result = run_cli("validate", "--input", str(tmp_path / "missing.csv"))
    assert result.returncode == 2
    assert "無法讀取" in result.stderr
    assert "Traceback" not in result.stderr


def test_validate_without_network_calls(monkeypatch, tmp_path):
    import socket
    from stock_quote_fetcher.cli import main

    def forbidden(*args, **kwargs):
        raise AssertionError("validate must never access network or database sockets")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    path = tmp_path / "holdings.csv"
    path.write_text("ticker,buy_price,quantity\nUNKNOWN,1,0.5\n", encoding="utf-8")
    assert main(["validate", "--input", str(path)]) == 0
    path.write_text("ticker,buy_price,quantity\nUNKNOWN,0,0.5\n", encoding="utf-8")
    assert main(["validate", "--input", str(path)]) == 2


def test_database_cli_configuration_errors_are_redacted(monkeypatch, tmp_path, capsys):
    from stock_quote_fetcher.cli import main
    monkeypatch.delenv('DB_PASSWORD',raising=False)
    path = tmp_path / 'config.toml'
    path.write_text('[database]\npassword="sensitive-example"\n')
    for command in ('db-check','migrate'):
        assert main([command,'--config',str(path)]) == 2
        output = capsys.readouterr()
        assert not output.out and 'sensitive-example' not in output.err
