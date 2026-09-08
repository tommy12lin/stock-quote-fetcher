# 步驟 7 執行紀錄

日期：2026-09-08。狀態：完成。Dockerfile、compose.yaml 與 .dockerignore 已交付，並在目標 Docker 環境完成設定解析、建置、單次指令、持續執行、停止／重啟、資料保留、收集程序互斥與資料庫故障驗證。連續盤中觀測與 report 仍分屬步驟 9 與步驟 8。

## 交付

| 檔案 | 內容 |
|---|---|
| Dockerfile | 固定 BASE_IMAGE digest；builder stage 以 pip 安裝固定 uv 後 `uv sync --frozen --no-dev --no-editable`；test stage 另含 dev group；runtime stage 只複製 venv，建立 uid／gid 10001 的 app 帳號並以 exec form ENTRYPOINT 執行 CLI |
| .dockerignore | 允許清單：僅 pyproject.toml、uv.lock、README.md 與 src 進入 build context；其餘（含 .env、config.toml、憑證、input／output、docs、tests、.git）全部排除 |
| compose.yaml | 單一 app service，預設 monitor；/input 唯讀、/output 可寫、公司 CA 唯讀單檔掛載；external network、restart、stop_grace_period、healthcheck、cap_drop、no-new-privileges 與 log rotation |
| input/holdings.example.csv | 供 `INPUT_DIR` 預設目錄存在的匿名範例；實際 holdings.csv 與 config.toml 由使用者放入同目錄，皆被 Git 忽略 |
| src/stock_quote_fetcher/config.py | 新增 `runtime_image_id()`：優先採執行環境注入的 `APP_IMAGE_ID`，否則退回映像內建的 `APP_BASE_IMAGE`，最後才是 `runtime-unspecified` |
| src/stock_quote_fetcher/monitor.py、quoting.py | start_run 改以 `runtime_image_id()` 記錄映像，取代步驟 6 的固定字串 |
| tests/test_storage.py | `runtime_image_id` 的優先順序、空白值與長度上限案例 |

不需要新的 migration：runs.image_id 已由 0001_initial.sql 建立，本步驟只改寫入值。

## 實測環境版本

| 元件 | 實測值 |
|---|---|
| Docker Engine | 29.6.1（client 與 server 同版，API 1.55，linux/amd64） |
| Docker Compose | v5.2.0 |
| buildx | v0.35.0-desktop.2 |
| 儲存驅動／核心 | overlayfs；6.18.33.2-microsoft-standard-WSL2（Docker Desktop，14 CPU） |
| 基礎映像 | `python:3.14.7-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6`；建置前重新核對，`python:3.14-slim` 當日仍解析為同一 digest，映像內為 Python 3.14.7、Debian 13.6 |
| 交付映像 | `stock-quote-fetcher:0.1.0`，Id `sha256:1d6a14e1c29c1414d3c719d1405f0675f543186278c4018d38c88d9e9636047e`；`docker images` 回報未壓縮 518 MB，其中 venv 層 255 MB、基礎映像其餘層約 143 MB |
| 既有 PostgreSQL | 執行檔 17.10；映像 `postgres:17-alpine@sha256:dc17045ccfd343b49600570ea734b9c4991cf1c3f3302e67df51e3b402dd55c4`；網路 infrastructure_default |

映像 Id 為本機建置產物的識別，非 registry digest；本 POC 不推送 registry，因此不宣稱跨機器可用同一 digest 取得。上表的 Id 是本次功能驗證所使用的建置；驗證後另以 `docker compose build --no-cache` 從乾淨 context 重建成功並通過 validate 與 db-check 抽測，Id 為 `sha256:9421d8d4f4a68736cb61eb07bf7bcaf7d4517e7a99fb00ab6fc78a4d2d7cc7e3`。兩次 Id 不同屬預期：可重現性由基礎映像 digest 與 uv.lock 保證，不是位元相同的映像。

## 建置與映像檢查

`docker compose build` 成功，鎖定安裝解析出與 uv.lock 一致的版本（psycopg 3.3.5、yfinance 1.7.0、httpx 0.28.1、exchange-calendars 4.13.2、tzdata 2026.3 等）。builder stage 內另驗證四個直接依賴可匯入、Asia/Taipei 與 America/New_York 時區可載入、`stock-poc --version` 回報 0.1.0。

以 `--network none` 檢查交付映像：

