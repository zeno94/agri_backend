# 农机配件进销存 ERP 后端

> 企业级农机配件进销存后端：FastAPI + SQLAlchemy 2.0（异步）+ MySQL 8.0 + Redis + JWT + Alembic + Docker。

覆盖「员工/老板登录 → 配件主数据 → 采购入库 → 销售出库（防超卖） → 库存流水 → 库存预警 → 老板看板」完整业务闭环。全部接口自动生成 OpenAPI 文档，可直接对接 Vue 管理端。

---

## 一、快速开始

### 方式一：Docker Compose 一键启动（推荐）

依赖：Docker 24+、Docker Compose v2。

```bash
# 1. 准备环境变量（仓库内已含可直接运行的 .env；生产环境务必替换 SECRET_KEY）
cp .env.example .env

# 2. 构建并启动 MySQL 8.0 + Redis 7 + API
docker compose up -d --build

# 3. 查看启动日志（首次会自动执行 Alembic 迁移并初始化基础数据）
docker compose logs -f api
```

启动完成后：

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| API 文档（Swagger） | <http://127.0.0.1:8000/docs> | 可直接 Authorize 调试 |
| API 文档（ReDoc） | <http://127.0.0.1:8000/redoc> | 只读文档 |
| 健康检查 | <http://127.0.0.1:8000/health> | 存活探针 |
| 就绪检查 | <http://127.0.0.1:8000/ready> | 数据库 + Redis 状态 |
| MySQL | `127.0.0.1:3306` | 库 `agri_erp`，账号 `erp / erp_password` |
| Redis | `127.0.0.1:6379` | 库 0 |

默认账号（来自 `.env`，上线前必须修改）：

| 角色 | 账号 | 密码 | 权限 |
| --- | --- | --- | --- |
| 老板 boss | `admin` | `Boss@123456` | 全部接口 + 经营看板 |
| 员工 employee | `staff` | `Staff@123456` | 业务接口，无看板权限 |

> 若连接的是旧数据库且 `admin` 已存在，`init_db` 出于安全考虑只跳过、不会覆盖密码。
> 忘记密码或登录返回 `INVALID_CREDENTIALS` 时，使用 `scripts.reset_password` 重置（见常见问题）。

容器入口按顺序执行：等待 MySQL → `alembic upgrade head` → 幂等初始化账号/示例数据 → Uvicorn 多 worker 启动。

### 方式二：本地开发（Docker 只跑基础设施）

