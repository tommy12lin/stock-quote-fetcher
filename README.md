# 台美股報價與持股市值 POC

以 Python 與 Docker Container 驗證台美股盤中報價的可取得性、資料時效與持續運行可靠性。使用 CSV 輸入持股，透過指令操作，分別呈現 TWD 與 USD 市值小計。

## 目前狀態

- 2026-09-08：完成步驟 5 單次 quote、四個 Provider、品質檢查、重試／冷卻、快取與 CSV／JSON 輸出；Yahoo、Finnhub、TWSE 與 TPEx 均通過真實容器驗證。見 [步驟 5 證據](docs/step-5-evidence.md)。

- 2026-09-08：完成步驟 4 官方標的解析、映射、快取與 migration；141 項測試通過，容器正式保存 13,343 筆五來源 generation，匿名範例全數 resolve 成功。見 [步驟 4 證據](docs/step-4-evidence.md)。

- 2026-09-08：完成步驟 3 PostgreSQL 持久化與 migration；專用帳號連線、實際 schema 套用及 120 項測試通過。見 [步驟 3 證據](docs/step-3-evidence.md)。

- 2026-09-08：完成步驟 2 的離線 CSV 驗證、共用模型與精確估值核心。`validate` 可實際使用；見 [步驟 2 證據](docs/step-2-evidence.md)。
- 2026-09-08：完成步驟 1；Python 3.14.7、uv 0.12.10、直接依賴及 uv.lock 已固定，CLI 骨架可安裝，10 項測試通過。見 [步驟 1 證據](docs/step-1-evidence.md)。
- 2026-09-08：完成開發計畫步驟 0 的 PostgreSQL 設計同步；既有容器 17.10、網路及持久化掛載已唯讀確認，專用帳號登入與 app 連線尚未測。見 [執行證據](docs/step-0-evidence.md)。
- 2026-09-08：ticker 自動判斷及標的映射已實作：數字開頭為台股、英文字母開頭為美股；台股原始代碼依官方清單映射 `.TW`／`.TWO`。
- 2026-09-07：需求討論後建立 v0.1 規格與架構文件，同日完成第一輪來源與依賴實測，資料來源評估與架構文件更新至 v0.2。
- 已確認：CSV／CLI、Python、Docker Compose、免費來源優先、可接受約 15–20 分鐘延遲、分幣別小計。
- CLI 已提供 help／version、validate、db-check、migrate、instruments-refresh 、resolve 與 quote；monitor／report 尚未實作，會明確回報並退出 1。Dockerfile 與 compose.yaml 待步驟 7。
- 文件中的建議驗收門檻與技術選型均有標示；它們不代表已取得的測試成績。

### 第一輪實測已確認（2026-09-07，以一次性探針取樣）

- 依賴相容性通過：`python:3.14-slim`（Python 3.14.7、Debian 13）以純 wheel 安裝 yfinance 1.7.0、httpx 0.28.1、exchange_calendars 4.13.2、pytest 9.1.1，映像無 gcc 亦不需編譯。Python 3.14 選型不需降版。
- 台股價格正確：2330.TW、0050.TW 對 TWSE，6488.TWO 對 TPEx，同交易日同口徑比對三筆全數相同。樣本數過小，不構成驗收計畫要求的價格吻合率。
- yfinance 提供最新成交價與秒級來源時間，故本輪不需要分鐘 K 線退路；台股宣告延遲 20 分鐘、美股宣告 0。
- Finnhub 已以環境注入金鑰通過 AAPL、VOO 與 `BRK.B` 真實抓價；回應 rate-limit header 顯示當次窗口 limit 60、remaining 59。

### 已知阻礙與未完成項

- PostgreSQL 使用既有 `postgres` 容器；App Compose 將加入 `infrastructure_default` external network，以 `postgres:5432` 連線。目標 database／schema／帳號為 `stock_quote_fetcher`／`app`／`stock_quote_app`，步驟 3 已驗證權限與登入並套用初始 migration；密碼由執行環境注入，不寫入文件。
- 公司網路以 TLS 檢查代理重簽 `finnhub.io`、TWSE 與 TPEx 的憑證（Yahoo 放行）。容器需注入公司根憑證**並**關閉 Python 3.13+ 預設的 `VERIFY_X509_STRICT` 才能連線；設計見架構文件第 6 節。
- 步驟 4 已從 Windows Root store 匯出不含私鑰的公司公開 CA 至本機已忽略的 secrets 目錄並完成來源實測；Dockerfile／Compose 的正式掛載與 OS trust 安裝仍屬步驟 7。
- Finnhub 免費金鑰已驗證可取得美股個股、ETF 與股別代碼；盤中時效及長時間額度行為仍待持續觀測。
- 尚無連續觀測結果，因此沒有可靠性、限流或時效達標的驗收數據。2026-09-07 為美國勞動節休市，美股盤中觀測最早自 2026-09-08 起算。
- 端到端時效門檻、驗收百分比門檻與美股估值來源仍待討論確認。

