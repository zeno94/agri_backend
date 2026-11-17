"""日志基础设施：统一格式，并通过 ContextVar 将 request_id 注入到每一行日志。"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

from app.core.config import settings

# 由请求中间件写入，异步上下文安全
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """把当前请求的 request_id 注入 LogRecord。"""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - 覆盖 logging 接口
        record.request_id = request_id_ctx.get()
        return True


def setup_logging() -> None:
    """初始化根日志器。重复调用是幂等的，便于测试。"""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(request_id)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(RequestIdFilter())

    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # 业务日志在调试模式下更详细，第三方库保持 INFO 以免刷屏
    logging.getLogger("app").setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # 访问日志由自定义中间件输出，避免和 uvicorn 重复
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
