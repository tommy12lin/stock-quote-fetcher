# C6 執行紀錄：建置、部署與一次性初始化

日期：2026-09-23 開檔（`C6-1`）。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C6`。本檔只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public，workflow 的執行紀錄亦公開可見。映像路徑、GCP 專案 ID 與專案編號屬識別碼而非憑證，與 `C1` 執行紀錄一致照實記錄。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C6-1` GitHub Actions 建置與推送 | ✅ 完成 | run `35806642267`，digest 已取得並經 GCP 端獨立核對 |
| `C6-2` 部署設定 | 🟡 已部署（2026-09-30） | ~~**仍被 `C4-1` 的兩個數值擋住**，見下~~ 服務 `stock-quote` 已上線，設定逐項核對、反面測試通過。**未完成的有~~三項~~~~兩項~~一項**：從服務連資料庫尚未實測（要帶簽章的請求，由 `C7-2` 承接）；~~日誌的內容與保留量未處理~~（同日已處理，見文末「`C6-2` 補記：日誌」節；現行 revision 因此為 `stock-quote-00004-4v6`，映像 `a1fb03ff680d`）；~~部署方式偏離 `D6`~~（同日 `D6` 已改寫為接受手動 `gcloud`，此項解除）。見下方 `C6-2` 節 |
| `C6-3` 一次性初始化 | ✅ 完成（2026-09-30） | ~~⬜ 未開始~~ 管理者在正式 Supabase 重跑 bootstrap 成功，前後快照除清單多一代外相同；runtime 更新清單成功（`finpo-catalog-refresh` 在新映像上的第一次執行），`cloud_db check` 通過。界線（bootstrap 是否實際改動分不出來、沒有重做 DELETE 被拒的反面測試、新一代列數未讀出）見下方 `C6-3` 節 |
| `C6-4` digest 與回滾紀錄 | ~~🟡 部分~~ ✅ 完成（2026-09-30） | **同日補記：回滾已實測**，由 `ab1667ccf7f7` 回滾到 `244fd00583bb`（`00002-wl7`）再換回（`00003-qs6`），兩次都只有映像與 nonce 改變、啟動成功；secret 版本已記錄。界線（沒有觀察到舊版行為、資料庫向後相容沒有被考驗、secret 參照 `latest` 不隨映像回滾）與三個缺口見下方 `C6-4` 節。以下為原記錄：digest 產出機制已建立（本項），~~回滾實測待 `C7-7`~~ 回滾實測屬本項，未實測（2026-09-30 補記更正：C6 完成條件要求「服務可由記錄的映像 digest 重新部署並啟動成功」，本檔 `C6-2` 節亦記為「屬 `C6-4`」，與計畫書抬頭「下一步為 `C6-4`（回滾實測）」一致；`C7-7` 的「前版映像回滾」是營運驗收時的再次演練，不取代本項）。**2026-09-30 補記**：`D6` 修訂後部署紀錄以本檔為準，首次部署的完整指令、digest 與 `describe` 已記在下方 `C6-2` 節 |

## C6-1　GitHub Actions 建置與推送

### 交付

`.github/workflows/build-image.yml`：push 到 `main` 時建置 `linux/amd64` 的 **web** 映像並推送 Artifact Registry，以 Workload Identity Federation 取得憑證。**只建置與推送，不部署**——依 `D6`，部署一律手動觸發（`C6-2` 另立 workflow），因此 `main` 上一次失敗的建置不會讓任何東西上線。

### `C1-9` 留下的三條待辦，處置與理由

| 條件 | 處置 |
|---|---|
| (a) action 釘 commit SHA | `actions/checkout` v7.0.1 → `3d3c42e5aac5ba805825da76410c181273ba90b1`；`google-github-actions/auth` v2.1.13 → `c200f3691d83b41bf9bbd8638997a462592937ed`。兩者皆以 `git ls-remote` 對上游解析，非轉抄。**另只使用這兩個 action**，其餘走原生 `docker` 指令 |
| (b) ref 限制 | 以 job 層 `if: github.ref == 'refs/heads/main'` 實作。**provider 層的 `assertion.ref` 未加**，理由見下 |
| (c) cleanup policy | 已設 `keep-recent-3`（保留最近 3 個版本）＋ `delete-older`（其餘刪除），dry run 關閉 |

(a) 的實質理由不是「釘 SHA」這個動作，而是**本 job 帶 `id-token: write`**：用到被汙染的 action 等同交出 deploy SA 的 `artifactregistry.writer` 與 `run.admin`。tag 可被重新指向，commit SHA 不行。同一個理由推導出「少用 action」——每多一個第三方 action 就多一個等同交出憑證的入口，所以登入與建置都用原生指令。

(b) 只在 workflow 層限制的原因：WIF provider 的 attribute condition 目前仍只含 `assertion.repository`，因此本 repo 的任何分支都換得到憑證；而 `workflow_dispatch` 可指定任意 ref，**光靠 `on.push.branches` 擋不住**，那一行 `if` 是目前唯一的關卡。在 provider 加 `assertion.ref` 會使日後無法從分支驗證 workflow 改動（`C1-9` 當初正是靠這個性質完成驗證），屬另一個取捨，留待需要時再決定。

(c) 的依據：`C1-9` 實測第一個 tag 約 125 MB、其後每個增量 tag 約 82 MB，約第 6 個即超出 0.5 GB 免費額度。本次第一個映像實際為 **125,962,183 bytes**，與該估計相符。

### 執行結果

| 項目 | 值 |
|---|---|
| run | `35806642267`（`Build image`，push 觸發） |
| 耗時 | 48 秒 |
| commit | `224a29b1b011…` |
| tag | `224a29b1b011`（commit SHA 前 12 碼） |
| digest | `sha256:99ee3a38f1dd6b1ed1b01f713ccee1494c0fdc07d78a5e8d7bd1e22fd4a5dcb3` |
| 映像大小 | 125,962,183 bytes |
| service account 金鑰 | **0 個**（全程 WIF） |

**tag 取 commit SHA 前 12 碼**，使映像與原始碼一一對應，回滾時不需查表。digest 在 `docker push` 之後以 `docker inspect` 取得（`RepoDigests` 在推送前沒有值），寫入 job summary 作為 `C6-4` 的回滾依據，不靠人工抄寫。`access_token` 以 stdin 交給 `docker login`，不進命令列——run log 公開。

