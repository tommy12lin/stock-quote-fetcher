# C1 執行紀錄：帳號與雲端資源準備

日期：2026-09-16。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C1`。本檔只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public，因此秘密內容、資料庫密碼與完整 DSN 一律不進入本檔；僅記錄資源名稱、版本編號與設定。GCP 專案 ID 與專案編號屬識別碼而非憑證，且 `C6-1` 的 workflow 與映像路徑本來就會公開，故照實記錄。**個人電子郵件位址與 Billing 帳戶 ID 一律不記錄**：兩者對證據價值無幫助，卻會永久留在公開的 git 歷史中。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C1-1` GCP project 與 Billing | ✅ 完成 | |
| `C1-2` API 啟用與 Artifact Registry | ✅ 完成 | repository 命名與計畫書原建議不同，見下 |
| `C1-3` runtime service account | ✅ 完成 | 追加建立 `db-password`；授權在 secret 層而非 version 層，理由見下 |
| `C1-4` Supabase 專案 | ✅ 完成 | Free plan 可指定 `ap-northeast-1`（東京），`D4` 成立 |
| `C1-5` 應用專用非管理角色 | ✅ 完成 | 角色 `finpo_app`；`app`／`dashboard` 兩 schema 皆通過 |
| `C1-6` 入口認證 | ⬜ 未開始 | |
| `C1-7` 簽章秘密與輪替方式 | ✅ 完成 | 兩組 secret 已建；輪替設計已定案（見下） |
| `C1-8` 預算警示 | ✅ 完成 | 實填 TWD 300；取消 Credits 的 `Promotions and others`。通知送達未實測，見下 |
| `C1-9` WIF 與 deploy SA | ⬜ 未開始 | 尚缺 `iamcredentials`／`sts` 兩個 API |

## C1-1　專案與 Billing

| 項目 | 值 |
|---|---|
| Project ID | `finpo-508709` |
| Project number | `896096883650` |
| Billing 帳戶 | 已連結（帳戶 ID 不記錄於公開文件，以 `gcloud billing projects describe finpo-508709` 查詢） |
| `billingEnabled` | `true` |
| 帳戶幣別 | **TWD** |
| 專案層級 IAM | `roles/owner` → 專案擁有者個人 Google 帳號，**唯一繫結**（帳號位址不記錄於公開文件） |

部署身分權限確認：目前操作帳號為專案唯一 Owner，`C1` 的所有建立動作不受權限限制。

**幣別對 `C1-8` 的影響**：`D5` 的上限 $10／警示 $5 為美元，但 Billing 預算只接受帳戶幣別，因此 `C1-8` 須以 TWD 填入（約 NT$320，門檻用 50%／100% 百分比表示，避免匯率變動時兩個數字不一致）。

**「專案地區」的查證結果**：GCP **專案本身沒有地區屬性**，Console 上不存在對應設定。`D4` 的 `asia-northeast1` 是在每個資源建立時各自指定，本階段的落點為 Artifact Registry repository（`C1-2`）、Secret Manager 複製位置（`C1-7`）與 Cloud Run 服務（`C6-2`）。App Engine／Firestore 首次建立時要求的不可變更 location 與本專案無關，未設定亦不應設定。

## C1-2　API 與 Artifact Registry

已啟用的 API：

| API | 用途 |
|---|---|
| `run.googleapis.com` | Cloud Run |
| `artifactregistry.googleapis.com` | 映像存放 |
| `secretmanager.googleapis.com` | 簽章秘密 |

依 `D6`，**Cloud Build 維持未啟用**（映像由 GitHub Actions 建置）。`C1-9` 另需 `iamcredentials.googleapis.com` 與 `sts.googleapis.com`，尚未啟用。

Repository（`gcloud artifacts repositories describe finpo --location=asia-northeast1`）：

| 欄位 | 值 |
|---|---|
| name | `projects/finpo-508709/locations/asia-northeast1/repositories/finpo` |
| format | `DOCKER` |
| mode | `STANDARD_REPOSITORY` |
| 加密 | Google-managed key |
| 大小 | 0.000 MB |
| registryUri | `asia-northeast1-docker.pkg.dev/finpo-508709/finpo` |

區域為 `asia-northeast1`，與 `D4` 一致。

**命名決定（與計畫書原建議不同）**：實際建立的 repository 名為 `finpo`，非原先建議的 `stock-quote`。維持此命名，理由是 Artifact Registry 的 repository 可容納多個映像，以**專案**命名 repository、以**服務**命名 image，較能容納日後同一財務系統下的其他服務：

```
asia-northeast1-docker.pkg.dev/finpo-508709/finpo/stock-quote:<tag>
```

