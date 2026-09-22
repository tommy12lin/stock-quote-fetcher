# 台美股報價與持股市值 POC

本機網頁第一版已新增：上傳 Excel、保存持股、查看市值／成本／損益與配置圖。啟動命令與驗證見 [持股儀表板第一版](docs/dashboard-v1.md)；網頁使用獨立 Compose 與 schema，既有 CLI／monitor 維持原流程。**自 `C2-1`／`C2-6` 起，Python 端改為 ASGI（FastAPI＋uvicorn）且只提供 `/api/`，不再供應 `/`、`/app.js`、`/style.css`**，靜態檔改由 Cloudflare 供應；`http://localhost:8765/` 因此不再能直接開啟頁面，本機開啟方式見 [C2 執行紀錄](docs/cloud-C2-evidence.md)。

以 Python 與 Docker Container 驗證台美股盤中報價的可取得性、資料時效與持續運行可靠性。使用 CSV 輸入持股，透過指令操作，分別呈現 TWD 與 USD 市值小計。

## 目前狀態

- 2026-09-08：步驟 9 觀測啟動。代表標的固定為 11 檔（2330、2317、0050、6488、3529、006201、AAPL、MSFT、BRK.B、VOO、QQQ），全部經官方清單 `resolve` 通過；估值固定 Yahoo，比較來源 finnhub／twse／tpex，沿用驗收建議門檻。觀測前以 migration 0003 將官方商品類型寫入 quotes，`report` 因此可依官方級距判定台股最小報價單位；203 項測試通過。campaign `f0a98b5a` 自 2026-09-08T12:13Z 起連續執行，預定 3,600 個機會。盤中觀測結果與 V01–V10 彙整待補，見 [步驟 9 證據](docs/step-9-evidence.md)。

- 2026-09-08：完成步驟 8 `report` 與證據輸出；run 與 campaign 兩種範圍、依預定輪次重建的分母、來源／市場／標的指標、停機重建、價格比對、小計人工核對與結論分類已實作，輸出 JSON／Markdown，185 項測試通過，不需新 migration。已對既有專案資料庫的真實 run 與 campaign 實跑，並在 monitor 持鎖時確認 report 不需收集鎖。見 [步驟 8 證據](docs/step-8-evidence.md)。盤中連續觀測與交叉比對屬步驟 9。

- 2026-09-08：完成步驟 7 容器部署與整合驗證；Dockerfile、compose.yaml 與 .dockerignore 已交付，並在 Docker Engine 29.6.1／Compose v5.2.0／既有 PostgreSQL 17.10 完成連線、單次指令、持續執行、停止／重啟、資料保留與收集程序互斥驗證，172 項測試及資料庫故障案例於隔離環境通過。見 [步驟 7 證據](docs/step-7-evidence.md)。`report` 屬步驟 8，盤中連續觀測屬步驟 9。

- 2026-09-08：完成步驟 6 monitor 排程與停止／恢復；campaign 續接、遲到跳過、冷卻沿用、SIGTERM 安全停止、心跳與 healthcheck 已實作，171 項測試通過，不需新 migration。真實 provider 的連續觀測屬步驟 9。見 [步驟 6 證據](docs/step-6-evidence.md)。

- 2026-09-08：完成步驟 5 單次 quote、四個 Provider、品質檢查、重試／冷卻、快取與 CSV／JSON 輸出；Yahoo、Finnhub、TWSE 與 TPEx 均通過真實容器驗證。見 [步驟 5 證據](docs/step-5-evidence.md)。

- 2026-09-08：完成步驟 4 官方標的解析、映射、快取與 migration；141 項測試通過，容器正式保存 13,343 筆五來源 generation，匿名範例全數 resolve 成功。見 [步驟 4 證據](docs/step-4-evidence.md)。

- 2026-09-08：完成步驟 3 PostgreSQL 持久化與 migration；專用帳號連線、實際 schema 套用及 120 項測試通過。見 [步驟 3 證據](docs/step-3-evidence.md)。

