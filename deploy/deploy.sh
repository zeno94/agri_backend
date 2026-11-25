#!/usr/bin/env bash
# 服务器端部署脚本。
#
# 由 GitHub Actions 通过 SSH 触发，也可以手动执行：
#   /opt/agri/agri_backend/deploy/deploy.sh
#
# 做的事：拉最新编排 -> 拉最新镜像 -> 替换容器 -> 等健康检查通过。
# 设计要点：
#   1. flock 串行化：前后端仓库各自触发部署，两个 job 可能同时到达服务器；
#   2. 等健康检查再退出：部署失败要让 CI 变红，而不是「命令执行成功」就算成功；
#   3. 只替换镜像变了的容器，MySQL 数据卷不动。
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agri/agri_backend}"
COMPOSE_FILE="docker-compose.prod.yml"
LOCK_FILE="${LOCK_FILE:-/tmp/agri-deploy.lock}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

exec 9>"$LOCK_FILE"
if ! flock -w 180 9; then
  echo "[deploy] 另一个部署任务占用锁超过 180s，放弃本次部署" >&2
  exit 1
fi

echo "[deploy] $(date -Is) 开始部署"
cd "$APP_DIR"

echo "[deploy] 拉取最新编排..."
git pull --ff-only -q

cd deploy
echo "[deploy] 拉取镜像..."
docker compose -f "$COMPOSE_FILE" pull -q

echo "[deploy] 替换容器..."
docker compose -f "$COMPOSE_FILE" up -d

echo "[deploy] 等待健康检查（最多 ${WAIT_SECONDS}s）..."
elapsed=0
while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
  sleep 5
  elapsed=$((elapsed + 5))
  api=$(docker inspect agri-erp-api --format '{{.State.Health.Status}}' 2>/dev/null || echo unknown)
  web=$(docker inspect agri-erp-web --format '{{.State.Health.Status}}' 2>/dev/null || echo unknown)
  mysql=$(docker inspect agri-erp-mysql --format '{{.State.Health.Status}}' 2>/dev/null || echo unknown)
  echo "[deploy]   ${elapsed}s api=$api web=$web mysql=$mysql"
  if [ "$api" = "healthy" ] && [ "$web" = "healthy" ] && [ "$mysql" = "healthy" ]; then
    echo "[deploy] 部署完成"
    docker compose -f "$COMPOSE_FILE" ps --format 'table {{.Name}}\t{{.Status}}'
    exit 0
  fi
done

echo "[deploy] 超时未就绪：api=$api web=$web mysql=$mysql" >&2
docker compose -f "$COMPOSE_FILE" ps >&2
docker compose -f "$COMPOSE_FILE" logs --tail 40 api >&2 || true
exit 1
