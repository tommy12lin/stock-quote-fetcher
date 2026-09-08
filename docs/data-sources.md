# 資料來源評估

版本：v0.4；查核日期：2026-09-08；狀態：步驟 5 單次 quote 與四個來源真實容器驗證完成；持續盤中觀測待執行。

## 1. 選型原則

需求為個人用途、免費優先、台美股盤中可更新，接受約 15–20 分鐘來源延遲。免費不等於可靠；成功取得 HTTP 回應也不等於取得有效盤中價。

| 候選 | 用途 | 已查核資訊 | 尚需驗證 |
|---|---|---|---|
| Yahoo Finance／yfinance | 台股主要候選；美股候選與比較來源 | 已實測可取得台股上市／上櫃／ETF 與美股個股／ETF 的最新成交價與秒級來源時間；台股回傳 `exchangeDataDelayedBy=20`，美股回傳 `0`；yfinance 1.7.0 於 Python 3.14 容器安裝與匯入正常。yfinance 為非 Yahoo 官方維護工具 [S1][S2] | 盤中連續觀測、限流與 429 行為、美股盤中時效、長時間穩定性 |
| Finnhub Quote API | 美股比較來源 | 以環境注入金鑰於目標容器取得 AAPL、VOO 與 `BRK.B`；個股、ETF、股別代碼均成功。rate-limit header 顯示本次窗口 limit 60、remaining 59 [S3] | 正常交易時段時效、連續觀測下的額度與 429 行為 |
| TWSE OpenAPI | 台股上市收盤交叉檢查 | 已實測 `/v1/exchangeReport/STOCK_DAY_ALL`：HTTP 200、1380 列、涵蓋 2330 與 0050、數值為字串、日期為民國年。2026-09-07 16:45（台北）時仍為前一交易日 1150904 的資料 [S4] | 當日資料實際發布時刻、ETF 完整涵蓋、非交易日行為 |
| TPEx OpenAPI | 台股上櫃收盤交叉檢查 | 已實測 `/openapi/v1/tpex_mainboard_quotes`：HTTP 200、1013 列、涵蓋 6488，且 2026-09-07 16:45 已提供當日 1150907 資料 [S5] | 上櫃 ETF 是否涵蓋、缺值表示法、非交易日行為 |
| TWSE 公司／基金 OpenAPI 與 ISIN 清單 | 台股標的主檔 | `t187ap03_L`、`t187ap47_L` 與 ISIN `strMode=4` 容器正式更新成功；官方分類／CFICode 區分股票、ETF 及不支援商品 [S4][S8] | 欄位與涵蓋變更需由 refresh 失敗及後續觀測偵測 |
| Nasdaq Trader Symbol Directory | 美股標的主檔 | `nasdaqlisted.txt` 與 `otherlisted.txt` 為官方欄位目錄，盤中定期更新；容器實取並解析 4,295／6,688 筆受支援股票與 ETF [S9] | 名稱型 security-type 白名單可能保守拒絕少數股票，於代表名單驗收追蹤 |
| FinMind 即時快照 | 免費方案不足時的替代選項 | 文件標示股票快照約 10 秒更新，限 Sponsor 會員 [S6] | 費用、涵蓋及權限；本次不自行訂閱 |
| Alpha Vantage | 其他美股候選，初期不優先 | Quote 預設每日更新；即時／15 分鐘延遲需 premium [S7] | 如調整預算再評估；不以每日價格宣稱符合盤中需求 |

Yahoo 網頁與 yfinance 使用同一資料體系，兩者一致不構成獨立來源交叉驗證。多個供應商也可能共用上游，報告需說明已知資料來源關係。

## 2. 第一輪實測配置

1. 台股：以 yfinance 取得上市、上櫃與 ETF，逐項驗證價格種類、貨幣與時間。
2. 美股：yfinance 與 Finnhub 分別記錄，使用同一組代表股票與 ETF；兩來源時間與價格口徑未對齊時不列入吻合率。
3. 台股收盤：以 TWSE／TPEx 對應交易日一般交易收盤資料進行交叉檢查。
4. 先固定估值來源；另一來源只作比較，避免混合價格使故障無法歸因。
5. 結果未符合要求時，結論可為免費方案不足、限定部分標的適用或需要付費來源，不自動降低時效需求。

## 3. 時效的解讀

- source delay：供應商宣告的延遲，不是本次觀測得到的保證值。
- quote age：received_at 減 quote_time，可能同時包含來源延遲與無成交期間。
- fetch latency：取得資料操作的耗時，與行情本身的新舊不同。
- display age：輸出時刻減 quote_time，還包含輪詢等待時間。

