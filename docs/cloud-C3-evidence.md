# C3 執行紀錄：認證與 session token

日期：2026-09-21，2026-09-22 補記重跑驗證與完成條件拆分。範圍：[第一階段計畫](cloud-phase-1-plan.md) 的 C3。此次修改本機工作樹，沒有部署或讀取真實秘密。

## 進度

| 項目 | 狀態 |
|---|---|
| C3-1 API HMAC 驗簽 | 實作與本機驗證完成 |
| C3-2 無狀態 session | 實作與本機驗證完成 |
| C3-3 前端恢復 | 程式與模擬測試完成，2026-09-22 勾選；真實 Access／縮容驗收併入 C7-3 |
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

## 2026-09-22：重跑驗證與完成條件拆分

重跑本機驗證，結果與 09-21 一致：

| 檢查 | 結果 |
|---|---|
| `uv run pytest tests/test_web.py tests/test_web_auth.py -q` | 77 passed |
| `node --test tests/web_session.test.cjs` | 6 passed |
| `node --check src/stock_quote_fetcher/static/app.js` | 通過 |

另逐段審了 C3-3 的實作，對照計畫要求的三件事，沒有找到缺陷：

- 401／403 重取後只重試一次：`app.js` 的 `api()` 以 `retry` 參數控制，重試時傳入 `false`；`/api/session` 自身排除在重試條件外，session 端點失敗不會遞迴。
- 跨網域轉址偵測：`fetch` 以 `redirect:'manual'` 發出，`opaqueredirect`、`redirected` 與 `text/html` 三種跡象都導向整頁重載；`TypeError` 亦然，因為 `fetch` 無法區分 CORS 轉址與斷網。
- 不實作登入表單：前端只重載，登入流程完全交給 Access。

三處容易寫錯但實際是對的地方，記下來以免日後被誤改：GET 不帶 `X-Portfolio-Token`（GET 由 Worker 的 HMAC 驗，session token 只擋寫入，兩者不互相取代）；驗簽對 `raw_path` 加原始 query 計算，不重組 JSON；`Guard` 讀掉 body 後以 `replay()` 補回給下游，否則路由讀不到內容。

**完成條件已拆為程式面與雲端面**（計畫 C3 段落同步更新）。原完成條件把「程式是否寫對」與「雲端是否真的會恢復」寫在同一句，其中「瀏覽器閒置至服務縮容後再操作」需要真實的 Cloud Run 縮容與 Access session 過期，本機造不出來，而 Worker 尚未撰寫（C7-2）、服務尚未部署（C6）。這使 C3-3 在程式早已交付後仍掛著未勾選，看起來像有未寫的程式。拆開後程式面結清、雲端面歸 C7-3，並在 C7-3 項目內明文寫上承接關係，避免日後因 C3-3 已勾選而略過該驗收。

拆分只改驗收口徑，沒有降低要求：C3 的雲端完成條件仍然必須通過，只是記在 C7-3。此次未修改任何產品程式。

## 尚未驗證

- 沒有部署 Cloud Run／Worker，沒有真實 Google／Access 過期或閒置縮容後自動恢復驗收。C3-3 已於 2026-09-22 勾選，但**勾選只代表程式交付**；C3 的雲端完成條件仍待 C7-3，理由見上節。
- Worker WebCrypto／Python 線上互通、Origin 轉發與直接 run.app 拒絕，交由 C7-2／C7-3 實測。
- Auth 啟動時快取環境變數。Secret Manager 的更新／停用不會修改存活程序 keys；切換 Worker 前須確認所有服務實例已載入新配置，退休舊秘密也需確保實例不再持有。C1-7 所述自然汰換不是此次已驗證的零中斷保證。
- C4 背景工作／鎖／recovery 未改，C5 剩餘項目仍待完成。
