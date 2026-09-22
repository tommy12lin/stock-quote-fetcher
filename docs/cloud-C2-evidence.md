# C2 執行紀錄：HTTP 層與 Cloud Run 執行契約

日期：2026-09-18（依賴驗證與 `web.py` 改寫同日）。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C2`。體例沿用 [C1 執行紀錄](cloud-C1-evidence.md)：只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C2-1` 換成成熟的 WSGI／ASGI 層 | ✅ 完成 | FastAPI＋uvicorn；依賴驗證與改寫皆有證據，新增 23 項 HTTP 層測試 |
| `C2-2` Host／Origin 白名單可設定 | ✅ 完成 | 兩個環境變數；代理標頭一律不信任；對 `C7-2` 追加一條必辦事項 |
| `C2-3` 綁定 `0.0.0.0` 並讀取 `PORT` | ✅ 完成 | `PORT` 環境變數；`--container` 保留為明確開關 |
| `C2-4` Web 啟動配置 | ✅ 完成 | 新增 `stock-web` 進入點與 Dockerfile 的 `web` target，**不靠部署設定覆寫 command** |
| `C2-5` 雲端設定檔進入映像 | ✅ 完成 | 採**選項 A**：`deploy/cloud.toml` 隨 `web` 映像出貨 |
| **健康檢查**（`C2` 完成條件，原無對應項目） | ✅ 完成 | `GET /healthz`，liveness only |
| `C2-6` Python 端是否續供靜態檔 | ✅ 完成 | **決定不提供**，三條靜態路由已移除 |
| `C2-7` `static/`／`migrations/` 可讀取 | ✅ 完成 | 範圍縮為 `migrations/`（`C2-6` 後 Python 不再讀 `static/`）；已驗證 |

## C2-1　依賴驗證（改寫前的前置）

### 選定與理由

採 **FastAPI ＋ uvicorn**。`C2-1` 原文只要求「成熟的 WSGI／ASGI 層」，未指定實作。

| 決定 | 內容 | 理由 |
|---|---|---|
| 版本表示 | `fastapi==0.141.1`、`uvicorn==0.53.0` | 與既有四個依賴一致，一律精確釘版；`uv add` 預設寫出的 `>=` 已改掉 |
| **不採** `uvicorn[standard]` | 僅裝 uvicorn 本體 | extras 會帶入 `httptools`／`uvloop`／`websockets`／`watchfiles` 等編譯型依賴。`D2` 已載明 Worker-level Access **不支援 WebSocket**，本階段前端以 `fetch` 輪詢（static/app.js:86），多裝無對價 |

**已知取捨（記錄而非隱藏）**：本專案的路由全部手寫、回傳已組好的 dict，且 `C3-1` 要求對**原始 body bytes** 計算 HMAC，因此 body 必須以 `Request` 取原始 bytes，不得宣告 Pydantic model 參數——**FastAPI 的型別驗證在本專案用不到**。改用 Starlette 可省下 `pydantic`／`pydantic-core`／`annotated-doc` 等，壓縮後約少 4 MiB、安裝後約少 10.8 MB。兩者皆可行，選 FastAPI 為專案決定，不是技術限制。

### 新增的套件

既有鎖定檔中已有 `anyio`、`h11`、`typing-extensions`（由 httpx／yfinance 帶入），不重複計算。新增九個：

| 套件 | 版本 | 安裝後 | 備註 |
|---|---|---|---|
| `fastapi` | 0.141.1 | 1.7 MB | |
| `starlette` | 1.6.0 | 686 KB | |
| `pydantic` | 2.13.5 | 3.2 MB | |
| `pydantic-core` | 2.46.5 | 5.4 MB | **唯一含二進位擴充者** |
| `uvicorn` | 0.53.0 | 586 KB | |
| `click` | 8.5.0 | 960 KB | uvicorn 的 CLI 相依 |
| `annotated-types` | 0.8.0 | 48 KB | |
| `typing-inspection` | 0.4.4 | 105 KB | |
| `annotated-doc` | 0.0.5 | 5 KB（wheel） | **見下方「留待注意」** |

合計安裝後約 13 MB。

**鎖定檔性質**：`git diff uv.lock` 為**純新增、0 行刪除**，既有套件版本無一變動；`uv lock --check` 通過。

### 驗證結果

前三項在本機（Windows）對 linux 目標進行，第四項起在實際映像內執行。

| # | 測項 | 作法 | 結果 |
|---|---|---|---|
| 1 | 解析是否成立 | `uv add --no-sync`，`requires-python >=3.14.7,<3.15` | ✅ 50 packages，無衝突、無既有套件被迫降版 |
| 2 | 目標平台 wheel 是否齊全 | `uv pip install --dry-run --only-binary :all: --python-platform x86_64-manylinux_2_28 --python-version 3.14` | ✅ 通過。`--only-binary :all:` 表示**只要有任一套件需原始碼編譯即失敗** |
| 3 | 鎖定檔與 pyproject 一致 | `uv sync --frozen --no-dev --no-editable`（與 Dockerfile 同一道指令） | ✅ 通過 |
| 4 | **映像內建置** | `docker build --target builder`（Dockerfile 未改，僅換 pyproject／uv.lock） | ✅ `uv sync --frozen` 44 packages／3.26s |
| 5 | **是否發生原始碼編譯** | `--no-cache --progress=plain` 全量日誌過濾 `Building` | ✅ 僅 `Building stock-quote-fetcher @ file:///app`（本專案自身，走 uv_build）。**無任何第三方 sdist 編譯**；`pydantic-core` 為下載 2.0 MiB wheel |
| 6 | 二進位擴充可載入 | 映像內 `import pydantic_core` | ✅ `_pydantic_core.cpython-314-x86_64-linux-gnu.so`；映像內為 Python 3.14.7 / GCC 14.2.0 |
| 7 | 全套匯入 | 新舊依賴 ＋ `zoneinfo` 兩時區 | ✅ `fastapi 0.141.1`／`uvicorn 0.53.0`／`starlette 1.6.0`／`pydantic 2.13.5` |
| 8 | 公司憑證 | 未掛 `company_ca` secret | ✅ 不需要，建置正常完成 |

