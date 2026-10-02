-- C7-4 C3：最近兩個 job（存 F3 後的自動更新、第二次手動更新）。唯讀，輸出不含代碼。
-- 兩段分開執行。

-- 查詢 1：每批（每個 run）的起訖、檔數、市場
WITH j AS (
  SELECT id, (document->>'created_at')::timestamptz AS c, (document->>'completed_at')::timestamptz AS d
  FROM dashboard.refresh_jobs ORDER BY document->>'created_at' DESC LIMIT 2
), jn AS (SELECT *, row_number() OVER (ORDER BY c) AS job_n FROM j)
SELECT jn.job_n, left(jn.id, 8) AS job,
       row_number() OVER (PARTITION BY jn.job_n ORDER BY min(fa.started_at)) AS batch,
       string_agg(DISTINCT cy.market, ',') AS markets,
       count(DISTINCT fa.instrument_id) AS instruments,
       count(*) AS attempts,
       count(*) FILTER (WHERE fa.status <> 'success') AS not_success,
       min(fa.started_at) AS first_start, max(fa.completed_at) AS last_end,
       round(extract(epoch FROM max(fa.completed_at) - min(fa.started_at))::numeric, 3) AS wall_s
FROM jn
JOIN dashboard.fetch_attempts fa ON fa.started_at BETWEEN jn.c AND jn.d
JOIN dashboard.cycles cy ON cy.id = fa.cycle_id
GROUP BY jn.job_n, jn.id, fa.run_id
ORDER BY jn.job_n, first_start;

-- 查詢 2：第二個 job 的處理順序，對照每個標的在第一個 job 有沒有被嘗試、有沒有成功
WITH j AS (
  SELECT (document->>'created_at')::timestamptz AS c, (document->>'completed_at')::timestamptz AS d
  FROM dashboard.refresh_jobs ORDER BY document->>'created_at' DESC LIMIT 2
), jn AS (SELECT *, row_number() OVER (ORDER BY c) AS job_n FROM j),
per AS (
  SELECT jn.job_n, fa.instrument_id, cy.market,
         min(fa.started_at) AS first_start,
         bool_or(fa.status = 'success') AS ok,
         string_agg(DISTINCT fa.status || coalesce('/' || fa.error_code, ''), ',') AS statuses
  FROM jn
  JOIN dashboard.fetch_attempts fa ON fa.started_at BETWEEN jn.c AND jn.d
  JOIN dashboard.cycles cy ON cy.id = fa.cycle_id
  GROUP BY jn.job_n, fa.instrument_id, cy.market
)
SELECT row_number() OVER (ORDER BY p2.first_start) AS order_in_job2,
       p2.market,
       (p1.instrument_id IS NOT NULL) AS tried_in_job1,
       p1.ok AS ok_in_job1,
       p2.ok AS ok_in_job2,
       p2.statuses AS job2_statuses
FROM per p2
LEFT JOIN per p1 ON p1.job_n = 1 AND p1.instrument_id = p2.instrument_id
WHERE p2.job_n = 2
ORDER BY p2.first_start;
