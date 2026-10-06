-- RD-0(c) / RD-2: finpo_app 的角色屬性，不含密碼。只有 SELECT，不改任何東西。
-- 在正式專案與演練專案的 SQL Editor 各跑一次，逐列比對。
-- pg_auth_members 的 inherit_option／set_option 需要 PostgreSQL 16 以上（正式專案為 17.6）。
-- finpo_app 不存在時，第 4、7 列的 has_*_privilege 會讓整個查詢報錯，所以演練專案要在 RD-2 建好角色後才跑。
-- 2026-10-06 已在本機 postgres:17-alpine（17.10）以假角色預演，8 列都讀得出來；Supabase 上尚未執行。
SELECT * FROM (
  SELECT 1 AS n, 'role' AS item, (
    SELECT row_to_json(r)::text FROM (
      SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
             rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil, rolconfig
      FROM pg_roles WHERE rolname = 'finpo_app'
    ) r
  ) AS value
  UNION ALL
  -- finpo_app 是哪些角色的成員
  SELECT 2, 'member_of', (
    SELECT string_agg(g.rolname || ' admin=' || m.admin_option || ' inherit=' || m.inherit_option
                      || ' set=' || m.set_option, ', ' ORDER BY g.rolname)
    FROM pg_auth_members m
    JOIN pg_roles g ON g.oid = m.roleid
    JOIN pg_roles u ON u.oid = m.member
    WHERE u.rolname = 'finpo_app'
  )
  UNION ALL
  -- 哪些角色是 finpo_app 的成員（PG 16 起，建立者會自動取得 ADMIN）
  SELECT 3, 'members', (
    SELECT string_agg(u.rolname || ' admin=' || m.admin_option || ' inherit=' || m.inherit_option
                      || ' set=' || m.set_option, ', ' ORDER BY u.rolname)
    FROM pg_auth_members m
    JOIN pg_roles g ON g.oid = m.roleid
    JOIN pg_roles u ON u.oid = m.member
    WHERE g.rolname = 'finpo_app'
  )
  UNION ALL
  SELECT 4, 'db_privs_connect_create_temp',
    has_database_privilege('finpo_app', current_database(), 'CONNECT')::text || ','
    || has_database_privilege('finpo_app', current_database(), 'CREATE')::text || ','
    || has_database_privilege('finpo_app', current_database(), 'TEMP')::text
  UNION ALL
  SELECT 5, 'datacl', (SELECT datacl::text FROM pg_database WHERE datname = current_database())
  UNION ALL
  -- ALTER ROLE ... SET 與 ALTER ROLE ... IN DATABASE ... SET 的設定
  SELECT 6, 'role_settings', (
    SELECT string_agg(coalesce(d.datname, '*') || ':' || array_to_string(s.setconfig, ';'), ' | ')
    FROM pg_db_role_setting s
    LEFT JOIN pg_database d ON d.oid = s.setdatabase
    WHERE s.setrole = (SELECT oid FROM pg_roles WHERE rolname = 'finpo_app')
  )
  UNION ALL
  SELECT 7, 'public_schema_usage_create',
    has_schema_privilege('finpo_app', 'public', 'USAGE')::text || ','
    || has_schema_privilege('finpo_app', 'public', 'CREATE')::text
  UNION ALL
  SELECT 8, 'server_version', current_setting('server_version')
) q
ORDER BY n;
