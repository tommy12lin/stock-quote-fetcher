# 步驟 1 執行紀錄

日期：2026-09-08。範圍：專案骨架、版本鎖定、匿名範例及 Linux 容器依賴相容性；未連線 PostgreSQL 或報價服務。

## 交付

- pyproject.toml、uv.lock、.python-version：套件中繼資料、console script、精確直接依賴、Python 與 uv 版本。
- src/stock_quote_fetcher：CLI 參數解析、help／version、模組入口；功能命令回報未實作且退出 1，參數錯誤退出 2。
- tests/test_cli.py：透過已安裝 console script 驗證公開入口、退出碼與未實作行為。
- examples/holdings.csv、config.example.toml、.env.example、.gitignore：匿名持股、一般設定草案、空秘密欄位及忽略規則。憑證均忽略，移除舊規則对公司根憑證的例外，符合架構要求。
- README、架構與開發計畫：同步使用方法及狀態。

## 版本與查核依據

Python 官方版本頁重新確認 3.14.7；套件版本由 PyPI 各套件 JSON API 的 info.version 查核，與當日安裝版本一致。[Python 版本](https://www.python.org/doc/versions/)、[uv](https://pypi.org/project/uv/)、[uv_build](https://pypi.org/project/uv_build/)、[psycopg](https://pypi.org/project/psycopg/)、[yfinance](https://pypi.org/project/yfinance/)、[httpx](https://pypi.org/project/httpx/)、[exchange-calendars](https://pypi.org/project/exchange-calendars/)、[tzdata](https://pypi.org/project/tzdata/)、[pytest](https://pypi.org/project/pytest/)。

| 項目 | 本次結果 |
|---|---|
| Python | 3.14.7 |
| uv／uv_build | 0.12.10／0.12.10；uv_build 無傳遞依賴 |
| yfinance／httpx | 1.7.0／0.28.1 |
| exchange-calendars／tzdata | 4.13.2／2026.3 |
| psycopg／psycopg-binary | 3.3.5／3.3.5；實作 binary，bundled libpq 180006 |
| pytest | 9.1.1 |
| OS／平台 | Debian 13 trixie、linux/amd64、glibc 2.41 |
| Docker Engine／Compose | 29.6.1／v5.2.0 |
| 基礎映像 | python:3.14.7-slim-trixie |
| 多平台 index digest | sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 |
| linux/amd64 manifest | sha256:810da6270e43d30a1f3e0e1eabbeb6fbd9d78ad9dd2e754d5297a3d6cb42df46 |
| uv.lock SHA-256 | 4aa3b96862003b9eb385411e85b32a11d52bb6eba74d57f36fa3a10c49f04999 |

Docker registry 的固定 patch tag 經 imagetools inspect 確認指向上述 index。本輪指定 amd64，不推論其他平台已通過。

## 驗證結果

完整輸出見 [step-1-validation.txt](step-1-validation.txt)。

1. uv lock 解析 41 個套件；uv lock --check 通過。跨平台 lock 與本平台實際安裝數不同屬正常。
2. uv sync --frozen 安裝 40 個套件（含本專案），uv pip check 通過；映像沒有 gcc。
3. 直接依賴皆匯入成功，psycopg 確認 binary implementation；Asia/Taipei、America/New_York 時區載入成功。
4. pytest：10 passed in 3.81s。確認 help、套件版本、模組入口、必要參數與未知命令，以及未實作命令不輸出成功、不建立輸出目錄。
5. uv build 成功產生 sdist，再從 sdist 建立 wheel；另一個乾淨 venv 以 --no-deps 安裝 wheel 後 help／version 成功，確認 CLI 骨架不需載入報價／資料庫依賴。完整依賴環境另由前述 sync 驗證。建置產物位於一次性容器 /tmp，測完移除。
6. git diff --check 通過；git check-ignore 確認本機秘密／設定／持股／憑證／輸出忽略，三份範例檔可追蹤。

## 重跑方式

已安裝 Python 3.14.7 與 uv 0.12.10 可直接依 README 執行。此主機 PATH 尚無 Python／uv，這次使用一次性 Docker 容器，不修改主機 Python 安裝。

以下 PowerShell 命令在專案根目錄重跑鎖定檢查、安裝與 CLI 測試；需要套件下載網路。venv、cache 置於容器 /tmp，退出自動清除：

```powershell
$step1Commands = @'
python -m pip install --disable-pip-version-check --no-cache-dir uv==0.12.10
uv lock --check --python /usr/local/bin/python
uv sync --frozen --python /usr/local/bin/python
uv pip check --python /tmp/stock-poc-venv/bin/python
uv run --frozen pytest -q -p no:cacheprovider
uv run --frozen stock-poc --help
'@
docker run --rm --platform linux/amd64 --mount "type=bind,source=$((Get-Location).Path),target=/workspace" -w /workspace -e UV_PROJECT_ENVIRONMENT=/tmp/stock-poc-venv -e UV_CACHE_DIR=/tmp/uv-cache -e PYTHONDONTWRITEBYTECODE=1 python:3.14.7-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 sh -ec $step1Commands
```

日常不執行 uv lock 更新。需要調整依賴時更新 pyproject.toml 後產生 lock，再重新驗證與記錄版本。

## 尚未驗證

本輪僅滿足 V01 的依賴安裝部分。Dockerfile／App Compose、非 root 執行、PostgreSQL 登入／權限、報價功能、實際 CSV 驗證及估值仍待後續步驟；Windows 原生安裝尚未測。config.example.toml 與 .env.example 尚無執行時解析器，CLI 不自動載入 .env。這些狀態不記為功能驗收通過。
