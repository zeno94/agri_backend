#!/usr/bin/env bash
# 农机 ERP 巡检脚本：可用性 + 依赖 + 资源水位，异常时通过 webhook 告警。
#
# 为什么不用 Prometheus + Grafana：这台服务器只有 961MB 内存，两个容器起步就要 300MB。
# 巡检脚本几乎不占内存，5 分钟一跑，覆盖「服务还活着吗、数据库通不通、盘会不会满」这三件事。
# /metrics 仍然对外暴露，将来换 Prometheus 抓取不用改代码。
#
# 用法：
#   ./heartbeat.sh            # 单次巡检，正常退出 0，异常退出 1
#   crontab: */5 * * * * /opt/agri/monitor/heartbeat.sh
#
# 配置：同目录 monitor.env（可选），支持
#   HEARTBEAT_URL        正常时 ping 的地址（healthchecks.io 之类，没配就不发）
#   HEARTBEAT_FAIL_URL   异常时 ping 的地址
#   DINGTALK_WEBHOOK     钉钉机器人 webhook，异常时推送文本告警
#   DISK_WARN_PCT        磁盘告警阈值，默认 85
#   MEM_WARN_PCT         内存告警阈值，默认 92
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/monitor.env"
LOG_FILE="${SCRIPT_DIR}/heartbeat.log"

# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

PUBLIC_URL="${PUBLIC_URL:-https://agri.novix.ccwu.cc}"
API_CONTAINER="${API_CONTAINER:-agri-erp-api}"
DISK_WARN_PCT="${DISK_WARN_PCT:-85}"
MEM_WARN_PCT="${MEM_WARN_PCT:-92}"

FAIL=0
REASONS=()

fail() {
  FAIL=1
  REASONS+=("$1")
}

# 1) 公网可达性：Cloudflare → NPM → web
http_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${PUBLIC_URL}/health" 2>/dev/null)
[ "$http_code" = "200" ] || fail "health=${http_code}"

# 2) 依赖健康：直接问 api 容器，绕过外网噪声
ready=$(docker exec "$API_CONTAINER" wget -qO- --timeout=5 http://127.0.0.1:8000/ready 2>/dev/null || echo '')
case "$ready" in
  *'"database":true'*) : ;;
  *) fail "database=down" ;;
esac
case "$ready" in
  *'"redis":true'*) : ;;
  *) fail "redis=down" ;;
esac

# 3) 资源水位
disk_pct=$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')
[ -n "$disk_pct" ] && [ "$disk_pct" -lt "$DISK_WARN_PCT" ] || fail "disk=${disk_pct}%"

mem_pct=$(free -m 2>/dev/null | awk '/^Mem:/{printf "%d", $3 / $2 * 100}')
[ -n "$mem_pct" ] && [ "$mem_pct" -lt "$MEM_WARN_PCT" ] || fail "mem=${mem_pct}%"

stamp="$(date -Is)"
summary="health=${http_code} disk=${disk_pct}% mem=${mem_pct}%"

if [ "$FAIL" -eq 0 ]; then
  echo "${stamp} OK ${summary}" >>"$LOG_FILE"
  # 正常心跳：healthchecks.io 之类的「没收到 ping 就告警」服务
  if [ -n "${HEARTBEAT_URL:-}" ]; then
    curl -fsS --max-time 10 "$HEARTBEAT_URL" >/dev/null 2>&1 || true
  fi
  exit 0
fi

message="[农机 ERP] 巡检异常：${REASONS[*]} | ${summary}"
echo "${stamp} FAIL ${message}" >>"$LOG_FILE"

[ -n "${HEARTBEAT_FAIL_URL:-}" ] && curl -fsS --max-time 10 "$HEARTBEAT_FAIL_URL" >/dev/null 2>&1 || true

if [ -n "${DINGTALK_WEBHOOK:-}" ]; then
  payload=$(printf '{"msgtype":"text","text":{"content":"%s"}}' "$message")
  curl -sS --max-time 10 -H 'Content-Type: application/json' -d "$payload" "$DINGTALK_WEBHOOK" >/dev/null 2>&1 || true
fi

# 日志自己也要有上限，别把盘写满——这是刚踩过的坑
if [ -f "$LOG_FILE" ]; then
  lines=$(wc -l <"$LOG_FILE")
  if [ "$lines" -gt 2000 ]; then
    tail -n 1000 "$LOG_FILE" >"${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
  fi
fi

exit 1
