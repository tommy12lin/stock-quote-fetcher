# C1 執行紀錄：帳號與雲端資源準備

日期：2026-09-16，`C1-6` 於 2026-09-17 補記，同日更正 consent screen 發布狀態（見下）。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C1`。本檔只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public，因此秘密內容、資料庫密碼與完整 DSN 一律不進入本檔；僅記錄資源名稱、版本編號與設定。GCP 專案 ID 與專案編號屬識別碼而非憑證，且 `C6-1` 的 workflow 與映像路徑本來就會公開，故照實記錄。**個人電子郵件位址與 Billing 帳戶 ID 一律不記錄**：兩者對證據價值無幫助，卻會永久留在公開的 git 歷史中。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C1-1` GCP project 與 Billing | ✅ 完成 | |
| `C1-2` API 啟用與 Artifact Registry | 🟡 部分完成 | Artifact Registry 與三個 API 已就緒；WIF 所需的 `iamcredentials`／`sts` 併入 `C1-9` 啟用。repository 命名與計畫書原建議不同，見下 |
| `C1-3` runtime service account | ✅ 完成 | 追加建立 `db-password`；授權在 secret 層而非 version 層，理由見下 |
| `C1-4` Supabase 專案 | ✅ 完成 | Free plan 可指定 `ap-northeast-1`（東京），`D4` 成立 |
| `C1-5` 應用專用非管理角色 | ✅ 完成 | 角色 `finpo_app`；`app`／`dashboard` 兩 schema 皆通過 |
| `C1-6` 入口認證 | ✅ 完成 | team name `khlin`；Free 方案**要求綁卡**；載體改為 Worker，`D5` 不買網域成立 |
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

## C1-6　入口認證

依 `D1` 建立。**前端載體已於 2026-09-17 由 Pages Functions 改為 Workers static assets**（`D2` 修訂，理由見計畫書），因此本項實測的對象是 `workers.dev` 主機名，不是原訂的 `pages.dev`。

### 帳號層設定

| 項目 | 值 |
|---|---|
| Zero Trust team name | `khlin` |
| Team domain | `https://khlin.cloudflareaccess.com` |
| Zero Trust 方案 | Free（50 人以內） |
| Google OAuth Client 所在 GCP 專案 | `finpo-508709` |
| Authorized redirect URI | `https://khlin.cloudflareaccess.com/cdn-cgi/access/callback` |
| identity provider | **Google**（個人帳號，非 Google Workspace） |
| PKCE | **已啟用** |

**team name 與 OAuth consent screen 的 App name 刻意不以專案命名。** 一個 Cloudflare 帳號只有一個 Zero Trust organization，team name 是帳號層唯一的一份；日後每個新前端都是在同一個 team domain 下多加一個 Access application，不會各自擁有 team name。取成 `finpo` 會讓第二個專案登入時被導向 `finpo.cloudflareaccess.com`，語意錯誤。改名並非不可逆，但每個已設定的 identity provider 的 redirect URI 都要同步更新，更新完成前所有 app 登入全滅，故當一次性決定處理。同理，Google 同意頁顯示的 App name 也是帳號層共用。

**已知耦合（刻意延後處理）**：OAuth Client 建在 `finpo-508709` 內，但它服務的是帳號層登入，日後所有前端都會相依於這個 GCP 專案。未另開 identity 專用專案的理由是搬遷成本極低——team name 不變則 redirect URI 不變，搬家只是在新專案建一個相同 redirect URI 的 Client，再把 ID／secret 貼回 Cloudflare 兩個欄位。

### 實測：Zero Trust Free 要求綁定付款方式

**要求。** 訂閱 Free 方案的流程必須填入信用卡，月費 $0。

