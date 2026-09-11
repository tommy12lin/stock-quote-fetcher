# 系統規格

版本：v0.5；日期：2026-09-08；狀態：CSV、資料模型、估值核心、PostgreSQL、官方標的映射、報價、monitor 排程、容器部署與 report 已實作；報價已保存官方商品類型，盤中連續觀測與交叉比對進行中。

## 1. 目的與範圍

主要目的為驗證免費優先的台美股報價取得方案，包含價格、幣別、時間、涵蓋率與穩定性。持股市值是用來驗證資料可用性的最小應用。

### 已確認需求

| ID | 需求 |
|---|---|
| R01 | 以 Python 開發；語言與套件追求最新且受維護的版本，LTS 解讀見架構文件 |
| R02 | 部署至 Linux Docker Container，POC 實作交付 Dockerfile 與 Docker Compose |
| R03 | CSV 輸入 ticker、每股買入價、持有股數，採 CLI 操作；數字開頭視為台股、英文字母開頭視為美股，不需 market 欄位或台股來源後綴 |
| R04 | 台股以 TWD、美股以 USD 計價，分別計算市值小計，不跨幣別相加 |
| R05 | 盤中可更新，可接受約 15–20 分鐘的來源延遲；免費優先，可申請免費 API Key |
| R06 | 買入價保存於輸入與持股資料，本次不計算損益 |
| R07 | 暫不處理手續費、多帳戶、現金、損益 |

### 設計預設

以下為本版設計選擇，可於實作前調整，並非使用者逐項指定：

- 支援台灣上市／上櫃普通股與 ETF、美國市場股票與 ETF；不含興櫃、權證、期權、OTC 與非 TWD／USD 商品。
- 先以約 10 檔代表標的驗證，不宣稱已涵蓋全市場。
- 採一般交易時段最新成交價；市場休市時使用最近可用的一般交易時段價格。美股盤前／盤後不納入估值。
- 持股數量在一次執行期間固定；股數因拆股等事件變更時需更新 CSV。POC 不自動調整持股。
- 預設每 60 秒啟動一輪抓取，依方案額度限制排程，不重疊執行。

## 2. CSV 契約

UTF-8，接受 BOM；固定三欄，欄名如下。範例買入價為虛構測試資料，不是行情：

```csv
ticker,buy_price,quantity
2330,900,100
0050,50,200
6488,1000,10
AAPL,180,2.5
VOO,400,1
```

| 欄位 | 規則 |
|---|---|
| ticker | 字串；去除首尾空白並標準化英文字母大小寫；保留前導零 |
| buy_price | 每股買入價，依市場使用 TWD 或 USD；有限且大於零的十進位數 |
| quantity | 持有股數，有限且大於零；台股必須為整數，美股可為小數 |

市場自動判斷規則（2026-09-08 確認）：

- 去除首尾空白並轉為大寫後，首字元為 ASCII 數字 `0–9` 視為台股，為英文字母 `A–Z` 視為美股；其他首字元拒絕。
- 台股輸入原始代碼，例如 `2330`、`0050`、`6488`、`00400A`；保留前導零與代碼內的英文字母，不需要輸入 `.TW`／`.TWO`，也不增加 market 欄位。
- 首字元只決定台美市場，不證明標的存在或受支援。抓價前以標的清單確認上市／上櫃、商品類型與幣別，再產生來源代碼，例如 Yahoo 的 `2330.TW`／`6488.TWO`；不得依碼數猜測上市／上櫃或輪流試抓兩種後綴。
- 美股使用美國市場 ticker。特殊美股代碼（例如不同股別）由市場清單與來源映射處理，不以任意字串替換猜測代碼。
- `validate` 僅離線驗證格式及依首字元套用股數規則；標的存在性與來源映射於 `quote`／`monitor` 抓價前確認。查無、映射不唯一或清單取得失敗須明確回報，不猜測來源代碼。