```bash
# 1. 只启动 MySQL 与 Redis
docker compose up -d mysql redis

# 2. 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. 配置（本地 .env 中的 DATABASE_URL 默认指向 127.0.0.1:3306）
cp .env.example .env
#    按需修改 SECRET_KEY / 数据库密码

# 4. 初始化数据库结构与基础数据
alembic upgrade head
python -m app.db.init_db

# 5. 启动开发服务器（热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

也可以使用 Makefile：

```bash
make install   # 安装依赖
make dev       # 热重载启动
make migrate   # 执行迁移
make seed      # 初始化数据
make test      # 运行测试
make schema-check   # 检查数据库缺表/缺列（dry-run）
make repair-schema  # 补建缺失的表/字段/索引
make up        # Docker Compose 全量启动
```

> 端口冲突时可为 Compose 指定宿主机端口：`MYSQL_PORT=3307 REDIS_PORT=6380 API_PORT=8001 docker compose up -d`。

---

## 二、功能与接口清单

统一前缀 `/api/v1`；除登录与探针外均需要 `Authorization: Bearer <token>`。

| 模块 | 方法与路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| 认证 | `POST /auth/login` | 公开 | JSON 登录（前端推荐），body `{"username": "...", "password": "..."}` |
| 认证 | `POST /auth/login/form` | 公开 | OAuth2 表单登录，仅供 Swagger Authorize |
| 认证 | `POST /auth/login/json` | 公开 | 兼容旧前端的 JSON 别名（已标记 deprecated） |
| 认证 | `GET /auth/me` | 登录 | 当前用户信息 |
| 配件 | `GET /parts` | 登录 | 分页、名称模糊搜索、分类筛选，Redis 缓存 5 分钟 |
| 配件 | `GET /parts/warning` | 登录 | `stock <= safe_stock` 的配件及建议补货量 |
| 配件 | `GET /parts/{id}` | 登录 | 配件详情 |
| 配件 | `POST /parts` | 登录 | 新增配件；初始库存自动写期初流水 |
| 配件 | `PUT /parts/{id}` | 登录 | 修改配件；库存变化自动写盘点流水 |
| 往来单位 | `GET /partners` | 登录 | 分页、类型筛选、名称搜索 |
| 往来单位 | `POST /partners` | 登录 | 新增供应商/客户 |
| 往来单位 | `GET /suppliers` | 登录 | 供应商下拉列表（前端兼容，等价 `partner_type=supplier`） |
| 往来单位 | `GET /customers` | 登录 | 客户下拉列表（前端兼容，等价 `partner_type=customer`） |
| 采购 | `POST /purchases/inbound` | 登录 | 采购入库（事务 + 行锁 + 库存流水） |
| 采购 | `GET /purchases` | 登录 | 采购单分页查询 |
| 销售 | `POST /sales/outbound` | 登录 | 销售出库（悲观锁防超卖，整单原子） |
| 销售 | `GET /sales` | 登录 | 销售单分页查询 |
| 看板 | `GET /dashboard` | **仅 boss** | 今日/本月销售额、单据数、销量 Top 5 |
| 库存 | `GET /inventory/logs` | 登录 | 库存流水分页查询（按配件/类型筛选） |
| 系统 | `GET /health`、`GET /ready` | 公开 | 存活 / 就绪探针 |

> 请求格式约定：所有业务写接口（POST/PUT）统一接收 `application/json`；唯一例外是 Swagger 专用的 `/auth/login/form`，使用 `application/x-www-form-urlencoded`。

> 现有 Vue 前端兼容字段：配件列表额外接受 `page_size`（≤1000），新增配件接受 `price`；采购/销售接受 `supplier_id` / `customer_id` 与明细 `unit_price`；销售单还支持顶层 `part_id` + `quantity` 的单条格式。规范字段仍为 `size` / `sale_price` / `partner_id` / `items` / `price`。

> 路由顺序细节：`/parts/warning` 必须声明在 `/parts/{part_id}` 之前，代码中已按此顺序注册。

---

## 三、目录结构

```text
agri_backend/
├── app/
│   ├── main.py                     # FastAPI 入口：lifespan、CORS、中间件、异常处理、探针
│   ├── api/
│   │   ├── deps.py                 # DB/Redis 依赖、JWT 当前用户、boss 角色校验
│   │   └── v1/
│   │       ├── router.py           # v1 路由聚合
│   │       └── endpoints/          # auth / parts / partners / business_partners / purchases / sales / dashboard / inventory
│   ├── core/
│   │   ├── config.py               # pydantic-settings 配置中心
│   │   ├── security.py             # bcrypt 密码哈希、JWT 签发与校验
│   │   ├── exceptions.py           # AppError + 全局异常处理器
│   │   ├── redis.py                # Redis 连接管理与降级
│   │   ├── cache.py                # 配件列表缓存键 / 读写 / 版本失效
│   │   ├── middleware.py           # X-Request-ID + 访问日志
│   │   ├── logging.py              # 统一日志格式
│   │   └── money.py                # Decimal 金额规整、业务单号
│   ├── db/
│   │   ├── base.py                 # DeclarativeBase、命名约定、UTC 时间混入
│   │   ├── session.py              # 异步引擎、Session 工厂、健康检查
│   │   ├── schema.py               # 启动结构预检（缺表/缺列时 fail-fast）
│   │   └── init_db.py              # 幂等初始化账号、往来单位、示例配件
│   ├── models/                     # 8 张表：users/partners/parts/purchase_*/sale_*/inventory_logs
│   ├── schemas/                    # Pydantic V2 请求/响应模型
│   ├── crud/                       # 纯数据访问：查询、分页、行锁、聚合
│   └── services/                   # 业务编排：事务、库存、缓存失效、DTO 组装
├── migrations/                     # Alembic 异步迁移（0001_initial_schema.py）
├── scripts/
│   ├── entrypoint.sh               # 容器启动脚本
│   ├── wait_for_db.py              # 等待 MySQL 就绪
│   ├── repair_schema.py            # 旧库补列/补索引（只增不减）
│   └── reset_password.py           # 重置/创建账号密码（兼容旧哈希）
├── tests/                          # pytest：认证/配件/缓存/采购/销售/看板
├── Dockerfile
├── docker-compose.yml              # MySQL 8.0 + Redis 7 + API
├── requirements.txt
├── requirements-dev.txt
├── alembic.ini
├── pyproject.toml                  # pytest / ruff 配置
├── Makefile
├── .env / .env.example
└── README.md
```

分层规则：

```text
HTTP → Router（参数校验 / 鉴权） → Service（事务 / 业务规则） → CRUD（SQL） → Model → MySQL
                                      ↘ Redis（缓存加速，可降级）
