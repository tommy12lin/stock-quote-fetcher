-- C7-7-3：DB 容量與連線數。唯讀，輸出不含代碼、金額與 IP。
-- 四段分開執行（在 SQL Editor 只選取一段再按 Run），各自貼回結果。
-- 對照基準：C5-6 在初始化後量得 dashboard 合計 401,408 bytes、整個 database 11,521,171 bytes。

-- 查詢 1：dashboard 與 app 的每張表，列數為精確計數
SELECT n.nspname AS schema,
       c.relname AS table_name,
       (xpath('/row/n/text()',
              query_to_xml(format('SELECT count(*) AS n FROM %I.%I', n.nspname, c.relname), false, true, '')))[1]::text::bigint AS row_count,
       pg_table_size(c.oid)          AS table_bytes,
       pg_indexes_size(c.oid)        AS index_bytes,
       pg_total_relation_size(c.oid) AS total_bytes
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('dashboard', 'app') AND c.relkind IN ('r', 'p')
ORDER BY total_bytes DESC, schema, table_name;

-- 查詢 2：每個 schema 的合計，以及整個 database 的大小
-- TOAST 已算進所屬的表（pg_total_relation_size），所以排除 pg_toast。
SELECT n.nspname AS schema,
       count(*) AS relations,
       sum(pg_total_relation_size(c.oid)) AS total_bytes
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'm') AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp%'
GROUP BY n.nspname
UNION ALL
SELECT '(database)', NULL, pg_database_size(current_database())
ORDER BY total_bytes DESC;

-- 查詢 3：每一代官方清單的列數與到期狀態
SELECT row_number() OVER (ORDER BY g.completed_at) AS n,
       left(g.id::text, 8) AS generation,
       to_char(g.completed_at AT TIME ZONE 'UTC', 'MM-DD HH24:MI:SS') AS completed_utc,
       to_char(g.expires_at AT TIME ZONE 'UTC', 'MM-DD HH24:MI:SS')   AS expires_utc,
       g.expires_at > now() AS unexpired,
       count(ci.instrument_id) AS row_count,
       count(ci.instrument_id) FILTER (WHERE ci.market = 'TW') AS tw,
       count(ci.instrument_id) FILTER (WHERE ci.market = 'US') AS us
FROM dashboard.instrument_catalog_generations g
LEFT JOIN dashboard.catalog_instruments ci ON ci.generation_id = g.id
GROUP BY g.id, g.completed_at, g.expires_at
ORDER BY g.completed_at;

-- 查詢 4：目前的連線，依角色、應用程式、類型、狀態計數；最後一列是上限
-- 在服務閒置時執行（沒有人開著 finpo 頁面在更新）。SQL Editor 自己也會佔連線。
SELECT coalesce(usename::text, '(none)')                AS role,
       coalesce(nullif(application_name, ''), '(none)') AS application,
       backend_type,
       coalesce(state, '(none)')                        AS state,
       count(*)                                         AS connections
FROM pg_stat_activity
GROUP BY 1, 2, 3, 4
UNION ALL
SELECT '(limit)',
       'max_connections=' || current_setting('max_connections'),
       'superuser_reserved=' || current_setting('superuser_reserved_connections'),
       'total_now',
       (SELECT count(*) FROM pg_stat_activity)
ORDER BY 1, 2, 3, 4;
