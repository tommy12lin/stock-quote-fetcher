# C7 執行紀錄：Cloudflare 前端與端到端驗收

日期：2026-09-22 開檔。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C7`。本檔只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public。Cloud Run 服務網址含 GCP 專案編號，與 `C1` 執行紀錄一致視為識別碼而非憑證，照實記錄。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C7-1` Workers static assets 部署 | ⬜ 未開始 | **2026-10-01 補記**：部署前準備已核對，wrangler 固定為 `4.145.0`，登入有效，`finpo` 自 09-17 以來沒有再部署過，見「`C7-1` 部署前準備」節。~~尚未部署~~ **同日補記：🟡 已部署**（`ca71f76e`），canary 退場，Access 在新 Worker 與 preview URL 上重新證明有效，安全標頭生效。~~Access 下的 125 秒確認未做。~~見「`C7-1`／`C7-2` 首次分段部署」節。**10-02 補記**：Access 下的上限仍是 125 秒（preview URL 上 120 秒通過、130 秒於 125.4 秒被切），本項要求的都有證據了，~~是否勾選待使用者決定~~ **同日使用者決定勾選，✅ 完成**。見「`C7-1`／`C7-2` 收尾」節 |
| `C7-2` `/api/*` 代理與逾時對齊 | 🟡 部分完成 | **逾時量測已完成**（本檔）；代理實作、`run_worker_first`、HMAC 跨語言互通與 `Origin` 轉發待 `C6` 部署後。**2026-09-30 補記**：代理程式已在本機完成，只有 Node 測試，未部署，見「`C7-2` 代理程式（本機）」節。**2026-10-01 補記：已部署**，雲端正向驗簽、`Origin` 與上傳標頭轉發、`run_worker_first`、缺 secret 時不轉發都已實測；請求日誌的 `remoteIp` 是 Cloudflare 出口、`userAgent` 為空。~~524 轉換與三層逾時對齊未做。~~見「`C7-1`／`C7-2` 首次分段部署」節。**10-02 補記**：524 在雲端轉成 504 `upstream_timeout`，前端顯示 Worker 的訊息、不重新整理；三層逾時的對齊已逐層寫出。本項要求的都有證據了，~~是否勾選待使用者決定~~ **同日使用者決定勾選，✅ 完成**。見「`C7-1`／`C7-2` 收尾」節 |
| `C7-3` 入口驗證與繞過測試 | ~~⬜ 未開始~~ ✅ 10-03 完成（使用者決定勾選） | 承接 `C3-3` 的雲端驗收。五項見「`C7-3` 入口驗證」節 |
| `C7-4` 功能驗收 | 🟡 進行中 | 10-01 開始，第 0 項通過，見「`C7-4` 功能驗收」節 |
| `C7-5` 持久性驗收 | ⬜ 未開始 | 承接 `C4` 的雲端完成條件。**2026-10-03 補記**：程序已寫在計畫書 `C7-5` 項下，~~尚未執行~~。**同日 🟡 進行中**：`C7-5-2`、`C7-5-3` 已執行，rollout 與刪除 revision 都沒有中斷進行中的更新，見「`C7-5`」節。**同日 ✅ 完成（使用者決定勾選）**，四項都已執行；界線是容器真的被終止的路徑在雲端未實測 |
| `C7-6` 外部來源驗收 | 🟡 進行中 | **R1、R4 已完成**，見下文。**2026-09-29 R2 已執行**：GCP 11/11 抓價成功，台股 6 檔為當日一般時段，但 MIS 嚴格逐秒對齊為 0/6，價格正確性證據不足；~~R3、R5 未執行~~。**同日晚上 R3、R5 已執行**：R3 美股 5 檔取得當日一般時段成交（價格正確性證據不足），台股 6 檔等於 09-29 官方收盤；R5 截斷收尾正確，`c` 為 3.967（含暖機）／2.947（不含第 1 批）秒／檔，**`refresh_max_tickers` 待使用者決定**。五場都沒有 429。尚待收尾（清單更新、`reset`、`purge`、刪除 Job）。**2026-10-03 補記：✅ 完成（使用者決定勾選）**。收尾已於 09-30 完成，`refresh_max_tickers` 取 27。盤中價格正確性（台股、美股）仍為證據不足，界線見計畫書 `C7-6` |
| `C7-7` 營運驗收 | 🟡 部分 | **冷啟動已提前量測**（本檔），其餘（匯出還原、回滾、計費、抓價耗時）未開始；含 `C1-8` 的預算通知送達。**2026-10-05 補記**：執行程序已寫在計畫書 `C7-7` 項下，拆成 `C7-7-1`–`C7-7-6`，~~尚未執行~~。**同日 `C7-7-1` 完成**：真實路徑的冷啟動為 2.967–4.175 秒（n=18），超過算式所用的 3.5 秒；110 秒仍成立，`cloud.toml` 的註解過時。見「`C7-7-1`」節。**同日 `C7-7-2` 完成**：27 檔的更新 8 次，耗時 90.5–110.3 秒，1 次被截短。見「`C7-7-2`」節。**同日 `C7-7-3` 的查詢部分完成**：database 38.5 MB（7.7%），閒置連線 12／60；~~Supabase 儀表板三項待讀~~ 儀表板已讀出，Pool Size 15 是實際的連線上限。見「`C7-7-3`」節 |
| `C7-8` Worker 驗 Access JWT | ~~⬜ 未開始~~ ✅ 10-01 完成（使用者決定勾選） | 2026-09-30 新立，見計畫書。**2026-10-01 補記**：排在 `C7-1`／`C7-2` 首次部署之後、`C7-4` 之前，列為第一階段完成條件，另須核對 `email` claim。**同日下午補記**：已設計（見計畫書）；第 0 步確認 Worker 收得到 `Cf-Access-Jwt-Assertion`，但 tail 遮蔽了值，見「`C7-8` 第 0 步」節；第 3 步（jose 實作與 Node 測試）已完成，~~未部署~~，見同節。**同日部署 `474e5c4f`，第 5 步正向、第 6 步 preview URL 反面測試通過**，見同節 |

## C7-1　部署前準備（2026-10-01）

本節只記錄部署前的工具與帳號核對，**沒有對 `finpo` 做任何部署**，以下指令全為唯讀。

### wrangler 版本

| 項目 | 結果 |
|---|---|
| 核對前的狀態 | 這台機器沒有可執行的 wrangler：沒有全域安裝、全域 npm 套件為空、repo 內沒有 `package.json`，`npx --no-install wrangler` 因快取中沒有套件而取消 |
| 選定版本 | **`wrangler@4.145.0`**（使用者決定固定一個最新穩定版） |
| 選定依據 | `npm view wrangler dist-tags` 的 `latest` 為 `4.145.0`（`legacy` 為 `3.114.17`）；發布時間 2026-09-30T14:20Z，即核對前一天 |
| 執行方式 | `npx --yes wrangler@4.145.0 …`，以 `WRANGLER_SEND_METRICS=false` 關閉遙測；`--version` 回 `4.145.0` |
| Node | `v24.21.0` |

「穩定」的依據只有 npm 的 `latest` tag，此外沒有核對。版本只固定在指令裡，repo 沒有 `package.json` 或 lockfile 記錄它，之後的部署指令要沿用同一版，否則 `wrangler.jsonc` 的 `compatibility_date` 核對無法重現。`compatibility_date` 尚未以此版核對，排在首次部署時做。

### 登入與帳號

`npx --yes wrangler@4.145.0 whoami`：

| 項目 | 結果 |
|---|---|
| 登入方式 | OAuth token，存於 `%APPDATA%\xdg.config\.wrangler\config\default.toml`。檔案修改時間為 09-22 16:36，與本檔 `C7-2` 逾時量測同日，推定是當時 `wrangler login` 留下的；檔案內容未開啟 |
| 帳號 | 帳號擁有者的個人 Gmail，Account ID `d6c5b629…c694`。repo 為 public，email 與完整 Account ID 不寫入本檔 |
| `CLOUDFLARE_API_TOKEN` | 未設定，所以用的確實是上述 OAuth token |
| 部署所需 scope | 有 `workers_scripts (write)`、`workers (write)` |
| 警告 | wrangler 提示缺 `k2.read`／`k2.write` 兩個 scope，建議重跑 `wrangler login`。推定與部署 Worker、設定 secret 無關，**未實測**；首次部署若出現權限錯誤，先重跑 `wrangler login` |

### `finpo` 所在帳號與現況

`npx --yes wrangler@4.145.0 deployments list --name finpo`（在 repo 外的目錄執行，不讀 `wrangler.jsonc`）：

| 項目 | 結果 |
|---|---|
| 部署筆數 | **1** |
| 建立時間 | 2026-09-17T03:50:23Z，來源 `Upload` |
| 版本 | `570ea2b7-ae77-44c6-930d-63ba6ab42f04`，流量 100% |

兩點佐證這就是 `finpo` 所在的帳號：`C1-6` 記錄的受保護主機 `finpo.drhiromu.workers.dev`，其 workers.dev subdomain 與此帳號相符；而且以 `--name finpo` 查得到部署。唯一一筆部署的日期與 `C1-6` canary 相符，表示 `finpo` 自那之後沒有再部署過。這筆部署承載的是不是 canary 內容，本次**沒有核對**。下方「`finpo` Worker 上的 `C1-6` canary」節的未登入複驗只證明 Access 生效，看不到內容。

## C7-2　代理逾時量測

### 為什麼要量

`D3` 採「請求內同步完成」，但**整體 deadline 與單次檔數兩個數值刻意未定**，`D3` 明文禁止在本項量測前寫入推測值。計畫書第 6 節風險表記載的假設是「Cloudflare 邊緣對長請求常見在約 100 秒切斷（524）」，並註明**未測**。`C4-1` 的機制已完成但兩個設定鍵仍是沿用既有行為的預設值，`C6-2` 不得在回填前部署。本項要取代的就是這個假設。

`D3` 另有一條作廢條件（計畫書第 272 行）：若量出的上限扣掉冷啟動後不足以在單次請求內完成一份可用清單，`D3` 作廢並回到選項 2，`C4` 的工作生命週期需重新設計。**本次量測未觸發該條件**，理由見下。

### 量測拓樸

需要量的是兩段不同的東西，混在一起量會分不出是哪一段先斷：

```
curl ──①──> workers.dev Worker ──②──> origin
           ① client-facing：請求能維持開啟多久
           ② subrequest：Worker 對外 fetch 能撐多久
```

- ① 以 `/self?s=N` 量：Worker 自己延遲 N 秒後才回應，不發任何 subrequest。
- ② 以 `/proxy?s=N` 量：Worker fetch 一個延遲 N 秒才送出 headers 的 origin。

兩者都以「延遲後才送出 headers 與 body」模擬，因為 `run_job` 在跑完整份清單前不會有任何輸出，這與串流回應的行為不同。

### origin 的選擇：三個候選被否決

| 候選 | 否決理由 |
|---|---|
| 另一個 `workers.dev` Worker | **Cloudflare error 1042**：Worker 不得 fetch 同一 zone 上的另一個 Worker，`workers.dev` 全帳號同屬一個 zone。實測 `upstream_status=404`、body 為 `error code: 1042` |
| `httpbin.org` / `postman-echo.com` | 延遲上限 10 秒，不足以探 100 秒量級的邊界 |
| `httpstat.us` | 公司網路連不到；經 Worker 可達，但 `s=30` 時在 **19.5 秒**被**它自己的** Cloudflare 以 522 切斷。量到的會是別人的逾時 |

最終採**拋棄式 Cloud Run 服務**，`asia-northeast1`，與正式服務同區、同網路路徑：

| 項目 | 值 |
|---|---|
| 服務 | `c72-probe-origin`（與正式服務分離，非 `C6-2`） |
| 映像 | `asia-northeast1-docker.pkg.dev/finpo-508709/finpo/c72-probe-origin:1` |
| digest | `sha256:315c39ddc3c005d945ed0ac19bf5e412b71f0f908266625506c055b10473588e` |
| 網址 | `https://c72-probe-origin-896096883650.asia-northeast1.run.app` |
| 身分 | `finpo-runtime`（無任何專案層級角色，故即使公開亦無可及之物） |
| 設定 | `--timeout=3600`、min=0、max=1、1 vCPU／512 MiB、concurrency=10 |
| 內容 | stdlib-only Python HTTP server，睡 N 秒後回 JSON；無依賴、無資料庫、無秘密 |

`--timeout=3600` 是關鍵：Cloud Run 預設 300 秒，不調高則平台會先切斷，量到的是 Cloud Run 而非 Cloudflare。

### 結果

量測用的 Worker 為 `finpo-probe-proxy`（不受 Access 保護，以便腳本化）。

| 請求秒數 | ① `/self` client-facing | ② `/proxy` → Cloud Run subrequest |
|---|---|---|
| 60 | 200 / 60.13s | 200 / 60.19s |
| 100 | 200 / 100.17s | 200 / 100.17s |
| 110 | — | 200 / 110.19s |
| 120 | — | 200 / 120.35s、120.34s、120.30s（見下方偶發） |
| 124 | — | **200 / 124.19s（最後一個成功點）** |
| 130 | — | **524 / 125.04s** |
| 150 | 200 / 150.13s | **524 / 125.11s** |
| 300 | 200 / 300.13s | **524 / 125.07s** |
| 600 | **200 / 600.12s** | **524 / 125.14s** |

### 結論

1. **subrequest 上限約 125 秒。** 130／150／300／600 四個請求秒數全部在 **125.0–125.2 秒**被切，切斷時間與請求秒數無關——這是一個固定計時器，不是負載或抖動。最後一個成功點為 124 秒。
2. **client-facing 沒有可觀測的上限。** 到 600 秒（10 分鐘）仍完整通過。**兩段差距超過一個數量級。**
3. **計畫書的「約 100 秒」假設低估了，但方向正確。** 確實是 524、確實在邊緣，實際值為 125 秒而非 100 秒。第 6 節風險表該列須改寫。
4. **524 是以 upstream response 的形式回到 Worker 手上**（`upstream_status: 524`），`fetch()` 未 throw。Worker 因此有能力把它轉成給前端的明確錯誤，而不是讓瀏覽器空等。這是 `C7-2` 正式 Worker 的一條實作要求。
5. **`D3` 的作廢條件未觸發。** 125 秒扣掉冷啟動後仍足以在單次請求內完成一份小清單，「請求內同步完成」維持成立。

### 一筆偶發，以及為什麼判定它不是平台行為

邊界收斂時 `s=120` 出現一次 `curl: (56) Recv failure: Connection was reset`，`http_code=000`，發生在 120.23 秒——失敗模式與 524 完全不同：不是 upstream 回錯誤，是客戶端連線被重置，請求根本沒拿到回應。

這與「125 秒固定計時器」矛盾（120 失敗而 124 成功），故**重跑三次**：120.35s、120.34s、120.30s，**三次全部 200 通過**。判定為單次偶發網路重置，非平台行為。判定依據另有一條：`/self` 在 150／300／600 秒都從同一台機器通過，若存在硬性的 120 秒客戶端閒置逾時，那三筆不可能通過。

**保留此紀錄而非刪除**，理由與 `C4-1`「部分更新無法收斂」同型——單次量測看起來正確、重跑才顯現落差。四次中一次的偶發率本身也是資訊：`C7-4` 的前端驗收若看到同樣的 `http_code=000`，第一個假設應是網路偶發而非程式缺陷。

### 對其他項目的影響

| 項目 | 影響 |
|---|---|
| `C4-1` `refresh_deadline_seconds` | 硬上界 **125 秒**，且須再扣除 Cloud Run 冷啟動與 Worker 開銷。**最終值仍未定**：真實映像的冷啟動未量（`C7-7`） |
| `C4-1` `refresh_max_tickers` | 本項未提供依據，仍待 `C7-6` 的實際抓價耗時 |
| `C6-2` request timeout | 須大於 `refresh_deadline_seconds`；但無論設多大都無法超過 125 秒的邊緣上限，**平台 timeout 不是有效的放寬手段** |
| `D3` 第 272 行作廢條件 | 未觸發，`D3` 維持成立 |
| 計畫書第 6 節風險表 | 「Worker 對外請求的實際逾時上限」一列可結清為已量測；「約 100 秒」須更正為 125 秒 |
| 未來若改串流回應 | client-facing 無上限（實測 600 秒），代表分批輸出可大幅放寬可用時間。本階段不做，但這是 125 秒限制唯一已知的繞法 |

### 臨時資源

| 資源 | 用途 | 清除狀態 |
|---|---|---|
| Worker `finpo-probe-origin` | 原訂慢 origin，遭 1042 否決後未再使用 | ✅ 已刪（2026-09-22） |
| Worker `finpo-probe-proxy` | 量測用代理（不受 Access 保護） | ✅ 已刪（2026-09-22） |
| Cloud Run `c72-probe-origin` | 慢 origin | ✅ 已刪（2026-09-22） |
| 映像 `c72-probe-origin:1` | 同上 | ✅ 已刪（2026-09-22） |

清除後複驗：`gcloud run services list --region=asia-northeast1` 與 `gcloud artifacts docker images list .../finpo` 皆為 0 筆；`finpo` Worker 未登入仍回 `302`，canary 未受影響。

`finpo-probe-proxy` 的外部目標為白名單而非自由 `url` 參數：它部署時不受 Access 保護，接受任意網址等於開一個公開代理。

### `finpo` Worker 上的 `C1-6` canary：`C7-1` 之前不得覆寫

正式 Worker `finpo` 目前承載的**不是**主控台自動產生的佔位內容，而是 `C1-6` 刻意留下的 canary：

```
C1-6-CANARY-OK
若你在未登入狀態下看得到這行字，Access 沒有生效。
```

它的價值在於**現在**這個窗口——正式前端尚未部署，若沒有這段字，「Access 有沒有生效」就沒有任何東西可驗。`C7-1` 部署真實前端後，被保護的對象換成前端本身，canary 才功成身退。

**在此之前任何對 `finpo` 的部署都會毀掉它**，包括原本規劃用來做 Access 逾時確認的探針頁。本次即差點覆寫，經制止後改道。

順帶完成一次不需登入即可執行的複驗（2026-09-22）：

| 檢查 | 結果 |
|---|---|
| 未登入 `GET https://finpo.drhiromu.workers.dev/` | `302` |
| 導向目標 | `https://khlin.cloudflareaccess.com/cdn-cgi/access/login/finpo.drhiromu.workers.dev?...` |
| 回應 body | Cloudflare 的 302 頁，**不含** canary 字串 |

`meta` JWT 的 payload 內 `auth_status: "NONE"`、`hostname: "finpo.drhiromu.workers.dev"`，與 `C1-6` 記載的 Worker-level Access 行為一致。此複驗可隨時重跑，不需憑證、不需瀏覽器。

**2026-10-01 補記：canary 已退場**。`C7-1` 部署了真實前端（版本 `39bb1a9b`，之後放 secret 成為 `ca71f76e`）。被保護的對象換成前端本身，它在未登入時的 0 次命中、登入後的頁面顯示，取代了 canary 的作用。canary 版本 `570ea2b7` 仍可回滾。見「`C7-1`／`C7-2` 首次分段部署」節。

### 附錄：探針原始碼

臨時資源已刪除，原始碼留此以便 `C7-1` 複驗時重建。工作檔放在 session 的 scratchpad，跨 session 不留存。

慢 origin（Cloud Run，`Dockerfile` 為 `FROM python:3.13-slim` ＋ `COPY server.py /app/server.py` ＋ `USER 65532:65532` ＋ `ENTRYPOINT ["python", "/app/server.py"]`）：

```python
import http.server, json, os, socketserver, time
from urllib.parse import parse_qs, urlparse

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        seconds = float(parse_qs(urlparse(self.path).query).get("s", ["0"])[0])
        started = time.monotonic()
        time.sleep(seconds)
        body = json.dumps({"role": "cloudrun-origin", "requested_s": seconds,
                           "slept_ms": int((time.monotonic() - started) * 1000)}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

Server(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
```

量測 Worker 的兩條路徑（`/self` 量 ①，`/proxy` 量 ②）：

```js
const ORIGIN = "https://<cloud-run-probe>/";
export default {
  async fetch(request) {
    const url = new URL(request.url);
    const s = Number(url.searchParams.get("s") ?? "0");
    const started = Date.now();
    if (url.pathname === "/self") {
      await new Promise((r) => setTimeout(r, s * 1000));
      return Response.json({ role: "self", requested_s: s, elapsed_ms: Date.now() - started });
    }
    const upstream = await fetch(ORIGIN + "?s=" + s);
    const body = await upstream.text();
    return Response.json({ role: "proxy", requested_s: s, elapsed_ms: Date.now() - started,
                           upstream_status: upstream.status, upstream_body: body.slice(0, 120) });
  },
};
```

掃描以 `curl -sS --max-time $((s+90)) -w 'http_code=%{http_code} time_total=%{time_total}'` 逐點發出。**`--max-time` 必須大於待測秒數加足夠餘裕**，否則量到的是 curl 自己的逾時。

### 本項尚未完成的部分

逾時量測已結清，但 `C7-2` 的其餘要求都需要 `C6` 部署完成後才能做：

- `/api/*` 代理的正式實作與 `assets.run_worker_first` 只列 `/api/*` 的核對
- Worker 端 WebCrypto 與後端 Python 對同一 canonical string 的簽章互通
- Worker 轉發時原樣帶上瀏覽器 `Origin` 標頭（`C2-2` 追加的必辦事項）
- 前端、代理與後端三層逾時的實際對齊
- **經 Access 保護路徑的逾時確認**：上表的 125 秒得自不受 Access 保護的 `finpo-probe-proxy`。Access 在 Worker 之前執行、且不參與回應路徑，理論上不會縮短該上限，但這是推論而非實測。原訂以探針頁部署到 `finpo` 取得實測，因會覆寫上述 canary 而放棄；改於 `C7-1` 部署真實前端（canary 功成身退時）一併確認

**2026-09-30 補記**：上列第一、二、三項的**程式**已在本機完成，見下節；雲端的核對仍未做。

## C7-2　代理程式（本機，2026-09-30）

**本節只有本機的 Node 測試，沒有部署，也沒有動 `finpo`。** 部署要和 `C7-1` 一起做，因為兩者是同一支 Worker（`D2`），第一次部署就會換掉 `C1-6` 的 canary。

### 檔案

| 檔案 | 內容 |
|---|---|
| `worker/index.js` | `/api/*` 代理，依 `D1` 加上 `X-Timestamp` 與 `X-Signature` |
| `wrangler.jsonc` | `name: finpo`；`assets.directory` 指向 `src/stock_quote_fetcher/static/`；`run_worker_first: ["/api/*"]`；`UPSTREAM_ORIGIN` 為決定性網址。秘密 `PROXY_HMAC_SECRET` 以 `wrangler secret put` 設定，不寫進檔案 |
| `tests/worker.test.mjs` | 以 Node 內建的 `node --test` 執行，不需要安裝任何套件 |

### 行為

| 情況 | 處理 | 理由 |
|---|---|---|
| 簽章的 path+query | 從實際 `fetch` 的那個 URL 物件讀回 | 簽的就是送上線路的請求列，包括 URL 解析器做過的編碼 |
| 簽章的 body | 用 `request.arrayBuffer()` 讀一次，雜湊和轉發都用這份 | `D2` 的實作注意 |
| 轉發的請求標頭 | 只轉 `Content-Type`、`Origin`、`X-Portfolio-Token`、`X-Upload-Filename`、`X-Upload-Sheet` | Access 的 cookie 與 `Cf-Access-Jwt-Assertion` 不會送到後端，也就不會進 Cloud Run 日誌。代價是後端以後新讀的標頭必須加進清單，就像 `C6-2` 的上傳標頭一樣 |
| 轉回的回應標頭 | 只轉 `Content-Type`、`Content-Disposition`、`Cache-Control`、`Content-Security-Policy`、`X-Content-Type-Options`、`Referrer-Policy` | 不轉 `Server`、`X-Cloud-Trace-Context` 之類的平台標頭 |
| `/api` 以外的路徑 | 404，不轉發 | 找不到靜態檔的路徑會回落到 Worker，不擋的話會被簽章送到後端 |
| body 超過 5 MiB | 413，不雜湊、不轉發 | 與 `web_input.MAX_UPLOAD` 相同。先擋是為了不讓大檔的雜湊耗掉 CPU |
| 秘密缺少或短於 32 bytes，或 `UPSTREAM_ORIGIN` 未設 | 500，不轉發 | 失敗時關閉 |
| 上游 524 | 504 的 JSON，`code: upstream_timeout` | 本檔的逾時量測：524 以回應的形式回到 Worker |
| 上游 3xx，或 4xx／5xx 且不是 JSON | JSON，`code: upstream_error`；3xx 改為 502，其餘保留原狀態碼 | **計畫沒要求，追加的**。`app.js` 收到任何 `text/html` 回應都會當成 Access 過期而重新整理整頁；後端的錯誤一律是 JSON 且從不轉址，所以這類回應只可能來自前面的平台 |
| `fetch` 丟例外 | 502 的 JSON，`code: upstream_unreachable` | |
| 其他回應 | 狀態碼與 body 原樣轉回 | 含範本 xlsx 的二進位內容 |
| 上游轉址 | `redirect: 'manual'`，不跟隨 | |

錯誤 JSON 的格式與後端 `WebError.payload` 相同（`code`、`message`、`issues`）。

### 測試

| 指令 | 結果 |
|---|---|
| `node --check worker/index.js` | 通過 |
| `PYTHON=.venv/Scripts/python.exe node --test tests/worker.test.mjs tests/web_session.test.cjs` | 17 passed、0 skipped（Node 24.21.0、Python 3.14.6） |

跨語言的兩項測試會啟動 Python，以 `src` 內的 `stock_quote_fetcher.web_auth.Auth` 驗證。傳給 Python 的 `raw_path` 與查詢字串是從 Worker 實際 `fetch` 的 URL 拆出來的，比照 uvicorn 交給 `Guard` 的內容，**沒有沿用 Worker 自己簽的字串**。

- 正向：GET、帶查詢與中文百分比編碼的 GET、含空白與中文的路徑、二進位上傳（含 `0x00`、`0xff`）、JSON 的 PUT，五個都通過驗證。
- 反面：同一個請求分別竄改 body、路徑、查詢、方法、秘密，五個都被拒；未竄改的對照通過。

找不到 Python 時這項測試會失敗，不會 skip。

### 注入錯誤

依本專案的規則，測試要在程式寫錯時會失敗。對 `worker/index.js` 的副本一次注入一個錯誤，再跑同一份測試：

| 注入的錯誤 | 結果 |
|---|---|
| 簽章漏掉查詢字串 | 2 項失敗（跨語言正、反面） |
| 簽章一律用空 body | 2 項失敗（同上） |
| 轉發所有請求標頭 | 1 項失敗 |
| 不轉換 524 | 1 項失敗 |
| 不包裝 HTML 錯誤頁與 3xx | 1 項失敗 |
| 拿掉 `/api` 前綴檢查 | 1 項失敗 |
| 拿掉 5 MiB 上限 | 1 項失敗 |
| 改為跟隨轉址 | 1 項失敗 |
| 轉回所有回應標頭 | 1 項失敗 |
| 拿掉秘密檢查 | 1 項失敗 |
| 以 `new URL(path, base)` 組上游網址 | **0 項失敗** |

最後一項抓不到，是因為它碰不到：會讓 `new URL(path, base)` 跑到別的主機的路徑（`//other.host/...`）不以 `/api` 開頭，已先被前綴檢查擋下。原本另有一個「上游主機不受路徑影響」的測試，它守的正是這個碰不到的情況，**已刪除**，對應的程式註解也改為不宣稱它有防護作用。注入用的腳本放在 session 的 scratchpad，沒有留存。

### 未實測

- **測試跑在 Node，不是 Workers 的執行環境**（workerd）。`Request`、`Headers`、WebCrypto 在兩者的行為推定相同，未核對。
- **在 Workers 裡由程式設定 `Origin` 標頭會不會生效**。瀏覽器禁止設定它，Workers 推定允許，未實測。若不生效，所有寫入請求都會被後端判 403。
- **GFE 會不會原樣把請求路徑交給 uvicorn**。若它改寫了編碼，正向驗簽就會失敗，只有部署後才看得到。
- **5 MiB 上傳的 CPU 耗時**。Free 方案每次 10 ms，SHA-256 加 HMAC 是否在上限內沒有量過；一般的持股 Excel 遠小於這個大小。
- **依 `Content-Length` 提前擋下的那條路徑**。Node 的 `Request` 不會設定這個標頭，所以測試只走到讀完 body 後再擋的那條。
- **`compatibility_date`**（`2026-09-01`）沒有用 wrangler 核對過，這台也沒有安裝 wrangler。
- 部署後還要核對：靜態檔路徑不會啟動 Worker、請求日誌的 `remoteIp` 與 `userAgent` 記到什麼、三層逾時的對齊。

**2026-10-01 補記**：部署後，上列的 `Origin` 標頭、GFE 路徑（就這次用到的路徑而言）、`compatibility_date`、靜態檔不啟動 Worker、`remoteIp`／`userAgent` 都已在雲端核對；5 MiB 的 CPU 耗時、`Content-Length` 那條路徑、三層逾時的對齊仍未做。見「`C7-1`／`C7-2` 首次分段部署」節。

### 建置觸發

建置的 `paths-ignore` 原本只排除 `docs/**` 與 `**.md`，推送這些檔案會觸發一次映像建置。映像內容其實不變，因為 `.dockerignore` 不放行它們，但每次建置都會把最舊的一個可回滾版本擠出保留窗口。**使用者決定**把 `worker/**`、`wrangler.jsonc`、`tests/*.mjs` 加進 `paths-ignore`；改到 workflow 檔的那一次提交本身仍會建置。

**同日補記：推送與建置**。`f903fab`（程式與 workflow）與 `c88b258`（文件）一次推送，觸發一次建置：run `36694568081` 成功，映像 `c88b258728f4`（`sha256:5f9a0986bec883f9d38bace998cb05b62a131bf42271e25adbcf8997e69bc18c`），沒有服務或 Job 使用它。推送前後以 `gcloud artifacts docker images list` 與 `describe` 唯讀核對：

| 映像 | 建立時間（UTC） | 使用者 | 推送後 |
|---|---|---|---|
| `b6347e610e87` | 09-25 14:06 | 無 | 推送前就已超出 3 版，清除政策不是即時的，所以還列得到 |
| `244fd00583bb` | 09-26 11:04 | 無（`C6-4` 回滾實測的對象） | 出了窗口，回滾到這一版的能力消失 |
| `ab1667ccf7f7` | 09-30 12:30 | Job `finpo-catalog-refresh` | 窗口內，排最舊 |
| `a1fb03ff680d` | 09-30 15:40 | 服務 `stock-quote` | 窗口內 |
| `c88b258728f4` | 09-30 17:12 | 無 | 窗口內 |

建置後的清單仍列得到 5 個，兩個舊映像要等清除政策執行才會刪掉。**下一次推程式變更會擠掉 `ab1667ccf7f7`**，推送前要先把 `finpo-catalog-refresh` 改指向較新的映像。`paths-ignore` 的效果還沒觀察到，要等第一次只改 Worker 檔案的推送沒有觸發建置才算確認。

**2026-10-01 更正**：上表「建立時間」一欄標為 UTC，實際是**台北時間**。`gcloud artifacts docker images list` 的 `CREATE_TIME` 以本機時區顯示：`90edd37e91fb` 列為 `10:07:58`，而它的建置 run `36804313065` 在 02:08:01Z 完成；`c88b258728f4` 列為 `17:12`，它的 run 在 09:11:58Z 觸發。各映像的先後順序不受影響。

**2026-10-01 補記：`paths-ignore` 已確認生效**。`b6d0e59`（文件）與 `7fda352`（`C7-8` 第 3 步：`worker/index.js`、`worker/package.json`、`worker/package-lock.json`、`worker/.gitignore`、`wrangler.jsonc`、`tests/worker.test.mjs` 與文件）一次推送（`e261fbd..7fda352`），這是第一次只改 Worker 相關檔案的推送。推送前 `gh run list --workflow build-image.yml` 最新一筆是 `36804313065`；推送後等了 45 秒以上，`gh run list` 仍沒有新的 run，該提交的 check-runs 為 0。registry 以 `gcloud artifacts docker images list` 唯讀核對，仍只有 `ab1667ccf7f7` 與 `a1fb03ff680d` 兩個，沒有新映像。

界線：只觀察到「沒有建置」，沒有讀 GitHub 判斷時的紀錄。`worker/` 下新增的檔案（`package.json` 等）也被 `worker/**` 排除，與預期相符。

## C7-1／C7-2　首次分段部署（2026-10-01）

依計畫書 `C7-1` 項下 10-01 補記的分段程序執行：先部署不帶 secret 的 Worker，以未登入與已登入的請求重新證明 Access 生效，然後才放 secret。**`C1-6` 的 canary 自此退場**。時間皆為 UTC。

| 版本 | 建立時間 | 來源 | 內容 |
|---|---|---|---|
| `570ea2b7-ae77-44c6-930d-63ba6ab42f04` | 09-17 03:50 | Upload | `C1-6` canary（回滾用） |
| `39bb1a9b-bf0e-4c08-86d8-6509b4d0da71` | 10-01 02:22:58 | deployment | 靜態檔、`_headers`、`/api/*` 代理，**沒有 secret** |
| `ca71f76e-8d52-4d59-9e61-edbd9890c696` | 10-01 02:42:38 | Secret Change | 同上，加上 `PROXY_HMAC_SECRET`。**現行版本**，流量 100% |

分工依使用者決定：wrangler 的唯讀指令與 curl 由 Claude 執行；部署、放 secret、刪除映像由使用者執行（Claude 執行 `wrangler deploy` 時被權限機制擋下）；瀏覽器操作由使用者執行。

### 部署前（第 0、1 步）

| 項目 | 結果 |
|---|---|
| `_headers` | 列指令時發現 `static/_headers` 以未追蹤檔的形式出現，`Referrer-Policy` 為 `no-referrer`。依 Fetch 規範，這會讓同源 POST 帶 `Origin: null`，被後端的 Origin 白名單判 403。改為 `same-origin` 後提交（`90edd37`） |
| Job 改指向 | 因為 `90edd37` 會觸發建置，推送前由使用者把 `finpo-catalog-refresh` 改指向 `a1fb03ff680d`（`sha256:df4a49e8…`），generation 3，02:03:19Z。Job 不保留舊版設定，所以拿上一次 execution `tsp9t` 保存的範本比對：容器範本 22 行（args、env、secret、映像、資源）只有映像不同；`maxRetries`、SA、`timeoutSeconds`、`taskCount`、`gen2` 都相同 |
| 建置 | run `36804313065` 成功，映像 `90edd37e91fb`（`sha256:6faccf750e7aa33e416ca64ddd4a11ed6b641416565bb72722fd1c00e034d2e7`） |
| dry-run | `wrangler deploy --dry-run` 讀到 assets 目錄的 4 個檔案（三個靜態檔加 `_headers`），4.21 KiB；binding 只有 `UPSTREAM_ORIGIN`；`compatibility_date` 沒有警告 |
| `secret list` | `[]` |
| 基準 | 未登入 `GET /` 回 302 導向 `khlin.cloudflareaccess.com`，143 bytes，canary 字串 0 次 |

### 第 2 步：部署，不放 secret

使用者在 repo 根目錄執行 `npx --yes wrangler@4.145.0 deploy`（`WRANGLER_SEND_METRICS=false`），輸出 `Current Version ID: 39bb1a9b-…`。`versions view` 確認：handler `fetch`，`compatibility_date` 2026-09-01，binding 只有 `UPSTREAM_ORIGIN`。

**未登入**（Claude 以 `curl -sS` 發出）：

| 請求 | 結果 |
|---|---|
| GET `/`、`/index.html`、`/app.js`、`/style.css`、`/_headers`、`/api/portfolio`、`/nope` | 全部 302 導向 Access 登入，143 bytes；`MY PORTFOLIO` 與 canary 字串都是 0 次 |
| POST `/api/portfolio` | 302 |
| preview URL `39bb1a9b-finpo.drhiromu.workers.dev` | **存在**，302 導向 Access，內容 0 次 |

**已登入**（使用者以瀏覽器操作，DevTools 開啟）：