對 `D5` 的影響：**成本結論不變**。`D5` 的零帳單前提依賴的是「Cloudflare Free 沒有 overage billing，超量是該類請求回錯誤並於 UTC 00:00 重置」，不是「帳號無付款能力」，該前提未受影響，`C1-8` 的 GCP 預算警示亦不需調整。但帳號上現已存在可扣款的付款方式，日後誤啟用任何付費產品——最接近的是 `D2` 提到的 Workers Paid（帳號層 $5／月）——會直接扣款，中間沒有第二道關卡。

### 實測：Access 可保護 `workers.dev`，`D5` 的「不買網域」成立

| 項目 | 值 |
|---|---|
| 受保護主機 | `finpo.drhiromu.workers.dev`（`drhiromu` 為帳號層 workers.dev subdomain） |
| 建立方式 | Worker 的 `Access` 分頁 → `Protect this Worker behind Access` |
| Traffic scope | **`All traffic`**（非 `Previews only`） |
| 涵蓋範圍 | 該 Worker 的所有 hostname，含 `workers.dev` 與 preview URL |
| Access application 數量 | **1**（preview 未另立，由 Worker-level Access 一併涵蓋） |
| Policy 名稱 | 自動產生為 `email domain` |
| Policy 實際規則 | Action `Allow`，Include → **`Emails`** → 單一位址 |
| identity provider | 僅 Google（登入時直接導向 Google，未出現登入方式選單） |

**Worker-level Access 只需一個 application 即涵蓋 preview**，這是 `D2` 改採此載體的主因。Pages 路線需建兩個 application（正式 ＋ `*.` 萬用字元）並手動對齊 policy，preview 網址同樣託管完整前端且公開可讀，漏建等同正門上鎖、側門大開。

### 驗證輸出（2026-09-17）

未登入狀態，自本機對 `https://finpo.drhiromu.workers.dev` 發出：

| 測項 | 結果 | 判讀 |
|---|---|---|
| `GET /` | `302` → `khlin.cloudflareaccess.com/cdn-cgi/access/login/...`，`auth_status: NONE` | 入口生效，且 application 綁定的是該主機名 |
| `GET /` 內容中的佔位標記 | **`0` 次命中**（套用 Access 前為 `1`） | 未登入時 HTML 一個 byte 都沒離開 Cloudflare |
| `GET /app.js` | `302` | 靜態資產同樣受保護 |
| `GET /api/portfolio` | `302`（**不是 404**） | Access 在 Worker 路由之前執行 |
| 無痕視窗登入（白名單帳號） | 直接導向 Google，登入後可見佔位頁，`CF_Authorization` cookie 存在 | 正向通過；未出現選單即確認 One-time PIN 旁路未啟用 |
| 無痕視窗登入（非白名單 Gmail） | 遭 **Cloudflare Access 拒絕頁**擋下 | policy 的 email 白名單生效 |

`/api/portfolio` 那一列值得點名：該路徑目前沒有任何對應程式碼，若 Access 排在 Worker 之後會回 404。它回 302，證明驗證發生在路由之前——`C7-2` 的代理放上去即自動受保護，`D1` 要求的「所有 API 含 GET 都須通過驗證」在邊緣層已先成立一半。

佔位頁僅含一行標記字串，不含任何專案內容，`C7-1` 部署真正的靜態檔時取代之。

**拒絕來源的歸屬**：非白名單帳號是被 **Cloudflare Access 的拒絕頁**擋下，不是被 Google 擋下。這個區別決定本測項有沒有效力：

| 擋下的是誰 | 畫面 | 證明了什麼 |
|---|---|---|
| **Cloudflare Access**（實際發生） | Access 的拒絕頁 | **policy 的 email 白名單生效** |
| Google | `Access blocked: ... has not completed the Google verification process` | 只證明該帳號不在 Google 的 Test users 清單內（consent screen 確為 `Testing`）；Access policy **完全沒被執行到**，反面測試等於白測 |

因此授權層確實由 Access policy 把關，而非借道 Google 的 Test users 清單。這兩者在使用者眼中都只是「進不來」，但只有前者是本專案要的性質——Test users 清單是 Google 的開發階段設施，不是授權機制。