| 檢查 | 結果 |
|---|---|
| 執行身分 | `uid=10001(app) gid=10001(app)`；Config.User=`app:app` |
| ENTRYPOINT | `[/app/.venv/bin/stock-poc]`（exec form），CMD `[--help]` |
| build context 洩漏 | /app 下只有 .venv；pyproject.toml、uv.lock、README.md、src、docs、tests、examples、dist、.git、config.toml、.env、憑證目錄全部不存在 |
| 程式碼可寫性 | app 帳號寫入 /app/.venv 被拒（Permission denied），venv 由 root 擁有 |
| 建置工具殘留 | runtime stage 無 uv |
| 系統信任存放區 | /etc/ssl/certs/ca-certificates.crt 存在（ca-certificates 20250419） |

## 設定解析

`docker compose config --quiet` 通過。以 `--no-interpolate` 檢視時，`.env` 僅以 env_file 路徑呈現，DB_PASSWORD／FINNHUB_API_KEY 不會被展開進 config 輸出，可在不外洩秘密的前提下檢查契約。

## 公司 CA 掛載

以唯讀單檔掛載 `/run/secrets/company-root-ca.crt` 後於容器內檢查：檔案為 1 個 PEM 憑證區塊、1674 bytes，寫入被拒（Read-only file system）。DER SHA-1 為 `92715B2174E4131E2FF6B57295B7309B9AE87519`，與步驟 4 從 Windows Root store 認定的 `CN=ACLCA, DC=ADVANTECH, DC=CORP` 相同。載入後 SSLContext 的 CA 數量由 150 增為 151，`verify_mode` 維持 CERT_REQUIRED、`check_hostname` 維持 True，只有 VERIFY_X509_STRICT 被移除。

未在映像中執行 `update-ca-certificates`，也未把憑證烘進映像層。實作採架構第 6.2 節的每 provider SSLContext：公司 CA 只由 config.toml 明列的 `tls.relaxed_providers`／`relaxed_sources` 載入，其餘來源（含 Yahoo）使用完全預設的驗證，因此「目前放寬了什麼」可從設定稽核。架構第 6.1 節列出的 OS trust 安裝為替代方案，本次未採用。

## 一次性指令

| 案例 | 結果 |
|---|---|
| validate（`--network none`，無資料庫） | 匿名五檔退出 0；插入非法 ticker 後整份拒絕，stderr 標行號並退出 2 |
| db-check | `資料庫檢查成功：PostgreSQL 17.10；專用帳號權限符合。` 退出 0；容器經 infrastructure_default 以 `postgres` DNS 連線 |
| migrate | 既有專案 schema 已是最新，回報套用 0 個版本並退出 0，未變更資料 |
| quote | run-id 419b30d3-7859-48dc-9c2f-7b4b6a51aeae；TWD 精確總額 278480.00（degraded）、USD 1507.94（complete）；退出 3。TPEx 兩次嘗試分別為 timeout 與 network_error，如實記入 summary.json，未被隱藏 |
| 輸出落地 | 容器以 uid 10001 寫入主機 `output/step7/<run-id>/`：summary.json 與兩個 cycle 目錄的 holdings.csv |
| 映像記錄 | 注入 `APP_IMAGE_ID` 後 runs.image_id 為 `sha256:1d6a14e1…`；未注入時退回 `base:python:3.14.7-slim-trixie@sha256:cad9a2c…`。步驟 6 遺留的 `runtime-unspecified` 已不再產生 |

## 持續執行、停止與重啟

同一 campaign `7d3c6ec5-ffe8-47fd-ac11-c99801545dc0` 依序產生三個 run，全部保存於既有專案資料庫：

| 階段 | 觀測 |
|---|---|
| `docker compose up -d` | 容器 PID 1 為 `/app/.venv/bin/python /app/.venv/bin/stock-poc monitor …`，SIGTERM 直接送抵處理器，無 shell 或 init 中介 |
| healthcheck | 第一次探測即 healthy，`心跳年齡 3.3 秒`；當時台美股皆已收盤，等待期間仍更新心跳，休市未被誤判為故障 |
| 第二收集程序 | monitor 持鎖期間，quote、monitor、migrate、instruments-refresh 四種路徑全部回報「另一個收集程序或 migration 正在使用此 database／schema。」並退出 1 |
| `docker compose stop` | 1 秒內完成（stop_grace_period 90 秒），退出碼 0、非 OOM／非強制中止；日誌為「安全停止，可續跑」。run 3631161a 標 interrupted 並寫入 ended_at |
| 停止後 healthcheck | 「monitor healthcheck 失敗：沒有進行中的 run。」退出 1 |
| 重新啟動 | 新 run 8477b583 掛回同一 campaign，summary 的 campaign_created 為 false |
| 意外停止（SIGKILL） | 容器退出碼 137，run 8477b583 仍為 running 且 ended_at 為空；強制 1 秒門檻的 healthcheck 回報「心跳已逾期。」退出 1 |
| 恢復 | 再次啟動後新 run 449e2d48 建立前，8477b583 被標 interrupted 並記 recovered_at；summary 的 recovered 為 `{runs: 1, cycles: 0, fetch_attempts: 0}` |
| `docker compose down` | 容器停止並移除，run 449e2d48 走安全停止路徑；external network infrastructure_default 與既有 postgres 容器（healthy）均未受影響，未觸碰任何資料庫 volume |
| 資料保留 | down 之後仍可查得四個 run（含三個同 campaign）與各自 cycle，資料未隨容器移除而消失 |