### 映像實測核對

從 Artifact Registry 以 digest 拉回後實際檢查，不只看建置有沒有綠燈：

| 檢查 | 結果 | 為什麼要查 |
|---|---|---|
| `Entrypoint` | `["/app/.venv/bin/stock-web","--container","--config","/app/cloud.toml"]` | **`--target web` 是否真的生效**。預設目標 `runtime` 的 ENTRYPOINT 是 CLI，推上去 Cloud Run 只會判定啟動失敗，而失敗訊息不會指向這個原因 |
| `Cmd` | `null` | 確認不需覆寫 command／args（`C6-2`） |
| `User` | `app:app` | 非 root 設計保留 |
| 架構 | `linux/amd64` | 交付目標 |
| `/app/cloud.toml` | 存在，2644 bytes，`root:root` `0644` | `C2-5`：設定檔隨映像出貨、應用帳號唯讀 |
| `/app/supabase-ca.crt` | 存在，1367 bytes | `C5-3`：TLS 驗證所需的官方 CA |
| `/tmp` | **空** | 公司 CA 的合併檔（`/tmp/build-ca.pem`）沒有殘留——runner 未傳入 `company_ca`，Dockerfile 三處條件式掛載整段跳過，交付映像與公司網路脫鉤（`D6`） |
| `stock-web --help` | 正常輸出 usage | venv 可執行，依賴齊全 |

GCP 端另以 `gcloud artifacts docker images list` 獨立核對：digest 與 tag 皆與 run log 一致，tag 與本地 `git rev-parse HEAD` 前 12 碼相符。

### `config.example.toml` 移除 `[tls]`

`company_ca_file`、`relaxed_providers`、`relaxed_sources` 三個欄位只為穿過會攔截 TLS 的公司代理而存在，每一個都在削弱憑證驗證。以空值形式擺在例示檔裡，等於邀請把它們複製到不需要的部署上。

欄位本身**保留可用**（設在被忽略的 `config.toml`），`config.py` 三者預設皆為關閉，因此省略整個區段等同原本的空值。已以兩個載入器實跑確認：

| 載入器 | 結果 |
|---|---|
| `load_instrument_catalog_config` | `company_ca_file=''`、`relaxed_sources=()` |
| `load_quote_config` | `company_ca_file=''`、`relaxed_providers=()` |

與移除前完全相同；`document.get('tls', {})` 對缺少的區段本來就有預設值。無任何測試引用該檔。

### 兩則 runner 警告

| 警告 | 影響 |
|---|---|
| `google-github-actions/auth` 以 Node 20 為目標、被強制跑在 Node 24 上 | 與 `C1-9` 當時觀察到的同一則。目前僅為棄用警告，建置未受影響；該 action 更新後即消失 |
| **`ubuntu-latest` 將於 2026-10-19 起遷移至 Ubuntu 26** | **約一個月後建置環境會在無人改動的情況下改變。** 本專案的映像內容大致不受影響——基礎映像以 digest 釘死、依賴由 `uv.lock` 鎖定——真正的變數是 runner 上的 docker／BuildKit 版本。若遷移後建置失敗或映像產生非預期差異，**這是第一個檢查點**；處置方式為把 `runs-on` 改釘 `ubuntu-24.04`，但那與 `D6` 選用標準 runner 的決定相左，故不預先改動 |

### 仍未驗證

| 項目 | 說明 |
|---|---|
| WIF attribute condition 的**阻擋效力** | 沿用 `C1-9` 的狀態：仍只有正向驗證。「別的 repository 換不到憑證」需要第二個 repository 才能構成證據，**不得宣稱已驗證能擋下** |
| cleanup policy 的**實際刪除行為** | policy 已設定並由 API 回讀確認，但**刪除仍未實際發生過**。2026-09-23 已累積至 **4 個版本**（超過 `keepCount: 3`）而四個都還在：Artifact Registry 的 cleanup policy 是**背景非同步回收**，不在推送時同步套用。因此「下一次建置就會看到刪除」是錯的，時機不由推送決定。下次查看 registry 時若仍為 4 個以上，先確認是否只是尚未回收，再懷疑 policy 設錯 |
| 建置的**可重現性** | **已測，且結論是「不可重現」**——見下節 |

### 意外取得的結果：相同 build context 產生不同 digest

第二次建置（run `35806964620`，commit `eea0c80b276e`）是**只改 `docs/` 的提交**觸發的。`docs/` 被 `.dockerignore` 排除，`git diff --name-only` 確認兩個 commit 之間沒有任何檔案落在 build context 的允許清單內（`pyproject.toml`／`uv.lock`／`README.md`／`src`／`deploy/cloud.toml`／`deploy/supabase-ca.crt`）。**build context 位元組相同，映像卻不同：**

| | run `35806642267` | run `35806964620` |
|---|---|---|
| digest | `sha256:99ee3a38…` | `sha256:63ac8530…` |
| 大小 | 125,962,183 | 125,961,768（**少 415 bytes**） |

逐層比對（`RootFS.Layers`）定位差異：

| 層 | 內容 | 結果 |
|---|---|---|
| 1–4 | 基礎映像 | **相同**（`ARG BASE_IMAGE` 釘 digest 有效） |
| 5–6 | `useradd`／`install -d`、`COPY --from=builder /app/.venv` | 不同 |
| 7 | — | 相同 |
| 8–9 | web stage 的 `COPY cloud.toml`、`COPY supabase-ca.crt` | **不同** |

第 8、9 層是決定性的證據：那兩個檔案的**內容與權限都被釘死**（`COPY --chown=root:root --chmod=0644`），層卻仍然不同，因此差異只可能來自 tar 層內嵌的 **mtime**——`actions/checkout` 每次把工作目錄的檔案時間設為當次取出的時間。`/app/.venv` 那層還多一個來源：`UV_COMPILE_BYTECODE=1` 產生的 `.pyc` 會嵌入來源檔的 mtime。

**Dockerfile 對 `--chmod` 寫的註解因此需要修正認知。** 該註解說釘死權限位元是為了「讓建置可重現」；那確實解決了 Windows 與 Linux runner 給出不同模式位元的問題，但**沒有**達成它所宣稱的可重現——mtime 仍在變。註解的處置正確，目標未達成。

**影響有限，但要寫清楚是哪一種有限**：