`C6-1` 的 workflow 與 `C6-2` 的部署設定一律使用上述路徑。Artifact Registry 不支援 repository 改名，此決定為終局。

## C1-3　runtime service account

| 項目 | 值 |
|---|---|
| SA 名稱 | `stock-quote-runtime`（`@finpo-508709.iam.gserviceaccount.com`） |
| 專案層級角色 | **無**。建立精靈第 2 段「Grant this service account access to project」整段跳過 |
| secret 層授權 | `proxy-hmac-secret`、`proxy-hmac-secret-prev`、`db-password` 各一筆 `roles/secretmanager.secretAccessor` |

**驗證**：以 `gcloud projects get-iam-policy finpo-508709 --flatten="bindings[].members" --filter="bindings.members:stock-quote-runtime"` 查詢，輸出為空，確認該 SA **未持有任何專案層級權限**；三個 secret 各以 `gcloud secrets get-iam-policy` 確認綁定存在。

**為何必須指定 runtime SA**：Cloud Run 未指定 service account 時會改用預設的 Compute Engine SA，而該身分帶專案層級 `Editor`。服務被攻破或依賴被汙染時，影響範圍即整個 GCP 專案，而非單一服務。

**授權層級與計畫書字面不同（secret 層，非 version 層）**：計畫書 `C1-3` 寫「只授予所需 secret version 的讀取權」，實際授在 secret 層。理由是 `C1-7` 的輪替程序以「新增版本」進行，且 `C6-2` 以 `latest` 參照；若權限綁在特定版本上，新增版本的瞬間 runtime 對新版本無權限，服務立即開始失敗——零中斷輪替的設計會被自己的權限設定破壞。secret 層授權的範圍仍僅限該 secret，未擴及其他資源。

**追加 `db-password`（計畫書 `C1-3` 原無此項）**：`C6-2` 規定 `DB_PASSWORD` 由 Secret Manager 注入 Cloud Run，而 Cloud Run 掛載 secret 時該 secret 必須已存在，否則部署失敗。理由與 `C1-7` 先建兩組相同：部署設定不應在需要變更秘密的時刻一併變更。值為 `C1-5` 的 `finpo_app` 密碼。

| Secret | 複製位置 | 用途 |
|---|---|---|
| `proxy-hmac-secret` | `asia-northeast1` | HMAC current |
| `proxy-hmac-secret-prev` | `asia-northeast1` | HMAC previous |
| `db-password` | `asia-northeast1` | Supabase `finpo_app` 密碼 |

Secret Manager 免費額度為 6 個作用中版本，目前使用 3 個。

## C1-4　Supabase 專案

| 項目 | 值 |
|---|---|
| 區域 | `ap-northeast-1`（東京，AWS） |
| Free plan 能否指定該區域 | **可以**；建立專案時於區域下拉直接選取，未被導向 general region |
| 連線模式 | Session pooler（host 屬 `*.pooler.supabase.com`，port 5432） |
| database | `postgres` |

**`D4` 因此成立**：Cloud Run（`asia-northeast1`）與 Supabase（`ap-northeast-1`）同置東京，`C1-2` 已建立的 `finpo` Artifact Registry 不需重建。計畫書第 6 節「Supabase Free plan 能否指定 `ap-northeast-1`」一項解除。

Session pooler 的 host、port 與使用者名稱不記錄於本檔（public repository），以 Supabase 主控台 Connect → Session pooler 取得。**不可改用 Transaction pooler**：兩者 host 相同、僅 port 不同（session 5432／transaction 6543），理由見 `C5-1`。

## C1-5　應用專用非管理角色

| 項目 | 值 |
|---|---|
| 角色名 | `finpo_app` |
| 角色屬性 | `LOGIN`、`NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` |
| schema | `app`（來源，config.py 預設）與 `dashboard`（儀表板，dashboard.py:91 預設） |
| schema 所有權 | 由 `postgres` 保留，未移轉給 `finpo_app` |
| 授權 | database 層 `CONNECT`；兩個 schema 皆 `USAGE` ＋ `CREATE` |

**驗證結果**：以 `finpo_app` 經 session pooler 從本機連線，`stock-poc db-check --connection-only` 於 `app`（設定檔預設）與 `dashboard`（以 `DB_SCHEMA` 覆寫）**兩個 schema 皆通過**，`check_permissions()`（storage.py:122）無異常。連線後 `current_user` 為 `finpo_app`：pooler 的登入名格式為 `<role>.<project-ref>`，但伺服器端身分是角色名本身，因此該函式對 `pg_roles` 的查詢成立。

