#!/usr/bin/env bash
# 容器入口：等待数据库 -> 执行迁移 -> 初始化基础数据 -> 启动 API
set -euo pipefail

cd /app

if [[ "${WAIT_FOR_DB:-true}" == "true" ]]; then
  echo "[entrypoint] 等待 MySQL 就绪..."
  python -m scripts.wait_for_db
fi

echo "[entrypoint] 执行 Alembic 数据库迁移..."
alembic upgrade head

echo "[entrypoint] 初始化基础账号与示例数据（幂等）..."
python -m app.db.init_db

echo "[entrypoint] 启动 Uvicorn..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