第 5 項是本次的關鍵測項：runtime 映像內**沒有編譯器**（architecture.md 第 5 節），任何需要 build 的 sdist 都會使建置失敗。`pydantic-core` 為 Rust 編譯的二進位套件，其 `cp314-cp314-manylinux_2_17_x86_64` wheel 存在是 FastAPI 路線成立的前提；基礎映像為 Debian 13，glibc 遠新於 2.17，相容。

### 附帶取得的 runtime 可用性證據

在 runtime 映像內以 uvicorn 啟動一個最小 ASGI app 並自我發出請求：

| 測項 | 結果 |
|---|---|
| 以 `uid 10001`（`app`，非 root）綁 `0.0.0.0:$PORT` | ✅ 成功 |
| `POST /api/portfolio` 帶 body，讀取原始 bytes | ✅ `200`，正確讀到 14 bytes |
| `Server` 回應標頭 | ⚠️ `uvicorn`（見留待注意） |
| `should_exit` 後執行緒正常結束 | ✅ |

這回答了 `C2-3` 的一半（非 root 綁全介面並讀 `PORT` 可行）與 graceful shutdown 的可行性，但**兩者的正式驗收仍歸 `C2-3`／`C4`**，不得以本測項代替。

### 映像大小與 Artifact Registry 免費額度

`docker image ls` 顯示的大小是本機解壓後的量，**不是計費基準**；Artifact Registry 儲存的是壓縮後的 blob。以 `docker buildx build -o type=oci` 匯出後逐層量測：

| | 基準（現況依賴） | 加 FastAPI＋uvicorn |
|---|---|---|
| 本機未壓縮（`docker image ls`） | 519 MB | 539 MB |
| **壓縮後合計（＝推送量）** | **114.7 MiB** | **119.1 MiB** |

七層中只有一層變動：

```
28.4 MiB ┐
 4.1 MiB ├ 基礎映像 python:3.14.7-slim-trixie，共 44.3 MiB
11.8 MiB ┘   digest 相同，所有 tag 共用，只儲存一份
70.5 → 74.8 MiB   /app/.venv（依賴 ＋ 本專案程式碼）← 唯一會變動的層
```

**FastAPI 那一組的增量為 +4.3 MiB（壓縮後）**，對免費額度的影響可忽略。

但由此量出一個與 `C6-1` 直接相關的數字：程式碼以 `--no-editable` 裝進 venv，因此**只改一行 Python 也會產生一整層新的約 82 MB**（74.8 MiB 換算）。以免費額度 0.5 GB 推算：

| tag 數 | 累積 | 佔免費額度 |
|---|---|---|
| 1 | ~125 MB | 25% |
| 3 | ~289 MB | 58% |
| 5 | ~453 MB | 91% |
| **6** | **~535 MB** | **超出** |

**約第 6 次推送即超出免費額度**，超出後為 $0.10／GB／月。金額本身極小（即使用到 1 GB 也約 $0.05／月），不威脅 `D5` 的 $10 上限，但會使預算報表長期出現非零數字——與 `C1-8` 取消 `Promotions and others` 的效果疊加（見 `C1-9` 附註）。

**因此 `C1-9` 已列的 cleanup policy 不是可有可無的項目**，它決定第 6 次推送之後會不會開始計費。建議設為只保留最近 3 個 tag，穩定在約 289 MB（58%），兼顧回滾餘地。此項歸 `C6-1`。

**同時更正 `C1-9` 的一句推估**：該處寫「Python 映像每個 tag 約 200–400 MB」，係以未壓縮量級估計，偏高。實測第一個 tag 約 125 MB、其後每個增量 tag 約 82 MB。結論方向不變（仍會超出 0.5 GB，仍需 cleanup policy），只是觸線的 tag 數比原估更晚。

**未量測**：以上為本機匯出 OCI layout 的量測，**尚未實際推送到 Artifact Registry**。最終數字以 `C6-1` 首次推送後的 repository 大小為準。

### 留待注意（不影響本次結論）

