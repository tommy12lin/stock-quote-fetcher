# C7 執行紀錄：Cloudflare 前端與端到端驗收

日期：2026-09-22 開檔。範圍：[雲端部署第一階段執行計畫](cloud-phase-1-plan.md) 的 `C7`。本檔只記錄**已實際執行並驗證**的結果；未執行的項目標為未完成，不預先宣稱通過。

**本檔不含任何秘密值。** 本 repository 為 public。Cloud Run 服務網址含 GCP 專案編號，與 `C1` 執行紀錄一致視為識別碼而非憑證，照實記錄。

## 進度

| 項目 | 狀態 | 備註 |
|---|---|---|
| `C7-1` Workers static assets 部署 | ⬜ 未開始 | |
| `C7-2` `/api/*` 代理與逾時對齊 | 🟡 部分完成 | **逾時量測已完成**（本檔）；代理實作、`run_worker_first`、HMAC 跨語言互通與 `Origin` 轉發待 `C6` 部署後 |
| `C7-3` 入口驗證與繞過測試 | ⬜ 未開始 | 承接 `C3-3` 的雲端驗收 |
| `C7-4` 功能驗收 | ⬜ 未開始 | |
| `C7-5` 持久性驗收 | ⬜ 未開始 | 承接 `C4` 的雲端完成條件 |
| `C7-6` 外部來源驗收 | ⬜ 未開始 | 與本檔一同決定 `refresh_max_tickers` |
| `C7-7` 營運驗收 | ⬜ 未開始 | 含 `C1-8` 的預算通知送達 |

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
