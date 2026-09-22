# C3 執行紀錄：認證與 session token

日期：2026-09-21。範圍：[第一階段計畫](cloud-phase-1-plan.md) 的 C3。此次修改本機工作樹，沒有部署或讀取真實秘密。

## 進度

| 項目 | 狀態 |
|---|---|
| C3-1 API HMAC 驗簽 | 實作與本機驗證完成 |
| C3-2 無狀態 session | 實作與本機驗證完成 |
| C3-3 前端恢復 | 程式與模擬測試完成；真實 Access 驗收待 C7-3 |
| C3-4 安全失敗回應 | 本機驗證完成 |

## 實作契約

- `web_auth.py` 與 `web.Guard` 保護 `/api`、所有 `/api/*`，包含 GET、session 與未知 API 路由。`/healthz` 保持免驗證，Host／Origin 防護繼續保留。
- Canonical bytes 為 `timestamp|method|raw_path+query|sha256(raw_body)`，維持 URL 編碼與 query 順序，body 不经 JSON 重組。先檢查 ±60 秒，再以 `hmac.compare_digest` 比對 current／previous。重複簽章標頭被拒，body 仍有 5 MiB 限制。
- 環境變數：`PROXY_HMAC_SECRET` 必填、`PROXY_HMAC_SECRET_PREV` 選填，各非空秘密至少 32 bytes。使用隨機秘密；長度驗證不代表熵驗證。Secret Manager 名稱分別為 `proxy-hmac-secret`／`proxy-hmac-secret-prev`，不能把資源名稱當成環境變數名稱。
- 未設開發用驗簽旁路，本機 client 也須簽章。既有未簽章 smoke script 尚不能驗收新介面。`--initialize`／`--refresh-catalog` 不啟動 HTTP，因此不要求 HMAC 秘密。
- Session 格式 `issued.signature`，以 `portfolio-session-v1|issued` 區隔用途，效期 3600 秒。同一組秘密跨程序重啟／revision 可驗證，也接受 previous；不另建 session secret。固定秘密不傳回瀏覽器，session token 不能替代 API 簽章。
- 缺簽章／竄改回應相同的 401 `unauthorized`；Origin 不符為 403 `origin_denied`；session 過期為 403 `session_expired`。不回傳秘密、canonical string 或內部例外內容。
- 前端遇到認證 401／403 後重取 session，再重試一次；Origin 拒絕、409、一般業務錯誤不重試。網路失敗不重送寫入。
- `fetch` 使用 manual redirect。opaque redirect、HTML 或 TypeError 觸發整頁重新載入；CORS 與網路故障無法可靠區分，故 sessionStorage 記錄 60 秒冷卻以防迴圈。
- 有修改時將草稿、匯率與原 revision 暫存同分頁 sessionStorage，登入後恢復並移除暫存，儲存仍使用原 revision，避免覆蓋登入期間其他修改。Excel 檔需重新選取。網路失敗可能在寫入已完成後發生，登入後須確認結果。

## 驗證

| 檢查 | 結果 |
|---|---|
| `python -m pytest tests/test_web.py tests/test_web_auth.py -q` | 77 passed |
| `node --test tests/web_session.test.cjs` | 6 passed |
| `node --check src/stock_quote_fetcher/static/app.js` | 通過 |
| 完整 Python 套件 | 287 passed、46 skipped、2 warnings |

HTTP 測試獨立產生 HMAC，覆蓋 body／query／method／path 竄改、過期、未授權不進入業務方法、雙秘密、session 重啟與輪替。前端測試覆蓋只重試一次、Origin／409 不重試、redirect 保留草稿、網路冷卻與 session 失敗不遞迴。前端採 Node VM 模擬 fetch，並非真實瀏覽器或 Access 實測。

完整套件在 Windows 使用 `.venv/Scripts` 加入 PATH、工作區暫存目錄及 `PYTHONUTF8=1`。兩個既有參數測試的名稱超過 Windows 環境變數長度限制，因此此次執行以 pytest plugin 縮短超過 1000 字元的 nodeid，保留原參數與斷言；未改產品碼或略過這些測試。46 項 skip 為現有整合環境限制，不能宣稱資料庫整合全數通過。

## 尚未驗證

- 沒有部署 Cloud Run／Worker，沒有真實 Google／Access 過期或閒置縮容後自動恢復驗收。C3-3 保留未勾選，整階段完成條件待 C7。
- Worker WebCrypto／Python 線上互通、Origin 轉發與直接 run.app 拒絕，交由 C7-2／C7-3 實測。
- Auth 啟動時快取環境變數。Secret Manager 的更新／停用不會修改存活程序 keys；切換 Worker 前須確認所有服務實例已載入新配置，退休舊秘密也需確保實例不再持有。C1-7 所述自然汰換不是此次已驗證的零中斷保證。
- C4 背景工作／鎖／recovery 未改，C5 剩餘項目仍待完成。