- `C6-4` 的回滾**不受影響**。回滾是以記錄下來的 digest 重新部署一個既存映像，不是重建。
- 受影響的是另一條路徑：**「映像遺失後照同一個 commit 重建」不會得到同一個 digest**。功能等價，但 digest 不同，因此任何以 digest 為準的紀錄或比對都對不上。真要修，方向是 `SOURCE_DATE_EPOCH` 加上 BuildKit 的時間戳重寫；本階段不做，先記錄。

### `paths-ignore` 的判斷單位是一次 push，不是一個 commit

2026-09-23 實測：把「程式修正」與「文件更新」拆成兩個 commit 一起推，建置**照常觸發**（正確——該次 push 確實含程式變更），但 **run 與映像 tag 都掛在 head commit（文件那個）上**，tag 為 `06e2df807527` 而非程式 commit `2a94be4…`。

`paths-ignore` 評估的是整次 push 涵蓋的檔案集合，不是逐個 commit；GitHub 以 head commit 標記 run，而本 workflow 的 tag 取 `GITHUB_SHA` 前 12 碼。

**對 `C6-4` 的影響**：映像 tag 指向的 commit **不保證是造成該映像內容變化的那個 commit**。回滾仍以 digest 為準，不受影響；但若有人從 tag 反查「這個映像對應哪次程式變更」，會查到錯的 commit。要讓兩者對應，程式與文件必須**分兩次 push**，不是分兩個 commit。

### 一個應該修的觸發條件

上述第二次建置本身就是問題的示範：**只改文件的提交也會建置並推送一個新映像**。`on: push: branches: [main]` 沒有路徑過濾，因此每一次文件提交都消耗一次建置、並在 registry 佔掉一個版本——而 cleanup policy 只保留 3 個，等於用文件提交把真正的程式版本擠出保留窗口。建議加 `paths-ignore`（`docs/**`、`**.md`）。尚未實作，留待決定。

## 交接給 `C6-2`

**`C6-2` 仍不得執行。** 計畫書的硬性前提未解除：`deploy/cloud.toml` 的 `[scheduler]` 仍未回填 `refresh_deadline_seconds` 與 `refresh_max_tickers`。現況：

| 數值 | 狀態 |
|---|---|
| `refresh_deadline_seconds` | 硬上界 **125 秒**已由 `C7-2` 量出（見 [C7 證據](cloud-C7-evidence.md)），但**仍須扣除冷啟動**。本項交付的映像使冷啟動終於可量——**這是 `C6-1` 解開的東西** |
| `refresh_max_tickers` | 完全無依據，待 `C7-6` 的實際抓價耗時 |

`C6-2` 另須注意：request timeout 必須大於 `refresh_deadline_seconds`，但**無論設多大都無法超過 125 秒的邊緣上限**（`C7-2` 已證實限制在邊緣不在平台）。

**2026-09-30 補記**：兩個數值都已回填（`refresh_deadline_seconds = 110`，`refresh_max_tickers = 27`，`ab1667c`），前提解除，`C6-2` 已執行，見下節。

## C6-2　部署（2026-09-30）

**結論：服務 `stock-quote` 已部署並啟動成功，設定逐項與下表一致；不帶簽章或簽章錯誤的 `/api/` 請求回 401，舊式網址因 Host 不在白名單而回 403。從服務連資料庫尚未實測，本項不勾選完成。**

### 執行

由使用者在 Windows PowerShell 5.1 執行。我方的自動執行權限以「弱化認證」為由擋下這條指令，指的是 `--allow-unauthenticated`；依 `D1`，這一項是必要的。部署開始於 05:20:48Z 左右（第一筆日誌的時間）。

```
gcloud run deploy stock-quote --region=asia-northeast1
  --image=asia-northeast1-docker.pkg.dev/finpo-508709/finpo/stock-quote@sha256:7da85b3a2d0f97d3cad47968e2f3c59c79ace0e4cf56d8d352270d0e52346a1f
  --service-account=finpo-runtime@finpo-508709.iam.gserviceaccount.com
  --cpu=1 --memory=1Gi --min-instances=0 --max-instances=1 --concurrency=10 --timeout=150
  --allow-unauthenticated
  --set-env-vars="DB_HOST=…,DB_PORT=5432,DB_NAME=postgres,DB_USER=…,WEB_ALLOWED_HOSTS=stock-quote-896096883650.asia-northeast1.run.app,WEB_ALLOWED_ORIGINS=https://finpo.drhiromu.workers.dev"
  --set-secrets="DB_PASSWORD=db-password:latest,PROXY_HMAC_SECRET=proxy-hmac-secret:latest,PROXY_HMAC_SECRET_PREV=proxy-hmac-secret-prev:latest"
```

（`DB_HOST` 與 `DB_USER` 屬識別資訊，依 `C1-4` 不記錄於本檔；兩者與 `finpo-catalog-refresh` 的設定相同。）

### 設定值與依據

| 設定 | 值 | 依據 |
|---|---|---|
| 服務名 | `stock-quote` | `C6-1`：repository 以專案命名、image 以服務命名 |
| 映像 | `ab1667ccf7f7`，`sha256:7da85b3a…`（含 `refresh_max_tickers = 27`） | 09-30 run `36669128758` |
| 規格 | 1 vCPU／1 GiB、min=0、max=1 | `C6-2`、`D3` |
| request timeout | **150 秒** | **依算式選的，不是量測值**：必須大於 `refresh_deadline_seconds` 110，程式最晚約 118.5 秒收尾（`C7-7` 算式），邊緣在 125 秒切斷。超過 118.5 之後，這一層就不會是先觸發的那一層。多留約 30 秒，是因為冷啟動是否算進平台的計時**未實測**；而低於預設的 300，卡住的請求就不會佔住唯一的實例 5 分鐘。使用者選定 |
| concurrency | **10** | **沒有量測依據**。計畫書只規定不可為 1。取與 `C7-2`、`C7-7` 兩個量測服務相同的值，使用者選定 |
| `WEB_ALLOWED_HOSTS` | 只有決定性網址 `stock-quote-896096883650.asia-northeast1.run.app` | 範圍最窄，使用者選定。**`C7-2` 的 Worker 必須呼叫這個網址**；呼叫舊式網址會被判 403（下方反面測試） |
| `WEB_ALLOWED_ORIGINS` | `https://finpo.drhiromu.workers.dev` | `C1-6` 的前端 Worker。preview URL 不在白名單內 |
| 公開呼叫 | `allUsers` → `roles/run.invoker` | `D1`：Worker 以一般 HTTPS 呼叫，關卡在 `C3-1` 的 HMAC |
| 秘密 | 三把都參照 `latest`，`finpo-runtime` 對三把都有 `secretAccessor`（部署前以 `get-iam-policy` 核對）；目前都只有版本 1，均為 enabled | `C1-3`、`C1-7` |
| 探測 | 不另設，維持平台預設的 TCP 啟動探測 | `/healthz` 在公開網址不可用（C7 證據）；計畫書寫的是「若設定」。預設沒有 liveness probe |
| command／args | 不覆寫 | 映像的 ENTRYPOINT 已帶 `--container --config /app/cloud.toml`；schema 用 `web` 的預設值 `dashboard` |

