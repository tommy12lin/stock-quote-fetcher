#!/bin/sh
# RD-5：在 python runner 容器內執行（repo 以唯讀掛在 /workspace），以 finpo_app 經 session pooler 驗證還原後的演練專案。
# 連線參數由 DB_HOST／DB_PORT／DB_NAME／DB_USER／DB_SSLROOTCERT 環境變數覆寫 deploy/cloud.toml；
# 密碼在這裡互動讀入一次，只存在這個容器的行程環境裡，容器結束即消失。
# 全部是唯讀操作：cloud_db check 只查權限；持股以 READ ONLY 交易讀取。
set -u
OUT=/out/rd5-result.txt
: > "$OUT"

printf 'Password for %s: ' "$DB_USER"
stty -echo 2>/dev/null
read -r DB_PASSWORD
stty echo 2>/dev/null
printf '\n'
export DB_PASSWORD

echo "start $(date -u +%T)" | tee -a "$OUT"
python -m pip install -q --root-user-action=ignore uv==0.12.10 && uv sync --frozen -q || { echo "依賴安裝失敗" | tee -a "$OUT"; exit 2; }

echo "== cloud_db check" | tee -a "$OUT"
uv run --frozen python -m stock_quote_fetcher.cloud_db check --config deploy/cloud.toml 2>&1 | tee -a "$OUT"

echo "== runtime read" | tee -a "$OUT"
uv run --frozen python - <<'PY' 2>&1 | tee -a "$OUT"
import json
from dataclasses import replace
from pathlib import Path
from stock_quote_fetcher.config import load_database_config
from stock_quote_fetcher.storage import Storage

# 與 cloud_db 相同：cloud.toml 沒有 schema，預設值不是 dashboard（本機預演時漏了這行，得到 SQLSTATE 3F000）。
config = replace(load_database_config(Path('deploy/cloud.toml')), schema='dashboard')
with Storage(config) as storage:
    perms = storage.check_permissions()
    with storage.transaction(writer=False, readonly=True):
        row = storage.conn.execute(
            "SELECT document->>'revision' AS revision, jsonb_array_length(document->'rows') AS rows "
            "FROM dashboard.portfolio WHERE id = 1").fetchone()
    print(json.dumps({'username': perms['username'], 'server_version': perms['server_version'],
                      'ssl_in_use': storage.conn.pgconn.ssl_in_use,
                      'revision': row['revision'], 'rows': row['rows']}, ensure_ascii=False))
PY
echo "end $(date -u +%T)" | tee -a "$OUT"