20 分鐘來源延遲加每分鐘輪詢可能使輸出時的行情年齡超過 20 分鐘。規格應展示以上分量，驗收計畫需分別量測，不能用抓取頻率取代時效證據。

來源未提供可信時間時保留 time_unknown。若只有分鐘 K 線，報告紀錄區間起迄，不將其視為瞬間成交。缺少時間與市場狀態時，不能宣稱已驗證符合盤中時效。

## 4. 來源選定前必查

- 目標股票與 ETF 的代碼、上市市場與幣別。
- 使用的是最新成交、官方收盤、買賣報價或 K 線收盤。
- 一般時段／盤前／盤後區分與時區、夏令時間、假日行為。
- 免費額度的單位：請求、標的、分鐘或每日；批次是否分別計費。
- 429、封鎖、逾時、空回應與欄位異動時的可觀測性。
- Docker 容器環境的 DNS／TLS／網路、SDK 的隱藏快取與重試。
- 個人使用、資料保存與移交時的分享範圍。Yahoo 官方提醒不應再散布其資料 [S1]；正式專案如變更用途需重新核對。

第一輪與步驟 5 實測已回答代碼與幣別、價格口徑、時區欄位、未知代碼的可觀測性、Finnhub 單次窗口額度 header，以及容器的 DNS 與 TLS 行為。仍未回答的是長時間額度與 429 行為、SDK 隱藏快取與重試，以及盤前／盤後與假日的完整行為；這些需要持續觀測確認。

## 5. 第一輪實測結果（2026-09-07）

觀測環境：Windows 11 主機的 Python 3.14.6 探針，以及 `python:3.14-slim` 容器（Debian 13 trixie、Python 3.14.7、digest `sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6`、linux/amd64）。探針為一次性腳本，非 POC 程式碼；下列為單次取樣，不是連續觀測統計。

### 5.1 來源狀態

| 來源／市場 | 連線 | 標的涵蓋 | 時效 | 請求額度 | 穩定性 | 結論 |
|---|---|---|---|---|---|---|
| yfinance／台股 | 通（主機與容器） | 上市、上櫃、ETF 各取樣成功 | 來源宣告 20 分鐘；單次取樣時間為當日 13:30 收盤成交 | 未確認 | 未測（僅單次取樣） | 具備必要欄位，待盤中連續觀測 |
| yfinance／美股 | 通（主機與容器） | 個股、ETF、不同股別各取樣成功 | 來源宣告 `0`；取樣時美股休市，未取得盤中資料 | 未確認 | 未測 | 欄位齊備，盤中時效待測 |
| Finnhub／美股 | 通（需金鑰與公司 CA） | AAPL、VOO、`BRK.B` 成功 | 休市樣本與 Yahoo 同交易日；來源未宣告延遲，標 freshness_unknown | header：limit 60、remaining 59；窗口單位未由回應明示 | 未測（僅單次取樣） | 可作美股比較來源，盤中與長時間行為待測 |
| TWSE／收盤比對 | 通（需公司 CA，見第 6 節） | 2330、0050 命中 | 16:45 仍為前一交易日 | 未確認 | 未測 | 可作收盤比對，但發布較晚 |
| TPEx／收盤比對 | 通（需公司 CA，見第 6 節） | 6488 命中 | 16:45 已有當日資料 | 未確認 | 未測 | 可作當日收盤比對 |

### 5.2 台股價格交叉比對

同交易日、同口徑（一般交易時段收盤）比對，取樣時間 2026-09-07T16:45+08:00：

| ticker | 官方來源 | 官方交易日 | 官方收盤 | yfinance 比對欄位 | yfinance 值 | 差異 |
|---|---|---|---|---|---|---|
| 2330.TW | TWSE | 2026-09-04 | 2410.00 | regularMarketPreviousClose | 2410.0 | 0 |
| 0050.TW | TWSE | 2026-09-04 | 107.90 | regularMarketPreviousClose | 107.9 | 0 |
| 6488.TWO | TPEx | 2026-09-07 | 971.00 | regularMarketPrice | 971.0 | 0 |

6488.TWO 的當日最高 1015、最低 966 亦與 TPEx 一致。TWSE 端點在取樣時只提供前一交易日，故上市股比對的是 yfinance 的前一交易日收盤欄位，非當日價。三筆樣本全數相同，但樣本數過小，不足以支撐驗收計畫的「價格吻合率」；仍需依 [POC 驗收計畫](poc-validation.md) 第 5 節累積各類標的的有效比對樣本。

### 5.3 yfinance 欄位觀測

