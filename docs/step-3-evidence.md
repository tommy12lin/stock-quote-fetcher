# 步驟 3 執行紀錄

日期：2026-09-08。狀態：PostgreSQL 持久化、migration 與隔離整合測試完成。報價 Provider／monitor／report CLI 仍待後續步驟。

## 交付

| 檔案 | 內容 |
|---|---|
| src/stock_quote_fetcher/config.py | TOML database 區段、DB_* 覆寫、秘密僅由 DB_PASSWORD 注入、有限逾時與專用 schema 驗證 |
| src/stock_quote_fetcher/migrations/0001_initial.sql | 9 個資料表、NUMERIC domains、關聯／唯一性／完整性 CHECK 與索引；另由 runner 建立 schema_migrations |
| src/stock_quote_fetcher/storage.py | migration checksum、專用帳號檢查、session advisory lock、短交易、持股／報價／估值、恢復及唯讀快照查詢 |
| src/stock_quote_fetcher/cli.py | db-check、migrate；設定錯誤退出 2、資料庫錯誤退出 1 |
| tests/test_storage.py | 明確 opt-in 的臨時 PostgreSQL 整合測試及離線設定測試 |

## 實際專案資料庫

- 使用者將密碼放入本機已忽略的 .env；Docker --env-file 注入測試程序，工具未列印秘密值。CLI 本身仍不自動載入 .env。
- Python app container 經 infrastructure_default，以 stock_quote_app 登入 postgres:5432／stock_quote_fetcher／app。
- PostgreSQL 17.10；CONNECT／USAGE／CREATE 權限符合，rolsuper／rolcreatedb／rolcreaterole 均為 false。
- 初次 migrate：套用 1 個版本；第二次：套用 0 個版本；db-check 完整 schema／checksum／SELECT／INSERT／UPDATE 檢查通過。
- 既有 postgres 容器沒有停止、重建或修改 volume；沒有在實際專案資料庫執行故障注入。正式 schema 只套用 DDL 與 migration 版本紀錄，未放入測試持股／報價。

## 測試

Python 3.14.7、uv 0.12.10、psycopg 3.3.5；依賴鎖定檔不變。完整執行結果：**120 passed in 8.59s**，見 step-3-validation.txt。sdist 與 wheel 建置成功，乾淨 venv 安裝確認 wheel 包含 0001_initial.sql。

故障測試使用固定名稱 `stock-poc-test-db` 的臨時 PostgreSQL、internal Docker network 與 tmpfs；不發布主機 port。測試 fixture 的管理連線固定此臨時 hostname，每個案例建立隨機 schema／非管理角色，測試後清除。既有資料庫的密碼與 DSN 不用於 fixture。

| 已驗證範圍 | 結果 |
|---|---|
| migration | 重複執行不重建；checksum 改動、未知／缺少版本拒絕；DDL 失敗連同版本紀錄回滾 |
| NUMERIC 與時間 | 超過 28 位精度的價格、數量與估值往返一致；外部 Decimal precision=4 不影響結果；UTC 時間保留 |
| 非法價格 | NaN／正負 Infinity／零／負值記為 invalid_payload 證據，不存入正常 quotes 或估值；資料庫 domain 亦拒絕 NaN |
| 交易 | quote 插入後 attempt 更新失敗，整組回滾；valuation 插入後 totals 失敗，整輪回滾且 cycle 不標成功 |
| 互斥 | 第二 session 被拒絕；session 關閉或連線終止後鎖釋放；未持鎖不能寫入 |
| 權限與逾時 | 管理帳號拒絕；缺表權限可辨識；寫入權限錯誤／statement timeout 停止 session，錯誤去敏 |
| 恢復 | 舊 running run／cycle、started attempt 標 interrupted 與 recovered_at，不虛構 completed_at；新 run 使用新 UUID |
| 追溯與唯一性 | 跨 run 的 holding／cycle 關聯、重複 attempt 被拒絕；campaign 輸入／設定變更不得沿用 |
| 快取 | 保留原 quote-id、來源與時間，使用端 valuation 加 cached／stale，原 quote 不覆寫 |
| 報告 | REPEATABLE READ READ ONLY 拒絕寫入；writer 提交後既有快照不變；campaign 保留跨 run、跳過、已到期缺輪及未來輪次 |
| 秘密 | 設定拒絕 password 欄位、repr 隱藏 password；不保存 FetchResult 原始錯誤字串或含 token URL |

