# C5 執行紀錄：資料庫與連線

日期：2026-09-20。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C5`。體例沿用 [C1 執行紀錄](cloud-C1-evidence.md)。

**本檔不含任何秘密值。** 本 repository 為 public。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C5-1` 使用 session pooler | ✅ 已實測 | 2026-09-16，紀錄在 [C1 執行紀錄](cloud-C1-evidence.md) 的 `C1-5` 附帶結果 |
| `C5-2` 管理者先建 schema 並授權 | 🟡 部分 | `C1-5` 已以管理者建立兩個 schema 並授權；「runtime 只保留必要權限」的收斂尚未做 |
| `C5-3` 明確設定 TLS | ✅ 完成 | 本檔；**惟 Supabase 憑證鏈尚未實測**，見下 |
| `C5-4` 連線後 `SET` 並核對 | 🟡 已量測、未實作 | 2026-09-16 量測見 `C1-5`；處置與 `C5-3` 同一處實作 |
| `C5-5` 雙 schema fallback | ⬜ 未開始 | |
| `C5-6` 證據資料保存期與容量 | ⬜ 未開始 | |

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

### 未驗證（必須在 `C6-2` 之前補上）

**Supabase session pooler 的憑證是否能被系統信任庫驗證，尚未實測。** 若其憑證由公開 CA 簽發，`sslrootcert=system` 直接成立；若為 Supabase 自簽，則須改為下載其 CA 憑證、隨映像出貨（與 `C2-5` 同樣的做法）並把 `DB_SSLROOTCERT` 指向它。

**本項無法以推論代替**：兩種情況的設定不同，猜錯的表徵是 `C6-2` 首次部署時資料庫連不上。確認方式（任一）：

```
openssl s_client -starttls postgres -connect <pooler-host>:5432 -showcerts </dev/null | openssl x509 -noout -issuer
```

或直接以 `DB_SSLMODE=verify-full DB_SSLROOTCERT=system` 從本機跑一次 `stock-poc db-check --connection-only`——通得過即代表公開 CA 成立。**pooler host 屬識別資訊，不記錄於本檔**（`C1-4`）。

### 連帶影響

`C5-4` 的處置（改為連線建立後執行 `SET`，並以 `SHOW` 核對實際值）與本項落在同一段程式（`Storage.__enter__`）。兩者的原則相同：**設定要明確送出，而且要在事後確認真的生效**。實作 `C5-4` 時應把 `SHOW` 的核對與本項的 `ssl_in_use` 核對寫在一起。

## 下次接續

`C5-3` 完成，`C5-4` 的量測已在 `C1-5` 取得但**實作尚未進行**，兩者在同一段程式，建議接著做。

`C5-2` 的「runtime 只保留必要權限」、`C5-5` 的雙 schema fallback、`C5-6` 的保存期尚未開始。

**進入 `C6-2` 之前必須先完成**：上方「未驗證」一節的 Supabase 憑證鏈確認。
