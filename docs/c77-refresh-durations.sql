-- C7-7-2：抓價耗時。唯讀，輸出不含代碼與金額。
-- 兩段分開執行（在 SQL Editor 只選取一段再按 Run），各自貼回結果。
--
-- job 與 run 之間沒有外鍵：一次更新的每一批各開一個 run（dashboard.py run_job），
-- 所以以「run 的 started_at 落在 job 的 created_at 與 completed_at 之間」歸屬。
-- 更新由 advisory lock 互斥，job 的時間窗不會重疊（C4-3）。
-- 官方清單更新（finpo-catalog-refresh）不開 run，不會被算進來。

-- 查詢 1：每個 job 一列
WITH j AS (
  SELECT id,
         (document->>'created_at')::timestamptz   AS created,
         (document->>'completed_at')::timestamptz AS completed,
         document->>'status'                      AS status,
         coalesce((document->>'catalog_only')::boolean, false) AS catalog_only,
         (document->>'portfolio_revision')::int   AS rev,
         document->>'message'                     AS message
  FROM dashboard.refresh_jobs
), r AS (
  SELECT j.id AS job_id, ru.id AS run_id
  FROM j JOIN dashboard.runs ru ON ru.started_at BETWEEN j.created AND coalesce(j.completed, j.created)
), a AS (
  SELECT r.job_id,
         count(DISTINCT r.run_id)                              AS batches,
         count(DISTINCT fa.instrument_id)                      AS instruments,
         count(fa.id)                                          AS attempts,
         count(fa.id) FILTER (WHERE fa.status <> 'success')    AS not_success,
         string_agg(DISTINCT fa.status || coalesce('/' || fa.error_code, ''), ',')
           FILTER (WHERE fa.status <> 'success')               AS not_success_kinds,
         string_agg(DISTINCT cy.market, ',')                   AS markets,
         min(fa.started_at)                                    AS first_attempt,
         max(fa.completed_at)                                  AS last_attempt
  FROM r
  LEFT JOIN dashboard.fetch_attempts fa ON fa.run_id = r.run_id
  LEFT JOIN dashboard.cycles cy ON cy.id = fa.cycle_id
  GROUP BY r.job_id
)
SELECT row_number() OVER (ORDER BY j.created)                               AS n,
       left(j.id, 8)                                                        AS job,
       to_char(j.created AT TIME ZONE 'UTC', 'MM-DD HH24:MI:SS')            AS created_utc,
       round(extract(epoch FROM j.completed - j.created)::numeric, 3)       AS wall_s,
       j.status, j.catalog_only, j.rev,
       a.batches, a.instruments, a.attempts, a.not_success, a.not_success_kinds, a.markets,
       round(extract(epoch FROM a.first_attempt - j.created)::numeric, 3)   AS setup_s,
       round(extract(epoch FROM j.completed - a.last_attempt)::numeric, 3)  AS wrapup_s,
       round((extract(epoch FROM j.completed - j.created) / nullif(a.instruments, 0))::numeric, 3) AS s_per_instrument,
       j.message
FROM j LEFT JOIN a ON a.job_id = j.id
ORDER BY j.created;

-- 查詢 2：每一批（每個 run）依市場組合彙總，對照 C7-6 R5 的單檔成本
WITH j AS (
  SELECT (document->>'created_at')::timestamptz AS created,
         (document->>'completed_at')::timestamptz AS completed
  FROM dashboard.refresh_jobs
), b AS (
  SELECT ru.id AS run_id,
         string_agg(DISTINCT cy.market, '+' ORDER BY cy.market) AS mix,
         count(DISTINCT fa.instrument_id) AS instruments,
         count(fa.id) FILTER (WHERE fa.status <> 'success') AS not_success,
         extract(epoch FROM max(fa.completed_at) - min(fa.started_at)) AS wall_s
  FROM j
  JOIN dashboard.runs ru ON ru.started_at BETWEEN j.created AND coalesce(j.completed, j.created)
  JOIN dashboard.fetch_attempts fa ON fa.run_id = ru.id
  JOIN dashboard.cycles cy ON cy.id = fa.cycle_id
  GROUP BY ru.id
)
SELECT mix,
       count(*)                                    AS batches,
       sum(instruments)                            AS instruments,
       sum(not_success)                            AS not_success,
       round(min(wall_s / instruments)::numeric, 3) AS min_s_per_instrument,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY wall_s / instruments))::numeric, 3) AS median_s_per_instrument,
       round(max(wall_s / instruments)::numeric, 3) AS max_s_per_instrument,
       round((sum(wall_s) / sum(instruments))::numeric, 3) AS pooled_s_per_instrument
FROM b
GROUP BY mix
ORDER BY mix;
