# U5 自動匯率：實作與驗證紀錄

建立日期：2026-10-13

自動抓匯率（`docs/feature-roadmap.md` 的 U5）在本專案的實作與驗證。決議與來源查證寫在 feature-roadmap.md「自動匯率（U5）的決議與查證」節，本文件不重複，只記錄實作、測試、實測，以及還沒做的事。**程式已在本機完成並通過測試，尚未推送、尚未部署**（使用者決定等 10-17 的清單更新做完再部署）。

## 範圍

- 只實作「按更新報價時抓」。本專案維持 `D3`，沒有加固定排程（決議 8）。每天三次的排程留給 finpo。
- 只有 USD/TWD。資料表以幣別對為單位，沒有寫死美元；但程式只核對過 Yahoo 的 `TWD=X`，`fx.yahoo_symbol` 遇到其他幣別對會直接拒絕。
- 拿掉手動匯率（決議 3）。舊持股文件裡的 `fx`、`fx_source`、`fx_updated_at` 欄位會被忽略，不搬移，也不刪除。

## 改了什麼

| 檔案 | 內容 |
|---|---|
| `migrations/0004_fx_rates.sql` | 新表 `fx_rates`：幣別對、匯率（`positive_decimal`）、`rate_kind`（目前只允許 `market`）、來源、來源代號、報價時間、取得時間、`job_id`。只新增、不覆蓋 |
| `fx.py`（新） | 經同一個子程序 worker 抓 Yahoo，核對 `symbol`、`quoteType == CURRENCY`、`currency` 等於報價幣別、價格為正。用 `regularMarketPrice`，不用 bid／ask 平均（理由見下方「已知異常」） |
| `storage.py` | `save_fx_rate`（要有收集程序鎖）、`latest_fx_rate`；`fx_rates` 加入 `TABLES`，所以 `check_schema` 與 `cloud_db` 的授權、RLS 都會涵蓋它 |
| `dashboard.py` | `refresh_fx`：在抓股價之前抓匯率，計入同一個 `refresh_deadline_seconds`，逾時上限取「剩餘時間」與 `operation_timeout_seconds` 的較小者。失敗不讓整次更新失敗：有舊匯率就沿用並在訊息註明時間；完全沒有匯率時，原本會是 `succeeded` 的工作改為 `partial`。`valuation` 改讀最新一筆匯率；`save` 不再讀寫 `fx` |
| `cloud_db.py` | bootstrap 的預設持股文件拿掉 `fx` 欄位 |
| `static/` | 拿掉匯率輸入框與「套用匯率」按鈕；總覽顯示「USD / TWD 匯率 · 來源 · 報價時間 · 取得時間」，只顯示時間，不標示過期（決議 5）；投入成本的說明改為「原幣成本依最新匯率換算」；頁尾說明損益口徑；存檔後缺匯率時也會自動觸發一次更新 |

未實現損益的算法沒有改。決議 1 的算法（原幣損益 × 最新匯率）和現行的「市值換算減成本換算」數學上相同，新增的 `test_unrealized_profit_is_the_original_currency_profit_at_the_latest_rate` 把這個口徑釘住。

## 測試

### 完整套件（隔離容器）

2026-10-13 約 15:00（台北）照 `docs/step-3-evidence.md` 的程序執行（`postgres:17-alpine` 只接 internal 網路，runner 另接 bridge 以安裝依賴，Git Bash 加 `MSYS_NO_PATHCONV=1`）：

- **423 passed，0 skipped**。
- 第一次跑出 43 failed、35 errors。原因是遷移檔裡的正規表示式 `[A-Z]{3}`：遷移原文會經過 psycopg 的 `sql.SQL.format`，大括號被當成佔位符。改成 `[A-Z][A-Z][A-Z]`，並在檔內註明原因。第二次只剩 2 failed，原因相同，出在測試輔助函式的 `'{created_at}'`，改成以參數傳入 JSON 路徑。

### 修正前會不會失敗

把新測試檔放到 `HEAD`（`b62595a`）的 worktree，接同一個拋棄式資料庫跑新增的 6 個整合測試。舊程式沒有 `fx` 模組，所以測試的 stub 改成匯入失敗時略過。6 個全部失敗，但原因不全是行為：

| 測試 | 修正前的失敗原因 | 是否為行為斷言 |
|---|---|---|
| `test_a_manual_rate_is_neither_kept_nor_used` | 存檔結果仍含 `fx` | 是 |
| `test_a_failed_rate_keeps_the_last_one_and_says_so` | 訊息沒有「沿用」 | 是 |
| `test_no_rate_at_all_leaves_the_refresh_partial` | 狀態是 `succeeded` 而不是 `partial` | 是 |
| `test_every_fetched_rate_is_kept_and_the_newest_is_used` | `fx_rates` 表不存在 | 否（結構） |
| `test_taiwan_only_holdings_fetch_no_rate` | `fx_rates` 表不存在 | 否（結構） |
| `test_the_rate_is_fetched_inside_the_refresh_deadline` | 測試本身匯入 `fx` 失敗 | 否（模組不存在） |

