"""认证接口。"""

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
    summary="登录（OAuth2 表单）",
    description="标准 OAuth2 password flow，供 Swagger 授权按钮与前端表单登录使用。",
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenOut:
    return await auth_service.login(db, form.username, form.password)


@router.post(
    "/login/json",
    response_model=TokenOut,
    summary="登录（JSON）",
    description="供 Vue 等前端以 application/json 方式登录，返回同样的 JWT。",
)
async def login_json(payload: LoginRequest, db: DbSession) -> TokenOut:
    return await auth_service.login(db, payload.username, payload.password)


@router.get("/me", response_model=UserOut, summary="当前登录用户信息")
async def read_current_user(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
