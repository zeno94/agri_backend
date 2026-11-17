"""统一业务异常与全局异常处理器。

成功响应直接返回业务数据；失败响应统一为：
    {"code": "INSUFFICIENT_STOCK", "message": "库存不足...", "detail": {...}}
前端可通过 HTTP 状态码 + code 做稳定判断。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)

# 常见 HTTP 状态码 -> 稳定业务错误码
STATUS_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    """可预期的业务异常，由全局处理器转换为标准错误响应。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        detail: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

    def __repr__(self) -> str:  # 便于日志排查
        return f"AppError(code={self.code!r}, status={self.status_code}, message={self.message!r})"


def _error_body(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI 实例上注册全局异常处理。"""

    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(_error_body(exc.code, exc.message, exc.detail)),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": ".".join(str(part) for part in error.get("loc", ())),
                "msg": error.get("msg", "参数校验失败"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", "请求参数校验失败", errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODE_MAP.get(exc.status_code, f"HTTP_{exc.status_code}")
        if isinstance(exc.detail, str):
            message, detail = exc.detail, None
        else:
            message, detail = "请求处理失败", exc.detail
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(_error_body(code, message, detail)),
            headers=exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("数据库唯一约束/外键冲突：%s %s", request.url.path, exc.orig)
        return JSONResponse(
            status_code=409,
            content=_error_body("DATA_CONFLICT", "数据唯一性冲突或关联数据不存在"),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("数据库异常：%s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_error_body("DATABASE_ERROR", "数据库操作失败，请稍后重试"),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常：%s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL_ERROR", "服务器内部错误"),
        )