- 2026-09-08：完成步驟 2 的離線 CSV 驗證、共用模型與精確估值核心。`validate` 可實際使用；見 [步驟 2 證據](docs/step-2-evidence.md)。
- 2026-09-08：完成步驟 1；Python 3.14.7、uv 0.12.10、直接依賴及 uv.lock 已固定，CLI 骨架可安裝，10 項測試通過。見 [步驟 1 證據](docs/step-1-evidence.md)。
- 2026-09-08：完成開發計畫步驟 0 的 PostgreSQL 設計同步；既有容器 17.10、網路及持久化掛載已唯讀確認，專用帳號登入與 app 連線尚未測。見 [執行證據](docs/step-0-evidence.md)。
- 2026-09-08：ticker 自動判斷及標的映射已實作：數字開頭為台股、英文字母開頭為美股；台股原始代碼依官方清單映射 `.TW`／`.TWO`。
- 2026-09-07：需求討論後建立 v0.1 規格與架構文件，同日完成第一輪來源與依賴實測，資料來源評估與架構文件更新至 v0.2。
- 已確認：CSV／CLI、Python、Docker Compose、免費來源優先、可接受約 15–20 分鐘延遲、分幣別小計。
- CLI 已提供 help／version、validate、db-check、migrate、instruments-refresh、resolve、quote、monitor、healthcheck 與 report。Dockerfile 與 compose.yaml 已交付並在目標環境驗證。
- 文件中的建議驗收門檻與技術選型均有標示；它們不代表已取得的測試成績。

### 第一輪實測已確認（2026-09-07，以一次性探針取樣）

- 依賴相容性通過：`python:3.14-slim`（Python 3.14.7、Debian 13）以純 wheel 安裝 yfinance 1.7.0、httpx 0.28.1、exchange_calendars 4.13.2、pytest 9.1.1，映像無 gcc 亦不需編譯。Python 3.14 選型不需降版。
- 台股價格正確：2330.TW、0050.TW 對 TWSE，6488.TWO 對 TPEx，同交易日同口徑比對三筆全數相同。樣本數過小，不構成驗收計畫要求的價格吻合率。
- yfinance 提供最新成交價與秒級來源時間，故本輪不需要分鐘 K 線退路；台股宣告延遲 20 分鐘、美股宣告 0。
- Finnhub 已以環境注入金鑰通過 AAPL、VOO 與 `BRK.B` 真實抓價；回應 rate-limit header 顯示當次窗口 limit 60、remaining 59。

### 已知阻礙與未完成項

- PostgreSQL 使用既有 `postgres` 容器；App Compose 已以 `infrastructure_default` external network 透過 `postgres:5432` 連線，並於步驟 7 實測通過。目標 database／schema／帳號為 `stock_quote_fetcher`／`app`／`stock_quote_app`，步驟 3 已驗證權限與登入並套用初始 migration；密碼由執行環境注入，不寫入文件。
- 公司網路以 TLS 檢查代理重簽 `finnhub.io`、TWSE 與 TPEx 的憑證（Yahoo 放行）。容器需注入公司根憑證**並**關閉 Python 3.13+ 預設的 `VERIFY_X509_STRICT` 才能連線；設計見架構文件第 6 節。
- 公司公開 CA（不含私鑰）存於本機已忽略的 secrets 目錄，由 Compose 以唯讀單檔掛載至 `/run/secrets/company-root-ca.crt`，容器內已核對 DER SHA-1 與步驟 4 一致。憑證不烘進映像層，也未執行 `update-ca-certificates`：公司 CA 只由 config.toml 明列的來源載入，其餘來源使用完全預設的驗證。
- Finnhub 免費金鑰已驗證可取得美股個股、ETF 與股別代碼；盤中時效及長時間額度行為仍待持續觀測。
- 連續觀測已於 2026-09-08 啟動，但尚未累積任何盤中輪次，因此仍沒有可靠性、限流或時效達標的驗收數據。美股自 2026-09-08 當晚（台北 21:30）起算，台股自 2026-09-09 起算，每市場需三個完整交易日。
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

1. 依 [開發計畫](docs/development-plan.md) 推進；步驟 0–8 已完成，步驟 9 的盤中觀測進行中，之後為步驟 10 的結論與移交。
2. 依規格實作 POC，交付版本鎖定、Dockerfile、compose.yaml、範例設定與操作說明。
3. 在目標 Docker 環境完成功能測試與台美股交易時段觀測。
4. 以實測結果決定來源是否符合需求，更新文件並共同確認 POC。
5. 將規格、架構、選型結論與驗收證據移交正式開發專案。

本次不包含多帳戶、現金、手續費、損益、外匯換算、券商持股同步或交易下單。

