# 資料來源評估

版本：v0.1；查核日期：2026-09-07；狀態：文件評估，API 尚未實測。

## 1. 選型原則

需求為個人用途、免費優先、台美股盤中可更新，接受約 15–20 分鐘來源延遲。免費不等於可靠；成功取得 HTTP 回應也不等於取得有效盤中價。

| 候選 | 用途 | 已查核資訊 | 尚需驗證 |
|---|---|---|---|
| Yahoo Finance／yfinance | 台股主要候選；美股候選與比較來源 | Yahoo 延遲表列出台灣 .TW／.TWO 為 20 分鐘；yfinance 為非 Yahoo 官方維護工具 [S1][S2] | 個股／ETF 涵蓋、容器連線、限流、來源時間、盤中欄位、Python 相容性 |
| Finnhub Quote API | 美股候選 | 文件提供美股 Quote，需 API Key，包含價格與時間欄位 [S3] | 免費帳號實際權限、額度、ETF、交易場所涵蓋與正常時段價格 |
| TWSE OpenAPI | 台股上市收盤交叉檢查 | 官方開放 API 提供市場資料 [S4] | 選定端點、當日資料發布時間、日期格式、ETF 涵蓋 |
| TPEx OpenAPI | 台股上櫃收盤交叉檢查 | 官方上櫃行情資料集為每日盤後資料 [S5] | 端點欄位與數字格式、缺值及交易日發布時間 |
| FinMind 即時快照 | 免費方案不足時的替代選項 | 文件標示股票快照約 10 秒更新，限 Sponsor 會員 [S6] | 費用、涵蓋及權限；本次不自行訂閱 |
| Alpha Vantage | 其他美股候選，初期不優先 | Quote 預設每日更新；即時／15 分鐘延遲需 premium [S7] | 如調整預算再評估；不以每日價格宣稱符合盤中需求 |

Yahoo 網頁與 yfinance 使用同一資料體系，兩者一致不構成獨立來源交叉驗證。多個供應商也可能共用上游，報告需說明已知資料來源關係。

## 2. 第一輪實測配置

1. 台股：以 yfinance 取得上市、上櫃與 ETF，逐項驗證價格種類、貨幣與時間。
2. 美股：yfinance 與 Finnhub 分別記錄，使用同一組代表股票與 ETF；Finnhub 金鑰缺少時明確記為未測，不製造測試成功結果。
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

## 5. 待實測結果表

| 來源／市場 | 連線 | 標的涵蓋 | 時效 | 請求額度 | 穩定性 | 結論 |
|---|---|---|---|---|---|---|
| yfinance／台股 | 未測 | 未測 | 文件列 20 分鐘，未測 | 未確認 | 未測 | 待定 |
| yfinance／美股 | 未測 | 未測 | 未測 | 未確認 | 未測 | 待定 |
| Finnhub／美股 | 未測 | 未測 | 未測 | 帳號實際權限待查 | 未測 | 待定 |
| TWSE／收盤比對 | 未測 | 未測 | 每日資料端點待定 | 未確認 | 未測 | 僅比較用途 |
| TPEx／收盤比對 | 未測 | 未測 | 每日盤後 | 未確認 | 未測 | 僅比較用途 |

## 6. 官方與維護者參考資料

- [S1：Yahoo Finance exchanges and data providers](https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html)：台灣市場後綴與延遲表。先前查核可讀；最近一次開啟失敗，實作時需再次核對。
- [S2：yfinance 維護者說明](https://github.com/ranaroussi/yfinance)：非官方工具、研究用途與資料使用條款提醒。
- [S3：Finnhub Quote](https://finnhub.io/docs/api/quote)：驗證及 Quote 回應文件；[Pricing](https://finnhub.io/pricing) 本次未取得可解析方案表，未將搜尋摘要當成已確認額度。
- [S4：TWSE OpenAPI](https://openapi.twse.com.tw/)：官方 API 目錄。
- [S5：TPEx OpenAPI](https://www.tpex.org.tw/openapi/)；[政府資料開放平臺：上櫃股票行情](https://data.gov.tw/dataset/11370)：資料頻率與涵蓋說明。
- [S6：FinMind 即時資料](https://finmind.github.io/tutor/TaiwanMarket/RealTime/)：Sponsor 股票快照。
- [S7：Alpha Vantage API](https://www.alphavantage.co/documentation/)；[方案與額度](https://www.alphavantage.co/premium/)：Quote 更新與 premium 限制。
