-- C6-3：初始化前後的唯讀快照。只有一個 SELECT，不寫入任何東西。
-- 在 Supabase SQL Editor 以管理者執行，結果整張表複製回來即可（不含秘密）。
WITH t AS (
  SELECT c.oid, c.relname, c.relrowsecurity, pg_get_userbyid(c.relowner) AS owner
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'dashboard' AND c.relkind = 'r'
)
SELECT * FROM (
  SELECT 1 AS n, 'current_user' AS item, current_user::text AS value
  UNION ALL SELECT 2, 'db_now', now()::text
  UNION ALL SELECT 3, 'migrations',
    (SELECT string_agg(version || ':' || left(checksum, 12) || ':' || package_version, ', ' ORDER BY version) FROM dashboard.schema_migrations)
  UNION ALL SELECT 4, 'portfolio',
    (SELECT 'revision=' || (document->>'revision') || ' rows=' || jsonb_array_length(document->'rows') FROM dashboard.portfolio WHERE id = 1)
  UNION ALL SELECT 5, 'refresh_jobs', (SELECT count(*)::text FROM dashboard.refresh_jobs)
  UNION ALL SELECT 6, 'catalog_generations',
    (SELECT count(*) || ' latest_completed=' || max(completed_at) || ' latest_expires=' || max(expires_at) FROM dashboard.instrument_catalog_generations)
  UNION ALL SELECT 7, 'tables', (SELECT count(*)::text FROM t)
  UNION ALL SELECT 8, 'rls_enabled', (SELECT count(*) FILTER (WHERE relrowsecurity) || '/' || count(*) FROM t)
  UNION ALL SELECT 9, 'owners', (SELECT string_agg(DISTINCT owner, ', ') FROM t)
  UNION ALL SELECT 10, 'policies',
    (SELECT count(*) || ' ' || string_agg(DISTINCT policyname || '/' || cmd || '/' || array_to_string(roles, '+'), ', ')
     FROM pg_policies WHERE schemaname = 'dashboard')
  UNION ALL SELECT 11, 'grants_finpo_app',
    (SELECT string_agg(relname || '=' || privs, ', ' ORDER BY relname) FROM (
       SELECT t.relname, string_agg(g.privilege_type, '+' ORDER BY g.privilege_type) AS privs
       FROM t LEFT JOIN information_schema.role_table_grants g
         ON g.table_schema = 'dashboard' AND g.table_name = t.relname AND g.grantee = 'finpo_app'
       GROUP BY t.relname) x)
  UNION ALL SELECT 12, 'schema_acl', (SELECT nspacl::text FROM pg_namespace WHERE nspname = 'dashboard')
  UNION ALL SELECT 13, 'app_schema_usage_finpo_app',
    (SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'app')
                 THEN has_schema_privilege('finpo_app', 'app', 'USAGE')::text ELSE 'no app schema' END)
  UNION ALL SELECT 14, 'advisory_locks_held', (SELECT count(*)::text FROM pg_locks WHERE locktype = 'advisory' AND granted)
) s ORDER BY n;