持久化使用既有 PostgreSQL，CSV／JSON／Markdown 為輸入及匯出格式。App 不建立或接管資料庫容器，不掛載資料庫 volume。一次性 quote 或 migration 前停止同 database／schema 的 monitor；report 使用唯讀交易。停止 app 使用其專案的 Compose，不操作基礎設施 Compose。資料庫 migration／儲存 API、monitor CLI、Compose 操作與 `report` 已實作並驗證；`report` 使用唯讀快照、不取收集鎖，可在 monitor 執行中產生。

## 開發環境與離線驗證

使用 Python 3.14.7 與 uv 0.12.10，在專案根目錄執行：

```text
uv sync --frozen
uv run --frozen stock-poc --help
uv run --frozen stock-poc --version
uv run --frozen stock-poc validate --input examples/holdings.csv
uv run --frozen pytest -q
```

uv 版本由 pyproject.toml 強制核對，Python 修補版由 .python-version 選定；uv.lock 保存傳遞依賴與下載雜湊。更新依賴時才重新產生鎖定檔，日常使用 frozen 安裝。Linux amd64 已驗證；Windows 原生環境亦已跑完整套件（297 passed、51 skipped，skip 為需要一次性 PostgreSQL 容器的整合測試），但有下述前提。本機無 Python／uv 時可用 [固定 Docker 映像驗證命令](docs/step-1-evidence.md)。

**Windows 原生環境執行測試需先設 `PYTHONUTF8=1`**，否則 `tests/test_cli.py` 會有 6 項失敗：

```text
$env:PYTHONUTF8 = "1"
uv run --frozen pytest -q
```

該檔以子程序執行 `stock-poc` 並以 UTF-8 解碼其輸出，而中文版 Windows 的子程序預設以 cp950 輸出。解碼失敗發生在 subprocess 的讀取執行緒裡，`stdout`／`stderr` 因此變成 `None`，**表徵是斷言的 `TypeError` 而不是編碼錯誤**，看起來與編碼無關。

改用 `.venv\Scripts\python.exe -m pytest` 直接執行時，還需要把 `.venv\Scripts` 加入 `PATH`：`run_cli` 呼叫的是裸的 `stock-poc`，`uv run` 會自動處理而直接呼叫 python 不會，缺少時表徵是 12 項 `FileNotFoundError`（WinError 2）。兩種入口的 `sys.path` 差異則由 pyproject.toml 的 `pythonpath` 消除，不需另行設定。

匿名範例位於 examples/holdings.csv。config.example.toml 的 database 區段供 db-check／migrate 使用，providers、scheduler 限制與 TLS 已供 quote 與 monitor 使用，可複製為已忽略的 config.toml；一般設定與秘密值分離，DB_PASSWORD／FINNHUB_API_KEY 僅示於 .env.example 空欄。db-check／migrate 讀取 database 設定；CLI 不自動載入 .env，可由 Docker --env-file 注入。實際持股、憑證與秘密值不得放入範例檔。

`validate` 不需資料庫、設定檔或 API Key，只驗證 CSV 格式及股數規則，不確認股票是否存在。成功列出持股筆數並退出 0；任一列錯誤整份拒絕，stderr 顯示行號並退出 2。估值核心已串入 quote；固定估值案例與斷網驗證方式見步驟 2 證據。


## 單次報價

`quote` 會先驗證 CSV，再使用未過期的官方標的清單抓價、保存 PostgreSQL 紀錄及匯出。設定中的比較來源獨立保存，不會取代 Yahoo 估值來源。

```text
uv run --frozen stock-poc quote --input examples/holdings.csv --config config.toml --output output
```

DB_PASSWORD／FINNHUB_API_KEY 必須由執行環境注入；CLI 不自動讀取 .env。Docker 可使用 --env-file .env。本機 config.toml 已啟用 Finnhub／TWSE／TPEx 比較；未填金鑰時 Finnhub 明確失敗，Yahoo 仍可完成。執行環境須可讀取設定中的公司 CA 路徑。

每個 run 輸出 summary.json，及按 cycle 分隔的 holdings.csv。缺價／降級或已啟用來源最終失敗退出 3；純粹價格比對時間不一致保留證據，不宣稱已驗證吻合。詳見 [步驟 5 操作與限制](docs/step-5-evidence.md)。

## 持續觀測

`monitor` 依交易日曆為台美股各自排定輪次，逐輪執行與 quote 相同的抓價、品質判斷與保存。休市不排輪次；排定時間展開後即固定，供報告重建停機缺口。