| 觀測項 | 結果 | 對規格的影響 |
|---|---|---|
| `regularMarketPrice` 與 `regularMarketTime` | 兩者皆有，時間為 Unix 秒 | `price_kind` 可定為 `last_trade`，`time_precision` 為秒；本輪不需要分鐘 K 線的 `bar_close` 退路 |
| `exchangeDataDelayedBy` | 台股 `20`；美股 `0`（NasdaqGS、NYSE、NYSEArca） | 可作為 `declared_delay_seconds` 來源；美股宣告值優於原先假設，端到端時效門檻應依實測重新討論 |
| `marketState` | 台股 `POSTPOST`、美股 `CLOSED` | 可支援 `session` 判斷，但仍須以交易日曆為準，不單靠此欄位 |
| `exchangeTimezoneName` | `Asia/Taipei`、`America/New_York` | 可交叉檢核市場時區 |
| `postMarketPrice` | 美股休市時仍提供（AAPL 320.01、VOO 707.84） | 必須明確排除，不可誤用於估值 |
| `currency`／`quoteType` | `TWD`／`USD`、`EQUITY`／`ETF` | 可支援幣別與商品類型驗證 |
| 未知代碼 `NOSUCH.TW` | HTTP 404，錯誤訊息含代碼，info 為空 | `unsupported_symbol` 可與其他錯誤區分 |
| 不同股別 `BRK-B` | 以連字號可取得；點號形式不適用 | instruments 映射需記錄 Yahoo 的股別分隔符規則 |

美股取樣時最新成交為 2026-09-04T16:00 ET，因 2026-09-07 為美國勞動節休市。美股盤中觀測最早自 2026-09-08 起算。

### 5.4 官方端點欄位觀測

| 觀測項 | TWSE `STOCK_DAY_ALL` | TPEx `tpex_mainboard_quotes` |
|---|---|---|
| 代碼欄位 | `Code` | `SecuritiesCompanyCode` |
| 收盤欄位 | `ClosingPrice` | `Close` |
| 日期欄位 | `Date`，民國年格式如 `1150904` | 同格式，如 `1150907` |
| 數值型別 | 全為字串 | 全為字串 |
| 已知欄名瑕疵 | 無 | `LatesAskPrice` 缺一個 t，adapter 須照原樣讀取 |

兩個端點的代碼均保留前導零，且存在含英文字母的代碼（例如 `00400A`、`00411A`）。CSV 的 ticker 規則與代碼映射必須容納這類代碼，不可假設全為數字。數值以字串回傳，可直接轉 Decimal，不經過浮點數。民國年日期需轉換為西元交易日後才可與其他來源對齊。

## 6. 環境限制：公司網路 TLS 攔截

2026-09-07 於公司網路實測發現，部分目標主機的 TLS 連線被公司代理攔截並重新簽發憑證，簽發者為 `C=TW, O=Advantech, CN=prisma-advantech.com`，其上層為自簽根 `DC=CORP, DC=ADVANTECH, CN=ACLCA`（SHA-1 指紋 `92715B2174E4131E2FF6B57295B7309B9AE87519`）。該根憑證已存在於主機的 Windows 信任存放區，屬公司部署的憑證，非不明來源。

| 主機 | 憑證簽發者 | 是否受攔截 |
|---|---|---|
| `query1.finance.yahoo.com` | DigiCert Global G2 TLS RSA SHA256 2020 CA1 | 否，放行 |
| `finnhub.io` | prisma-advantech.com | 是 |
| `openapi.twse.com.tw` | prisma-advantech.com | 是 |
| `www.tpex.org.tw` | prisma-advantech.com | 是 |

因此 yfinance 不受影響，但 Finnhub、TWSE、TPEx 在預設憑證設定下皆無法連線。容器內實測結果：

| 設定 | TWSE | TPEx | Finnhub |
|---|---|---|---|
| 僅使用預設 CA | 憑證驗證失敗 | 憑證驗證失敗 | 憑證驗證失敗 |
| 注入公司根憑證，保留 Python 預設 `VERIFY_X509_STRICT` | 失敗（Missing Authority Key Identifier） | 同左 | 同左 |
| 注入公司根憑證並關閉 `VERIFY_X509_STRICT` | HTTP 200 | HTTP 200 | HTTP 401（僅缺金鑰） |

僅注入根憑證不足。Python 3.13 起 `ssl.create_default_context()` 預設啟用 `VERIFY_X509_STRICT`，而該公司根憑證缺少 Authority Key Identifier 擴充，因此仍會被拒絕。處理方式與設計影響見 [架構與部署](architecture.md) 的 TLS 與 CA 章節。

