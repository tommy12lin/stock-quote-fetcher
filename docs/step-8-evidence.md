# 步驟 8 執行紀錄

日期：2026-09-08。範圍：`report` 與證據輸出。指標定義依 [POC 驗收計畫](poc-validation.md) 第 4–6 節，門檻仍為未確認的建議值。

## 交付

| 檔案 | 內容 |
|---|---|
| `src/stock_quote_fetcher/reporting.py` | 唯讀報告：指標、分母重建、停機重建、價格比對、小計核對、結論分類與 JSON／Markdown 輸出 |
| `src/stock_quote_fetcher/storage.py` | 新增唯讀 `read_schedule`；`read_campaign` 改為沿用它，無新 migration |
| `src/stock_quote_fetcher/cli.py` | `report` 實作，新增 `--config` 與互斥的 `--run-id`／`--campaign-id`，並印出關鍵指標與未完成項目 |
| `tests/test_reporting.py` | 固定觀測紀錄的離線核對、UUID／範圍錯誤與隔離 PostgreSQL 的實跑案例 |
| `docs/system-spec.md`、`docs/architecture.md` | 第 3、5 節與模組／持久化章節同步 CLI、輸出路徑與分母規則 |
| `docs/step-8-validation.txt` | 185 項測試輸出 |

## 指標與分母規則

| 指標 | 分母 | 規則 |
|---|---|---|
| 名單涵蓋率 | 持股筆數 | 以估值來源取得幣別與市場相符、價格為正的報價才算可驗證；查無標的另列 unsupported |
| 首次取得成功率 | 已執行的首次操作 | 只採 `response_evidence.adapter.executed` 為真的操作；不因重試成功而改寫 |
| 重試後成功率 | 已執行的抓取機會 | 一個機會為（輪次、來源、標的），重試留在同一機會內 |
| 排程覆蓋率 | 到期的預定輪次 | 只有 `completed` 計為已執行；跳過、中斷與完全沒有紀錄的停機留在分母 |
| 時效達標率 | 到期一般時段窗口 × 該市場持股 | 排除 opening_delay、post_close 與未到期窗口並公開排除數；宣告延遲 ≤ 1200 秒且 quote age ≤ 1270 秒才算達標 |
| 操作耗時 | 已執行操作的 elapsed_ms | 最近排名 p50／p95／最大值，不內插 |

已被輪次認領的預定機會一律視為到期，時鐘不同步不會縮小分母。冷卻、輪次預算耗盡與查無標的不進入首次／重試成功率分母，但保留在狀態統計與 `not_executed_operations`。快取回傳不是本次來源成功，只出現在 `cache_usage` 與估值品質標記。

## 離線固定紀錄核對

`tests/test_reporting.py` 以一份可人工核對的紀錄驗證：一個 campaign 有七個預定機會（五個一般時段、一個收盤後、一個未到期），一個 interrupted run 產生四個輪次（兩個完成、一個 `scheduler_lag` 跳過、一個收盤後完成），共 9 個操作／8 個機會。

| 項目 | 期望值 | 依據 |
|---|---|---|
| 操作／機會／已執行／重試 | 9／8／5／1 | 三筆查無標的與一筆來源冷卻未執行 |
| 首次取得成功率 | 3/4 | 一筆首次逾時後重試才成功 |
| 重試後成功率 | 4/4 | 逾時的機會於同輪預算內成功 |
| 耗時 p50／p95 | 200／10000 ms | 最近排名，樣本 [120,150,200,300,10000] |
| 排程覆蓋率 | 3/6 | 六個到期機會中兩個完全沒有紀錄、一個跳過 |
| 排除維護窗口後 | 3/4 | 兩個缺漏落在事先計畫的維護窗口 |
| 停機重建 | 一段 2 個缺漏、7200 秒 | 依 3600 秒輪詢間隔合併連續缺漏 |
| 時效 | 合格 10，達標 1、逾時 1、缺漏 8 | 收盤後窗口排除 2、未到期排除 0 |
| 時效判定 | 證據不足 | 有逾時樣本且無法獨立判斷是否因無成交而變舊 |
| 價格吻合率 | 1/1（美股）；台股 0/0 | 台股缺標的類型，最小報價單位無法判定 |
| 小計重算 | 一致，顯示尾差 0.00 | 以持久化股數 × 價格與 `exact_sum` 重算 |

另驗證 `report` 不接受同時給定或都不給定範圍、拒絕非 UUID、campaign 範圍彙整各 run 摘要、單次 quote 的 run 無 campaign 時排程與時效指標回報無資料，以及 `read_schedule` 必須在 `report_snapshot` 中執行。

隔離 PostgreSQL 案例以固定時鐘跑一次 monitor 後產生報告，並在另一個 session 持有收集鎖時執行，確認 report 不需要鎖、JSON 與磁碟內容一致、campaign 範圍把停止後未認領的機會留在分母並重建停機。

```text
185 passed in 8.15s
```

