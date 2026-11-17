"""认证相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.user import UserOut


class LoginRequest(BaseModel):
    """JSON 登录参数（表单登录由 OAuth2PasswordRequestForm 解析）。"""

    username: str = Field(..., min_length=1, max_length=50, description="登录账号")
    password: str = Field(..., min_length=1, max_length=128, description="登录密码")


class TokenOut(BaseModel):
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="有效期（秒）")
    user: UserOut = Field(..., description="当前登录用户信息")