| 核對 | 結果 |
|---|---|
| 頁面 | 顯示「持股總覽」版面。這是 `C1-6` 要求的基準線：有它，上面的「0 次」才分得出是 Access 擋下，而不是檔案沒部署 |
| `index.html` 的回應標頭 | 有 `Content-Security-Policy`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: same-origin` |
| Console | 沒有 CSP 違規。唯一的訊息是 `/api/session` 回 500 的網路錯誤 |
| `/api/session` | 500，`code: proxy_misconfigured` |

`/api/portfolio` 沒有發出：`app.js` 要等 `/api/session` 成功才會呼叫它（`app.js` 最後一行的啟動流程）。列核對項目時原本寫成兩者都應回 500，那是錯的。

`wrangler tail finpo --format=json` 在這段期間記到 4 筆：`/api/session` 3 筆（500，沒有例外）、`/favicon.ico` 1 筆（404）。`/favicon.ico` 沒有對應的靜態檔，所以會回落到 Worker，這是 `wrangler.jsonc` 註明的行為。**`/`、`/app.js`、`/style.css` 都沒有出現**。

### 第 3 步：放入 secret

| 項目 | 結果 |
|---|---|
| 3a 格式檢查 | `len=64 printable=True`。指令只印出長度與「是否全為 0x21–0x7e」，不印值 |
| 為何要檢查 | wrangler 4.145.0 的 `secret put` 會對讀到的值做 `trimEnd()`（`wrangler-dist/cli.js` 的 `trimTrailingWhitespace`）。管線多出的換行不會進入 Worker，但如果 Secret Manager 的值本身以空白結尾，Worker 拿到的會比後端短。這台只有 PowerShell 5.1，它把管線內容轉成字串再以 ASCII 重新編碼並補上 CRLF，所以值必須是可見 ASCII 才不會被改動 |
| 3b | 使用者執行 `gcloud.cmd secrets versions access latest --secret=proxy-hmac-secret \| npx --yes wrangler@4.145.0 secret put PROXY_HMAC_SECRET --name finpo`，輸出 `Success! Uploaded secret PROXY_HMAC_SECRET` |
| `secret list` | 只有 `PROXY_HMAC_SECRET`，`secret_text` |
| 新部署 | `ca71f76e`，來源 `Secret Change`，流量 100% |
| 未登入 `GET /`、`/api/session` | 都是 302 導向 Access |

### 第 4 步：正向核對

使用者在瀏覽器重新整理頁面、下載範本、以下載的 `持股範本.xlsx` 做三次上傳預覽，按取消，沒有套用或儲存。沒有按「更新報價」或「更新股票清單」。

| 時間 | 請求 | tail 狀態 | Worker wall（ms） | Cloud Run 狀態 | 後端延遲（s） |
|---|---|---|---|---|---|
| 02:46:57 | GET `/api/session` | 200 | 3675 | 200 | 2.967 |
| 02:47:01 | GET `/api/portfolio` | 200 | 343 | 200 | 0.220 |
| 02:47:02 | GET `/api/portfolio/valuation?market=ALL` | 200 | 189 | 200 | 0.091 |
| 02:48:45 | GET `/api/templates/holdings.xlsx` | 200 | 150 | 200 | 0.005 |
| 02:49:08 | POST `/api/imports/preview` | 200 | 602 | 200 | 0.510 |
| 02:49:33 | POST `/api/imports/preview` | 200 | 604 | 200 | 0.505 |
| 02:49:58 | POST `/api/imports/preview` | 200 | 580 | 200 | 0.492 |

所有請求的 CPU time 都在 1 ms 以內，沒有例外，版本都是 `ca71f76e`。靜態檔依然沒有出現在 tail。第一筆 `/api/session` 的 2.97 秒推定是冷啟動（`C7-7` 量得 2.3–3.4 秒），沒有另外核對。

| 核對 | 結果 | 證明什麼 |
|---|---|---|
| `/api/session`、`/api/portfolio` 回 200，頁面顯示空持股 | ✅ | **雲端的正向驗簽通過，服務連得上資料庫**。這是 `C6-2` 剩下的兩項 |
| 帶查詢字串的 GET（`valuation?market=ALL`）、二進位 body 的 POST 通過驗簽 | ✅ | 這些路徑上，GFE 沒有改寫 Worker 簽章的請求列與 body |
| 上傳預覽回 200，對話框顯示工作表 | ✅ | Workers 裡由程式設定 `Origin` 會生效，兩個上傳標頭也有轉發。`same-origin` 下寫入請求的 `Origin` 正確 |
| tail 只記到 `/api/*` 與無對應檔案的路徑 | ✅ | `run_worker_first` 只讓 `/api/*` 先進 Worker，靜態檔不啟動 Worker |
| 直接 `GET run.app/api/session`、`/api/portfolio`，不帶簽章 | 401 `unauthorized` | 沒有改變 |
| preview URL `ca71f76e-finpo.drhiromu.workers.dev` | 302 導向 Access | 新版本的 preview URL 也在 Access 保護內 |

### Cloud Run 請求日誌

以 `logging read` 查 `run.googleapis.com/requests`，`stock-quote`，02:20–03:00Z，共 **7 筆**，與第 4 步 tail 的 7 筆逐筆對應。

- **第 2 步那 3 次 500 一筆都沒有**。同一條查詢查得到第 4 步的請求，所以這不是過濾條件寫錯（PowerShell 吃掉雙引號會靜默回 0 筆，見 R4 節）。「缺 secret 時不轉發」原本只有 Node 測試，至此有雲端的實測證據。
- **`remoteIp`**：4 個不同位址，分屬 `172.68.`、`172.71.`、`162.158.` 開頭的網段，推定是 Cloudflare 的出口，沒有對照 Cloudflare 公布的 IP 清單。使用者本人的 IP 不在日誌裡。完整位址不寫入本檔。
- **`userAgent`**：7 筆都是空字串。Worker 只轉發白名單內的標頭（見「`C7-2` 代理程式（本機）」節），`User-Agent` 不在其中。所以日誌裡沒有使用者的 IP，也沒有瀏覽器資訊，事後要從 Cloud Run 日誌追查請求來源比較困難，要靠 Cloudflare 那一側。這是觀察結果，沒有判定為缺陷。
- **檔名**：上傳的 `持股範本.xlsx`，不論原字或百分比編碼，在 7 筆的完整 JSON 裡都查不到，`X-Upload-Filename` 也查不到。日誌裡出現的 `holdings.xlsx` 是下載範本的 GET 路徑。這是 `C6-2` 日誌修正在真實前端上的第一次觀察，正式驗收仍在 `C7-4`。

### 映像整理

使用者要求刪除沒有用途的映像。以 build context 會放行的路徑（`src`、`pyproject.toml`、`uv.lock`、`README.md`、`deploy/cloud.toml`、`deploy/supabase-ca.crt`、`Dockerfile`）比對 `git diff`：

| 映像 | 使用者 | 與現行 `a1fb03ff680d` 的差異 | 處置 |
|---|---|---|---|
| `a1fb03ff680d` | 服務 `00004-4v6`、Job `finpo-catalog-refresh` | — | 保留 |
| `ab1667ccf7f7` | revision `00001-dx4`、`00003-qs6` | 上傳檔名改走標頭之前的版本 | 保留，唯一能回滾到不同程式的目標 |
| `c88b258728f4` | 無 | 沒有差異 | 使用者以 digest 刪除 |
| `90edd37e91fb` | 無 | 只多了 `_headers`，後端不提供靜態路由，用不到它 | 使用者以 digest 刪除；需要時可以 `workflow_dispatch` 重建 |

刪除後 registry 只剩 `a1fb03ff680d` 與 `ab1667ccf7f7`。保留政策是 3 版，所以**下一次程式推送不會擠掉任何映像**，第二次才會擠掉 `ab1667ccf7f7`。revision `00002-wl7` 的 `244fd00583bb` 先前已被清除。

### 未實測、未做

- ~~**Access 下的 125 秒上限**（`C7-1` 承接）、**524 的轉換**、**三層逾時的對齊**（`C7-2`）。~~ 10-02 已做，見「`C7-1`／`C7-2` 收尾」節。
- **5 MiB 上傳的 CPU 耗時**，以及依 `Content-Length` 提前擋下的那條路徑。這次的上傳只是範本，CPU time 在 1 ms 以內。
- **含中文百分比編碼的路徑**在雲端的驗簽。這次的請求沒有用到；Node 測試涵蓋了。
- **`no-referrer` 會導致 403 的反面測試**沒有做，`Origin: null` 的推論只有規範依據。
- **從 preview URL 寫入**：preview 主機不在 `WEB_ALLOWED_ORIGINS`，推定寫入會被判 403（`C6-2` 的設計），沒有實測。
- **遙測**：設了 `WRANGLER_SEND_METRICS=false`，wrangler 仍印出遙測提示，實際有沒有送出沒有核對。
- `C7-3`、`C7-4`、`C7-5`、`C7-8` 都還沒開始。**`C7-8` 依計畫排在 `C7-4` 之前**。

### 操作環境

- wrangler 一律用 `npx --yes wrangler@4.145.0`，見「`C7-1` 部署前準備」節。
- 這台在 `%LOCALAPPDATA%` 的 Cloud SDK 是壞的（`lib/gcloud.py` 不存在），所有 gcloud 指令都用 Git 忽略的可攜版 `output\tools\google-cloud-sdk\bin\gcloud.cmd`（R2 節記錄的 586.0.0）。
- 這台找不到 PowerShell 7，日誌查詢以 5.1 執行。過濾條件的雙引號寫成 `\"`，寫在 `.ps1` 檔裡；查得 7 筆就是查詢沒有被靜默改壞的正向對照。

## C7-1／C7-2　收尾：Access 下的逾時、524 轉 504、三層對齊（2026-10-02 13:20–13:45 台北）

程序見計畫書 `C7-2` 項下 10-02 補記。要量的三件事，正式後端都碰不到，因為它有 110 秒的 deadline。所以用 09-22 的拋棄式慢 origin 當上游，Worker 則用**真正的 `finpo` 程式**，以只上傳、不部署的版本打 preview URL。

### 臨時資源

| 資源 | 內容 | 清除 |
|---|---|---|
| 映像 `c72-probe-origin:2` | 依本檔「附錄：探針原始碼」重建，`linux/amd64`，`sha256:ddda0c10…`。推送前確認清除政策 `keep-recent-3` 是 `mostRecentVersions`，依 GCP 文件以套件為單位計數，不會擠掉 `stock-quote`；這點本專案沒有實測，推送後 `stock-quote` 的版本沒有減少 | ✅ 已刪 |
| Cloud Run `c72-probe-origin` | 由使用者部署（帶 `--allow-unauthenticated`）。設定同 09-22：`--timeout=3600`、max 1、1 vCPU／512 MiB、concurrency 10、`finpo-runtime`。IAM 只有 `allUsers` → `run.invoker` | ✅ 已刪 |
| Worker 版本 `45e127f7` | `versions upload --var UPSTREAM_ORIGIN:<慢 origin 決定性網址>`，**沒有部署** | 由 `6ed463e5` 取代為最新版本（見下） |

推送映像用 `gcloud auth print-access-token` 登入 Docker，推完即 `docker logout`，沒有改 Docker 的 credential helper 設定。

### 前置核對

| 檢查 | 結果 |
|---|---|
| 慢 origin 直接打 `?s=1`（兩個網址） | 200，`slept_ms` 1001／1002 |
| 上傳 `45e127f7` 後的 `deployments status` | 仍是 `474e5c4f` 100% |
| preview URL 未登入的 `/` 與 `/api/c71?s=1` | 都是 302，導向 `khlin.cloudflareaccess.com` 的登入頁；回應內容 0 次命中慢 origin 的 `cloudrun-origin` |

### 結果

使用者登入 preview URL 後，在 Console 執行 [`c71-timeout-check.js`](c71-timeout-check.js)：

| s | 瀏覽器收到 | 秒數 | 慢 origin 的請求日誌 |
|---|---|---|---|
| 5 | 200，`role: cloudrun-origin` | 5.48 | 200，5.003 s |
| 120 | 200，`role: cloudrun-origin` | 120.49 | 200，120.004 s |
| 130 | **504，`code: upstream_timeout`** | **125.40** | **200，130.004 s** |
| 130，經 `app.js` 的 `api()` | 丟出 Worker 的訊息「後端未在連線時限內回應；已完成的部分會保留。若剛才是在儲存或更新，請重新整理頁面確認結果。」 | **125.38** | **200，130.005 s** |

- **`C7-1`：Access 下的上限仍是 125 秒**。120 秒通過，130 秒在 125.4 秒被切。09-22 沒有 Access 時量到的是 125.0–125.2 秒，最後成功點 124 秒。這次只有兩個點夾住，沒有重新收斂邊界。
- **`C7-2`：524 在雲端被轉成 504**，body 是 Worker 的 JSON，`code` 為 `upstream_timeout`。tail 讀不到 preview 的請求（`C7-8` 第 6 步），所以 Worker 端拿到的確實是 524，是由回應的代碼推得的：只有 524 那條分支會產生 `upstream_timeout`。
- **前端那一層**：`api()` 收到 504 後丟出 Worker 的訊息，**頁面沒有重新整理**。依據是腳本跑完並印出了表格；若頁面重新整理，Console 的執行環境會消失。

### 新發現：邊緣切斷之後，上游仍把請求做完

兩筆 130 秒的請求，瀏覽器在 125.4 秒就收到 504，但慢 origin 的日誌都是 **200、130.00 秒**。第二筆在 05:36:12.68Z 送出，第一筆到 05:36:17.31Z 才結束，兩者重疊。也就是說，Cloudflare 放棄等待之後，Cloud Run 端的請求沒有被中斷。

這對應 `C7-6` R1 留下的未實測項「被 524 切斷後，Cloud Run 端是否繼續」，但**只回答了一半**：

- 慢 origin 只是 `sleep` 後寫回應，中途不讀也不寫 socket。真正的後端在 `run_job` 期間也不寫回應，形態相近，但它跑在 FastAPI 的 threadpool 裡，用戶端斷線時會不會被取消，**沒有測**。
- 日誌的 200 只代表容器寫出了回應，不代表有人收到。
- 對設計的意義：如果真正的後端也照樣做完，Worker 訊息裡「已完成的部分會保留」就有依據，而且保留的會比切斷那一刻更多。Cloud Run 的 timeout 是 150 秒，做得再久也會在那裡被平台切斷。

### 三層逾時的對齊

| 層 | 值 | 依據 |
|---|---|---|
| 前端 `app.js` | `fetch` **沒有設逾時**，一直等到代理回應 | 讀程式（`api()` 沒有 `AbortSignal`）。本次 125.38 秒仍在等，收到 504 後顯示 Worker 的訊息 |
| 代理（瀏覽器 → Worker） | 沒有可觀測的上限 | 09-22 量到 600 秒仍通過（沒有 Access） |
| 代理（Worker → Cloud Run） | **125 秒**，超過時回 524，Worker 轉成 504 | 09-22 量到 125.0–125.2 秒；本次在 Access 下 120 秒通過、130 秒於 125.4 秒被切 |
| 後端 `refresh_deadline_seconds` | **110 秒**，最晚約 118.5 秒收尾（算式見 `deploy/cloud.toml`） | `C7-4` C2 在正式主機名稱上，端到端 110.653 秒通過，不含冷啟動 |
| 後端 Cloud Run timeout | **150 秒** | `C6-2` 依算式選定。本次發現平台不會因邊緣切斷而提前中止請求（見上），所以這一層是工作的最後上限 |

順序是 **後端收尾（≤ 118.5）＜ 邊緣（125）＜ Cloud Run（150）**，前端不設上限。正常的更新由 deadline 先收尾，回應趕在邊緣之前送到；萬一超過，使用者會在 125 秒收到一句明確的說明，而不是空白或整頁重新整理。

### 界線

- **量的是 preview URL，不是正式的主機名稱**。兩者共用同一個 Access application，跑的也是同一份 Worker 程式（只差一個 var）。正式主機名稱上的證據只有 `C7-4` C2 的 110.653 秒，沒有超過 125 秒的樣本。
- 每個點只有 1 個樣本（130 秒有 2 個）。
- **後端端到端的最壞情況沒有量**：冷啟動加上 110 秒 deadline 還在 125 秒內，是 `C7-7` 的算式推得的，`C7-7` 才會量冷啟動。
- 真正的後端在 524 之後會不會照樣做完，沒有測（見上）。

### 收尾

| 步驟 | 結果 |
|---|---|
| 上傳不帶 `--var` 的版本 `6ed463e5`（`C7-8` 的教訓：讓最新版本回到正確設定） | `UPSTREAM_ORIGIN` 回到 `stock-quote-896096883650…`；`deployments status` 仍是 `474e5c4f` 100% |
| 刪除 Cloud Run `c72-probe-origin` 與映像 | 複驗：`run services list` 只剩 `stock-quote`；registry 只剩 `stock-quote` 的 4 個版本 |
| `45e127f7` | 仍在版本清單裡，但沒有部署。它的 preview URL 受 Access 保護，上游已刪除，打得到也只會得到錯誤 |

## C7-8　第 0 步：Worker 收不收得到 Access 的 JWT（2026-10-01）

設計見計畫書 `C7-8` 項下「設計」補記。官方文件只說 Access 會把 `Cf-Access-Jwt-Assertion` 帶給 origin，沒有說 Worker 層級的 Access 會帶給 Worker 本身；設計只讀這個標頭，所以先實測。本節沒有部署，也沒有改任何設定。

### 方法

Claude 以一支過濾腳本包住 `npx --yes wrangler@4.145.0 tail finpo --format=json`（`WRANGLER_SEND_METRICS=false`），只輸出標頭**名稱**；如果 JWT 的值看得到，再輸出 `alg`、`kid`、`iss`、`aud`、claim 名稱與有效期長度。token、`email` 與其他標頭的值都不印，tail 的原始輸出只留在記憶體，沒有寫入磁碟。腳本放在 session 的暫存目錄，沒有進 repo。使用者在已登入的瀏覽器重新整理 `finpo.drhiromu.workers.dev` 一次。

### 結果

tail 記到 3 筆，都是 `finpo.drhiromu.workers.dev`、版本 `ca71f76e` 的現行程式：

| 時間（UTC） | 請求 | 狀態 | CPU（ms） | wall（ms） |
|---|---|---|---|---|
| 03:23:03 | GET `/api/session` | 200 | 2 | 4108 |
| 03:23:07 | GET `/api/portfolio` | 200 | 2 | 221 |
| 03:23:08 | GET `/api/portfolio/valuation` | 200 | 2 | 150 |

3 筆的標頭名稱完全相同，共 23 個，**都有 `cf-access-jwt-assertion`**，另有 `cf-access-authenticated-user-email`、`cookie`、`cf-connecting-ip`、`x-real-ip` 等。

| 核對 | 結果 | 證明什麼 |
|---|---|---|
| `cf-access-jwt-assertion` 的名稱 | 3/3 出現 | **Worker 層級的 Access 會把這個標頭帶給 Worker 本身**，至少在 `workers.dev` 主機上是如此。設計不必改成讀 cookie |
| 它的值 | 長度 8、不是三段式，推定是 tail 把值換成 `REDACTED`（剛好 8 個字元）。`cookie` 的值同樣被遮成 `REDACTED` | **值看不到**，所以沒能確認它是 JWT，也讀不到 `alg`、`kid`、`iss`、`aud` |

### 這個結果的界線

- **值是不是合法的 Access JWT、`aud` 是什麼，都還沒證明。** 原定第 1 步「AUD 與第 0 步看到的 `aud` 核對」做不到了，改由第 5 步的正向核對承擔：新程式用使用者抄出的 AUD 驗證真實請求並放行，才同時證明值是 JWT、`aud` 也抄對了。
- **preview URL 上有沒有這個標頭沒有觀察**，這次只打了正式主機。第 6 步的反面測試在 preview URL 上做，如果那裡沒有標頭，請求會因為「沒有 JWT」被擋下，而不是因為白名單或 `aud` 不符，測試就白做了。因此新程式的 `console.log` 要記失敗類別，第 6 步要從 tail 的 log 核對 403 的原因是預期的那一種。tail 會帶出 `console.log` 是 wrangler 的一般行為，本專案還沒實測過，第 5 步一併確認。
- **`cf-access-authenticated-user-email` 不能拿來取代 JWT 的 `email` claim**。它只是 Access 加上的純文字標頭，Access 被關掉時用戶端可以自己帶，沒有簽章。設計只信任 JWT 裡的 `email`。
- **用戶端自己帶 `Cf-Access-Jwt-Assertion` 時，Access 會不會覆蓋，沒有測試**。Access 正常時這不影響安全性：偽造的值過不了簽章驗證。
- 現行程式（不驗 JWT）的 CPU time 這次是 2 ms，首次分段部署第 4 步那 7 筆都在 1 ms 以內。tail 只給整數 ms，這是基準線，不是驗簽的成本。

### 第 1 步：AUD

使用者在 finpo 的 application 頁面找不到 AUD。Claude 改以不登入的 `curl -sS` 打 `GET /`：回 302 導向 `khlin.cloudflareaccess.com/cdn-cgi/access/login/finpo.drhiromu.workers.dev`，查詢參數為 `kid`、`meta`、`redirect_url`，只讀出 `kid`，`meta` 沒有讀出。`kid` 為 `fa06f0350059e4038d2927c1e83ac81e01825cc7930609d12bbdf3e41980c065`，64 個十六進位字元。

「登入網址的 `kid` 就是 AUD」原本是依 Access 的慣例推論的，**使用者隨後在儀表板核對，確認一致**。已寫入 `wrangler.jsonc` 的 `ACCESS_AUD`；JS 測試仍為 25 passed，dry-run 的 binding 多了 `ACCESS_AUD`，大小不變。真實 token 的 `aud` 是否含這個值，仍由第 5 步的正向核對證明。

### 第 2 步（部分）：`versions` 指令的說明

以 `npx --yes wrangler@4.145.0 versions upload --help` 與 `versions secret put --help` 查得：

| 指令 | 說明文字 | 對第 6 步的意義 |
|---|---|---|
| `versions upload` | 「Uploads your Worker code and config as a new Version」；有 `--var`、`--secrets-file`（與先前的 secret 疊加，沒列出的不刪）、`--preview-alias` | 可以只在這次上傳帶入改錯的 `ACCESS_AUD`（`--var`）或白名單（`--secrets-file`），不必改 repo 裡的 `wrangler.jsonc` |
| `versions secret put` | 「Create or update a secret variable for a Worker」 | 沒說會不會部署 |

**說明文字都沒有說「不部署」，也沒說會產生 preview URL。** 這兩點仍未核對。第 6 步每次上傳後，要立刻以唯讀的 `deployments status` 確認正式流量仍 100% 在原版本，再打 preview URL。萬一上傳真的部署了，後果是擁有者自己也被 403 擋下（拒絕方向，不是放行方向），回滾到第 4 步部署的版本即可。

### 第 3 步：實作與 Node 測試（本機，未部署）

**沒有部署，沒有動 `finpo`，也沒有放任何 secret。**

| 檔案 | 內容 |
|---|---|
| `worker/index.js` | 設定檢查之後、讀 body 之前，先驗 `Cf-Access-Jwt-Assertion`：jose 的 `jwtVerify`，`algorithms: ['RS256']`、`issuer`、`audience`、`requiredClaims: ['exp', 'email']`；再比對 `email` 是否在白名單內（兩邊都去空白、轉小寫）。token 本身的問題回 403 `access_denied`；JWKS 抓不到、逾時或格式錯回 503 `access_unverifiable`。兩者都不簽章、不轉發，`console.log` 只記失敗類別 |
| `worker/package.json`、`package-lock.json`、`.gitignore` | jose 釘在 `6.2.12`，lockfile 顯示沒有其他依賴；`node_modules/` 不進 repo |
| `wrangler.jsonc` | 新增 `ACCESS_TEAM_DOMAIN`。**`ACCESS_AUD` 還沒填**，要等第 1 步由使用者抄出，不放推測值；缺它時 Worker 對所有 `/api` 回 500 `proxy_misconfigured`。另把檔頭「`C7-1` 之前不得部署」的舊註解改為現行的部署限制 |
| `tests/worker.test.mjs` | 新增 8 個測試，見下；既有測試改為預設帶一個合法的 token |

**與設計不同的一處**：計畫原本要把 `package.json`／`package-lock.json` 加進 `build-image.yml` 的 `paths-ignore`。改 workflow 本身的那次提交會觸發一次建置，所以改為把它們放在 `worker/` 底下，沿用既有的 `worker/**` 規則，不必動 workflow。代價是第二階段 React 的 npm 設定不會和它共用同一份 `package.json`。

**jose 的行為，讀原始碼確認**（`dist/webapi/jwks/remote.js`、`lib/jwt_claims_set.js`）：

- 取 JWKS 用全域 `fetch`，而且是呼叫當下才讀取，所以 Node 測試換掉 `globalThis.fetch` 就攔得到。設計時的推論成立。
- 預設值：快取 10 分鐘、逾時 5 秒、碰到不認得的 `kid` 時最多每 30 秒重抓一次。在 Workers 環境下，它不在請求之間共用進行中的抓取。
- `exp` 只在存在時檢查，所以要列進 `requiredClaims` 才會強制存在。`clockTolerance` 保持預設的 0，沒有另訂寬限。若第 5 步出現剛登入就被 `nbf` 擋下的情形，再依實測決定。

**測試**：以 WebCrypto 自產 RSA 金鑰並**手工簽 token，不透過 jose 簽**，避免簽與驗共用同一份程式的缺陷。JWKS 由同一個被換掉的 `fetch`，在 `/cdn-cgi/access/certs` 提供。

| 測試 | 涵蓋 |
|---|---|
| 缺設定或格式錯 | 缺 AUD、缺白名單、白名單只有空白、缺 team domain、team domain 結尾有 `/` 或帶路徑、`http://`。都回 500，**沒有轉發，也沒有抓 JWKS** |
| 沒有 JWT | GET 與 PUT 都回 403，沒有轉發，log 為 `missing` |
| 驗證失敗的 token（14 種） | 別的金鑰冒用信任的 `kid`、簽章不變但換掉 payload、`aud` 不符、`iss` 不符、已過期、`nbf` 在未來、沒有 `exp`、沒有 `email`、`email` 不在白名單、`email` 不是字串、`alg: none`、以公鑰當 HMAC 金鑰的 HS256、JWKS 裡沒有的 `kid`、不是 JWT。每一種都斷言 403、沒有轉發、log 的原因 |
| 純文字的 email 標頭 | 帶 `Cf-Access-Authenticated-User-Email: <擁有者>`，但 JWT 的 `email` 是別人，回 403 |
| 白名單比對 | 大小寫不同、前後有空白、名單有兩人，兩人都放行 |
| JWKS 不可用（4 種） | 連不上、回 502、回 HTML、內容不是 key set。都回 503，沒有轉發 |
| JWKS 快取 | 連續兩個請求只抓一次 |
| 金鑰輪替 | 新金鑰在 30 秒冷卻內出現時回 403、不重抓；時間推進 31 秒後重抓並放行。用 `node:test` 的 mock timers 只模擬 `Date` |

`PYTHON=.venv/Scripts/python.exe node --test tests/worker.test.mjs tests/web_session.test.cjs`：**25 passed、0 skipped**（Node 24.21.0）。執行前先跑過 `npm ci --prefix worker`。Python 程式沒有改，隔離容器的完整套件沒有重跑。

**修正前會失敗**：把 `worker/index.js` 換回 `HEAD` 的版本，8 個新測試有 7 個失敗，原因都是行為斷言（例如預期 403、實得 200；預期抓 1 次 JWKS、實得 0 次），不是函式不存在。剩下的「白名單比對」在舊程式上會通過：它是正向測試，守的是「不該誤擋」，而舊程式什麼都放行。它的作用由下方錯誤注入證明。

**錯誤注入**：一次注入一種，共 16 種，**16 種都被抓到**：

| 注入的錯誤 | 抓到它的測試 |
|---|---|
| 沒有 JWT 也放行 | 沒有 JWT |
| 忽略拒絕結果 | 5 個 |
| 拿掉 `algorithms` | 驗證失敗（見下方說明） |
| 拿掉 `issuer`／`audience` | 驗證失敗 |
| `exp` 不列為必要 | 驗證失敗 |
| `email` 不列為必要 | 驗證失敗（見下方說明） |
| 不比對白名單 | 驗證失敗、email 標頭 |
| 比對時 token 那側不轉小寫／名單那側不轉小寫 | 白名單比對 |
| 所有錯誤都回 503／都回 403 | 驗證失敗、金鑰輪替／JWKS 不可用 |
| 不檢查 team domain 格式／允許空白名單 | 缺設定 |
| 每個請求都重建 key set | JWKS 快取、金鑰輪替 |
| 改信任純文字的 email 標頭 | email 標頭 |

**有兩種只靠原因字串抓到，請求其實仍被擋下**：

- 拿掉 `algorithms` 後，`alg: none` 仍被 jose 擋下，原因變成 `ERR_JOSE_NOT_SUPPORTED`。jose 本來就不接受 `none`。
- `email` 不列為必要 claim 後，沒有 `email` 的 token 仍被白名單比對擋下，原因變成 `email`。

這兩項是多一層保險，拿掉了也不會放行，只有 log 的分類會變。

**打包**：`npx --yes wrangler@4.145.0 deploy --dry-run --outdir <暫存目錄>`，沒有上傳。

- Total Upload 為 **40.83 KiB／gzip 11.56 KiB**，打包後的 `index.js` 含 jose。
- binding 有 `UPSTREAM_ORIGIN` 與 `ACCESS_TEAM_DOMAIN`。

**未實測**：

- 在 Workers 執行環境裡的行為，包括 jose 在 workerd 上取 JWKS。
- 真實 Access token 的 `iss`、`aud`、`email` 格式。
- 驗簽的 CPU 時間。

以上都由第 5 步確認。

### 第 4 步：放白名單，再部署

部署前基準（Claude 唯讀核對）：`secret list` 只有 `PROXY_HMAC_SECRET`；`deployments status` 為 `ca71f76e` 100%。

**4a 放白名單**：使用者以 `npx --yes wrangler@4.145.0 secret put ACCESS_ALLOWED_EMAILS --name finpo` 的互動提示輸入，沒有用管線。值只有使用者知道，本檔不記錄。之後 Claude 唯讀核對：

| 項目 | 結果 |
|---|---|
| `secret list` | `ACCESS_ALLOWED_EMAILS`、`PROXY_HMAC_SECRET`，都是 `secret_text` |
| `deployments status` | `6b39cc89-862f-4e89-b0ad-eea23b398347` 100%，來源 `Secret Change`，03:47:42Z |
| `versions view 6b39cc89` | binding 只有 `UPSTREAM_ORIGIN`，沒有 `ACCESS_*` 變數，兩個 secret 都在。由 binding 推定它跑的仍是 `ca71f76e` 的舊程式（新設定會多出 `ACCESS_TEAM_DOMAIN`、`ACCESS_AUD`），舊程式不讀這個 secret |
| 未登入 `GET /`、`/api/session` | 都是 302 導向 Access 登入 |

`6b39cc89` 取代 `ca71f76e` 成為回滾目標：舊程式，但兩個 secret 都在。

**4b 部署**：使用者在 repo 根目錄執行 `npx --yes wrangler@4.145.0 deploy`（`f78cd9b`，`worker/node_modules` 由 `npm ci --prefix worker` 安裝）。Claude 唯讀核對：

| 項目 | 結果 |
|---|---|
| `deployments status` | `474e5c4f-4bfd-4c4e-a36f-c1d38c164b63` 100%，04:17:09Z |
| `versions view 474e5c4f` | binding 有 `ACCESS_AUD`、`ACCESS_TEAM_DOMAIN`、`UPSTREAM_ORIGIN`；secret 有 `ACCESS_ALLOWED_EMAILS`、`PROXY_HMAC_SECRET`；`compatibility_date` 2026-09-01 |
| 未登入 GET `/`、`/index.html`、`/app.js`、`/api/session`、`/api/portfolio`，POST `/api/portfolio` | 全部 302 導向 Access 登入，143 bytes，頁面標記「持股總覽」0 次 |
| preview URL `474e5c4f-finpo.drhiromu.workers.dev` 的 `/`、`/api/session` | 302 導向 Access |
| 登入網址的 `kid` | 正式主機與 preview URL 都是 `fa06f035…c065`，與 `ACCESS_AUD` 相同。推定 preview URL 由同一個 Access application 保護，第 6 步的反面測試因此可以在 preview URL 上做 |

### 發現：公司網路開始解密 `*.workers.dev` 的 TLS

第 4b 步之後，curl 打 `finpo.drhiromu.workers.dev` 失敗：`CRYPT_E_NO_REVOCATION_CHECK`。同一台機器約 30 分鐘前（第 0、1 步）還正常。`wrangler tail` 也失敗：`CERT_SIGNATURE_FAILURE`。

以 Node 的 `tls.connect` 唯讀讀取對方出示的憑證鏈，不送任何資料：

| 主機 | 簽發者 | Node 驗證 |
|---|---|---|
| `finpo.drhiromu.workers.dev`、`tail.developers.workers.dev` | `prisma-advantech.com`（O=Advantech）← `ACLCA` | 失敗，`CERT_SIGNATURE_FAILURE`；加 `--use-system-ca` 改用 Windows 憑證庫仍失敗 |
| `api.cloudflare.com`、`dash.cloudflare.com`、`logging.googleapis.com`、`oauth2.googleapis.com` | Google Trust Services | 通過 |

判讀：公司的 TLS 檢查代理只解密 `*.workers.dev`，所以 wrangler 的部署與查詢指令（走 `api.cloudflare.com`）不受影響，tail 與 curl 受影響。開始攔截的時間介於 03:23Z（第 0 步的 tail 還能連）與 04:2xZ 之間，確切時間不知道。**沒有以關閉憑證驗證的方式繞過**。

影響：

- 上表的未登入檢查以 `curl --ssl-no-revoke` 執行：只略過撤銷清單查詢，憑證鏈與主機名稱照常驗證。這些回應經過公司代理。內容（302、143 bytes、導向 `khlin.cloudflareaccess.com`）與直連時相同，但嚴格說不是直連取得的。
- 使用者瀏覽器連 `finpo` 的流量同樣會被公司代理解密，代理看得到 Access 的 cookie 與頁面上的持股。第一階段是假持股（`D5`），這是公司網路政策而非本專案的缺陷，但放真實持股前要考慮。
- 第 5 步改以 Cloud Run 請求日誌取代 tail，CPU 時間與 Worker 的 log 改由儀表板取得。

### 第 5 步：正向核對

使用者在瀏覽器重新整理頁面，頁面正常顯示持股總覽。Claude 以 `gcloud logging read` 查 Cloud Run 請求日誌：

| 時間（UTC） | 請求 | Cloud Run 狀態 | 後端延遲（s） | revision |
|---|---|---|---|---|
| 04:25:27 | GET `/api/session` | 200 | 3.343 | `stock-quote-00004-4v6` |
| 04:25:31 | GET `/api/portfolio` | 200 | 0.185 | 同上 |
| 04:25:32 | GET `/api/portfolio/valuation?market=ALL` | 200 | 0.096 | 同上 |

- **新程式在雲端以真實 Access token 驗證通過並簽章**。04:17:09Z 之後 100% 的流量都在 `474e5c4f`，所以這 3 筆是新程式處理的；它們抵達 Cloud Run 並得到 200，代表 Worker 驗過簽章、`iss`、`aud`、`exp`，`email` 也在白名單內，然後簽了 HMAC。**第 1 步的 AUD 至此在雲端得到證明**；jose 在 workerd 上取 JWKS 也成立。
- 04:17Z 到 04:25Z 之間沒有其他紀錄：上面的未登入請求都停在 Access。
- 第一筆 3.34 秒推定是冷啟動（`C7-7` 量得 2.3–3.4 秒），沒有另外核對。
- **查詢本身的正向對照**：同一條查詢查得到第 0 步 03:23Z 的 3 筆。查詢條件第一次寫成 batch 檔時，`call` 把 `%%2F` 展開了兩次，`%2` 被當成第二個參數吃掉，條件被靜默改壞，回 0 筆。改用 `log_id(run.googleapis.com/requests)` 避開 `%` 之後才查到。這是 R4 節「引號陷阱」之外，`cmd` 的另一個靜默回 0 筆的坑。

~~**本步還沒做的**：~~

- ~~驗簽的 CPU 時間：tail 不能用，改由使用者看儀表板的 Metrics。~~ 同日已由 tail 量得，見下。
- Worker 的 `console.log` 能不能看到：正向請求不會寫 log，留到第 6 步。

**CPU 時間（同日補記）**。使用者先切到手機熱點，結果 `*.workers.dev` 仍由 `prisma-advantech.com` 簽發。推定解密的是筆電上的代理程式，而不是公司網路，所以換網路無效；這是推論，沒有查代理程式本身。之後再檢查一次，`tail.developers.workers.dev` 與 `finpo.drhiromu.workers.dev` 改由 Google Trust Services、Let's Encrypt 簽發，Node 驗證通過，才開 tail。使用者重新整理頁面：

| 時間（UTC） | 請求 | 狀態 | CPU（ms） | wall（ms） | 版本 |
|---|---|---|---|---|---|
| 04:37:15 | GET `/api/session` | 200 | 3 | 822 | `474e5c4f` |
| 04:37:15 | GET `/api/portfolio` | 200 | 3 | 161 | 同上 |
| 04:37:16 | GET `/api/portfolio/valuation` | 200 | 2 | 138 | 同上 |

- 3 筆都帶 `cf-access-jwt-assertion`，沒有 log、沒有例外。
- **驗 JWT 之後的 CPU 時間是 2–3 ms，Free 方案的上限是 10 ms**。第 0 步的舊程式是 2 ms，首次分段部署第 4 步是 1 ms 以內。
- 界線：tail 只給整數 ms，只有 3 筆，而且看不出這個 isolate 有沒有在這次請求裡抓 JWKS、匯入公鑰，所以**單獨的驗簽成本沒有量出來**，只能說增加量在個位數 ms 以內。5 MiB 上傳時的 CPU 時間仍未量（`C7-2` 承接）。

### 第 6 步：雲端反面測試（preview URL）

做法：上傳不部署的版本，每個版本只改一個設定，由使用者在瀏覽器（已登入）打開該版本的 preview URL。每次上傳後，Claude 先以 `deployments status` 確認正式流量沒有移動，才請使用者打開。

| 子步 | 版本 | 怎麼產生 | 改了什麼（`versions view` 核對） | 頁面 | Cloud Run |
|---|---|---|---|---|---|
| 6a | `294d9efc-4efd-46f4-9392-5831115a71da`，04:39:18Z | `versions upload --var ACCESS_AUD:c7-8-wrong-audience` | `ACCESS_AUD` 為 `c7-8-wrong-audience`，兩個 secret 都在 | 「登入身分未通過驗證」 | **沒有紀錄** |
| 6b | `6fa94819-1ebd-499e-82c7-3a34568977f8`，04:47:04Z | `versions upload --secrets-file`，檔案只有 `ACCESS_ALLOWED_EMAILS: nobody@example.test` | `ACCESS_AUD` 正確，兩個 secret 都在（值讀不回來） | 「登入身分未通過驗證」 | **沒有紀錄** |
| 6c | `f6b74704-797e-4d3d-bf75-d2c1feedde13`，04:51:36Z | `versions secret put ACCESS_ALLOWED_EMAILS`，使用者以互動提示放回正確的值 | `ACCESS_AUD` 正確，兩個 secret 都在 | **正常顯示持股總覽** | 05:02:08–14Z 3 筆 200（`/api/session` 3.749 s，推定冷啟動；`/api/portfolio`；`/api/portfolio/valuation`） |

- 「登入身分未通過驗證」是 Worker 的 403 `access_denied` 訊息（500、503 的訊息不同），所以 6a、6b 都是 Worker 拒絕，不是 Access 或後端。
- **6a、6b 都沒有轉發**：Cloud Run 從 04:42:19Z 到 05:02:08Z 之間沒有任何紀錄。
- 6c 的 3 筆 200 來自 preview URL：開著的正式主機 tail 在 05:02 沒有記到請求。
- **tail 在這段期間是否連著**：兩個 tail（未指定版本的、`--version-id 294d9efc` 的）都不是跑到 30 分鐘時限才結束，而是在 **05:04:56Z** 以 `CERT_SIGNATURE_FAILURE` 退出（輸出檔的最後寫入時間），也就是公司代理又接回 `*.workers.dev` 的時候。使用者在 05:02 打開 6c 之後才問能否切回公司網路，時間上一致。斷線時間晚於 05:02:14Z 的 6c 請求，也晚於使用者重新整理 6a preview URL 的時間（04:47 上傳 6b 之前），所以上面「05:02 正式主機沒有請求」與下面「preview 的請求不進 tail」兩個判讀都成立。界線：wrangler 只在重新連線時報錯，若連線在 05:04:56Z 之前已經靜默停住，這裡看不出來。

**403 的原因是以對照組推得的，不是從 log 讀到的**。原本打算從 tail 讀 `console.log` 的失敗類別，但 preview URL 的請求**沒有進入 `wrangler tail`**：沒指定版本的 tail 只記到正式主機，加了 `--version-id 294d9efc…` 的 tail 在使用者重新整理 preview URL 時一筆都沒記到。這是觀察，沒有找到文件說明原因。改為：6c 與 6a、6b 在同一種主機（preview URL）、同一個登入下，只有設定全部正確，結果回 200。這證明 preview 主機也會帶 `Cf-Access-Jwt-Assertion`，`aud`、`email` 也對得上。因此 6a 的 403 歸因於 AUD 不符，6b 的 403 歸因於 `email` 不在白名單。第 0 步擔心的「preview 上因沒有 JWT 而被擋、測試白做」由此排除。**Worker 的 `console.log` 在雲端能不能看到，仍未確認**：正向請求不寫 log，preview 的請求又不進 tail。

**第 2 步的未核對項目至此補齊**：

- `versions upload` 不部署，並產生 preview URL（輸出有 `Version Preview URL`）。`--var` 的值在上傳輸出中顯示為 `(hidden)`，`versions view` 看得到。
- `versions secret put` 同樣只建立版本、不部署，來源為 `create_version_api`。
- 6a、6b、6c 期間正式流量都是 `474e5c4f` 100%。

**收尾**：6c 讓最新的版本帶回正確的白名單。版本的 secret 推定繼承自最新的版本，沒有核對；6c 就是為了避免下次 `wrangler deploy` 把假名單帶進正式環境。`f6b74704` 與正式的 `474e5c4f` 程式相同，設定也相同。6a、6b 的版本仍留在版本清單中，preview URL 受 Access 保護，而且它們對 `/api` 一律回 403，沒有刪除。

**雲端沒有做的反面案例**：沒有 JWT、簽章錯誤、已過期。Access 正常運作時，這些請求到不了 Worker，設計時已決定只以 Node 測試（`tests/worker.test.mjs`）為證據。

**其他觀察**：

- `/favicon.ico` 在 preview URL 回 404：沒有對應的靜態檔，回落到 Worker，Worker 對 `/api` 以外的路徑一律回 404，與首次部署的記錄相同。
- 04:42:19Z 正式主機有 3 筆 200（`474e5c4f`），時間在使用者打開 6a 的 preview URL 前後，來源（重新整理正式網址，或另一個分頁）沒有確認。

## C7-3　入口驗證（2026-10-02 起，~~進行中~~ 10-03 完成，使用者決定勾選）

項目拆分與使用者的決定見計畫書 `C7-3` 項下 10-02 補記。

### `C7-3-1`：繞過代理（2026-10-02 06:07:52–06:08:00Z）

從公司網路以 `curl` 發出。偽造的簽章是 64 個 `a`，偽造的 JWT 是格式正確、簽章無效的字串。

| # | 請求 | 回應 | Cloud Run 請求日誌 |
|---|---|---|---|
| A1 | `run.app` `GET /api/session`，不帶簽章 | 401 `unauthorized` | 401 |
| A2 | `GET /api/portfolio/valuation`，不帶簽章 | 401 | 401 |
| A3 | `PUT /api/portfolio`，不帶簽章 | 401 | 401 |
| A4 | `POST /api/portfolio/refresh`，不帶簽章 | 401 | 401 |
| A5 | 偽造簽章，時間戳為現在 | 401 | 401 |
| A6 | 偽造簽章，時間戳為一小時前 | 401 | 401 |
| A7 | 不帶簽章，但帶偽造的 `Cf-Access-Jwt-Assertion`、`Cf-Access-Authenticated-User-Email`、`X-Forwarded-For`、`X-Forwarded-Host`，以及白名單內的 `Origin` | 401 | 401 |
| A8 | 舊式網址 `stock-quote-nfmyvudecq-an.a.run.app` | 403 `拒絕不合法的 Host` | 403 |
| B1 | Worker `/`，未登入 | 302 導向 Access | 沒有紀錄 |
| B2 | Worker `/api/session`，未登入 | 302 | 沒有紀錄 |
| B3 | Worker `/api/session`，帶偽造的 `Cf-Access-Jwt-Assertion` 與 `CF_Authorization` cookie | 302 | 沒有紀錄 |

- 日誌中這段時間恰好 8 筆，都在 revision `00005-pzn`，對應 A1–A8。往前 30 分鐘內沒有其他請求，所以 B1–B3 沒有到達 Cloud Run，是在 Access 就被擋下。
- **A7 證明後端不信任 Access 或轉送的標頭**：帶上 Access 才會加的標頭也沒有用，關卡只有 HMAC 簽章（`C2-2` 決定代理標頭一律不信任）。
- **A3、A4 是寫入**：被擋在 `Guard`，沒有進到處理程式。持股文件沒有讀出比對，依據是 401 由 `Guard` 回傳的程式路徑。
- **B3**：偽造的 Access cookie 過不了 Access，所以 Worker 的 JWT 驗證（`C7-8`）這次沒有被碰到。Worker 那一層的反面測試在 `C7-8` 第 6 步做過。
- **界線**：沒有做「拿到真的簽章後重放」的測試。簽章綁定方法、路徑、body 雜湊與時間戳，時間窗 ±60 秒，這是讀程式與 `C3` 的單元測試得出的，沒有在雲端實測重放。

### `C7-3-2`、`C7-3-3`：無痕視窗與未授權帳號（使用者操作，2026-10-02 約 14:50–15:05 台北）

| 項 | 使用者回報 | 判定 |
|---|---|---|
| `C7-3-2` 無痕視窗開 `finpo` | 先導向 Access 登入頁，再到 Google 登入頁；**整個過程沒有看到任何持股頁面的內容** | ✅ |
| `C7-3-3` 以第二個 Google 帳號完成 Google 登入 | 回到 Access 頁面，顯示「That account does not have access」 | ✅ |

**更正（同日）**：使用者回報時另附了 `2026-10-03T02:37:24.679Z`，本節原本把它記成「頁面上的時間」、把日期記成 10-03。這個時間比當下（10-02 約 07:05Z）晚了 19.5 小時，不可能是被拒絕的時刻；它與隨後讀到的 `CF_Authorization` 到期時間 `02:37:27.405Z` 只差 3 秒，推定是誤貼了 cookie 的到期時間。已把日期改回 10-02，並刪去該時間。

- **`C7-3-3` 是 Access 擋的，與計畫書的推定不同**。計畫書推定 OAuth 應用程式在 Testing 模式、這個帳號不在 Test users 內，所以 Google 會在第一關擋下，Access policy 測不到。實際上這個帳號通過了 Google，由 Access policy 拒絕，所以**入口的 Access 那一層有實測到**。Google 為什麼放行，**沒有查證**：可能這個帳號本來就在 Test users 內，或是 OAuth 應用程式的發佈狀態不是 Testing。這不影響本項判定，但關係到 `CLAUDE.md` 寫的「Access policy、`ACCESS_ALLOWED_EMAILS`、Google 的 Test users 三處都要加」是否三處都真的在把關。**同日補記**：使用者確認 OAuth 應用程式的狀態是 Testing。先前曾想 publish，但需要可驗證的網域等條件，`workers.dev` 無法驗證，所以沒有 publish。這排除了「不是 Testing」的可能，剩下的解釋是這個帳號本來就在 Test users 內，**尚待使用者核對名單**。若不在名單內，就代表 Google 那一層實際上沒有把關，`CLAUDE.md` 的說明要修正。**同日再補記：使用者核對，這個帳號不在 Test users 名單內。** 所以 **Google 的 Test users 實際上沒有擋下名單外的帳號**，入口的關卡只有 Access policy 與 Worker 的 `ACCESS_ALLOWED_EMAILS`（`C7-8`）兩層。已修正 `CLAUDE.md`：放行新的人時，必加的是這兩處；Test users 照舊加上，但不再寫成「少了就進不來」。Google 為何放行，**原因未查**。候選有二：這個帳號在 GCP 專案上有角色，或是 Google 對只要求 openid／email 等基本範圍的應用程式不強制執行 Test users 限制。兩者都沒有查證。

**與 `C1-6` 的紀錄衝突（同日發現）**：C1 證據記錄，09-17 有一個名單外的帳號被 Google 擋下（`Access blocked: ... has not completed the Google verification process`）。所以第二個候選與那筆紀錄不合，Google 那一層不是完全不擋，而是**有時擋、有時不擋**。因此多了第三個候選：同一份紀錄寫明 09-17 反面測試所用的帳號當時**在** Test users 內。若今天用的是同一個帳號、後來才被移出名單，Google 可能沿用了當時的授權，沒有重新檢查名單。三個候選都沒有查證。`CLAUDE.md` 據此改寫為「不能依賴它把關」，而不是「它不是關卡」。**同日再補記**：使用者確認今天的帳號與 09-17 的**不是同一個**，所以第三個候選若要成立，只能是這個帳號自己曾在名單內、後來被移出，沒有紀錄可以佐證。剩下的候選是：這個帳號在 GCP 專案上有角色；它曾在名單內；Google 的行為與 09-17 不同。都沒有查證。
- 帳號沒有寫進本檔，repo 為 public。
- 判定依據只有使用者的回報。Access 的拒絕沒有從 Zero Trust 的 Access 日誌核對；請求沒有到達 Worker，所以 tail 也看不到。

### `C7-3-4`：閒置到縮容且後端 token 過期後，不重新整理直接操作（2026-10-02 15:09–16:26 台北）

使用者在 15:09 重新整理 `finpo`，分頁開著不動，16:25 直接按「更新報價」。這次刻意在 Access session 到期（10-03 10:37 台北）之前做，所以只有後端 token 過期，Access 沒有過期。Cloud Run 的請求日誌與系統日誌（revision `00005-pzn`）：

| 時間（UTC） | 事件 | 說明 |
|---|---|---|
| 07:09:49.83 | `GET /api/session` 200 | 重新整理，取得後端 token |
| 07:09:50.50 → 08:25:46.49 | **沒有任何請求** | 閒置 76 分鐘 |
| 08:25:46.49 | `POST /api/portfolio/refresh` **403**，358 bytes，3.947 s | token 已 75.9 分鐘，超過 `SESSION_TTL` 3600 秒 |
| 08:25:46.51 | `Starting new instance. Reason: AUTOSCALING` | **冷啟動**。max 為 1，新實例啟動代表原本的實例已縮容 |
| 08:25:50.67 | `STARTUP TCP probe succeeded` | 約 4.2 秒，與 403 的耗時相符 |
| 08:25:51.01 | `GET /api/session` 200 | 前端自動重取 session |
| 08:25:51.30 | `POST /api/portfolio/refresh` **200**，15.685 s | 重試成功 |
| 08:26:07.27 | `GET /api/portfolio/valuation` 200 | 更新完成後重新讀取估值 |

- **判定：✅**。這是 `C3` 雲端完成條件的前半「閒置至服務縮容後再操作，不需手動重新整理即可繼續使用」，三個條件同時成立：縮容、後端 token 過期、沒有重新整理。C7-4 期間的兩個附帶觀察各只碰到其中一部分。
- **403 是 `session_expired`，是推得的**：回應內容沒有讀出。依據有二：`app.js` 只在 401／403 且 `code` 為 `unauthorized` 或 `session_expired` 時重取並重試，而 `Guard` 對 `unauthorized` 回的是 401；大小 358 bytes，與 C7-4 那次推定為 `session_expired` 的 403 相同。
- **沒有重新整理，也是推得的**：重新整理時，頁面會依序打 `session`、`portfolio`、`valuation`，這次在 `session` 之後是重試的 `refresh`，沒有 `GET /api/portfolio`。
- 403 本身就包含了冷啟動：第一個請求觸發新實例，3.9 秒後被驗證擋下。冷啟動與 token 過期在同一個請求裡被處理掉，使用者只多等了約 5 秒。
- Access session 過期的那一半在 `C7-3-5`。
- 使用者回報的畫面：「報價涵蓋 2 / 2 檔」「降級估值 · 請參閱逐股品質」，工作訊息「已完成：2/2 檔有可用報價」。

### `C7-3-5`：Access session 自然過期後的恢復（2026-10-03 09:55–11:00 台北）

前一個 session 在 10-02 約 02:37Z 登入，`CF_Authorization` 的到期時間是 10-03 02:37:27Z（台北 10:37）。使用者在到期前打開頁面、改了匯率但不儲存，過了到期時間後不重新整理，直接按儲存。

| 時間（UTC） | 來源 | 事件 |
|---|---|---|
| 01:55:17–01:55:22 | Cloud Run | `session`、`portfolio`、`valuation` 都是 200，有冷啟動。到期前打開頁面，沒有重新登入 |
| 01:55:22 → 02:51:17 | Cloud Run | **沒有任何請求**。到期後按儲存的那一下沒有到達 Cloud Run，是在 Access 被擋下 |
| 02:51:13 | `CF_Authorization` 的新到期時間 `2026-10-04T02:51:13.543Z` 減 24 小時 | Access 重新登入 |
| 02:51:17–02:51:22 | Cloud Run | `session`、`portfolio`、`valuation` 都是 200，有冷啟動。**這組請求只在頁面初次載入時發出**（`app.js` 只在初始化時 `GET /api/portfolio`），所以頁面重新載入了 |
| 03:00:33 | Cloud Run | `PUT /api/portfolio` **200**，接著 `valuation` 200 |

使用者回報：按儲存後**沒有察覺頁面重新載入**，也沒有出現登入畫面；回到頁面時匯率是改過的值，狀態列顯示「有未保存的修改 · 總覽仍使用已保存清單」；再按儲存，匯率已保存。

- **判定：✅**。這是 `C3` 雲端完成條件的後半。Access 過期後，前端偵測到轉址、整頁重新載入、經 Access 重新登入，未儲存的草稿恢復，之後可以正常儲存。
- **草稿恢復的依據**：重新載入時，`app.js` 先把匯率欄設成伺服器上已保存的值，只有在 sessionStorage 有 `portfolio-login-draft` 時才換回草稿的值。重新載入後看到的是改過的匯率，所以恢復機制有作用。
- **沒有觀察到的**：恢復時會顯示的「已恢復登入前的草稿，請確認後儲存。」提示，使用者當下沒有注意，事後也想不起來。「有未保存的修改」是 `setDirty()` 的狀態列，有沒有重新載入都會出現，所以不能拿來佐證恢復。
- **使用者感覺不到重新載入**：Google 的登入仍有效，Access 自動完成重新認證，不需要點任何東西。從按下到頁面回來的時間沒有量；Cloud Run 端第一個請求含冷啟動，耗時 3.1 秒。
- **Access session 長度**：10-02 與 10-03 兩次都是登入後恰好 24 小時到期，推定為 24 小時。Zero Trust 儀表板上的設定沒有核對。
- **界線**：Google 的登入也過期時，要多一次 Google 登入，這次沒有碰到；重新載入有 60 秒的冷卻（`resumeLogin`），這次沒有碰到。這是 `842becc` 部署後第一次在雲端看到的工作訊息；兩檔都處理到了，所以維持原本的格式，新加的說明沒有出現，也不該出現。

## C7-4　功能驗收（~~進行中~~ 10-02 完成，使用者決定勾選）

清單、測試資料與執行順序見計畫書 `C7-4` 項下 10-01 補記。瀏覽器操作由使用者執行；Cloud Run 請求日誌由 Claude 以 `log_id(run.googleapis.com/requests)` 唯讀查詢。查詢腳本用 Windows PowerShell 5.1，過濾條件內的雙引號寫成 `\"`（裸雙引號會被吃掉，第一次查詢就因此回 `Unparseable filter`）。Worker 版本 `474e5c4f`，Cloud Run revision `stock-quote-00004-4v6`。

### 第 0 項：持股為空時按「更新報價」（2026-10-01 13:50 台北）

使用者打開 finpo，頁面顯示「已保存版本 5」、持股為空。這是計畫書推定的狀態（`C7-6` 收尾 `reset` 之後），**至此以畫面核對**。按「更新報價」後，畫面顯示「請先保存持股。」

請求日誌，05:40–06:00Z：

| 時間（UTC） | 請求 | 狀態 | latency |
|---|---|---|---|
| 05:49:28.44 | GET `/api/session` | 200 | 3.850 s |
| 05:49:32.81 | GET `/api/portfolio` | 200 | 0.166 s |
| 05:49:33.08 | GET `/api/portfolio/valuation?market=ALL` | 200 | 0.091 s |
| 05:50:10.51 | POST `/api/portfolio/refresh` | 400 | 0.088 s |
| 05:50:44.97 | POST `/api/portfolio/refresh` | 400 | 0.085 s |

- **通過**：畫面訊息正確，請求有經 Worker 抵達後端並回 400。前三筆 GET 是同一時段的正向對照，證明這條查詢沒有因過濾條件寫錯而漏掉請求。
- **回 400 的就是「請先保存持股」這條路徑**：這是讀程式推得的。`refresh()` 在 claim 之前，只有空持股這一條會回 400；驗簽、`Origin`、session 失敗回的是 401／403。日誌不記錄回應內容。
- **沒有寫 job**：程式在 claim 之前就拒絕，這是**讀程式推得的，沒有以資料庫核對**。refresh_jobs 的筆數，留到本項結束時以一次唯讀查詢一併核對。**同日補記：已核對**。C7 之後列出 refresh_jobs 的全部 3 筆，最早一筆是 B1 的 07:09:10Z，05:50 前後沒有任何 job。見「C7」節。
- **有兩筆 POST，相隔 34 秒**。是否都是使用者按的，待確認。第二筆同樣回 400，與冷卻無關，因為空持股的檢查在冷卻之前。
- `/api/session` 的 3.85 秒推定包含冷啟動，比 `C7-7` 量到的 2.3–3.4 秒長；沒有查實例的啟動紀錄，所以不當成冷啟動的量測值。

### A4／A4b：前端與 Worker 的大小、副檔名檢查（2026-10-01 約 14:00–14:10 台北）

測試檔由 `scripts/c74_fixtures.py`（`a8a5b99`）產生：

| 檔案 | bytes | SHA-256 |
|---|---|---|
| F5 剛好 5 MiB.xlsx | 5,242,880 | `be7fb7bb661867d1d984d4e509fdebef287d3200fbe16e81a7e1d3f891ae763f` |
| F6 超過 5 MiB.xlsx | 5,242,881 | `83a436f74e025d4c8455e750db9dc8422de8519ec1dc379cbddaf3405a2ee7c0` |

**tail 在這段期間斷線**。約 05:52Z（台北 13:52）開的 `wrangler tail`，在 05:53:17Z 查看時已以 `CERT_SIGNATURE_FAILURE` 結束；以 `tls.connect` 讀 `tail.developers.workers.dev` 的憑證，簽發者是 `Advantech`／`prisma-advantech.com`，與 `C7-8` 第 6 步記錄的公司代理解密相同。06:12Z 重查時仍是如此。沒有以關閉憑證驗證的方式繞過（讀簽發者的那次連線只讀憑證，沒有送出資料）。因此本節**沒有任何 Worker 端的紀錄**。

使用者回報：四個步驟都依測試邏輯做了，畫面與 Console 的結果都如預期；**順序沒有嚴格照 1→2→3→4**。步驟 3 在 Console 印出 `ERR 檔案不得超過 5 MiB。`。

請求日誌，05:49–07:00Z，第 0 項之後：

| 時間（UTC） | 請求 | 狀態 | latency |
|---|---|---|---|
| 05:55:45.10–45.53 | GET `session`、`portfolio`、`valuation` | 200 | — |
| 05:55:46.42–47.14 | GET `session`、`portfolio`、`valuation` | 200 | — |
| 06:06:19.08 | POST `/api/imports/preview` | **400** | 0.003 s |
| 06:10:23.82 | POST `/api/imports/preview` | 200 | 0.617 s |

| 項目 | 結果 | 依據與界線 |
|---|---|---|
| A4 非 `.xlsx` 被前端擋下 | ✅ | 畫面顯示「請選擇不超過 5 MiB 的 .xlsx 檔案。」。這句只出現在 `app.js` 的 `onchange` 裡、`upload()` 之前就 `return` 的分支，所以出現這句就代表沒有發出請求。**這是讀程式推得的**：使用者沒有回報 Network 分頁，Cloud Run 也無法排除請求只到 Worker 的情況 |
| A4 F6 被前端擋下 | ✅ | 同上 |
| A4b F6 由 Worker 回 413 | ✅ | Console 印出 413 的訊息。同一段時間的 Cloud Run 日誌**沒有任何 413**，而後端的 `body_bytes` 也會回同一句、狀態同為 413，所以這不是後端回的，是 Worker 回的。同一條查詢查得到 06:06、06:10 兩筆 POST，可當作正向對照 |
| A4b F5 的 CPU 時間 | ~~⬜ 未取得~~ **10-02 已量到：14 ms，超過 Free 的 10 ms，但請求沒有被終止** | 06:10:23 的 200 推定是 F5 的預覽，後端耗時 0.617 秒。tail 斷線，Worker 的 CPU 時間沒有記到，待 tail 恢復後重傳 F5 再量。**10-02 補記**：見下方「A4b 補記：F5 的 CPU 時間」節 |

**06:06:19 的 400 原因未確認**。依程式，這條路徑在後端回 400 的情況有三種：檔名不是 `.xlsx`、`Content-Length` 不是整數、body 長度與 `Content-Length` 不符。後兩者在瀏覽器經由 Worker 送出時推定不會發生，所以最可能是有一次從 Console 送出的檔案不是 `.xlsx`。原因有兩點：使用者說順序沒有照走，而 `$('file').files[0]` 會停留在最後一次選的檔案，包括被前端擋下的檔案。只花 3 ms 也與「讀完 body、名稱檢查就失敗」相符。這是推論，使用者沒有逐步記錄，所以**不排除其他原因**。它不影響上表的判定：F6 的 413 有 Console 的原文，也沒有對應的 Cloud Run 紀錄。

05:55 的兩次頁面載入，以及第 0 項的兩次更新，是不是都由使用者操作，都沒有確認。

### A1–A3：上傳預覽、中文工作表、儲存時才擋下的代碼（2026-10-01 約 14:50–14:58 台北）

使用者回報 A1–A3 都如預期：
- A1：F1（`持股範本.xlsx`）預覽 27 列、沒有錯誤，按取消。
- A2：F2（SHA-256 `a9a650967a84c59b618a2b17ba3ea0836f1a443557953344171e77ab07f3bd91`）三張工作表的錯誤與內容都正確。
- A3：套用「無法識別代碼」後儲存，顯示無法識別並指出 ZZZZ9；重新整理後仍是版本 5、持股為空。
- 使用者沒有逐步記錄時間。

請求日誌，06:11–08:00Z：

| 時間（UTC） | 請求 | 狀態 | latency |
|---|---|---|---|
| 06:50:42.39 | GET `/api/session` | 200 | 3.065 s |
| 06:50:46.04–46.38 | GET `portfolio`、`valuation` | 200 | — |
| 06:52:28.73 | POST `/api/imports/preview` | 200 | 0.513 s |
| 06:53:15.66 | POST `/api/imports/preview` | 200 | 0.522 s |
| 06:54:01.00 | POST `/api/imports/preview` | 200 | 0.522 s |
| 06:54:10.34 | POST `/api/imports/preview` | 200 | 0.522 s |
| 06:55:50.08 | POST `/api/imports/preview` | 200 | 0.489 s |
| 06:55:52.27 | POST `/api/imports/preview` | 200 | 0.486 s |
| 06:56:30.07 | PUT `/api/portfolio` | 400 | 0.897 s |
| 06:57:42.91–43.30 | GET `session`、`portfolio`、`valuation` | 200 | — |

| 項目 | 結果 | 依據與界線 |
|---|---|---|
| A1 | ✅ | 畫面與 preview 的 200 |
| A2 中文 `X-Upload-Sheet` 的轉發與驗簽 | ✅ | 切換工作表後，畫面顯示的是另一張的內容。內容只能來自帶 `X-Upload-Sheet` 的 preview 回應，而期間所有 preview 都是 200，沒有 401／403。**預覽一共 6 次**，依步驟預期是 4 次（A1 一次，F2 開檔一次，切換兩次），哪一筆對應哪一步無法從日誌分辨，日誌不記錄標頭。多出的 2 次推定是重新選檔或切回同一張，沒有確認 |
| A3 儲存時回 400、整份不存 | ✅ | PUT 回 400，重新整理後畫面為版本 5、持股為空。0.897 秒比 preview 長，與「讀官方清單再比對」相符，但沒有拆開量測 |
| A5（日誌不含檔名） | 待做 | 留到 B1 之後一併查 |

**附帶觀察（B5，尚未正式驗收）**：A3 第 7 步重新整理時，使用者表示**沒有出現「離開網站？」的確認**。依 `app.js`，套用預覽時會呼叫 `setDirty()`，儲存失敗不會清除 `dirty`，`beforeunload` 的處理器在 `dirty && !loginRedirecting` 時會呼叫 `preventDefault()`，所以預期應該要出現確認。~~是否為缺陷還不能判定，待確認的有：瀏覽器、重新整理的方式、確認框的標題、重新整理前是否顯示「有未保存的修改」。~~

**同日補記：不是缺陷，是 Claude 的指示寫錯了字樣**。使用者回報：瀏覽器是 Chrome，按的是重新整理按鈕，跳出的確認框標題是「要重新載入網站嗎？」。Chrome 在重新整理時用這個標題，關閉分頁或離開頁面時才用「離開網站？」，而 Claude 的步驟寫的是後者。由此 **B5 ✅**（Chrome、重新整理按鈕）。界線有兩點：
- 計畫書 B5 寫的是「關閉分頁」，這個變體沒有測。兩者走的是同一個 `beforeunload` 處理器，推定行為相同。
- 回報沒有區分這次確認框是出現在 A3 第 7 步，還是事後重現的那一次。

### B1、C1、C2、B2：儲存 F1 與第一次更新報價（2026-10-01 15:08–15:11 台北）

使用者上傳 F1 並套用、儲存。依 `app.js`，儲存成功後若涵蓋不足會自動更新報價，所以 C2 隨 B1 開始（計畫書同日補記）。台股與美股當時都休市。tail 仍被公司代理攔截（07:06Z 重查，簽發者 `Advantech`），本節沒有 Worker 端的紀錄。

請求日誌：

| 時間（UTC） | 請求 | 狀態 | latency |
|---|---|---|---|
| 07:08:44.89–45.32 | GET `session`、`portfolio`、`valuation` | 200 | — |
| 07:08:54.64 | POST `/api/imports/preview` | 200 | 0.543 s |
| 07:09:07.89 | PUT `/api/portfolio` | 200 | 0.876 s |
| 07:09:08.92 | GET `/api/portfolio/valuation?market=ALL` | 200 | 0.913 s |
| 07:09:10.04 | POST `/api/portfolio/refresh` | 200 | **110.653 s** |
| 07:11:00.91 | GET `/api/portfolio/valuation?market=ALL` | 200 | 1.060 s |

`refresh` 的回應（使用者從 Network 分頁複製；只有工作的中繼資料，沒有持股內容）：`job_id` `1cf7ef80-549b-4545-a2d7-9eb36810cdb5`、`portfolio_revision` 6、`status` `partial`、`message`「已完成：26/27 檔有可用報價」、`created_at` 07:09:10.304Z、`completed_at` 07:11:00.573Z。Chrome 顯示的耗時為 1.8 min。

抓價紀錄由使用者在 Supabase SQL Editor 執行唯讀查詢取得（只有 `SELECT`，輸出不含代碼）：

| 批 | 市場 | 檔數 | 起訖（UTC） | 牆鐘 | 每檔 | 其後空檔 |
|---|---|---|---|---|---|---|
| 1 | TW | 5 | 07:09:12.412–36.480 | 24.07 s | 4.81 s | 0.46 s |
| 2 | US | 5 | 07:09:36.939–56.512 | 19.57 s | 3.91 s | 0.46 s |
| 3 | US | 5 | 07:09:56.969–07:10:15.522 | 18.55 s | 3.71 s | 0.42 s |
| 4 | US | 5 | 07:10:15.940–34.325 | 18.39 s | 3.68 s | 0.47 s |
| 5 | US | 5 | 07:10:34.797–53.692 | 18.90 s | 3.78 s | 0.43 s |
| 6 | US | 2 | 07:10:54.124–07:11:00.430 | 6.31 s | — | — |

成功的嘗試為 26／27。唯一失敗的一筆是美股，attempt 1，`status=timeout`、`error_code=timeout`，07:10:57.824→07:11:00.244，`elapsed_ms` 2373；它的估值為 `missing_quote`，旗標為空。

| 項目 | 結果 | 依據與界線 |
|---|---|---|
| B1 儲存 | ✅ | PUT 200，job 的 `portfolio_revision` 為 6。`names` 與 `instruments` 有沒有寫入沒有直接讀出；之後的估值與更新都用得上它們，這是間接證據 |
| C1 存後、更新前全部缺價 | ✅ | 使用者回報：涵蓋 0/27、每列「缺少可用價格」、顯示更新中的提示 |
| C2 更新完成、總覽同步 | ✅ | 回應 200、`partial`；畫面顯示「報價涵蓋 26 / 27 檔」，以及 TWD 5/5、USD 21/22 的小計；完成後重新讀取了估值（07:11:00.91 的 GET） |
| C2 端到端在 125 秒內 | ✅ | Cloud Run latency 110.653 s，餘裕 14.3 s。實例在 07:08:44 就已經在回應（`session` 只花 3 ms），**不含冷啟動**；冷啟動時的餘裕會少 2–4 秒（`C7-7`） |
| B2 未填匯率 | ✅ | 品質欄顯示「待輸入匯率」 |
| D3 品質欄 | 已記錄 | 出現三種：「快取、休市」、「快取、休市、交易時段未知」、「缺少可用價格」。台股報價時間 13:30:03–13:30:11，美股 04:00:00–04:00:02（台北）。「交易時段未知」與 R3 記錄過的規則一致：成交時間晚於收盤 5 秒以上就會標上。**只記錄、不判定** |

**發現：27 檔的上限在 F1 上沒有守住 110 秒，最後一檔被預算截短**。

- **判定依據**：deadline 從 `run_job` 開始起算，job 的 `created_at` 是 07:09:10.304，所以 deadline 約在 07:11:00.3。失敗那一筆在 07:11:00.244 結束，只跑了 2.37 秒；同場其他美股每檔要 3.7–3.9 秒，單次呼叫的上限是 10 秒（`operation_timeout_seconds`）。可見它分到的時間是剩下的預算，不是單次上限。`error_code` 是 `timeout` 而不是 `cycle_budget_exhausted`，因為它開始時預算還沒用完（`quoting.py` 只在開始前就沒有預算時，才記 `cycle_budget_exhausted`）。**「給它完整的時間就能成功」是推論**，沒有驗證。
- **為什麼 27 不夠**：27 是 `floor((110 − F) ÷ c)`，其中 `c` 取 R5 的 3.967 秒／檔（Job、只有台股、第 1 批含暖機）。本場在正式路徑上量到的數字比它大：
  - 台股第 1 批是 4.81 秒／檔；
  - 美股是 3.68–3.91 秒／檔；
  - 批與批之間的空檔約 0.45 秒（R5 是 0.21–0.26 秒）；
  - `F` 為 2.11 秒（07:09:10.304 → 07:09:12.412；R5 為 1.470）。
  
  依本場的數字，27 檔約需 111 秒。R5 只有台股，使用者 09-29 決定接受這一點，美股的單檔成本以 R3、R4 為旁證；本場是**美股單檔成本在正式路徑上的第一次量測**。
- **`C7-6` 留下的覆核（Job 與正式服務走同一個出口）：沒有結論**。本場的單檔成本比 R5 高，但市場組成不同、時段不同、只有一場，分不出差異是出口造成的，還是組成與變異造成的。
- **訊息的缺口**：`run_job` 只有在**整批來不及開始**時（`cut`）才會加註「N 檔未在時限內處理…再次更新會優先處理」。同一批內被預算截短的嘗試沒有加註，所以畫面只顯示「已完成：26/27 檔有可用報價」，使用者看不出這是時限造成的、再按一次就會補上。下次更新時，依新鮮度排序會把這一檔排到最前面（`order_by_staleness`，從未有報價的排最前），收斂的機制不受影響。這屬於行為正確、說明不足。
- **處置待使用者決定**。依 `D3`，不在沒有資料與決定的情況下改 `deploy/cloud.toml`。**同日使用者決定：先不改**，等 C3（F3，32 檔、以台股為主）多量一場再定。候選有三：維持 27、調低、改為 `0`（只由 deadline 約束）。另有一項尚未決定：同一批內被截短的嘗試，要不要也在訊息裡加註。**10-01 補記**：C3 兩場的數據已取得（算式得 28–29），見「C3」節，仍待使用者決定。訊息的待決另外多了一種情況：持股超過上限時，即使全部都有報價，每次仍回報 `partial`。**10-02 補記：使用者決定維持 27**，`deploy/cloud.toml` 不改。Claude 提出、使用者採納的理由有三個。第一，29 是五場中最快的 C3 得出的值，27 則是以 R5 含暖機的 `c` 算出，比 29 保守，改成 29 就是改用最快的場次當標準。第二，27 在本場已有 1 檔被截短，上限越高，同一批內被截短的情況越常發生。110 秒的 deadline 才是擋住 125 秒邊緣上限的機制，上限取 27 或 29 都不影響這一點，差別只在多出的標的是被延後，還是在同一批內被截短。第三，改值是程式變更，會觸發建置、把 `ab1667ccf7f7` 擠出 registry，還要重新部署並以隔離容器重跑完整套件，代價大於多 2 檔的好處。~~訊息的說明不足仍待決。~~ 訊息的說明不足由使用者決定修正，同日改於 `842becc`，見「訊息修正」節。

### B3、D2：匯率（2026-10-01 15:23–16:06 台北）

| 時間（UTC） | 請求 | 狀態 | latency | 操作 |
|---|---|---|---|---|
| 07:23:16.55–16.97 | GET `session`、`portfolio`、`valuation` | 200 | — | 使用者重新載入頁面 |
| 07:23:42.60 | PUT `/api/portfolio` | 200 | 0.887 s | 使用者**在 B3 之前自行套用了想要的匯率**，revision 6→7 |
| 07:23:43.63 | GET `valuation` | 200 | 0.877 s | |
| 08:05:30.40 | PUT `/api/portfolio` | 400 | **4.175 s** | B3 `-1`，見下方的縮容觀察 |
| 08:06:01.56 | PUT `/api/portfolio` | 400 | 0.675 s | B3 9 位小數 |
| 08:06:10.54 | PUT `/api/portfolio` | 400 | 0.591 s | B3 `10001` |
| 08:06:29.98 | PUT `/api/portfolio` | 200 | 0.818 s | B3 `32.5`，revision 7→8 |
| 08:06:30.95 | GET `valuation` | 200 | 3.226 s | |

使用者回報：B3、D2 的結果都與 Claude 列出的預期一致，目前為版本 8。

- **B3 ✅**：三種錯誤的匯率都回 400、revision 不變；正確的匯率回 200、revision +1。07:23:42 那次是使用者主動的操作，不是測試步驟。它之後**沒有接著更新報價**，與「只改匯率不會自動更新」相符（`save(true)` 不呼叫 `refresh()`）。
- **D2 ✅**：總市值的標題為「已知持股市值（非完整總額）」，損益顯示「完整報價與匯率齊全後顯示」（1 檔缺價）。
- **正式持股的匯率目前是 B3 第 4 步輸入的 `32.5`**，不是使用者 07:23 套用的值。

**附帶觀察（屬 `C7-3`，不是本項的驗收）：閒置到縮容之後，不重新整理也能寫入**。系統日誌顯示，08:05:30.42 有新實例啟動（`Starting new instance. Reason: AUTOSCALING`）。今天一共有三次冷啟動：05:49:28、06:50:42、08:05:30。也就是說，07:23:43 之後實例已縮容。頁面在 07:23:16 取得 session token 之後，到 08:05:30 之間**沒有再打 `/api/session`**，但 08:05:30 的 PUT 仍回 400，而這是匯率驗證的錯誤。`Guard` 在驗簽、`Origin`、session 任一關失敗時回 401／403，所以 400 代表這三關都過了。這次 PUT 包含冷啟動，共 4.175 秒。這與 `C3` 的雲端完成條件「閒置至服務縮容後再操作，不需手動重新整理即可繼續使用」的其中一半相符。但 Access session 過期的另一半沒有碰到，所以**留給 `C7-3` 正式驗收**。

### B4、C5、C6：兩個分頁與更新中改版本（2026-10-01 16:44–16:51 台北）

分頁 A 是 15:23 起一直開著的分頁；分頁 B 在 08:44:40Z 新開，這次載入碰上冷啟動（`session` 3.542 s）。三項都用匯率產生版本變化。

| 時間（UTC） | 分頁 | 請求 | 狀態 | latency | 說明 |
|---|---|---|---|---|---|
| 08:44:40.48–44.83 | B | GET `session`、`portfolio`、`valuation` | 200 | 3.542／0.160／4.294 s | 新分頁，冷啟動 |
| 08:45:07.61 | A | PUT `/api/portfolio` | **403** | 0.003 s | session token 過期，見下方 |
| 08:45:07.71 | A | GET `/api/session` | 200 | 0.003 s | 前端自動重取 |
| 08:45:07.83 | A | PUT `/api/portfolio` | 200 | 0.948 s | B4 第 2 步，revision 8→9 |
| 08:45:25.43 | B | PUT `/api/portfolio` | **409** | 0.649 s | B4 第 3 步 |
| 08:45:44.72–45.01 | B | 重新載入 | 200 | — | B4 第 4 步 |
| 08:46:08.98 | A | POST `/api/portfolio/refresh` | 200 | **106.178 s** | C5 |
| 08:46:11.13 | B | POST `/api/portfolio/refresh` | **202** | 0.222 s | C5，2.15 秒後按 |
| 08:46:11.53–08:47:54.10 | B | GET `/api/jobs/3b1d9738-…` × 18 | 200 | 0.08–0.20 s | 輪詢 |
| 08:47:55.24 | A | GET `valuation` | 200 | 0.787 s | A 收到完成的回應 |
| 08:47:56.11 | B | GET `valuation` | 200 | 0.538 s | B 輪詢到完成 |
| 08:49:32.67 | A | POST `/api/portfolio/refresh` | 200 | **101.965 s** | C6 |
| 08:49:51.80 | A | PUT `/api/portfolio` | 200 | 1.539 s | C6 第 9 步，使用者想要的匯率，revision 9→10 |
| 08:49:55.84 | A | GET `valuation` | 200 | 1.299 s | `save()` 之後的重新讀取 |

分頁的歸屬是由時間順序與 session 的行為推得的，日誌不記錄來源分頁。

- **B4 ✅**：B 回 409。使用者回報畫面顯示衝突的訊息、匯率欄保留 B 的輸入，重新整理後為版本 9、匯率 `32.6`。
- **C5 ✅（202 那一種）**：B 在 A 之後 2.15 秒按下，拿到 202 與同一個 job，並輪詢到完成。兩個分頁各重新讀取一次估值，C5 期間**只有一個 job**（A 的回應與 B 輪詢的 job_id 相同）。refresh_jobs 的筆數沒有以資料庫核對。**同日補記：已核對**，C6 之前（08:49:32Z）的 job 只有兩筆，08:46 前後只有 `3b1d9738-…` 一筆。見「C7」節。A 的回應：`3b1d9738-30e9-439c-acf5-a8365351f48d`、revision 9、`succeeded`、「已完成：27/27 檔有可用報價」、08:46:09.193→08:47:55.060（**105.87 s**）。畫面為「報價涵蓋 27 / 27 檔」、「降級估值 · 請參閱逐股品質」。上一場缺價的那一檔這次也有了報價，與「從未有報價的排最前面」相符；但這次的抓取順序沒有讀出。
- **C6 ✅**：更新結束後，使用者在 16:50 看到「先前版本的報價工作已完成；目前清單維持新版本，請再次更新報價。」。08:51:14 前後**沒有**再讀取估值，與 `settle()` 在 revision 不一致時不重新讀取相符。C6 那一場的 `status` 與訊息沒有取得。（同日補記：`status` 已在「C7」節的 refresh_jobs 查詢讀到，為 `succeeded`；訊息仍未取得。）

**附帶觀察一（屬 `C7-3`）：session 過期後，自動續期在雲端第一次被實際觸發**。分頁 A 的 token 是 07:23:16Z 取得的，到 08:45:07Z 已過了 81.9 分鐘，超過 `web_auth.SESSION_TTL` 的 3600 秒。第一次 PUT 回 403，100 ms 內出現 `GET /api/session`，接著重試的 PUT 回 200。`app.js` 只有在 401／403 且 `code` 為 `unauthorized` 或 `session_expired` 時才會這樣重取並重試，所以這次的 403 推定是 `session_expired`（回應內容沒有讀出，大小為 358 bytes）。使用者沒有察覺任何異常。對照 08:05:30 那次：token 42 分鐘時仍有效。**這是 `C3-3` 的雲端證據之一，正式驗收仍在 `C7-3`**；Access session 過期的部分不在這裡。

**附帶觀察二：背景分頁的輪詢間隔被拉長**。`watch()` 每次輪詢結束後 1.8 秒再發下一次，預期間隔約 2 秒。實際的 18 次間隔是 2.0–12.0 秒，例如 08:46:19→31、08:46:38→49、08:47:39→49 各約 10–12 秒。**推定**是 Chrome 對背景分頁的計時器節流，因為使用者當時在看分頁 A，**沒有驗證**。影響是 B 最多晚約 10 秒才看到完成；本場 B 的估值只比 A 晚 0.9 秒，因為最後一次輪詢剛好接近完成時刻。不判定為缺陷。

**附帶觀察三：請求日誌的時間與 job 的時間差了約 1 秒**。B 最後一次輪詢記在 08:47:54.100，回應 640 bytes，與 A 完成時的回應大小相同。依程式，`status` 要到最後一次 `put_job` 才會寫成完成，而 job 的 `completed_at` 是 08:47:55.060。所以若那次輪詢拿到的是完成的工作，請求日誌的時間就比實例上的 `datetime.now()` 早了約 1 秒。前面計算 deadline 時用的都是同一個時鐘（job 與抓價紀錄都在實例上產生），不受影響。差異的原因沒有查。

**C5、C6 是 F1 的第二、三場更新**：端到端分別為 106.178 s 與 101.965 s，第一場是 110.653 s。~~逐批耗時與 C6 的結果待以同一段唯讀查詢讀出。~~ 同日已由使用者在 SQL Editor 以唯讀查詢讀出（輸出不含代碼）：

| 場 | job（UTC） | job 耗時 | `F` | 第 1–5 批牆鐘（各 5 檔） | 第 6 批（2 檔） | 批間空檔 | `W` | 結果 |
|---|---|---|---|---|---|---|---|---|
| C2 | 07:09:10.304→07:11:00.573 | 110.27 s | 2.108 s | 24.07、19.57、18.55、18.39、18.90 | 6.31（1 檔被截） | 0.42–0.47 | 0.143 | `partial` 26/27 |
| C5 | 08:46:09.193→08:47:55.060 | 105.87 s | 1.816 s | 20.49、18.60、18.50、18.42、18.33 | 8.02 | 0.30–0.34 | 0.084 | `succeeded` 27/27 |
| C6 | 08:49:32.864→08:51:14.550 | 101.69 s | 1.669 s | 18.61、18.79、17.48、18.02、18.57 | 7.01 | 0.26–0.37 | 0.072 | `succeeded` 27/27 |

- 每場 27 檔都只有 6 批，沒有出現「超出本次上限」。
- C5、C6 的第 1、2 批都是 TW,US 混合，C2 的第 1 批則只有台股。這與 `order_by_staleness` 相符：上一場被截掉的那檔美股從未有報價，所以排在最前面，接著是上一場最早抓的台股。**逐檔的順序沒有讀出**，這是由每批的市場組成推得的。
- C6 的 job 是 revision 9 發起的，更新期間存成 revision 10，與 C6 的訊息相符。
- **單檔成本（含批間空檔）**：
  - 整場平均：C5 為 (105.867 − 1.816 − 0.084) ÷ 27 = 3.851 s，C6 為 3.702 s。
  - 滿 5 檔批次的最大值：C2 第 1 批 4.906 s、C5 第 1 批 4.162 s、C6 第 2 批 3.811 s。
  - 套用 `floor((110 − F) ÷ c)`：C2 的最大值得 21，C5 的最大值得 25，C5 的平均得 28。**三場的變異已經跨過 27**，所以這幾個數字只作為決定的資料，不是建議值。
- **C2 第 1 批（24.07 s、只有台股）是三場中最慢的一批**。當時實例已暖（`session` 3 ms），但那是儲存之後的第一次抓價，27 檔都沒有既有報價，也是這個實例第一次對台股來源發出請求，與後兩場的狀況不同。慢的原因沒有查。

### A5：日誌不含檔名、工作表名與代碼（2026-10-01 05:40–09:00Z）

以 `resource.type="cloud_run_revision"` 加上服務名稱查詢，不限 log。查詢在 08:12:57Z 執行，所以**實際涵蓋 05:49:28–08:06:30Z**，不到標題寫的 09:00Z；B4 之後的請求不在範圍內。這段時間的**全部** 59 筆是：請求日誌 44 筆、stdout 9 筆、`varlog/system` 6 筆。

- **請求日誌**：每筆的 `httpRequest` 只有 9 個欄位，為 `latency`、`protocol`、`remoteIp`、`requestMethod`、`requestSize`、`requestUrl`、`responseSize`、`serverIp`、`status`。`userAgent` 與 `referer` 都不存在。`requestUrl` 只有 5 種：`imports/preview`、`portfolio`、`portfolio/refresh`、`portfolio/valuation?market=ALL`、`session`。
- **stdout 與 system**：15 筆全部是三次啟動的訊息（監聽埠、`Allowed hosts`、`Allowed origins`、啟動探針）。
- **字串搜尋**：中文檔名、工作表名、`ZZZZ9`、OTC 代碼的百分比編碼，都是 0 次。整份檔案的非 ASCII 字元也是 0 個。

**A5 ✅**。判定依據是**逐一列出每一筆、每一個欄位**，不是字串搜尋。這樣做是因為匯出經過 Windows PowerShell 5.1 的管線，原始中文若被轉碼，字串搜尋會變成假陰性。這段時間涵蓋 A1–A3 的 9 次上傳與 1 次儲存，以及 B1 的儲存與更新。**界線**：A4b 的 F5 預覽（06:10）也在範圍內；Worker 端的 log（tail）在這段時間讀不到，所以 Cloudflare 那一側沒有核對。

### C7：「更新股票清單」（2026-10-01 17:12 台北）

依決定 2，按鈕維持顯示，本項只驗它回 409 的說明、不寫 job。持股為 F1、revision 10。使用者只按了一次，期間沒有按「更新報價」。

使用者回報：畫面訊息與 Claude 列出的預期相同，也就是「官方股票清單改由管理者在服務外更新，無法從頁面執行。」；Network 分頁顯示 409，回應的 `code` 為 `catalog_refresh_offline`。

請求日誌，08:52–09:30Z：

| 時間（UTC） | 請求 | 狀態 | latency |
|---|---|---|---|
| 09:11:42.95 | GET `/api/session` | 200 | 3.039 s |
| 09:11:46.44 | GET `/api/portfolio` | 200 | 0.157 s |
| 09:11:46.74 | GET `/api/portfolio/valuation?market=ALL` | 200 | 2.504 s |
| 09:12:05.66 | POST `/api/catalog/refresh` | **409** | 0.004 s |

refresh_jobs 的全部內容，由使用者在 SQL Editor 以唯讀 `SELECT` 讀出（只取 id、`status`、`catalog_only`、`portfolio_revision`、兩個時間；沒有篩選條件，所以是整張表）：

| id | `status` | `catalog_only` | revision | `created_at`（UTC） | `completed_at`（UTC） | 對應 |
|---|---|---|---|---|---|---|
| `1cf7ef80-…` | `partial` | false | 6 | 07:09:10.304 | 07:11:00.573 | B1／C2 |
| `3b1d9738-…` | `succeeded` | false | 9 | 08:46:09.193 | 08:47:55.060 | C5 |
| `46be5c08-…` | `succeeded` | false | 9 | 08:49:32.864 | 08:51:14.551 | C6 |

| 項目 | 結果 | 依據與界線 |
|---|---|---|
| C7 回 409 與說明 | ✅ | 畫面訊息、Network 的狀態與 `code` 都相符。Cloud Run 有這筆 409，所以它是**後端**回的，不是 Worker 回的。3.8 ms 也與程式相符：`refresh()` 在讀持股與 claim 之前就拒絕，沒有碰資料庫 |
| C7 不寫 job | ✅ | 整張表只有 3 筆，都是 `catalog_only=false`，最晚的一筆在 08:49:32Z 建立，09:12 前後沒有新增 |
| 第 0 項不寫 job | ✅ | 補上第 0 項延後的核對：最早一筆是 07:09:10Z，05:50 前後沒有 job |
| C5 只多 1 筆 | ✅ | 補上 C5 延後的核對：08:46 前後只有 `3b1d9738-…` |

- ~~**界線一**：使用者沒有回報按完之後「更新報價」按鈕是否恢復成可按。依 `app.js`，`refresh()` 的 `catch` 會把它設回 `disabled=false`，這是讀程式推得的。~~ **同日補記**：使用者回報按鈕已恢復成可按，與 `refresh()` 的 `catch` 相符。
- **界線二**：這張表在 `C7-6` 收尾時被 `purge` 清空過，所以「整張表 3 筆」等於今天全部的 job。這個前提是 09-30 的唯讀查詢核對過的（見「收尾」節），之後到今天 B1 之前，沒有記錄到任何會寫 job 的操作。
- C6 那一場的 `status` 原本沒有取得，這裡讀到是 `succeeded`，與 runs 的 27/27 一致。
- 09:11:42 的 `session` 花了 3.04 秒，推定是冷啟動；沒有查系統日誌確認。

### C3：F3 寬名單，存檔後更新兩次（2026-10-01 17:17–17:24 台北）

F3 共 32 檔，以台股為主，超過 27 檔的上限。存檔後會自動更新一次，接著使用者再按一次「更新報價」。台股與美股當時都休市。

請求日誌：

| 時間（UTC） | 請求 | 狀態 | latency | 說明 |
|---|---|---|---|---|
| 09:17:50.67 | POST `/api/imports/preview` | 200 | 0.516 s | F3 |
| 09:18:09.26 | PUT `/api/portfolio` | 200 | 0.969 s | revision 10→11 |
| 09:18:10.38 | GET `valuation` | 200 | 0.913 s | |
| 09:18:11.44 | POST `/api/portfolio/refresh` | 200 | **101.050 s** | 存檔後自動觸發，第 1 次 |
| 09:19:52.68 | GET `valuation` | 200 | 0.848 s | |
| 09:22:34.20–34.65 | GET `session`、`portfolio`、`valuation` | 200 | — | 重新載入頁面 |
| 09:22:40.31 | POST `/api/portfolio/refresh` | 200 | **101.562 s** | 使用者按的，第 2 次 |
| 09:24:22.01 | GET `valuation` | 200 | 0.887 s | |
| 09:25:09.78 | GET `valuation` | 200 | 0.877 s | Console 的「其他」查詢 |

job（由使用者在 SQL Editor 以唯讀 `SELECT` 讀出，輸出不含代碼）：

| job | `status` | `message` | revision | `created_at`→`completed_at`（UTC） | 耗時 |
|---|---|---|---|---|---|
| `4bdc2358-…` | `partial` | 已完成：27/32 檔有可用報價；5 檔超出本次上限，再次更新會優先處理這些標的 | 11 | 09:18:11.597→09:19:52.397 | 100.80 s |
| `dd519ff0-…` | `partial` | （同上） | 11 | 09:22:40.532→09:24:21.783 | 101.25 s |

每批（同一來源，以 job 的起訖時間圈出 fetch_attempts，再依 run 分組）：

| job | 第 1–5 批牆鐘（各 5 檔） | 第 6 批（2 檔） | 批間空檔 | 市場組成 | 失敗 |
|---|---|---|---|---|---|
| 第 1 次 | 18.460、17.518、17.640、17.376、17.464 | 6.997 | 0.552–0.686 | 前 2 批 TW,US，其餘 TW | 0 |
| 第 2 次 | 18.076、17.493、17.950、17.792、17.767 | 7.183 | 0.548–0.620 | 前 3 批 TW,US，其餘 TW | 0 |

兩次各有 27 個 instrument、27 筆嘗試，全部成功，沒有被 deadline 截掉。

| 項目 | 結果 | 依據與界線 |
|---|---|---|
| 第 1 次為 `partial`，訊息含「N 檔超出本次上限」 | ✅ | job 的 `message` 原文 |
| 第 2 次優先處理第 1 次被延後的標的 | ✅ | 第 2 次的處理順序中，第 1–5 位都是第 1 次**沒有嘗試**的標的，第 6–27 位都是第 1 次嘗試過、成功的標的。兩次合計，去重後正好是 32 個 instrument |
| 「其他」合併出現在圖表 | ✅ | 使用者在 Console 讀 `valuation?market=ALL` 的 `chart`，共 16 項，最後一項是「其他」，有 17 個成員；15 + 17 = 32，代表 32 檔都有權重（匯率沿用 revision 10 的值）。只輸出了項目是否為「其他」與成員數，沒有輸出代碼 |
| D3（C3 之後再看一次） | 未記錄 | 本場沒有讀明細的品質欄 |

- **第 1 次的排序**：C3 的第二個 job 還沒執行之前，同一段查詢比對的是 C6（F1）與 F3 第 1 次。結果是 F3 第 1 次的前 25 位都不在 F1 裡，最後 2 位在 F1 裡。F1 的標的今天已經有報價，F3 的其他標的從 `C7-6` 的 `purge` 之後就沒有報價，所以這與「從未報價的排最前」相符。由此可以推得：F3 與 F1 重疊 7 檔，被延後的 5 檔都是 F1 重疊的、今天報價最新的幾檔。**這是推論**，報價時間沒有讀出。
- **畫面回報與資料庫有出入**：使用者第一次回報第 2 次的結果是「已完成：32/32 檔有可用報價」，但資料庫的 `message` 是「27/32…」。依程式，分子只計算本次處理過的批次，最多 27，所以不可能出現 32/32。**推定**使用者看到的是總覽的「報價涵蓋 32 / 32 檔」，沒有確認。判定以資料庫為準。

**觀察：持股超過上限時，每次更新都會回報 `partial`，即使所有標的都有新鮮報價**。第 2 次結束時，32 檔都有報價（「其他」有 17 個成員，涵蓋 32/32），但 job 仍是 `partial`、「27/32 檔有可用報價」，而且「再次更新會優先處理這些標的」會一直出現，因為每次都會延後 5 檔。原因是 `run_job` 的 `count` 與 `status` 只看本次處理的批次，沒有把先前已經有的報價算進去。收斂的機制不受影響，第 2 次確實補上了第 1 次延後的標的。這和 C2 那一節「同一批內被截短的嘗試沒有加註」一樣，**屬於行為正確、說明不足**，處置併入同一項待決。

**`refresh_max_tickers` 的第四、五場數據**（以台股為主，與 C2、C5、C6 以美股為主的組成不同）：

| 場 | job 耗時 | `F` | `W` | 每檔平均（含空檔） | 滿 5 檔批次的最大值（含空檔） | `floor((110 − F) ÷ c)`：最大值／平均 |
|---|---|---|---|---|---|---|
| C3 第 1 次 | 100.80 s | 1.980 s | 0.207 s | 3.652 s | 3.815 s（第 1 批） | 28／29 |
| C3 第 2 次 | 101.25 s | 1.899 s | 0.227 s | 3.671 s | 3.727 s（第 1 批） | 29／29 |

- 五場依同一算式得出的範圍：C2 的最大值為 21，C5 的最大值為 25，C5 的平均為 28，C3 為 28–29。**最低的 21 來自 C2 的第 1 批**，那一批只有台股、所有標的都還沒有報價，而且是存檔後的第一次抓價。
- C3 第 1 次的情境與 C2 相近，也是存檔後的第一次抓價，大部分標的也還沒有報價，但第 1 批是 TW,US 混合，每檔 3.815 秒，沒有重現 C2 的 4.906 秒。所以 C2 為什麼慢，仍然沒有解釋。
- 本場的批間空檔約 0.55–0.69 秒，比 C2 的 0.42–0.47、C5／C6 的 0.26–0.37 秒長，原因沒有查。
- Cloud Run 的 latency 為 101.050 與 101.562 秒，離 125 秒的邊緣上限有 23 秒以上的餘裕。本場不含冷啟動，因為 09:22:34 的 `session` 只花 3 ms；09:18 前的實例狀態沒有查。
- 本節的兩段查詢見 [`c74-c3-check.sql`](c74-c3-check.sql)。

### D1：市場篩選的合計（2026-10-02 09:40 台北，C3 之後）

持股為 F3（32 檔：台股 27、美股 5），revision 11，所有標的都有報價，匯率已設定。請求日誌裡，腳本的三筆 GET 在 10-02 01:40:46–49Z（`ALL`、`TW`、`US`），都是 200。這時是台股盤中，C3 之後沒有再更新，所以估值用的是 10-01 C3 抓到的報價。使用者在 finpo 頁面的 Console 執行 [`c74-d1-check.js`](c74-d1-check.js)。這支腳本以 GET 讀 `valuation?market=ALL／TW／US`，用 BigInt 做精確小數運算，不經過浮點數，自行重算後與回應比對。輸出只有布林值與檔數，不含代碼與金額。

腳本交給使用者之前，先在 Node 以模擬回應跑過：故意算錯的已知市值、成本、總市值，以及一個不一致的圖表值，都判為 `false`；改成正確值後，都判為 `true`。

| 檢查 | ALL | TW | US |
|---|---|---|---|
| 明細只含該市場 | ✅ | ✅ | ✅ |
| `count`、`coverage` 與明細一致 | ✅ 32／32 | ✅ 27／27 | ✅ 5／5 |
| 每列 `market_value` = `price` × `quantity`（精確相等） | ✅ | ✅ | ✅ |
| `known_total` = Σ（市值 × 匯率），四捨五入到 0.01 | ✅ | ✅ | ✅ |
| `cost` = Σ（股數 × 買價 × 匯率），四捨五入到 0.01 | ✅ | ✅ | ✅ |
| `total`、`profit` 與精確值相符 | ✅ | ✅ | ✅ |
| 各幣別 `summaries` 的小計（精確相等）與檔數 | ✅ | ✅ | ✅ |
| 圖表各項合計與 `known_total` 的差在捨入誤差內 | ✅ | ✅ | ✅ |
| 圖表項數／「其他」的成員數 | 16／17 | 11／17 | 5／0 |
| `status` | `degraded` | `degraded` | `degraded` |

交叉核對：TW 與 US 的檔數、精確市值、精確成本相加都等於 ALL，三種篩選的匯率相同。

- **D1 ✅**。
- 圖表項數與 `calculate()` 的規則相符：ALL 取前 15 項，單一市場取前 10 項，其餘合併為「其他」。US 只有 5 檔，所以沒有「其他」。
- **界線**：驗的是 API 回應內部的一致性，**沒有比對畫面上顯示的數字**；價格本身是否正確屬 `C7-6`。`return_pct` 沒有驗算。`status` 為 `degraded`，代表至少一列帶有降級旗標，是哪些旗標由 D3 記錄。

### D3（C3 之後）：明細的品質欄（2026-10-02 09:42 台北）

使用者在 Console 讀 `valuation?market=ALL`（請求日誌 01:42:05.92Z，200），依市場、來源、`session`、旗標分組計數，只輸出了組合與筆數：

| 市場 | 來源 | `session` | 旗標 | 筆數 |
|---|---|---|---|---|
| TW | yahoo | `unknown` | `cached`、`session_unknown`、`stale` | 22 |
| TW | yahoo | `regular` | `cached`、`stale` | 5 |
| US | yahoo | `closed` | `cached`、`market_closed`、`stale` | 4 |
| US | yahoo | `unknown` | `cached`、`market_closed`、`session_unknown`、`stale` | 1 |

- **情境**：報價是 10-01 17:18–17:24（台北）抓的，當時台股已收盤、美股尚未開盤；讀取的時間是 10-02 09:42，台股盤中。所以全部都帶 `cached` 與 `stale`。
- **與 C2 之後的那一次不同**：C2 之後（10-01 15:11，報價剛抓完），台股出現的是「快取、休市」；這次台股沒有 `market_closed`，而 27 檔中有 22 檔是 `session_unknown`。推定是因為讀取時台股正在開盤，所以不再標休市；而 `session` 是依成交時間判斷的，與 R3 記錄過的規則相符。**這是推論**，逐列的報價時間沒有讀出。
- 依計畫書，**只記錄、不判定**。旗標標得對不對屬 `C7-6`。

### C4：冷卻（2026-10-02 09:49–09:52 台北）

F4 是網站「下載範本」的 2 檔（`0050`、`AAPL`，依 `web_input.template_xlsx`）。當時台股盤中、美股休市。

請求日誌：

| 時間（UTC） | 請求 | 狀態 | latency | 說明 |
|---|---|---|---|---|
| 01:49:01.35 | GET `/api/templates/holdings.xlsx` | 200 | 0.004 s | 下載 F4 |
| 01:49:20.65 | POST `/api/imports/preview` | 200 | 0.519 s | |
| 01:49:26.34 | PUT `/api/portfolio` | 200 | 1.062 s | 存 F4，revision 11→12 |
| 01:49:45.17 | POST `/api/portfolio/refresh` | 200 | 11.510 s | 使用者按的 |
| 01:50:07.26–07.92 | GET `session`、`portfolio`、`valuation` | 200 | — | 重新載入 |
| 01:50:16.38–01:51:16.03 | preview ×2、PUT ×3 | 200 | — | revision 12→15 |
| 01:51:24.32 | POST `/api/portfolio/refresh` | **200** | 9.963 s | 距上一個 job 99.15 s，冷卻已過 |
| 01:52:02.38 | POST `/api/portfolio/refresh` | **429** | 0.247 s | |
| 01:52:06.53 | POST `/api/portfolio/refresh` | **429** | 0.248 s | |

job（使用者在 SQL Editor 以唯讀 `SELECT` 讀出最新 3 筆）：

| job | `status` | `message` | revision | `created_at`→`completed_at`（UTC） | 耗時 |
|---|---|---|---|---|---|
| `79e4001f-…` | `succeeded` | 已完成：2/2 檔有可用報價 | 15 | 01:51:24.564→01:51:34.175 | 9.61 s |
| `08681a2d-…` | `succeeded` | 已完成：2/2 檔有可用報價 | 12 | 01:49:45.417→01:49:56.596 | 11.18 s |
| `dd519ff0-…` | `partial` | （C3 第 2 次） | 11 | 10-01 09:22:40.532→09:24:21.783 | |

| 項目 | 結果 | 依據與界線 |
|---|---|---|
| job 耗時低於 60 秒，冷卻碰得到 | ✅ | `79e4001f` 為 9.61 s，結束時距 `created_at` 才 9.6 秒 |
| 60 秒內再按，回 429 `cooldown` | ✅ | 兩次 429，分別在 `created_at` 之後 37.8 s 與 42.0 s（以請求日誌的時間計；附帶觀察三記錄過兩個時鐘差約 1 秒，不影響判定）。使用者回報畫面為「更新冷卻中，請於一分鐘後重試。」，這句只對應 `code='cooldown'`；`refresh_busy` 的訊息不同，而且當時沒有進行中的 job |
| 429 不寫 job | ✅ | 01:51:24 之後沒有新的 job。依程式，冷卻在 claim 的交易內、`put_job` 之前就拒絕 |
| 正向對照：超過 60 秒就不擋 | ✅ | 01:51:24 的請求距上一個 job 的 `created_at` 99.15 s，照常執行並成功 |

- **C4 ✅**。
- **界線**：60 秒的邊界附近（例如 59 秒、61 秒）沒有測；這個 429 是單一實例上的結果，冷卻跨實例的效果（`C4-5`）沒有在雲端觸發。
- **存 F4 之後沒有自動更新**。這與 Claude 給使用者的步驟不同（步驟寫的是「儲存後會自動更新」）。依 `app.js`，`save()` 只有在涵蓋不足時才會自動呼叫 `refresh()`；`0050` 與 `AAPL` 在 F3 階段已有報價，存檔後涵蓋率是 2/2，所以不會自動觸發。第一次更新是使用者自己按的。**這是 Claude 指示寫錯，不是缺陷**；通過條件不受影響，因為判定用的是 01:51:24 那一個 job。
- 01:50–01:51 的 3 次 PUT 各使 revision +1（12→15），與 job 的 revision 相符。這幾次儲存的內容沒有記錄。
- 使用者看到的「請參閱逐股品質」是總覽品質欄的「降級估值 · 請參閱逐股品質」（`status=degraded`），不是 job 的訊息。

### A4b 補記：F5 的 CPU 時間（2026-10-02 10:37–10:39 台北）

**tail 恢復了**。C4 之後、本次測試之前（沒有記下時刻），以 Node 的 `tls.connect` 讀 `tail.developers.workers.dev` 的憑證，簽發者是 `Google Trust Services WE1`，`authorized: true`，不再是公司代理的 `Advantech`。那次連線只讀憑證，沒有送出資料；之後的 `wrangler tail` 是正常驗證憑證的連線。代理為什麼恢復，沒有查。

以 `npx --yes wrangler@4.145.0 tail finpo --format json` 收事件，原始輸出存在 scratchpad，不進 repo，只取出下表的欄位。使用者先重新整理頁面作為正向對照，再以正常的上傳介面預覽 F5，按取消、沒有儲存。

| 時間（UTC） | 請求 | 狀態 | `outcome` | `cpuTime` | `wallTime` | `content-length` |
|---|---|---|---|---|---|---|
| 02:37:31.79 | GET `/api/session` | 200 | ok | 4 ms | 3620 ms | — |
| 02:37:35.58 | GET `/api/portfolio` | 200 | ok | 1 ms | 343 ms | — |
| 02:37:36.10 | GET `/api/portfolio/valuation` | 200 | ok | 1 ms | 2300 ms | — |
| 02:37:31.97 | GET `/favicon.ico` | 404 | ok | 0 ms | 0 ms | — |
| 02:38:24.74 | GET `/api/session` | 200 | ok | 7 ms | 307 ms | — |
| 02:38:25.21 | GET `/api/portfolio` | 200 | ok | 3 ms | 264 ms | — |
| 02:38:25.62 | GET `/api/portfolio/valuation` | 200 | ok | 2 ms | 434 ms | — |
| **02:39:04.81** | **POST `/api/imports/preview`** | **200** | **ok** | **14 ms** | 1962 ms | **5,242,880** |

全部事件都是版本 `474e5c4f`。Cloud Run 在 02:39:06.05 有對應的 preview，回 200，耗時 0.648 s（10-01 06:10 那次是 0.617 s）。

- **A4b 的 F5 量到了：14 ms**。`content-length` 正好是 F5 的大小，所以這筆就是 F5。
- **超過 Free 方案文件寫的 10 ms，但這次沒有被終止**：`outcome` 是 `ok`，預覽也回 200。Cloudflare 怎麼執行這個上限（每次都擋，或是允許偶爾超過），**本項沒有查證，也只有 1 個樣本**，所以不能推論「5 MiB 的上傳在 Free 方案上安全」。
- **成本來自 Worker 對 body 的雜湊**：讀 `worker/index.js`，Worker 會把整個 body 讀成一個 `ArrayBuffer`，再以 `crypto.subtle.digest('SHA-256', …)` 算出 HMAC 簽章要用的 body 雜湊。所以 CPU 時間會隨上傳大小增加。這是讀程式推得的；不同大小的檔案沒有逐一量測。
- **實際使用時的影響推定很小**：真實的持股 Excel 是 KB 等級。但小檔案預覽的 CPU 時間本次沒有量，F1、F2 的預覽在 tail 斷線期間發生。
- **處置待使用者決定**。選項有三：接受（單一使用者、5 MiB 是上限而不是常態，被終止時前端會收到錯誤）；調低 `MAX_UPLOAD`（Worker 與 `web_input` 要一起改）；改用付費方案。本項不改程式。**同日補記：使用者決定接受**，並勾選 `C7-4`。
- 不帶 body 的請求是 1–7 ms，`C7-8` 第 5 步記錄的是 2–3 ms。02:38:24 那次 `session` 的 7 ms 比較高，原因沒有查。

### 訊息修正（2026-10-02 下午，`842becc`，未部署）

使用者決定修正 C2 與 C3 兩節記下的兩種「行為正確、說明不足」。改的是 `run_job` 組訊息的方式，抓價、排序、收斂、`status` 的判定都沒有動。

| 情況 | 修正前 | 修正後 |
|---|---|---|
| 同一批內被時限截短（C2） | 「已完成：26/27 檔有可用報價」，沒有任何說明 | 加上「N 檔在時限截止前未取得新報價…再次更新會優先處理這些標的」 |
| 超出上限，延後的都有先前的報價（C3） | 「已完成：27/32 檔有可用報價；5 檔超出本次上限…」 | 「已完成：本次處理 27/32 檔，其中 27 檔有可用報價；5 檔超出本次上限…。未處理的 5 檔都保留先前的報價」 |

做法：

- **時限截短的判定**：`QuoteRunner` 的事件多記一個 `budget_limited`，意思是這次呼叫拿到的時間少於 `operation_timeout_seconds`，所以是 deadline 而不是來源的上限決定了它。這類逾時，加上開始前預算就用完的 `cycle_budget_exhausted`，合計為截短。同一檔在本次另有成功的嘗試就不算。C2 那一筆拿到 10 秒中的 2.37 秒，符合這個條件。
- **「保留先前的報價」只查一次**：用排序時也在用的 `latest_quote_times`，一次查完所有未處理的標的，不像 `valuation()` 那樣逐檔讀快取再估值。原因是未處理的可能有數百檔（持股上限 500），而這時 110 秒的 deadline 已經用掉，逐檔查詢會吃掉到 125 秒邊緣上限之間僅剩的餘裕。
- **`status` 不變**：超出上限時仍是 `partial`，因為這次工作確實沒有更新到全部持股。前端只顯示 `message`，不顯示 `status`（`app.js` 的 `settle`），所以使用者看到的問題由訊息解決。

界線：

- 「保留先前的報價」只代表資料庫裡有這檔的報價，**沒有核對它能不能估值**，所以可能和頁面的「報價涵蓋」不一致。例如報價存在、但幣別或市場對不上而不被採用。
- 重試因為 deadline 將至而沒有發生（`collect` 內 `monotonic()+delay >= deadline` 那一步），這種失敗不會被標成時限截短。
- 修正後的訊息只在隔離資料庫上測過，**沒有在雲端看過**。要等新映像部署後，下一次超出上限或被截短的更新才看得到。

測試，依 `docs/step-3-evidence.md` 的隔離容器程序：

- **完整套件：399 passed、0 skipped**。
- 新增 4 個測試，另改 1 個既有斷言，因為訊息開頭的格式改了。時限的測試用假時鐘同時餵給 `run_job` 與它建立的 `QuoteRunner`，所以不必真的等待。
- **修正前會失敗**：另開一個停在修正前（`d5e6580`）的 worktree，只放進新的測試檔，在同一個容器跑。3 個在訊息斷言失敗，其中 C2 的舊訊息「已完成：0/2 檔有可用報價」原樣重現、沒有任何註記。另外 2 個是反向守門，修正前就通過：時間充裕時的來源逾時不得歸咎於時限；延後的標的沒有報價時，不得說它保留了報價。

先前沒被發現的原因：既有測試的 deadline 都在第一批開始前就用完（`cut_the_clock`），走不到批次內截短；上限的測試也沒有先前的報價可比。

## C7-5　持久性驗收（2026-10-03，~~進行中~~ 同日完成，使用者決定勾選）

程序見計畫書 `C7-5` 項下 10-03 補記。動工前的唯讀核對也記在那裡。

### 前置：換回 F1（2026-10-03 11:38 台北）

使用者上傳 F1 並儲存，回報畫面為「持股已保存。可按「更新報價」取得新價格。」、「報價涵蓋 27 / 27 檔」、「降級估值 · 請參閱逐股品質」。

| 時間（UTC） | 請求 | 狀態 | latency | revision |
|---|---|---|---|---|
| 03:37:54.93 | GET `/api/session` | 200 | 3.740 s | `00005-pzn` |
| 03:37:59.14 | GET `/api/portfolio` | 200 | 0.171 s | `00005-pzn` |
| 03:37:59.60 | GET `/api/portfolio/valuation` | 200 | 4.120 s | `00005-pzn` |
| 03:38:12.26 | POST `/api/imports/preview` | 200 | 0.571 s | `00005-pzn` |
| 03:38:22.85 | PUT `/api/portfolio` | 200 | 0.913 s | `00005-pzn` |
| 03:38:24.04 | GET `/api/portfolio/valuation` | 200 | 0.938 s | `00005-pzn` |

- **儲存後沒有自動更新**，日誌裡沒有 `POST /api/portfolio/refresh`。這與 `app.js` 相符：只有涵蓋不足（`coverage < count`）時才自動更新，而 F1 的 27 檔在 `C7-4` 時已有報價，涵蓋為 27/27。計畫書原本預期「若觸發自動更新，順便當作基準耗時」，所以**本場沒有未中斷的基準**，比較時沿用 `C7-4` 的三場（101.7–110.3 秒，平日、雙邊休市）。今天是週六，雙邊也都休市。
- 載入時的 `session` 花了 3.74 秒，推定為冷啟動，沒有查系統日誌確認。

### `C7-5-2`：更新途中重新部署（2026-10-03 11:54–11:56 台北）

使用者 11:54:25 按「更新報價」，約 10 秒後執行 `gcloud run services update stock-quote --region=asia-northeast1 --revision-suffix=c75a`，頁面 11:56:15 結束。gcloud 回報 `stock-quote-c75a` 承接 100% 流量。日誌（請求、stdout、系統、稽核，以服務名過濾）：

| 時間（UTC） | revision／實例 | 事件 |
|---|---|---|
| 03:54:25.96 | `00005-pzn`／`…5bbcdf45` | `POST /api/portfolio/refresh` 到達；同時 `Starting new instance. Reason: AUTOSCALING`（先前的實例已縮容） |
| 03:54:45.15 | — | 稽核：`Services.ReplaceService` |
| 03:54:47.69 | `c75a`／`…09a4920a` | `Starting new instance. Reason: DEPLOYMENT_ROLLOUT` |
| 03:54:51.81 | `c75a` | 啟動探測成功 |
| 03:55:01.47 | `00005-pzn`／`…5bbcdf45` | 系統日誌：`Shutting down user disabled instance` |
| 03:56:14.15 | `00005-pzn` | 更新請求結束：**200**，latency 108.183 s |
| 03:56:15.18 | `c75a` | `GET valuation` 200，4.246 s |

- **判定：rollout 沒有中斷進行中的更新**。舊 revision 在流量轉走後，把請求做完並回 200。job 沒有卡住，因為它根本沒有被中斷。
- **「Shutting down」那一筆不代表當下終止**：它之後舊實例又跑了 72.7 秒，請求才正常結束。若當時已送 SIGTERM，依推論約 10 秒後就會被 SIGKILL，請求不可能做完。所以推定當下沒有送 SIGTERM，或送了但沒有在 10 秒後強制結束。兩者分不出來，uvicorn 的 `log_level` 是 `warning`，收到 SIGTERM 時不會寫日誌。
- **設定核對**：以 `revisions describe` 比對 `00005-pzn` 與 `c75a`，`spec`（映像、資源、環境變數、secret 參照、concurrency、timeout）與 annotations **完全相同**；labels 只差平台自動加上的 `client.knative.dev/nonce`、`serving.knative.dev/route` 與 `configurationGeneration`。服務的 template 名稱如預期停在 `stock-quote-c75a`。
- **逐批**（使用者在 SQL Editor 執行 `output/c75/tools/c75_jobs.sql` 查詢 2，唯讀、輸出不含代碼）：job `1e3d2f61`，6 批、27 檔，`not_success` 全為 0。

  | 批 | 市場 | 檔數 | 起訖（UTC） | 牆鐘 |
  |---|---|---|---|---|
  | 1 | TW,US | 5 | 03:54:30.258–51.689 | 21.43 s |
  | 2 | US | 5 | 03:54:52.122–03:55:10.249 | 18.13 s |
  | 3 | US | 5 | 03:55:10.662–28.348 | 17.69 s |
  | 4 | US | 5 | 03:55:28.775–47.161 | 18.39 s |
  | 5 | TW,US | 5 | 03:55:47.565–03:56:06.249 | 18.68 s |
  | 6 | TW,US | 2 | 03:56:06.614–14.100 | 7.49 s |

  **第 3–6 批都在「Shutting down」那一筆（03:55:01.47）之後開始**，舊實例在那之後仍持續抓價、寫入資料庫，不只是把回應送出去而已。請求到達到第 1 批開始為 4.30 秒，含冷啟動（實例 03:54:25.97 才開始啟動）。
- job 的 `status` 與畫面上的訊息：**未取得**。查詢 1 沒有貼回，使用者也沒有回報畫面訊息。由請求 200、6 批 `not_success` 全為 0 推得應為 `succeeded` 27/27，**未直接讀出**。

### `C7-5-3`：更新途中刪除 revision（2026-10-03 11:58–12:00 台北）

`C7-5-2` 的請求沒有被中斷，所以照程序改用刪除 revision。使用者 11:58:30 按「更新報價」，約 5 秒後執行一行指令：先 `--revision-suffix=`（清空後綴，產生新 revision `00007-66j`），成功後 `gcloud run revisions delete stock-quote-c75a --quiet`。gcloud 回報兩步都成功。頁面 12:00:03 結束。

| 時間（UTC） | revision／實例 | 事件 |
|---|---|---|
| 03:58:31.48 | `c75a`／`…09a4920a` | `POST /api/portfolio/refresh` 到達（即 `C7-5-2` 時啟動的那個實例） |
| 03:58:39.35 | — | 稽核：`Services.ReplaceService` |
| 03:58:41.40 | `00007-66j`／`…aa07d7c2` | `Starting new instance. Reason: DEPLOYMENT_ROLLOUT` |
| 03:58:48.01 | — | 服務 Ready |
| 03:58:50.73 | `c75a` | 稽核：**`Revisions.DeleteRevision`** |
| 03:58:51.55 | `c75a` | system_event：`Revision retired.` |
| 04:00:02.25 | `c75a` | 更新請求結束：**200**，latency 90.772 s，回應 641 bytes |
| 04:00:02.55 | `00007-66j` | `GET valuation` 200，5.294 s |

- **判定：刪除 revision 也沒有中斷進行中的更新**。刪除在請求開始後 19.3 秒完成，被刪除的 revision 又把請求做了 71.5 秒，回 200。這次 `c75a` 的實例**連「Shutting down」那一筆系統日誌都沒有**。
- **結論：以平台操作製造不出「更新途中容器被終止」**。rollout 與刪除 revision 兩種都試過，Cloud Run 都讓進行中的請求做完。所以 job 停在 `running`、等租約到期回收的那條路徑，在雲端**沒有被觸發，仍未實測**。在雲端會走到這條路徑的，只剩這次碰不到的情況：實例當機、記憶體耗盡、主機故障。
- **逐批**（同一段查詢）：job `c5d53c47`，6 批、27 檔，`not_success` 全為 0。

  | 批 | 市場 | 檔數 | 起訖（UTC） | 牆鐘 |
  |---|---|---|---|---|
  | 1 | TW,US | 5 | 03:58:33.334–49.533 | 16.20 s |
  | 2 | US | 5 | 03:58:50.039–03:59:05.205 | 15.17 s |
  | 3 | US | 5 | 03:59:05.747–21.551 | 15.80 s |
  | 4 | US | 5 | 03:59:22.050–37.923 | 15.87 s |
  | 5 | TW,US | 5 | 03:59:38.466–55.249 | 16.78 s |
  | 6 | TW,US | 2 | 03:59:55.701–04:00:01.990 | 6.29 s |

  **刪除（03:58:50.73）正好落在第 2 批開始後 0.7 秒**，第 2–6 批（約 71 秒的抓價與寫入）全在 revision 被刪除之後執行。
- **latency 90.8 秒，比 `C7-4` 的三場（101.7–110.3 秒）與 `C7-5-2`（108.2 秒）短**：滿 5 檔的批次每檔 3.03–3.36 秒，`C7-5-2` 是 3.54–4.29 秒。市場組成相同（兩場都是 TW,US／US×3／TW,US），差別之一是這次實例已暖（03:54:47 起就在跑），`C7-5-2` 是冷啟動後的第一次抓價。**原因沒有查**，只有一場，不據此推論單檔成本。
- job 的 `status` 與畫面上的訊息：**未取得**，理由同 `C7-5-2`。推得應為 `succeeded` 27/27，**未直接讀出**。

### `C7-5-4`、`C7-5-1`：更新途中關閉瀏覽器，縮容後重開（2026-10-03 12:08–12:58 台北）

使用者按「更新報價」後關閉瀏覽器的所有視窗，12:58 重開 `finpo`。**按下與關閉的時刻使用者沒有回報**，按下的時刻以請求日誌為準；關閉時刻依程序應為按下後約 30 秒，**未記錄**。等待期間的兩次 SQL 查詢沒有回報。

| 時間（UTC） | revision／實例 | 事件 |
|---|---|---|
| 04:08:46.02 | `00007-66j`／`…aa07d7c2` | `POST /api/portfolio/refresh` 到達 |
| 04:10:34.74 | `00007-66j` | 更新請求結束：**200**，latency 108.715 s，回應 641 bytes |
| 04:10:34 → 04:58:12 | — | **沒有任何日誌**（47.6 分鐘） |
| 04:58:12.85 | `00007-66j`／`…10aa72d4` | `GET /api/session` 200，3.440 s；同時 `Starting new instance. Reason: AUTOSCALING` |
| 04:58:16.40 | `00007-66j` | 啟動探測成功 |
| 04:58:16.79 | `00007-66j` | `GET /api/portfolio` 200，0.185 s，8,247 bytes |
| 04:58:17.31 | `00007-66j` | `GET valuation` 200，3.986 s |

**`C7-5-1` 縮容後重開：✅**
- **縮容**：重開時是另一個實例 `…10aa72d4`，而且是 `AUTOSCALING` 冷啟動。max 為 1，代表 `…aa07d7c2` 已經縮容，判讀同 `C7-3-4`。
- **持股仍在**：使用者回報 27 檔、版本號 17，畫面「報價涵蓋 27 / 27 檔」「降級估值 · 請參閱逐股品質」。版本 17 與先前的版本相符：`C7-4` 結束時為 15，`C7-3-5` 的儲存使它變成 16，今天存 F1 變成 17。17 是**推得的**，存 F1 時的版本號沒有直接讀出。`GET /api/portfolio` 的 8,247 bytes 與持股文件的內容沒有逐項比對。
- **沒有要求重新登入**（使用者回報「沒看到」）。這與預期相符：Access session 在 10:51 重新登入，10-04 10:51（台北）才到期（`C7-3-5`）。

**`C7-5-4` 更新途中關閉瀏覽器：後端的更新沒有被中斷**
- Cloud Run 把這個請求記為**正常完成**：200、108.7 秒、641 bytes，與前兩場完成的回應大小相同。所以瀏覽器關掉之後，Cloud Run 這一端的連線沒有斷，更新在請求內做完。
- **推定原因是 Cloudflare 收到瀏覽器斷線後，沒有中止往上游的請求**。這與 `C7-1`／`C7-2` 收尾時的發現一致：邊緣切斷以後，上游仍然把請求做完。**Worker 端沒有觀察**（沒有開 tail，`*.workers.dev` 也仍受公司代理影響），所以這是推論。另一種可能是瀏覽器其實沒有在 30 秒時關掉，請求日誌分辨不出兩者。
- **計畫書記下的假設缺陷沒有被觸發，也沒有被排除**。那個假設的前提是 Cloud Run 的請求已經結束、執行緒還活著。本場 Cloud Run 一直把請求視為進行中，CPU 沒有被節流，所以碰不到。依目前的設定，Cloud Run 端提早結束請求的途徑只剩 `timeoutSeconds` 150 秒，而 `refresh_deadline_seconds` 110 秒先到，所以這條路徑在現行設定下**推定碰不到**。這是推論，沒有實測。
- job 的 `status`：**未直接讀出**。由 200 與 641 bytes 推得為完成。

### 勾選（2026-10-03 13:20 台北，使用者決定）

- **已有證據的**：縮容後持股仍在（`C7-5-1`）；更新途中 rollout（`C7-5-2`）、刪除 revision（`C7-5-3`）、關閉瀏覽器（`C7-5-4`）三種情況，job 都沒有卡住，請求都正常完成。
- **界線**：三種中斷都沒有真的打斷後端，所以 job 停在 `running`、等 90 秒租約到期回收的路徑**在雲端未實測**，只有 `C4` 的隔離資料庫整合測試為證據。實例當機、記憶體耗盡才會走到這條路徑，本項製造不出來。
- **沒有直接讀出的**：三個 job（`1e3d2f61`、`c5d53c47`，以及 `C7-5-4` 那一個）的 `status` 與訊息；`C7-5-4` 關閉瀏覽器的時刻。使用者沒有補讀，以現有證據決定勾選。
- **正式持股維持 F1**（使用者決定）。
- **設定核對**：`00007-66j` 與 `00005-pzn` 的 `spec` **完全相同**，映像仍是 `sha256:a216b906…`；annotations 只差 `run.googleapis.com/operation-id`。服務的 template 名稱已清空、恢復自動命名，traffic 為 `latestRevision: true`、100% 在 `00007-66j`。revision 清單為 `00007-66j`、`00005-pzn`、`00004-4v6`、`00003-qs6`、`00002-wl7`、`00001-dx4`，`c75a` 已不在。計畫書「收尾」中的恢復命名因此已經完成。

## C7-6　外部來源驗收（~~進行中~~ 2026-10-03 完成，使用者決定勾選）

執行方式、場次定義與判定標準見計畫書 `C7-6` 項下的草稿。本節只記錄**已實際執行**的場次；未執行的場次不預先宣稱結果。

### 量測資源

| 項目 | 值 |
|---|---|
| 載具 | Cloud Run Job `c76-source-probe`，`asia-northeast1`（與正式服務分離，非 `C6-2`） |
| 映像 | tag `06e2df807527`，digest `sha256:6c01fedd772dd9c9527e0f128e06b059675b47a77065a5bd77d5513f6e095678` |
| 映像內容核對 | `2a94be4`（一批共用時間預算）是 `06e2df8` 的祖先；該 commit 的 `deploy/cloud.toml` 為 `refresh_deadline_seconds = 110`。此映像不含 `1e40ffc`（`cloud_db purge`），但 purge 不在更新路徑上，由管理者在本機執行 |
| 規格與身分 | 1 vCPU／1 GiB、`--tasks=1`、`--max-retries=0`、`--task-timeout=600`、`finpo-runtime` |
| 資料庫 | Supabase 東京區的 session pooler（port 5432），以 `finpo_app` 連線；host 與完整帳號屬識別資訊，不記錄於本檔（`C1-4`） |
| 秘密 | `DB_PASSWORD` 由 Secret Manager `db-password:latest` 掛載；不掛 HMAC 秘密 |
| 腳本 | `scripts/c76_probe.py`（commit `96a8dbd`），base64 後放在環境變數 `C76_PROBE`，共 11,068 字元，**Cloud Run 接受**（建立成功、執行時可讀到）。這是 R0 無法驗證的項目之一，至此結清 |

### 建立 Job 時的缺陷：啟動指令被 Git Bash 靜默改寫

在 Windows 的 Git Bash 下執行 `gcloud run jobs create ... --command=/app/.venv/bin/python`，gcloud 回報建立成功，但 `jobs describe` 顯示實際寫入的 command 是 **`C:/Program Files/Git/app/.venv/bin/python`**：MSYS 把開頭為 `/` 的參數當成 POSIX 路徑，轉成 Windows 路徑。若照此執行，容器會找不到 Python 而直接失敗。

**怎麼發現的**：建立後刻意以 `describe` 核對 command 與 args 是否拆成預期的兩個參數，不是等執行失敗才發現。**執行前已改正，R1 使用的是正確設定，沒有任何一次執行使用錯誤的指令。**

改正過程也記一筆：

| 嘗試 | 結果 |
|---|---|
| 整行加 `MSYS_NO_PATHCONV=1`（docker 在這台機器上的做法，見 `step-3-evidence.md`） | **失敗**：gcloud 的啟動包裝器本身依賴路徑轉換，報 `can't open file ... gcloud.py` 而起不來。Job 設定未被改動 |
| `MSYS2_ARG_CONV_EXCL="--command="`，只排除這一個參數 | 成功；再次 `describe`，command 為 `/app/.venv/bin/python`，args 與環境變數不變 |

**為何先前沒被發現**：`C7-2` 與 `C7-7` 的臨時資源都沒有覆寫 command，這是第一次在這台機器上把值以 `/` 開頭的參數傳給 gcloud。**往後凡是值以 `/` 開頭的 gcloud 參數，建立後都要以 `describe` 核對。**

### R1　官方清單（2026-09-23）

| 項目 | 值 |
|---|---|
| execution | `c76-source-probe-mhj2r`，結束碼 0 |
| 觸發 → 腳本開始 | 08:13:56Z → 08:14:19.7Z（台北 16:13:56 → 16:14:19），約 23.7 秒。含 Job 排程、映像拉取與容器啟動，**不等同** service 的冷啟動（`C7-7` 量的是 service） |
| 更新工作 | `c439a9f2-cb2b-488d-9a03-e55f1b905f34`，`succeeded` |
| 清單 generation | `489f036e-f77d-467b-941a-59649dc7044e` |
| 筆數 | **13,427**（TW 2,363、US 11,064）。步驟 9 的 generation 為 13,342 筆，量級一致 |
| 更新耗時（`refresh()` 前後的 monotonic） | **135.192 秒** |

**結論：官方清單的五個來源都能從 GCP 出口取得**；若任一來源失敗，`save_instrument_catalog` 會整筆拒絕（它要求每個來源恰好一份），不會產生 generation。本場只做了一次，未觀察到 429 或封鎖，但**一次成功不代表不會被限流**。

**135 秒的拆解**（以 generation 的 `completed_at` 為分界。該時間戳是 `save_instrument_catalog` 在**開始寫入前**取的，見 `storage.py` 的 `save_instrument_catalog`）：

| 階段 | 時間 | 耗時 |
|---|---|---|
| `refresh()` 開始 → 開始寫入 | 08:14:19.874 → 08:15:21.800 | 約 **61.9 秒**：認領更新工作、嘗試載入既有清單、取得收集鎖、向五個官方來源抓取。依程式結構，抓取應佔絕大部分，但**各階段未分別計時** |
| 開始寫入 → `refresh()` 返回 | 08:15:21.800 → 約 08:16:35.07 | 約 **73.3 秒**：13,427 筆逐筆 INSERT（每筆一次 `_insert`），加上提交與寫回更新工作 |

逐筆寫入平均約 5.46 毫秒（73.3 ÷ 13,427）。「每筆一次往返」是讀程式得出的，**單筆耗時未實測**。

### 發現：清單更新超過 125 秒的邊緣上限

135 秒超過 `C7-2` 量出的 Worker 對外 subrequest 上限（125 秒）。正式部署後：

1. **頁面上的「更新股票清單」會失敗。** 它依 `D3` 在請求內完成，使用者會收到 524，而不是 `C4-1` 設計的部分完成訊息。
2. **這段路徑不受 `refresh_deadline_seconds` 約束。** deadline 只在抓報價的批次之間檢查，清單的抓取與寫入不看 deadline。
3. **更新報價時若清單已過期，也會先跑這一段。** `run_job` 在清單不可用時會先抓整份清單，再開始抓價。

`deploy/cloud.toml` 把 `max_age_hours` 設為 168，註解的理由之一是「清單也能從 dashboard 隨需更新」。**那條隨需更新的路徑，正是本場量出超過上限的路徑**，因此該理由不成立。168 小時仍能讓更新報價少觸發清單更新，這部分理由不受影響。

**未確定的**：
- **只有一個樣本**，變異多大未知。
- 61.9 秒內**哪個來源最慢未拆開**。各來源的 `fetched_at` 已存在 generation 的 `sources` 欄位，但尚未讀出。
- **被 524 切斷後，Cloud Run 端是否繼續把清單寫完，未實測。**
- 寫入的 73 秒改成批次寫入應可大幅縮短，這是推論，**未實測**。

**處理方式待決定**，不在本項範圍內擅自修改。可能的方向：清單寫入改為批次；清單更新改由管理者在請求外執行（`C6-3` 的初始化本來就是如此）；或兩者並行。受影響的是 `C6-2`、`C7-2`（三層逾時對齊）與 `C7-4`（功能驗收含「更新股票清單」）。**`C7-6` 的報價量測不受影響**，前提見下一段。

**2026-09-23 補記：處理方式已決定並實作（兩者都做）**。

1. **清單改為批次寫入**：`save_instrument_catalog` 改以單一 `INSERT ... SELECT FROM jsonb_to_recordset(%s)` 寫入整份清單，不再逐筆往返。測試斷言「寫入 2,000 筆與 5 筆所用的 SQL 陳述式數量相同」，並逐欄比對寫入內容。還原成逐筆寫入時，該測試會失敗。
2. **清單更新移出使用者請求**：新增設定 `[instruments] refresh_in_request`。本機預設維持 `true`，行為不變；`deploy/cloud.toml` 設為 `false`。關閉時：
   - 頁面上的「更新股票清單」在認領工作**之前**就回 409（`catalog_refresh_offline`），不會寫出一筆不會執行的更新工作。
   - 更新報價時若清單已過期，**不在請求內重抓**，改用持股存檔時一併記下的標的身分，做法比照 `valuation()`；任一檔沒有記下的身分時，立即以失敗結束，並提示須由管理者更新。
   - 清單不可用時，儲存持股的錯誤訊息改為「須由管理者更新」，不再叫使用者去按一個會被拒絕的按鈕。
   - 請求外的執行者沿用既有的 `stock-web --refresh-catalog`（`C6-3`），由管理者以 Cloud Run Job 執行。

**測試**：新增 7 個案例，完整套件在隔離容器下 **376 passed、0 skipped**（基準 369）。其中「請求內絕不抓清單」的案例把 `fetch_all` 換成 `pytest.fail`：它屬於 `BaseException`，`run_job` 的廣泛例外處理吞不掉，所以一旦被呼叫，測試就會失敗，不會被記成一筆失敗的更新工作而默默通過。變異測試：分別拿掉 409 檢查、恢復「清單過期就在請求內抓」、拿掉「缺身分即失敗」、讓訊息忽略設定、還原逐筆寫入，五處都會讓對應的案例失敗。

**尚未驗證**（須等含此修正的映像建置後，在雲端實測）：
- 批次寫入從 Cloud Run 到 Supabase 的實際耗時。「應大幅縮短」仍是推論。
- 單一 INSERT 寫入 13,427 筆能否在 `statement_timeout`（預設 10 秒，`C5-4`）內完成。若超過，清單更新會整筆失敗，這一點須在實測時確認。
- 以 Cloud Run Job 執行 `stock-web --refresh-catalog` 的實際行為。映像的 ENTRYPOINT 已帶 `--container --config /app/cloud.toml`，只需附加 `--args=--refresh-catalog`、不必覆寫 command，但**未實測**。

**2026-09-23 補記：新映像的請求外清單更新已實測**。映像為 `218b4b962c5a`（`sha256:5ceea993f3518048b2fcec885b1aae282223a87564d0067c348efccfe3d2d53c`，build run `35840240857`）。以新建的 Cloud Run Job `finpo-catalog-refresh` 執行：沿用映像的 ENTRYPOINT，只附加 `--args=--refresh-catalog`、不覆寫 command，身分為 `finpo-runtime`，連線設定與 `c76-source-probe` 相同。建立後以 `describe` 核對 command 為空、args 只有 `--refresh-catalog`。

| 項目 | 值 |
|---|---|
| execution | `finpo-catalog-refresh-xmm8g`，結束碼 0，輸出 `Dashboard catalog refreshed.` |
| 觸發 → 更新完成（輸出時間戳） | 09:09:19Z → 09:10:41.07Z，約 **82 秒**。R1 同一區間（觸發 → `refresh()` 返回）為 08:13:56Z → 08:16:35.07Z，約 159 秒 |
| execution 開始 → 更新完成 | 09:09:30.34Z → 09:10:41.07Z，約 **70.7 秒**，含容器啟動、Python 載入、抓取與寫入 |

結論與界線：
- **以 Cloud Run Job 執行 `--refresh-catalog` 可行**，至此結清。
- **單一 INSERT 未碰到 `statement_timeout`**：執行成功，代表寫入 13,427 筆的那一條陳述式在 10 秒內完成。10 秒的值來自 `C5-4`，`Storage` 每次連線後都會設定並以 `SHOW` 核對。
- **寫入耗時無法單獨量出**：`--refresh-catalog` 只在結束時輸出一行，本次沒有讀出新 generation 的 `completed_at`，所以抓取與寫入沒有拆開。已知的只有上界：execution 開始到結束共 70.7 秒；R1 光抓取就約 62 秒，扣掉後寫入加上容器啟動約 9 秒以內。這是**以不同次執行的抓取時間相減得到的推估**，抓取本身的變異未知，**不得當成寫入耗時的量測值**。
- 兩次都是單一樣本；觸發到完成的差距（約 77 秒）與 R1 逐筆寫入的 73 秒量級相符，但只是相符，不構成證明。
- 這次更新已在請求外執行，不再受 125 秒邊緣上限約束。總耗時現在影響的只有 Job 的 `--task-timeout`（600 秒），餘裕充足。

**對 R2–R5 時間限制的更新**：這次寫入了一代新清單，到期時間往後延到約 **2026-09-30 09:10Z（台北 17:10）**。確切時間以新 generation 的 `completed_at` 加 168 小時為準，本次未讀出。R1 那一代依 `C5-6` 規則保留最近兩代。量測 Job `c76-source-probe` 已同步改用新映像 `218b4b962c5a`；清單有效時，新舊兩版的報價更新路徑相同，只有清單過期時的處理不同。

**已知的後續事項**：
- 前端仍會顯示「更新股票清單」按鈕，按下後顯示 409 的說明。改為隱藏屬 `C7-1`／`C7-4` 的介面範圍，本次未處理。
- 清單每 168 小時到期，**到期前須有人執行一次請求外更新**；到期後持股無法儲存，但已存持股的報價更新不受影響。第一階段不新增排程，此責任比照 `C5-6` 的每週清理，由管理者手動執行。
- 新映像的 `cloud.toml` 關閉了請求內更新，因此 `c76_probe` 的 `catalog` 模式在新映像上會回 409。若須重跑 R1，改用 `--refresh-catalog`。R2–R5 使用的 `06e2df807527` 映像不受影響。

**對 R2–R5 的時間限制**：本 generation 於 **2026-09-30 08:15:21Z（台北 16:15）** 到期（168 小時）。到期後 `run_job` 會在更新報價時先重抓整份清單，把約 135 秒混進報價耗時。**R2–R5 必須在到期前完成**，否則要先重跑 R1。

**2026-09-29 補記：第二次請求外清單更新（到期前）**。R3、R5 結束後，在執行它們的同一台以 pwsh 7 執行。**新 generation 尚未以資料庫核對**，下方的到期時間是依程式推得的，不是讀出的值。

| 項目 | 值 |
|---|---|
| 執行前核對（台北 22:34） | `describe`：映像 `sha256:5ceea993…`（`218b4b962c5a`），command 為空，args 只有 `--refresh-catalog`，`finpo-runtime`、`timeoutSeconds` 600、`maxRetries` 0，與 09-23 建立時相同。最近一次 execution 為 09-23 的 `xmm8g`；`c76-source-probe` 最近一次為 R5 的 `h8cz4`，已完成。兩支 Job 都沒有執行中的 execution。Registry 仍有 `218b4b962c5a` |
| 執行 | `gcloud run jobs execute finpo-catalog-refresh --region=asia-northeast1 --wait` |
| execution | `finpo-catalog-refresh-mc22l`，`gcloud` 回報成功完成；日誌 3 筆：`Dashboard catalog refreshed.`、`Container called exit(0).`、一筆空白 INFO |
| 觸發 → `--wait` 返回 | 14:35:15Z → 14:35:42Z（台北 22:35:15 → 22:35:42），26 秒 |
| execution 開始 → 輸出「更新完成」 | 14:35:22.3Z → 14:35:35Z，**約 13 秒**。09-23 同一區間約 70.7 秒 |

**快了約 58 秒，原因未查明**。`--refresh-catalog` 只在結束時輸出一行，抓取與寫入沒有分開計時，所以無法判斷是官方來源回應較快，還是其他原因。單一樣本，不據此修改任何時間預算。**2026-09-30 補記**：以各來源的 `fetched_at` 拆開後，差距約 52 秒集中在 `tpex_isin` 一個來源，寫入不到 1 秒，見下方「補查結果」。為什麼 09-23 的 TPEx 慢，仍未查明。

**為什麼推定已寫入新 generation**（讀程式碼得出，**未實測**）：`web.py` 的 `--refresh-catalog` 路徑不看現有清單是否過期，一律 `fetch_all` 後呼叫 `save_instrument_catalog`；後者（`storage.py`）每次都在同一個交易內插入新的 generation 與全部列，內容相同也不跳過；任何例外都會讓行程以非 0 結束、Job 記為失敗，本次為成功。依此推得新 generation 的 `expires_at` 略早於 **2026-10-06 14:35:35Z（台北 22:35）**，因為 `stamp` 是在插入前取的。

**待補查**：讀出最新兩代 generation 的 `completed_at`、`expires_at` 與列數（09-23 為 13,427 筆），核對新一代確實存在、列數量級相符，且 R1 那一代依 `C5-6` 的保留規則處理。這台沒有專案 venv（`uv` 為 0.9.11，專案要求 0.12.10），**使用者決定之後再補查**。補查前，不得宣稱清單已延期到上述時間。

**2026-09-30 補記：補查結果。新 generation 已寫入，現在生效的就是它，到期時間為 2026-10-06 14:35:34.66Z（台北 22:35）**。上面的推論與讀出的值一致。

**怎麼查的**：在執行 R1、R2 的那台（本 repo 的這個工作目錄）查。這台有專案 venv，但資料庫密碼只在 Secret Manager（`db-password`），由 Job 執行時注入；從本機連線就得把密碼取到本機行程裡，所以不這樣做（使用者決定）。改為執行一次 `c76-source-probe`，只在這次執行覆寫 `C76_PROBE`，換成唯讀查詢腳本 [`c76-catalog-check.py`](c76-catalog-check.py)。這支腳本放在 `docs/` 下，推送時不會觸發建置，映像窗口不受影響。

| 項目 | 值 |
|---|---|
| 腳本 | `docs/c76-catalog-check.py`，SHA-256 `860f45f41dc92cc9006ef8efa9e450a246c9db48aac5705be6064a99ec544241`，blob `53459efa1ed9579fa14f33e4f3721cbc39ca3ade`。容器內對解碼後的 `C76_PROBE` 算出的雜湊相同（`check` 行），證實這次執行跑的是這支腳本 |
| 唯讀 | 全部查詢在同一個 `REPEATABLE READ READ ONLY` 交易內，只有 SELECT；資料庫回報 `transaction_read_only = on` |
| 執行 | Git Bash：`MSYS2_ARG_CONV_EXCL="--update-env-vars=" gcloud run jobs execute c76-source-probe --region=asia-northeast1 --update-env-vars="C76_MODE=catalog-check,C76_PROBE=<base64>" --wait`。base64 不含逗號，但可能含 `/`，所以依本檔「建立 Job 時的缺陷」只把這個參數排除在路徑轉換之外 |
| 為什麼也覆寫 `C76_MODE` | Job 層級的 `C76_MODE` 仍是 R1 的 **`catalog`**（R2–R5 都只在執行時覆寫）。萬一 `C76_PROBE` 的覆寫沒生效，原探針會照 `catalog` 重抓並寫入清單；改成原探針不接受的 `catalog-check`，它就會在連資料庫前報錯退出 |
| execution | `c76-source-probe-ndsmt`，00:53:00Z 觸發，00:53:15.4Z 完成，成功 |
| 日誌 | Git Bash 下以 `gcloud logging read`（依 execution 名稱過濾）取得 7 行：`C76` 5 行（`check` 1、`generation` 3、`current` 1，`current` 行的 `generations: 3` 與行數相符）、`exit(0)`、一筆空白。存為 `output/c76/catalog-check.jsonl`（Git 忽略），SHA-256 `31373a1bc887ebff2c2c19a8b1e348da400cfcb3babb1d34ab1c22ed17037179` |
| Job 設定 | 執行前後 `describe` 的 `spec.template` 以 JSON 比對完全相同；映像仍為 `sha256:5ceea993…`，Job 層級的 `C76_PROBE` 未被改動 |
| 寫入 | 無。沒有抓報價，也沒有碰 `portfolio`；清除清單不因這次增加任何項目 |

**三代 generation**（依 `completed_at` 由新到舊；時間為 UTC）：

| generation | 來源 | `completed_at` | `expires_at` | 列數（TW／US） |
|---|---|---|---|---|
| `57d47501-4efd-4964-b84b-6a850336fec6` | 09-29 `mc22l` | 09-29 14:35:34.658 | **10-06 14:35:34.658** | **13,457**（2,363／11,094） |
| `73dd61a0-718d-4d1a-8bb4-19d7e05ef4d2` | 09-23 `xmm8g` | 09-23 09:10:40.375 | 09-30 09:10:40.375 | 13,427（2,363／11,064） |
| `489f036e-f77d-467b-941a-59649dc7044e` | R1 | 09-23 08:15:21.800 | 09-30 08:15:21.800 | 13,427（2,363／11,064） |

- **現在生效的是 `57d47501-…`**。用的是與 `load_instrument_catalog`（`storage.py`）相同條件的 SQL（`completed_at <= now() AND expires_at >= now()`，取最新一筆），00:53:11Z 查詢。這是**等效的 SQL，沒有呼叫該函式本身**。
- **列數**：13,457 等於五個來源 `row_count` 的總和。台股 2,363 不變，美股多 30 筆（`nasdaq_listed` 4,333 → 4,358、`nasdaq_other` 6,731 → 6,736），量級相符。五個來源的 `payload_hash` 都與 09-23 不同，台股列數相同但內容有變；逐列差異沒有比對。
- **保留規則**：三代都還在，這是對的。`C5-6` 的保留只在明確執行 `cloud_db prune` 時生效（服務啟動時不做維護），而 `prune` 只刪「超過天數、已過期、且不在最新兩代內」的 generation（`cloud_db.py` 的 `prune`）。依預設的 30 天，最早能被清掉的是 R1 那一代，時間在 10-23 08:15Z 之後。**本次沒有執行 `prune`**，這段是讀程式碼得出的。
- 舊兩代今天就會到期（台北 16:15、17:10），到期後的行為不變：生效的已經是新一代。

**「快了約 58 秒」的拆解**。`fetch_all`（`catalog.py`）依序抓五個來源，每個來源在下載並解析完才記 `fetched_at`，所以相鄰兩個來源的 `fetched_at` 差距，就是後一個來源的抓取加解析時間：

| 區間 | R1（09-23） | `xmm8g`（09-23） | `mc22l`（09-29） |
|---|---|---|---|
| `twse_funds` | 0.47 | 0.85 | 0.19 |
| **`tpex_isin`** | **52.75** | **54.62** | **2.79** |
| `nasdaq_listed` | 0.82 | 0.82 | 0.87 |
| `nasdaq_other` | 1.01 | 0.89 | 1.06 |

（單位：秒。第一個來源 `twse_companies` 的起點無法從 `fetched_at` 得知，所以不列。）

- **差距集中在 `tpex_isin`**：與 `xmm8g` 相比少了約 51.8 秒，另外約 6 秒沒有拆開（容器啟動與第一個來源都在裡面）。09-23 的兩次都慢，而且快慢相近；09-29 則在 3 秒內完成。**TPEx 為什麼在 09-23 慢，未查明**：可能是來源端，也可能是網路路徑，這些資料分不出來。解析本身在 09-29 連同下載只用了 2.79 秒，因此 50 秒不是花在解析上。
- **寫入耗時的上界**：`completed_at`（`save_instrument_catalog` 在插入前取的 `stamp`）是 14:35:34.658Z，`Dashboard catalog refreshed.` 的日誌時間戳是 14:35:35.269Z，相差 **0.61 秒**，包含版本檢查、13,457 列的單一 INSERT、提交與輸出。這是本項第一次有**寫入耗時的上界**；上方 09-23 那一次仍然沒有量出。依據是日誌時間戳，而不是程式內的計時。
- **對時間預算的影響：無**。清單更新本來就在請求外（`refresh_in_request = false`），不受 125 秒上限約束。只有一個樣本，而且 09-23 已經出現過 54 秒，所以**不得以 09-29 的 13 秒當作清單更新的典型耗時**。

### 清單更新：`ljtrf`（2026-10-02 10:53 台北）

清單原定 10-07 13:51（台北）到期，`C7-4` 做完後先更新一次。Claude 執行 `jobs execute` 時被自動權限擋下，改由使用者以可攜版 gcloud 執行 `run jobs execute finpo-catalog-refresh --region=asia-northeast1 --wait`。執行前以 `describe` 核對：Job 與正式服務用的都是 `a1fb03ff680d`（`sha256:df4a49e8…`），映像仍在 registry 內。這是 `finpo-catalog-refresh` **第一次在 `a1fb03ff680d` 上執行**；`tsp9t` 用的是 `ab1667ccf7f7`。

| execution | 觸發 | 容器開始 | 完成 | 觸發→完成 | 映像 |
|---|---|---|---|---|---|
| `ljtrf` | 10-02 02:53:21.559Z | 02:53:25.430Z | 02:55:33.450Z | **131.89 s** | `a1fb03ff680d` |
| `tsp9t` | 09-30 05:50:46.451Z | 05:50:50.643Z | 05:51:23.459Z | 37.01 s | `ab1667ccf7f7` |
| `mc22l` | 09-29 14:35:20.315Z | 14:35:22.340Z | 14:35:39.515Z | 19.20 s | 更早的映像 |

日誌：02:55:30.288Z stdout 為 `Dashboard catalog refreshed.`，02:55:30.439Z 為 `Container called exit(0).`，之間沒有錯誤。

generation 由使用者在 SQL Editor 以唯讀 `SELECT` 讀出（官方清單為公開資料，不含持股）：

| generation | `completed_at` | `expires_at` | 列數 | 生效中 |
|---|---|---|---|---|
| `5a49077d-…` | 10-02 02:55:29.591Z | **10-09 02:55:29.591Z（台北 10:55）** | 13,477 | ✅ |
| `8bdf148c-…`（`tsp9t`） | 09-30 05:51:20.259Z | 10-07 05:51:20.259Z | 13,454 | |
| `57d47501-…`（`mc22l`） | 09-29 14:35:34.658Z | 10-06 14:35:34.658Z | 13,457 | |

「生效中」用的是與 `load_instrument_catalog` 相同條件的 SQL，**不是呼叫該函式本身**。五個來源都是 `tls_relaxed=false`。新一代的列數等於五個來源 `row_count` 的總和（1,095 + 257 + 1,011 + 4,365 + 6,749），美股比上一代多 23 筆，台股不變。

續上方的拆解表（同一方法：相鄰兩個來源的 `fetched_at` 差）：

| 區間 | R1（09-23） | `xmm8g`（09-23） | `mc22l`（09-29） | `tsp9t`（09-30） | `ljtrf`（10-02） |
|---|---|---|---|---|---|
| 容器開始 → `twse_companies` 完成 | — | — | 7.40 | 8.37 | **22.27** |
| `twse_funds` | 0.47 | 0.85 | 0.19 | 0.97 | 2.74 |
| **`tpex_isin`** | **52.75** | **54.62** | **2.79** | **18.44** | **97.28** |
| `nasdaq_listed` | 0.82 | 0.82 | 0.87 | 0.84 | 1.01 |
| `nasdaq_other` | 1.01 | 0.89 | 1.06 | 0.99 | 0.86 |
| `completed_at` → `refreshed` 日誌 | — | — | 0.61 | 未讀 | 0.70 |

（單位：秒。第一列包含容器內 Python 的啟動，所以不等於 `twse_companies` 本身的耗時。）

- **這次慢在 `tpex_isin`**：131.9 秒中有 97.3 秒花在這一個來源上，寫入連同提交約 0.70 秒。五場的 `tpex_isin` 從 2.8 秒到 97.3 秒不等，**變異很大**。
- **單次逾時擋不住這種慢**：`fetch_source` 以 `httpx.Client(timeout=operation_timeout_seconds)` 抓取，`instruments` 的預設值是 30 秒，`cloud.toml` 沒有覆寫。這個逾時是每個 I/O 操作各自計算的，沒有總時限，所以資料只要持續流入，一個來源就可以跑超過 30 秒。這是讀程式與 httpx 的行為推得的；這次 97 秒內有沒有出現過接近 30 秒的停頓，沒有資料。上限只剩 Job 的 task timeout（沒有查）。
- **與時段的關係只是猜測**：快的那次（`mc22l`）在台北 22:35，`tsp9t` 在 13:50，`ljtrf` 在 10:53，台股盤中。看起來像是 TPEx 的網站在台灣上班時間比較慢，但 09-23 那兩次的台北時間沒有對照，而且只有 5 個樣本，**未驗證**。
- `twse_companies` 那一段也比前兩次慢（22.27 秒，前兩次是 7–8 秒），但裡面包含程序啟動，分不出是誰慢。
- **對使用沒有影響**：清單更新在請求外（`refresh_in_request = false`），沒有 125 秒的邊緣上限。若 TPEx 在某次慢到 Job 的 task timeout，結果是更新失敗、沿用舊一代清單，舊一代在到期前仍有效。這是讀程式推得的，沒有實測。
- **下一次清單更新須在 10-09 10:55（台北）前執行**。建議避開台股盤中；這只根據上面那個未驗證的猜測。

### R4 參考資料（2026-09-25 取得，R4 尚未執行）

這是 R4 的比對基準，不是 R4 的結果。取得時間為 2026-09-25 05:33:46Z（台北 13:33），網路為本機，不是 GCP；依計畫書，參考資料從哪個網路取得都可以。原始回應存於本機 `output/c76/r4-reference/`（Git 忽略）。

台股 09-25、09-28 休市（TWSE `holidaySchedule`），所以 R4 對應的前一交易日是 **2026-09-24**。各檔回應裡都沒有 09-25 的資料列，與休市一致。

| 代號 | 市場 | 來源 | 09-24 收盤 | 漲跌 |
|---|---|---|---|---|
| 2330 | 上市 | TWSE `STOCK_DAY` | 2,475.00 | −25.00 |
| 2317 | 上市 | TWSE `STOCK_DAY` | 250.50 | −5.50 |
| 0050 | 上市 ETF | TWSE `STOCK_DAY` | 112.40 | −0.05 |
| 6488 | 上櫃 | TPEx `tradingStock` | 948.00 | −2.00 |
| 3529 | 上櫃 | TPEx `tradingStock` | 3,230.00 | −75.00 |
| 006201 | 上櫃 ETF | TPEx `tradingStock` | 46.17 | −0.11 |

每檔的漲跌都和前一列收盤價的差一致，可以排除欄位讀錯。006201 在 09-24 只成交 61 張，是低成交量的案例。

**美股沒有參考值**：比較來源尚未決定，R4 的美股價格比對記為證據不足。

### R4 證據草稿腳本（2026-09-26 準備，R4 尚未執行）

`scripts/c76_report.py` 讀 `r4.jsonl` 與本機的參考原始檔，輸出本節要貼入的 markdown 草稿，用法見計畫書「R4 執行準備」的 09-26 補記。它只整理日誌，**不產生任何量測結果**。

- **參考值直接讀原始檔**：依日期取 09-24 那一列，不取最後一列。從本機 `output/c76/r4-reference/` 解析出的 6 檔為 2330 2475.00、2317 250.50、0050 112.40、6488 948.00、3529 3230.00、006201 46.17，**與上表一致**。
- **測試**：新增 8 個離線案例，完整套件在隔離容器下 **392 passed、0 skipped**（基準 384）。另有 2 個警告，來自 `test_web.py` 匯入的 starlette `TestClient` 的棄用警告，與本次變更無關；新案例在 `-W error` 下仍然通過。
- **變異測試**：分別改成以下 11 種寫法，每一種都會讓至少一個案例失敗：取最後一列當參考、只看存入旗標、旗標缺漏當通過、一個 tick 內當通過、ETF 用股票級距、兩個市場用同一個 `trading_date`、不比頁面價格、改看第一次嘗試而非最後一次成功、美股也拿去比收盤、缺參考值當通過、缺嘗試不報。
- **拿掉的一道條件**：原本也會列出「成功但帶 retry-after」的嘗試。這道條件被拿掉後，沒有任何案例失敗。查程式發現 `provider_worker` 只在非 200 回應時才讀 retry-after，成功的嘗試不會帶這個值，所以這道條件防不到任何情境，已經拿掉。
- **證明不了的**：Cloud Logging 匯出的實際行格式。腳本沿用 `c76_mis` 的讀法，只取以 `C76 ` 或 `{` 開頭的行，其餘一律略過。如果匯出時一行被截斷，解析會直接報錯；如果一行被拆成多行，開頭那段同樣報錯，後面幾段因為不以 `{` 開頭而被略過。整筆 `attempt` 行遺失的情形不會被當成通過：該檔會列為「沒有嘗試紀錄」。

### R4　雙邊休市（2026-09-26）

**結論：「半夜按更新」情境符合預期。** 11 檔都帶 `market_closed`，存入、估值、頁面三層都有；台股 6 檔的 `trading_date` 都是 09-24，價格**完全等於**官方收盤；美股 5 檔的 `trading_date` 都是 09-25。沒有 429、封鎖或逾時。**美股價格正確性為證據不足**：沒有比較來源，這是 2026-09-25 使用者的決定。另有一項旗標觀察，見下方「`session_unknown`」。只有一個樣本。

**執行機器改為本 repo 的這個工作目錄**（2026-09-26 使用者決定），取代 09-25「回 R1 那台跑」的決定。原因：R4 只需要觸發 Job 和取日誌，而參考原始檔本來就在這台。gcloud 586.0.0 以 winget（`Google.CloudSDK`，安裝程式來自 `dl.google.com`，雜湊由 winget 驗證）安裝在使用者目錄，由使用者本人登入專案擁有者帳號。gcloud 指令一律在 PowerShell 下執行。

**執行前的 `describe` 核對**（09-26 上午，觸發 R4 之前）：

| 核對項 | 結果 |
|---|---|
| command／args | `/app/.venv/bin/python`；`-c` 與 `exec(__import__('base64').b64decode(__import__('os').environ['C76_PROBE']))`，共 2 個。沒有被改寫成 Windows 路徑 |
| `C76_PROBE` | 11,068 字元。base64 解碼後的 git blob 為 `2c87174d…`，與 `96a8dbd`、`HEAD` 的 `scripts/c76_probe.py` **完全相同** |
| 映像 | `sha256:5ceea993f3518048b2fcec885b1aae282223a87564d0067c348efccfe3d2d53c`，即 **`218b4b962c5a`** |
| 規格／身分 | 1 vCPU／1Gi、`taskCount` 1、`maxRetries` 0、`timeoutSeconds` 600、`finpo-runtime`。Job 預設 `C76_MODE=catalog`，執行時覆寫為 `refresh` |
| 最近一次 execution | R1 的 `c76-source-probe-mhj2r`，R1 之後沒有人執行過 |

**更正**：上方「已知的後續事項」寫「R2–R5 使用的 `06e2df807527` 映像」，**這句是錯的**。`describe` 證實 Job 在 R1 之後已改用 `218b4b962c5a`，與「對 R2–R5 時間限制的更新」那段的敘述一致。原句保留不改，以本段為準。

**映像保留窗口，第一次以 `gcloud artifacts docker images list` 核對**：Registry 內恰好有 `06e2df807527`（09-23 13:03 建立）、`218b4b962c5a`（09-23 17:00）、`b6347e610e87`（09-25 14:06）三個，與計畫抬頭依 `gh run list` 所做的推定一致。`finpo-catalog-refresh` 的映像也是 `218b4b962c5a`，**沒有任何 Job 使用 `06e2df807527`**。因此：
- 再推**一次**非純文件的提交，擠掉的是 `06e2df807527`，不影響任何 Job。
- 推**第二次**會擠掉 `218b4b962c5a`，`c76-source-probe` 與 `finpo-catalog-refresh` 都將無法執行，包括清單到期前必須跑的那一次。

**執行**：`gcloud run jobs execute c76-source-probe --region=asia-northeast1 --update-env-vars=C76_MODE=refresh,C76_TICKERS=fixed --wait`

| 項目 | 值 |
|---|---|
| execution | `c76-source-probe-h8cms`，`gcloud` 回報成功完成；容器日誌為 `Container called exit(0).` |
| 觸發 → 腳本開始 | 02:51:13.3Z → 02:51:44.4Z（台北 10:51:13 → 10:51:44），約 31 秒。含 Job 排程與容器啟動；R1 為 23.7 秒 |
| execution 完成 | 02:52:26.7Z；`--wait` 在 02:52:38.7Z 返回 |
| instance | `c356e634-375e-4860-addf-ee651a025176` |
| deadline／max_tickers | 110／0 |
| 更新工作 | `3213a160-796b-4920-b71a-5126162f70f9`，`succeeded`，「已完成：11/11 檔有可用報價」 |
| `refresh()` 耗時 | 37.34 秒 |
| **portfolio revision**（最後 `reset` 用） | **1** |
| **manifest**（併入清除清單） | `{"runs": ["676eba17-90b2-4301-9dd6-dfc0114d167b", "717bace7-1c44-4874-b012-44194265a7b0", "9f3a7ef5-6c40-4510-b5ba-69fbe5d3d8b1"], "refresh_jobs": ["3213a160-796b-4920-b71a-5126162f70f9"]}` |
| 錯誤行 | 0 |

**取日誌時的缺陷：過濾條件的雙引號被 PowerShell 吃掉，查詢靜默回 0 筆**。在 PowerShell 下以 `& gcloud.cmd logging read 'labels."run.googleapis.com/execution_name"="…"'` 查詢，回傳 0 筆、沒有錯誤；改成時間範圍的條件後，才報出 `Unparseable filter`。原因是 PowerShell 呼叫 `.cmd` 時把引數裡的雙引號剝掉了。第一次的 0 筆**不是**日誌尚未寫入，這一點差點被誤判。改正方式是把雙引號寫成 `\"`，之後查到 31 筆，其中 `C76 ` 開頭的 29 筆存為 `output/c76/r4.jsonl`（Git 忽略）。另外 2 筆是平台訊息（`exit(0)`，以及一筆 `jsonPayload` 為空的項目）。**往後在 PowerShell 下查日誌，0 筆的結果要先懷疑過濾條件。**

**2026-09-26 補記：上面的改正方式只適用於 `gcloud.cmd`**。準備 R3 程序時，以新開 PowerShell 視窗的 PATH 查到的 `gcloud` 是 **`gcloud.ps1`**，它的引號規則剛好相反。以 R4 的 execution 實測：`gcloud.ps1` 寫成 `\"` 時靜默回 **0 筆**，用一般雙引號則是 **31 筆**。R4 當時以完整路徑呼叫 `gcloud.cmd`，所以要寫成 `\"`。兩種寫錯的方式都不報錯。**怎麼發現的**：寫進 R3 程序的指令沒有照 R4 的呼叫方式照抄，而是在新視窗的解析方式下實際跑了一次。若直接沿用 R4 的寫法，R3 會查到 0 筆。**同日再補記：前面這些都是在 pwsh 7 下的結果**。這台 Windows Terminal 的預設設定檔是 Windows PowerShell 5.1，在 5.1 下，`gcloud.ps1` 加一般雙引號的同一段程式也是**取到 0 行、沒有報錯**；5.1 也不支援 `Out-File -Encoding utf8NoBOM`。所以程序規定只能用 pwsh 7，開始前先檢查版本。存檔也改成 `[IO.File]::WriteAllLines`，在 pwsh 7 下重現 R4，結果與 `r4.jsonl` 雜湊相同。同一次準備也以 `--verbosity=debug` 核對了參數解析：經 `gcloud.ps1` 時，沒加引號的逗號會被換成空白（`--region=asia-northeast1,x` 被解析成 `"asia-northeast1 x"`），加引號後才保留逗號。R4 的 `--update-env-vars=C76_MODE=refresh,C76_TICKERS=fixed` 沒有加引號卻正常，是因為當時呼叫的是 `gcloud.cmd`；R4 日誌的 `start` 行為 `mode: refresh`、`portfolio` 行為 `spec: fixed`，證實覆寫確實生效。核對用的是兩次帶無效區域的 `describe`，都在送出請求前失敗，`gcloud config list` 確認設定沒有被改動。

**各批**：`run_job` 分成 3 批。第二批同時含台股與美股，所以一批跨市場共用預算（`2a94be4`）在雲端上實際執行到了。

| run | 狀態 | 檔數 | 內容 | 開始（台北） | 結束（台北） | 牆鐘（秒） |
|---|---|---|---|---|---|---|
| `717bace7-…` | completed | 5 | 2330、2317、0050、6488、3529 | 10:51:47 | 10:52:06 | 18.401 |
| `676eba17-…` | completed | 5 | 006201、AAPL、MSFT、BRK.B、VOO | 10:52:06 | 10:52:20 | 13.656 |
| `9f3a7ef5-…` | completed | 1 | QQQ | 10:52:20 | 10:52:23 | 2.723 |

**逐次嘗試**（每檔一次，全部 `success`；旗標為抓取當下存入的）：

| 代號 | elapsed_ms | price | price_kind | quote_time（台北） | trading_date | session | delay | 存入旗標 |
|---|---|---|---|---|---|---|---|---|
| 2330 | 7448 | 2475.0 | last_trade | 09-24 13:30:08 | 2026-09-24 | unknown | 1200 | market_closed, session_unknown |
| 2317 | 2518 | 250.5 | last_trade | 09-24 13:30:04 | 2026-09-24 | closed | 1200 | market_closed |
| 0050 | 2479 | 112.4 | last_trade | 09-24 13:30:04 | 2026-09-24 | closed | 1200 | market_closed |
| 6488 | 2696 | 948.0 | last_trade | 09-24 13:30:04 | 2026-09-24 | closed | 1200 | market_closed |
| 3529 | 2558 | 3230.0 | last_trade | 09-24 13:30:32 | 2026-09-24 | unknown | 1200 | market_closed, session_unknown |
| 006201 | 2520 | 46.17 | last_trade | 09-24 13:30:39 | 2026-09-24 | unknown | 1200 | market_closed, session_unknown |
| AAPL | 2746 | 341.07 | last_trade | 09-26 04:00:01 | 2026-09-25 | closed | 0 | market_closed |
| MSFT | 2556 | 516.17 | last_trade | 09-26 04:00:01 | 2026-09-25 | closed | 0 | market_closed |
| BRK.B | 2560 | 505.48 | last_trade | 09-26 04:00:03 | 2026-09-25 | closed | 0 | market_closed |
| VOO | 2581 | 710.79 | last_trade | 09-26 04:00:00 | 2026-09-25 | closed | 0 | market_closed |
| QQQ | 2525 | 744.5 | last_trade | 09-26 04:00:00 | 2026-09-25 | closed | 0 | market_closed |

**逐檔判定**：以 `scripts/c76_report.py` 產生草稿，並經人工核對。

| 代號 | 估值旗標 | 頁面旗標 | 官方收盤 | 差 | 價格比對 | 不符之處 |
|---|---|---|---|---|---|---|
| 2330 | market_closed, session_unknown | cached, market_closed, session_unknown | 2475.00 | 0.00 | 相等 | 無 |
| 2317 | market_closed | cached, market_closed | 250.50 | 0.00 | 相等 | 無 |
| 0050 | market_closed | cached, market_closed | 112.40 | 0.00 | 相等 | 無 |
| 6488 | market_closed | cached, market_closed | 948.00 | 0.00 | 相等 | 無 |
| 3529 | market_closed, session_unknown | cached, market_closed, session_unknown | 3230.00 | 0.00 | 相等 | 無 |
| 006201 | market_closed, session_unknown | cached, market_closed, session_unknown | 46.17 | 0.00 | 相等 | 無 |
| AAPL | market_closed | cached, market_closed | — | — | 證據不足 | 無 |
| MSFT | market_closed | cached, market_closed | — | — | 證據不足 | 無 |
| BRK.B | market_closed | cached, market_closed | — | — | 證據不足 | 無 |
| VOO | market_closed | cached, market_closed | — | — | 證據不足 | 無 |
| QQQ | market_closed | cached, market_closed | — | — | 證據不足 | 無 |

頁面 11 列都有市值，`failure_reason` 都是空的；頁面價格與本次抓到的價格一致。存入旗標帶 `freshness_unknown` 的有 0／11 檔：台股宣告延遲 1200 秒，美股宣告 0 秒。

**人工核對時另外看到的，腳本的判定沒有涵蓋**：
- **`session_unknown`：台股 6 檔中有 3 檔被標上**。這 3 檔的成交時間是 13:30:08、13:30:32、13:30:39；成交時間在 13:30:04 的另外 3 檔被判為 `closed`。`quality.py` 的 `assess` 把成交時間超過日曆收盤（XTAI 13:30）加 5 秒的報價標為 `session_unknown`。這是**已知且刻意保留的規則**：step 5 就記錄過 2330 在 13:30:08 被這樣標記，當時「未放寬規則」（`step-5-evidence.md`、`data-sources.md`）。**這次新知道的是影響範圍**：同一天的收盤成交時間可以晚到 13:30:39，6 檔中有 3 檔落在 5 秒之外。影響是這 3 檔的頁面都會帶 `session_unknown`。另外，`quoting.py` 的 `compare` 會把帶此旗標的報價判為「不可比較」，快取候選也會跳過它。R4 的市值計算沒有受影響。**要不要放寬這個規則是另一個決定，本場不處理**，只照實記錄。
- **`price_kind` 在休市時仍為 `last_trade`**。Yahoo 轉接器對一般時段的成交價一律標 `last_trade`；休市時抓到的其實就是前一交易日的最後一筆成交，價格也等於官方收盤。計畫書的 R4 預期沒有要求 `price_kind`，這裡只是記下觀察。
- **2330 的第一次請求耗時 7,448 毫秒**，其餘 10 檔在 2,479–2,746 毫秒之間。2330 是整個容器的第一次 Yahoo 請求，推測含連線與套件初始化，但**只有一個樣本，沒有拆開量**。本場的耗時不用來推 `refresh_max_tickers`，那是 R5 的工作。

### 本場寫入、待清除的資料

| 資料 | 處置 |
|---|---|
| 更新工作 `c439a9f2-cb2b-488d-9a03-e55f1b905f34` | 列入清除清單（本場 manifest：`runs` 為空，`refresh_jobs` 為這一筆） |
| 清單 generation `489f036e-…` | **保留**（2026-09-23 使用者決定；`C6-3` 本來就需要） |
| 持股 | 未變動 |

原始日誌存於本機 `output/c76/r1.jsonl`（Git 忽略）。

**2026-09-26 補記：R4 寫入、待清除的資料**（上表是 R1 的）：

| 資料 | 處置 |
|---|---|
| runs `717bace7-1c44-4874-b012-44194265a7b0`、`676eba17-90b2-4301-9dd6-dfc0114d167b`、`9f3a7ef5-6c40-4510-b5ba-69fbe5d3d8b1` | 列入清除清單 |
| 更新工作 `3213a160-796b-4920-b71a-5126162f70f9` | 列入清除清單 |
| 持股 | 存入 11 檔假持股，revision 由 0 變成 **1**。最後以 `C76_MODE=reset` 還原，屆時的 `C76_EXPECT_REVISION` 取最後一場印出的 revision |

R4 原始日誌存於本機 `output/c76/r4.jsonl`（Git 忽略）。這台沒有 `r1.jsonl`，R1 的 manifest 以本檔的紀錄為準。

### 臨時資源（本節）

| 資源 | 狀態 |
|---|---|
| Cloud Run Job `c76-source-probe` | ~~**存在**，待 R2–R5 與清除完成後刪除。~~2026-09-23 映像由 `06e2df807527` 改為 `218b4b962c5a`。**2026-09-30 補記：已刪除**（03:30Z），見「收尾」節 |
| Cloud Run Job `finpo-catalog-refresh` | **保留**：這是請求外清單更新的執行者，不是臨時資源（`C6-3`） |

### R2　台股盤中（2026-09-29）

本場在台北 11:44 後觸發，Cloud Run execution 為 `c76-source-probe-p7jrp`。Job 沿用已核對仍存在的映像 `sha256:5ceea993f3518048b2fcec885b1aae282223a87564d0067c348efccfe3d2d53c`，以 `C76_MODE=refresh,C76_TICKERS=fixed` 執行。`start` 日誌時間為 11:45:04，`refresh()` 從 11:45:06 起耗時 **43.151 秒**；Job `succeeded`，3 批 run 全為 `completed`，11 筆 attempt 全為 `success`，0 筆 `error`，11 筆 view 都有價格且 `failure_reason` 為空。沒有觀察到 429、封鎖或逾時。portfolio revision 由 1 變為 **2**。取得的 `job.message` 中文字元顯示為 `?`，但狀態欄、批次狀態與 11 筆獨立 attempt 都可核對成功；字元在哪一層流失尚未查明。

這台沒有另一台電腦未推送的 `bf55be2` 分支，也沒有預裝 gcloud。先在本機分支 `codex/c76-r2-local` 重作事前已決定的 MIS `d+t` 對齊規則，提交 `3aec5e6`，`scripts/c76_mis.py` 的 blob 為 `789c9ff583cf18afedd913d14f1d69f1c6a0f868`；10 項相關測試通過，未宣稱完整套件通過。此分支**未推送**，避免清單測試結束前觸發映像建置。Google 官方 Windows CLI 可攜版 586.0.0 放在 Git 忽略的 `output/tools/`，下載 ZIP 的 SHA-256 為 `bc20cd716edf62e0ba110de1be31b8bebe4c520b8b6a09c791f9f3d4c4653f4b`，與官方頁面一致；沿用本機既有登入，project 核對為 `finpo-508709`。先以 R4 execution 驗證 Cloud Logging 的 PowerShell 7／`gcloud.cmd` 引號寫法，查得 31 行，其中 29 行為 `C76`，再取本場日誌。

**台股逐檔結果**（`quote_time` 為台北時間；6 檔 `price_kind=last_trade`、`trading_date=2026-09-29`、`session=regular`；下表旗標為抓取時存入的）：

| 代號 | Yahoo 價格 | `quote_time` | 存入旗標 | MIS 逐秒對齊 |
|---|---:|---|---|---|
| 2330 | 2480.00 | 11:25:08 | 無 | 未對齊 |
| 2317 | 252.00 | 11:25:14 | 無 | 未對齊 |
| 0050 | 111.50 | 11:25:21 | 無 | 未對齊 |
| 6488 | 955.00 | 11:25:18 | 無 | 未對齊 |
| 3529 | 3360.00 | 11:25:05 | 無 | 未對齊 |
| 006201 | 45.69 | 11:23:34 | `stale` | 未對齊 |

美股 AAPL、MSFT、BRK.B、VOO、QQQ 亦全數抓價成功，`trading_date=2026-09-28` 且均帶 `market_closed`。BRK.B 的 `quote_time` 為台北 09-29 04:05:25、晚於一般時段收盤，另帶 `session_unknown`；其餘 4 檔的 `session=closed`。view 旗標比存入旗標多 `cached`，006201 在 view 仍帶 `stale`。006201 從成交到接收約 1318.6 秒，超過程式的 1200 秒宣告延遲加 70 秒容許值，因此 `stale` **符合現行程式規則**；是否真的因為沒有新成交，MIS 未能獨立證實。

**MIS 參考與比對**：記錄從 11:13:34 到 11:54:03，每 5 秒輪詢一次，共 438 筆。最初 4 筆因本機沙箱拒絕網路連線而留下 `ConnectError`，改用可連線的執行方式後 434 筆均為 HTTP 200、`rtcode=0000`；首筆成功快照為 11:14:09，早於 Job 開始約 31 分鐘。以事前定案的台北時間 `d+t` **逐秒完全相等**為對齊條件，6 檔皆是 `no_snapshot_at_trade_time`，對齊 **0/6**；未用鄰近快照價格充當吻合。5 檔至少有一筆帶價（`z` 非 `-`）快照，006201 全程沒有帶價快照。2,604 筆報價欄位中，`tlong` 與 `d+t` 在本交易日全部一致；這和 R4 休市快照曾差 3,600 秒不同，但不改本場事前定好的對齊鍵。**台股盤中價格正確性結論為證據不足，不是價格不符，也不是已驗證吻合；006201 的 `stale` 亦只有規則核對，缺獨立成交時間證據。**

三份原始／衍生檔均在本機 Git 忽略的 `output/c76/`：

| 檔案 | SHA-256 |
|---|---|
| `r2-mis.jsonl` | `63bbe795cbc74e13b754f78980e6fe755470440d3b6a661c7323d92ff79ff311` |
| `r2.jsonl` | `ad5c63fc5371619a3be0f217456348e90c41995ecb36986e3d967f710859ff54` |
| `r2-compare.jsonl` | `d773888bdd4a3d7d02724eba849de9f0818449c87754bd96d52410b2cc2da984` |

**待 C7-6 收尾時清除**：本場 manifest 的 runs 為 `5562c234-6c5a-40ec-9a45-3adf191c9cd6`、`7ddc58fa-39fb-4e07-9858-e8b38a8990dc`、`a05864af-3631-4cd3-b587-200f7772549d`，refresh job 為 `0015ab84-cc5b-4029-82d5-c356f1656a48`。假持股目前仍在 revision 2；依原計畫等最後一場後才 `reset`，並先 dry-run 再 purge，各場未到收尾前不刪。

### R3 參考資料（2026-09-29 取得，R3 尚未執行）

這是 R3 台股 6 檔的比對基準，不是 R3 的結果。計畫書原把 09-29 晚上的 R3 台股價格記為證據不足（沒有現成參考值）；**2026-09-29 使用者決定補取官方收盤**，改為比對。取得時間為 2026-09-29 13:27:41Z（台北 21:27），網路為本機，不是 GCP。來源與 R4 相同：上市為 TWSE `rwd/zh/afterTrading/STOCK_DAY`（`date=20260929`），上櫃為 TPEx `www/zh-tw/afterTrading/tradingStock`（`date=2026/09/29`），6 筆皆為 HTTP 200。原始回應存於本機 `output/c76/r3-reference/`（Git 忽略）。

| 代號 | 市場 | 09-29 收盤 | 漲跌 | 前一列（09-24）收盤 |
|---|---|---|---|---|
| 2330 | 上市 | 2,475.00 | 0.00 | 2,475.00 |
| 2317 | 上市 | 250.50 | 0.00 | 250.50 |
| 0050 | 上市 ETF | 111.30 | −1.10 | 112.40 |
| 6488 | 上櫃 | 945.00 | −3.00 | 948.00 |
| 3529 | 上櫃 | 3,305.00 | +75.00 | 3,230.00 |
| 006201 | 上櫃 ETF | 46.00 | −0.17 | 46.17 |

解析以系統 Python 的標準庫直接讀原始檔，取日期為 `115/09/29` 的那一列，不取最後一列；這台沒有專案 venv，**未經 `c76_report.reference_closes` 解析**。每檔的漲跌都等於與前一列收盤的差，且前一列都是 09-24、數值與「R4 參考資料」表一致，可以排除欄位讀錯與日期錯位。各檔的 09-29 列都是回應的最後一列。006201 當日成交 101 張。

**2330 與 2317 的 09-29 收盤恰好等於 09-24 收盤**。對這兩檔，價格相等無法區分 Yahoo 回的是 09-29 收盤還是沿用 09-24 的舊值，判定須同時看 `trading_date` 是否為 09-29；只有價格相等不能算通過。

| 檔案 | SHA-256 |
|---|---|
| `fetched_at.txt` | `5b675002702088ed622d45c3b5ec986a35b0b1d3e52613e209a88a93d771fe38` |
| `twse-2330-202609.json` | `35ed3c3ccfcaa1a002eaf0585a0da5137b6491e646c441a23fa8ccb016380c84` |
| `twse-2317-202609.json` | `02febbc3bfb44be1a8a4fa89c86e2b0d329a6bbf069357f0567c2f13aba8ee59` |
| `twse-0050-202609.json` | `2e729f60ed9731af2be5250157937248e1a06729963b454bea4daddf4e2e8fe7` |
| `tpex-6488-20260929.json` | `0783cef9dceb93e0d7326ba8501a675b8a931ee0f4fe7528762e205fde0eb335` |
| `tpex-3529-20260929.json` | `82597c19369de2da9461ee73c981529144015b4625bb55d754ed6eecc9792785` |
| `tpex-006201-20260929.json` | `a224f06bfd235ccdbbd723a15ff82e40c999b2237067ccbbc3c311872fca144c` |

### R3　美股盤中（2026-09-29）

**結論：美股 5 檔取得當日一般時段成交，台股 6 檔價格等於 09-29 官方收盤。** 美股 5 檔都是 `last_trade`、`trading_date` 09-29、`session=regular`，成交時間在紐約 10:01:45–10:01:57，存入、估值、頁面三層都沒有 `market_closed` 或 `stale`。這是本專案**第一次**觀測到美股盤中的抓價結果。**美股價格正確性仍為證據不足**：沒有比較來源（2026-09-25 使用者決定）。台股 6 檔都帶 `market_closed`、`trading_date` 為 09-29，價格與「R3 參考資料」表**完全相等**。沒有 429、封鎖或逾時。只有一個樣本。

**執行機器**：本 repo 的這個工作目錄（執行 R4 的那台），pwsh 7.6.6，`gcloud` 解析為 `gcloud.ps1`，帳號與 project 經 `gcloud config list` 核對為 `finpo-508709`。R2 在另一台執行；兩台沒有同時執行 probe 或清單更新。

**執行前核對**（台北 21:34，觸發前 22:00:38 再核一次 execution 清單與映像）：

| 核對項 | 結果 |
|---|---|
| command／args | `/app/.venv/bin/python`；`-c` 與 `exec(…C76_PROBE…)`，共 2 個 |
| `C76_PROBE` | 11,068 字元，解碼後 git blob `2c87174d4da9794750f0b14e390002d442d83787`，與 `96a8dbd`、`HEAD` 的 `scripts/c76_probe.py` 相同 |
| 映像 | `sha256:5ceea993…`（`218b4b962c5a`）；Registry 內為 `b6347e610e87`、`244fd00583bb`、`218b4b962c5a` 三個，`06e2df807527` 已被清除政策刪除，沒有 Job 使用它 |
| 身分／規格 | `finpo-runtime`、`timeoutSeconds` 600、`maxRetries` 0。Job 預設 `C76_MODE=catalog`、未設 `C76_TICKERS`，執行時覆寫 |
| 最近一次 execution | `c76-source-probe` 為 R2 的 `p7jrp`（已完成）；`finpo-catalog-refresh` 只有 09-23 的 `xmm8g`。兩者都沒有執行中的 execution |

**執行**：`gcloud run jobs execute c76-source-probe --region=asia-northeast1 --update-env-vars="C76_MODE=refresh,C76_TICKERS=fixed" --wait`（值加雙引號，原因見計畫書「R3 執行準備」）

| 項目 | 值 |
|---|---|
| execution | `c76-source-probe-dnxnv`，`gcloud` 回報成功完成 |
| 觸發 → 腳本開始 | 14:00:59Z → 14:01:18.4Z（台北 22:00:59 → 22:01:18），約 19 秒。R4 為 31 秒 |
| execution 完成 | 14:02:03.4Z；`--wait` 在台北 22:02:06 返回（觸發後 67 秒） |
| instance | `f9c5d646-a353-43cd-b7d0-926ebb3efd44` |
| deadline／max_tickers | 110／0 |
| 更新工作 | `aa60a176-7045-4294-a93b-c051a210ef6b`，`succeeded`，「已完成：11/11 檔有可用報價」 |
| `refresh()` 耗時 | 40.464 秒 |
| **portfolio revision**（最後 `reset` 用） | **3**（R2 之後為 2，與預期一致） |
| **manifest**（併入清除清單） | `{"runs": ["6443d6c2-7c1b-4e1d-8f36-c05bec3b49e6", "7010f9ff-b832-41db-bd0a-585b7ffd0d3a", "ba7ca41d-4952-492b-8be0-09cc359dddea"], "refresh_jobs": ["aa60a176-7045-4294-a93b-c051a210ef6b"]}` |
| 錯誤行 | 0 |

**取日誌**：以計畫書「R3 執行準備」的 pwsh 7 寫法，第一次查詢即得 31 筆，其中 `C76 ` 開頭 29 筆：`start` 1、`batch` 3、`attempt` 11、`view` 11、`portfolio` 1、`job` 1、`manifest` 1、`error` 0，與預期相同。存為 `output/c76/r3.jsonl`（Git 忽略），SHA-256 `f0a3b45e72843de0dcbf019d48087e217c8b0a8a91c6d9f7d94863d0c380a0e5`。這台取得的 `job.message` 中文正常顯示；R2 在另一台取得時顯示為 `?`，因此字元流失較可能發生在那台的取得或顯示環節，**未查證**。

**各批**：第二批同時含台股與美股，跨市場共用預算在雲端第二次實際執行到（第一次為 R4），兩次都沒有截斷。

| run | 狀態 | 檔數 | 內容 | 開始（台北） | 結束（台北） | 牆鐘（秒） |
|---|---|---|---|---|---|---|
| `7010f9ff-…` | completed | 5 | 2330、2317、0050、6488、3529 | 22:01:21.3 | 22:01:40.9 | 19.647 |
| `6443d6c2-…` | completed | 5 | 006201、AAPL、MSFT、BRK.B、VOO | 22:01:41.2 | 22:01:56.8 | 15.580 |
| `ba7ca41d-…` | completed | 1 | QQQ | 22:01:57.1 | 22:02:00.1 | 3.036 |

**逐次嘗試**（每檔一次，全部 `success`；旗標為抓取當下存入的；表格由 `r3.jsonl` 以程式產生，未手抄）：

| 代號 | elapsed_ms | price | price_kind | quote_time | trading_date | session | marketState | delay | 存入旗標 |
|---|---|---|---|---|---|---|---|---|---|
| 2330 | 7539 | 2475.0 | last_trade | 09-29 13:30:09（台北） | 2026-09-29 | unknown | POSTPOST | 1200 | market_closed, session_unknown |
| 2317 | 2838 | 250.5 | last_trade | 09-29 13:30:04（台北） | 2026-09-29 | closed | POSTPOST | 1200 | market_closed |
| 0050 | 2893 | 111.3 | last_trade | 09-29 13:30:04（台北） | 2026-09-29 | closed | POSTPOST | 1200 | market_closed |
| 6488 | 2954 | 945.0 | last_trade | 09-29 13:30:04（台北） | 2026-09-29 | closed | POSTPOST | 1200 | market_closed |
| 3529 | 2908 | 3305.0 | last_trade | 09-29 13:30:31（台北） | 2026-09-29 | unknown | POSTPOST | 1200 | market_closed, session_unknown |
| 006201 | 2960 | 46.0 | last_trade | 09-29 13:30:39（台北） | 2026-09-29 | unknown | POSTPOST | 1200 | market_closed, session_unknown |
| AAPL | 3147 | 333.015 | last_trade | 09-29 10:01:45（紐約） | 2026-09-29 | regular | REGULAR | 0 | 無 |
| MSFT | 2834 | 504.4082 | last_trade | 09-29 10:01:49（紐約） | 2026-09-29 | regular | REGULAR | 0 | 無 |
| BRK.B | 3053 | 502.15 | last_trade | 09-29 10:01:49（紐約） | 2026-09-29 | regular | REGULAR | 0 | 無 |
| VOO | 3038 | 703.42 | last_trade | 09-29 10:01:51（紐約） | 2026-09-29 | regular | REGULAR | 0 | 無 |
| QQQ | 2880 | 738.22 | last_trade | 09-29 10:01:57（紐約） | 2026-09-29 | regular | REGULAR | 0 | 無 |

**逐檔判定**：人工判定，**未使用** `c76_report.py` 的逐檔判定（它是 R4 專用的，見計畫書）。判定依據是計畫書 R3 準備段的預期，以及 09-29 補記改過的台股預期。

| 代號 | 估值旗標 | 頁面旗標 | 官方收盤 | 價格比對 | 不符之處 |
|---|---|---|---|---|---|
| 2330 | market_closed, session_unknown | cached, market_closed, session_unknown | 2475.00 | 相等，且 `trading_date` 為 09-29 | 無 |
| 2317 | market_closed | cached, market_closed | 250.50 | 相等，且 `trading_date` 為 09-29 | 無 |
| 0050 | market_closed | cached, market_closed | 111.30 | 相等 | 無 |
| 6488 | market_closed | cached, market_closed | 945.00 | 相等 | 無 |
| 3529 | market_closed, session_unknown | cached, market_closed, session_unknown | 3305.00 | 相等 | 無 |
| 006201 | market_closed, session_unknown | cached, market_closed, session_unknown | 46.00 | 相等 | 無 |
| AAPL | 無 | cached | — | 證據不足 | 無 |
| MSFT | 無 | cached | — | 證據不足 | 無 |
| BRK.B | 無 | cached | — | 證據不足 | 無 |
| VOO | 無 | cached | — | 證據不足 | 無 |
| QQQ | 無 | cached | — | 證據不足 | 無 |

頁面 11 列都有市值，`failure_reason` 都是空的；頁面價格與本次抓到的價格一致（0 筆不符）。存入旗標帶 `freshness_unknown` 的有 0／11 檔。美股從成交到接收為 1–5 秒，宣告延遲 0 秒；頁面層在更新結束後重新判定，也沒有出現 `stale`。R3 準備段曾推測頁面層較容易出現 `stale`，本場沒有發生，只有一個樣本。

**人工核對時另外看到的**：
- **`session_unknown` 又是 2330、3529、006201 這三檔**，成交時間 13:30:09、13:30:31、13:30:39；另 3 檔為 13:30:04、判為 `closed`。與 R4 的規則說明一致（日曆收盤加 5 秒之外即標記）。今晚是 09-29 的收盤、不是 R4 那一筆報價，事前沒有預期，這裡只記下觀察。
- **2330 的第一次請求耗時 7,539 毫秒**，其餘 10 檔 2,834–3,147 毫秒。與 R4（7,448 毫秒）相同，都是容器的第一次 Yahoo 請求。
- 台股 `marketState` 為 `POSTPOST`，美股為 `REGULAR`。這是 Yahoo 回應的原始欄位，程式不以它判定休市。

### R5　吞吐量（2026-09-29）

**結論：截斷行為正確，`c` 已量得，`refresh_max_tickers` 的候選值待使用者決定。** 110 秒 deadline 截斷後，更新工作為 `partial`，訊息正確提示未處理的檔數與「再次更新會優先處理」；`refresh()` 耗時 110.034 秒，超出 110 秒 0.034 秒，在算式預留的 3 秒內，整個 `run_job` 在 118.5 秒內結束。沒有 429 或封鎖。**處理到的 40 檔全是台股**（09-26 的推估是約 40 檔、幾乎全為台股，實際 40 檔、美股 0 檔），所以 `c` 是**台股**的單檔成本，而且是在**台股休市時**量得的。

**時段與前提**：R3 同一晚。R3 沒有任何非成功的嘗試（沒有 `rate_limited` 或 `http_429`），R3 的 `--wait` 於 22:02:06 返回，R5 於 22:04:54 觸發，間隔約 2 分 48 秒，大於計畫書要求的 2 分鐘。

**執行前核對**（22:04:31）：映像仍為 `sha256:5ceea993…`，command 為 `/app/.venv/bin/python`；Registry 仍有 `218b4b962c5a`；最新 execution 為 R3 的 `dnxnv`（已完成），`finpo-catalog-refresh` 沒有新的 execution。

**執行**：`gcloud run jobs execute c76-source-probe --region=asia-northeast1 --update-env-vars="C76_MODE=refresh,C76_TICKERS=wide:150" --wait`

| 項目 | 值 |
|---|---|
| execution | `c76-source-probe-h8cz4`，`gcloud` 回報成功完成；容器日誌為 `Container called exit(0).` |
| 觸發 → 腳本開始 | 14:04:54Z → 14:05:10.1Z（台北 22:04:54 → 22:05:10），約 16 秒 |
| execution 完成 | 14:07:07.3Z；`--wait` 在台北 22:07:08 返回（觸發後 134 秒） |
| instance | `07b3f9bf-7508-45d6-ad23-8e4ed977cc5c` |
| deadline／max_tickers | 110／0 |
| 更新工作 | `b73cf54f-291d-4212-9361-77964821859b`，**`partial`**，「已完成：34/150 檔有可用報價；110 檔未在時限內處理，再次更新會優先處理這些標的」 |
| `refresh()` 耗時 | 110.034 秒（`refresh_started_at` 22:05:11.416） |
| **portfolio revision**（最後 `reset` 用） | **4** |
| **manifest**（併入清除清單） | `{"runs": ["5b7256be-9a86-4a43-8ae6-6ce85f71ffe6", "741c85e1-301c-415c-97eb-a6cd2ef9c2f4", "9827b751-21e6-44a5-9974-0dc71dce2060", "cda3fe06-76a4-46a4-a6e9-6db30c8c0a65", "dd4c883f-109a-443c-964e-27cb3018f4d0", "e2796bcf-eec2-483b-b1dd-07c05e6907ee", "e6d0122f-a906-4d11-89d4-a14328cd9390", "eb32caa4-c495-4dad-88eb-fa6faa78f648"], "refresh_jobs": ["b73cf54f-291d-4212-9361-77964821859b"]}` |
| 錯誤行 | 0 |

**取日誌**：第一次查詢即得 204 筆，其中 `C76 ` 開頭 202 筆：`start` 1、`batch` 8、`attempt` 40、`view` 150、`portfolio` 1、`job` 1、`manifest` 1、`error` 0，與預期相符（`view` 150、`portfolio` 1、`attempt` 不是 150）。另 2 筆為 `exit(0)` 與一筆空白 INFO。存為 `output/c76/r5.jsonl`（Git 忽略），SHA-256 `cca6c999686613561a995303db748731be5a7381c4fee3e7667933fb80116a5f`。

**150 檔名單**（`wide:150`，`portfolio` 行記錄的順序；前 75 檔為台股、後 75 檔為美股）：

2897 6790 6146 8176 3693 2441 1733 4147 4426 00743 009823 4133 00637L 3419 7740 6831 00870B 1615 5410 8429 9927 00400A 3228 4523 5529 8271 5604 1795 5533 6184 6517 00753L 1476 1453 00756B 2254 00902 5902 3018 00875 6506 3150 5236 6739 3713 6908 5543 008201 3581 6496 4419 2751 4746 2816 00787B 2380 3141 1710 5481 3128 00663L 00862B 3443 00972 1528 6508 3679 3592 4102 8929 3526 6148 8473 6144 2890 GRAN UPV ESRT DDFJ RRR FRTT NTRB EMLP IBMR IGR IVW CCM AESG ALK SHE NSIT JUCY XDIV CHOW GGUS XBAP UBOT BOIL FPS ALM GRNI JHMB GK EXPD JOBY QBIG JHX R BJ XIJN BFJA XMPT JUNM DDFF WDRN GDTC RDIV UHAL TCBS TRUI SHLD XTJA OCDB BMSI DJUL TDS PG HCIC JPRE PEXL GCAL JACK AGIX NVYY GDL PNI TMSF TGS DLX NEXA VEMY TLTX FIMU SMC PXH EES EROC KAI TENJ XJR

以頁面列的市場欄核對：前 75 檔全為 TW、後 75 檔全為 US；名單與固定 11 檔沒有重疊。實際處理到的恰為名單的前 40 檔，順序相同。

**計算**：`pwsh -NoProfile -File docs/c76-r5-calc.ps1 -Log output/c76/r5.jsonl`，定義見計畫書「R5 執行準備」。`c` = 該批牆鐘 ÷ 檔數；`c'` 把該批之後的空檔併入。

| 批 | run | 檔數 | 嘗試 | 牆鐘（秒） | 其後空檔（秒） | `c` | `c'` | 預算截斷 | 排除 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `dd4c883f-…` | 5 | 5 | 19.84 | 0.24 | 3.97 | 4.02 | 0 | 否 |
| 2 | `741c85e1-…` | 5 | 5 | 14.73 | 0.24 | 2.95 | 3.00 | 0 | 否 |
| 3 | `9827b751-…` | 5 | 5 | 13.97 | 0.21 | 2.79 | 2.84 | 0 | 否 |
| 4 | `5b7256be-…` | 5 | 5 | 13.71 | 0.25 | 2.74 | 2.79 | 0 | 否 |
| 5 | `e2796bcf-…` | 5 | 5 | 14.31 | 0.24 | 2.86 | 2.91 | 0 | 否 |
| 6 | `eb32caa4-…` | 5 | 5 | 13.96 | 0.23 | 2.79 | 2.84 | 0 | 否 |
| 7 | `e6d0122f-…` | 5 | 5 | 13.84 | 0.26 | 2.77 | 2.82 | 0 | 否 |
| 8 | `cda3fe06-…` | 5 | 5 | 2.38 | — | — | — | 4 | **是**（含 `cycle_budget_exhausted`） |

| 量 | 值 |
|---|---|
| `F`（第一批開始 − `refresh_started_at`，「`run_job` 開始到第一批開始」的上界） | 1.470 秒（R4 為 1.604，11 檔） |
| `W`（最後一批結束 → `refresh()` 返回） | 0.135 秒 |
| `refresh()` 超出 110 秒的部分 | 0.034 秒（含進入 `run_job` 之前的時間） |
| 用於 `c` 的批數 | 7／8 |
| `c`（p95，最近排名法；7 批時即最大值，為第 1 批） | 3.967 秒／檔 → `floor((110 − F) ÷ c)` = **27** |
| `c`，不含第 1 批（6 批，最大值為第 2 批） | 2.947 秒／檔 → **36** |
| `c'`（p95，含空檔） | 4.016 秒／檔 → **27** |

**`refresh_max_tickers` 未決定**。候選為 27（含第 1 批的暖機，計畫書原定取法）、36（不含第 1 批），或維持 `0`（只由 deadline 約束；本場證明截斷時會正確收尾，這個選項也有數據支持）。依計畫書，用哪一個由使用者決定；決定前**不寫入** `deploy/cloud.toml`（`D3`）。

**逐次嘗試**（表格由 `r5.jsonl` 以程式產生，未手抄；旗標為抓取當下存入的）：

| 批 | 代號 | status | reason | executed | elapsed_ms | price | quote_time（台北） | session | 存入旗標 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2897 | success | — | true | 7973 | 10.95 | 09-29 13:30:16 | unknown | market_closed, session_unknown |
| 1 | 6790 | success | — | true | 2915 | 37.6 | 09-29 13:30:24 | unknown | market_closed, session_unknown |
| 1 | 6146 | success | — | true | 2811 | 180.0 | 09-29 13:30:28 | unknown | market_closed, session_unknown |
| 1 | 8176 | success | — | true | 2981 | 9.78 | 09-29 13:30:21 | unknown | market_closed, session_unknown |
| 1 | 3693 | success | — | true | 2752 | 702.0 | 09-29 13:30:18 | unknown | market_closed, session_unknown |
| 2 | 2441 | success | — | true | 2850 | 122.0 | 09-29 13:30:38 | unknown | market_closed, session_unknown |
| 2 | 1733 | success | — | true | 2696 | 29.45 | 09-29 13:30:16 | unknown | market_closed, session_unknown |
| 2 | 4147 | success | — | true | 2727 | 63.0 | 09-29 13:30:11 | unknown | market_closed, session_unknown |
| 2 | 4426 | success | — | true | 3014 | 7.61 | 09-29 13:30:31 | unknown | market_closed, session_unknown |
| 2 | 00743 | invalid_payload | normalization_failed | true | 3040 | — | — | — | — |
| 3 | 009823 | success | — | true | 2728 | 10.43 | 09-29 13:30:18 | unknown | market_closed, session_unknown |
| 3 | 4133 | success | — | true | 2800 | 20.45 | 09-29 13:30:01 | closed | market_closed |
| 3 | 00637L | success | — | true | 2691 | 18.17 | 09-29 13:30:05 | closed | market_closed |
| 3 | 3419 | success | — | true | 2743 | 11.8 | 09-29 13:30:35 | unknown | market_closed, session_unknown |
| 3 | 7740 | success | — | true | 2636 | 102.0 | 09-29 13:30:26 | unknown | market_closed, session_unknown |
| 4 | 6831 | success | — | true | 2619 | 492.0 | 09-29 13:30:37 | unknown | market_closed, session_unknown |
| 4 | 00870B | success | — | true | 2674 | 26.22 | 09-29 11:03:43 | closed | market_closed, stale |
| 4 | 1615 | success | — | true | 2663 | 42.6 | 09-29 13:30:35 | unknown | market_closed, session_unknown |
| 4 | 5410 | success | — | true | 2644 | 33.2 | 09-29 13:30:08 | unknown | market_closed, session_unknown |
| 4 | 8429 | success | — | true | 2731 | 5.85 | 09-29 13:30:36 | unknown | market_closed, session_unknown |
| 5 | 9927 | success | — | true | 2753 | 69.9 | 09-29 13:30:23 | unknown | market_closed, session_unknown |
| 5 | 00400A | success | — | true | 2984 | 15.51 | 09-29 13:30:05 | closed | market_closed |
| 5 | 3228 | success | — | true | 2674 | 180.0 | 09-29 13:30:12 | unknown | market_closed, session_unknown |
| 5 | 4523 | success | — | true | 2842 | 23.85 | 09-29 13:30:01 | closed | market_closed |
| 5 | 5529 | success | — | true | 2669 | 26.5 | 09-29 13:30:01 | closed | market_closed |
| 6 | 8271 | success | — | true | 2750 | 199.5 | 09-29 13:30:27 | unknown | market_closed, session_unknown |
| 6 | 5604 | success | — | true | 2673 | 30.95 | 09-29 13:30:39 | unknown | market_closed, session_unknown |
| 6 | 1795 | success | — | true | 2642 | 177.5 | 09-29 13:30:27 | unknown | market_closed, session_unknown |
| 6 | 5533 | success | — | true | 2706 | 13.85 | 09-29 13:30:38 | unknown | market_closed, session_unknown |
| 6 | 6184 | success | — | true | 2794 | 40.1 | 09-29 13:30:21 | unknown | market_closed, session_unknown |
| 7 | 6517 | success | — | true | 2623 | 62.8 | 09-29 13:30:01 | closed | market_closed |
| 7 | 00753L | success | — | true | 2703 | 8.61 | 09-29 13:30:02 | closed | market_closed |
| 7 | 1476 | success | — | true | 2736 | 273.0 | 09-29 13:30:01 | closed | market_closed |
| 7 | 1453 | success | — | true | 2769 | 10.8 | 09-29 13:30:05 | closed | market_closed |
| 7 | 00756B | success | — | true | 2618 | 29.14 | 09-29 13:30:34 | unknown | market_closed, session_unknown |
| 8 | 2254 | timeout | operation_deadline | true | 1992 | — | — | — | — |
| 8 | 00902 | timeout | cycle_budget_exhausted | false | 0 | — | — | — | — |
| 8 | 5902 | timeout | cycle_budget_exhausted | false | 0 | — | — | — | — |
| 8 | 3018 | timeout | cycle_budget_exhausted | false | 0 | — | — | — | — |
| 8 | 00875 | timeout | cycle_budget_exhausted | false | 0 | — | — | — | — |

34 筆成功的 `trading_date` 都是 09-29、都帶 `market_closed`；`elapsed_ms` 為 2,618–7,973，中位數 2,731。頁面 150 列中，34 列有價格且與本次抓到的一致；台股 41 列、美股 75 列沒有價格，`failure_reason` 為 `missing_quote`。存入旗標帶 `freshness_unknown` 的有 0 檔。

**非成功的嘗試，逐筆說明**：
- **4 筆 `timeout | cycle_budget_exhausted | executed=false`**（00902、5902、3018、00875）：預期中的預算截斷，沒有向來源送出請求。
- **2254：`timeout | operation_deadline | executed=true`，1,992 毫秒**。請求確實送出了。程式把單次抓取的時限設為剩餘預算與 `operation_timeout_seconds`（10 秒）取小者（`quoting.py` 的 `self.fetch(…, min(remaining, …))`），子程序逾時即回 `operation_deadline`（`providers.py`）。這次抓取開始於 22:06:58.988，距 `refresh()` 的 deadline（22:07:01.416）約 2.4 秒；子程序實際在 1,992 毫秒時結束，也就是拿到的時限約 2 秒，而本場成功嘗試的最短耗時為 2,618 毫秒。因此判定為**整體 deadline 截斷了一筆進行中的請求**，不是 Yahoo 的 10 秒逾時。這是依程式與時間點的推論；Yahoo 那一筆本來是否較慢，無從證明。它在第 8 批，第 8 批整批不計入 `c`。
- **00743：`invalid_payload | normalization_failed | executed=true`，3,040 毫秒**。回應可解析，但 `symbol`、`regularMarketPrice` 等 8 個欄位全為 null。00743 在官方清單中（頁面顯示名稱「國泰中國A150」）；Yahoo 為何回空欄位（已下市、代號對應不同或暫時性）**未查證**。它有實際送出請求，依計畫書計入 `c`（在第 2 批）。
- 沒有 `rate_limited`、`http_429`，也沒有 `content_type` 之類的封鎖跡象。

**人工核對時另外看到的**：
- **`session_unknown` 出現在 24／34 檔**。帶此旗標的成交時間為 13:30:08–13:30:39，沒有帶的為 13:30:01–13:30:05（另有 00870B 見下）。這與 R4 記下的規則（日曆收盤加 5 秒之外即標記）一致，並把 R4「6 檔中 3 檔」的影響範圍擴大到一個較大的樣本：本場 33 檔收盤成交中，有 24 檔落在 5 秒之外。是否放寬規則仍是另一個決定，本場不處理。
- **00870B 帶 `stale`**：最後成交在 09-29 11:03:43，`session=closed`、宣告延遲 1200 秒。這是檔低成交量的標的，當天午後可能沒有成交，但 `stale` 的觸發條件**未逐條對照 `quality.py` 核對**，也沒有獨立的成交資料佐證。
- **第一次請求（2897）耗時 7,973 毫秒**，與 R3、R4 的第一檔（7.5、7.4 秒）同一量級。這使第 1 批的 `c` 為 3.97，其他批為 2.74–2.95。暖機在 `min-instances=0` 下每次冷啟動都要付一次，但只付一次，所以另外列出不含第 1 批的值。

**本場量不到的**，不得因本場而宣稱：
- **美股的單檔成本**：處理到的 40 檔全是台股。R3 的美股逐檔 `elapsed_ms` 為 2,834–3,147，R4 為 2,525–2,746，只能作為**旁證**，而且 `elapsed_ms` 不含批次內的寫入，量法與 `c` 不同。
- **一批含兩個市場時的截斷**：本場沒有跨市場的批。
- **台股盤中的單檔成本**：本場在台股收盤後執行，Yahoo 對盤中標的的回應速度是否不同，未量測。
- **請求路徑上進入 `run_job` 之前的時間**：125 秒的邊緣上限從請求進來就開始算，本場只給出上界 `F`。正式路徑的端到端由 `C7-2`、`C7-4` 確認。

### R3、R5 寫入、待清除的資料

| 資料 | 處置 |
|---|---|
| R3 runs `7010f9ff-b832-41db-bd0a-585b7ffd0d3a`、`6443d6c2-7c1b-4e1d-8f36-c05bec3b49e6`、`ba7ca41d-4952-492b-8be0-09cc359dddea`；更新工作 `aa60a176-7045-4294-a93b-c051a210ef6b` | 列入清除清單 |
| R5 runs（8 筆，見上方 manifest）；更新工作 `b73cf54f-291d-4212-9361-77964821859b` | 列入清除清單 |
| 持股 | R3 後 revision 為 3，R5 存入 150 檔後為 **4**。收尾時 `C76_MODE=reset` 以 `C76_EXPECT_REVISION=4` 還原，除非之後又有場次 |

至此，清除清單包含 R1、R2、R3、R4、R5 五場的 manifest。五場都沒有 429，預期不會有仍由這些嘗試維持的來源冷卻；`cloud_db purge` 本身也會檢查，遇到時整筆拒絕。**2026-09-30 補記：已清除**，見下節。

### 收尾（2026-09-30）

**結論：五場的量測資料已全部清除，假持股已還原為空，`c76-source-probe` 已刪除。清除後以唯讀查詢核對：以 id 查各表都是 0 筆，官方清單沒有被動到。** `refresh_max_tickers` 由使用者決定取 **27**，理由與算式見 R5 節及 `deploy/cloud.toml` 的註解。

**執行機器與分工**：在執行 R1、R2 的那台（本 repo 的這個工作目錄）執行。這天，我方的自動執行權限擋下了 `reset` 與清除清單的準備，所以使用者決定由本人執行這兩步；`purge` 本來就只能由管理者執行（runtime 沒有 DELETE）。使用者的 `!` 前綴這天跑在 Windows PowerShell 5.1，**讀日誌一律改用 Git Bash**，以避開本檔 R3 節記錄的 5.1 靜默 0 筆問題。在 5.1 下執行 dry-run 時，`!` 介面會印出 `Read-Host` 的提示卻收不到輸入，所以 `purge` 改在獨立的 PowerShell 視窗執行。

| 步驟 | 執行者與方式 | 結果 |
|---|---|---|
| 1. `reset` | 使用者，PowerShell 5.1：`gcloud run jobs execute c76-source-probe --region=asia-northeast1 --update-env-vars="C76_MODE=reset,C76_EXPECT_REVISION=4" --wait` | execution `c76-source-probe-rhfjb`，02:01:01Z 建立、02:01:19Z 成功。日誌：`start` 行為 `mode: reset`，接著 **`reset`，`revision: 5`**，最後 `exit(0)`。**用 5.1 傳帶引號逗號的參數，實測沒有被拆開。**原始日誌 `output/c76/reset.jsonl`，SHA-256 `3d59420e88cd293d7e75272fdfb4debde993d30a1cfe65f96da11d45e74112d6`。`start` 行的 `max_tickers: 0` 是因為 Job 還在用舊映像，不是設定錯誤 |
| 2. 合併清除清單 | 使用者，以 `[IO.File]::WriteAllText` 寫成不帶 BOM 的 UTF-8 檔（5.1 的 `Set-Content -Encoding utf8` 會帶 BOM，而 `json.loads` 會拒絕） | `output/c76/purge-manifest.json`，SHA-256 `3477709ad56ae8a985d3767bc263bf3a07bc84f4071096d1783f189942c5580e`。以 `cloud_db.load_manifest` 在本機讀回：**17 個 run、5 個更新工作**，開頭沒有 BOM。R1、R2 兩場的 manifest 與這台的原始日誌 `r1.jsonl`、`r2.jsonl` 逐字相同；R3–R5 的原始日誌不在這台，以本檔的紀錄為準 |
| 3. dry-run | 使用者，以管理者帳號從本機連線，`DB_SSLROOTCERT` 指向 `deploy/supabase-ca.crt`；密碼以 `Read-Host -AsSecureString` 輸入，只放在該行程的環境變數，指令結束即移除 | `{"apply": false, "valuations": 73, "valuation_totals": 20, "quotes": 67, "fetch_attempts": 73, "cycles": 20, "holdings": 73, "runs": 17, "refresh_jobs": 5}`，沒有任何拒絕訊息 |
| 4. `--apply` | 同上，另加 `--apply` | `{"apply": true, …}`，**各表筆數與 dry-run 完全相同**；工具在同一交易內重做全部檢查，若實際刪除筆數與預覽不符會整筆回復，本次沒有觸發 |
| 5. 清除後核對 | 我方，唯讀，方式同上方「補查結果」：執行一次 `c76-source-probe`，只在該次覆寫 `C76_PROBE` 為 [`c76-purge-check.py`](c76-purge-check.py)，並把 `C76_MODE` 覆寫為原探針不接受的 `purge-check` | 見下表 |
| 6. 刪除 Job | 我方，經使用者確認：`gcloud run jobs delete c76-source-probe --region=asia-northeast1 --quiet` | `Deleted job [c76-source-probe].`，隨後 03:30:23Z 的 `gcloud run jobs list` 只剩 `finpo-catalog-refresh` |

**dry-run 筆數與各場紀錄的對照**（在 `--apply` 前核對）：`fetch_attempts` 73 = R2、R3、R4 各 11 ＋ R5 40；`holdings`、`valuations` 也是 73，每次嘗試一檔、一筆估值；`quotes` 67 = 11 × 3 ＋ R5 的成功 34；`cycles`、`valuation_totals` 20 = R2–R4 每場 4 個（第 2 批跨兩市場，佔 2 個）＋ R5 每批 1 個 × 8。每一項都說得出由來，沒有多也沒有少。

**清除後核對**（execution `c76-source-probe-zbpxg`，02:42:58Z，資料庫回報 `transaction_read_only = on`；腳本 SHA-256 `15f27edc8b5743de102140042854f1d72b6edb9e8c54eca95255b548886d094a`，blob `2fccb0dd7afddbaf3ed783b8cfc73ed530bc0b5b`，與容器內算出的雜湊相同；原始日誌 `output/c76/purge-check.jsonl`，SHA-256 `568d2ca497ff73d300b63ff7fc6dc9e5842cfb56c0b5b2e14c4f5a82f43a34c8`）：

| 項目 | 結果 |
|---|---|
| 以清單的 17 個 run 查 `RUN_TABLES`，範圍用 `cloud_db` 自己的 `run_scope`；以 5 個 id 查 `refresh_jobs` | **全部 0 筆** |
| 整個 `dashboard` 各表筆數 | `campaigns`、`scheduled_cycles`、`runs`、`holdings`、`cycles`、`fetch_attempts`、`quotes`、`valuations`、`valuation_totals`、`refresh_jobs` 都是 **0**；`portfolio` 1 列 |
| `portfolio` | revision **5**，`rows` 0、`instruments` 0、`fx` null |
| 官方清單 | 3 代、`catalog_instruments` 共 **40,311** 列，等於 13,457 ＋ 13,427 × 2，與上方「補查結果」一致，**沒有被動到**（使用者 09-23 決定保留） |
| Job 設定 | 上午補查、`reset` 與本次核對，三次執行之後的 `describe`，其 `spec.template` 都與補查前相同 |

**與計畫書不一致、照實記下的地方**：
- 計畫書要求刪除後「`gcloud run jobs list` 為 0 筆」，實際剩 1 筆 `finpo-catalog-refresh`。那句話寫在這支 Job 建立之前；這支 Job 是 `C6-3` 的常設資源，不是量測的臨時資源（見 R4 節的臨時資源表）。
- 「沒有其他 run」這一點，只證明了截至 02:42:58Z 沒有，不能推到之後。`C6-2` 尚未部署，正式服務還不存在，所以目前沒有其他寫入者。
- **`refresh_max_tickers = 27` 寫入後的測試**：本機以 `load_refresh_config` 讀回 `deadline_seconds=110, max_tickers=27`。另由使用者在本機執行 `uv run --frozen pytest tests/test_deploy_config.py -q`，結果為 `7 passed in 0.21s`（當天我方的自動執行權限擋下了這支測試）。**完整套件沒有以隔離容器程序重跑**，所以不宣稱完整套件通過。
- **推送與映像**（同日補記）：`a1e22b3`（文件）與 `ab1667c`（`cloud.toml`）一起推送，只觸發一次建置，run `36669128758` 成功（04:30:14Z → 04:30:59Z）。新映像 tag 為 `ab1667ccf7f7`，digest `sha256:7da85b3a2d0f97d3cad47968e2f3c59c79ace0e4cf56d8d352270d0e52346a1f`，建置日誌記錄的值與 `gcloud artifacts docker images list` 一致。推送前 Registry 有 `218b4b962c5a`、`b6347e610e87`、`244fd00583bb`；推送後暫時是 4 個，清除政策會刪掉的是最舊的 `218b4b962c5a`。
- **`finpo-catalog-refresh` 改指向新映像**：以 `gcloud run jobs update … --image=…@sha256:7da85b3a…` 更新。更新前後的 `spec.template` 逐欄比對，只有兩處不同：映像由 `5ceea993…` 變成 `7da85b3a…`，以及 gcloud 自動產生的 `client.knative.dev/nonce` 標籤。args（`--refresh-catalog`）、`finpo-runtime`、`timeoutSeconds` 600、`maxRetries` 0、`DB_PASSWORD` 的 Secret 掛載都沒有變。**新映像上的 `finpo-catalog-refresh` 還沒有實際執行過**；最遲在 10-06 22:35（台北）清單到期前的那次更新，就是它在新映像上的第一次執行，屆時要核對結果。**2026-09-30 補記**：已提前在 `C6-3` 執行（`finpo-catalog-refresh-tsp9t`，映像 `7da85b3a…`，成功）。新一代的到期時間為 10-07 05:51:20Z（台北 13:51），這是以管理者快照讀出的值。見 [C6 證據](cloud-C6-evidence.md) 的 `C6-3` 節。
- **本次沒有做反面測試**：沒有另外驗證清單以外的 id 會被 `purge` 拒絕。那部分由 `tests/test_cloud_db.py` 的案例守住（計畫書 `C7-6` 的「測試資料清除」補記），這裡沒有在雲端重測。

## C7-7（提前執行）　冷啟動量測

`C7-7` 本來就要量冷啟動，但這裡提前執行，因為它是 `refresh_deadline_seconds` 定案的最後一個未知減項：`C7-2` 量出的 125 秒是**整個請求**的總額，抓價工作只能用掉其中一部分。

### 量測服務

刻意與正式服務分離，用畢刪除：

| 項目 | 值 |
|---|---|
| 服務 | `c77-coldstart-probe`（`asia-northeast1`） |
| 映像 | 真實 web 映像 `sha256:5c7af5ed…`（tag `d836dbef0e48`） |
| 規格 | **1 vCPU／1 GiB**，比照 `C6-2`——CPU 與記憶體直接影響冷啟動 |
| secret | `PROXY_HMAC_SECRET`／`PROXY_HMAC_SECRET_PREV`／`DB_PASSWORD`，比照 `C6-2` 掛載（secret 解析發生在實例啟動階段，算進冷啟動） |
| 資料庫 | **未設定任何 `DB_*` 連線參數**，因此連不到 Supabase |

不接資料庫是安全的，因為 `Dashboard.__init__` 只載入設定、不建立連線，`/healthz` 也明文「只由行程本身回答」。

**附帶查明**：`DB_PASSWORD` 在啟動時就被設定驗證要求，即使整個啟動流程不連線。缺它會以 `ConfigurationError` 結束行程，不會延遲到第一個請求。`C6-2` 本來就會掛載它，但這解釋了為什麼它是啟動的必要條件而非選用。

### 結果

每組樣本等待 960 秒讓實例縮容，打一次冷請求、緊接一次熱請求。**三組都有對應的新 `listening on` 日誌行**，確認實例確實重建，不是靠等待時間推測。

| 樣本 | 冷 | 熱 | 差 |
|---|---|---|---|
| 1 | 3.418s | 0.259s | 3.16s |
| 2 | 2.300s | 0.465s | 1.84s |
| 3 | 2.448s | 0.269s | 2.18s |

本機另量應用自身初始化（容器啟動 → 開始監聽，取 docker daemon 時鐘，避開用戶端開銷）五次：1.348／1.271／1.246／1.335／1.227 秒，中位數 **1.27 秒**。兩者相減可知 Cloud Run 的排程、映像拉取與 secret 解析約佔 **1–2 秒**。

### `refresh_deadline_seconds` 定為 110 秒

```
125.0   邊緣硬上限（C7-2，最後成功點 124）
 −3.5   冷啟動最壞值（實測 3.418）
 −1.0   deadline 之後的收尾（組訊息、寫 job 列）
 −2.0   修正後殘餘超出（int() 截斷與批次粒度）
─────
118.5   理論上限；取 110，留 8.5 秒餘裕
```

已寫入 `deploy/cloud.toml`。**`refresh_max_tickers` 維持未設**（0 ＝ 只由 deadline 約束）：`C7-6` 尚未量出單檔實際成本，沒有那個數字而設上限只會無理由地延後標的。

### 量測途中發現的缺陷：一批可超出 deadline 達一整份 cycle 預算

`run_job` 每批把 cycle 預算壓成 `min(cycle_budget, remaining)`，註解寫著「no cycle can outlive the deadline」。**單就一個 cycle 而言正確**，但 `QuoteRunner.run()` 是：

```python
for market in sorted({h.market for h in holdings}):
    self.run_cycle(...)      # 每個市場各自 deadline = now + cycle_budget_seconds
```

每個市場**各拿一份完整預算**。`Market` 只有 `TW`／`US`，所以一批最壞耗時 `2 × min(cycle_budget, remaining)`。設批次開始時剩餘 R，結束時刻為 `(D − R) + 2 × min(50, R)`，在 **R = 50** 取極大值 **D + 50**。

台股加美股的混合持股正是本專案的目標情境（`C7-6` 要驗上市、上櫃、美股與 ETF），而依新鮮度排序後批次天然混市場，因此這不是邊緣情況。

**為什麼到現在才顯現**：預設 deadline 300 秒夠寬鬆，超出 50 秒看不出來。一旦為了塞進 125 秒而把 deadline 壓到 110 秒，程式就會跑到 160 秒，而邊緣在 125 秒切斷——使用者看到失敗，而不是 `C4-1` 設計要回傳的優雅部分完成。與 `C4-1` 的收斂缺陷同一類：單位層級推理正確，聚合層級不成立。

**修正**：`QuoteRunner.run()` 新增 `budget=` 參數，為這一次呼叫的所有市場 cycle 提供共用總額；`run_cycle()` 取 `min(cycle_budget_seconds, budget)`。`monitor.py` 直接呼叫 `run_cycle()` 而非 `run()`，且不傳 `budget`，因此常駐監控「每個市場各自排程一個 cycle」的語義完全不變。`dashboard.py` 改傳 `budget=deadline − now`。

參數用相對秒數而非絕對時刻，因為 `QuoteRunner` 的時鐘是可注入的（測試用假時鐘），傳絕對時刻會跨兩個時鐘。

**測試**（`test_one_budget_is_shared_across_markets_not_spent_once_per_market`）：每個市場 6 檔、每次 fetch 燒掉它拿到的完整 10 秒逾時，使 50 秒預算真正成為約束（每市場只放一檔時 cycle 做完就結束，上限根本碰不到，那樣的測試證明不了任何事）。兩個斷言：給 `budget=50` 時合計 ≤ 50 秒；不給時每市場各拿一份、合計 **剛好 100 秒**——後者正是缺陷的量化。

修正前該測試以 `TypeError` 失敗（參數不存在），所以「修正前會失敗」這件事只證明 API 是新的；真正量化缺陷的是那個 100 秒斷言。

完整套件於隔離的拋棄式 PostgreSQL 上 **362 passed、0 skipped**（基準 361，加本次新增 1）。

### `/healthz` 在 Cloud Run 公開網址上不可用

量測途中以 `/healthz` 當探針時發現它回 404，改用 `/` 才成立。查證結果：

| 測試 | 結果 |
|---|---|
| 本機容器 `GET /healthz` | **200 OK**，應用自己的標頭 |
| Cloud Run 公開網址 `GET /healthz` | **404**，Google 品牌錯誤頁，**Cloud Run 請求日誌無此筆** |
| `/healthz/`、`/healthz2`、`/nonexistent` | 全數抵達應用（403「拒絕不合法的 Host。」） |
| `?x=1` | 不影響，仍被攔截 |
| 無關網域 | wikipedia／cloudflare 的 `/healthz` 正常抵達；example.com 的 404 來自 `Server: cloudflare`，是該站自己的 |

所以：應用實作正確、網路沒有全面攔截，是**精確路徑 `/healthz` 在 `run.app` 前端被攔下、不轉發到容器**。該 404 還缺少其他回應都有的 `server: Google Frontend` 標頭。

**不宣稱確知是哪一層所為**——未從公司網路以外的位置複驗。但「請求不抵達容器」有 Cloud Run 日誌為證。

對 `C6-2` 的影響：計畫書要求把 startup／liveness probe 指向 `GET /healthz`。平台 probe 在內部直接打容器連接埠，不經公開網址前端，**推測不受影響但未驗證**；受影響的是任何從外部走公開網址的健康檢查——會拿到 404，而 404 看起來像部署失敗，不像被攔截。

### 臨時資源（本節）

| 資源 | 清除狀態 |
|---|---|
| Cloud Run `c77-coldstart-probe` | ✅ 已刪（2026-09-23） |

清除後複驗：`gcloud run services list --region=asia-northeast1` 為 0 筆。探針未推送自己的映像（直接沿用 `C6-1` 建出的正式映像），故 Artifact Registry 無需清理。

## C7-7-1　冷啟動：真實路徑（2026-10-05）

**結論：正式服務在 10-01 到 10-03 之間，因為 `AUTOSCALING` 啟動新實例共 19 次。排除一筆後，觸發啟動的那個請求在 Cloud Run 記到的 latency 為 2.967–4.175 秒，中位數 3.54 秒（n=18）。被排除的是 108 秒的更新報價，冷啟動的部分從它分不出來。其中 10 筆超過 `refresh_deadline_seconds` 算式所用的 3.5 秒。重算之後仍在 110 秒以內，所以不需要改設定；但 `deploy/cloud.toml` 的註解已經過時。**

### 方法

- **日誌**：以 `output/c77/tools/c77_alllogs.ps1` 唯讀匯出服務 `stock-quote` 在 2026-09-30T00:00Z 到 2026-10-05T00:48:15Z 之間的全部日誌（`resource.type="cloud_run_revision"`，含請求、stdout、系統日誌）。共 379 筆，沒有碰到 `--limit`。最後一筆在 10-03 04:58:17Z，之後沒有任何流量。
- **分析**：用 [`c77-coldstart.py`](c77-coldstart.py)。每一筆 `Starting new instance` 都以 `labels.instanceId` 找出同一實例的前兩個請求。
- **第一版分析漏掉了觸發的請求**：觸發啟動的那個請求，`timestamp` 是抵達時間，比 `Starting new instance` 早 0.01–0.04 秒。第一版只取啟動之後的請求，所以每次都漏掉它，看起來冷啟動只有 0.2 秒。改為不限時間、只依實例配對後，每個 `AUTOSCALING` 實例的第一個請求都比啟動事件早幾十毫秒。這個請求的 latency 包含了等實例啟動的時間。
- **stdout 的時間戳不能拿來量**：例如 10-01 02:46:58 那次，請求在啟動後約 2.94 秒就已回應，`listening` 的日誌卻記在啟動後 3.06 秒。stdout 的時間戳比實際晚，所以本節不採用「啟動到 `listening`」的值。

### 結果

`DEPLOYMENT_ROLLOUT` 不計入，那是部署時預先啟動的實例，不是使用者等到的冷啟動。

| 啟動（UTC） | revision | 觸發的請求 | 狀態 | latency |
|---|---|---|---|---|
| 10-01 02:46:58 | `00004-4v6` | GET `/api/session` | 200 | 2.967 s |
| 10-01 03:23:03 | `00004-4v6` | GET `/api/session` | 200 | 3.674 s |
| 10-01 04:25:27 | `00004-4v6` | GET `/api/session` | 200 | 3.343 s |
| 10-01 05:02:08 | `00004-4v6` | GET `/api/session` | 200 | 3.749 s |
| 10-01 05:49:28 | `00004-4v6` | GET `/api/session` | 200 | 3.850 s |
| 10-01 06:50:42 | `00004-4v6` | GET `/api/session` | 200 | 3.065 s |
| 10-01 08:05:30 | `00004-4v6` | PUT `/api/portfolio` | 400 | 4.175 s |
| 10-01 08:44:40 | `00004-4v6` | GET `/api/session` | 200 | 3.542 s |
| 10-01 09:11:42 | `00004-4v6` | GET `/api/session` | 200 | 3.039 s |
| 10-02 01:34:24 | `00004-4v6` | GET `/api/session` | 200 | 3.540 s |
| 10-02 02:37:32 | `00004-4v6` | GET `/api/session` | 200 | 3.061 s |
| 10-02 06:07:52 | `00005-pzn` | GET `/api/session` | 401 | 3.341 s |
| 10-02 06:51:46 | `00005-pzn` | GET `/api/session` | 200 | 4.159 s |
| 10-02 08:25:46 | `00005-pzn` | POST `/api/portfolio/refresh` | 403 | 3.947 s |
| 10-03 01:55:17 | `00005-pzn` | GET `/api/session` | 200 | 3.936 s |
| 10-03 02:51:17 | `00005-pzn` | GET `/api/session` | 200 | 3.146 s |
| 10-03 03:37:54 | `00005-pzn` | GET `/api/session` | 200 | 3.740 s |
| 10-03 03:54:25 | `00005-pzn` | POST `/api/portfolio/refresh` | 200 | 108.183 s（不計入） |
| 10-03 04:58:12 | `00007-66j` | GET `/api/session` | 200 | 3.440 s |

| 樣本 | n | 最小 | 中位數 | 最大 |
|---|---|---|---|---|
| 全部（排除更新報價） | 18 | 2.967 s | 3.541 s | 4.175 s |
| 只取 `/api/session` 200 | 15 | 2.967 s | 3.540 s | 4.159 s |
| 對照：同一批實例上非第一個的 `/api/session` 200 | 17 | 0.002 s | 0.003 s | 0.009 s |
| 對照：同一批實例上非第一個的 `/api/portfolio` 200 | 42 | 0.085 s | 0.180 s | 1.539 s |

### 解讀

- **冷啟動本身就是 3–4 秒，不含資料庫**。`/api/session` 只簽發 token（`web.py` 的 `session()`），不連資料庫，熱的時候 2–9 ms。所以觸發請求的 latency 幾乎全是等實例啟動的時間。
- **資料庫連線沒有「冷」的額外成本**。`Storage` 每次操作都新開一條連線，沒有連線池（`dashboard.py` 的 `with Storage(self.db)`），所以連資料庫的成本每個請求都要付，冷熱一樣。冷啟動後第一個 `/api/portfolio` 為 0.146–1.470 秒，和熱的分布（中位數 0.180 秒）沒有可分辨的差異。
- **這比 09-23 的探針慢**：探針三個樣本為 2.300–3.418 秒，真實路徑的中位數就有 3.54 秒。探針與正式服務的映像不同（`d836dbef0e48` 與 `a1fb03ff680d`／`35743d47289f`），量測時間也不同。**差異的原因沒有查**。
- **先前「推定是冷啟動」的值，這次都得到配對**：`C7-4` 第 0 項的 3.85 秒（10-01 05:49:28）、`C7-8` 第 6 步的 3.749 秒（05:02:08）、`C7-4` B4 的 3.542 秒（08:44:40）、`C7-4` C7 的 3.04 秒（09:11:42）、`C7-3-4` 的 403（10-02 08:25:46），都是新實例的第一個請求。

### 對 `refresh_deadline_seconds` 的影響

算式所用的冷啟動最壞值 3.5 秒，在 18 個樣本中有 10 個超過。以實測最大值 4.175 秒重算：

```
125.0  邊緣硬上限
−4.2   冷啟動最壞值（真實路徑，實測 4.175）
−1.0   收尾
−2.0   殘餘超出
─────
117.8  理論上限；110 仍留 7.8 秒餘裕（原為 8.5 秒）
```

所以 **110 秒不需要改**。依 `CLAUDE.md`，除非重新量過邊緣上限，這個值不得調高；7.8 秒的餘裕也不是調高它的理由。

但 `deploy/cloud.toml` 的註解仍寫著「worst measured … 3.5」與「118.5」，**已經過時**。改這個檔案、推送之後會觸發建置，並擠掉一個回滾窗口，所以**這次不改**，留到下一次有程式變更時一起改。

**冷啟動加上更新報價，端到端只有一個樣本**：10-03 03:54:25 那次，冷啟動加上 27 檔的更新共 108.183 秒，200（`C7-5-2`）。「冷啟動 + 跑滿 110 秒 deadline」的最壞情況沒有實測，仍是由算式推得。

### 界線

- **只量到 Cloud Run 這一段**。latency 是 Cloud Run 記的，不含 Worker、Access 與使用者到 Cloudflare 的網路。使用者實際等的時間更長，這次沒有量。
- **樣本只有一個使用者、三天、19 次**，時段都在台北的白天。
- 從縮容到下一次冷啟動的閒置時間沒有分析，啟動時間是否與閒置長短有關不知道。

## C7-7-2　抓價耗時（2026-10-05）

**結論：正式服務至今共 11 次更新報價，全部在資料庫裡，且與 Cloud Run 請求日誌的 11 筆 `POST /api/portfolio/refresh` 200 一一對上。27 檔的更新有 8 次，耗時 90.5–110.3 秒，中位數 103.7 秒。其中 1 次碰到 110 秒的 deadline（1 檔被截短），另有 2 次在 105.7–108.4 秒。批次內的單檔成本，三種市場組合的合計平均都在 3.57–3.76 秒／檔，沒有出現 429 或封鎖。**

### 方法

- 查詢為 [`c77-refresh-durations.sql`](c77-refresh-durations.sql)，唯讀，輸出不含代碼與金額。執行前在本機的拋棄式 `postgres:17-alpine` 上用 `0001_initial.sql` 建表、放入假資料，逐欄和手算核對過（涵蓋跨市場、逾時、未完成的 job）。
- 由使用者在 Supabase SQL Editor 執行兩段，結果貼回。
- job 與 run 之間沒有外鍵，以「run 的 `started_at` 落在 job 的起訖之間」歸屬。更新有 advisory lock 互斥，時間窗不重疊。
- **兩段的合計互相核對過**：批次 51 = 51，處理檔次 222 = 222，未成功 1 = 1。

### 查詢 1：每個 job

| # | 建立（UTC） | 總耗時 | 狀態 | 批數 | 檔數 | 未成功 | 準備 | 收尾 | 每檔平均 | 請求 latency | 請求 − job |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10-01 07:09:10 | 110.269 s | `partial` | 6 | 27 | 1（`timeout`） | 2.273 s | 0.329 s | 4.084 s | 110.653 s | 0.384 s |
| 2 | 10-01 08:46:09 | 105.867 s | `succeeded` | 6 | 27 | 0 | 1.936 s | 0.201 s | 3.921 s | 106.178 s | 0.311 s |
| 3 | 10-01 08:49:32 | 101.687 s | `succeeded` | 6 | 27 | 0 | 1.739 s | 0.160 s | 3.766 s | 101.965 s | 0.278 s |
| 4 | 10-01 09:18:11 | 100.801 s | `partial`（27/32） | 6 | 27 | 0 | 1.980 s | 0.207 s | 3.733 s | 101.050 s | 0.249 s |
| 5 | 10-01 09:22:40 | 101.251 s | `partial`（27/32） | 6 | 27 | 0 | 1.899 s | 0.227 s | 3.750 s | 101.562 s | 0.311 s |
| 6 | 10-02 01:49:45 | 11.178 s | `succeeded` | 1 | 2 | 0 | 2.250 s | 0.277 s | 5.589 s | 11.510 s | 0.332 s |
| 7 | 10-02 01:51:24 | 9.611 s | `succeeded` | 1 | 2 | 0 | 2.083 s | 0.233 s | 4.806 s | 9.963 s | 0.352 s |
| 8 | 10-02 08:25:51 | 15.318 s | `succeeded` | 1 | 2 | 0 | 2.045 s | 0.191 s | 7.659 s | 15.685 s | 0.367 s |
| 9 | 10-03 03:54:28 | 105.731 s | `succeeded` | 6 | 27 | 0 | 1.725 s | 0.164 s | 3.916 s | 108.183 s | **2.452 s**（冷啟動） |
| 10 | 10-03 03:58:31 | 90.491 s | `succeeded` | 6 | 27 | 0 | 1.649 s | 0.186 s | 3.352 s | 90.772 s | 0.281 s |
| 11 | 10-03 04:08:46 | 108.394 s | `succeeded` | 6 | 27 | 0 | 1.982 s | 0.187 s | 4.015 s | 108.715 s | 0.321 s |

所有 job 的 `catalog_only` 都是 false，市場都是 `TW,US`。總耗時是 job 的 `created_at` 到 `completed_at`。請求 latency 取自 `C7-7-1` 匯出的請求日誌，以時間配對。

各 job 的來歷：
- 1 是 `C7-4` C2。
- 2、3 是 `C7-4` B4、C5、C6。
- 4、5 是 `C7-4` C3（F3，32 檔；上限 27，所以每次都有 5 檔超出）。
- 6–8 是 F4（2 檔）。
- 9–11 是 `C7-5-2`、`C7-5-3`、`C7-5-4`。

job 1 的訊息沒有提到截短，因為當時的映像還沒有訊息修正（`842becc`）。

### 查詢 2：每一批，依市場組合

| 組合 | 批數 | 檔次 | 未成功 | 最小 | 中位數 | 最大 | 合計平均 |
|---|---|---|---|---|---|---|---|
| TW | 8 | 34 | 0 | 3.475 | 3.541 | 4.732 | 3.702 |
| TW+US | 21 | 87 | 0 | 3.145 | 3.693 | 6.541 | 3.762 |
| US | 22 | 101 | 1 | 3.005 | 3.626 | 3.915 | 3.571 |

單位都是秒／檔。一批的耗時取第一次嘗試開始到最後一次嘗試結束，**不含批與批之間的空檔**。

### 耗時拆解

以 27 檔、6 批的更新為例，時間花在這幾處：

| 部分 | 實測 | 算式的預留 |
|---|---|---|
| 請求進來到 job 建立、job 結束到回應 | 0.25–0.38 s（熱）；冷啟動時 2.45 s | 冷啟動 3.5 s（`C7-7-1` 已改為 4.2 s） |
| 準備（job 建立到第一次抓價） | 1.65–2.27 s | 沒有單列 |
| 批與批之間 | 平均 0.45 s／批（全部 job 的內部時間 836.7 s，減去批次合計 813.8 s，再除以 51 批） | 沒有單列 |
| 抓價 | 3.57–3.76 s／檔（合計平均） | — |
| 收尾（最後一次抓價到 job 結束） | 0.16–0.33 s | 1.0 s |

準備的 2 秒是每次都要付的固定成本，所以只有 2 檔時，每檔平均被拉高到 4.8–7.7 秒。準備的 2 秒花在哪一步，這次沒有拆開。

### 解讀

- **27 檔貼著 deadline 跑**。依上表估算，27 檔約需 2 + 27 × 3.7 + 6 × 0.45 ≈ 104.6 秒，離 110 秒只有約 5 秒。8 次裡 1 次被截短，2 次超過 105 秒。這和 `C7-4` C2 節「27 檔約需 111 秒」的預告一致；`refresh_max_tickers` 維持 27 是使用者 10-02 的決定，截短時會正確回傳 `partial`、下次優先處理。本項只記錄觀察到的頻率，不重新評估。
- **和 `C7-6` R5 的 `c` 量法不同，不能直接比**。R5 的 3.967 是 p95、含暖機，2.947 不含第 1 批；而且只有台股、在台股收盤後、從拋棄式 Job 量。本項是正式服務、台美混合、取合計平均。本項的台股批次中位數為 3.541 秒／檔，比 R5 不含第 1 批的 2.947 高，原因沒有查（時段、出口、組成都不同）。
- **冷啟動加更新只有一個樣本**（job 9）：請求 108.183 秒，比 job 本身多 2.45 秒，在 125 秒內。

### 界線

- **沒有美股盤中的樣本**。11 次的時間換算台北為 10-01 15:09–17:22、10-02 09:49–16:25、10-03 11:54–12:08。美股一般時段（台北約 21:30–04:00）完全沒有。台股盤中只有 10-02 上午的 2 檔、10-03 中午的 27 檔。
- **持股都是假資料**（F1、F3、F4），樣本只有 11 次、3 天，都由同一個使用者觸發。
- 只有 1 次未成功，所以失敗和重試對耗時的影響沒有樣本。
- 查詢 2 的批次耗時不含批間空檔；空檔的 0.45 秒是用總數相減推得的，沒有逐批量。

## C7-7-3　DB 容量與連線數（2026-10-05）

**結論：整個 database 為 38,505,619 bytes（約 38.5 MB），是 Free 500 MB 的 7.7%。`dashboard` 有 95% 是官方清單（5 代，每代約 5.15 MB）；報價相關的表合計約 1.1 MB，平均每檔次約 5 KB。閒置時共 12 條連線，`max_connections` 為 60，沒有任何 `finpo_app` 的連線。~~Supabase 儀表板的三項（Usage 頁、專案狀態、pooler 設定）還沒讀出，~~更新進行中的連線數排在 `C7-7-6`。**

**同日補記**：Supabase 儀表板已讀出。Usage 頁的 Database Size 為 0.054 GB（11%），比 SQL 讀到的大約 15 MB，~~原因沒有查~~（同日查明是 `template0`、`template1`，見「Database Size 差額的原因」節）；Egress 0.097 GB（2%）。**Pool Size 為 15**，這才是連線的實際上限。先前推得的「最壞約 20 條」是高估，已更正為約 11–12 條，仍是推論。計費週期與專案狀態沒有讀出。

### 方法

查詢為 [`c77-capacity.sql`](c77-capacity.sql)，唯讀，輸出不含代碼、金額與 IP。執行前在本機的拋棄式 `postgres:17-alpine` 上用 `0001`、`0002` migration 建表、放入假資料試跑過：
- 列數和放入的筆數相同；
- schema 合計等於各表加總；
- 已過期的清單和空的清單都正確顯示。

由使用者在 Supabase SQL Editor 分四段執行，結果貼回。

### 查詢 1：各表

| 表 | 列數 | 表 | 索引 | 合計（bytes） |
|---|---|---|---|---|
| `catalog_instruments` | 67,242 | 11,722,752 | 14,032,896 | **25,755,648** |
| `fetch_attempts` | 222 | 237,568 | 57,344 | 294,912 |
| `runs` | 51 | 221,184 | 49,152 | 270,336 |
| `holdings` | 222 | 57,344 | 73,728 | 131,072 |
| `quotes` | 221 | 81,920 | 49,152 | 131,072 |
| `cycles` | 72 | 57,344 | 65,536 | 122,880 |
| `valuations` | 222 | 65,536 | 40,960 | 106,496 |
| `portfolio` | 1 | 81,920 | 16,384 | 98,304 |
| `valuation_totals` | 72 | 49,152 | 16,384 | 65,536 |
| `instrument_catalog_generations` | 5 | 16,384 | 32,768 | 49,152 |
| `refresh_jobs` | 11 | 16,384 | 16,384 | 32,768 |
| `scheduled_cycles` | 0 | 8,192 | 24,576 | 32,768 |
| `schema_migrations` | 3 | 16,384 | 16,384 | 32,768 |
| `campaigns` | 0 | 8,192 | 8,192 | 16,384 |

`app` schema 沒有任何表。列數和 `C7-7-2` 對得上：`runs` 51 = 51 批，`fetch_attempts` 222 = 222 檔次，`refresh_jobs` 11 = 11 次。

`quotes` 是 221，比 222 少 1，就是 `C7-7-2` job 1 那一次逾時（逾時不產生報價）。

### 查詢 2：各 schema 與整個 database

| schema | 合計（bytes） |
|---|---|
| **（整個 database）** | **38,505,619** |
| `dashboard` | 27,140,096 |
| `pg_catalog` | 10,092,544 |
| `auth` | 1,179,648 |
| `storage` | 278,528 |
| `information_schema` | 253,952 |
| `realtime` | 57,344 |
| `vault` | 24,576 |

各 schema 加起來是 39,026,688，比整個 database 多約 0.5 MB。推定原因是 `pg_catalog` 裡有叢集共用的系統表（例如角色、database 清單），它們存在 database 目錄之外，`pg_database_size` 不算它們。**沒有查證**。

和 `C5-6`（初始化後、還沒有任何業務資料）相比：
- 整個 database 從 11,521,171 增加到 38,505,619，多了約 27.0 MB；
- `dashboard` 從 401,408 增加到 27,140,096。

### 查詢 3：各代官方清單

| # | generation | 完成（UTC） | 到期（UTC） | 未到期 | 列數 | 台股 | 美股 |
|---|---|---|---|---|---|---|---|
| 1 | `489f036e` | 09-23 08:15:21 | 09-30 08:15:21 | 否 | 13,427 | 2,363 | 11,064 |
| 2 | `73dd61a0` | 09-23 09:10:40 | 09-30 09:10:40 | 否 | 13,427 | 2,363 | 11,064 |
| 3 | `57d47501` | 09-29 14:35:34 | 10-06 14:35:34 | 是 | 13,457 | 2,363 | 11,094 |
| 4 | `8bdf148c` | 09-30 05:51:20 | 10-07 05:51:20 | 是 | 13,454 | 2,363 | 11,091 |
| 5 | `5a49077d` | 10-02 02:55:29 | 10-09 02:55:29 | 是 | 13,477 | 2,363 | 11,114 |

- **補上 `C6-3` 留下的缺口**：`C6-3` 記著「新 generation 的列數沒有讀出」，那一代（`tsp9t`）是第 4 代，13,454 列。`ljtrf` 是第 5 代，13,477 列。
- 五代的台股都是 2,363 檔，美股在 11,064–11,114 之間變動。
- 現行清單 10-09 02:55:29Z（台北 10:55）到期，和 `CLAUDE.md` 的到期提醒一致。
- **第 1、2 代已經過期，但還在**。`prune` 從來沒有執行過；就算執行，依 `C5-6` 也只刪超過 30 天的，它們要到 10-23 之後才符合條件。

### 查詢 4：閒置時的連線

| 角色 | 應用程式 | 類型 | 狀態 | 數量 |
|---|---|---|---|---|
| — | — | archiver、autovacuum launcher、background writer、checkpointer、walwriter | — | 各 1，共 5 |
| `authenticator` | PostgREST 14.5 | client backend | idle | 1 |
| `postgres` | pg_net 0.20.4 | pg_net worker | idle | 1 |
| `postgres` | supabase/dashboard-query-editor | client backend | active | 1（這次查詢本身） |
| `supabase_admin` | — | client backend | idle | 1 |
| `supabase_admin` | — | logical replication launcher | — | 1 |
| `supabase_admin` | pg_cron scheduler | pg_cron launcher | — | 1 |
| `supabase_admin` | postgres_exporter | client backend | idle | 1 |
| **上限** | `max_connections` = **60**，`superuser_reserved_connections` = 3 | | | 目前共 12 |

- **閒置時沒有 `finpo_app` 的連線**，和 `C7-7-1` 讀程式的結論一致：沒有連線池，每次操作開一條、用完就關。session pooler 在用戶端斷開後，也沒有留下伺服器端的連線。
- Supabase 自己的服務佔了 7 條（不含背景程序與這次查詢）。

**更新進行中的連線數還沒讀**，排在 `C7-7-6` 同場。以下是讀程式推得的上限，**未實測**：
- 一次更新最多同時開 2 條。`run_job` 在整個批次迴圈期間都握著一條；迴圈內每批結束時，`progress()` → `put_job()` 再另開一條寫入進度（`dashboard.py` 的 `with Storage(self.db) as own`）。`claim` 的那條在 `run_job` 開始前就已關閉，不會和它們重疊。
- ~~Cloud Run 的 max 為 1、concurrency 為 10。最壞情況約 10 × 2 = 20 條，加上 Supabase 自己的約 12 條，仍在 57 條（60 − 3）以內。~~
- ~~但 pooler 的 Pool Size 可能比 `max_connections` 更早成為上限，那個值還沒讀到。~~
- **同日更正**：上面兩點高估了，而且比錯了對象。
  - 同一時間只會有一個更新在跑：其他請求的 `claim` 會讀到 `running` 的 job 並直接回傳，只用 1 條連線。其餘路徑（`get`、`save`、`valuation`、`job`）都是一次 1 條，用完就關。
  - 所以 Cloud Run 的 max 為 1、concurrency 為 10 時，`finpo_app` 最多約 2 + 9 = 11 條。清單更新 Job（`web --refresh-catalog`）若同時在跑，再加 1 條。
  - 真正的上限是 pooler 的 **Pool Size 15**（見下方），不是 `max_connections` 60。11–12 條在 15 以內。
  - **以上是讀程式推得的，未實測**。rollout 期間兩個 revision 可能各有一個實例，這時上限會更高，沒有算進來。連線數超過 Pool Size 時 Supavisor 會怎麼處理（排隊或拒絕），也沒有查證。

### 成長估算（由上表推得，不是量測）

- **官方清單**：每代約 5.15 MB（每列約 383 bytes，含索引），每週一代。
  - **只要定期 `prune`**，會一直保留最新兩代，再加上 30 天內的那幾代，穩定在約 5–6 代、25–30 MB。
  - **完全不 `prune`**，一年約 270 MB，是 Free 上限的一半以上。
- **報價**：報價相關的 7 張表合計 1,122,304 bytes，222 檔次，**平均每檔次約 5 KB**。一次 27 檔的更新約 133 KiB。
  - 若每天更新 10 次、保留 30 天，約 40 MB。
  - 這只是一個假設情境，不是使用量的預測。
- `C5-6` 已經記過：刪除後空間可以重用，但檔案不一定縮小，也不會自動 `VACUUM FULL`。
- **結論**：容量在可見的未來不是限制，但前提是有人照 `C5-6` 每週執行 `prune`。**目前從來沒有執行過**，這是營運上要補的事。

### Supabase 儀表板（2026-10-05，使用者讀出）

頁面位置取自 Supabase 文件裡的連結：組織的 `dashboard/org/_/usage`，以及專案的 `dashboard/project/_/database/settings`。Claude 的 WebFetch 被公司代理的 TLS 解密擋下（certificate signature failure），改用 app 內建的瀏覽器才讀到文件。

| 項目 | 值 |
|---|---|
| Database Size | **0.054 / 0.5 GB（11%）** |
| Egress | **0.097 / 5 GB（2%）** |
| Pool Size | **15** |
| Max Client Connections | 200 |

Usage 頁另註明「may take up to 1 hour to refresh」，而且目前不對超額計費，超過上限可能被限制。

- **Database Size 和 SQL 讀到的值對不上**：Usage 頁是 0.054 GB，`pg_database_size` 是 38,505,619 bytes（約 0.0385 GB），差了約 15 MB。~~原因沒有查。可能的因素有：Usage 頁算的範圍不同（例如含 WAL 或其他磁碟用量）、GB 和 GiB 的換算不同、或最多 1 小時的更新延遲。~~ **判斷是否接近上限時，以兩者中較大的 Usage 頁為準**。11% 仍遠低於上限。**同日已查明，見下一節**。
- **Egress 0.097 GB**：Supabase 送出的資料，大部分推定是 Cloud Run 讀資料庫的流量，但沒有拆開。時間區間沒有讀出。
- **Pool Size 15 是 `finpo_app` 連線的實際上限**，比 `max_connections` 60 小得多。推得的最多 11–12 條在這之內（見上方更正）。
- **未讀**：計費週期、專案狀態（Active 與否）。

### Database Size 差額的原因：Supabase 算的是整個叢集（2026-10-05）

**結論：差額是 `template0` 與 `template1`**。Supabase 的 Database Size 是叢集內所有 database 的合計，而 `c77-capacity.sql` 查詢 2 只量了目前這個 database。三個加總為 53,779,253 bytes，四捨五入就是 Usage 頁的 0.054 GB。

**依據是 Supabase 文件**（`docs/guides/platform/database-size`，以 app 內建瀏覽器讀取）：
- Database size 的定義，就是對 `pg_database` 的每一列取 `pg_database_size` 再加總。
- 這個指標每天更新一次。
- Free 方案在 database size 超過 500 MB 時變成唯讀。那個 500 MB 指的就是這個 database size，不是 disk size；disk 另有 1 GB。

**查詢**為 [`c77-dbsize.sql`](c77-dbsize.sql)，唯讀。

**本機試跑**：在拋棄式 `postgres:17-alpine` 上，分別以超級使用者和無權限角色執行。
- 無權限時，讀不到的那一列顯示 NULL，查詢不中斷。
- WAL 的查詢在無權限時會報錯。

本機的 `template0`、`template1` 各約 7.5 MB。**送出之前先寫下了預測**：若 Supabase 上也只有這三個 database，合計約 53.6 MB ≈ 0.054 GB。

**Supabase 上的結果**（使用者在 SQL Editor 執行）：

| database | 可連線 | bytes |
|---|---|---|
| `postgres`（目前這個） | 是 | 38,505,619 |
| `template1` | 是 | 7,752,851 |
| `template0` | 否 | 7,520,783 |
| **合計** | | **53,779,253** |

| WAL 檔數 | WAL bytes |
|---|---|
| 5 | 67,109,231 |

- **預測成立**：只有三個 database，沒有 NULL 列，合計 53,779,253 bytes。
  - 以 10⁹ 換算為 0.0538 GB，四捨五入是 0.054，和 Usage 頁一致；以 GiB 換算會是 0.050。所以 Usage 頁推定用的是十進位 GB，**沒有其他佐證**。
- `postgres` 為 38,505,619 bytes，和稍早 `c77-capacity.sql` 的值一位不差，兩次查詢之間沒有寫入。
- **模板 database 約佔 15.3 MB**，這是固定的成本，不會隨使用成長。所以 Free 上限 500 MB 中，實際能給資料用的約 485 MB。
- **WAL 約 67 MB**，算在 disk size（1 GB）裡，不算在 500 MB 的 database size 裡。一個 WAL 檔是 16 MiB，4 個剛好是 67,108,864 bytes；第 5 個只有約 367 bytes，那是什麼檔沒有查。
- Supabase 文件另外寫到：組織層級的 Fair Use 限制，看的是**計費週期內每日 database size 的平均**，不是即時值。目前 11% 不受影響。