### 五個值得記下的坑

1. **policy 名稱與實際規則不一致。** 內建流程自動產生的 policy 名為 `email domain`，實際規則卻是逐一列舉的 `Emails`。名稱會誤導日後的判斷（看到「domain」以為可以放心加同網域的人，一改就開門），**應改名為 `owner-only`**。
2. **內建 Access 流程的粒度不足。** Worker `Access` 分頁的簡化建立器只提供 `Cloudflare account` 與 `Email domain`，無法選 identity provider。官方文件載明進階設定須於建立後至 Zero Trust 編輯該 application。過渡期務必選 `Cloudflare account`（範圍＝帳號成員＝一人）；若選 `Email domain` 並填個人 Gmail 的網域，等同放行全世界所有 Gmail 使用者，而正向測試對此完全無感。
3. **主控台導覽已改版。** Zero Trust 併入 `dash.cloudflare.com`（`one.dash.cloudflare.com` 轉跳），`Settings → Authentication → Login methods` 改為 **`Integrations → Identity providers`**，`Access` 改為 **`Access controls`**。
4. **Testing 模式是一道隱形的第二閘門。** consent screen 維持 `Testing`（見下節），因此**能通過 Google 那一關的帳號僅限 Test users 清單內者**。日後要放行第二個人時，只在 Access policy 加 email **不夠**，還須把對方加進 Google 的 Test users，否則他會在更前面被 Google 擋下。表徵是「白名單加了卻仍進不去」，極易誤判為 Access 設定問題。查核處為 Google Auth Platform → Audience → Test users。
5. **新版 `Create application` 預設建出 Worker 而非 Pages 專案。** 此即 `D2` 載體修訂的觸發點。誤建後的表徵是主機名為 `<worker>.<subdomain>.workers.dev` 而非 `<project>.pages.dev`，以 `curl -s` 測試舊主機名時錯誤被 `-s` 吞掉、只看到空輸出，容易誤判為「內容不對」。**驗證時應保留 curl 的錯誤輸出**（`-sS`），並先在套用 Access 前量一次基準線，確認標記字串取得 `1`，否則之後的「讀不到」無法區分是 Access 生效還是檔案根本沒部署成功。

### Google OAuth consent screen 的發布狀態

| 項目 | 值 |
|---|---|
| User type | `External`（個人 Gmail 非 Workspace，只有此選項） |
| Publishing status | **`Testing`**，publish 已試過並**被擋下**，決定維持 Testing |
| App name | `khlin-gcp`（帳號層通用命名，不綁專案，理由同 team name，見上） |
| 查核方式 | Google Auth Platform → Audience，**直接查核**（2026-09-17） |

Cloudflare Access 只需 `openid`／`email`／`profile` 三個非敏感 scope，不觸發 Google 的 verification 流程。

**本項曾記錯，於 2026-09-17 更正。** 原先寫「最終狀態為 `In production`」，係由「非白名單 Gmail 通過了 Google 那一關、由 Access 擋下」反推而來。該推論不成立：實際狀態為 `Testing`，而 6c 所用的測試帳號**本身即在 Test users 清單內**（已查核清單確認），因此在 Testing 模式下仍可通過 Google。**記取的教訓是：可由設定頁一眼確認的事實，不應以行為反推代替查核。**

**更正不影響 6c 的結論。** 反面測試證明的是「帳號**通過 Google 那一關之後**，被 Access policy 的 email 白名單擋下」；它得以通過 Google 的原因是 `In production` 還是 Test users，與該結論無關。上方拒絕來源表要區分的是「擋下的是 Google 還是 Access」，實際擋下者為 Access，該區分成立。

**維持 `Testing`。** 單人使用下 Testing 完全夠用，且其 Test users 限制方向為更緊而非更鬆。兩項代價：