`tests/test_fx.py` 的解析與 worker 邊界測試，在修正前都會因 `fx` 模組不存在而失敗，不算行為斷言。損益口徑的測試在修正前就會通過，它是鎖定口徑用的，不是修正用的。

## 實測

以下都在**公司網路**上執行，不能代表 GCP 出口（同 `C7-6` 的原則）。

### 單次抓取

`fx.fetch('USD','TWD',10)` 經真正的子程序 worker 抓 Yahoo：成功，32.146，報價時間 07:07:19Z，**耗時 1.91 秒**（含啟動子程序）。只有一個樣本。

### 從頁面走一次完整流程（拋棄式資料庫）

- 環境：拋棄式 `postgres:17-alpine`（只綁 127.0.0.1）、一般權限角色、`refresh_in_request=false`。靜態檔與 `/api` 由一個只在本機用的包裝層提供：它用一次性的金鑰替 `/api` 請求簽章，代替 Worker，服務自己的 `Guard` 照常驗證。**Worker 與 Access 這一段沒有走到**。用完已刪除容器並停止程序。
- 先寫入一份 U5 之前格式的持股（2330 × 10、AAPL × 2.5，並帶舊的手動匯率 `29.5`）。開頁面時顯示「待取得匯率」與「尚未取得 USD / TWD 匯率」，**舊的 29.5 沒有被使用**。
- 按「更新報價」（真的連 Yahoo）：工作 `succeeded`、「已完成：2/2 檔有可用報價」；`fx_rates` 新增一筆 USD/TWD 32.147，來源 `yahoo`、`TWD=X`、`market`，報價時間 07:10:45Z，取得時間 07:10:48Z，帶 `job_id`。
- 畫面顯示「USD / TWD 32.147 · 來源 Yahoo · 報價時間 2026/10/13 15:10:45 · 取得時間 2026/10/13 15:10:48」。手算核對：投入成本 9,000 + 2.5 × 180 × 32.147 = 23,466.15，和畫面一致；總市值 52,302.91 − 23,466.15 = 28,836.76，和未實現損益一致。
- 估值狀態是「降級估值」，來自既有的逐股品質規則，與匯率無關，沒有細查。
- 沒有檢查手機寬度的版面。

### 與中央銀行收盤價交叉核對

`docs/u5-fx-crosscheck.py`。中央銀行的 JSON 先用 curl 下載再交給腳本：這台機器的 Python 對公司 TLS 解密憑證會報「Missing Subject Key Identifier」，不關閉驗證。

- 比對 2026-09-09 至 10-08 共 20 個兩邊都有資料的日子：Yahoo 日線收盤相對中央銀行收盤，**絕對差最大 0.409%（09-15），平均 0.132%**，正負都有。
- 兩者不是同一個時間點：中央銀行是台北 16:00 的銀行間收盤，Yahoo 日線用它自己的日界。所以這只能說明 Yahoo 的水準合理，不能說明逐筆吻合。0.409% 相當於 100 萬台幣的美元部位差約 4,000 元。
- 中央銀行最新一筆是 10-12；Yahoo 的日線缺 10-12，原因未查。10-09 兩邊都沒有（推測是國慶補假，未查證）。

### GCP 出口實測（2026-10-13 17:21 台北，未推送、未部署）

- 載具：臨時 Cloud Run Job `u5-fx-probe`，`asia-northeast1`，**沿用服務現用的映像** `35743d47289f`（`sha256:a216b906…`），身分 `finpo-runtime`，1 vCPU／1 GiB，`maxRetries` 0。不掛密鑰、沒有資料庫設定，只讀不寫。這個映像裡沒有 `fx` 模組，但 `fx.fetch` 實際做的就是同一個 `provider_worker` 呼叫；`provider_worker.py`、`providers.py`、`uv.lock`、`Dockerfile` 自 `35743d4` 以來都沒有改動（`git log 35743d4..HEAD` 核對），所以量到的是同一段程式。
- 腳本 `docs/u5-fx-gcp-probe.py`（SHA-256 `f03178ed…`），base64 後放在環境變數 `FX_PROBE`。參數全部寫在 `output/u5/job-create.yaml`，以 `--flags-file` 傳入，避開 C7-6 那次 Git Bash 改寫 `/app/...` 的問題。使用者以 PowerShell 建立 Job，Claude 以 `describe` 核對 command、args、映像、環境變數雜湊、沒有密鑰都符合後，使用者才執行。
- 執行 `u5-fx-probe-pbxnz`：09:21:19Z 開始、09:21:54Z 完成，exit(0)。
- 收尾：使用者刪除 Job。10-14 00:37Z，Claude 用 `jobs list` 確認只剩 `finpo-catalog-refresh`，並用 `describe` 確認服務與 `finpo-catalog-refresh` 仍是 `sha256:a216b906…`，沒有被動到。執行紀錄隨 Job 一起刪除；日誌留在 Cloud Logging，本機副本在 `output/u5/logs.json`（不進 git）。

