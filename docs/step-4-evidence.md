# 步驟 4 執行紀錄

日期：2026-09-08。狀態：標的清單來源、解析、映射、快取、PostgreSQL migration 及容器正式更新均完成。

## 已交付

| 檔案 | 功能 |
|---|---|
| src/stock_quote_fetcher/instruments.py | 官方清單解析、股票／ETF 白名單、外幣 ETF 排除、Yahoo 代碼映射、查無／不支援／歧義處理 |
| src/stock_quote_fetcher/catalog.py | 五個固定 HTTPS 來源、回應大小與 Content-Type 限制、公司 CA 與來源別 strict-mode 設定 |
| src/stock_quote_fetcher/migrations/0002_instrument_catalog.sql | 清單 generation、來源證據、標的、別名及 provider symbol 持久化 |
| src/stock_quote_fetcher/storage.py | 原子發布完整 generation、24 小時預設有效期及只讀載入 |
| src/stock_quote_fetcher/cli.py | `instruments-refresh` 與 `resolve` |
| tests/test_instruments.py、test_catalog.py、test_storage.py | 解析、類型篩選、TLS、映射、過期、原子性及資料庫整合案例 |

## 來源與規則

| 來源 | 用途 | 解析規則 |
|---|---|---|
| TWSE `t187ap03_L` | 上市公司 | 公司代號，stock，Yahoo `.TW` |
| TWSE `t187ap47_L` | 上市 ETF | 官方基金類型需為指數股票型基金或交易所交易基金；依官方編碼規則排除外幣加掛類別 |
| TWSE ISIN `strMode=4` | 上櫃股票及 ETF | 只接受官方「股票」／「ETF」分類，並以 CFICode `ES`／`CE` 交叉驗證；Yahoo `.TWO` |
| Nasdaq Trader `nasdaqlisted.txt` | Nasdaq 股票及 ETF | 排除 test issue 與非正常 financial status；ETF 使用官方旗標，股票採保守的名稱類型白名單 |
| Nasdaq Trader `otherlisted.txt` | NYSE、NYSE American、NYSE Arca、Cboe BZX、IEX | 排除 test issue 及非股票／ETF；保存 ACT、CQS、Nasdaq aliases，Yahoo 股別以 `.` 轉 `-`，如 `BRK.B` → `BRK-B` |

美股官方目錄未提供完整的 security-type 欄位。ETF 可直接使用官方 ETF flag；非 ETF 僅接受名稱明示 Common Stock／Common Shares／Ordinary Shares／ADS／ADR 等類型，並排除 warrant、right、unit、preferred、note、bond 等。此策略可能保守地拒絕少數合法股票，但不會將未確認商品猜成股票；查無與被篩除目前統一回報 `not_found_or_unsupported`。

台股幣別固定為本 POC 支援的 TWD。ETF 依 TWSE／TPEx 官方代碼規則排除外幣加掛類別；步驟 5 仍會用報價來源回傳的 currency／quoteType 再檢查一次。

## 實測

- Linux amd64／Python 3.14.7 完整測試：**141 passed in 8.77s**。見 [step-4-validation.txt](step-4-validation.txt)。
- sdist／wheel 建置及乾淨 venv 安裝成功；wheel 包含 `0002_instrument_catalog.sql`。
- 實際專案 PostgreSQL 17.10：套用 1 個新 migration；第二次套用 0；完整 schema／checksum／權限檢查通過。
- 隔離 PostgreSQL 使用 internal network、tmpfs、無 host port；測試 generation 原子發布、過期拒絕及重複 market/ticker 不發布。
- 容器正式更新取得 Nasdaq Trader 清單：`nasdaq_listed` 4,295 筆、`nasdaq_other` 6,688 筆。
- 透過 Windows 信任存放區取得台股官方實際資料並直接串流至同一容器解析：TWSE 公司 1,094 筆（2330 → `2330.TW`）、TWSE TWD ETF 257 筆（0050 → `0050.TW`）、TPEx 股票／TWD ETF 1,009 筆（6488 → `6488.TWO`）。資料未寫入 repository。

Windows `curl --ssl-no-revoke` 僅關閉憑證撤銷狀態檢查，以因應公司代理無法提供撤銷資訊；鏈與主機名驗證仍啟用。產品程式不使用此選項。容器程式保持鏈與主機名驗證；只有設定於 `tls.relaxed_sources` 的來源會載入公司 CA 並移除 Python 3.13+ 的 `VERIFY_X509_STRICT`。

## 正式更新結果

從 Windows CurrentUser Root store 依已知 SHA-1 指紋 `92715B2174E4131E2FF6B57295B7309B9AE87519` 找到 `CN=ACLCA, DC=ADVANTECH, DC=CORP`。CurrentUser／LocalMachine 兩份相同，皆為自簽根且 `HasPrivateKey=False`。匯出 CurrentUser 的公開憑證至已忽略的 `secrets/company-root-ca.crt`，容器內再次核對 subject、issuer 與 SHA-1 指紋後唯讀掛載。本機 `config.toml` 設定如下：

```toml
[tls]
company_ca_file = "/run/secrets/company-root-ca.crt"
relaxed_sources = ["twse_companies", "twse_funds", "tpex_isin"]
```

依賴安裝時公司代理也攔截 PyPI；臨時容器先用 `update-ca-certificates` 安裝此公開 CA，再以 uv `--system-certs` 完成 frozen 安裝。這是步驟 7 Dockerfile／Compose 必須納入的環境操作，應用抓取仍使用來源別 SSLContext 並只對上述三個來源移除 `VERIFY_X509_STRICT`。

正式 `instruments-refresh` 成功發布 generation `20434d08-1298-4c48-bf9f-bd3d886c6500`，共 13,343 筆，2026-09-09T05:08:50Z 到期：

| 來源 | 有效筆數 | TLS relaxed |
|---|---:|---|
| twse_companies | 1,094 | true |
| twse_funds | 257 | true |
| tpex_isin | 1,009 | true |
| nasdaq_listed | 4,295 | false |
| nasdaq_other | 6,688 | false |

匿名範例 `resolve` 全數成功：2330 → TWSE stock／2330.TW；0050 → TWSE ETF／0050.TW；6488 → TPEx stock／6488.TWO；AAPL → NASDAQ-Q stock／AAPL；VOO → NYSE Arca ETF／VOO。

本機憑證與 config.toml 均被 Git 忽略，未納入版本控制。臨時 app 容器於驗證後移除；正式 generation 保留於既有 PostgreSQL。步驟 4 完成，下一步為步驟 5 Provider、品質檢查與單次 quote。
