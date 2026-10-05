-- C7-7-3 補記：Usage 頁的 Database Size 與 pg_database_size(current_database()) 差約 15 MB。
-- Supabase 文件（platform/database-size）定義 Database size 為叢集內所有 database 的 pg_database_size 合計，
-- 而 c77-capacity.sql 查詢 2 只量了目前這個 database。唯讀。
-- 兩段分開執行，各自貼回結果。

-- 查詢 1：每個 database 的大小，以及合計
-- 沒有 CONNECT 權限、也不屬於 pg_read_all_stats 時，pg_database_size 會報錯；這種列改顯示 NULL，不中斷整個查詢。
WITH d AS (
  SELECT datname,
         datallowconn,
         CASE WHEN has_database_privilege(datname, 'CONNECT') OR pg_has_role('pg_read_all_stats', 'member')
              THEN pg_database_size(datname) END AS bytes
  FROM pg_database
)
SELECT datname, datallowconn, bytes, (datname = current_database()) AS is_current
FROM d
UNION ALL
SELECT '(sum)', NULL, sum(bytes), NULL FROM d
ORDER BY bytes DESC NULLS LAST;

-- 查詢 2：WAL 目錄的大小（文件列為 Disk size 的一部分，不算進 Database size）
-- 需要 pg_monitor 或超級使用者；權限不足時會報錯，照實貼回錯誤訊息即可。
SELECT count(*) AS wal_files, sum(size) AS wal_bytes FROM pg_ls_waldir();