| 次 | 結果 | 耗時（含啟動子程序） | 價格 | 核對 |
|---|---|---|---|---|
| 1 | success | 7.310 秒 | 32.150 | 全部通過 |
| 2 | success | 2.819 秒 | 32.151 | 全部通過 |
| 3 | success | 2.849 秒 | 32.145 | 全部通過 |

- **GCP 出口可以抓到 `TWD=X`**，`quoteType`、`currency`、`symbol` 都和公司網路上看到的一樣。
- 第 1 次 7.31 秒，是新容器裡的第一次呼叫；之後約 2.8 秒，比公司網路上（1.47–1.91 秒）慢。只有一次執行、3 個樣本。
- **這是另開的 Job 容器，不是服務在請求裡抓的耗時**，後者仍要部署後才量得到（部署程序第 6 步）。對 `refresh_max_tickers = 27` 的影響，以下是推論，不是量測：C7-6 R5 的每檔成本 3.967 秒是由批次 1 帶著冷容器的第一次請求（約 8 秒）拉高的；現在抓匯率排在最前面，冷啟動的第一次請求可能改由匯率承擔。所以加上匯率之後，冷啟動時少處理幾檔，要等真實路徑量到才知道。在那之前不改上限。

### 已知異常（未處理）

- 10-13 下午 `TWD=X` 的 `regularMarketPrice` 32.138 高於它自己的 `ask` 32.016，原因未查，只有一個樣本。程式因此不使用 bid／ask。
  - 補記（同日 17:18–17:21）：bid／ask 從 14:50 到 17:21 一直是 31.916／32.016，公司網路和 GCP 都一樣，同一段時間價格在 32.118～32.151 之間變動。所以這兩個欄位看起來沒有在更新，價格高於 ask 應該是因為 ask 停住了。原因仍未查。
- 同一時段，臺銀即期中價 32.20 與 Yahoo 32.138～32.147 差約 0.2%，中央銀行前一日收盤是 31.895。當天新台幣大幅變動，差異來源沒有拆解。

## 尚未驗證

- ~~**GCP 出口抓 `TWD=X`**：從 Cloud Run 抓股價已經在運作，但沒有抓過匯率代號。~~ 10-13 補記：已用臨時 Job 實測可以抓到，見上方「GCP 出口實測」。
- **服務在請求裡抓匯率要花幾秒**：臨時 Job 量到 2.8～7.3 秒，但那不是服務在請求裡抓的。它會佔用 110 秒的時限，`refresh_max_tickers = 27` 是用整整 110 秒算出來的（C7-6 R5），所以持股多、又是冷啟動時，可能有幾檔改排到下一次更新。時限本身仍守得住。量到真實路徑的數字之前，不調整 `refresh_max_tickers`。
- Worker、Access 這一段，以及手機版面。
- 非 USD 幣別對。
- `fx_rates` 不在 `cloud_db prune` 的範圍內，會一直累積。每次按更新最多一筆，量很小，沒有處理。

## 部署程序（10-17 清單更新與核對做完之後，由使用者執行）

**注意：遷移一套用到正式資料庫，現行映像的主要功能就會失敗**（讀程式碼推論，未實測）。`start_run` 的 `check_schema` 和讀官方清單時的 `_check_versions(require_current=True)`，都要求資料庫的遷移清單與程式內的完全一致。資料庫多了 `0004` 之後，`35743d47289f` 的更新報價、存檔和 `finpo-catalog-refresh` 都會回「Schema 版本或 migration checksum 不符」。所以第 3、4 步要接著做。同理，**套用 `0004` 之後，C7-7-6 的前版映像回滾就不能用了**，回滾目標必須改成含 `0004` 的映像。

0. 確認 10-17 那次清單更新的核對與備份匯出都已完成，而且沒有更新正在執行。
1. 推送前，以 `describe` 核對服務與 Job 都用 `35743d47289f`（CLAUDE.md 的規則）。
2. 推送 → 建置新映像。Registry 只保留 3 版，這次會擠掉 `723f6f2ef7f5`。
3. 以管理者身分執行 `python -m stock_quote_fetcher.cloud_db bootstrap-sql --schema dashboard --runtime-role finpo_app` 產生的 SQL（方式同 C6-3）。這段 SQL 可以重跑：已套用的遷移會比對 checksum，持股不會被重設；它也會替 `fx_rates` 授權並開啟 RLS。
4. 立刻把服務與 `finpo-catalog-refresh` 都改用新映像，並以 `describe` 核對只有映像改變。
5. 以 runtime 跑 `cloud_db check`，確認權限契約（`fx_rates` 只有 SELECT、INSERT、UPDATE）。
6. 在正式網站按一次「更新報價」（真實路徑），然後唯讀核對：
   - 工作訊息，以及總覽上的匯率列。
   - `fx_rates` 新增的那一筆。
   - 抓匯率耗時的上限：同一個 `job_id` 的 `received_at` 減去該工作的 `created_at`。這包含子程序啟動與連線建立，不含冷啟動。
7. 結構改了，匯出一份新備份。下一次每季還原演練時，表的數量會是 15 張，不是 14 張。
8. 結果補記到本文件，並更新 feature-roadmap.md 的 U5 狀態。