1. ~~**`Server: uvicorn` 標頭會外洩實作。**~~ **已處理**：改寫時設 `server_header=False`，實跑確認回應中無 `Server` 標頭（見下）。
2. **`annotated-doc 0.0.5` 隨 FastAPI 進入依賴樹。** 版本號仍在 `0.0.x`。本專案對依賴一向保守（architecture.md 第 5 節「減少直接依賴」），此項為**已知並接受**，非疏漏；若日後改採 Starlette 則自然消失。
3. ~~**本次未驗證的是 `C2-1` 的本體。**~~ **已於同日完成**，見下節。
4. ~~**`tests/` 目前沒有任何 HTTP 層測試。**~~ **已處理**：新增 `tests/test_web.py`（23 項），以 Starlette `TestClient` 驅動，未新增任何依賴（`httpx==0.28.1` 早已在鎖定檔內）。
5. **`starlette.testclient` 對 httpx 1.x 的棄用警告。** 執行測試時出現 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`。目前僅為警告，測試全數通過；日後 Starlette 移除相容層時需改用 `httpx2`，屆時是新增依賴而非只改程式。

### 清理

驗證用的四個本機映像（`finpo-deptest:*`）已刪除，未推送至任何 registry。Dockerfile 全程未修改。

## C2-1　改寫結果

`web.py` 全面改寫，`ThreadingHTTPServer`／`BaseHTTPRequestHandler` 移除。所有路由與 `Dashboard` 的呼叫方式維持不變。

### 結構

```
Failsafe( Guard( FastAPI app ) )      ← uvicorn.run() 收到的即為此疊層
```

| 層 | 職責 | 取代了什麼 |
|---|---|---|
| `Failsafe` | 吞掉 Starlette 送出 503 後仍會 re-raise 的例外，只在 stderr 記一行「例外型別 ＋ 方法 ＋ 路徑」 | 原 `except Exception` 的靜默 503 |
| `Guard` | Host／Origin／token 檢查，**在路由之前**執行 | web.py:59-67 的前置檢查 |
| FastAPI app | 路由、例外對應 | `handle_request` 內的 if 串接 |

### 逐項對照

| 既有行為 | 舊位置 | 現在的作法 |
|---|---|---|
| 四個安全標頭 | web.py:52-55 | `respond()` 統一附加；CSP 內容已調整，見下 |
| access log 完全消音 | web.py:43 | `uvicorn.run(access_log=False)`；實跑確認無存取紀錄輸出 |
| `json.dumps(ensure_ascii=False)` | web.py:48 | `respond()` 內自行序列化，不交給框架；測試確認回應為 UTF-8 而非 `\uXXXX` |
| 5 MiB 上傳上限 | web.py:87-97 | `body_bytes()` 邊串流邊累計，**不只信 `Content-Length`**；宣告值與實收長度不符回「上傳未完成。」 |
| 例外三段對應 | web.py:109-114 | `WebError`／`JSONDecodeError`／`UnicodeDecodeError`／`Exception` 四個 exception handler |
| 並行上限 8 | web.py:18 `BoundedSemaphore(8)` | lifespan 內設 `anyio` threadpool `total_tokens = 8`；語意同為**排隊**而非拒絕 |
| 同步 `Dashboard` 不阻塞 event loop | — | 端點為 `async def` 只負責讀 body，所有阻塞呼叫一律經 `run_in_threadpool` |
| `X-Portfolio-Token`／Origin 檢查 | web.py:66 | `Guard`，語意逐字保留 |
| 查詢參數取第一個值 | `parse_qs(...)[0]` | `first()` 以 `getlist()[0]` 實作（Starlette 的 `.get()` 取的是最後一個，會與舊行為不同） |

### 刻意的行為變更（四項，皆非疏漏）

1. **CSP 改為 `default-src 'none'; frame-ancestors 'none'; base-uri 'none'`。** 原策略含 `script-src 'self'`／`style-src` 等，是為了保護此行程回應的 HTML；`C2-6` 決定後本行程只回 JSON 與 xlsx，對應的策略是「全部拒絕」。
2. **移除 `Transfer-Encoding` 的拒絕**（原 web.py:87）。該檢查存在的原因是 `BaseHTTPRequestHandler` **不會解碼 chunked**，放行等於把分塊框架當成 body 讀進來；uvicorn／h11 會正確解碼，該理由消失。真正要守的不變量是 5 MiB，已由串流累計強制。保留此拒絕反而會在 `C7-2` 經 Worker 轉發時造成無謂的 400。
3. **未處理例外改為「回 503 並在 stderr 記一行」**，原本完全不記錄。理由：Cloud Run 上完全不記錄等同不可除錯。**刻意只記型別與路徑，不記例外訊息**——httpx／psycopg 的訊息可能含 ticker，而 ticker 是持股資料，正是 web.py:43 當初消音的原因。已有測試釘住這條（訊息中的 `2330` 不得出現在 stderr）。
4. **未知方法（如 `DELETE`）由 501 改為 404**，與未知路徑同一回應。既不確認路由是否存在，也與既有的「找不到頁面。」訊息一致。

### 刻意未變更（留給對應項目）

| 項目 | 現況 | 歸屬 |
|---|---|---|
| Host 白名單仍寫死 `localhost`／`127.0.0.1`，Origin 仍只接受 `http://` | 原樣保留 | `C2-2` |
| `--container` 才綁 `0.0.0.0`，port 仍來自 `--port` 而非 `PORT` | 原樣保留 | `C2-3` |
| 啟動時的 `pg_try_advisory_lock` 單例租約 | 原樣保留 | `C4` |
| `refresh()` 的 daemon 執行緒與 202 回應 | 原樣保留 | `C4`／`D3` |
| token 仍為每程序隨機產生 | 原樣保留 | `C3-2` |

