-- RD-2：在「演練專案」的 SQL Editor 以 postgres 執行。不要在正式專案執行。
-- 屬性依 2026-10-06 RD-0(c) 從正式專案讀出的結果（rd-role-attrs.sql），不是只照 C1 證據。
-- 執行前把 <密碼> 換成自己產生的值；值裡不要有單引號。這份檔案本身不含密碼，不要把填了密碼的版本存回 repo。
-- 正式專案已經有 finpo_app，第一段會直接報錯中止，所以誤貼到正式專案也不會改到任何東西。

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finpo_app') THEN
    RAISE EXCEPTION 'finpo_app 已存在：這裡不是新的演練專案，停止';
  END IF;
END
$$;

-- 正式專案：rolinherit=true、rolconnlimit=-1、rolconfig=null、沒有 role_settings，這裡照寫預設值讓意圖明確。
-- postgres 會自動取得 finpo_app 的 ADMIN 成員關係（PostgreSQL 16 起的行為），正式專案也是如此，不必另外 GRANT。
CREATE ROLE finpo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT
  CONNECTION LIMIT -1 PASSWORD '<密碼>';

-- 正式專案的 datacl 有一筆明確的 finpo_app=c/postgres。PUBLIC 本來就有 CONNECT（=Tc），照樣明確授權，讓 datacl 一致。
GRANT CONNECT ON DATABASE postgres TO finpo_app;