- 必填欄位遺漏、未知額外欄位、空值、非數字、NaN、Infinity、負值或零值皆拒絕。
- 本版拒絕同一標準化 ticker 重複列，回報行號；避免暗自推算平均成本。
- 空檔與只有標頭的檔案拒絕。
- 離線解析細節：三個欄名可調整順序，但名稱必須精確且各出現一次；空白資料列也拒絕。数值去除首尾空白後接受 ASCII 十進位與科學記號（例如 1.8e2），不接受底線分隔或全形數字。ticker 僅將 ASCII 英文字母轉大寫，不將其他 Unicode 字元轉成英文字母。
- 錯誤行號以 CSV 記錄起始的實體行為準，結構解析失敗則使用解析器回報行；任何錯誤不回傳部分持股。無法讀取檔案、UTF-8 編碼錯誤及驗證失敗均退出 2。
- CSV 結構或欄位驗證失敗時，整份輸入不生效、不開始抓價。
- 格式合法但查無標的、來源不支援、幣別不符，列為該標的錯誤；其他標的仍可完成抓價。
- 買入價與股數不傳給外部報價服務，只傳查詢所需的標的代碼。

## 3. 預定 CLI

`validate`、`db-check`、`migrate`、`instruments-refresh`、`resolve`、`quote`、`monitor`、`healthcheck` 與 `report` 已可執行。

```text
stock-poc validate --input /input/holdings.csv
stock-poc db-check --config /input/config.toml --connection-only
stock-poc migrate --config /input/config.toml
stock-poc db-check --config /input/config.toml
stock-poc instruments-refresh --config /input/config.toml
stock-poc resolve --input /input/holdings.csv --config /input/config.toml
stock-poc quote --input /input/holdings.csv --config /input/config.toml --output /output
stock-poc monitor --input /input/holdings.csv --config /input/config.toml --output /output [--campaign-id <campaign-id>]
stock-poc healthcheck --config /input/config.toml [--max-heartbeat-age-seconds <seconds>]
stock-poc report --config /input/config.toml --run-id <run-id> --output /output
stock-poc report --config /input/config.toml --campaign-id <campaign-id> --output /output
```

- `validate`：離線驗證 CSV，不連外。
- `db-check`：驗證資料庫連線、專用帳號、schema 版本與讀寫權限；--connection-only 僅檢查連線及 migration 所需 schema 權限。
- `migrate`：以專用帳號套用版本化 SQL，與收集程序互斥；不建立 database／schema，也不清除既有資料。先停止 monitor。
- `instruments-refresh`：從固定官方來源更新完整標的 generation；任一來源失敗不發布新版本。
- `resolve`：使用最新未過期清單驗證標的及顯示交易所、商品類型與 Yahoo 代碼；不抓行情。查無、不支援或歧義退出 3。
- `quote`：執行一次抓取、保存紀錄，輸出持股表與分幣別摘要。
- `monitor`：依交易日曆排定的輪次持續抓取並保存；收到停止訊號時完成或中止本輪、記錄狀態並安全退出。省略 `--campaign-id` 時自動續接輸入與公開設定相同且仍在期間內的 campaign，找到多個相符者則拒絕執行並要求明確指定。
- `healthcheck`：檢查資料庫可用性與收集程序心跳；分別回報心跳逾期與沒有進行中的 run，不抓價也不取收集鎖。`--max-heartbeat-age-seconds` 預設 120。
- `report`：從持久化紀錄產生可靠性報告，不重新抓價、不取收集鎖，可在 monitor 執行中產生。`--run-id` 與 `--campaign-id` 互斥且必須指定其一：run 範圍統計單一執行，campaign 範圍彙整同一 campaign 的所有 run 並附各 run 摘要。需要 `--config` 取得資料庫連線；預定機會、排程覆蓋率與時效分母來自 campaign 的預定輪次，單次 quote 的 run 沒有 campaign 時該類指標回報無資料。
- monitor 啟動時讀取並記錄 CSV 與設定的雜湊；CSV 修改後需重新啟動，新執行使用新的 run-id。續跑沿用原 campaign 及其已展開的預定輪次，只認領尚未執行的機會，不補抓過去缺口；落後排定時間達一個輪詢間隔者記為 skipped／scheduler_lag。
- 預定退出碼：0＝成功；2＝輸入／設定錯誤；3＝quote 有缺價、降級或品質無法確認；1＝不可恢復的執行錯誤。monitor 對單筆抓價失敗持續運行並記錄，不因此整個退出。`report` 只在成功產生報告時回 0；報告內的證據不足或未達建議門檻寫在報告與 stderr，不改變退出碼。

## 4. 報價契約與品質