此限制屬於執行環境而非資料來源本身。移交正式專案時須註明：在沒有 TLS 攔截的網路中不需要這些設定，且不應把公司憑證或寬鬆的驗證設定當成產品預設。較乾淨的替代方案是請 IT 將這些主機加入 TLS 檢查的放行名單（Yahoo 已在其中），如此程式端可完全使用預設憑證驗證。

## 6.1 步驟 4 標的清單實測

2026-09-08 實際讀取五個官方來源。Nasdaq 兩個文字目錄可由目標容器以預設 CA 取得；TWSE OpenAPI 與 ISIN 主機在容器中以預設 CA 失敗，符合上述既知限制。從 Windows Root store 匯出不含私鑰的 ACLCA 公開根憑證，唯讀掛載並核對指紋後，容器正式發布 13,343 筆 generation：上市公司 1,094、上市 TWD ETF 257、上櫃股票／TWD ETF 1,009、Nasdaq listed 4,295、其他美國交易所 6,688。匿名範例 2330.TW、0050.TW、6488.TWO、AAPL、VOO 全數 resolve 成功。

清單實作固定五個 HTTPS URL，不接受設定任意來源 URL；限制回應 Content-Type 與 12 MiB，任一來源下載、格式、分類／CFICode 或重複代碼異常時，不發布新 generation。完整 generation 預設 24 小時有效，過期後 `resolve` 明確失敗，不以猜後綴或舊清單靜默繼續。來源時間、payload SHA-256、bytes、有效列數及 TLS 設定存入 PostgreSQL。

TWSE 基金清單使用官方基金類型，只納入 ETF，並依官方證券編碼規則排除外幣加掛 ETF。TPEx ISIN 清單只納入「股票」及「ETF」分類，以 CFICode 前綴再核對並排除外幣加掛 ETF。美股 ETF 使用 Nasdaq 官方 ETF flag；非 ETF 因目錄未提供獨立 security-type 欄，只保守接受名稱明示 common／ordinary shares、ADS／ADR 等股票，排除權證、權利、單位、特別股及債券類商品。

## 7. 官方與維護者參考資料

- [S1：Yahoo Finance exchanges and data providers](https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html)：台灣市場後綴與延遲表。先前查核可讀；最近一次開啟失敗，實作時需再次核對。
- [S2：yfinance 維護者說明](https://github.com/ranaroussi/yfinance)：非官方工具、研究用途與資料使用條款提醒。
- [S3：Finnhub Quote](https://finnhub.io/docs/api/quote)：驗證及 Quote 回應文件；[Pricing](https://finnhub.io/pricing) 本次未取得可解析方案表，未將搜尋摘要當成已確認額度。
- [S4：TWSE OpenAPI](https://openapi.twse.com.tw/)：官方 API 目錄。
- [S5：TPEx OpenAPI](https://www.tpex.org.tw/openapi/)；[政府資料開放平臺：上櫃股票行情](https://data.gov.tw/dataset/11370)：資料頻率與涵蓋說明。
- [S6：FinMind 即時資料](https://finmind.github.io/tutor/TaiwanMarket/RealTime/)：Sponsor 股票快照。
- [S7：Alpha Vantage API](https://www.alphavantage.co/documentation/)；[方案與額度](https://www.alphavantage.co/premium/)：Quote 更新與 premium 限制。
- [S8：TWSE ISIN 有價證券國際證券辨識號碼一覽表](https://isin.twse.com.tw/isin/C_public.jsp?strMode=4)：上櫃分類、ISIN 與 CFICode；[TWSE ETF 代碼說明](https://www.twse.com.tw/zh/products/securities/etf/products/foreign.html)、[TPEx ETF 商品分類](https://www.tpex.org.tw/zh-tw/product/etf/overview/categories.html)：外幣加掛 ETF 編碼。
- [S9：Nasdaq Trader Symbol Directory 定義](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)：Nasdaq／其他交易所目錄欄位、ETF／test issue／exchange 定義與更新頻率。

## 步驟 5 實測（2026-09-08）

14:00 左右匿名五檔 Yahoo 全部取得；TWSE／TPEx 仍為前一交易日，尚不能與當日 Yahoo 判定吻合。2330 的來源時間 13:30:08 超出日曆收盤＋五秒，保留 session_unknown。

Finnhub 真實驗證已完成：AAPL、VOO 與 `BRK.B` 均成功；VOO 驗證 ETF、`BRK.B` 驗證股別代碼。AAPL 與 Yahoo 價格相同但時間戳相差一秒，因此未列為對齊；VOO 同時間同價格、差異 0。rate-limit header 顯示當次窗口 limit 60、remaining 59、reset 約 22 秒後；窗口單位是依時間差推測，未當成供應商契約。詳見 [步驟 5 證據](step-5-evidence.md)。