### `describe` 核對（部署後）

逐項讀出並與上表比對，**全部一致**：映像 digest、`cpu 1`／`memory 1Gi`、`maxScale 1`（`minScale` 未出現，即預設 0）、`containerConcurrency 10`、`timeoutSeconds 150`、`serviceAccountName finpo-runtime`、6 個一般環境變數與 3 個 secret 參照、command／args 為空、埠 8080、ingress `all`。IAM 只有 `allUsers` → `run.invoker` 一條。

PowerShell 5.1 在參數裡帶了引號的逗號，這次**沒有被拆開**（6 個環境變數、3 把 secret 各自獨立出現），與 C7 證據「收尾」節的 `reset` 結果一致。

平台自行加上、非由參數指定的：`run.googleapis.com/startup-cpu-boost: true`（gcloud 的預設值），以及預設的 TCP 啟動探測（`periodSeconds 240`、`timeoutSeconds 240`、`failureThreshold 1`）。**`C7-7` 量冷啟動時的服務是否也開了 startup CPU boost，當時沒有記錄**，所以兩者的冷啟動是否可比，未確認。

| 項目 | 值 |
|---|---|
| revision | `stock-quote-00001-dx4`，Ready，100% 流量 |
| `status.urls` | `https://stock-quote-896096883650.asia-northeast1.run.app`（決定性網址，與 `WEB_ALLOWED_HOSTS` 一致）、`https://stock-quote-nfmyvudecq-an.a.run.app`（舊式網址） |

### 啟動日誌

05:20:56Z `Starting new instance. Reason: DEPLOYMENT_ROLLOUT`；05:20:59.64Z 印出 `listening on 0.0.0.0:8080`，以及 allowed hosts、allowed origins 各一行，值與設定相同；05:20:59.83Z `Default STARTUP TCP probe succeeded after 1 attempt`。到 05:23:47Z 為止共 14 筆日誌，沒有任何 error、traceback 或 exception。

### 反面測試（05:23:45Z–05:23:47Z，自本機以 curl 發出）

| 請求 | 回應 | 說明 |
|---|---|---|
| 決定性網址 `GET /api/portfolio`，不帶簽章 | **401** `unauthorized` | `C3-1` 的驗簽生效 |
| 決定性網址 `GET /api/session`，不帶簽章 | **401** | 同上；這個端點以前會對任何人發 token（`D1`） |
| 決定性網址 `GET /api/portfolio`，帶格式正確但錯誤的 `X-Timestamp`／`X-Signature` | **401** | 錯誤簽章同樣被拒 |
| 舊式網址 `GET /api/portfolio`、`GET /` | **403** `拒絕不合法的 Host。` | Host 白名單生效，而且 Host 檢查發生在驗簽之前 |
| 決定性網址 `GET /healthz` | **404**，Google 前端的 HTML 錯誤頁 | 與已知限制相同（C7 證據）；日誌裡**沒有**這筆請求，證實它沒有抵達容器 |
| 決定性網址 `GET /` | **404**，應用程式的 JSON（`找不到頁面。`） | 容器有回應。雲端的靜態檔由 Worker 提供（`D2`），容器不提供首頁 |

日誌裡對應的請求都記錄了狀態碼（401／403／404），與 curl 看到的一致。這批請求落在部署時啟動的那個實例上，**所以不是冷啟動量測**。

### 未完成、未實測的部分

- **從服務連資料庫：未實測。** 啟動時不連資料庫（`Dashboard.__init__` 只載入設定），而每個 `/api/` 端點都要簽章。自行簽章就得把 `proxy-hmac-secret` 取到本機，所以不這樣做；由 `C7-2` 的 Worker 以正式路徑送出第一個帶簽章的請求時一併確認。**在那之前，不得宣稱服務能讀寫資料庫。**
- **正向的驗簽：未實測。** 目前只證明了「沒簽或簽錯會被拒」，還沒證明「簽對會放行」。同樣由 `C7-2` 承接（Worker 與後端對同一 canonical string 產生相同簽章）。
- ~~**日誌的內容與保留量：未處理。** `C6-2` 要求「限制內容與保留量」。目前沿用 Cloud Logging 預設的 bucket 與保留期，沒有另外設定，也沒有逐項核對日誌內容不含敏感資料。啟動日誌印出的是 allowed hosts 與 origins，不含秘密。~~ 同日已處理：盤點時發現平台請求日誌會記下上傳的檔名，已修正並部署；保留期維持 30 天為明確選擇。見文末「`C6-2` 補記：日誌」節。
- **部署方式偏離 `D6`。** `D6` 定「部署到 Cloud Run 一律手動觸發（`workflow_dispatch`）」，本檔 `C6-1` 節也寫了「`C6-2` 另立 workflow」。這次是由使用者以 `gcloud run deploy` 直接部署，deploy workflow **尚未實作**。~~要補上 workflow，還是改寫 `D6` 接受手動 `gcloud`，待使用者決定；這也牽動 `C6-4`「以 digest 手動觸發重新部署」的回滾方式。~~ **同日使用者決定改寫 `D6`，接受手動 `gcloud`**（見計畫書 `D6` 的 09-30 修訂）。部署紀錄與回滾改以本檔為準。附帶查明：`finpo-deploy` 仍持有已無用途的 `roles/run.admin` 與對 `finpo-runtime` 的 `serviceAccountUser`，~~是否撤除待決定~~ 同日已撤除（見 C1 證據 `C1-9` 節補記）。**往後部署與回滾都由管理者以自己的帳號執行 `gcloud`**，建置 workflow 已無法部署。
- ~~**回滾：未實測**，屬 `C6-4`。~~ 同日已實測，見下方 `C6-4` 節。現行 revision 因此變為 `stock-quote-00003-qs6`（映像與 `00001-dx4` 相同）。
- **冷啟動：未在正式服務上量測**，屬 `C7-7` 的正式驗收（見上方 startup CPU boost 一段）。

