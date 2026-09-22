# C5 執行紀錄：資料庫與連線

日期：2026-09-20 初版；2026-09-22 完成 C5-1–C5-6。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 C5。本檔保留初版 TLS 驗證歷史，最新結果以下表與「2026-09-22 完成驗證」為準。

**本檔不含任何秘密值。** 本 repository 為 public。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C5-1` 使用 session pooler | ✅ 已實測 | 2026-09-16，紀錄在 [C1 執行紀錄](cloud-C1-evidence.md) 的 `C1-5` 附帶結果 |
| `C5-2` 管理者先建 schema 並授權 | ✅ 完成 | 雲端初始化、14 表 RLS、runtime 權限收斂與反面測試通過 |
| `C5-3` 明確設定 TLS | ✅ 完成 | 官方 CA＋verify-full；實際非 root Web 映像連線通過 |
| `C5-4` 連線後 SET 並核對 | ✅ 完成 | Supabase SHOW 核對、statement／lock timeout 實際觸發 |
| `C5-5` 雙 schema fallback | ✅ 完成 | 儀表板只使用自身 schema；不依赖 app |
| `C5-6` 證據資料保存期與容量 | ✅ 完成 | 30 天策略、dry-run／apply 工具、保留與清理測試、雲端表／索引容量 |

## C5-3　明確設定 TLS

### 問題

`psycopg.connect()` 原本未指定 `sslmode`（storage.py:87），等同沿用 libpq 預設的 **`prefer`**：對方提供 TLS 就加密、不提供就**靜默改送明文**，而且**任何情況下都不驗證伺服器憑證**。本機連 compose 網路內的 PostgreSQL 無所謂；但 `C6-2` 之後 Cloud Run 會經公網連 Supabase，且 `min=0` 表示**每次冷啟動都重送一次密碼**。

### 實作

| 項目 | 內容 |
|---|---|
| 新增設定欄位 | `database.sslmode`（預設 **`verify-full`**）與 `database.sslrootcert`（預設 **`system`**，即作業系統信任庫） |
| 環境變數覆寫 | `DB_SSLMODE`、`DB_SSLROOTCERT`，沿用既有 `DB_*` 機制 |
| **接受的值只有四個** | `disable`／`require`／`verify-ca`／`verify-full` |
| **拒絕 `prefer` 與 `allow`** | 這兩者正是「對方不給 TLS 就改送明文而不出聲」的來源。留著它們等於留一條安靜的降級路徑 |
| 連線後核對 | `sslmode != disable` 時檢查 `conn.pgconn.ssl_in_use`，不成立即關閉連線並報錯 |

**預設值選安全的一邊**：沒有指定的部署得到的是驗證過的 TLS 連線，而**沒有 TLS 的本機資料庫必須明講**（`compose.yaml` 與 `compose.web.yaml` 已加 `DB_SSLMODE=disable`，`config.example.toml` 同步說明）。反過來設計——預設 `prefer`、雲端再改成 `verify-full`——會讓「忘記設定」這件事的後果落在正式環境而不是開發環境。

**連線後核對的理由**：libpq 在 `require`／`verify-*` 下本來就不會建立明文連線，這段檢查照理不會觸發。仍然加上，是因為 `C5-4` 已經有過**設定被靜默忽略**的前例（pooler 收下 startup options 卻不套用）。**送出設定不等於設定生效**，這條在本專案已經被證實過一次。

### 驗證

以自簽 CA ＋ 啟用 TLS 的一次性 PostgreSQL 實測七種組合（容器網路另設別名 `finpo-alias` 指向同一台，用於製造主機名不符）：

| # | 組合 | 結果 | 證明了什麼 |
|---|---|---|---|
| 1 | `disable` | 連線成功，`ssl_in_use=False` | 基準線：未加密確實是未加密 |
| 2 | `require` | 連線成功，`ssl_in_use=True` | 加密生效 |
| 3 | `verify-full` ＋ 正確 CA | 連線成功，`ssl_in_use=True` | 正向通過 |
| 4 | `verify-full` ＋ **無關的 CA** | **拒絕連線** | 憑證未被信任時確實擋下——**這是本項的核心測項** |
| 5 | `verify-full` ＋ **系統信任庫** | **拒絕連線** | 自簽憑證不在公開信任鏈中，符合預期 |
| 6 | `verify-full` ＋ **主機名不符** | **拒絕連線** | 主機名驗證生效 |
| 7 | `verify-ca` ＋ 主機名不符 | 連線成功，`ssl_in_use=True` | 兩個模式確實不同，設定是逐項生效而非被忽略 |

第 4 與第 6 項是關鍵：它們證明 `verify-full` **不是一個被收下卻沒作用的字串**。第 7 項用「同樣的連線在 `verify-ca` 下通得過」反證了第 6 項的拒絕來自主機名驗證，而不是連線本身有問題。

**另確認一個會在 `C6-2` 當天才爆的前提**：`verify-full` ＋ `system` 需要映像內有系統信任庫。`web` 映像的 `/etc/ssl/certs/ca-certificates.crt` 存在且含 **150 個根憑證**，前提成立。

測試憑證與容器於驗證後全部刪除。單元測試同步增加：`sslmode` 的六種無效輸入（含 `prefer`、`allow`、大小寫不符）皆拋 `ConfigurationError`；未指定時預設為 `verify-full`。容器內完整套件 **264 passed、45 skipped、0 failed**。

### 2026-09-20 待驗證事項（已於 09-22 解決，見下方新紀錄）

**Supabase session pooler 的憑證是否能被系統信任庫驗證，尚未實測。** 若其憑證由公開 CA 簽發，`sslrootcert=system` 直接成立；若為 Supabase 自簽，則須改為下載其 CA 憑證、隨映像出貨（與 `C2-5` 同樣的做法）並把 `DB_SSLROOTCERT` 指向它。

**本項無法以推論代替**：兩種情況的設定不同，猜錯的表徵是 `C6-2` 首次部署時資料庫連不上。確認方式（任一）：

```
openssl s_client -starttls postgres -connect <pooler-host>:5432 -showcerts </dev/null | openssl x509 -noout -issuer
```

或直接以 `DB_SSLMODE=verify-full DB_SSLROOTCERT=system` 從本機跑一次 `stock-poc db-check --connection-only`——通得過即代表公開 CA 成立。**pooler host 屬識別資訊，不記錄於本檔**（`C1-4`）。

### 連帶影響

`C5-4` 的處置（改為連線建立後執行 `SET`，並以 `SHOW` 核對實際值）與本項落在同一段程式（`Storage.__enter__`）。兩者的原則相同：**設定要明確送出，而且要在事後確認真的生效**。實作 `C5-4` 時應把 `SHOW` 的核對與本項的 `ssl_in_use` 核對寫在一起。

## 2026-09-20 接續備忘（歷史紀錄；以下項目已於 09-22 完成）

`C5-3` 完成，`C5-4` 的量測已在 `C1-5` 取得但**實作尚未進行**，兩者在同一段程式，建議接著做。

`C5-2` 的「runtime 只保留必要權限」、`C5-5` 的雙 schema fallback、`C5-6` 的保存期尚未開始。

**進入 `C6-2` 之前必須先完成**：上方「未驗證」一節的 Supabase 憑證鏈確認。

## 2026-09-22 完成驗證

### C5-2：管理者初始化與 runtime 權限

透過已登入的 Supabase SQL Editor，以管理者建立 dashboard 的三版 migration、portfolio 與 refresh_jobs。初始化前兩個 schema 都是空的；沒有搬移或刪除 POC 資料，沒有匯入真實持股。管理者保留 schema、table 與 domain 所有權。

`python -m stock_quote_fetcher.cloud_db bootstrap-sql` 由既有 migration 原文及 checksum 產生可重跑 SQL；未知版本或 checksum 不符會整筆回滾，且須先取得 collector advisory lock。重跑不重設 portfolio，管理者與 runtime 不得為同一個角色。

| 權限／操作 | runtime 實測 |
|---|---|
| dashboard schema USAGE | 允許 |
| 13 張業務表 SELECT／INSERT／UPDATE | 允許；以 refresh_jobs 實際寫入、更新與讀取核對，最後強制 rollback |
| schema_migrations SELECT | 允許 |
| CREATE TABLE、DELETE、修改 migration 紀錄 | 全部拒絕，SQLSTATE 42501 |
| TRUNCATE／REFERENCES／TRIGGER | 逐項權限核對皆無 |
| app schema USAGE／CREATE | 已撤除；不再是儀表板依賴 |
| 管理屬性 | 無 superuser／createdb／createrole／replication／bypassrls |
| RLS | 全部 14 張表啟用，runtime_access 政策限定既有 runtime 角色；migration 表政策僅 SELECT |

最初的「不啟用 RLS」選項被自動核准審查拒絕，沒有執行；改為啟用 RLS 的 SQL 後才成功套用。沒有建立新登入角色或重設密碼。隔離資料庫另證明：具 table 讀取權但沒有適用 RLS 政策的角色，看不到 portfolio 資料。

**C6 初始化方式因此調整**：管理者執行 bootstrap SQL，runtime 僅負責正常 API／清單更新；runtime 不可再執行 `web --initialize` 或 migration。C6 仍需建立部署環境的一次性程序及更新官方清單。

### C5-3：官方 CA 與實際交付映像

系統信任庫下驗證失敗，TLS 握手診斷回報 `self-signed certificate in certificate chain`；葉憑證簽發者為 Supabase Intermediate 2021 CA。未以 require 或 disable 繞過驗證。

從主控台 Database Settings 的 [官方 CA 下載連結](https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt) 取得公開憑證，存為 `deploy/supabase-ca.crt`。使用方式符合 [Supabase SSL 文件](https://supabase.com/docs/guides/platform/ssl-enforcement)。

- 檔案 SHA-256：`700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`。
- `.dockerignore` 明確放行，`.gitignore` 只對此公開 CA 加例外；私人憑證仍排除。
- Web image 以 root 擁有、0644 權限放置 `/app/supabase-ca.crt`；`deploy/cloud.toml` 指定 verify-full 與該路徑。
- 實際 `stock-c5:web` 映像以 UID 10001 連線：`tls=true`、`sslmode=verify-full`、CA hash 相符，runtime 權限檢查通過。不是只從工作樹測試。
- 本機 `.env` 密碼不適用此 Supabase 角色；實测使用已存在的 Secret Manager `db-password`，僅由子程序記憶體／環境傳遞，未另存或輸出。連線識別資訊亦未寫入本檔。

### C5-4：session 設定及真正逾時

`Storage.__enter__` 移除 startup options，改為連線後 SET，再逐項 SHOW。支援 PostgreSQL 將毫秒正規化為 s／min 的回應；設定不符即關閉連線，不允許帶著未知設定繼續工作。

| 項目 | Supabase 實測 |
|---|---|
| statement_timeout | 10s |
| lock_timeout | 3s |
| TimeZone | UTC |
| search_path | pg_catalog |
| 測試 statement_timeout=500ms，執行 pg_sleep(2) | 546ms 返回 SQLSTATE 57014 |
| 測試 lock_timeout=200ms，等待另一 session 的 advisory lock | 245ms 返回 SQLSTATE 55P03 |
| 另一 session 嘗試取得仍被持有的 advisory lock | false；session pooler 互斥行為成立 |

耗時含網路往返，不是精準的伺服器計時。短時限只用在獨立測試連線，不修改正式預設值。另補上 TLS 欄位的 configuration_snapshot 白名單，避免抓價建立 run 時因新欄位被拒。

### C5-5：單一 schema

catalog 與 valuation 只查 `self.db`，不再回退來源 schema，也不再要求來源與儀表板 schema 名稱不同。沒有清單時維持既有可恢復的 503 提示，需由 C6 更新清單。雲端已撤除 runtime 對 app 的權限；本機測試涵蓋沒有來源 schema 的查詢路徑。

### C5-6：保存策略、清理與容量

預設保留 **30 天**的已完成／中斷 standalone run 證據；CLI 不接受少於 7 天。第一階段由管理者每週手動先看 dry-run 再決定 apply，不在 HTTP 啟動或請求內自動清理，也未新增排程服務。

以下例外即使超過保存期仍保留：

- 每組 instrument／provider／ticker／currency／market 最新 20 筆快取候選的完整 run；排序與 cached_quotes 一致，含 id 作時間相同時的排序依據。
- 被保留 valuation 引用的 quote 所在 run，遞迴保留引用鏈。
- campaign 所屬 run、仍在 running 或未記錄 ended_at 的 run。
- 最新兩代官方清單、尚未過期的清單。
- queued／running job 與最新一筆 job，避免破壞冷卻判斷；portfolio 完全不清理。

清理使用同一 collector advisory lock，依外鍵順序在單一 transaction 刪除。預設只回傳候選數量；runtime 沒有 DELETE，只有另行授權的管理者可 apply。此策略不是硬性容量上限：冷門標的與引用鏈可能保留超過 30 天，容量仍須持續檢查。DELETE 可供頁面重用，不保證實體檔案立即縮小；未自動執行 VACUUM FULL。

```sh
# 不需秘密：產生給管理者／SQL Editor 執行的初始化 SQL。
python -m stock_quote_fetcher.cloud_db bootstrap-sql --schema dashboard --runtime-role finpo_app