**因此本次改寫不會讓服務在 Cloud Run 上可用**，它只完成「HTTP 層是成熟的 ASGI 實作」這一件事。

### 驗證

| 測項 | 作法 | 結果 |
|---|---|---|
| 完整測試套件（容器內，專案慣例環境） | `docker build --target test` ＋ `docker run -v <repo>:/work` | ✅ **227 passed、45 skipped、0 failed**（45 項 skip 為需 PostgreSQL 的既有測試） |
| 新增的 HTTP 層測試 | `tests/test_web.py`，Starlette `TestClient` | ✅ 23 項全過 |
| `Server` 標頭 | 本機實跑 uvicorn 後以 httpx 取標頭 | ✅ **不存在**（`server_header=False`） |
| access log | 同上，觀察 stdout／stderr | ✅ 無任何存取紀錄 |
| 四個安全標頭與 `Content-Type` | 同上 | ✅ 皆符合 |
| runtime 映像可載入新模組 | `python -m stock_quote_fetcher.web --help` | ✅ 正常輸出 |

`tests/test_web.py` 涵蓋：token 取得、三條讀取路由的參數傳遞、重複查詢參數取第一個值、xlsx 範本下載、**三條靜態路由確已消失**、未知方法與未知路徑同回應、Host 拒絕、寫入需 Origin ＋ token（三種缺漏各一）、讀取不需 token、`save` 的 body 解析、兩條 refresh 回 202、格式錯誤的 JSON 與無法解碼的 body 各回 400、超量上傳（有／無 `Content-Length` 兩種）回 413、非 `.xlsx` 拒絕、`WebError` 的狀態與 payload 透傳、未預期例外回 503 且不洩漏內容、stderr 只記型別與路徑。

### 未驗證

1. **尚未以真實 `Dashboard` ＋ 資料庫端到端跑過。** 測試以假的 service 物件驅動 HTTP 層；`Dashboard` 本身的行為由既有測試涵蓋，但兩者串起來跑真實請求尚未做，需可連線的 PostgreSQL，併入 `C2-3`／`C7`。
2. **`C2` 的完成條件要求「健康檢查可通過」，但目前沒有任何健康檢查端點**，且 `C2-1`–`C2-7` 沒有一項會產生它。需在 `C2-4` 一併補，或另立項目。**此為計畫書的缺口，不是本次遺漏。**
3. **原有的 15 秒連線讀取逾時（web.py:41 `settimeout(15)`）已消失。** uvicorn 無等價的預設讀取逾時（`timeout_keep_alive` 是 keep-alive 閒置逾時，性質不同）。本機只綁 loopback、雲端前面有 Cloudflare 與 Cloud Run 的逾時，風險有限，但這是一項**被移除而未取代**的防護，應於 `C2-3` 或 `C4` 明確決定要不要補。

## C2-6　Python 端不再供應靜態檔

**決定：不提供。** `/`、`/app.js`、`/style.css` 三條路由已自 `web.py` 移除，Python 端只保留 `/api/`。

理由依計畫書 `C2-6` 與 `D2`：前端由 Cloudflare Workers static assets 供應，Python 回應的 CSP 套不到那份 HTML，留著等於維護一份不生效的安全標頭；而 `run_worker_first` 只列 `/api/*`，靜態檔本來就不會走到後端。

### 後果（已處理與未處理）

| 項目 | 狀態 |
|---|---|
| `README.md` 原本寫「開啟 `http://localhost:8765/`」 | ✅ 已更新 |
| `docs/dashboard-v1.md` 仍描述舊的本機開啟流程 | ⬜ **未更新**，需回頭處理 |
| `compose.web.yaml` 的 `ports: 127.0.0.1:8765:8765` 仍有效（API 仍在該埠） | 無需變更 |
| **本機要開啟頁面目前沒有可用路徑** | ⬜ 未解決，見下 |

**本機開發的缺口**：靜態檔若以另一個 server（例如 `python -m http.server`）供應，其 Origin 會是 `http://localhost:<其他埠>`，而 `Guard` 只接受 `http://localhost:8765`，所有寫入請求會被 403 擋下——讀取可用、儲存不可用。三個選項，尚未決定：

1. 等 `C7-1` 以 `wrangler dev` 同時供應靜態檔與代理（與正式架構一致，但要等到 `C7`）；
2. 在 `C2-2` 讓 Origin 白名單可設定時，順帶允許本機開發用的來源；
3. 加一個僅供開發的 `--serve-static` 旗標把三條路由放回去（與本決定的精神相反，僅為過渡）。

`src/stock_quote_fetcher/static/` 的檔案**保留不動**：它們是前端的來源，`C7-1` 要部署到 Cloudflare 的就是這份。但 Python 端已不再讀取，因此 `C2-7`「確認最終映像內 `static/` 可讀取」的目的已不成立，該項的範圍需重新認定為只剩 `migrations/`（storage.py 仍以套件資源方式載入）。

## C2-2　Host／Origin 白名單與代理標頭的信任範圍

### 先確定這兩個檢查各自在擋什麼

改成可設定之前必須先回答「雲端還需不需要它們」，否則只是把寫死的值換成可設定的值，卻不知道該填什麼。

