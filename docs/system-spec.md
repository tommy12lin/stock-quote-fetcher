# 系統規格

版本：v0.1；日期：2026-09-07；狀態：需求基線與設計草案，待 POC 實測。

## 1. 目的與範圍

主要目的為驗證免費優先的台美股報價取得方案，包含價格、幣別、時間、涵蓋率與穩定性。持股市值是用來驗證資料可用性的最小應用。

### 已確認需求

| ID | 需求 |
|---|---|
| R01 | 以 Python 開發；語言與套件追求最新且受維護的版本，LTS 解讀見架構文件 |
| R02 | 部署至 Linux Docker Container，POC 實作交付 Dockerfile 與 Docker Compose |
| R03 | CSV 輸入 ticker、每股買入價、持有股數，採 CLI 操作 |
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
2330.TW,900,100
0050.TW,50,200
6488.TWO,1000,10
AAPL,180,2.5
VOO,400,1
```

| 欄位 | 規則 |
|---|---|
| ticker | 字串；去除首尾空白並標準化英文字母大小寫；保留前導零 |
| buy_price | 每股買入價，依市場使用 TWD 或 USD；有限且大於零的十進位數 |
| quantity | 持有股數，有限且大於零；台股必須為整數，美股可為小數 |

台股需包含 `.TW` 或 `.TWO` 以辨識市場；美股使用美國市場 ticker。特殊美股代碼（例如不同股別）由市場清單與來源映射處理，不以任意字串替換猜測代碼。

- 必填欄位遺漏、未知額外欄位、空值、非數字、NaN、Infinity、負值或零值皆拒絕。
- 本版拒絕同一標準化 ticker 重複列，回報行號；避免暗自推算平均成本。
- 空檔與只有標頭的檔案拒絕。
- CSV 結構或欄位驗證失敗時，整份輸入不生效、不開始抓價。
- 格式合法但查無標的、來源不支援、幣別不符，列為該標的錯誤；其他標的仍可完成抓價。
- 買入價與股數不傳給外部報價服務，只傳查詢所需的標的代碼。

## 3. 預定 CLI

以下是待實作的契約，不是目前可執行的程式。

```text
stock-poc validate --input /input/holdings.csv
stock-poc quote --input /input/holdings.csv --config /input/config.toml --output /output
stock-poc monitor --input /input/holdings.csv --config /input/config.toml --output /output
stock-poc report --run-id <run-id> --output /output
```

- `validate`：離線驗證 CSV，不連外。
- `quote`：執行一次抓取、保存紀錄，輸出持股表與分幣別摘要。
- `monitor`：持續抓取並保存；收到停止訊號時完成或中止本輪、記錄狀態並安全退出。
- `report`：從持久化紀錄產生指定觀測執行的可靠性報告，不重新抓價。
- monitor 啟動時讀取並記錄 CSV 與設定的雜湊；CSV 修改後需重新啟動，新執行使用新的 run-id。
- 預定退出碼：0＝成功；2＝輸入／設定錯誤；3＝quote 有缺價、降級或品質無法確認；1＝不可恢復的執行錯誤。monitor 對單筆抓價失敗持續運行並記錄，不因此整個退出。

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
- last_trade 為目標；若來源只能提供分鐘 K 線，記錄 bar_close 與區間時間，不假裝是逐筆成交價；是否可接受列入實測結論。
- 不以還原股價乘目前持股，應使用未還原的一般交易時段價格。
- 保存 UTC 時間，顯示時附台灣／紐約當地時區；美股夏令時間、假日、提早收盤由交易日曆處理。
- 來源延遲 20 分鐘與 60 秒輪詢分開記錄，可能產生約 21 分鐘加網路處理時間的端到端資料年齡；不直接宣稱總延遲小於 20 分鐘。
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

`completeness`：

- complete：所有該幣別持股可估值且符合當前市場狀態的品質規則。
- degraded：全部可估值，但使用舊快取、資料時效未知或其他需揭露的降級資料。
- partial：至少一筆無可用價；total 為 null，known_subtotal 僅為已知部分。
- unavailable：所有持股均無價；total 為 null，known_subtotal 為 0，但不能顯示為資產總值 0。

若先前有經驗證的報價，本次失敗可顯示該價格與原始時間，標記 cached／stale；不可把快取更新成「剛取得的新行情」。每筆來源的失敗紀錄仍保留。

## 6. 需求驗證追蹤

| 需求 | 驗證案例 |
|---|---|
| R01、R02 | V01、V09 |
| R03 | V02、V03 |
| R04、R06、R07 | V04 |
| R05 | V05、V06、V07、V08、V10 |

案例內容與建議門檻見 [POC 驗收計畫](poc-validation.md)。
