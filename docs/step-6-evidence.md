# 步驟 6 執行紀錄

日期：2026-09-08。狀態：完成。monitor 排程、停止／恢復、心跳與 healthcheck 已實作並以隔離環境驗證；真實環境的連續觀測屬步驟 9，容器部署驗證屬步驟 7。

## 交付與測試

| 檔案 | 內容 |
|---|---|
| src/stock_quote_fetcher/monitor.py | 日曆排程展開、campaign 建立／續接、輪次迴圈、遲到跳過、心跳等待、SIGTERM／SIGINT 處理與輸出 |
| src/stock_quote_fetcher/storage.py | find_matching_campaign、get_campaign、scheduled_cycles、provider_cooldowns、interrupt_run、finish_campaign、check_monitor_health |
| src/stock_quote_fetcher/quoting.py | 由 run 拆出 run_cycle（單市場、可指定 scheduled_at 與 scheduled_cycle_id）；加入 stop_requested、CollectionInterrupted、restore_cooldowns 與 effective_cooldown_seconds 證據 |
| src/stock_quote_fetcher/config.py | scheduler 新增 campaign_duration_days、post_close_observation_minutes、heartbeat_interval_seconds 及範圍驗證；納入公開設定快照白名單 |
| src/stock_quote_fetcher/cli.py | monitor（含 --campaign-id）與 healthcheck（--max-heartbeat-age-seconds） |
| tests/test_monitor.py、tests/test_cli.py | 排程、設定、訊號、停止／續跑、恢復與 healthcheck 案例 |

不需要新的 migration：campaigns、scheduled_cycles 與 cycles.scheduled_cycle_id 已由步驟 3 的 0001_initial.sql 建立，本步驟只新增查詢與狀態轉換。

完整 Linux amd64／Python 3.14.7／uv 0.12.10／隔離 PostgreSQL 17-alpine 測試 **171 passed in 15.34s**，見 [step-6-validation.txt](step-6-validation.txt)。sdist 與 wheel 建置成功，wheel 含 stock_quote_fetcher/monitor.py。隔離資料庫使用 internal network 與 tmpfs、未發布主機 port，未對既有 PostgreSQL 注入故障。

| 已驗證範圍 | 結果 |
|---|---|
| 市場獨立與休市 | 2026-09-07 台股照排、美股無任何輪次 |
| DST 與提早收盤 | 美股首輪 2026-03-06 為 14:00Z、03-09 為 13:00Z；11-27 regular 輪次止於 19:00Z 前 |
| 開盤延遲窗口 | 台股 60 秒間隔下開盤後 20 筆標 opening_delay |
| 設定驗證 | 三個 scheduler 欄位可載入；0、超界與 bool 一律拒絕 |
| 訊號 | SIGTERM 設定停止旗標，離開 context 後還原原本 handler |
| 停止與續跑 | 首次 run 完成兩輪、跳過一輪後安全停止；續跑產生新 run-id、沿用同一 campaign、只取未認領輪次 |
| 遲到跳過 | 注入兩小時停滯後，落後 ≥ 一個 poll_interval 的輪次記 skipped／scheduler_lag，不補抓 |
| 認領唯一性 | 四個 cycle 對應四個相異 scheduled_cycle_id，無重複認領 |
| 意外停止恢復 | 遺留的 running run／cycle 被標 interrupted 並記 recovered_at；新 run 使用新 UUID |
| 心跳與健康檢查 | 心跳逾期與「沒有進行中的 run」分別回報；設定錯誤退出 2 且不輸出成功訊息 |
| campaign 邊界 | 不存在、非 UUID 與已結束的 --campaign-id 均退出 2，不建立 run |

## 實作規則

- 排程於 campaign 建立時一次展開並寫入 scheduled_cycles，之後不重算。台美各自依 exchange_calendars 的交易日與時段產生機會；休市日不產生輪次，因此停機統計不會把休市誤記為缺口。
- 收盤後延長觀測：來源延遲已知時取「宣告延遲（台股 1200 秒、美股 0）＋兩個 poll_interval」；啟用發布時間未確認的來源（台股的 TWSE／TPEx、美股的 Finnhub）時改用 post_close_observation_minutes 上限，不假設其發布時間。
- 台股開盤後 20 分鐘的輪次標 opening_delay，與 regular、post_close 分開保存，供步驟 8 依窗口計算指標。
- campaign 以 input_hash 與 config_hash 辨識：同輸入同公開設定且仍在期間內會自動續接，CSV 或設定變動則開新 campaign。找到多個相符時拒絕執行並要求 --campaign-id，不自行挑選。
- 輪次不重疊：待辦機會以 LEFT JOIN cycles 排除已認領者，每個 cycle 綁定唯一 scheduled_cycle_id（資料庫 UNIQUE 約束）。重啟只取當下時間之後的機會，過去的缺口留在 scheduled_cycles 供報告重建，不事後補抓。
- 實際起跑落後排定時間達一個 poll_interval 以上時，該輪記 skipped／scheduler_lag，理由碼與正常輪次同樣入庫。
- 來源冷卻跨重啟沿用：以各來源最後一筆 rate_limited 嘗試的 effective_cooldown_seconds 與 completed_at 重算剩餘秒數，載入新 runner。冷卻仍為來源獨立。
- SIGTERM／SIGINT 只設定旗標。run_cycle 在每個標的抓取前後檢查，必要時丟出 CollectionInterrupted，該 cycle 標 interrupted、run 標 interrupted，campaign 維持 running 以便續跑；等待中收到停止則不啟動新 cycle。處理器在離開 context 時還原。
- 意外停止的辨識在取得專案收集鎖之後、建立新 run 之前執行，把遺留的 running／started 紀錄標 interrupted 並記 recovered_at，數量回報在 summary 的 recovered 欄位。
- 等待期間每 heartbeat_interval_seconds 更新 runs.heartbeat_at。healthcheck 區分「沒有進行中的 run」與「心跳已逾期」，資料庫連線或權限失敗則以既有 StorageError 訊息退出 1；三者不共用同一個結論。
- 輸出沿用步驟 5 格式：output/<run-id>/summary.json 以暫存檔原子替換，每輪另存 <cycle-id>/holdings.csv；summary 保存 campaign、輪次、嘗試與比對紀錄。