每筆正規化報價至少包含：

| 欄位 | 意義 |
|---|---|
| instrument_id / provider_symbol | 系統標的識別與來源 ticker |
| market / currency / provider | 市場、幣別與來源 |
| price / price_kind | 十進位價格與 last_trade／close／bar_close 類型 |
| quote_time / time_precision | 來源時間與精度；未知時為空，不能以抓取時間代替 |
| received_at | 系統取得資料的 UTC 時間 |
| trading_date / session | 當地交易日與 regular／closed／unknown 狀態 |
| declared_delay_seconds | 已確認的來源宣告延遲，未知則為空 |
| fetch_status / quality_flags | 本次取得結果與資料品質標記 |

`fetch_status`：success、timeout、rate_limited、network_error、provider_error、invalid_payload、unsupported_symbol、interrupted。

`quality_flags` 可並存：cached、stale、time_unknown、future_time、market_closed、currency_mismatch、session_unknown、price_kind_mismatch。同一筆資料可為本次成功取得，但行情時間過舊。

- 價格必須有限且大於零；不以 0 或買入價補缺價。
- 驗證 market、currency、symbol 與輸入對應；幣別錯誤的資料不參與市值。
- 來源時間超過取得時間 5 秒以上時標示 future_time，保留證據但不採用該報價；5 秒為建議時鐘容許差，實作前核對主機校時。
- last_trade 為目標；若來源只能提供分鐘 K 線，記錄 bar_close 與區間時間，不假裝是逐筆成交價；是否可接受列入實測結論。2026-09-07 實測補註：yfinance 對台股與美股皆提供最新成交價與秒級來源時間，本輪不需啟用 bar_close 路徑；此規則保留給其他來源與退化情況。
- 不以還原股價乘目前持股，應使用未還原的一般交易時段價格。
- 保存 UTC 時間，顯示時附台灣／紐約當地時區；美股夏令時間、假日、提早收盤由交易日曆處理。
- 離線模型另以 pre_market／post_market 表示來源的盤前後資料，估值排除；未知 session 或時間以降級狀態呈現。bar_close 在來源接受政策確認前列為 price_kind_mismatch，不納入估值。
- 來源延遲 20 分鐘與 60 秒輪詢分開記錄，可能產生約 21 分鐘加網路處理時間的端到端資料年齡；不直接宣稱總延遲小於 20 分鐘。2026-09-07 實測補註：yfinance 宣告台股 20 分鐘、美股 0；此為來源宣告值，未經盤中觀測驗證，美股的端到端上限與門檻需另行討論確認。
- 低成交量標的的最後成交時間較舊不必然表示供應商故障；無法判斷時標示不確定，不計入已證明新鮮的資料。
- 開盤前與開盤後來源延遲尚未經過的期間，辨識前一交易日價格，避免誤判成當日盤中行情。

## 5. 市值與輸出

`單筆市值 = 持有股數 × 可用報價`。依幣別分組求和，不建立 TWD＋USD 的混合數字。

使用 Decimal，保留來源與輸入精度，內部運算不得提前四捨五入；顯示金額以 ROUND_HALF_UP 至小數二位。小計先加總未四捨五入值再顯示，列加總顯示值可能有尾差，報告附精確十進位字串供核對。

預定輸出為持股 CSV、摘要 JSON、可靠性報告 JSON／Markdown。以 run-id／cycle-id 分隔輸出，避免覆寫其他執行的證據。

| 輸出 | 內容 |
|---|---|
| 持股列 | ticker、股數、買入價、幣別、報價、價格類型、報價時間、取得時間、來源、市值、品質標記 |
| 幣別摘要 | currency、known_subtotal、total、持股列數、已估值列數、缺價數、降級數、completeness |
| 可靠性摘要 | 觀測期間、預期／實際輪數、請求成功率、缺漏、延遲分布與未能判定的項目 |

`report` 輸出寫入 `<output>/reports/<scope>-<id>/<產生時間>/report.json` 與 `report.md`，每次產生新目錄，不覆寫既有報告。JSON 為權威資料、Markdown 為同一份內容的可讀版本，內容依驗收計畫第 6 節分為觀測範圍與版本、規模、每來源／市場／標的指標、失敗與停機、價格比對、小計人工核對、結論與未完成項目七節。

