# 本機持股儀表板第一版

2026-09-10：儀表板新增經發行公司核實的 OTC 補充清單，目前支援 IFNNY（Infineon Technologies AG 的 USD ADS，OTCQX，Yahoo 代碼 IFNNY）。來源：https://www.infineon.com/about/investor/infineon-share 。補充資料位於 `otc_catalog.py`，只在儀表板識別時合併，不修改既有觀測清單；既有交易所資料優先。這不是所有 OTC 股票的完整清單，未核實代碼仍拒絕保存，報價仍需通過原有代碼、商品類型、幣別與時間檢查。

2026-09-09。入口：<http://localhost:8765/>。

## 使用方式

1. 點「下載範本」，保留 `ticker,quantity,buy_price` 三個欄位。股票代碼必須為文字，台股股數單位是股。
2. 點「上傳 Excel」，選工作表、檢查預覽與錯誤，按「確認取代草稿」。也可直接新增持股。
3. 若有美股，輸入 USD/TWD 匯率。點「儲存持股」；保存後缺價會自動排入更新，也可按「更新報價」。
4. 查看持股總市值、成本、未實現損益／報酬率、原幣小計、環形配置與逐股報價資訊。市場篩選會同步改變合計與配置分母。
   市值配置顯示全部市場前 15 檔、單一市場前 10 檔，其餘合併為灰色「其他」；未超過上限時不顯示空群組。各持股配色不重複，滑鼠指向色塊或以 Tab 聚焦可查看名稱、代碼、台幣市值與占比。
5. 「套用匯率」只保存匯率，保留未保存的持股草稿。官方清單失效時按「更新股票清單」再重新保存。

缺匯率或缺價時不產生完整總額；缺價保留已知市值並列出排除股票。所有歷史價格保留來源及時間，以快取／降級狀態顯示，不宣稱即時。成本與市值採相同手動匯率，不含手續費、稅、股息或歷史匯兌損益。

## 啟停

```powershell
docker compose -f compose.web.yaml up -d web
docker compose -f compose.web.yaml stop web
```

重新建置程式：`docker compose -f compose.web.yaml build web`，再執行上述啟動命令。這份 Compose 使用 `stock-portfolio` 專案、獨立映像及 `127.0.0.1:8765`，不重建既有 `stock-quote-fetcher-app-1`。

首次部署由資料庫管理者建立 `dashboard` schema，owner 為既有專用帳號 `stock_quote_app`；不建立／接管 PostgreSQL 容器或 volume。然後明確執行：

```powershell
docker compose -f compose.web.yaml run --rm web --config /input/config.toml --schema dashboard --initialize
```

啟動 HTTP 服務不自動 migration。`--initialize` 只套用到專用 schema：沿用既有報價證據表，再建立獨立 portfolio 與 refresh_jobs 表。正常保存只使用短交易與 revision 比對，不取得 collector lock。清空清單也是明確保存操作。

本機原生 Python 3.14.7 環境亦可使用 `uv run --frozen python -m stock_quote_fetcher.web --config config.toml`。目前已驗證 Docker Linux amd64；Windows 原生 Python 未另行驗證。

## 技術選擇與隔離

- 使用既有 Python 3.14.7、psycopg、Decimal 與 provider。前端是同源 HTML/CSS/JavaScript，環形圖用原生 SVG；不增加 Node、CDN、框架或 Excel 套件，原 uv.lock 保持有效。
- XLSX 以標準庫 ZIP/XML 解析 OOXML，限制 5 MiB 壓縮、50 MiB 展開、500 筆、64 工作表、2000 ZIP entries；子程序 15 秒逾時，Linux 512 MiB 位址空間及 12 秒 CPU 限制。拒絕巨集、加密、公式、日期／布林／錯誤型別及數字型 ticker；原始檔不落盤。僅支援標準 .xlsx，不支援券商自訂欄位。
- 持股與匯率保存於 `dashboard.portfolio` JSONB，包含 revision、官方標的識別與手動匯率中繼資料；`dashboard.refresh_jobs` 保存工作結果。使用獨立 schema 的既有報價表保存來源證據。
- 官方清單與可用歷史價格可從既有 app schema 唯讀取得；所有新行情寫入 dashboard。兩者的 schema-derived advisory lock 不同，已驗證 monitor 持鎖期間可更新網頁持股。
- 背景 worker 與 HTTP 同一程序、不同執行緒，按五檔批次收集完整清單，重用 QuoteRunner 的操作逾時、冷卻及品質規則。同時只接受一個更新工作，重複請求合併，全域冷卻 60 秒。程序重啟將中斷的工作標為失敗，可再更新。
- Web 服務另持 singleton advisory lease，限制同 schema 一個服務程序。報價來源仍是 Yahoo；不任選比較來源，也不停止或修改 monitor。
- API 金額以 Decimal 字串傳輸，先精確加總再顯示至兩位小數；瀏覽器浮點僅用於繪圖幾何與排序，沒有計算帳務合計。每次估值回應固定一個持股 revision 並附 valuation_id；前端只接受當前 revision 的結果。
- Host 白名單、Origin 檢查與記憶體 session token 保護寫入，同源 CSP、no-store、無存取內容日誌；HTTP 同時最多八個請求。不含登入、公開網路部署或跨來源 API。