| 檢查 | 原本的用途 | 雲端還成不成立 |
|---|---|---|
| Host 白名單 | loopback server 的 **DNS rebinding** 防護 | **不成立**。經 Cloudflare ＋ Cloud Run，主機名由 TLS 與平台路由決定，這層不再提供保護 |
| Origin 白名單（非 GET） | 擋跨站寫入（CSRF） | **仍然成立，而且是唯一防線**，見下 |
| `X-Portfolio-Token` | 同上 | 成立，但 `C3-2` 會改為無狀態簽章 |

**為什麼 HMAC 取代不了 Origin 檢查**：`D1` 的簽章證明的是「請求經過我的 Worker」，不是「請求由我的頁面發起」。惡意網站可以這樣繞：

```
evil.example 的 JS
   │  fetch('https://finpo.drhiromu.workers.dev/api/portfolio',
   │        {method:'PUT', credentials:'include', ...})
   ▼
瀏覽器自動帶上 CF_Authorization cookie
   ▼
Cloudflare Access：cookie 有效 → 放行
   ▼
Worker：照常加上 X-Timestamp 與 X-Signature   ← 簽章是「幫惡意請求簽的」
   ▼
Cloud Run：驗簽通過
```

整條鏈上唯一能看出「這不是我的頁面發的」的資訊是 `Origin: https://evil.example`。因此 Origin 白名單必須留在後端，且**不得提供萬用字元**——程式會在啟動時拒絕 `WEB_ALLOWED_ORIGINS=*`。

此處刻意不依賴「`CF_Authorization` 的 SameSite 屬性會不會擋下跨站帶 cookie」。**該屬性未經查證**，而且它由 Cloudflare 決定、可能隨平台變動；把 CSRF 防線押在一個沒驗證過又不歸自己管的性質上並不妥當。若日後查證確定 cookie 不會跨站送出，那是多一層保障，不是拿掉這層的理由。

### 實作

| 環境變數 | 未設定時 | 可接受的值 |
|---|---|---|
| `WEB_ALLOWED_HOSTS` | `localhost:<port>`、`127.0.0.1:<port>` | 逗號分隔的 `host[:port]`；**單獨的 `*` 表示明確停用 Host 檢查** |
| `WEB_ALLOWED_ORIGINS` | `http://localhost:<port>`、`http://127.0.0.1:<port>` | 逗號分隔的絕對來源（`http(s)://host[:port]`，不含路徑）；**不接受 `*`** |

三項設計決定：

1. **未設定即等同原本的 loopback 行為。** 本機模式不需要任何設定，`compose.web.yaml` 不必變更。
2. **格式錯誤在啟動時就失敗**（沿用 `argparse` 的錯誤出口，離開碼 2），不留到請求時才變成難以歸因的 403。空字串、含路徑的 origin、缺少 scheme 的 origin、`*` 用在 origins 上，皆為啟動錯誤。
3. **啟動時印出生效的白名單兩行。** 白名單不是秘密，而 403 是雲端最容易誤判為程式問題的錯誤，印出來可直接對照。

`Host` 允許 `*` 但 `Origin` 不允許，正是上表那個不對稱的結果：前者在雲端已無保護作用，後者是唯一防線。

### 代理標頭的信任範圍：一律不信任

- `X-Forwarded-Host`、`X-Forwarded-Server`、`Forwarded`、`X-Forwarded-Proto`、`X-Forwarded-For` **不參與任何判斷**。`Guard` 只讀 `Host` 與 `Origin`。
- **uvicorn 另設 `proxy_headers=False`**（其預設為 `True`，會依 `X-Forwarded-*` 改寫 client 位址與 scheme）。本服務沒有任何邏輯需要用戶端 IP 或 scheme，而這些標頭任何能連到服務的人都能偽造——Cloud Run 的網址一旦外流，直接對它送請求是做得到的（那時擋下來的是 `C3-1` 的簽章，不是這些標頭）。
- 由此產生的性質：**「請求從哪裡來」完全由 `C3-1` 的 HMAC 簽章認定，不由任何標頭宣稱。** 這與 `D1` 那句「不信任任何可偽造的標頭」是同一件事的落地。

### 對 `C7-2` 追加的必辦事項

> **Worker 轉發請求到 Cloud Run 時，必須原樣帶上瀏覽器的 `Origin` 標頭。**

漏掉的表徵是「讀取正常、所有儲存操作回 403」，而且在單人正向測試中不會顯現——自己的頁面發的請求有 Origin，只有在 Worker 主動剝除或重建 headers 時才會消失。已寫入計畫書的 `C7-2` 項目。

### 驗證

容器內完整套件 **245 passed、45 skipped、0 failed**；`tests/test_web.py` 增至 40 項，本次新增 17 項：

| 測項 | 內容 |
|---|---|
| 預設值 | 未設環境變數時，兩份白名單等同原本的 loopback 集合 |
| 環境覆寫 | 兩個變數皆可替換，逗號與空白容錯 |
| `*` 停用 Host 檢查 | `WEB_ALLOWED_HOSTS=*` 後，任意 Host 的 GET 回 200 |
| **`*` 不放寬 Origin** | Host 為 `*` 時，缺 Origin 的 PUT 仍回 403，且未觸及 service |
| 雲端來源可寫入 | Origin 設為 `https://finpo.drhiromu.workers.dev` 時 PUT 回 200 |
| 啟動期設定錯誤 | 八種無效輸入（空值、`*` 用於 origins、origin 缺 scheme／含路徑、host 帶 scheme 等）皆拋 `ConfigError` |
| **代理標頭無法冒充** | `X-Forwarded-Host`／`X-Forwarded-Server`／`Forwarded` 帶合法值但 `Host` 為 `evil.example` 時，仍回 403 |