連線中斷以 pg_terminate_backend 作用於臨時資料庫中的測試 session；未另外模擬「server 已 commit，但 client 收不到回應」的網路故障。程式對 DB 錯誤採結果可能未知、停止本次 session 的策略，UUID 由呼叫端事先產生，供重啟後查核；不自動重試寫入。

## 操作

原生 Python／uv 環境先注入 DB_PASSWORD；host CLI 如走發布的 PostgreSQL port，另依實際環境設定 DB_HOST／DB_PORT。容器仍使用 postgres DNS。一般設定可複製 config.example.toml 成 config.toml。

```text
uv sync --frozen
uv run --frozen stock-poc db-check --config config.toml --connection-only
uv run --frozen stock-poc migrate --config config.toml
uv run --frozen stock-poc db-check --config config.toml
uv run --frozen pytest -q
```

db-check --connection-only 檢查連線與 migration 的 schema 權限，容許尚未 migration；預設 db-check 另核對版本、checksum 及所有資料表的讀寫權限。migrate 與未來收集程序共用鎖；執行前停止 monitor。report_snapshot 不取收集鎖。

Windows／Docker 重跑整合測試（專案根目錄，固定名稱不得已被其他容器占用）：

```powershell
docker network create --internal stock-poc-test
docker run -d --name stock-poc-test-db --network stock-poc-test --tmpfs /var/lib/postgresql/data -e POSTGRES_PASSWORD=stock-poc-isolated-test-only postgres:17-alpine
# 待 pg_isready 回傳 accepting connections 後再執行測試。
docker exec stock-poc-test-db pg_isready -U postgres
docker run -d --name stock-poc-test-runner --network stock-poc-test --mount "type=bind,source=$((Get-Location).Path),target=/workspace,readonly" -w /workspace -e UV_PROJECT_ENVIRONMENT=/tmp/stock-poc-venv -e UV_CACHE_DIR=/tmp/uv-cache -e PYTHONDONTWRITEBYTECODE=1 python:3.14.7-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 sleep infinity
docker exec stock-poc-test-runner sh -ec 'python -m pip install uv==0.12.10; uv sync --frozen'
docker exec -e STOCK_POC_TEST_POSTGRES=disposable-local stock-poc-test-runner sh -ec 'uv run --frozen pytest -q -p no:cacheprovider'
# 僅移除上方建立的臨時測試資源。
docker rm -f stock-poc-test-runner stock-poc-test-db
docker network rm stock-poc-test
```

上述公開密碼只供隔離、用完即棄的測試資料庫。未設定 `STOCK_POC_TEST_POSTGRES=disposable-local` 時，資料庫整合案例會 skip，不能把一般離線 pytest 通過視為完成 DB 驗收。

## 後續界線

- 儲存 API 以持鎖 session 操作；start_run／create_campaign／recover_incomplete 核對 schema，不自動 migration。recover_incomplete 須在取鎖後、新 run 建立前呼叫。
- 每個 cycle 對應單一市場，finish_cycle 從 DB 持股與所選 quote UUID 重新估值，原子保存 rows／totals／完成狀態；來源選擇及快取是否仍可用由步驟 5 判斷。
- config.py 目前只負責 database 區段。公開設定快照採白名單；未來 scheduler／provider 啟動時須保存實際生效設定，不能把原始環境或秘密傳入快照。
- response_evidence 目前保存精簡正規化欄位並雜湊，原始錯誤訊息不持久化。Provider 解析器版本與可安全重現解析的原始欄位仍隨步驟 5 串接補足。
- read_run／read_campaign 是報告查詢基礎，尚未計算完整驗收指標或提供 report CLI；排程、SIGTERM 整合與容器部署分別在步驟 6–8。
- 下一步為步驟 4：標的清單來源確認與台美股來源代碼映射。