指標定義依驗收計畫第 4 節：一個抓取機會為一組（輪次、來源、標的），重試留在同一機會內；只有 Adapter 實際執行的操作進入首次與重試成功率分母，冷卻、輪次預算耗盡與查無標的不進入；只有 completed 的輪次計為已執行機會，停機、跳過與中斷仍留在排程覆蓋率分母；時效只採一般交易時段窗口，開盤延遲與收盤後延長觀測排除並公開樣本數；耗時取最近排名 p50／p95／最大值，不做內插。門檻為建議值且標記 `proposed_unconfirmed`，報告只回報是否達到建議值。無法從紀錄判定者一律輸出證據不足，包含無法獨立判斷是否因無成交而變舊的逾時效樣本，以及沒有保存標的類型（schema 0003 之前）而無法判定最小報價單位的台股價格比對。

`completeness`：

- complete：所有該幣別持股可估值且符合當前市場狀態的品質規則。
- degraded：全部可估值，但使用舊快取、資料時效未知或其他需揭露的降級資料。
- partial：至少一筆無可用價；total 為 null，known_subtotal 僅為已知部分。
- unavailable：所有持股均無價；total 為 null，known_subtotal 為 0，但不能顯示為資產總值 0。

若先前有經驗證的報價，本次失敗可顯示該價格與原始時間，標記 cached／stale；不可把快取更新成「剛取得的新行情」。每筆來源的失敗紀錄仍保留。

步驟 2 的 `value_holdings` 為離線函式：接收持股及以原始 ticker 索引的已選用 Quote；不查價、不挑選或驗證快取來源、不根據日曆推算 stale。來源映射、快取驗證、日曆與新鮮度標記於步驟 4／5 串接。函式另檢查價格、標的／市場／幣別、未來時間與價格種類；5 秒未來時間容許值為可傳入的測試預設，未代替實際主機校時驗證。

`ValuationReport.to_dict()` 提供 JSON 可序列化資料：精確數值為十進位字串，顯示值另以 `_display` 欄位提供，缺少完整總額時兩者皆為 null。CSV／JSON 檔案匯出及 run-id／cycle-id 命名於單次 quote 整合時完成。

## 6. 需求驗證追蹤

| 需求 | 驗證案例 |
|---|---|
| R01、R02 | V01、V09 |
| R03 | V02、V03 |
| R04、R06、R07 | V04 |
| R05 | V05、V06、V07、V08、V10 |

案例內容與建議門檻見 [POC 驗收計畫](poc-validation.md)。

### 步驟 5 實作補充（2026-09-08）

quote 已串起 CSV、映射、來源、品質、DB 與匯出。新增品質值 freshness_unknown，表示有來源時間但延遲未确认；time_unknown 仍表示時間缺少或僅日期。兩者均降級。比較來源 finnhub／twse／tpex 不替換 Yahoo；已啟用來源最終失敗亦退出 3。不同 alias 對應同一 instrument 時退出 2，要求合併持股。

輸出為 output/<run-id>/summary.json 與 <cycle-id>/holdings.csv，含來源嘗試、比較與當地時間。時間未對齊的比較不算價格吻合。[步驟 5 證據](step-5-evidence.md) 記錄完整規則與未測項目。

### 步驟 8 實作補充（2026-09-08）

`report` 以 REPEATABLE READ READ ONLY 快照讀取，不取收集鎖，可在 monitor 執行中產生報告。CLI 補 `--config` 與互斥的 `--run-id`／`--campaign-id`；run 範圍的排程覆蓋率只採該 run 起訖內的預定機會，已被該 run 認領的機會不受時鐘影響一律列入分母，campaign 範圍採整份預定輪次並附各 run 摘要。

報告不判定未由紀錄支持的項目：V04 依重算一致性判定，V09 依中斷與恢復紀錄判定為部分符合，V10 需可對齊比對樣本與每市場三個完整交易日，其餘 V01–V03、V05–V08 明列為不由報告判定。台股最小報價單位需要標的類型；quotes 自 migration 0003 起保存官方 `asset_type`，報告據此套用股票六級與 ETF 兩級的官方級距，0003 之前的報價仍列為無法判定。[步驟 8 證據](step-8-evidence.md) 與 [步驟 9 證據](step-9-evidence.md) 記錄實測與界線。