## API

| 方法與路徑 | 契約 |
|---|---|
| GET `/api/session` | 取得本次服務的寫入 token，前端只放記憶體 |
| GET `/api/portfolio` | 已保存 rows、revision、fx、fx_source、fx_updated_at |
| PUT `/api/portfolio` | JSON `{revision, rows:[{ticker,quantity,buy_price}], fx}`；數值輸入字串；衝突 409 |
| POST `/api/imports/preview?filename=...xlsx&sheet=...` | body 為原始 XLSX bytes，回傳 sheets/sheet/rows/issues；不保存 |
| GET `/api/portfolio/valuation?market=ALL` | ALL/TW/US，合計、成本、損益、占比、品質與時間 |
| POST `/api/portfolio/refresh` | 排入／合併工作；202 + job_id |
| POST `/api/catalog/refresh` | 背景更新官方清單；202 + job_id |
| GET `/api/jobs/{id}` | queued/running/succeeded/partial/failed |
| GET `/api/templates/holdings.xlsx` | 匿名格式範本 |

寫入需同源 Origin 及 `X-Portfolio-Token`。錯誤回傳 code/message/issues；輸入錯誤帶 row/field/message，Excel 另帶 sheet。

## 驗證與實際限制

- 新增 `tests/test_dashboard.py`：固定 TWD 1,600／成本 1,280／損益 320 案例、缺價／缺匯率、台股整數與小數股、重複／非法輸入、XLSX 文字代碼、公式／型別、空白列、檔案限制與其他分組。
- 新增 `tests/test_dashboard_storage.py`：真實隔離 PostgreSQL 上的原子保存、409、重新初始化後保留資料、鎖忙碌、舊工作版本保護、中斷恢復與不持 collector lock 保存。
- 完整既有與新增測試使用一次性 `stock-poc-test-db`，233 項通過（包含原本需 PostgreSQL 的 38 項）；不以正式資料庫執行破壞式回歸。
- `scripts/dashboard_smoke.py` 僅使用 dashboard_test，驗證 HTTP 上傳→保存→更新→估值、錯誤不覆蓋、Host/Origin 拒絕、工作合併、版本保護與新服務物件讀回資料；兩次真實更新均成功，0050/AAPL 涵蓋 2/2。行情數值不作固定斷言。
- 觀測程序在上述測試期間持續運作，沒有停止、重建或改動其清單。這些證據不等於原 POC 盤中可靠性驗收完成。
- 瀏覽器實測空白畫面、真實估值與配置、修改股數後先套用匯率（草稿仍保留，總覽股數未變）、再儲存持股（版本及股數更新）。手機 CSS 有效寬度 375px 時頁面 scrollWidth 仍為 375，明細與編輯表格在自己的容器內橫向捲動。完整 Excel 上傳流程由 HTTP 整合測試驗證，未以瀏覽器檔案選擇器另跑自動化。
- 第一版是單一使用者／單一清單。行情需手動更新；來源故障時保留既有行情。大清單更新需較久，畫面顯示批次進度。新清單中的未支援股票須修正才能保存。
- 估值於讀取時用已保存持股與可用報價重算；valuation_id 是回應識別，尚未另外持久化每次衍生估值快照。報價原始證據與持股當前版本持久化；歷史持股編輯版本瀏覽不在本版。

正式介面不放測試持股；請使用自己的 Excel 建立清單。