**兩個 schema 都建立的理由**：`catalog()`（dashboard.py:117）與 `valuation()`（dashboard.py:183）目前會回退查詢來源 schema。`C5-5` 若決定移除此 fallback，`app` 可一併撤除；在此之前兩者都必須存在。

**所有權保留在 `postgres` 的理由**：`C5-2` 要求 runtime 最終只保留必要權限。若以 `CREATE SCHEMA ... AUTHORIZATION finpo_app` 讓角色自持所有權，日後無法撤除其 CREATE。

**密碼**：與建立專案時產生的 `postgres` 管理員密碼為不同值，未共用。`C6-2` 將以 `DB_PASSWORD` 自 Secret Manager 注入 Cloud Run。

### 附帶取得的 `C5-4` 與 `C5-1` 實測結果

以 `finpo_app` 經 session pooler 自本機量測（2026-09-16）。兩項原本都排在 `C5`，因連線已可用而提前取得結論。

#### `C5-4`：startup options 被 pooler 靜默忽略

| 參數 | 不帶 options 的基準值 | 帶 options 連線後的實際值 | 程式期望 |
|---|---|---|---|
| `statement_timeout` | `2min` | `2min` | `10s` |
| `lock_timeout` | `0`（無限） | `0`（無限） | `3s` |
| `timezone` | `UTC` | `UTC` | `UTC` |

兩欄完全相同，即 `Storage.__enter__`（storage.py:88）傳入的 `-c` 參數**完全沒有作用**。`timezone` 看似「符合期望」只是因為 Supabase 預設本來就是 UTC，不構成 options 生效的證據。

**此問題在功能測試中不會顯現**：連線不被拒絕、查詢正常回應，程式自以為有 10 秒單句逾時與 3 秒鎖等待上限，實際上是 2 分鐘與無限等待。`D3` 已定案請求內同步完成，一次卡住的查詢即可吃掉整個 deadline，且失敗表徵會像是抓價緩慢而非資料庫問題。

**本機開發環境不會重現。** 直連 PostgreSQL 時 startup options 正常生效，只有經過 Supavisor 才失效。

`C5-4` 的處置因此確定：改為**連線建立後執行 `SET`**，並於 `SET` 後以 `SHOW` 核對實際值，不可只送出設定就視為成功。storage.py:91 已有連線後執行 `SET search_path` 的位置，為自然的實作點。

#### `C5-1`：session 模式成立

| 步驟 | 結果 | 期望 |
|---|---|---|
| 連線 A `pg_try_advisory_lock` | `True` | `True` |
| A 另外執行數句 SQL 後，連線 B 取同一把鎖 | `False` | `False` |
| A 釋放後 B 再取 | `True` | `True` |

第二步是關鍵：A 取鎖後又執行了其他語句，B 仍取不到，證明 pooler 在 session 模式下維持同一條後端連線，session 層 advisory lock 不會中途失效。

兩個下游推論：`C4-3`（以資料庫層原子認領取代行程內鎖）的前提成立；`C5-4` 改用連線後 `SET` 的做法可行——`SET` 同樣依賴連線的穩定性，若此測不過，該處置也不成立。

## C1-7　簽章秘密與輪替方式

### 已建立

| Secret 名稱 | 版本 | 複製政策 | 角色 |
|---|---|---|---|
| `proxy-hmac-secret` | `1`（enabled） | 使用者管理，`asia-northeast1` | current，實際使用中 |
| `proxy-hmac-secret-prev` | `1`（enabled） | 使用者管理，`asia-northeast1` | previous，目前為未使用的備位值 |

兩組皆以 `gcloud secrets versions list` 確認版本狀態為 enabled、複製位置為 `asia-northeast1`。

**為何一開始就建兩組**：Cloud Run 將 secret 掛為環境變數時該 secret 必須已存在，否則部署失敗。兩組都先建好，輪替時只需異動「秘密值」與「Cloudflare 環境變數」，**不必修改 Cloud Run 部署設定、不需重新部署**。輪替多半發生在懷疑外洩而急於處理的時刻，此時應避免同時變更部署設定。

Secret Manager 免費額度為 6 個作用中版本，本專案常態使用 2 個。

### 交付物一：給 `C3-1` 的設計約束

> 驗簽函式接受**一組**秘密（current ＋ 選用的 previous），逐一以 `hmac.compare_digest()` 比對，全部不符才回 401。previous 不存在或未設定時必須能正常運作。

這是本項目的**核心交付物**，理由如下。

秘密同時存在 GCP Secret Manager 與 Cloudflare 環境變數兩處，**兩者無法原子性地同時更新**。若 `C3-1` 寫成單一秘密比對，輪替必然產生完整中斷：

