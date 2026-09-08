# 步驟 2 執行紀錄

日期：2026-09-08。範圍：離線 CSV、共用模型、Decimal 估值及 JSON 可序列化結果。這是第一個可操作的功能里程碑。

## 交付

| 檔案 | 功能 |
|---|---|
| src/stock_quote_fetcher/input.py | UTF-8／BOM、三欄、正規化、市場分類、數字／股數、重複與行號；任何錯誤整份拒絕 |
| src/stock_quote_fetcher/models.py | Holding、Instrument、Quote、FetchResult 與品質列舉；原始 ticker 與 provider symbol 分離、UTC 時間、拒絕 float |
| src/stock_quote_fetcher/valuation.py | 精確乘積與小計、ROUND_HALF_UP 顯示、缺價／品質排除／降級、分幣別 completeness、to_dict 輸出 |
| src/stock_quote_fetcher/cli.py | validate 成功退出 0，輸入／讀檔錯誤退出 2；錯誤寫 stderr，不輸出部分成功 |
| tests/test_input.py、test_valuation.py、test_cli.py | CSV、固定估值、異常品質及已安裝 CLI 入口驗證 |
| README、system-spec、architecture、development-plan | 操作方法、解析細節、模組責任與完成狀態 |

## 測試結果

固定 Python 3.14.7／linux amd64 映像與 uv 0.12.10，沿用步驟 1 的 uv.lock，沒有新增依賴。最終 `pytest -q -p no:cacheprovider`：**91 passed in 5.22s**。完整輸出見 [step-2-validation.txt](step-2-validation.txt)。

| 案例對照 | 已驗證範圍 |
|---|---|
| V02 | BOM、前導零、ASCII 大小寫、數字開頭含字母、未知標的仍可離線驗格式、台股整數／美股小數、欄位錯誤、重複、空列／空檔／只有標頭、非有限數、錯誤編碼、CSV 結構及跨行記錄行號 |
| V04 離線 | 台股 100.25 × 100＝10025.00 TWD；美股 200.10 × 2.5＝500.25 USD；買入價改變不影響市值；不產生跨幣別總額 |
| V04 精度 | 超過 28 位有效數字的乘積；外部 Decimal context 設為 4 位仍保留精確值；1e40 與 1e-40 加總；兩筆 0.005 的顯示各 0.01，但精確小計 0.010 顯示 0.01 |
| V08 離線 | complete／degraded／partial／unavailable；全缺價 total 為 null；錯標的／市場／幣別、0／負值／非有限價格、未來時間、未知時間、盤前後、bar_close、快取旗標與部分缺價的降級數 |
| CLI／模型 | help／version、缺參數、模組入口、未實作命令不冒充成功；不可變來源映射、失敗 FetchResult 不攜帶快取、未知品質列舉拒絕 |

5 秒未來時間邊界及品質政策均以固定資料測試，沒有查詢真實行情或驗證主機時鐘。報價新鮮度與交易日曆仍待來源整合。

## 斷網驗證

先從 sdist 建立 wheel，再以固定基礎映像執行 `docker run --rm --network none`，專案唯讀掛載，透過 pip 的 `--no-index --no-deps` 安裝 wheel。容器確認未安裝 psycopg、httpx、yfinance、exchange_calendars。

- `validate --input examples/holdings.csv`：成功，5 筆持股。
- 固定無效案例：前一列有效，下一列台股 quantity=1.5；退出 2，stderr 顯示第 3 行，stdout 為空。
- 測試中另封鎖 socket 建立，驗證有效及無效 CSV 都不嘗試連網。

輸出見 [step-2-offline-validation.txt](step-2-offline-validation.txt)。所有測試均未取得或使用資料庫密碼／API Key。

## 重跑

有 Python／uv 的開發環境：

```text
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen stock-poc validate --input examples/holdings.csv
uv build
```

此主機使用 Docker；可沿用 [步驟 1 的 PowerShell 安裝及測試命令](step-1-evidence.md)，加上 `uv build --out-dir /workspace/dist` 產生已忽略的測試 wheel。建置後，在專案根目錄用以下命令確認可斷網執行：

```powershell
docker run --rm --network none --platform linux/amd64 --mount "type=bind,source=$((Get-Location).Path),target=/workspace,readonly" python:3.14.7-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 sh -ec 'python -m pip install --disable-pip-version-check --no-index --no-deps /workspace/dist/stock_quote_fetcher-0.1.0-py3-none-any.whl; stock-poc validate --input /workspace/examples/holdings.csv'
```

## 後續界線

validate 僅驗證格式，不查清單或猜測來源後綴。估值函式接受上游已選用 Quote，保留 cache 原始時間及旗標，不實作來源選擇、快取查核、日曆新鮮度或重新抓價。to_dict 供後續 CSV／JSON 輸出整合使用；quote／monitor／report CLI、資料庫、migration 及完整 V04／V08 驗收仍待後續步驟。下一步為 PostgreSQL 持久化與 migration。