1. 七天 refresh token 限制——**實質無影響**。Access 在登入當下完成 OAuth 交換後即改發自己的 `CF_Authorization` cookie，不依賴 Google 的 refresh token 續命。
2. Test users 成為隱形的第二閘門——見上方坑 4，日後放行第二人時必須同步維護兩份清單。

無論 `Testing` 或 `In production`，Google 那一關都只回答「你是誰」，**擋不擋得住一律由 Access policy 的 email 白名單決定**。`D1` 把「人員身分」與「授權」分為兩層，此處即其落地。

### 前瞻性試探：切換至 External production 被擋下（2026-09-17）

**這不是 `C1` 的工作項，也不是 phase 1 的需求。** 計畫書第 2 節已記載本專案的長期目標為開放多人，本次刻意嘗試 publish，目的是及早得知 Google 端對「開放多人」有什麼前置要求，以便回頭修正 `D5`。結論已取得，因此停手，未繼續補填欄位。

依上方指引先在 Branding 頁填妥 App name（`khlin-gcp`）、User support email 與 Developer contact information，**刻意留空 App logo 與三個 App domain URL**（留空的理由：上傳 logo 會強制觸發 Google verification；填入任一 URL 則其網域必須列入 Authorized domains）。隨後於 Audience 頁按 `Publish app`，遭擋下，原文如下：

> Valid app name, support email, homepage url, and privacy policy url are required for switching the app to external production mode. You must enter the missing information to proceed. Please visit the Branding page to finish configuring your app.

**結論：切換至 External production 需要 homepage URL 與 privacy policy URL**，兩者皆非免費欄位可打發。三層阻礙：

| 層 | 內容 |
|---|---|
| 1. 網域擁有權 | URL 須掛在 Authorized domain 下，而 Authorized domain 須是**自有且已於 Google Search Console 驗證**的頂層網域。`workers.dev` 與 `cloudflareaccess.com` 皆非本帳號所有 |
| 2. 公開可達性 | 隱私權政策頁必須公開可讀，但本 Worker 的 Access 為 Traffic scope `All traffic`（見上），**全站含該頁一律 302 導向登入**，Google 與使用者都讀不到 |
| 3. 架構相容性 | 要為單一路徑開例外，須退回 hostname-based Access，而那正是 `D2` 捨棄 Pages 路線的理由。為一個靜態頁放棄「一個開關全包」的性質不划算 |

第 2 層是關鍵：**隱私權政策不能放在這個受 Access 保護的 Worker 上**，必須另找公開載體。

**因此停手，不補填。** 三個理由：phase 1 不需要 production 模式；補填需買網域（約 $10／年）或另接一個平台，phase 1 得不到對應價值；且開放多人時要處理的是他人的持股資料，該份隱私權政策是**實質義務**而非解鎖按鈕用的格式文件，現在貼一頁佔位文字反而會讓日後忘記回頭認真寫。

**回填 `D5`**：計畫書 `D5` 的「第一階段不買網域」不受影響（phase 1 用不到 production 模式），但新增一條已知條件——**開放多人時必須先有自有網域**。詳見計畫書 `D5`。

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
4. 更新 Cloudflare 環境變數為新值，重新部署 Worker
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
| ~~Cloudflare Zero Trust 開通是否要求綁定付款方式~~ | `C1-6` | **已解決**：要求綁卡，月費 $0。`D5` 成本結論不變，理由見 `C1-6` |
| ~~Access 能否保護免費子網域的正式部署~~ | `C1-6` | **已解決**：`workers.dev` 可保護，且 Worker-level Access 一併涵蓋 preview，`D5` 的「不買網域」成立 |
| ~~OAuth consent screen 的發布狀態，及非白名單帳號的拒絕來源~~ | `C1-6` | **已解決**：由 Cloudflare Access 拒絕，policy 已驗證。consent screen 經直接查核為 `Testing`（推翻先前反推的 `In production`），該測試帳號在 Test users 內，不影響 policy 結論 |
| GitHub Actions 能否以 WIF 推送映像 | `C1-9` | `C1` 完成條件之一 |
| runtime SA 是否需要 `roles/logging.logWriter` 才輸出日誌 | `C6-2` | 未查證亦未授予。部署後若 Cloud Run 日誌為空，此為第一個檢查點；寧留待確認項，不憑印象預先多授角色 |
| 預算警示的通知是否確實送達信箱 | `C1-8`／`C7-7` | 常態費用 $0，無法在此刻觸發任一門檻。不得宣稱「可收到通知」 |