### 未處理

1. **Cloud Run 的實際主機名尚不可知**，要到 `C6-2` 首次部署後才產生，因此 `WEB_ALLOWED_HOSTS` 屆時填具體主機名或 `*` 留到 `C6-2` 決定。已在計畫書 `C6-2` 記下這兩個變數必須設定。
2. **本機開啟頁面的缺口仍未解。** 原以為 `C2-2` 可順帶解掉（把開發用的 Origin 加進白名單），實測推導後不成立：前端以相對路徑呼叫 `/api/`（static/app.js:14），靜態檔若由另一個埠供應，請求會打到那個埠而不是 8765，放寬 Origin 並不會讓它連回來。真正的解法仍是前面放一個代理（`C7-1` 的 `wrangler dev`）或加開發專用旗標。

## C2-3　監聽介面與 port

| 來源 | 優先序 | 說明 |
|---|---|---|
| `--port` | 最高 | 明確指定時一律採用，環境變數不覆蓋它 |
| `PORT` 環境變數 | 次之 | 代管平台提供（Cloud Run 為 `8080`）；非 1–65535 的整數於**啟動時**即失敗 |
| `8765` | 最後 | 本機預設，與改寫前相同 |

`--container` **保留為明確開關**，不改為自動偵測。help 文字已更新為「監聽所有介面；本機容器須搭配 loopback published port，代管平台（Cloud Run）則必須指定」——原文只提本機用途，在 Cloud Run 情境下會讀成「不該加」。`web` 映像已把 `--container` 烘進 ENTRYPOINT（見 `C2-4`），因此部署端不需要記得加。

啟動時輸出改為 `listening on <介面>:<port>`，原本印的是 `http://localhost:<port>`——在 Cloud Run 上那是假的。

## C2-4　Web 啟動配置

**決定：加 image target，不靠 Cloud Run 覆寫 command／args。**

計畫書列的兩個選項中，覆寫部署設定的做法會讓「映像本身不會啟動服務」成為常態，任何忘記帶 command 的部署都會起一個 `--help` 就退出的容器。啟動方式屬於映像的性質，應該烘進去。

兩項實作：

1. **`pyproject.toml` 新增 `stock-web = "stock_quote_fetcher.web:main"`**，與既有的 `stock-poc` 同一形式。
2. **Dockerfile 由「單一 runtime 末端」改為「共用 `base` ＋ 兩個末端」**：

```
builder ─┬─ test
         └─ base ─┬─ web      ENTRYPOINT ["/app/.venv/bin/stock-web", "--container"]
                  └─ runtime  ENTRYPOINT ["/app/.venv/bin/stock-poc"]   CMD ["--help"]
```

三個刻意的細節：

- **`web` 排在 `runtime` 之前**，使 `docker build .` 的預設目標仍是 `runtime`。`compose.yaml`／`compose.web.yaml` 都沒有指定 `target`，若把 `web` 放在最後會靜默改變它們建出來的映像。
- **`--container` 放在 ENTRYPOINT 而非 CMD**。`C2-5` 之後要追加 `--config`，若 `--container` 在 CMD 會被整組取代而靜默失去監聽介面，表徵是平台判定啟動失敗、但程式日誌看起來一切正常。
- **兩個末端共用所有層**，只差最後的中繼資料，因此 Artifact Registry 不會因此多存一份依賴層（見上方映像大小一節）。

`C6-1` 建置時應指定 `--target web`。

## 健康檢查（`GET /healthz`）

`C2` 的完成條件要求健康檢查，但 `C2-1`–`C2-7` 沒有任何一項會產生它（已回填計畫書）。本次一併補上。

| 設計決定 | 內容 | 理由 |
|---|---|---|
| **只做 liveness，不查資料庫** | 回 `200 {"status": "ok"}`，不碰 `Dashboard`、不連線、不 migration、不抓行情 | 查資料庫會讓冷啟動更慢、每次探測多佔一條 pooler 連線，且資料庫短暫不穩會讓平台誤殺一個其實還能服務其他請求的實例 |
| **路徑在 `/api/` 之外** | `/healthz` | `D1` 要求「所有 API 含 GET 都須通過驗證」，而 `C3-1` 之後 `/api/` 全部要驗簽；平台探測**無法簽章**。放在 `/api/` 下等於日後必須在驗簽函式裡開例外——例外開在認證程式裡比開在路由表上危險 |
| **豁免 Host／Origin／token 檢查** | `Guard` 對該路徑直接放行 | 探測端無法帶上我們指定的 Host，也不會有 Origin。該路徑回的是常數，沒有東西可保護 |
| **不回報版本或內部狀態** | 只有 `{"status": "ok"}` | `C3-4` 要求不洩漏內部資訊。健康檢查是少數不需驗證即可存取的端點，不該成為情報來源 |