完整輸出見 [step-8-validation.txt](step-8-validation.txt)。測試映像與執行方式同 [步驟 7 紀錄](step-7-evidence.md)。

## 既有專案資料庫實測

Engine 29.6.1、Compose v5.2.0、既有 PostgreSQL 17.10；映像 `stock-quote-fetcher:0.1.0` 重新建置後執行。

| 案例 | 結果 |
|---|---|
| monitor 執行中產生報告 | `docker compose up -d` 後容器 healthy 且持有收集鎖，`report` 仍成功產生（退出 0），確認 report 不取鎖 |
| run 範圍（步驟 7 的 quote run 419b30d3） | 名單涵蓋率 5/5；首次取得成功率 9/10；重試後成功率 9/10（未達建議 99%）；耗時 p50 2272／p95 10012／max 10012 ms（樣本 11，p95 未達建議 10 秒） |
| 每來源 | yahoo 5/5、twse 2/2、finnhub 2/2、tpex 0/1；tpex 的 timeout 後重試為 network_error，兩次皆如實計入 |
| 價格比對 | 樣本 4、對齊 1、吻合 1/1；未對齊原因 `time_or_price_basis_not_aligned` 2、`quality_not_comparable` 1 |
| 小計核對 | TWD 278480.00（degraded）、USD 精確 1507.935／顯示 1507.94，重算一致，顯示尾差 0.00；completeness complete 1、degraded 1 |
| 失敗與品質 | 逾時 1、network_error 1、時間未知報價 4、降級估值 1、快取使用 0 |
| campaign 範圍（7d3c6ec5） | 彙整 4 個 run（3 interrupted、1 當時 running）；預定機會 3600、到期 0、輪次 0；恢復紀錄含步驟 7 SIGKILL 後被標記的 run 8477b583 與 `recovered_at` |
| 結論分類 | run 範圍 V04 符合、V09 證據不足、V10 證據不足；campaign 範圍 V09 部分符合（有中斷與恢復紀錄）、其餘證據不足 |
| 未知 run-id | 「指定的 run 不存在。」退出 2，不建立輸出目錄 |

輸出落在 `output/step8/reports/<scope>-<id>/<產生時間>/report.json` 與 `report.md`，每次產生新目錄，不覆寫既有報告。

campaign 7d3c6ec5 的三個既有 run 都在台美股收盤後執行，因此預定機會全部尚未到期、沒有任何輪次；報告如實輸出涵蓋率 0/5 與排程／時效無資料，未以「沒有失敗」代替「沒有觀測」。

## 操作

```powershell
docker compose build app
docker compose run --rm app report --config /input/config.toml --run-id <run-id> --output /output
docker compose run --rm app report --config /input/config.toml --campaign-id <campaign-id> --output /output
```

`report` 使用 REPEATABLE READ READ ONLY 快照且不取收集鎖，可在 monitor 執行中產生，不需要先停止觀測。Git Bash 需設 `MSYS_NO_PATHCONV=1`，否則 `/input/config.toml` 會被改寫成 Windows 路徑。

## 未完成與界線

- 門檻（重試後成功率 99%、排程覆蓋率 99%、時效 95%、p95 ≤ 10 秒、每市場 3 個完整交易日）均為驗收計畫提出的建議值，報告標記 `proposed_unconfirmed`，只回報是否達到，不作為判定通過的依據。
- 無法從持久化資料獨立判斷行情是否因無成交而變舊，因此只要有逾時效樣本，時效結果一律為證據不足。
- 台股最小報價單位取決於標的類型（股票與 ETF 級距不同），quotes 未保存 asset_type，因此台股比對只輸出精確差異並標記 `tick_size_unknown`，不進入吻合率分母；美股採每股 0.01 美元。
- 本次沒有任何盤中輪次可統計：實測資料來自收盤後的 quote 與等待中的 monitor，因此時效達標率、排程覆蓋率與交易日數都不構成 V05、V06、V10 的成績。連續三個交易日觀測屬步驟 9。
- V01、V02、V03、V05–V08 由步驟 1–7 與步驟 9 執行，報告明列為不由本身判定，避免以報告產出代替功能驗收。
- 報告含持股代碼與股數，移交前依驗收第 7 節處理；報告不含密碼、API Key 或原始 provider 回應。
- `report` 只在成功產生報告時回 0；報告內的證據不足或未達建議門檻寫入報告與 stderr，不改變退出碼。
- 報告產生主機資訊（Python 與 platform）僅描述執行 `report` 的環境，run 的平台證據以 `image_id` 與 `package_version` 為準。

## 查核來源

- [POC 驗收計畫](poc-validation.md) 第 4–6 節：指標定義、時效規則、比對方法與報告七節格式。
- [PostgreSQL 交易隔離](https://www.postgresql.org/docs/current/transaction-iso.html)：REPEATABLE READ 提供單一快照，READ ONLY 交易不寫入。
- [PostgreSQL advisory lock](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS)：收集程序互斥使用 session 層級 advisory lock，report 不取用。
