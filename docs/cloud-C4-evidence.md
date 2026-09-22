# C4 執行紀錄：工作生命週期、單例假設與復原

日期：2026-09-22，同日補正一項缺陷（見「部分更新無法收斂」）。範圍：[第一階段計畫](cloud-phase-1-plan.md) 的 C4。此次修改本機工作樹並以隔離的拋棄式 PostgreSQL 驗證，沒有部署、沒有連線 Supabase、沒有讀取真實秘密。

## 進度

| 項目 | 狀態 |
|---|---|
| C4-1 請求內有時限完成 | 機制完成並驗證，含 09-22 的收斂補正；**deadline 與單次檔數兩個數值仍未量測** |
| C4-2 移除全程序 advisory lock | 完成，已實測兩個服務可在同一 schema 並存 |
| C4-3 資料庫層原子認領 | 完成，已實測第二實例不會重複認領 |
| C4-4 owner／lease／逾期回收 | 完成，已實測未到期的租約不被標成失敗 |
| C4-5 60 秒冷卻跨實例有效 | 完成，已實測第二實例同樣被冷卻擋下 |
| C4-6 中斷後保留既有報價 | 完成，已實測截斷後 quotes 與持股文件不變 |

## 實作契約

- **認領（C4-3）**：`Dashboard.claim()` 在單一交易內以 `pg_try_advisory_xact_lock(lock_key(schema + ':refresh'))` 取得認領權，並在同一交易內完成逾期回收、冷卻判斷與寫入新 job。交易範圍的鎖由 commit、rollback 與連線中斷一併釋放，沒有任何東西活過取得它的程序。取不到鎖回 429 `refresh_busy`，不阻塞。
- **租約（C4-4）**：job 文件內新增 `owner` 與 `lease_expires_at`。每次進度寫入即續約，進度寫入是這個 job 唯一的心跳。租約長度由設定導出：`cycle_budget_seconds + operation_timeout_seconds + 30`，即一批的預算加一次在途的來源呼叫再加緩衝；租約必須長過兩次進度寫入之間的安靜期，否則另一個實例會回收還在跑的工作。預設為 90 秒，必然大於 60 秒冷卻，因此回收一個崩潰的 job 之後不會立刻撞到它自己的冷卻。
- **回收時機**：改在 `claim()` 內回收，不在啟動時掃描。啟動時無從分辨「另一個存活實例正在做的事」與「被遺棄的事」，這正是原本 `recover_jobs()` 會誤判的原因。
- **沒有租約的舊 job 依定義視為逾期**：那是 C4-4 之前寫入的列，寫它的程序早已不存在。
- **讀取端（C4-4）**：`job()` 對租約已到期的 queued／running 一律呈現為 failed，即使尚未有人掃過。輪詢的人不會看著一個死掉的 job 一直停在 running。
- **不需要 DDL**：租約寫在既有的 `document` jsonb 內。C5-2 已撤除 runtime 的 CREATE 權限，任何新欄位或新表都得走管理者的 bootstrap，這裡刻意避開。
- **時限（C4-1）**：`refresh()` 在請求內跑完並回傳完成的 job。整體 deadline 為 `[scheduler] refresh_deadline_seconds`；每批預算取「剩餘時間」與 `cycle_budget_seconds` 的較小值，且 runner 逐批重建，使單一 cycle 不可能活過 deadline。單次檔數為 `refresh_max_tickers`，超出的檔數在完成訊息中明列。冷卻期間的來源退避由 storage 重建，逐批重讀不會遺失。
- **處理順序（C4-1，09-22 補正）**：切片之前先依「最後取得報價的時間」由舊到新排序，從未取得過報價者視為最舊。這是讓部分更新能夠收斂的關鍵；理由見下節。排序相同者維持存檔順序，結果是決定性的。
- **設定位置**：兩個鍵放在 `[scheduler]`，但**不**進入 `QuoteConfig`。它們限制的是 HTTP 請求而非一個報價 cycle，且加進 `QuoteConfig` 會改變 `configuration_snapshot` 的摘要，而 campaign 比對依賴該摘要。代價是這兩個值不會進入 run 的設定快照。
- **HTTP（C4-1）**：`POST /api/portfolio/refresh` 與 `/api/catalog/refresh` 改回 **200 附完成的 job**。只有一種情況仍回 202：另一個實例持有有效租約，回傳它那個未完成的 job 讓前端輪詢。
- **前端（C4-1）**：改為等待這個長請求並顯示「請保持分頁開啟」。被代理或邊緣截斷的長請求在 `fetch()` 眼中與 Access 轉址完全相同，因此這一個呼叫關掉整頁重載（`reloadOnRedirect=false`），改回報「未能在連線時限內完成」；真正的登入失效由下一個呼叫接手處理。若不這樣分開，一次更新逾時會被誤判成登入過期而重載整頁。
- **啟動（C4-2）**：不再取任何全程序鎖，也不再於啟動時掃描 job。原本拿不到鎖會以 `parser.error` 結束程序，Cloud Run 每次 rollout 都會有新舊 revision 並存，該行為會讓部署失敗。