**已知且接受的性質**：任何知道 Cloud Run 網址的人都能得到這個 200。它只證明「有一個服務在跑」，而網址本身已經透露了這件事。`D2` 的 `run_worker_first` 只列 `/api/*`，因此 `/healthz` 不會經由前端 Worker 暴露。

**留給 `C6-2`**：若設定 Cloud Run 的 startup／liveness probe，指向 `/healthz`；**不可**改指向任何 `/api/` 路徑，否則 `C3-1` 上線後探測會全數 401。

## 端到端驗證（`C2` 完成條件）

以一次性 PostgreSQL 容器實跑，參數比照雲端：**不覆寫 command、由環境變數提供 `PORT`**。

```
docker build --target web -t finpo-web:c2 .
docker run -d -e PORT=8080 -e DB_PASSWORD=… -v <config>:/input/config.toml:ro \
           -p 127.0.0.1:8080:8080 finpo-web:c2 --config /input/config.toml
```

啟動輸出：

```
Portfolio dashboard API: listening on 0.0.0.0:8080
Allowed hosts: 127.0.0.1:8080, localhost:8080
Allowed origins: http://127.0.0.1:8080, http://localhost:8080
```

| # | 測項 | 結果 |
|---|---|---|
| 1 | 容器以平台提供的 port 啟動，**未覆寫 command** | ✅ 綁 `0.0.0.0:8080`，`PORT` 生效 |
| 2 | `GET /healthz` | ✅ `200 {"status": "ok"}` |
| 3 | `GET /api/portfolio`（真實資料庫） | ✅ `200`，回傳 `{"fx": null, "rows": [], "revision": 0, …}` |
| 4 | `GET /api/portfolio`，`Host: evil.example` | ✅ `403 拒絕不合法的 Host。` |
| 5 | `GET /healthz`，`Host: probe.internal` | ✅ `200`（豁免生效） |
| 6 | **停止資料庫容器後** `GET /healthz` | ✅ 仍 `200` |
| 7 | 停止資料庫容器後 `GET /api/portfolio` | ✅ `503`，訊息為既有的中文提示 |
| 8 | 容器日誌內容 | ✅ 無任何存取紀錄；唯一的錯誤行為 `unhandled StorageError at GET /api/portfolio`（只有型別與路徑，無訊息內容） |

第 6、7 項是健康檢查語意的直接證據：**資料庫整個停掉，健康檢查仍然通過**，證明它不經過資料庫，因而也不可能觸發 migration；同一時刻 API 回 503，證明兩者確實走不同路徑。這比「讀程式碼確認沒呼叫 migrate()」強，因為它排除的是整條連線路徑。

一次性 PostgreSQL、網路與映像於驗證後全部刪除。

單元測試同步增至 53 項（容器內完整套件 **258 passed、45 skipped、0 failed**），新增 13 項涵蓋：`--port` 優先於 `PORT`、`PORT` 生效、退回 8765、六種無效 `PORT` 於啟動時失敗、健康檢查回應內容、健康檢查在 service 會拋例外時仍回 200 且完全未觸及 service、健康檢查忽略 Host 白名單、健康檢查路徑不在 `/api/` 之下。

## C2-5　雲端設定檔進入映像

**決定：選項 A——設定檔隨映像出貨**（`deploy/cloud.toml` → 映像內 `/app/cloud.toml`），不採 Secret Manager 掛載。

### 先確認的三件事（它們決定了這題的形狀）

1. **所有欄位都有預設值**，且 `doc.get('providers', {})` 這類寫法讓區段本身可省略。因此雲端設定檔只需要放「與預設不同」的值——**檔案很短是正確結果，不是沒寫完**。
2. **但檔案必須存在**：三個 loader 都會呼叫 `_load_document(path)`，讀不到或 TOML 壞掉就是 `ConfigurationError`。「雲端不給設定檔」不改 `config.py` 是做不到的；而讓設定檔可缺席會使 `--config` 打錯路徑由硬錯誤變成靜默套用預設值，**刻意不採**。
3. **設定檔裡不可能有秘密**：`config.py` 對四個區段都做欄位白名單，多一個欄位即報「秘密只能透過環境注入」。所以這份檔案的內容可以公開，Secret Manager 那條路等於**拿保險箱放非機密資料**。

### 未採 Secret Manager 掛載的理由

| 面向 | 選項 A（採用） | Secret Manager 掛檔（未採） |
|---|---|---|
| 審查軌跡 | 在 git 裡，PR 看得到，可寫測試驗證 | 不在 git，正式環境與 repo 會漂移 |
| 回滾 | **原子**：回滾映像即回滾設定 | 映像與設定各自回滾，可能錯配 |
| 失敗模式 | TOML 壞掉在建置／測試階段就抓到 | 實例啟動即失敗、反覆重啟，訊息只有「無法讀取設定檔或 TOML 格式錯誤。」 |
| 額度 | 無 | 吃 Secret Manager 的 6 個作用中版本（已用 3 個） |
| 工具正當性 | — | 內容非機密（見上第 3 點） |

成本面原本唯一的疑慮是「改一個數字要重推約 82 MB」，在 `C6-1` 設 cleanup policy（只留最近數個 tag）後**儲存量固定不再累積**，該疑慮解除。若 `C7-6` 的調參變成很緊的迴圈，升級路徑是替 `scheduler` 的數字加環境變數覆寫（沿用 `DB_*` 的既有機制），屬純增量，設定檔不必改。