## C6-3　一次性初始化與官方清單更新（2026-09-30）

**結論：管理者在正式 Supabase 上重跑了 bootstrap SQL，成功，且重跑前後除了清單多一代，其餘狀態完全相同（`portfolio` 沒有被重設）。接著由 runtime 以 `web --refresh-catalog` 更新清單，這是 `finpo-catalog-refresh` 第一次在新映像上執行，成功。最後以臨時 Job 從 runtime 身分跑 `cloud_db check`，最小權限契約通過。**

`C5-2` 已完成首次初始化；本項是在部署環境照正式程序再跑一遍，並證明初始化**在正式資料庫上可以獨立重跑**（`C6` 完成條件）。

### 程序（往後重跑照此執行）

| 順序 | 執行者 | 內容 |
|---|---|---|
| 1 | 管理者，Supabase SQL Editor | 執行 [`c6-db-snapshot.sql`](c6-db-snapshot.sql)（唯讀，單一 SELECT），留下初始化前的快照 |
| 2 | 任何人，本機 | `python -m stock_quote_fetcher.cloud_db bootstrap-sql --schema dashboard --runtime-role finpo_app > output/c6/bootstrap.sql`。不需連線，也不含秘密 |
| 3 | 管理者，Supabase SQL Editor | 執行步驟 2 的 SQL。整份在單一交易內：以 runtime 身分執行、collector 持有 advisory lock、migration 版本未知或 checksum 不符，任一種都會整筆回滾 |
| 4 | 管理者，`gcloud` | `gcloud run jobs execute finpo-catalog-refresh --region=asia-northeast1 --wait`（以 `finpo-runtime` 執行 `web --refresh-catalog`） |
| 5 | 管理者，`gcloud` | 以臨時 Job 從 runtime 身分執行 `cloud_db check`，核對後刪除（設定見下） |
| 6 | 管理者，Supabase SQL Editor | 再跑一次步驟 1 的快照，逐項比對 |

**不得以 runtime 執行 migration 或 `web --initialize`**（`C5-2`）。步驟 3 的 SQL 以 `current_user` 擋下 runtime，這次的快照也證實執行者為 `postgres`。

### 執行紀錄

| 步驟 | 時間（UTC） | 結果 |
|---|---|---|
| 1 快照（前） | `db_now` 05:49:21.88Z | 見下方比對表 |
| 2 產生 SQL | 05:49 前 | 以 HEAD（`2903fd7`）產生，239 行，SHA-256 `877419d7bc52f23e85cf345e53f06509d9f4c4e805cc8baa3c88de58e2dfc19e`（Windows 下以 shell 轉向寫檔，換行為 CRLF，雜湊依此計算）。migration 自 `3afdace`（`C5-2`）起未變，已部署映像 `ab1667c` 內的 migration 與此相同 |
| 3 bootstrap | 05:49:21Z–05:50:42Z 之間 | SQL Editor 回報 `Success. No rows returned`。確切執行時間沒有記錄，上下界分別是前快照與步驟 4 觸發的時間 |
| 4 清單更新 | 觸發 05:50:42Z；execution 05:50:50.64Z–05:51:23.46Z | `finpo-catalog-refresh-tsp9t`，成功。映像 `sha256:7da85b3a…`（`ab1667ccf7f7`），**是這支 Job 在新映像上的第一次執行**。日誌：05:51:20.93Z `Dashboard catalog refreshed.`、05:51:21.07Z `Container called exit(0).` |
| 5 runtime 核對 | execution 05:53:08.64Z–05:53:25.47Z | `c6-3-runtime-check-p58h6`，成功。stdout 為 `{"runtime_permissions": "passed"}`（Cloud Logging 將它解析為 `jsonPayload`，所以 `textPayload` 為空）。Job 已於 05:54Z 刪除，之後 `gcloud run jobs list` 只剩 `finpo-catalog-refresh` |
| 6 快照（後） | `db_now` 06:07:52.41Z | 見下方比對表 |

**臨時 Job `c6-3-runtime-check` 的設定**（建立後以 `describe` 核對）：映像同上（digest）；command `/app/.venv/bin/python`，args `-m stock_quote_fetcher.cloud_db check --config /app/cloud.toml`；身分 `finpo-runtime`；`DB_HOST`／`DB_PORT`／`DB_NAME`／`DB_USER` 由 `finpo-catalog-refresh` 的 `describe` 讀出後原樣帶入，沒有印出（`DB_HOST`、`DB_USER` 依 `C1-4` 不記錄）；`DB_PASSWORD` 掛 `db-password:latest`；timeout 120 秒、`maxRetries` 0。在 Git Bash 下建立，以 `MSYS2_ARG_CONV_EXCL` 排除 `--command=`、`--args=`、`--image=` 的路徑轉換，`describe` 讀回的 command 與 args 與預期相同。

### 前後快照比對

快照 SQL 為 [`c6-db-snapshot.sql`](c6-db-snapshot.sql)（SHA-256 `071b277b7c424250a245714147edfbc8a4dcf71c080a20838a32a832f286edae`）。14 項中只有 `db_now` 與 `catalog_generations` 不同；兩份原始結果存於本機 `output/c6/snapshot-{before,after}.json`（Git 忽略），以程式逐項比對。

