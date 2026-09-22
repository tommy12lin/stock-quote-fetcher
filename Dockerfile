# syntax=docker/dockerfile:1
# 固定基礎映像；每次建置前重新核對 3.14 系列最新修補版與 digest（架構第 2 節）。
# 2026-09-08 核對：python:3.14-slim 仍解析為同一 digest，映像內為 Python 3.14.7、Debian 13.6。
ARG BASE_IMAGE=python:3.14.7-slim-trixie@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

FROM ${BASE_IMAGE} AS builder
# uv 版本與 pyproject.toml 的 required-version 一致；不符時 uv 會直接拒絕執行。
ARG UV_VERSION=0.12.10
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1
RUN --mount=type=secret,id=company_ca \
    if [ -f /run/secrets/company_ca ]; then export PIP_CERT=/run/secrets/company_ca; fi; \
    pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# frozen：uv.lock 為權威，與 pyproject.toml 不符即失敗，不在建置時重新解析依賴。
RUN --mount=type=secret,id=company_ca \
    if [ -f /run/secrets/company_ca ]; then cat /etc/ssl/certs/ca-certificates.crt /run/secrets/company_ca > /tmp/build-ca.pem; export SSL_CERT_FILE=/tmp/build-ca.pem UV_SYSTEM_CERTS=true; fi; \
    uv sync --frozen --no-dev --no-editable \
 && /app/.venv/bin/python -c "import exchange_calendars, httpx, psycopg, yfinance, zoneinfo; zoneinfo.ZoneInfo('Asia/Taipei'); zoneinfo.ZoneInfo('America/New_York')" \
 && /app/.venv/bin/stock-poc --version && rm -f /tmp/build-ca.pem

# 只用於驗證：與 runtime 相同的鎖定依賴，另含 dev group 的 pytest。
# 不是交付映像；測試檔在執行時掛載，不進入任何 build context。
FROM builder AS test
RUN --mount=type=secret,id=company_ca \
    if [ -f /run/secrets/company_ca ]; then cat /etc/ssl/certs/ca-certificates.crt /run/secrets/company_ca > /tmp/build-ca.pem; export SSL_CERT_FILE=/tmp/build-ca.pem UV_SYSTEM_CERTS=true; fi; \
    uv sync --frozen && rm -f /tmp/build-ca.pem
# CLI 測試以 PATH 呼叫 stock-poc，與 runtime stage 相同。
ENV PATH=/app/.venv/bin:${PATH}
WORKDIR /work
ENTRYPOINT ["/app/.venv/bin/python", "-m", "pytest"]

FROM ${BASE_IMAGE} AS base
ARG BASE_IMAGE
ARG APP_UID=10001
ARG APP_GID=10001
# APP_BASE_IMAGE 讓每個 run 至少記錄到確切的基礎映像；APP_IMAGE_ID 由執行環境注入實際映像 ID。
ENV APP_BASE_IMAGE=${BASE_IMAGE} \
    PATH=/app/.venv/bin:${PATH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --gid ${APP_GID} app \
 && useradd --uid ${APP_UID} --gid ${APP_GID} --home-dir /home/app --create-home --shell /usr/sbin/nologin app \
 && install -d -o app -g app -m 0755 /input /output
# 程式碼與 venv 保持 root 擁有、應用帳號唯讀，執行帳號無法改寫自己的程式。
COPY --from=builder --chown=root:root /app/.venv /app/.venv
WORKDIR /app
USER app:app

# Web 服務映像（C2-4）：代管平台只會啟動容器、不下命令，因此啟動方式必須烘在映像裡，
# 不依賴部署設定覆寫 command／args。--container 為必要：Cloud Run 要求監聽 0.0.0.0，
# port 由 PORT 環境變數提供（C2-3），平台未提供時退回 8765。
# 本 stage 刻意排在 runtime 之前，使 `docker build .` 的預設目標維持 runtime 不變。
FROM base AS web
# C2-5：設定檔隨映像出貨，與程式同版本、同一次回滾。root 擁有、應用帳號唯讀。
# --chmod 明寫：COPY 沿用來源檔權限，Windows 與 Linux runner 會給出不同的模式位元，
# 使同一份程式在兩處建出不同的層。釘死為 0644 讓建置可重現。
COPY --chown=root:root --chmod=0644 deploy/cloud.toml /app/cloud.toml
COPY --chown=root:root --chmod=0644 deploy/supabase-ca.crt /app/supabase-ca.crt
# --container 與 --config 放在 ENTRYPOINT 而非 CMD：若放 CMD，任何附加參數都會把它們
# 整組取代而靜默失去監聽介面或設定檔，表徵是平台判定啟動失敗但程式看似正常。
ENTRYPOINT ["/app/.venv/bin/stock-web", "--container", "--config", "/app/cloud.toml"]

FROM base AS runtime
# 只用 exec form：CLI 必須是 PID 1，docker stop 的 SIGTERM 才會直接送到 monitor 的處理器。
ENTRYPOINT ["/app/.venv/bin/stock-poc"]
CMD ["--help"]
