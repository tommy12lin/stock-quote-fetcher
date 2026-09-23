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
| cleanup policy 的**實際刪除行為** | policy 已設定並由 API 回讀確認，但目前只有 1 個版本，未達 3 個上限，**刪除從未實際發生過**。累積到第 4 個 tag 時才會首次驗證 |
| 建置的**可重現性** | 同一 commit 重跑是否產生相同 digest 未測。Dockerfile 已為此做過處置（基礎映像釘 digest、`COPY --chmod` 釘死權限位元），但未實際驗證 |

## 交接給 `C6-2`

**`C6-2` 仍不得執行。** 計畫書的硬性前提未解除：`deploy/cloud.toml` 的 `[scheduler]` 仍未回填 `refresh_deadline_seconds` 與 `refresh_max_tickers`。現況：

| 數值 | 狀態 |
|---|---|
| `refresh_deadline_seconds` | 硬上界 **125 秒**已由 `C7-2` 量出（見 [C7 證據](cloud-C7-evidence.md)），但**仍須扣除冷啟動**。本項交付的映像使冷啟動終於可量——**這是 `C6-1` 解開的東西** |
| `refresh_max_tickers` | 完全無依據，待 `C7-6` 的實際抓價耗時 |

`C6-2` 另須注意：request timeout 必須大於 `refresh_deadline_seconds`，但**無論設多大都無法超過 125 秒的邊緣上限**（`C7-2` 已證實限制在邊緣不在平台）。
