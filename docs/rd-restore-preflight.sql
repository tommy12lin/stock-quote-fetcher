-- RD-3 的還原前檢查，由 rd-restore.sh 呼叫。只有 SELECT。
-- 輸出一列：伺服器版本|dashboard 與 app 已存在的數目|finpo_app 是否存在（1／0）
SELECT current_setting('server_version')
       || '|' || (SELECT count(1) FROM pg_namespace WHERE nspname IN ('dashboard', 'app'))
       || '|' || (SELECT count(1) FROM pg_roles WHERE rolname = 'finpo_app');