```

- `api` 不写 SQL、不做业务判断；
- `services` 是唯一的事务边界，负责 commit / rollback；
- `crud` 只取数或写对象，不提交事务；
- 所有响应由 Pydantic V2 Schema 约束，OpenAPI 文档即契约。

---

## 四、核心业务实现

### 1. JWT 鉴权与 RBAC

- 密码：先 `SHA-256 + Base64` 预处理，再 bcrypt（12 轮），规避 bcrypt 72 字节截断；登录在异步场景下通过线程池执行哈希，避免阻塞事件循环。
- 用户不存在时也执行一次 bcrypt 校验，抹平响应时间差，防止账号枚举。
- JWT HS256，包含 `sub / username / role / type / iat / nbf / exp / jti`，默认 12 小时。
- 每次请求都从数据库加载用户角色（而不是信任 Token 里的 role），角色变更立即生效；`/dashboard` 通过 `get_current_boss` 做 RBAC。
- 前端使用 JSON 登录 `/api/v1/auth/login`；Swagger 的 OAuth2PasswordBearer `tokenUrl` 指向表单端点 `/api/v1/auth/login/form`，Authorize 仍可直接调试。

### 2. 销售出库防超卖（本项目的核心）

```text
① 校验客户
② 按 part_id 升序 SELECT ... FOR UPDATE 锁定全部配件行
③ 先校验所有明细库存，有一条不足即抛 409 并 rollback
④ 全部充足后才统一扣减库存、写 SaleItem、写 InventoryLog(out, 负数)
⑤ 汇总金额，SaleOrder.status = completed，一次 commit
```

关键代码（`app/services/sale.py`、`app/crud/part.py`）：

```python
# 固定加锁顺序，避免多单互相持锁形成死锁
parts = await crud_part.lock_parts_by_ids(db, [item.part_id for item in payload.items])

shortages = [
    {"part_id": item.part_id, "part_name": parts[item.part_id].name,
     "requested": item.quantity, "available": parts[item.part_id].stock}
    for item in payload.items
    if parts[item.part_id].stock < item.quantity
]
if shortages:
    raise AppError("INSUFFICIENT_STOCK", "库存不足，销售单已回滚", 409, detail={"items": shortages})