# 由執行環境注入 DB_*；雲端 Web 映像使用 /app/cloud.toml。
python -m stock_quote_fetcher.cloud_db check --config /app/cloud.toml
python -m stock_quote_fetcher.cloud_db capacity --config /app/cloud.toml
python -m stock_quote_fetcher.cloud_db prune --config /app/cloud.toml --days 30

# 僅供管理者連線，先審查 dry-run 與備份，再明確執行。
python -m stock_quote_fetcher.cloud_db prune --config /app/cloud.toml --days 30 --apply
```

**雲端量測（初始化後、尚未載入官方清單／持股／報價）**：

| 項目 | bytes |
|---|---:|
| pg_database_size（整個 database） | 11,521,171 |
| dashboard 表大小合計（含 TOAST 等） | 139,264 |
| dashboard 索引合計 | 262,144 |
| dashboard pg_total_relation_size 合計 | **401,408** |

capacity 工具逐表回傳 table_bytes／index_bytes／total_bytes。這是空業務資料基準，不是正式用量預估，也不等同 Supabase 儀表板顯示的整體磁碟配額用量。雲端 dry-run 結果：runs=0、catalog_generations=0、jobs=0；沒有執行雲端資料刪除。

隔離 PostgreSQL 的清理測試建立 24 筆有報價的 run、1 筆無報價舊 run、1 筆進行中 run、4 代清單與不同狀態 job，驗證 dry-run 不修改資料、僅刪除 3 個可清理 run／2 代清單／2 個 terminal job、保留快取及跨 run 引用，重跑候選數為零。

### 測試與完成界線

- 重建鎖定依賴的 `stock-c5:test`，使用獨立 `stock-c5-test` 網路與一次性 PostgreSQL：**348 passed、0 skipped、2 warnings**。兩個 warning 是既有 Starlette／AnyIO 棄用警告。
- `node --test tests/web_session.test.cjs`：**6 passed**。
- 雲端 runtime 讀寫測試全部 rollback，權限與逾時結果如上。僅初始化空 portfolio，未匯入真實持股。
- C5 全項完成；C4 工作生命週期未改，C6 正式部署與清單更新、C7 端到端／成本／備份驗收仍待處理。
