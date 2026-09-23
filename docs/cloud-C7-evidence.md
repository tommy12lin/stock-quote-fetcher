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
| `C7-6` 外部來源驗收 | 🟡 進行中 | **R1 已完成**（本檔）：官方清單可從 GCP 出口取得，但清單更新耗時 135 秒、超過 125 秒邊緣上限，見本檔 `C7-6` 節。R2–R5 未開始 |
| `C7-7` 營運驗收 | 🟡 部分 | **冷啟動已提前量測**（本檔），其餘（匯出還原、回滾、計費、抓價耗時）未開始；含 `C1-8` 的預算通知送達 |

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

## C7-6　外部來源驗收（進行中）

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

**對 R2–R5 的時間限制**：本 generation 於 **2026-09-30 08:15:21Z（台北 16:15）** 到期（168 小時）。到期後 `run_job` 會在更新報價時先重抓整份清單，把約 135 秒混進報價耗時。**R2–R5 必須在到期前完成**，否則要先重跑 R1。

### 本場寫入、待清除的資料

| 資料 | 處置 |
|---|---|
| 更新工作 `c439a9f2-cb2b-488d-9a03-e55f1b905f34` | 列入清除清單（本場 manifest：`runs` 為空，`refresh_jobs` 為這一筆） |
| 清單 generation `489f036e-…` | **保留**（2026-09-23 使用者決定；`C6-3` 本來就需要） |
| 持股 | 未變動 |

原始日誌存於本機 `output/c76/r1.jsonl`（Git 忽略）。

### 臨時資源（本節）

| 資源 | 狀態 |
|---|---|
| Cloud Run Job `c76-source-probe` | **存在**，待 R2–R5 與清除完成後刪除 |

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