```
t0  Cloudflare = S1，Cloud Run = S1        正常
t1  更新 Cloudflare → S2
    Cloudflare 以 S2 簽章，Cloud Run 以 S1 驗簽   全部 401
t2  更新 Cloud Run → S2                    恢復
```

`t1`–`t2` 為完全中斷，且**調換順序無效**：先改 Cloud Run 則 Cloudflare 仍以 S1 簽章，同樣全滅。唯一解是過渡期內後端同時接受新舊兩把，而這是**程式結構**決定的，事後無法在不改認證程式的前提下補上。

單把與一組的差異在 `C3-1` 動工當天成本為零；留到必須輪替時才處理，等同在最不應變更認證程式的時刻變更認證程式。計畫書第 6 節標註本項「`C1-7`，最晚 `C3-1`」即為此意。

### 交付物二：輪替程序

順序不可調換。

```
1. 將「目前的值」寫入 proxy-hmac-secret-prev（新增版本）
2. 將「新產生的值」寫入 proxy-hmac-secret（新增版本）
   → 後端此時同時接受新舊兩把
3. 等待 Cloud Run 實例自然汰換
4. 更新 Cloudflare 環境變數為新值，重新部署 Pages
5. 觀察確認無 401
6. 停用 proxy-hmac-secret-prev 的該版本
```

第 1 步必須早於第 2 步。如此任何時刻後端都至少接受 Cloudflare 當下正在使用的那一把，全程零中斷。

**Cloud Run 的配合性質**：以 `latest` 參照的 secret 於**容器啟動時**解析，而 `C6-2` 設定 `min=0`，實例持續汰換，因此新版本會自動生效，第 3 步不需重新部署。此性質待 `C7` 期間實測確認。

**已知代價**：第 2 步至第 6 步之間舊秘密仍然有效。此窗口應於同日內收斂，並確實執行第 6 步停用。這是換取零中斷所付出的代價，需與 `D1` 已接受的「時間窗內重放無法阻擋」一併理解。

**已排定的首次輪替時機**：`D5` 定案真實持股待 `C7` 全數通過後才匯入。驗收期間秘密值會出現在多處操作紀錄中，因此**真實持股匯入前應執行一次輪替**。這是時間點已知的計畫內事件，不是假設情境。

## C1-8　預算警示

| 項目 | 值 |
|---|---|
| Budget 名稱 | `finpo-monthly` |
| Scope | 僅 `finpo-508709`（非帳戶下全部專案） |
| Time range | `Monthly` |
| Services | `All services` |
| Budget type | `Specified amount` |
| Target amount | **TWD 300** |
| Threshold rules | **50% 與 100%**，兩列皆 `Actual`；預設的 90% 一列已刪除 |
| Credits — `Promotions and others` | **取消勾選** |
| Credits — `Discounts` | 維持預設 |
| 通知對象 | `Email alerts to billing admins and users`（本帳戶唯一 Billing Administrator 為專案擁有者本人） |

**金額與 `D5` 的對應**：`D5` 定的上限為 $10，但 Billing 預算只接受帳戶幣別（`C1-1` 確認為 TWD），實填 300。以約 32 TWD/USD 計約當 $9.4，略低於 $10；偏差方向為**提早觸發**，不與 `D5` 衝突，不需調整。50% 門檻約當 $4.7，對應 `D5` 的 $5 警示門檻。

**門檻以百分比而非絕對金額表示**：匯率變動時只需改 Target amount 一個數字，兩個門檻自動跟隨，不會出現兩個數字各自對應不同匯率的情況。

**取消 `Promotions and others` 的理由（計畫書 `C1-8` 未提及此項）**：該選項預設為勾選，會把促銷額度（例如新帳號試用金）自成本中扣除，使預算在額度耗盡前看到的成本恆為 0。而 `D5` 明確定義本預算的用途是**異常偵測門檻**而非可動用預算——失控的抓價迴圈若燒掉的是試用金，正是最需要被通知的情況，卻會被靜默吸收。取消勾選後，預算追蹤的是未扣抵前的實際用量，符合 `D5` 原意。`Discounts` 維持預設，本專案無承諾使用折扣，勾選與否無差異。

**`Forecasted` 未採用**：兩列 threshold 皆用 `Actual`。預測值在月初資料稀疏時波動大，對一個 `D5` 推估常態為 $0 的專案只會產生雜訊。

**未實測：通知是否確實送達。** `C1` 完成條件寫「預算警示已建立且**可收到通知**」，但常態費用為 $0，不會有任何門檻被觸發，「能收到信」在此刻無法產生證據。本項僅能記為**已建立**，通知路徑的實際驗證併入 `C7-7` 的首月帳單檢視。