restart policy 另以獨立 compose project（`-p step7-restart-probe`、指向暫存的破損 config，於任何資料庫存取前就退出）驗證：`unless-stopped` 在程序自行以退出碼 2 結束時持續重啟，RestartCount 達 5，錯誤訊息每次都出現在日誌中，未被靜默吞掉。

需要注意的實際行為：Docker 對手動 `docker stop`／`docker kill` 視為使用者要求停止，不套用 restart policy，因此上述 SIGKILL 案例並未自動重啟，是由再次 `docker compose up -d` 恢復。restart policy 只在程序自行結束時生效。healthcheck 失敗本身同樣不會觸發重啟。

## 隔離環境的資料庫故障測試

未對既有 PostgreSQL 注入任何故障。另建 `--internal` 網路 `stock-poc-test-net`、tmpfs 資料目錄、未發布主機 port 的 `postgres:17-alpine`（17.10）作為用完即棄目標，並以與正式相同的名稱（database `stock_quote_fetcher`、schema `app`、帳號 `stock_quote_app`）與最小權限建立；該帳號 rolsuper／rolcreatedb／rolcreaterole 均為 false。

| 案例 | 結果 |
|---|---|
| 完整測試 | 以交付映像同一鎖定依賴的 test stage、掛載 tests 與 pyproject.toml 執行 **172 passed in 7.41s**，見 [step-7-validation.txt](step-7-validation.txt) |
| 連線與權限 | db-check 退出 0，回報 PostgreSQL 17.10 與專用帳號權限符合 |
| 密碼錯誤 | 「資料庫連線失敗；請核對網路、帳號與環境設定。」退出 1，訊息不含 DSN 或密碼 |
| 未套用 migration | db-check 回報「Schema 版本或 migration checksum 不符」退出 1，不自動建表 |
| migrate | 於隔離 schema 套用 2 個版本並退出 0 |
| 缺標的清單 | quote 回報「沒有可用且未過期的標的清單」退出 1，未抓價 |
| 資料庫不可達（容器停止） | db-check、quote、healthcheck 三者均回報連線失敗並退出 1 |
| 執行中資料庫消失 | monitor 執行中停止資料庫，程序退出 1 並回報「資料庫操作失敗（SQLSTATE 57P01）；結果可能未知，請依原 UUID 查核。」與市場休市、來源故障區分清楚 |

隔離環境另完成一次真實標的清單更新：透過掛載的公司 CA 由五個官方來源取得 13,342 筆並建立 generation，同時證明容器內的 TLS 設定對受攔截來源（TWSE／TPEx）可用。tmpfs 資料目錄在容器 stop／start 後即清空，因此該環境每次重建都需重跑 bootstrap 與 migrate；正式資料不使用 tmpfs。驗證後容器與兩個測試網路均已移除，既有 postgres、redis、rabbitmq 與 infrastructure volume 未變動。

sdist 與 wheel 於同一 test stage 重新建置成功。

## 操作

輸入目錄需同時包含 holdings.csv 與 config.toml，兩者皆被 Git 忽略：

```powershell
mkdir input
copy examples\holdings.csv input\holdings.csv
copy config.example.toml input\config.toml   # 依需要修改 providers、scheduler 與 tls
```

秘密只從執行環境注入。專案根目錄的 `.env`（已忽略）提供 DB_PASSWORD 與 FINNHUB_API_KEY，由 compose 的 env_file 傳入容器；缺少時受影響的來源或連線明確失敗，不會降級為停用驗證。

```powershell
docker compose build
$env:APP_IMAGE_ID = docker image inspect stock-quote-fetcher:0.1.0 --format '{{.Id}}'

docker compose run --rm app validate --input /input/holdings.csv
docker compose run --rm app db-check --config /input/config.toml
docker compose run --rm app migrate --config /input/config.toml
docker compose run --rm app instruments-refresh --config /input/config.toml
docker compose run --rm app quote --input /input/holdings.csv --config /input/config.toml --output /output

docker compose up -d
docker compose ps
docker compose logs -f app
docker compose exec app stock-poc healthcheck --config /input/config.toml
docker compose stop app
docker compose up -d
docker compose down
```

