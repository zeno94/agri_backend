"""请求上下文中间件：request_id 透传 + 访问日志。

使用纯 ASGI 实现，避免 BaseHTTPMiddleware 在流式响应下的额外开销与兼容问题。
"""

from __future__ import annotations

import re
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("app.access")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_PATTERN.match(incoming) else uuid4().hex
        token = request_id_ctx.set(request_id)
        started_at = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "%s %s -> %s (%.2f ms)",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_code,
                elapsed_ms,
            )
            request_id_ctx.reset(token)