**預算警示只通知、不停止計費**。超出後費用照樣產生，這正是 `C7-7` 仍須實際核對帳單的理由。

## 尚未取得的實測結果

以下項目在 `C1` 完成前仍為未知，不得在任何文件中宣稱已驗證：

| 項目 | 對應 | 影響 |
|---|---|---|
| Cloudflare Zero Trust 開通是否要求綁定付款方式 | `C1-6` | 影響 `D5` 的預算前提敘述 |
| Access 清空 Subdomain 後能否保護 `finpo.pages.dev` 正式部署 | `C1-6` | 不成立則 `D5` 的「不買網域」須推翻 |
| GitHub Actions 能否以 WIF 推送映像 | `C1-9` | `C1` 完成條件之一 |
| runtime SA 是否需要 `roles/logging.logWriter` 才輸出日誌 | `C6-2` | 未查證亦未授予。部署後若 Cloud Run 日誌為空，此為第一個檢查點；寧留待確認項，不憑印象預先多授角色 |
| 預算警示的通知是否確實送達信箱 | `C1-8`／`C7-7` | 常態費用 $0，無法在此刻觸發任一門檻。不得宣稱「可收到通知」 |

## C1 完成條件對照

| 完成條件 | 狀態 |
|---|---|
| 以專用角色從本機連上 Supabase，`check_permissions()` 通過 | ✅ 已達成（`C1-5`；`app` 與 `dashboard` 兩 schema） |
| 以 Google 帳號可通過 Access 登入測試頁 | ⬜ 未達成（`C1-6` 未開始） |
| 預算警示已建立且可收到通知 | 🟡 部分達成（`C1-8` 預算已建立；零花費下無法觸發門檻，通知送達併 `C7-7` 驗證） |
| GitHub Actions 以 WIF 推送測試映像，全程無 service account 金鑰 | ⬜ 未達成（`C1-9` 未開始） |

`C1` 尚未完成，不得開始 `C2`／`C5`。

## 下次接續

已完成：`C1-1`、`C1-2`、`C1-3`、`C1-4`、`C1-5`、`C1-7`、`C1-8`。剩餘：`C1-6`、`C1-9`。

**建議的下一步順序**：

主控台操作以**英文介面**名稱記錄，與實際使用的介面一致。

1. **`C1-6` 入口認證**（建議優先，內部順序不可顛倒）
   - 排在 `C1-9` 之前的理由：這是 `C1` 剩餘兩項中**唯一可能推翻既有決策**者。若 Access 無法保護 `finpo.pages.dev` 正式部署，`D5` 的「不買網域」即須推翻；`C1-9` 則無此類不確定性，純屬設定量大。早一步知道結論，改動成本較低。
   - Cloudflare Zero Trust 開通取得 team name → GCP 建 OAuth 2.0 Client（`Authorized redirect URI` 為 `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback`）→ 回 Cloudflare 設 Google login method → 建佔位 Pages 專案 → 建 Self-hosted Access application。
   - OAuth consent screen 為 **External**，**必須把自己加入 Test users 或直接 Publish app**，否則登入會被擋。
   - Access application 的 **Subdomain 欄位要清空**（刪掉預設的 `*`），這是 `D5` 不買網域能否成立的關鍵，須實測。

2. **`C1-9` WIF 與 deploy SA**
   - 先啟用 `iamcredentials.googleapis.com` 與 `sts.googleapis.com`。
   - IAM & Admin → Workload Identity Federation：Pool `github` ＋ OIDC provider `github`，`Issuer (URL)` 為 `https://token.actions.githubusercontent.com`。
   - Attribute mapping：`google.subject = assertion.sub`、`attribute.repository = assertion.repository`。
   - **Attribute condition 必填**：`assertion.repository == 'tommy12lin/stock-quote-fetcher'`。留空等同對外公開 GCP 寫入權。
   - deploy SA `stock-quote-deploy`（與 runtime SA 分開），角色：**Artifact Registry Writer**、**Cloud Run Admin**、以及對 `stock-quote-runtime` 的 **Service Account User**。
   - 綁定主體：`principalSet://iam.googleapis.com/projects/896096883650/locations/global/workloadIdentityPools/github/attribute.repository/tommy12lin/stock-quote-fetcher`，角色 **Workload Identity User**。
   - **不得產生 service account 金鑰。**

**待回填本檔的實測結果**：Cloudflare Zero Trust 是否要求綁卡、Access 能否保護 `finpo.pages.dev` 正式部署。
