# 步驟 0 執行紀錄

日期：2026-09-08。範圍：PostgreSQL 設計同步及既有容器配置唯讀確認，未執行資料庫 DDL／DML、重啟或帳密變更。

## 交付與檢查

| 交付 | 結果 |
|---|---|
| architecture.md 第 1、2、4、5 節 | PostgreSQL、driver 待驗證狀態、NUMERIC／TIMESTAMPTZ、SQL migration、交易與 advisory lock、campaign／run／預定輪次、external network 契約 |
| poc-validation.md V01／V09 | 新增 PostgreSQL 版本、連線、權限、migration、交易失敗、精度往返與停機缺口案例；案例本身尚未執行 |
| README.md | 同步狀態、連接設定與操作邊界 |
| development-plan.md | 步驟 0 完成勾選及本證據連結 |

## 唯讀環境證據

執行 `docker ps --format` 僅列名稱／映像／port；`docker inspect postgres --format` 僅列 Networks 與 Mounts；`docker exec postgres postgres --version` 僅查執行檔版本，未讀取容器環境變數或密碼。

| 項目 | 實際結果 |
|---|---|
| 容器／映像 | postgres／postgres:17-alpine |
| 執行檔版本 | postgres (PostgreSQL) 17.10 |
| 網路／DNS alias | infrastructure_default／postgres |
| 主機 port | 5432，IPv4／IPv6 公開掛載 |
| 資料 volume | infrastructure_postgres_data → /var/lib/postgresql/data，rw |
| 初始化目錄 | /run/desktop/mnt/host/d/workspace/infrastructure/init-db → /docker-entrypoint-initdb.d，ro |

初次受限 shell 無法存取 Docker API，經唯讀提升權限後取得上述結果。未改動容器、網路或 volume。

## 驗證界線與後續

步驟 0 確認的是配置與設計一致性，不是 V01／V09 通過。專用帳號、database／schema 存在性、登入／權限、app 容器 DNS／連線、實際 server 查詢版本、migration、精度往返與重啟保留仍待步驟 3／7。Driver 相容性待步驟 1。

目前無需使用者提供密碼；步驟 3 需有效憑證時以執行環境注入，再驗證專案範圍權限。既有 PostgreSQL 由使用者維護，本專案不升級或重建。