## 文件導覽

| 文件 | 內容 |
|---|---|
| [系統規格](docs/system-spec.md) | 範圍、CSV、CLI、報價品質、分幣別市值 |
| [架構與部署](docs/architecture.md) | 模組、資料模型、Python 版本策略、Docker Compose 設計、TLS 與 CA |
| [資料來源評估](docs/data-sources.md) | 候選來源、限制、時效、第一輪實測結果與 TLS 環境限制 |
| [POC 驗收計畫](docs/poc-validation.md) | 測試案例、可靠性指標、建議門檻、正式專案移交條件 |
| [開發執行計畫](docs/development-plan.md) | 分階段開發步驟、PostgreSQL 設計同步、交付物與 V01–V10 測試對照 |

## 執行順序

1. 依 [開發計畫](docs/development-plan.md) 推進；步驟 0–5 已完成，下一步實作 monitor 排程、停止與恢復。
2. 依規格實作 POC，交付版本鎖定、Dockerfile、compose.yaml、範例設定與操作說明。
3. 在目標 Docker 環境完成功能測試與台美股交易時段觀測。
4. 以實測結果決定來源是否符合需求，更新文件並共同確認 POC。
5. 將規格、架構、選型結論與驗收證據移交正式開發專案。

本次不包含多帳戶、現金、手續費、損益、外匯換算、券商持股同步或交易下單。

持久化使用既有 PostgreSQL，CSV／JSON／Markdown 為輸入及匯出格式。App 不建立或接管資料庫容器，不掛載資料庫 volume。一次性 quote 或 migration 前停止同 database／schema 的 monitor；report 使用唯讀交易。停止 app 使用其專案的 Compose，不操作基礎設施 Compose。資料庫 migration／儲存 API 已實作；monitor／report CLI 與 Compose 操作待後續步驟。

## 開發環境與離線驗證

使用 Python 3.14.7 與 uv 0.12.10，在專案根目錄執行：

```text
uv sync --frozen
uv run --frozen stock-poc --help
uv run --frozen stock-poc --version
uv run --frozen stock-poc validate --input examples/holdings.csv
uv run --frozen pytest -q
```

uv 版本由 pyproject.toml 強制核對，Python 修補版由 .python-version 選定；uv.lock 保存傳遞依賴與下載雜湊。更新依賴時才重新產生鎖定檔，日常使用 frozen 安裝。此輪已驗證 Linux amd64；Windows 原生環境尚未測試。本機無 Python／uv 時可用 [固定 Docker 映像驗證命令](docs/step-1-evidence.md)。

匿名範例位於 examples/holdings.csv。config.example.toml 的 database 區段供 db-check／migrate 使用，providers、scheduler 限制與 TLS 已供 quote 使用，monitor 排程仍待步驟 6，可複製為已忽略的 config.toml；一般設定與秘密值分離，DB_PASSWORD／FINNHUB_API_KEY 僅示於 .env.example 空欄。db-check／migrate 讀取 database 設定；CLI 不自動載入 .env，可由 Docker --env-file 注入。實際持股、憑證與秘密值不得放入範例檔。

`validate` 不需資料庫、設定檔或 API Key，只驗證 CSV 格式及股數規則，不確認股票是否存在。成功列出持股筆數並退出 0；任一列錯誤整份拒絕，stderr 顯示行號並退出 2。估值核心已串入 quote；固定估值案例與斷網驗證方式見步驟 2 證據。


## 單次報價

`quote` 會先驗證 CSV，再使用未過期的官方標的清單抓價、保存 PostgreSQL 紀錄及匯出。設定中的比較來源獨立保存，不會取代 Yahoo 估值來源。

```text
uv run --frozen stock-poc quote --input examples/holdings.csv --config config.toml --output output
```

DB_PASSWORD／FINNHUB_API_KEY 必須由執行環境注入；CLI 不自動讀取 .env。Docker 可使用 --env-file .env。本機 config.toml 已啟用 Finnhub／TWSE／TPEx 比較；未填金鑰時 Finnhub 明確失敗，Yahoo 仍可完成。執行環境須可讀取設定中的公司 CA 路徑。

每個 run 輸出 summary.json，及按 cycle 分隔的 holdings.csv。缺價／降級或已啟用來源最終失敗退出 3；純粹價格比對時間不一致保留證據，不宣稱已驗證吻合。詳見 [步驟 5 操作與限制](docs/step-5-evidence.md)。