## 驗證

隔離的拋棄式 PostgreSQL（`stock-poc-test-db`、internal network、tmpfs），依 `docs/step-3-evidence.md` 的既有程序建立；runner 另接橋接網路才能安裝依賴，資料庫本身仍只在內部網路上。

| 檢查 | 結果 |
|---|---|
| 完整 Python 套件（含資料庫整合） | **361 passed、0 skipped**（含 09-22 補正的三個案例） |
| `tests/test_dashboard_storage.py` | 19 passed |
| `node --test tests/web_session.test.cjs` | 8 passed |
| `node --check src/stock_quote_fetcher/static/app.js` | 通過 |

先前紀錄的 287 passed／46 skipped 是未開資料庫的結果。此次 46 項整合案例全部實際執行，不再是 skip。

新增的 C4 案例：

| 案例 | 驗證的性質 |
|---|---|
| `test_a_live_lease_is_never_declared_failed` | 未到期的租約不被回收（C4-4 的核心要求） |
| `test_an_expired_lease_is_reclaimed` | 到期才回收，並寫入 `completed_at` |
| `test_expired_lease_reads_as_failed_before_any_sweep` | 讀取端不顯示死掉的 running |
| `test_second_instance_does_not_duplicate_a_claimed_job` | 第二實例不會重複認領（C4-3） |
| `test_second_instance_claims_once_the_lease_has_run_out` | 租約到期後第二實例可接手，舊 job 標 failed |
| `test_lease_always_outlives_the_cooldown` | 回收後不會立刻撞到自己的冷卻 |
| `test_cooldown_holds_across_instances` | 60 秒冷卻跨實例有效（C4-5） |
| `test_refresh_stops_at_the_deadline_and_keeps_stored_quotes` | deadline 截斷且 quotes 與持股不變（C4-1／C4-6） |
| `test_tickers_beyond_the_cap_are_reported_not_dropped` | 超出上限的檔數被明列而非默默丟棄 |

時限相關的兩個案例以注入的時鐘驅動，不依賴真實經過時間，也因此不會真的呼叫行情來源。

前端新增兩案例：被截斷的長請求回報截斷而不重載整頁，且不留下登入草稿暫存。

### C4-2 的實測

同一 schema（`c4demo`）同時啟動兩個 `stock-web`：

```
Portfolio dashboard API: listening on 127.0.0.1:8801
Portfolio dashboard API: listening on 127.0.0.1:8802
8801 200 {"status": "ok"}
8802 200 {"status": "ok"}
```

兩者皆正常服務。改動前第二個程序會以 `同一 schema 已有儀表板服務。` 結束。同時查資料庫：

```
SELECT locktype, count(*) FROM pg_locks WHERE locktype='advisory';   -- 0 列
SELECT count(*) FROM pg_stat_activity WHERE usename='c4demo';        -- 0
```

沒有任何 advisory lock，也沒有常駐連線，確認啟動租約確實移除。此 schema 與角色為此次驗證另建，用畢清除。

## 2026-09-22 補正：部分更新無法收斂

### 缺陷

`run_job` 原本這樣挑要處理的標的：

```python
planned = holdings[:limit] if limit else holdings
for offset in range(0, len(planned), BATCH_SIZE):
```

每次都從持股清單的**第一筆**開始，順序是使用者存檔的順序，沒有游標也沒有依新鮮度排序。`QuoteRunner` 也不會跳過「已經很新」的標的，它每次都照抓。兩者相加的後果是：