```

```python
stmt = (
    select(Part)
    .where(Part.id.in_(sorted(set(part_ids))))
    .order_by(Part.id)
    .with_for_update()   # SELECT ... FOR UPDATE
)
```

并发语义：InnoDB 行锁会阻塞其他事务对同一配件的锁定读/更新，直到当前事务 commit/rollback。由于「校验 + 扣减」都在锁内完成，不存在「查的时候够、扣的时候不够」的超卖窗口。

**真实 MySQL 并发验证结果**：库存 10 件，10 个并发请求各购买 3 件 → 恰好 3 单成功、7 单返回 409，最终库存 1，库存流水链路 `10 → 7 → 4 → 1` 完全一致。

异常路径（`except Exception`）统一 `await db.rollback()`：库存不足时不会产生销售单、明细或流水，也不会出现部分扣减。

### 3. 采购入库事务

- 同样先按 `part_id` 升序加锁，防止采购与销售并发时丢失更新；
- 逐条 `stock += quantity`，写采购明细与 `InventoryLog(change_type=in, change_qty>0)`；
- 单据创建时直接置为 `completed`，金额由明细汇总并规整到分；
- 任一配件不存在或任一步失败，整单回滚。

### 4. Redis 列表缓存

```text
erp:parts:cache_version                    # 缓存版本号（INCR 即失效）
erp:parts:list:v{version}:{fingerprint}    # 列表缓存，TTL 300s
```

- 先读 Redis，命中直接返回；未命中查 MySQL 并回填；
- 任何写操作（新增/修改配件、采购入库、销售出库）都会对版本号 `INCR`，旧缓存不再被读取，随 TTL 自然回收，避免高并发下 `SCAN` 全量删除；
- Redis 不可用时**自动降级**为直连数据库，只记录 WARN，核心交易不受影响；启动日志会明确提示；
- 缓存内容为完整分页响应 JSON（Decimal 以字符串保存，避免精度丢失）；反序列化失败自动回源。

### 5. 老板看板

- 销售额：`func.sum(SaleOrder.total_amount)`，只统计 `completed`；
- Top 5：`SELECT part_id, part_name, SUM(quantity) ... GROUP BY part_id, part_name ORDER BY SUM(quantity) DESC LIMIT 5`；
- **时区口径**：数据库存 UTC，统计时按 `Asia/Shanghai` 计算自然日/自然月边界，再转 UTC 查询，避免「今日」在跨时区/跨零点时算错；
- 仅 boss 可访问，员工返回 403 `FORBIDDEN`。

### 6. 库存流水与审计

`inventory_logs` 记录 `change_type（in/out/check）`、带符号 `change_qty`、变动前后库存、操作人、备注（含业务单号）与时间。任何库存变化都必须有流水：采购、销售、配件初始库存、资料修改导致的库存调整（`check`）。

### 7. 统一响应与可观测性

成功响应直接返回业务数据；分页统一：

```json
{"items": [], "total": 0, "page": 1, "size": 20, "pages": 0}
```

失败统一：

```json
{"code": "INSUFFICIENT_STOCK", "message": "库存不足，销售单已回滚", "detail": {"items": []}}
```

所有请求生成 `X-Request-ID` 并贯穿访问日志；金额使用 Decimal，JSON 中序列化为字符串（如 `"25.00"`），时间统一输出带 `+00:00` 的 ISO 8601。

---

## 五、数据库设计

### 表结构

| 表 | 关键字段 | 约束/索引 |
| --- | --- | --- |
| `users` | id, username, password_hash, role, is_active | username 唯一；role CHECK(boss/employee) |
| `partners` | id, name, type, phone | type CHECK(supplier/customer)；name 索引 |
| `parts` | id, name, model, category, brand, stock, safe_stock, purchase_price, sale_price | 库存/价格非负 CHECK；name/category/brand 索引 |
| `purchase_orders` | id, order_no, partner_id, total_amount, status, operator_id, remark | order_no 唯一；partner/operator 外键 |
| `purchase_items` | id, order_id, part_id, quantity, price | quantity>0；order_id 级联删除 |
| `sale_orders` | 同 purchase_orders | 同上 |
| `sale_items` | 同 purchase_items | 同上 |
| `inventory_logs` | id, part_id, change_type, change_qty, before_stock, after_stock, operator_id, remark | (part_id, created_at) 复合索引 |

主键使用 BIGINT（SQLite 测试自动降级为 INTEGER），字符集 utf8mb4。金额 `DECIMAL(12,2) / (14,2)`，全部由应用层 Decimal 计算，不使用浮点。

### ER 关系

```mermaid
erDiagram
    USERS ||--o{ PURCHASE_ORDERS : operates
    USERS ||--o{ SALE_ORDERS : operates
    USERS ||--o{ INVENTORY_LOGS : operates
    PARTNERS ||--o{ PURCHASE_ORDERS : supplier
    PARTNERS ||--o{ SALE_ORDERS : customer
    PURCHASE_ORDERS ||--|{ PURCHASE_ITEMS : contains
    SALE_ORDERS ||--|{ SALE_ITEMS : contains
    PARTS ||--o{ PURCHASE_ITEMS : referenced
    PARTS ||--o{ SALE_ITEMS : referenced
    PARTS ||--o{ INVENTORY_LOGS : logs
```

---

## 六、配置说明

配置来源优先级：环境变量 > `.env` > 代码默认值。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | development / test / production |
| `DEBUG` | `false` | 调试模式 |
| `SECRET_KEY` | 占位值 | JWT 密钥，至少 32 位；生产必须替换 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Token 有效期（分钟） |
| `BCRYPT_ROUNDS` | `12` | bcrypt 成本因子 |
| `DATABASE_URL` | `mysql+aiomysql://erp:...@127.0.0.1:3306/agri_erp?charset=utf8mb4` | 异步 MySQL DSN |
| `DB_ECHO` | `false` | 打印 SQL |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `20` | 连接池 |
| `AUTO_CREATE_TABLES` | `false` | 仅本地开发；生产用 Alembic |
| `SCHEMA_CHECK_ON_STARTUP` | `true` | 启动时校验表/列，结构漂移直接 fail-fast |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis DSN |
| `CACHE_TTL_SECONDS` | `300` | 配件列表缓存 TTL |
| `CORS_ORIGINS` | `*` | 允许来源，逗号分隔；`*` 为全部 |
| `TIMEZONE` | `Asia/Shanghai` | 看板统计时区 |
| `SEED_BOSS_USERNAME` / `SEED_BOSS_PASSWORD` | `admin` / `Boss@123456` | 初始化老板账号 |
| `SEED_EMPLOYEE_USERNAME` / `SEED_EMPLOYEE_PASSWORD` | `staff` / `Staff@123456` | 初始化员工账号 |

CORS 说明：`allow_origins=*` 时使用 Bearer Token（非 Cookie），因此 `allow_credentials=False`，符合浏览器规范，Vue 前端可直接跨域调用。生产环境建议通过 `CORS_ORIGINS` 收敛为具体域名。

---

## 七、接口调用示例

### 1. 登录并保存 Token

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Boss@123456"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "$TOKEN"
```

前端 axios / fetch 直接提交 JSON：

```js
const { data } = await axios.post('/api/v1/auth/login', {
  username: 'admin',
  password: 'Boss@123456',
})
localStorage.setItem('token', data.access_token)
```

> 只有 Swagger 的 Authorize 使用表单端点 `/auth/login/form`；旧路径 `/auth/login/json` 保留兼容，新代码请使用 `/auth/login`。

### 2. 配件分页 / 搜索 / 分类筛选

```bash
curl -G http://127.0.0.1:8000/api/v1/parts \
  --data-urlencode 'page=1' \
  --data-urlencode 'size=10' \
  --data-urlencode 'name=滤清' \
  --data-urlencode 'category=滤清器' \
  -H "Authorization: Bearer $TOKEN"
```

响应示例：

```json
{
  "items": [
    {
      "id": 1,
      "name": "柴油滤清器",
      "model": "4L88",
      "category": "滤清器",
      "brand": "潍柴",
      "stock": 50,
      "safe_stock": 20,
      "purchase_price": "12.50",
      "sale_price": "25.00",
      "created_at": "2026-11-17T09:15:00+00:00",
      "updated_at": "2026-11-17T09:15:00+00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1
}
```

### 3. 新增配件

```bash
curl -X POST http://127.0.0.1:8000/api/v1/parts \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "柴油滤清器",
    "model": "4L88",
    "category": "滤清器",
    "brand": "潍柴",
    "stock": 10,
    "safe_stock": 5,
    "purchase_price": "12.50",
    "sale_price": "25.00"
  }'
```

### 4. 采购入库

先从 `GET /api/v1/partners?size=50` 获取供应商与客户 ID。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/purchases/inbound \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "partner_id": 1,
    "items": [
      {"part_id": 1, "quantity": 20, "price": "12.00"},
      {"part_id": 2, "quantity": 10}
    ],
    "remark": "11 月补货"
  }'
```

`price` 可省略：采购单取配件的 `purchase_price`，销售单取 `sale_price`。

### 5. 销售出库（含库存不足场景）

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sales/outbound \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "partner_id": 3,
    "items": [{"part_id": 1, "quantity": 5}]
  }'
```

库存不足时返回 `409`：

```json
{
  "code": "INSUFFICIENT_STOCK",
  "message": "库存不足，销售单已回滚",
  "detail": {
    "items": [
      {"part_id": 1, "part_name": "柴油滤清器", "requested": 500, "available": 30}
    ]
  }
}
```

### 6. 库存预警

```bash
curl http://127.0.0.1:8000/api/v1/parts/warning \
  -H "Authorization: Bearer $TOKEN"
```

### 7. 老板看板（仅 boss）

```bash
curl http://127.0.0.1:8000/api/v1/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "today_sales_amount": "211.00",
  "month_sales_amount": "211.00",
  "today_order_count": 2,
  "month_order_count": 2,
  "top_parts": [
    {"part_id": 1, "part_name": "柴油滤清器", "quantity": 3},
    {"part_id": 5, "part_name": "植保机喷头", "quantity": 2}
  ],
  "generated_at": "2026-11-17T09:20:00+00:00"
}
```

### 8. 库存流水

```bash
curl -G http://127.0.0.1:8000/api/v1/inventory/logs \
  --data-urlencode 'part_id=1' \
  --data-urlencode 'change_type=out' \
  -H "Authorization: Bearer $TOKEN"
```

---

## 八、数据库迁移

```bash
# 升级到最新版本
alembic upgrade head

# 查看当前版本
alembic current

# 回滚一个版本
alembic downgrade -1

# 修改模型后生成新迁移（生成后请人工 review）
alembic revision --autogenerate -m "add xxx"

# 检查模型与数据库是否存在漂移
alembic check
```

初始迁移 `migrations/versions/0001_initial_schema.py` 已包含全部表、索引、CHECK 与外键。容器启动时自动执行迁移，**生产环境请关闭 `AUTO_CREATE_TABLES`**，统一走 Alembic。

### 旧数据库 / 旧数据卷修复（保留数据）

如果数据库不是由当前 Alembic 迁移创建的（旧版本代码、手写 SQL、旧 Docker 数据卷），
常见报错：

```text
sqlalchemy.exc.OperationalError: (pymysql.err.OperationalError)
(1054, "Unknown column 'users.is_active' in 'field list'")
```

注意：`AUTO_CREATE_TABLES` / `create_all` 只会创建缺失的表，**不会给已有表补列**。
使用只增不减的结构修复工具：

```bash
# 1. 先 dry-run，确认会补哪些列/索引
python -m scripts.repair_schema

# 2. 确认后执行；旧库没有 alembic_version 时顺带标记 head
python -m scripts.repair_schema --apply --stamp-head
```

Docker 环境（会使用容器内的 DATABASE_URL）：

```bash
docker compose run --rm --entrypoint python api \
  -m scripts.repair_schema --apply --stamp-head
docker compose up -d
```

脚本只做 `ADD COLUMN / ADD INDEX / CREATE TABLE`，不删除列、不改类型；执行前请备份。
补列规则：可空列直接加；NOT NULL 列先可空、回填历史行、再改 NOT NULL；
`order_no` 回填为 `PO-LEGACY-<id>` / `SO-LEGACY-<id>`，库存流水按当前库存反推前后值。

如果没有任何历史数据，直接重建更干净：

```bash
docker compose down -v          # 会删除 MySQL 数据卷
docker compose up -d --build
```

否则也可手工执行 `ALTER TABLE users ADD COLUMN is_active ...`，但通常旧库还会缺
`created_at`、`updated_at`、`order_no`、`before_stock` 等列，建议直接用修复脚本。

---

## 九、测试

```bash
pytest                 # 36 个用例
ruff check app tests   # 静态检查
```

测试使用临时 SQLite + fakeredis + FastAPI 依赖覆盖，不依赖本机 MySQL/Redis，覆盖：

- 登录契约：JSON 请求体、参数校验、Swagger 表单端点、旧 JSON 路径兼容；
- 数据库结构预检：完整结构无漂移、缺列/缺表可被检测；
- 登录成功/失败/未带 Token/员工越权；
- 配件分页、模糊搜索、分类筛选、缓存命中与版本失效；
- 新增/修改配件的库存流水、库存预警、参数校验；
- 采购入库（库存、金额、流水、供应商校验、缺配件回滚）；
- 销售出库（默认单价、扣减、超卖 409、多明细原子性、重复配件校验）；
- 看板金额、单量、Top 5 排序与权限；
- 现有 Vue 前端契约：`/suppliers`、`/customers`、`page_size`、`price`、`supplier_id`/`unit_price`、销售单条 payload。

此外已使用真实 MySQL（InnoDB）做过并发验证：10 个并发销售请求争抢 10 件库存，恰好成功 3 单、库存归 1，流水前后值连续一致。

---

## 十、生产部署清单

- [ ] 替换 `SECRET_KEY`、MySQL/Redis 密码，`.env` 不入库；
- [ ] `ENVIRONMENT=production`、`DEBUG=false`、`AUTO_CREATE_TABLES=false`；
- [ ] `CORS_ORIGINS` 收敛到实际前端域名；
- [ ] 前置 Nginx/负载均衡 + HTTPS，限制请求体大小与超时；
- [ ] MySQL 8.0 设置 `default-time-zone=+00:00`，开启慢查询与备份；
- [ ] Redis 使用 `volatile-lru`（只淘汰带 TTL 的缓存键，保护版本号）或独立缓存实例；
- [ ] Uvicorn worker 数约为 CPU 核数，容器内存与连接池匹配；
- [ ] 网关层做登录限流/防爆破；如需主动下线 Token，可基于 `jti` 增加 Redis 黑名单；
- [ ] 对接日志平台，按 `X-Request-ID` 串联链路；监控 `/health`、`/ready` 与 5xx；
- [ ] 销售接口如需支持客户端重试，增加 `Idempotency-Key` 幂等键；
- [ ] 定期归档 `inventory_logs`、备份 `sale_orders/purchase_orders`。

---

## 十一、常见问题

**Q：登录或启动报 500 `Unknown column 'users.is_active' in 'field list'`？**

说明你连接的数据库结构比代码旧（不是登录格式问题）。`AUTO_CREATE_TABLES` 只建表，不会给已有表补列。
启动预检会直接提示缺失字段；按下面方式修复：

```bash
python -m scripts.repair_schema                    # 先看计划
python -m scripts.repair_schema --apply --stamp-head
```

```bash
# Docker 环境
docker compose run --rm --entrypoint python api \
  -m scripts.repair_schema --apply --stamp-head
docker compose up -d
```

脚本会补上 `users.is_active`、时间戳、`order_no`、库存流水快照列及索引。
没有历史数据时，直接 `docker compose down -v && docker compose up -d --build` 更干净。

**Q：登录返回 `INVALID_CREDENTIALS` / 用户名或密码错误？**

请求格式和数据库结构都正常，说明账号数据不匹配。常见原因：

- 旧库里的 `admin` 是其他系统/其他密码哈希方案创建的；
- `init_db` 只创建缺失账号，不会覆盖已存在账号的密码。

重置密码（推荐交互式输入，避免密码进入 shell history）：

```bash
python -m scripts.reset_password --username admin --activate
```

非交互环境或账号不存在时：

```bash
# 账号已存在：重置密码并启用
python -m scripts.reset_password --username admin --password 'Boss@123456' --activate

# 账号不存在：直接创建老板账号
python -m scripts.reset_password --username admin --password 'Boss@123456' --create --role boss
```

Docker 环境：

```bash
docker compose run --rm --entrypoint python api \
  -m scripts.reset_password --username admin --activate
```

重置成功后使用新密码登录。登录接口对“用户不存在”和“密码错误”返回相同的提示，是防止账号枚举的安全设计，不代表用户一定存在。

**Q：Docker 启动后 API 一直重启？**  
查看 `docker compose logs api`。常见原因是 MySQL 尚未健康（等待脚本会重试 60 次）或 `.env` 中 `DATABASE_URL` 被覆盖。Compose 已强制将 API 的数据库地址指向 `mysql:3306`。

**Q：本机 3306/6379/8000 被占用？**  
使用 `MYSQL_PORT=3307 REDIS_PORT=6380 API_PORT=8001 docker compose up -d`；如只启动基础设施，注意同步修改 `.env` 中的端口。

**Q：Vue 跨域失败？**  
默认 `CORS_ORIGINS=*`，已放开所有来源；若用 Cookie 需自行改为具体来源并调整 `allow_credentials`。本项目使用 Bearer Token，无需 Cookie。

**Q：接口返回 401？**  
Token 过期或未带 `Authorization: Bearer <token>`。重新登录即可；`code` 为 `TOKEN_EXPIRED` / `NOT_AUTHENTICATED` / `INVALID_TOKEN`。

**Q：Redis 挂了会影响下单吗？**  
不会。缓存读取/写入失败会被捕获并降级到数据库；但库存预警、列表性能会下降，建议监控 Redis 可用性。

**Q：金额为什么是字符串？**  
`Decimal` 在 JSON 中序列化为字符串（如 `"25.00"`），避免前端 JavaScript 浮点精度问题。前端展示/计算时使用 `Number(...)` 或后端新增汇总字段。

**Q：MySQL 8 的 `caching_sha2_password` 连接失败？**  
`requirements.txt` 已显式引入 `cryptography`，用于 aiomysql 的 RSA 公钥认证；同时 .env 中的 DSN 必须带 `charset=utf8mb4`。

**Q：为什么 `GET /parts/warning` 能匹配到？**  
它在路由注册时位于 `/parts/{part_id}` 之前，避免被动态路由吞掉。

---

## License

Proprietary / 内部项目使用。
