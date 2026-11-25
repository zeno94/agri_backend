"""Prometheus 指标。

暴露在 `GET /metrics`（Prometheus 文本格式），由 `deploy/` 里的巡检脚本或
Prometheus 抓取。设计原则：标签必须低基数——`route` 用路由模板（如 `/api/v1/parts/{part_id}`）
而不是真实路径，否则每个 ID 都会长成一条时间序列，把监控系统撑爆。

指标清单
--------
erp_http_requests_total{method,route,status}   Counter  请求总数
erp_http_request_duration_seconds{method,route} Histogram 请求耗时
erp_business_events_total{event}               Counter  业务事件（下单/幂等回放/越权等）
erp_database_up / erp_redis_up                 Gauge    依赖可用性，抓取时探测
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

_HTTP_REQUESTS = Counter(
    "erp_http_requests_total",
    "HTTP 请求总数",
    ["method", "route", "status"],
)

_HTTP_DURATION = Histogram(
    "erp_http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

_BUSINESS_EVENTS = Counter(
    "erp_business_events_total",
    "业务事件计数",
    ["event"],
)

DB_UP = Gauge("erp_database_up", "数据库可用（1=可用）")
REDIS_UP = Gauge("erp_redis_up", "Redis 可用（1=可用）")


def observe_request(method: str, route: str, status_code: int, elapsed_seconds: float) -> None:
    """记录一次请求。route 必须是路由模板，不能是真实路径。"""
    _HTTP_REQUESTS.labels(method=method, route=route, status=str(status_code)).inc()
    _HTTP_DURATION.labels(method=method, route=route).observe(elapsed_seconds)


def record_event(event: str) -> None:
    """记录一次业务事件，例如 sale.outbound、idempotent.replay、authz.denied。"""
    _BUSINESS_EVENTS.labels(event=event).inc()


def render() -> tuple[bytes, str]:
    """生成 Prometheus 文本格式的指标快照。"""
    return generate_latest(), CONTENT_TYPE_LATEST
