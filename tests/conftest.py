"""pytest 全局夹具。

测试环境说明：
- 使用临时 SQLite 文件 + aiosqlite，避免依赖本机 MySQL；
- 使用 fakeredis 验证缓存命中与失效逻辑；
- 通过 FastAPI dependency_overrides 注入测试会话与 Redis；
- 不触发 lifespan，因此不会去连接真实 MySQL / Redis。
"""

from __future__ import annotations

import os
from decimal import Decimal

# 必须在导入 app 之前设置，确保 Settings 单例读取到测试配置
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./_pytest_unused.db"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"  # 加速测试
os.environ["CACHE_TTL_SECONDS"] = "300"

import fakeredis.aioredis  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.redis import get_redis  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.module_defaults import DEFAULT_MODULES  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Customer, Module, Part, Supplier, User, UserModule  # noqa: E402
from app.models.enums import UserRole  # noqa: E402


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture
async def seed_data(session_factory):
    """基础主数据：老板、员工、供应商、客户、正常配件、低库存配件。"""
    async with session_factory() as session:
        boss = User(username="boss", password_hash=hash_password("Boss@123456"), role=UserRole.BOSS.value)
        employee = User(username="staff", password_hash=hash_password("Staff@123456"), role=UserRole.EMPLOYEE.value)
        supplier = Supplier(
            name="杞县丰农农机配件有限公司",
            phone="19903780102",
            address="杞县县城北环路",
            contact_person="李经理",
            main_categories=["传动带", "轴承"],
            delivery_days=1,
        )
        customer = Customer(
            name="王建军",
            phone="13803780001",
            city="开封市",
            county="杞县",
            town="邢口镇",
            village="冷屯村",
            customer_type="种粮户",
            main_crops=["小麦", "玉米"],
            tags=["核心客户"],
        )
        part = Part(
            name="柴油滤清器",
            model="4L88",
            category="滤清器",
            brand="潍柴",
            stock=10,
            safe_stock=5,
            purchase_price=Decimal("12.50"),
            sale_price=Decimal("25.00"),
        )
        low_part = Part(
            name="植保机喷头",
            model="AG-01",
            category="植保配件",
            brand="大疆",
            stock=2,
            safe_stock=10,
            purchase_price=Decimal("35.00"),
            sale_price=Decimal("68.00"),
        )
        session.add_all([boss, employee, supplier, customer, part, low_part])
        await session.flush()

        modules = []
        for data in DEFAULT_MODULES:
            module = Module(**data)
            session.add(module)
            modules.append(module)
        await session.flush()

        # 测试员工默认拥有全部非管理员模块，便于覆盖原有业务测试；
        # 模块隔离测试会单独创建/调整用户授权。
        for module in modules:
            if not module.is_admin_only:
                session.add(UserModule(user_id=employee.id, module_id=module.id))

        await session.commit()
        for obj in (boss, employee, supplier, customer, part, low_part):
            await session.refresh(obj)

        return {
            "boss_id": boss.id,
            "employee_id": employee.id,
            "supplier_id": supplier.id,
            "customer_id": customer.id,
            "part_id": part.id,
            "low_part_id": low_part.id,
            "module_ids": {m.code: m.id for m in modules},
        }


@pytest_asyncio.fixture
async def client(session_factory, fake_redis):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client

    app.dependency_overrides.clear()


async def _login(client: AsyncClient, username: str, password: str) -> dict[str, str]:
    # 前端统一使用 JSON 登录
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def boss_headers(client, seed_data):
    return await _login(client, "boss", "Boss@123456")


@pytest_asyncio.fixture
async def employee_headers(client, seed_data):
    return await _login(client, "staff", "Staff@123456")