| 項目 | 前（05:49Z） | 後（06:07Z） |
|---|---|---|
| `current_user` | `postgres` | 同左 |
| migrations | `0001` `44b28fa8b5a3`、`0002` `73d426bf735c`、`0003` `d80724dadb15`，皆為 `cloud-bootstrap` | 同左；三個 checksum 前 12 碼與本機 `migration_sources()` 算出的相同 |
| `portfolio` | `revision=5 rows=0` | **同左，未被重設** |
| `refresh_jobs` | 0 | 同左 |
| 清單 generation | **3**，最新 `completed_at` 09-29 14:35:34.66Z、`expires_at` 10-06 14:35:34.66Z | **4**，最新 `completed_at` **09-30 05:51:20.26Z**、`expires_at` **10-07 05:51:20.26Z（台北 13:51）** |
| 表數／RLS | 14／14 啟用 | 同左 |
| 表擁有者 | 只有 `postgres` | 同左 |
| policy | 14 條，`runtime_access` ALL 或 SELECT，對象 `finpo_app` | 同左 |
| `finpo_app` 表權限 | 13 張表 INSERT+SELECT+UPDATE，`schema_migrations` 只有 SELECT | 同左 |
| schema ACL | `{postgres=UC/postgres,finpo_app=U/postgres}` | 同左 |
| `finpo_app` 對 `app` 的 USAGE | false | 同左 |
| 已授予的 advisory lock | 0 | 同左 |

### 未驗證、有界線的部分

- **bootstrap 是否真的套用了語句，快照分不出來。** 所有 migration 都已存在，SQL 只會走「已存在且 checksum 相符」的分支，GRANT／POLICY 則是撤銷後重建成相同結果，所以「跑了但沒變」和「沒跑」在快照上長得一樣。能證明它有執行的，只有 SQL Editor 的 `Success`。
- **快照沒有涵蓋的項目**：policy 的 `USING`／`WITH CHECK` 內容、欄位層級權限、對 `PUBLIC` 的表權限、兩個 domain 的擁有者。這幾項由 bootstrap SQL 設定，但前後沒有比對。其中 RLS 與表權限的實際效果，已由 `cloud_db check` 從 runtime 端核對。
- **`cloud_db check` 是以 `has_table_privilege` 逐項核對權限，沒有實際嘗試 DELETE 或 CREATE。** 實際被拒（SQLSTATE 42501）的反面測試是 `C5-2` 在 09-22 做的，這次沒有重做。
- **新 generation 的列數沒有讀出。** 快照只數 generation 的代數；09-29 那一代為 13,457 列。Job 以結束碼 0 完成，而 `save_instrument_catalog` 要求五個來源各恰好一次、否則拋例外（`storage.py`），所以推定寫入完整，但沒有逐列核對。
- **清單更新耗時**：以 C7 證據的同一量法（execution 開始 → 輸出 `Dashboard catalog refreshed.`）為 05:50:50.64Z → 05:51:20.93Z，**約 30.3 秒**；09-29 約 13 秒、09-23 約 70.7 秒。觸發到 `--wait` 返回為 05:50:42Z → 05:51:34Z，約 52 秒（時間取自本機 `date`，不是日誌）。各來源的 `fetched_at` 沒有讀出，所以這 30 秒花在哪裡沒有拆開。依 C7 證據，不得以任何單一樣本當作典型耗時。
- **保留規則**：現在有 4 代。依 `C5-6`，只有明確執行 `cloud_db prune` 時才會清除；本次沒有執行 `prune`。

## C6-4　回滾實測（2026-09-30）

**結論：以 `C6-2` 記錄的同一條 `gcloud run deploy`、只換映像 digest，把服務從 `ab1667ccf7f7` 回滾到上一版 `244fd00583bb`，再以同樣方式換回 `ab1667ccf7f7`。兩次部署都啟動成功並接到 100% 流量；與部署前的 `describe` 相比，兩次都只有映像與 nonce 不同。服務可由記錄的 digest 重新部署並啟動（`C6` 完成條件的前半）。**

### 回滾目標的選擇

部署前以 `gcloud artifacts docker images list` 列出 repository，有 4 個映像：

| tag | digest | 建立（台北） |
|---|---|---|
| `218b4b962c5a` | `sha256:5ceea993…` | 09-23 17:00 |
| `b6347e610e87` | `sha256:3a204775…` | 09-25 14:06 |
| `244fd00583bb` | `sha256:44af174b…` | 09-26 11:04 |
| `ab1667ccf7f7` | `sha256:7da85b3a…` | 09-30 12:30（現行） |

選上一版 `244fd00583bb`。`git diff 244fd00583bb ab1667ccf7f7`（排除 `docs/`）只有 `deploy/cloud.toml` 一個檔案：上一版沒有 `refresh_max_tickers`（等於 0，只受 110 秒 deadline 約束），現行版為 27。兩版之間沒有程式碼與 migration 的變更，Web 啟動也不做 migration，所以這次回滾不會碰到資料庫。當時沒有實際使用者：前端 Worker 還沒上線，`/api/` 又要求簽章。

### 執行

兩次都由使用者在 PowerShell 執行（版本未確認），我方只做唯讀核對。指令與 `C6-2` 節相同，只把 `--image` 換成對應的 digest；`DB_HOST`、`DB_USER` 從部署前的 `describe` 讀出後帶入（見下方「發現的缺口」第 1 項）。

| 步驟 | 映像 | revision | 建立 | 啟動實例 → `listening` | TCP 探測 |
|---|---|---|---|---|---|
| 部署前 | `ab1667ccf7f7` | `stock-quote-00001-dx4` | 05:20:48Z | — | — |
| 1 回滾 | `244fd00583bb`（`sha256:44af174b…`） | `stock-quote-00002-wl7` | 07:17:56Z | 07:18:05.57Z → 07:18:08.42Z | 第 1 次成功 |
| 2 換回 | `ab1667ccf7f7`（`sha256:7da85b3a…`） | `stock-quote-00003-qs6` | 07:21:02Z | 07:21:05.24Z → 07:21:09.32Z | 第 1 次成功 |

啟動原因兩次都是 `DEPLOYMENT_ROLLOUT`，不是使用者請求觸發的冷啟動，所以上表的啟動時間**不是 `C7-7` 意義上的冷啟動量測**。

### 核對（每步部署後）

| 項目 | 步驟 1 | 步驟 2 |
|---|---|---|
| `describe --format=export` 與部署前逐行 `diff` | 只有 `image` 與 `client.knative.dev/nonce` 不同 | 同左 |
| 流量 | 100% 到 `00002-wl7`，`latestRevision: true` | 100% 到 `00003-qs6` |
| `Ready`／`ConfigurationsReady`／`RoutesReady` | 皆 True | `Ready` True |
| IAM | 只有 `allUsers` → `run.invoker` | 同左 |
| 不帶簽章的 `/api/portfolio`、`/api/session` | 401、401 | 401、401 |
| 決定性網址 `GET /` | 404（應用程式回應） | 同左 |
| 舊式網址 `/api/portfolio` | 403 | 同左 |
| 日誌 | 啟動 3 行（listening、allowed hosts、allowed origins，值與設定相同）；上述 4 筆請求的狀態碼與 curl 一致 | 同左 |
| 07:15Z 之後 `severity>=ERROR` | 0 筆 | 0 筆 |

