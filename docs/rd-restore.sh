#!/bin/sh
# RD-3：在 postgres:17-alpine 容器內執行，把 dump 還原到「演練專案」。
# 連線參數由 PGHOST／PGPORT／PGDATABASE／PGUSER／PGSSLMODE／PGSSLROOTCERT 環境變數提供；
# 密碼在這裡互動讀入一次，只存在這個容器的行程環境裡，容器結束即消失。
#
# 還原前先確認連到的是演練專案，不是就中止，不執行 pg_restore：
#   - 伺服器版本必須等於 EXPECT_VERSION（演練專案為 17.11，正式專案為 17.6）
#   - dashboard、app 兩個 schema 都還不存在
#   - finpo_app 角色已存在（RD-2 已建立）
# 2026-10-06 加入：第一次 RD-3 的指令沒有這道檢查，<ref> 若誤填成正式專案，pg_restore 會寫進正式資料庫。
set -u
OUT=/out
# 演練用 10-06 那一份；真正出事時以 -e DUMP=/in/<最新一份> 指定。
DUMP="${DUMP:-/in/finpo-20261006-0940.dump}"
EXPECT_VERSION="${EXPECT_VERSION:-17.11}"

date -u +%T > "$OUT/rd3-time.txt"
: > "$OUT/rd3-restore.log"

printf 'Password for %s: ' "$PGUSER"
stty -echo 2>/dev/null
read -r PGPASSWORD
stty echo 2>/dev/null
printf '\n'
export PGPASSWORD

check=$(psql -X -At -v ON_ERROR_STOP=1 -f /rd/rd-restore-preflight.sql 2>> "$OUT/rd3-restore.log")
rc=$?
echo "preflight_rc=$rc preflight=$check" >> "$OUT/rd3-time.txt"
if [ "$rc" -ne 0 ]; then
  echo "preflight 連線或查詢失敗，未還原" | tee -a "$OUT/rd3-time.txt"
  date -u +%T >> "$OUT/rd3-time.txt"
  exit 2
fi
if [ "$check" != "$EXPECT_VERSION|0|1" ]; then
  echo "不是預期的演練專案（預期 $EXPECT_VERSION|0|1，實際 $check），未還原" | tee -a "$OUT/rd3-time.txt"
  date -u +%T >> "$OUT/rd3-time.txt"
  exit 3
fi

echo "preflight 通過，開始還原" | tee -a "$OUT/rd3-time.txt"
date -u +%T >> "$OUT/rd3-time.txt"
pg_restore --verbose -d "$PGDATABASE" "$DUMP" 2>> "$OUT/rd3-restore.log"
echo "restore_exit=$?" >> "$OUT/rd3-time.txt"
date -u +%T >> "$OUT/rd3-time.txt"
cat "$OUT/rd3-time.txt"
