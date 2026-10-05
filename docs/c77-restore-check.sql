-- C7-7-5：逐表列數與內容雜湊。唯讀，輸出不含代碼、股數與金額（只有雜湊值）。
-- 匯出前、匯出後在 Supabase SQL Editor 各跑一次；還原後在本機資料庫再跑一次，三份逐列比對。
-- 整段一起選取執行，結果顯示的是最後一個 SELECT。
--
-- 雜湊的算法：每一列轉成文字取 md5，依位元組順序（COLLATE "C"）排序後串起來再取 md5。
-- 列的文字表示會受下面幾個 session 設定影響，所以先固定，免得兩邊的預設值不同就對不上。
-- 排序不依賴實體順序，所以 pg_restore 改變了列的存放位置也不影響結果。
SET TimeZone = 'UTC';
SET DateStyle = 'ISO, MDY';
SET IntervalStyle = 'postgres';
SET extra_float_digits = 1;
SET bytea_output = 'hex';

SELECT n.nspname AS schema,
       c.relname AS table_name,
       (xpath('/row/n/text()',
              query_to_xml(format('SELECT count(*) AS n FROM %I.%I', n.nspname, c.relname), false, true, '')))[1]::text::bigint AS row_count,
       (xpath('/row/h/text()',
              query_to_xml(format('SELECT md5(coalesce(string_agg(r, '''' ORDER BY r COLLATE "C"), '''')) AS h FROM (SELECT md5(t::text) AS r FROM %I.%I t) s',
                                  n.nspname, c.relname), false, true, '')))[1]::text AS content_md5
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('dashboard', 'app') AND c.relkind IN ('r', 'p')
ORDER BY schema, table_name;