兩次在 `listening` 之後都有一筆內容空白的 INFO，查明是 Cloud Audit 的 system event（`cloudaudit.googleapis.com/system_event`，`/Services.ReplaceService`），不是應用程式輸出。

`diff` 沒有變化的部分證實 6 個環境變數與 3 個 secret 參照都沒有被拆開或改動，與 `C6-2` 節的觀察一致。

### secret 版本（本項要求記錄）

| secret | 服務參照 | 現有版本 |
|---|---|---|
| `db-password` | `latest` | 1（enabled，09-16 建立） |
| `proxy-hmac-secret` | `latest` | 1（enabled，09-16 建立） |
| `proxy-hmac-secret-prev` | `latest` | 1（enabled，09-16 建立） |

三把都參照 `latest`，**回滾映像不會讓 secret 回到舊版本**。若 secret 輪替後需要回滾，要另外決定掛哪個版本；這次三把都只有版本 1，這一點**沒有情境可測**。

### 發現的缺口

1. **`C6-2` 節記錄的指令不足以單獨重跑。** `DB_HOST`、`DB_USER` 依 `C1-4` 以「…」遮蔽，這次是從服務的 `describe` 讀回再帶入。往後回滾時，這兩個值從 `gcloud run services describe stock-quote` 或 `finpo-catalog-refresh` 的 `describe` 取得，兩者相同。服務本身若已損壞到無法 `describe`，還有 Job 可以查。
2. **清除政策不是即時的。** repository 設定只保留最近 3 個版本，實際卻有 4 個：`218b4b962c5a` 在 `ab1667c` 建置（09-30 04:30Z）之後兩個多小時仍在。清除政策何時執行沒有查。依政策推定，下一次清除後剩 `b6347e6`、`244fd00`、`ab1667c`，而**每推一次程式變更，可回滾的舊版就少一個**：再推兩次，`244fd00583bb` 就會被刪，屆時只能回滾到當時的前一版。
3. **服務層級有 `run.googleapis.com/maxScale: '20'`**（`metadata.annotations`，不是 revision template）。`C6-2` 的 `describe` 核對只記了 revision 層級的 `maxScale 1`，沒有記到這一項。它不是部署指令指定的，來源與作用沒有查；revision 層級仍是 1，三次部署前後都沒有變。

### 未驗證、有界線的部分

- **只證明了「跑的是舊 digest」，沒有觀察到舊版的行為。** 例如 `refresh_max_tickers` 未設時是否真的不限檔數，要送帶簽章的請求才看得到，這次沒有做（理由同 `C6-2`：不把 `proxy-hmac-secret` 取到本機）。
- **資料庫的向後相容沒有被考驗。** 兩版之間沒有 migration 變更，所以「回滾映像、資料庫維持新 schema」的情境這次不存在。計畫書要求 migration 向後相容；日後若有新 migration，回滾前要另外確認。
- **流量切換期間是否有請求失敗，沒有量。** 部署期間沒有持續送請求。
- **舊 revision 還在**：`00001-dx4`、`00002-wl7` 沒有流量，min=0 不會常駐實例。本次沒有刪除；以 `update-traffic --to-revisions` 切回舊 revision 也是一種回滾方式，但 `D6` 定的方式是重跑 `gcloud run deploy`，這次只測了後者。

## `C6-2` 補記：日誌的內容與保留量（2026-09-30）

**結論：程式自己輸出的日誌不含持股資料與秘密；但平台的請求日誌會把 URL 連同查詢字串記下，而上傳預覽原本把使用者的 Excel 檔名與工作表名稱放在查詢字串。已改為以標頭傳遞並部署（`a1fb03f`，`stock-quote-00004-4v6`）。保留期維持 30 天，是使用者的明確選擇。**

### 盤點：程式輸出

| 來源 | 內容 | 依據 |
|---|---|---|
| 啟動 | `listening on`、allowed hosts、allowed origins 三行 | `web.py` 的 `main()`；兩份白名單是設定值，不是秘密 |
| 未處理的例外 | 只印例外類型、method 與路徑，不印訊息 | `Failsafe` 刻意如此，因為例外訊息可能帶 ticker；路徑中唯一的變數是 job id |
| uvicorn | `access_log=False`、`log_level='warning'` | 同上 |
| Excel 解析、抓價的子程序 | `capture_output=True`，stderr 不會進日誌；抓價子程序另外 `logging.disable(logging.CRITICAL)` | `web_input.py`、`providers.py`、`provider_worker.py` |
| 清單更新（Job） | `Dashboard catalog refreshed.` | 只在 `finpo-catalog-refresh` |

逐行讀原始碼得到的結論，沒有對每條程式路徑觸發過。第三方套件在主程序以 `warnings` 模組直接寫 stderr 的可能性沒有排除。

### 盤點：平台請求日誌（實測）

07:28:37Z 自本機送出不帶簽章的 `POST /api/imports/preview?filename=c6-2-log-probe.xlsx&sheet=probe-sheet`（空 body），回 401。`run.googleapis.com/requests` 的紀錄：

```
requestUrl: https://stock-quote-896096883650.asia-northeast1.run.app/api/imports/preview?filename=c6-2-log-probe.xlsx&sheet=probe-sheet
status: 401
remoteIp: （本機出口 IP）
userAgent: curl/8.21.0
```

- **查詢字串完整記錄，而且在驗簽之前就記**：沒有簽章的請求也會把檔名寫進日誌。
- 前端原本的寫法是 `/api/imports/preview?filename=…&sheet=…`，所以只要從儀表板上傳，檔名就會進日誌。檔名由使用者命名，可能含有人名。
- 程式早就關掉 uvicorn 的 access log，理由註明「會帶出檔名」，但沒考慮到平台自己也記 URL。
- 另一個查詢參數 `market` 只有 `ALL`／`TW`／`US`，維持原狀。
- 附帶觀察：第一次送時沒帶 body，在 Google 前端就回 411，日誌裡沒有這筆，表示沒有抵達服務。
- `remoteIp` 與 `userAgent` 會記錄。`C7-2` 上線後打到服務的是 Worker，這兩欄會變成 Cloudflare 的出口與 Worker 送出的值，**屆時要核對**，看是否仍帶到瀏覽器的資訊。