`APP_IMAGE_ID` 只影響 runs.image_id 的記錄值；省略時退回映像內建的基礎映像參照。可覆寫的一般設定為 `INPUT_DIR`、`OUTPUT_DIR`、`COMPANY_CA_FILE`、`DB_NETWORK` 及 `DB_HOST`／`DB_PORT`／`DB_NAME`／`DB_SCHEMA`／`DB_USER`，預設值即架構第 5 節的契約。

一次性 quote、migrate 或 instruments-refresh 前必須先停止同 database／schema 的 monitor，否則會因收集鎖被拒絕。停止 app 一律使用本專案的 Compose，不操作基礎設施 Compose。

在 Git Bash 執行時要設 `MSYS_NO_PATHCONV=1`，否則 `/input/config.toml` 這類容器路徑會被改寫成 Windows 路徑，症狀是誤報「無法讀取設定檔或 TOML 格式錯誤」。PowerShell 無此問題。

隔離資料庫故障測試重跑（專案根目錄）：

```powershell
docker build --target test -t stock-quote-fetcher:0.1.0-test .
docker network create --internal stock-poc-test-net
docker run -d --name stock-poc-test-db --network stock-poc-test-net -e POSTGRES_PASSWORD=stock-poc-isolated-test-only --tmpfs /var/lib/postgresql/data:rw,size=512m postgres:17-alpine
docker exec stock-poc-test-db pg_isready -U postgres
docker run --rm --network stock-poc-test-net -e STOCK_POC_TEST_POSTGRES=disposable-local --mount "type=bind,source=$((Get-Location).Path)\tests,target=/work/tests,readonly" --mount "type=bind,source=$((Get-Location).Path)\pyproject.toml,target=/work/pyproject.toml,readonly" stock-quote-fetcher:0.1.0-test -q
docker rm -f stock-poc-test-db
docker network rm stock-poc-test-net
```

test stage 與交付映像共用同一份 uv.lock，只多裝 dev group 的 pytest；測試檔以唯讀掛載提供，不進入任何 build context。上述公開密碼只供用完即棄的測試資料庫。需要真實標的清單或 provider 的隔離案例才需要有 egress 的網路，該網路同樣不發布主機 port，也不連上 infrastructure_default。

## 未完成與界線

- `report` 仍未實作（步驟 8）。架構第 5 節「預定操作」清單中的 `docker compose run --rm app report …` 目前會明確回報未實作並退出 1，本次未列為通過案例。
- 本次的 monitor 實跑都在台美股收盤後，只驗證排程等待、心跳、停止、恢復與互斥；沒有任何盤中輪次實際抓價。連續三個交易日觀測、額度行為與可靠性指標屬步驟 9，本步驟不產生任何達標結論。
- campaign 7d3c6ec5 仍為 running 且 planned_end 在七日後。步驟 9 若沿用相同 CSV 與公開設定會自動續接該 campaign；需要乾淨起點時應改動輸入或設定以建立新 campaign，並在觀測前固定門檻版本。
- 未啟用 `read_only: true` 根檔案系統。yfinance／curl_cffi 會在使用者家目錄寫入自己的快取，改為唯讀需另配置可寫的 tmpfs 掛載與其權限，本次以非 root 執行、cap_drop ALL、no-new-privileges 與 root 擁有的唯讀 venv 作為容器強化範圍。
- 映像未推送任何 registry，也未產生 SBOM 或映像簽章；`APP_IMAGE_ID` 記錄的是本機映像 Id。跨機器重現只以基礎映像 digest 與 uv.lock 保證，不宣稱位元相同。
- 只驗證 linux/amd64。Windows 容器與其他架構未測試。
- 日誌採 json-file 並限制 10 MB × 5；長時間觀測的實際輪替量在步驟 9 才會確認。

## 查核來源

- [Compose file reference](https://docs.docker.com/reference/compose-file/)：現行 Compose Specification 不含頂層 version 欄位；services、networks 與 env_file 語法。
- [Compose services reference](https://docs.docker.com/reference/compose-file/services/)：restart、stop_grace_period、healthcheck、cap_drop、security_opt 與 external network 用法。
- [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/)：手動停止的容器不套用 restart policy；healthcheck 失敗不觸發重啟。
- [uv sync](https://docs.astral.sh/uv/reference/cli/#uv-sync)：`--frozen`、`--no-dev` 與 `--no-editable` 行為。
- [Dockerfile reference](https://docs.docker.com/reference/dockerfile/)：ENTRYPOINT exec form 使容器指令成為 PID 1。
- [.dockerignore](https://docs.docker.com/build/concepts/context/#dockerignore-files)：排除與 `!` 例外的比對順序。
