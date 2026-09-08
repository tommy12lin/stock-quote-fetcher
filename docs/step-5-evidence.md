# 步驟 5 執行紀錄

日期：2026-09-08。狀態：完成。Provider、品質檢查、單次 quote、快取與匯出已實作；Yahoo、Finnhub、TWSE 與 TPEx 真實容器流程通過。

## 交付與測試

新增 providers.py、provider_worker.py、quality.py、quoting.py，擴充 config、cli、storage、models 與 valuation。測試位於 tests/test_quoting.py、tests/test_storage.py；匿名容器驗證入口為 tests/step5_smoke.py。既有 migration 與鎖定依賴不變。

完整 Linux amd64／Python 3.14.7／隔離 PostgreSQL 測試 **161 passed**，結果見 [step-5-validation.txt](step-5-validation.txt)。sdist／wheel 建置成功。案例包含 HTTP 401／429、Retry-After、TLS、真實子程序期限、休市／DST／提早收盤、來源隔離、快取原 quote-id、DB 提交失敗不匯出及匯出／DB 數值一致。隔離 DB 使用 internal network、tmpfs、無 host port；未對既有 PostgreSQL 注入故障。

## 實作規則

- 完整 CSV 驗證先於連線。quote 取得專案收集鎖後使用未過期標的清單，恢復舊未完成紀錄並建立新 run。不同 alias 對應同一 instrument 時退出 2，要求合併持股。
- 每市場一個 cycle，各有 50 秒網路抓取預算；先 Yahoo，再比較來源。10 秒操作期限包含 Python 子程序啟動、SDK 內部等待；逾時終止並回收程序。DB 短交易另有 timeout，不計入網路預算。
- 暫時性錯誤最多追加兩次，指數退避加隨機偏移；401／403／解析錯誤不重試。尊重 Retry-After；429 缺少該欄位時冷卻 60 秒。來源獨立冷卻，跨標的沿用至本次 quote 結束，操作起點至少相隔一秒；跨 monitor 輪次／重啟調度屬步驟 6。
- 每次 started attempt 提交後才呼叫 Adapter；預算耗盡、冷卻、映射失敗仍留紀錄，executed=false。executed 指 Adapter 是否呼叫，非底層 HTTP 次數。SDK cookie／crumb、內建重試／快取無法逐個觀測，不宣稱操作數等於 HTTP 請求數。
- Yahoo 每次建立獨立 SDK 程序，使用 regularMarketPrice／regularMarketTime，核對 symbol、quoteType、currency、exchangeTimezoneName。Decimal 由 SDK 值的十進位字串建立；SDK 已轉為 float 的上游原始 JSON 字面精度無法還原，後續計算／DB 往返不再使用 float。
- Finnhub 透過 X-Finnhub-Token header 認證，URL 不含金鑰。報價 API 無幣別／時段欄位，幣別依官方美股目錄，時間另與日曆核對；不同股別採官方 canonical ticker，`BRK.B` 已真實驗證。無宣告延遲時標 freshness_unknown，不宣稱已確認新鮮度。
- time_unknown 表示缺少來源時間或僅有日期；freshness_unknown 表示時間存在但延遲未確認。低成交量舊價標 stale，不直接推論供應商故障。未知時段可降級呈現；明確盤前／盤後排除估值。
- 快取僅從 PostgreSQL 取同 instrument／來源／代碼／幣別候選，重新驗證價格、時間與品質。只在本次抓價失敗後使用，保留原 quote-id／quote_time／received_at，估值端加 cached／stale。比較來源不替換 Yahoo。
- 官方收盤保存 trading_date、day 精度、quote_time=null。僅同交易日且 Yahoo 時間戳在日曆收盤五秒內才作收盤候選比較；Finnhub 須同時間戳、交易日、價格種類。未對齊不列入吻合率。
- Adapter 保存 parser_version、白名單原始欄位、來源別 TLS 狀態及雜湊；不保存原始 exception、header 或 token URL。保留 CERT_REQUIRED／check_hostname，只有明列的 Finnhub／TWSE／TPEx 可載入公司 CA 並移除 VERIFY_X509_STRICT；Yahoo 不支援關閉驗證。
- 估值與 run 完成提交後，才寫 output/<run-id>/summary.json 及 <cycle-id>/holdings.csv，含精確值／顯示值、UTC／當地時間、交易日、品質、來源嘗試與比较。
- 退出 0：估值完整且已啟用來源最終成功；3：缺價／降級或已啟用來源最終失敗；2：輸入／設定錯誤；1：儲存／輸出失敗。比對時間不一致本身不算抓取失敗。

## 真實匿名五檔結果

run-id：219eb3ab-a07f-4985-bed7-a655d2a7bc62；約 2026-09-08 14:00 台北。保存於既有專案 DB；完整個人用途輸出在已忽略的 output/step5/。

| 範圍 | 結果 |
|---|---|
| Yahoo | 五檔全部取得，操作約 3.3–3.7 秒 |
| TWD | 精確總額 278480.00，degraded；2330 時間 13:30:08 超過日曆收盤＋五秒，保留 session_unknown，未放寬規則 |
| USD | 精確總額 1507.935、顯示 1507.94，complete；AAPL／VOO 為 9 月 4 日最後成交，當時美股未開盤且 9 月 7 日休市，標 market_closed |
| 官方比較 | TWSE 兩筆、TPEx 一筆成功，但仍為 9 月 7 日；Yahoo 為 9 月 8 日，三筆均未列為有效比對 |
| Finnhub | AAPL、VOO、`BRK.B` 均成功；AAPL 與 Yahoo 同價但時間差一秒，未列為對齊；VOO 同時間同價、差異 0 |

Windows Time Service：Leap Indicator=0、Stratum=4、最近同步 2026-09-08 13:52:09 台北，root dispersion 約 0.86 秒。這是校時狀態證據，非獨立絕對誤差量測；未來時間容許值維持五秒。

## 操作與剩餘工作

本機 config.toml 已啟用 comparison=["finnhub", "twse", "tpex"] 及對應 relaxed_providers，沿用公司 CA 路徑。config.toml、.env 均被 Git 忽略。FINNHUB_API_KEY 已由新容器透過 `--env-file` 注入並驗證；CLI 不自動讀 .env。

```text
uv run --frozen stock-poc quote --input examples/holdings.csv --config config.toml --output output
```

容器使用 --env-file .env、infrastructure_default，將公司 CA 唯讀掛到 /run/secrets/company-root-ca.crt，並掛輸入／輸出目錄。臨時容器依步驟 3／4 安裝方式；正式 Dockerfile／Compose 屬步驟 7。

Finnhub 回應 rate-limit header 為 limit 60、remaining 59、reset 2026-09-08T06:18:57Z（請求後約 22 秒）；回應未明示窗口單位，因此不把「每分鐘 60 次」寫成已確認契約。步驟 5 已完成。下一步是步驟 6 monitor；台美盤中／三個完整交易日觀測、長時間額度行為與更多有效價格比較屬步驟 9，尚無可靠性達標結論。

## 查核來源

- [Finnhub Quote](https://finnhub.io/docs/api/quote)：header、欄位與 429。
- [yfinance get_info](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.get_info.html)：鎖定版本另確認實際簽章沒有 timeout 參數。
- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars)：日曆介面。
- [NYSE 日曆](https://www.nyse.com/markets/hours-calendars)、[Nasdaq 日曆](https://nasdaqtrader.com/Trader.aspx?id=Calendar)：2026-09-07 休市、11-27 提早收盤。
- [TWSE 開休市表](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html)：台股參考；完整年度及臨時停市仍須在正式觀測前核對。