## 操作

```text
uv run --frozen stock-poc monitor --input examples/holdings.csv --config config.toml --output output
uv run --frozen stock-poc monitor --input examples/holdings.csv --config config.toml --output output --campaign-id <uuid>
uv run --frozen stock-poc healthcheck --config config.toml --max-heartbeat-age-seconds 120
```

monitor 取得專案收集鎖，與 quote、migrate 互斥。省略 --campaign-id 時自動續接相同輸入與設定的進行中 campaign；沒有相符者才建立新的。停止用 SIGTERM（容器 `docker stop`）或 Ctrl+C，退出碼 0 並在訊息中回報可續跑。

隔離環境重跑（專案根目錄）：

```powershell
docker network create --internal stock-poc-test
docker run -d --name stock-poc-test-db --network stock-poc-test --tmpfs /var/lib/postgresql/data -e POSTGRES_PASSWORD=stock-poc-isolated-test-only postgres:17-alpine
docker exec stock-poc-test-db pg_isready -U postgres
docker run -d --name stock-poc-test-runner --network stock-poc-test --mount "type=bind,source=$((Get-Location).Path),target=/workspace,readonly" -w /workspace -e UV_PROJECT_ENVIRONMENT=/tmp/stock-poc-venv -e UV_CACHE_DIR=/tmp/uv-cache -e PYTHONDONTWRITEBYTECODE=1 python:3.14.7-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 sleep infinity
docker network connect bridge stock-poc-test-runner
docker exec stock-poc-test-runner sh -ec 'python -m pip install uv==0.12.10; uv sync --frozen'
docker network disconnect bridge stock-poc-test-runner
docker exec -e STOCK_POC_TEST_POSTGRES=disposable-local stock-poc-test-runner sh -ec 'uv run --frozen pytest -q -p no:cacheprovider'
docker rm -f stock-poc-test-runner stock-poc-test-db
docker network rm stock-poc-test
```

安裝依賴時才接上 bridge，測試本身在 internal network 執行。上述公開密碼只供用完即棄的測試資料庫。

## 未完成與界線

- 本步驟的排程、停止與恢復全部以固定時鐘、注入的 fetch 與隔離資料庫驗證；尚未對既有專案資料庫或真實 provider 執行 monitor。實際盤中連續觀測、額度行為與可靠性指標屬步驟 9。
- 針對既有專案資料庫的唯讀 healthcheck 尚未實跑：該操作需要 .env 注入密碼，未納入本次證據。使用者可依上方操作段自行執行後補記。
- 容器網路路徑、`docker stop` 的實際 SIGTERM 傳遞、重啟後資料保留與第二收集程序被拒絕，均在步驟 7 的目標環境驗證。
- start_run 目前以 image_id `runtime-unspecified` 記錄；步驟 7 完成映像後改為實際 digest。
- campaign 的 maintenance_windows 目前一律為空陣列，尚未提供人工維護窗口設定。
- THRESHOLD_VERSION 記為 `unconfirmed-v1`，代表驗收門檻仍待確認；步驟 9 固定門檻後再更新。
- 交易日曆以 exchange_calendars 4.13.2 為準，臨時停市與台股全年公告仍須在步驟 9 正式觀測前另行核對。

## 查核來源

- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars)：sessions_in_range、session_open_close 與提早收盤處理。
- [NYSE 日曆](https://www.nyse.com/markets/hours-calendars)、[Nasdaq 日曆](https://nasdaqtrader.com/Trader.aspx?id=Calendar)：2026-09-07 休市、11-27 提早收盤。
- [TWSE 開休市表](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html)：台股交易日參考。
- [Python signal](https://docs.python.org/3/library/signal.html)：處理器只在主執行緒的位元碼邊界執行，因此停止採合作式旗標。