### 檔案內容與位置

放在 **`deploy/cloud.toml`，不放進 Python 套件**——它是部署設定而非函式庫資料，映像內路徑因此固定為 `/app/cloud.toml`（放套件裡會變成含 Python 版本的 site-packages 路徑）。`.dockerignore` 加一行放行，只有 `web` stage 會 `COPY`。

實際內容只有 `[instruments] max_age_hours = 168`（其餘全部省略、沿用預設），加上一段說明什麼不該寫進來。

| 區段 | 處置 | 理由 |
|---|---|---|
| `[instruments] max_age_hours` | **168**（預設為 24） | `D3` 在請求內完成更新，而清單被判定過期會讓 `run_job` 先抓整份官方清單，等於在已有 deadline 的請求上再加一次無上限的外部抓取。拉長窗口把它移出關鍵路徑；清單仍可由儀表板手動更新 |
| `[tls]` | **整段省略** | 雲端無公司 CA、無 relaxed provider，預設即為空。寫成空區段反而像是「這裡可以填」 |
| `[providers]` | 省略 | `valuation` 預設 `yahoo`；`comparison` 被 `Dashboard.__init__` 強制清空（dashboard.py:96），因此**雲端服務不呼叫任何需要金鑰的 provider** |
| `[scheduler]` | 省略 | `D3` 的 deadline 與單次檔數待 `C7-2`／`C7-6` 實測回填。現在寫進推測值會看起來像已經決定 |
| `[database]` | 省略 | 走 `DB_*` 環境變數。**Supabase 的 pooler host 與角色名不進 repo**（`C1-4`），這是省略它的理由而非疏漏 |

`COPY` 另外明寫 `--chmod=0644`：`COPY` 預設沿用來源檔權限，Windows 建置得到 `0755`、Linux runner 得到 `0644`，同一份程式在兩處會建出**不同的層**。釘死模式位元讓建置可重現。

### 驗證

| 測項 | 結果 |
|---|---|
| `web` 映像內設定檔 | ✅ `-rw-r--r-- root root /app/cloud.toml`，應用帳號（uid 10001）不可寫 |
| **不掛載任何設定檔、不覆寫 command**，只給 `DB_*` 與 `PORT` | ✅ 正常啟動並服務 |
| `GET /healthz`／`GET /api/portfolio` | ✅ `200`／`200`（真實資料庫，回傳 `{"fx": null, "rows": [], "revision": 0, …}`） |
| `--initialize` | ✅ 建出 schema（同時是 `C2-7` 的證據） |
| **缺 `DB_PASSWORD` 時的行為** | ✅ 啟動即失敗：`資料庫連線設定不完整；請由 DB_PASSWORD 注入密碼。`——**fails closed**，不會拿空密碼去嘗試連線 |
| 映像內是否內建敏感環境變數 | ✅ 0 個（`pass`／`token`／`credential` 皆無命中） |

單元測試新增 `tests/test_deploy_config.py`（6 項）：三個 loader 都吃得下這份檔案、缺 `DB_PASSWORD` 時拋 `ConfigurationError`、**`[tls]` 不存在且三個相關值為空**（防止哪天有人把公司 CA 設定複製過來）、`[database]` 不存在且無任何值含 `supabase`／`pooler`、未設定任何需要金鑰的 provider、`migrations/` 可由套件資源讀取。

## C2-7　映像內資源可讀

`C2-6` 之後 Python 不再讀 `static/`，本項範圍縮為 `migrations/`（storage.py:70 以 `files('stock_quote_fetcher')` 載入）。

兩項證據：容器內 `--initialize` 成功建出 schema（實際套用了 migration）；單元測試直接列舉並讀取套件內的 `.sql` 檔。`static/` 仍隨套件出貨（幾 KB，且是 `C7-1` 要部署到 Cloudflare 的來源），Python 端不再讀取，不構成問題。

## 下次接續

**`C2` 全項完成**（`C2-1`–`C2-7` ＋ 健康檢查），四項完成條件皆有證據。容器內完整測試套件 **264 passed、45 skipped、0 failed**。

下一步為 `C3`（認證與 session token）或 `C4`（工作生命週期）。`C2` 交出去的四條約束：

- **`C3-1` 的 HMAC 必須對原始 body bytes 計算。** `body_bytes()` 回傳的即是未經解析的 bytes，直接取用，不可改由框架解析後重組。
- **`C3-1` 不得把 `/healthz` 納入驗簽範圍。** 平台探測無法簽章；該路徑刻意放在 `/api/` 之外就是為了不必在認證程式裡開例外。
- **`C7-2` 的 Worker 必須原樣轉發 `Origin`**，否則所有寫入回 403（理由見 `C2-2`）。
- **`C3-2` 的 token 仍是每程序隨機**（web.py `main()` 內的 `secrets.token_urlsafe(32)`），冷啟動或換 revision 後舊頁面的寫入仍會 403。

`C4` 的兩項（web.py 啟動時的 advisory lock、`refresh()` 的 daemon 執行緒，dashboard.py:229）未因換框架而改變，`C2` 完成時仍為未處理狀態。

本機開啟頁面的缺口（`C2-6`）同樣仍未解，選項見該節。
