"""配置中心：所有环境相关参数集中在此，使用 pydantic-settings 从环境变量 / .env 加载。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仅用于本地开发的占位密钥，生产环境启动时会强制校验并拒绝
INSECURE_DEFAULT_SECRET_KEY = "dev-only-insecure-secret-key-please-change-in-production-0123456789"


class Settings(BaseSettings):
    """应用配置。

    优先级：环境变量 > .env 文件 > 代码默认值。
    变量名大小写不敏感，例如 ACCESS_TOKEN_EXPIRE_MINUTES 也可写作 access_token_expire_minutes。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用信息 ----------
    APP_NAME: str = "农机配件进销存 ERP 系统"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    TIMEZONE: str = "Asia/Shanghai"

    # ---------- JWT / 密码安全 ----------
    SECRET_KEY: str = INSECURE_DEFAULT_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=720, ge=1, le=60 * 24 * 30)
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=16)

    # ---------- MySQL ----------
    DATABASE_URL: str = "mysql+aiomysql://erp:erp_password@127.0.0.1:3306/agri_erp?charset=utf8mb4"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=200)
    DB_POOL_RECYCLE: int = Field(default=1800, ge=60)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1)
    # 本地开发便捷开关；生产环境必须置为 false，由 Alembic 管理表结构
    AUTO_CREATE_TABLES: bool = False
    # 启动时校验数据库表/列是否与模型一致；漂移则 fail-fast
    SCHEMA_CHECK_ON_STARTUP: bool = True

    # ---------- Redis ----------
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=1, le=500)
    REDIS_SOCKET_TIMEOUT: float = Field(default=3.0, gt=0)
    CACHE_TTL_SECONDS: int = Field(default=300, ge=1, le=86400)
    PARTS_CACHE_PREFIX: str = "erp:parts"

    # ---------- 幂等与令牌吊销 ----------
    # 幂等键：同一 Idempotency-Key 在 TTL 内只执行一次，重复请求回放首次结果
    IDEMPOTENCY_PREFIX: str = "erp:idem"
    IDEMPOTENCY_TTL_SECONDS: int = Field(default=86400, ge=60, le=60 * 60 * 24 * 7)
    # JWT 吊销：jti 黑名单（登出）与用户级签发时间水位（改密/停用）
    JWT_REVOCATION_PREFIX: str = "erp:jwt"

    # ---------- CORS ----------
    # "*" 表示允许所有来源；多个来源用英文逗号分隔，例如 "http://localhost:5173,http://127.0.0.1:5173"
    CORS_ORIGINS: str = "*"

    # ---------- 初始化账号（仅 app.db.init_db 使用）----------
    SEED_BOSS_USERNAME: str = "admin"
    SEED_BOSS_PASSWORD: str = "Boss@123456"
    SEED_EMPLOYEE_USERNAME: str = "staff"
    SEED_EMPLOYEE_PASSWORD: str = "Staff@123456"

    @field_validator("TIMEZONE")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:  # pragma: no cover - 配置错误时快速失败
            raise ValueError(f"无效的时区配置：{value}") from exc
        return value

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_length(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SECRET_KEY 长度至少为 32 个字符")
        return value

    @model_validator(mode="after")
    def _reject_insecure_production_secret(self) -> Settings:
        if self.is_production and self.SECRET_KEY == INSECURE_DEFAULT_SECRET_KEY:
            raise ValueError("生产环境必须通过 SECRET_KEY 环境变量配置强随机密钥")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins(self) -> list[str]:
        """将逗号分隔的配置解析为 CORS 中间件需要的列表。"""
        raw = self.CORS_ORIGINS.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)


@lru_cache
def get_settings() -> Settings:
    """进程内单例，避免重复解析 .env。"""
    return Settings()


settings = get_settings()
