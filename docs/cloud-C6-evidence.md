# C6 執行紀錄：建置、部署與一次性初始化

日期：2026-09-23 開檔（`C6-1`）。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C6`。本檔只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public，workflow 的執行紀錄亦公開可見。映像路徑、GCP 專案 ID 與專案編號屬識別碼而非憑證，與 `C1` 執行紀錄一致照實記錄。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C6-1` GitHub Actions 建置與推送 | ✅ 完成 | run `35806642267`，digest 已取得並經 GCP 端獨立核對 |
| `C6-2` 部署設定 | ⬜ 未開始 | **仍被 `C4-1` 的兩個數值擋住**，見下 |
| `C6-3` 一次性初始化 | ⬜ 未開始 | |
| `C6-4` digest 與回滾紀錄 | 🟡 部分 | digest 產出機制已建立（本項），回滾實測待 `C7-7` |

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
