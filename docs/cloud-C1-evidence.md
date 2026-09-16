# C1 執行紀錄：帳號與雲端資源準備

日期：2026-09-16。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C1`。本檔只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public，因此秘密內容、資料庫密碼與完整 DSN 一律不進入本檔；僅記錄資源名稱、版本編號與設定。GCP 專案 ID 與專案編號屬識別碼而非憑證，且 `C6-1` 的 workflow 與映像路徑本來就會公開，故照實記錄。**個人電子郵件位址與 Billing 帳戶 ID 一律不記錄**：兩者對證據價值無幫助，卻會永久留在公開的 git 歷史中。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C1-1` GCP project 與 Billing | ✅ 完成 | |
| `C1-2` API 啟用與 Artifact Registry | ✅ 完成 | repository 命名與計畫書原建議不同，見下 |
| `C1-3` runtime service account | ⬜ 未開始 | `C1-7` 兩組秘密已齊備，可開始 |
| `C1-4` Supabase 專案 | ⬜ 未開始 | 需實測 Free plan 能否指定 `ap-northeast-1` |
| `C1-5` 應用專用非管理角色 | ⬜ 未開始 | |
| `C1-6` 入口認證 | ⬜ 未開始 | |
| `C1-7` 簽章秘密與輪替方式 | ✅ 完成 | 兩組 secret 已建；輪替設計已定案（見下） |
| `C1-8` 預算警示 | ⬜ 未開始 | |
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

## 尚未取得的實測結果

以下項目在 `C1` 完成前仍為未知，不得在任何文件中宣稱已驗證：

| 項目 | 對應 | 影響 |
|---|---|---|
| Supabase Free plan 能否指定 `ap-northeast-1` | `C1-4` | 不成立則 `D4` 須整組改採新加坡，Artifact Registry 亦須在 `asia-southeast1` 重建 |
| Cloudflare Zero Trust 開通是否要求綁定付款方式 | `C1-6` | 影響 `D5` 的預算前提敘述 |
| Access 清空 Subdomain 後能否保護 `finpo.pages.dev` 正式部署 | `C1-6` | 不成立則 `D5` 的「不買網域」須推翻 |
| runtime 角色能否通過 `check_permissions()` | `C1-5` | Supabase 預設 `postgres` 角色帶 `rolcreaterole`／`rolcreatedb`，必定觸發 `storage.py:122` 的拒絕 |
| GitHub Actions 能否以 WIF 推送映像 | `C1-9` | `C1` 完成條件之一 |

## C1 完成條件對照

| 完成條件 | 狀態 |
|---|---|
| 以專用角色從本機連上 Supabase，`check_permissions()` 通過 | ⬜ 未達成（`C1-4`／`C1-5` 未開始） |
| 以 Google 帳號可通過 Access 登入測試頁 | ⬜ 未達成（`C1-6` 未開始） |
| 預算警示已建立且可收到通知 | ⬜ 未達成（`C1-8` 未開始） |
| GitHub Actions 以 WIF 推送測試映像，全程無 service account 金鑰 | ⬜ 未達成（`C1-9` 未開始） |

`C1` 尚未完成，不得開始 `C2`／`C5`。

## 下次接續

已完成：`C1-1`、`C1-2`、`C1-7`。

**建議的下一步順序**：

1. **`C1-3` runtime service account**（GCP Console）
   - IAM 與管理 → 服務帳戶 → 建立 `stock-quote-runtime`。
   - **第 2 步「授予專案存取權」整步跳過，不選任何角色。** 不指定 SA 時 Cloud Run 會改用帶 Editor 的預設 Compute SA，這正是本項要避免的。
   - 授權方式：分別進入 Secret Manager 的 `proxy-hmac-secret` 與 `proxy-hmac-secret-prev`，在各自的「權限」分頁加入該 SA，角色為 Secret Manager 密鑰存取者。**兩組都要授，且不可從 IAM 頁面授予專案層級權限。**
   - 驗證：`gcloud projects get-iam-policy finpo-508709 --format=json` 查不到該 SA 才正確；密鑰層級以 `gcloud secrets get-iam-policy <name>` 查。

2. **`C1-8` 預算警示**（GCP Console → 帳單 → 預算與快訊）
   - 範圍**只勾 `finpo-508709`**；金額以 **TWD 約 320** 填入；門檻用 **50%／100% 百分比**，不要填兩個絕對金額。

3. **`C1-9` WIF 與 deploy SA**
   - 先啟用 `iamcredentials.googleapis.com` 與 `sts.googleapis.com`。
   - Workload Identity Pool `github` ＋ OIDC provider `github`，issuer `https://token.actions.githubusercontent.com`。
   - 屬性對應 `google.subject = assertion.sub`、`attribute.repository = assertion.repository`。
   - **屬性條件必填**：`assertion.repository == 'tommy12lin/stock-quote-fetcher'`。留空等同對外公開 GCP 寫入權。
   - deploy SA `stock-quote-deploy`（與 runtime SA 分開），角色：Artifact Registry 寫入者、Cloud Run 管理員、以及對 `stock-quote-runtime` 的服務帳戶使用者。
   - 綁定主體：`principalSet://iam.googleapis.com/projects/896096883650/locations/global/workloadIdentityPools/github/attribute.repository/tommy12lin/stock-quote-fetcher`，角色 Workload Identity 使用者。
   - **不得產生 service account 金鑰。**

4. **`C1-4`／`C1-5` Supabase**（可與上述並行）
   - 建立專案時**先確認 Free plan 的區域下拉能否選 `ap-northeast-1`（東京）**。不能選則依 `D4` 整組改採新加坡，Artifact Registry 亦須在 `asia-southeast1` 重建。
   - Connect → **Session pooler**（不是 Transaction pooler，理由見 `C5-1`），逐欄抄 host／port／dbname，不自行拼 host。
   - 以 SQL Editor 建立非管理角色（`NOSUPERUSER NOCREATEDB NOCREATEROLE`）與 schema，並授 CONNECT／USAGE／CREATE。pooler 連線的使用者名稱格式為 `<role>.<project-ref>`。

5. **`C1-6` 入口認證**（最後做，內部順序不可顛倒）
   - Cloudflare Zero Trust 開通取得 team name → GCP 建 OAuth Client（redirect URI 為 `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback`）→ 回 Cloudflare 設 Google login method → 建佔位 Pages 專案 → 建 Access application。
   - OAuth 同意畫面為 External，**必須把自己加入測試使用者或直接發布應用程式**，否則登入會被擋。
   - Access application 的 **Subdomain 欄位要清空**（刪掉預設的 `*`），這是 `D5` 不買網域能否成立的關鍵，須實測。

**待回填本檔的實測結果**：Supabase 東京區可否選擇、Cloudflare Zero Trust 是否要求綁卡、Access 能否保護 `finpo.pages.dev` 正式部署。