```text
uv run --frozen stock-poc monitor --input examples/holdings.csv --config config.toml --output output
uv run --frozen stock-poc healthcheck --config config.toml --max-heartbeat-age-seconds 120
```

省略 --campaign-id 時自動續接輸入與公開設定相同、且仍在期間內的 campaign；沒有相符者才建立新的。SIGTERM（容器 `docker stop`）或 Ctrl+C 為安全停止，退出 0 並提示可續跑；重新啟動使用新的 run-id 並掛回同一 campaign，只取尚未認領的輪次，不補抓過去的缺口。落後排定時間達一個輪詢間隔的輪次記為 skipped／scheduler_lag。healthcheck 分別回報心跳逾期與沒有進行中的 run。monitor 與 quote、migrate 共用收集鎖，不能同時執行。詳見 [步驟 6 操作與界線](docs/step-6-evidence.md)。

## 容器部署

交付 Dockerfile、compose.yaml 與 .dockerignore。映像固定基礎映像 digest、以 uv.lock frozen 安裝、非 root（uid 10001）執行，並以 exec form ENTRYPOINT 讓 CLI 成為 PID 1，`docker stop` 的 SIGTERM 因此直接送抵 monitor 的處理器。App Compose 只定義 app 與 external network，不定義 PostgreSQL service，也不掛載資料庫 volume。

輸入目錄需同時包含 holdings.csv 與 config.toml，兩者皆被 Git 忽略：

```powershell
mkdir input
copy examples\holdings.csv input\holdings.csv
copy config.example.toml input\config.toml
```

```powershell
docker compose build
$env:APP_IMAGE_ID = docker image inspect stock-quote-fetcher:0.1.0 --format '{{.Id}}'

docker compose run --rm app validate --input /input/holdings.csv
docker compose run --rm app db-check --config /input/config.toml
docker compose run --rm app migrate --config /input/config.toml
docker compose run --rm app instruments-refresh --config /input/config.toml
docker compose run --rm app quote --input /input/holdings.csv --config /input/config.toml --output /output

docker compose up -d
docker compose logs -f app
docker compose exec app stock-poc healthcheck --config /input/config.toml
docker compose stop app
docker compose down

docker compose run --rm app report --config /input/config.toml --run-id <run-id> --output /output
docker compose run --rm app report --config /input/config.toml --campaign-id <campaign-id> --output /output
```

秘密只從執行環境注入：專案根目錄的 `.env`（已忽略）提供 DB_PASSWORD 與 FINNHUB_API_KEY，由 compose 的 env_file 傳入容器。`APP_IMAGE_ID` 只影響 runs.image_id 的記錄值，省略時退回映像內建的基礎映像參照。可覆寫的一般設定為 `INPUT_DIR`、`OUTPUT_DIR`、`COMPANY_CA_FILE`、`DB_NETWORK` 與 `DB_HOST`／`DB_PORT`／`DB_NAME`／`DB_SCHEMA`／`DB_USER`。

一次性 quote、migrate 或 instruments-refresh 前先停止同 database／schema 的 monitor，否則會被收集鎖拒絕。停止 app 一律使用本專案的 Compose，不操作基礎設施 Compose。`docker compose down` 只移除 app 容器，資料留在既有 PostgreSQL。

`restart: unless-stopped` 只在程序自行結束時生效；手動 `docker stop`／`docker kill` 依 Docker 設計不會自動重啟，healthcheck 失敗本身也不會。意外停止後重新啟動會建立新 run-id、掛回原 campaign，並把遺留的未完成紀錄標為 interrupted。

在 Git Bash 執行時要設 `MSYS_NO_PATHCONV=1`，否則 `/input/config.toml` 這類容器路徑會被改寫成 Windows 路徑，症狀是誤報「無法讀取設定檔或 TOML 格式錯誤」。PowerShell 無此問題。

`report` 讀取持久化紀錄產生可靠性報告，不重新抓價也不取收集鎖，`--run-id` 與 `--campaign-id` 互斥且需指定其一；輸出寫入 `<output>/reports/<scope>-<id>/<產生時間>/report.json` 與 `report.md`，每次產生新目錄。報告含持股代碼與股數，移交前依驗收第 7 節處理。實測版本、映像檢查、隔離資料庫故障案例與界線見 [步驟 7 證據](docs/step-7-evidence.md) 與 [步驟 8 證據](docs/step-8-evidence.md)。