### 修正（`a1fb03f`）

- **前端**（`app.js`）：上傳檔案時，`api()` 自動帶 `X-Upload-Filename`；工作表以 `X-Upload-Sheet` 傳遞，兩者都經 percent-encoding（標頭只能放 ASCII），session 重試時一起重送。
- **後端**（`web.py`）：改以 `upload_name()` 從標頭讀取並解碼。查詢字串的 `filename` 不再讀取，仍用舊寫法的客戶端會被明確拒絕，不會繼續外洩。
- **取捨：這兩個值離開了 HMAC 的簽章範圍。** canonical string 是 timestamp、method、路徑加查詢字串、body 雜湊，不含一般標頭。要竄改得先攔到一個有效的簽章請求，竄改後也只影響該次上傳的副檔名檢查與工作表選擇，判斷影響很小。
- **`C7-2` 的 Worker 必須原樣轉發 `X-Upload-Filename` 與 `X-Upload-Sheet`**，否則上傳一律回「只接受 .xlsx 檔案」。

測試：新增 Python 測試 3 個、JS 測試 1 個，以 `git stash` 暫時移除 `src/` 的修改確認**修正前都因行為斷言失敗**。其中工作表的測試第一版在修正前也會通過（被 `.xlsx` 檢查先擋下，一樣回 400），改為斷言錯誤訊息「找不到工作表。」後才會失敗。`step-3-evidence.md` 的隔離容器程序：**395 passed、0 skipped、0 failed**；JS（`node --test`）9 passed。**`upload()` 組 URL 的那一行沒有自動化測試**：它位在現有 JS 測試載入範圍（`setDirty()` 之前）之外，由 `C7-4` 從真實前端上傳時確認。

附帶發現、另案處理：Windows 上 `bounded_preview` 的子程序以 cp950 輸出，父程序以 UTF-8 解碼，含中文的 Excel（包括官方範本）在本機都無法預覽。雲端是 Linux，推定不受影響，未實測。新測試以 fixture 直接呼叫 `preview_xlsx`，繞過這個問題。

### 建置與部署

| 項目 | 值 |
|---|---|
| 建置 | run `36684955673`，07:39:24Z 觸發，`build-push` 成功。**這是撤除 `finpo-deploy` 的 `run.admin` 與 `serviceAccountUser` 後的第一次建置**，證實撤除不影響建置（C1 證據 `C1-9` 節已補記） |
| 映像 | `a1fb03ff680d`，`sha256:df4a49e8267d9861fcc646e9b2e4f1cf949b132b242cf2eaa09d6ae55ba327cd`，run log 與 Artifact Registry 相同 |
| 部署 | 使用者在 PowerShell 以 `C6-2` 同一條指令執行，只換 `--image`；`DB_HOST`、`DB_USER` 同 `C6-4` 取自 `describe` |
| revision | `stock-quote-00004-4v6`，07:43:47Z 建立，Ready，100% 流量 |
| `describe` 與 `C6-4` 部署前基準逐行 `diff` | 只有 `image` 與 nonce 不同；IAM 仍只有 `allUsers` → `run.invoker` |
| 啟動 | 07:43:55.95Z 啟動實例（`DEPLOYMENT_ROLLOUT`），07:43:59.10Z `listening`，TCP 探測第 1 次成功；07:40Z 之後 `severity>=ERROR` 0 筆 |
| 不帶簽章的請求（07:47:44Z） | `/api/portfolio`、`/api/session` 401；`/` 404；舊式網址 403 |
| 帶檔名標頭、不帶簽章的上傳（07:47:45Z） | 401；請求日誌的 `requestUrl` 只有 `/api/imports/preview`。以 `"c6-2-hdr-probe"` 全文搜尋該服務近 1 小時的日誌，**0 筆**，平台沒有記錄這兩個標頭的值 |

`finpo-catalog-refresh` 沒有改映像，仍為 `ab1667ccf7f7`：清單更新與這次修改無關，而 `ab1667ccf7f7` 要再推兩次程式變更才會被清除。

**Artifact Registry**：`218b4b962c5a` 在 07:05Z 到 07:40Z 之間被清除政策刪除（`C6-4` 節「發現的缺口」第 2 項）。現有 `b6347e6`、`244fd00`、`ab1667c`、`a1fb03f` 四個，下次清除後應剩後三個。可回滾的舊版因此變成 `ab1667ccf7f7` 與 `244fd00583bb`。

### 保留期

| bucket | 保留期 | 內容 | 處置 |
|---|---|---|---|
| `_Default` | 30 天 | 服務的 stdout／stderr、請求日誌 | **維持 30 天，使用者選定**。30 天內免費，`C7` 驗收期間要查的日誌都還在。這是明確選擇，不是沒有設定 |
| `_Required` | 400 天，已鎖定 | 稽核日誌（admin activity、system event） | 平台固定，無法更改，不含應用程式資料 |

沒有設定 sink 或 exclusion。排除整類請求日誌的做法被否決：狀態碼與延遲在 `C7` 驗收時需要。

### 未驗證、有界線的部分

- **後端確實改讀標頭，只有單元測試證明。** 雲端上要送帶簽章的請求才看得到，這次沒有做（理由同 `C6-2`）。部署核對證明的是「新映像在跑」與「平台不記這兩個標頭」。
- **從真實前端上傳時，日誌裡不再有檔名，未實測**，由 `C7-4` 確認。
- **舊的日誌裡是否已有檔名：已搜尋，只有本節的探針。** 以 `httpRequest.requestUrl:"filename="` 搜尋該服務 30 天內的日誌，只有 07:28:38Z 那一筆 `c6-2-log-probe.xlsx`，它會留到 30 天保留期滿。該服務 30 天內的請求日誌共 20 筆，都是 `C6-2`、`C6-4` 與本節的測試請求。
- **日誌量沒有量測，也沒有設定上限。** 上述 20 筆只說明目前沒有實際流量，不能當作上線後的量。