- **deadline 截斷時**：再按一次更新，抓的還是同一批前面的標的。清單尾端永遠輪不到。
- **設了 `refresh_max_tickers` 時更嚴重**：那是硬切片，超過上限的標的**永遠不會被抓到**，不是「這次沒輪到」。

完成訊息卻寫著「請再次更新取得其餘報價」，這句話在當時是**錯的**——再次更新拿不到其餘報價。

### 為什麼當時沒被抓到

C4 的測試都只跑一次更新。「一次更新會不會漏」有測（`test_refresh_stops_at_the_deadline_and_keeps_stored_quotes`、`test_tickers_beyond_the_cap_are_reported_not_dropped`），但「連續兩次更新合起來會不會收斂」沒有測。單次行為正確，整體卻不收斂，這個落差整組測試看不出來。

影響程度取決於 deadline 與持股數的比值。預設 300 秒時一般跑得完，不會顯現；但 `C7-2` 正好可能把 deadline 壓到 100 秒以下，屆時持股超過一兩批（5–10 檔）的人，清單尾端就再也更新不到。也就是說這個缺陷會**正好在調整 deadline 之後才開始咬人**，那時很容易被誤判成抓價來源的問題。

### 修正

切片前先依最後報價時間由舊到新排序：

- 新增 `Storage.latest_quote_times(instrument_ids, provider)`，單一唯讀查詢取回每個 instrument 的 `max(received_at)`，不是逐檔查詢。
- 新增 `Dashboard.order_by_staleness()`，從未取得過報價者排最前（視為最舊），排序相同者維持存檔順序。
- 先 `resolve()` 全部持股再排序再切片；原本是先切片才 resolve。
- 完成訊息改為「再次更新會優先處理這些標的」，這句現在才成立。

依新鮮度優先本來就比依存檔順序更合理：要更新的本來就該是最舊的那幾檔。

### 驗證

| 案例 | 驗證的性質 |
|---|---|
| `test_never_quoted_holdings_are_the_stalest` | 從未報價者排在「剛剛才報價過」之前 |
| `test_order_rotates_so_a_capped_refresh_reaches_every_holding` | AAPL 最舊時排前；AAPL 更新後換 MSFT 排前，證明會輪替 |
| `test_equal_staleness_keeps_the_saved_order` | 同樣新鮮度時順序決定性，不會亂跳 |

三個案例都以**實際寫進 `quotes` 表的報價**驅動，不是替身，因此驗到的是排序真正會讀的那張表。修正後完整套件 **361 passed、0 skipped**。

## 尚未驗證與刻意未定

- **`C4-1` 的兩個數值刻意維持未定**。`refresh_deadline_seconds` 預設 300 秒，是沿用原本「每批就已經花掉」的預算並改成整體上限，比原本「整份清單沒有總時間上限」嚴格；`refresh_max_tickers` 預設不設限。兩者都不是對邊緣逾時的推測。`D3` 明文禁止在 `C7-2`／`C7-6` 量測前寫入猜測數字，`deploy/cloud.toml` 亦已記明 `C6-2` 不得在回填前部署。
- **`C6-2` 的 request timeout 必須大於 `refresh_deadline_seconds`**，否則平台會在程式自己收尾前切斷請求。預設 deadline 300 秒恰好等於 Cloud Run 的預設 request timeout，這個巧合必須在部署設定中拆開。已寫入 `C6-2`。
- **真實的容器終止與 rollout 未驗**。租約回收在隔離資料庫上成立，但 Cloud Run 實際縮容、SIGTERM 與新舊 revision 並存的行為由 `C7-5` 實測。C4 的雲端完成條件在該項通過前不得宣稱達成。
- **長請求與平台探測的互動未驗**。長請求佔住 threadpool 其中一個額度（`CONCURRENCY=8`），`/healthz` 在本機可正常回應，但 Cloud Run 的 concurrency 設定與探測行為要到 `C6-2`／`C7-5` 才確定。
- **`refresh_deadline_seconds` 與 `refresh_max_tickers` 不進入 run 的設定快照**，因此事後從快照看不出當次 run 是在什麼時限下跑的。這是為了不動 campaign 比對摘要所付的代價。
- 官方清單更新仍在 deadline 之外先行（`run_job` 開頭），只有後續的批次受時限管轄。`deploy/cloud.toml` 的 `max_age_hours = 168` 是讓這段盡量不落在關鍵路徑上的既有處置。