## C1 完成條件對照

| 完成條件 | 狀態 |
|---|---|
| 以專用角色從本機連上 Supabase，`check_permissions()` 通過 | ✅ 已達成（`C1-5`；`app` 與 `dashboard` 兩 schema） |
| 以 Google 帳號可通過 Access 登入測試頁 | ✅ 已達成（`C1-6`，含非白名單帳號遭 Access 拒絕的反面驗證） |
| 預算警示已建立且可收到通知 | 🟡 部分達成（`C1-8` 預算已建立；零花費下無法觸發門檻，通知送達併 `C7-7` 驗證） |
| GitHub Actions 以 WIF 推送測試映像，全程無 service account 金鑰 | ⬜ 未達成（`C1-9` 未開始） |

`C1` 尚未完成，不得開始 `C2`／`C5`。

## 下次接續

已完成：`C1-1`–`C1-8`（`C1-2` 除 `iamcredentials`／`sts` 兩個 API 外皆完成，該兩項併入 `C1-9`）。剩餘：**`C1-9`**。

**從空白 session 接手時**：先讀 [cloud-phase-1-plan.md](cloud-phase-1-plan.md) 第 3 節的 `D1`–`D6`（決策與理由）與第 4 節的 `C1`／`C6`（`C1-9` 的完成條件與 `C6-1` 如何使用這些身分），再讀本檔的 `C1-6`、`C1-7` 兩節（入口認證現況與秘密輪替的設計約束）。GCP 專案為 `finpo-508709`（專案編號 `896096883650`），Cloudflare team name 為 `khlin`，前端為 Worker `finpo`（`finpo.drhiromu.workers.dev`）。

主控台操作以**英文介面**名稱記錄，與實際使用的介面一致。

1. **`C1-9` WIF 與 deploy SA**
   - 先啟用 `iamcredentials.googleapis.com` 與 `sts.googleapis.com`。
   - IAM & Admin → Workload Identity Federation：Pool `github` ＋ OIDC provider `github`，`Issuer (URL)` 為 `https://token.actions.githubusercontent.com`。
   - Attribute mapping：`google.subject = assertion.sub`、`attribute.repository = assertion.repository`。
   - **Attribute condition 必填**：`assertion.repository == 'tommy12lin/stock-quote-fetcher'`。留空等同對外公開 GCP 寫入權。
   - deploy SA `stock-quote-deploy`（與 runtime SA 分開），角色：**Artifact Registry Writer**、**Cloud Run Admin**、以及對 `stock-quote-runtime` 的 **Service Account User**。
   - 綁定主體：`principalSet://iam.googleapis.com/projects/896096883650/locations/global/workloadIdentityPools/github/attribute.repository/tommy12lin/stock-quote-fetcher`，角色 **Workload Identity User**。
   - **不得產生 service account 金鑰。**

**待回填本檔的實測結果**：GitHub Actions 能否以 WIF 推送測試映像（`C1-9`）。`C1-6` 已無待補項。

**`C1` 之後的收尾**：`C1-6` 的佔位頁與 canary 標記字串於 `C7-1` 部署真正的靜態檔時取代；`C1-6` 自動產生的 policy 名稱 `email domain` 應改為 `owner-only`，避免名稱與實際規則不符而誤導日後判斷。
