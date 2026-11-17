"""认证接口。

前端统一使用 JSON 登录：POST /api/v1/auth/login，请求体 {"username": "...", "password": "..."}。
Swagger 的 OAuth2 password flow 需要表单格式，因此单独保留 POST /api/v1/auth/login/form，
并把 OAuth2PasswordBearer 的 tokenUrl 指向该表单端点。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import LoginRequest, TokenOut
from app.schemas.user import UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post(
    "/login",
    response_model=TokenOut,
    summary="登录（JSON）",
    description="前端推荐方式：请求体为 application/json，包含 username 与 password，返回 JWT。",
)
async def login(payload: LoginRequest, db: DbSession) -> TokenOut:
    """JSON 登录。

    FastAPI 会根据 LoginRequest 的字段生成 JSON Schema；缺少 username/password 时
    返回统一的 422 VALIDATION_ERROR，而不是 401 或 500。
    """
    return await auth_service.login(db, payload.username, payload.password)


@router.post(
    "/login/form",
    response_model=TokenOut,
    summary="登录（OAuth2 表单）",
    description=(
        "标准 OAuth2 password flow（application/x-www-form-urlencoded），"
        "仅供 Swagger Authorize 使用；前端请使用 POST /api/v1/auth/login。"
    ),
)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenOut:
    return await auth_service.login(db, form.username, form.password)


@router.post(
    "/login/json",
    response_model=TokenOut,
    summary="登录（JSON 兼容旧路径）",
    description="兼容旧版前端路径，新前端请直接使用 POST /api/v1/auth/login。",
    deprecated=True,
)
async def login_json(payload: LoginRequest, db: DbSession) -> TokenOut:
    return await auth_service.login(db, payload.username, payload.password)


@router.get("/me", response_model=UserOut, summary="当前登录用户信息")
async def read_current_user(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
