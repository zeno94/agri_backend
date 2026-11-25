# 农机配件进销存 ERP 后端

> 企业级农机配件进销存后端：FastAPI + SQLAlchemy 2.0（异步）+ MySQL 8.0 + Redis + JWT + Alembic + Docker。

覆盖「管理员/普通用户登录 → 动态模块授权 → 配件主数据 → 采购入库 → 销售出库（防超卖） → 库存流水 → 库存预警 → 客户/供应商管理 → 经营报表」完整业务闭环。管理员可创建普通用户并分配功能模块，侧边栏与路由权限由后端返回的模块列表驱动。全部接口自动生成 OpenAPI 文档，可直接对接 Vue 管理端。

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
| 管理员 boss | `admin` | `Boss@123456` | 全部模块 + 用户管理 + 模块配置 |
| 普通用户 employee | 由管理员在「用户管理」创建 | 创建时设置 | 只显示管理员勾选的模块 |

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
#    若提示 alembic: command not found，说明虚拟环境未激活；
#    也可以直接用 .venv/bin/alembic upgrade head
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
| 认证 | `POST /auth/logout` | 登录 | 记录退出审计；JWT 无状态，不吊销已签发 Token |
| 配件 | `GET /parts` | 登录 | 分页、名称模糊搜索、分类筛选，Redis 缓存 5 分钟 |
| 配件 | `GET /parts/warning` | 登录 | `stock <= safe_stock` 的配件及建议补货量 |
| 配件 | `GET /parts/{id}` | 登录 | 配件详情 |
| 配件 | `POST /parts` | **仅 boss** | 新增配件；初始库存自动写期初流水 |
| 配件 | `PUT /parts/{id}` | **仅 boss** | 修改配件/价格/库存；库存变化自动写盘点流水 |
| 客户 | `GET /customers/options` | 登录 | 销售页客户下拉选项 |
| 客户 | `GET /customers` | 客户管理模块 | 分页、姓名/电话/乡镇筛选，带订单与消费统计 |
| 客户 | `GET /customers/{id}` | 客户管理模块 | 客户详情、消费统计、跟进记录、最近订单 |
| 客户 | `POST /customers` | 客户管理模块 | 新增客户档案 |
| 客户 | `PATCH /customers/{id}` | 客户管理模块 | 修改客户档案 |
| 客户 | `POST /customers/{id}/followups` | 客户管理模块 | 记一条客户跟进；method 为方式，支持电话/微信/到店/上门/其他及自定义 |
| 供应商 | `GET /suppliers/options` | 登录 | 采购页供应商下拉选项 |
| 供应商 | `GET /suppliers` | **仅 boss** | 分页、名称/电话/联系人搜索，带采购统计 |
| 供应商 | `POST /suppliers` | **仅 boss** | 新增本地供应商 |
| 供应商 | `PATCH /suppliers/{id}` | **仅 boss** | 修改供应商 |
| 用户 | `GET /users` | **仅 boss** | 用户列表与已分配模块 |
| 用户 | `POST /users` | **仅 boss** | 创建普通用户并分配模块 |
| 用户 | `PATCH /users/{id}` | **仅 boss** | 修改账号/启用停用 |
| 用户 | `PUT /users/{id}/modules` | **仅 boss** | 重新分配可用模块 |
| 用户 | `POST /users/{id}/reset-password` | **仅 boss** | 重置普通用户密码 |
| 功能模块 | `GET /modules` | **仅 boss** | 全部模块配置 |
| 功能模块 | `PUT /modules/{id}` | **仅 boss** | 改名/图标/排序/启用/管理员专属 |
| 采购 | `POST /purchases/inbound` | 登录 | 采购入库（事务 + 行锁 + 库存流水） |
| 采购 | `GET /purchases` | 登录 | 采购单分页查询 |
| 销售 | `POST /sales/outbound` | 登录 | 销售出库（悲观锁防超卖，整单原子） |
| 销售 | `GET /sales` | 登录 | 销售单分页查询；支持日期、客户、单号筛选，返回 `total_amount` 合计 |
| 报表 | `GET /dashboard/report` | **仅 boss** | 按日期区间统计销售/采购/毛利、排行、分类占比与趋势 |
| 看板 | `GET /dashboard` | **仅 boss** | 今日/本月销售额、单据数、销量 Top 5（兼容旧前端） |
| 库存 | `GET /inventory/logs` | 登录 | 库存流水分页查询（按配件/类型筛选） |
| 审计 | `GET /audit/logs` | 登录 | boss 查看全部；employee 仅本人；支持日期/动作/结果/账号筛选 |
| 审计 | `GET /audit/logs/{id}` | 登录 | boss 任意；employee 仅本人，越权返回 404 |
| 系统 | `GET /health`、`GET /ready` | 公开 | 存活 / 就绪探针 |

> 请求格式约定：所有业务写接口（POST/PUT）统一接收 `application/json`；唯一例外是 Swagger 专用的 `/auth/login/form`，使用 `application/x-www-form-urlencoded`。

> 采购/销售规范字段为 `supplier_id` / `customer_id`，不再使用 `partner_id`；为兼容旧客户端，请求仍接受 `partner_id` 别名。配件列表额外接受 `page_size`（≤1000），新增配件接受 `price`，明细接受 `unit_price`，销售单还支持顶层 `part_id` + `quantity` 的单条格式。

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
│   │       └── endpoints/          # auth / parts / customers / suppliers / users / modules / purchases / sales / dashboard / inventory / audit
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
│   │   └── init_db.py              # 幂等初始化管理员、模块、示例客户/供应商/配件
│   ├── models/                     # 13 张表：users/customers/suppliers/modules/user_modules/customer_followups/parts/purchase_*/sale_*/inventory_logs/audit_logs
│   ├── schemas/                    # Pydantic V2 请求/响应模型
│   ├── crud/                       # 纯数据访问：查询、分页、行锁、聚合
│   └── services/                   # 业务编排：事务、库存、缓存失效、DTO 组装
├── migrations/                     # Alembic 异步迁移（0001 初始表 / 0002 审计 / 0003 拆客户供应商 / 0004 模块权限 / 0005 客户市县 / 0006 恢复下次跟进 / 0007 删除数据库外键）
├── scripts/
│   ├── entrypoint.sh               # 容器启动脚本
│   ├── wait_for_db.py              # 等待 MySQL 就绪
│   ├── repair_schema.py            # 旧库补列/补索引（只增不减）
│   ├── reset_password.py           # 重置/创建账号密码（兼容旧哈希）
│   ├── user_admin.py               # 账号巡检：角色/状态/哈希类型/改角色
│   ├── generate_historical_sql.py  # 旧版历史数据生成器（已停用，仅参考）
│   ├── generate_partner_data.py    # 一次性重造 1,000 客户 + 23 本地供应商
│   └── reshape_customers.py        # 追加 76 户、市县地址、手机号、标签/作物重塑
├── sql/
│   ├── seed_2022_09_12_2026_10_01.sql  # 10MB+ 完整数据库快照（表结构+数据）
│   ├── seed_stats.json             # 数据规模/营收/毛利统计
│   └── DATA_SOURCES.md             # 价格来源、导入步骤、自检 SQL
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

### 5. 经营报表

- `/dashboard` 保留今日/本月概览，兼容旧前端；
- `/dashboard/report` 支持 `start_date` / `end_date`（业务时区自然日，含首尾），返回销售额、采购额、销售毛利、毛利率、客单价、件数、销售单数、采购单数；
- 排行：销售额 Top 5 配件、Top 5 客户、采购额 Top 5 供应商、分类销售占比；
- 趋势：区间不超过约一个季度按日，超过则按月；日期边界先按 `Asia/Shanghai` 计算再转 UTC；
- 销售额：`func.sum(SaleOrder.total_amount)`，只统计 `completed`；毛利按 `parts.purchase_price × sale_items.quantity` 估算，未扣房租/人工/运输/税费；
- 所有汇总在数据库侧聚合；仅管理员可访问，普通用户返回 403 `FORBIDDEN`。
- 前端看板页提供日期范围组件与近7天/近30天/近90天/本月/上月/今年/全部快捷区间；默认近90天。

### 6. 角色与动态模块权限

系统只有两种角色：

- `boss`：管理员，默认拥有全部模块，并独占用户管理、模块配置、供应商管理、经营报表。
- `employee`：普通用户，由管理员创建，只能看到管理员勾选的功能模块。

模块权限不是写死在前端菜单里，而是由 `modules` + `user_modules` 两张表驱动：

| 模块 code | 默认名称 | 默认权限 |
| --- | --- | --- |
| dashboard | 经营报表 | 管理员专属 |
| parts | 配件管理 | 可分配 |
| purchase | 采购入库 | 可分配 |
| sale | 销售出库 | 可分配 |
| sales | 销售记录 | 可分配 |
| customers | 客户管理 | 可分配 |
| suppliers | 供应商管理 | 管理员专属 |
| warning | 库存预警 | 可分配 |
| audit | 操作日志 | 可分配（普通用户只看自己） |
| users | 用户管理 | 管理员专属 |
| modules | 模块配置 | 管理员专属 |

- 每个请求由 `require_module(code)` 依赖校验，管理员直接放行，普通用户必须拥有启用中的模块；越权返回 403 `FORBIDDEN` 并写 `authz.denied` 审计。
- 前端 `/auth/login`、`/auth/me` 返回 `user.modules`；侧边栏按模块排序生成，路由 `meta.module` 做二次守卫。即使直接输入 URL，后端仍会 403。
- 管理员可在「模块配置」改名、换图标、调整排序、启用/停用；停用后普通用户立即失去入口，管理员仍可访问。
- 模块类型列：管理员专属显示“管理员”；可分配模块显示“管理员 + 业务员”。
- 管理员在「用户管理」创建普通用户、勾选模块、重置密码、启用/停用；管理员账号受保护，不能通过接口修改或停用。
- 敏感写操作仍单独限制：配件新增/修改、供应商新增/修改、用户/模块配置仅管理员；客户管理由 `customers` 模块控制。
- 普通用户不能自行注册、不能自行开通模块；所有账号和授权均由管理员分配。
- 账号停用（`is_active=false`）与角色无关，任何角色都会在鉴权阶段被拒绝。
- 采购单/销售单/库存流水记录 `operator_id`，可以追溯具体操作人；客户/供应商/模块/用户变更均写审计日志。

### 7. 库存流水与操作审计

`inventory_logs` 记录 `change_type（in/out/check）`、带符号 `change_qty`、变动前后库存、操作人、备注（含业务单号）与时间。任何库存变化都必须有流水：采购、销售、配件初始库存、资料修改导致的库存调整（`check`）。

**操作审计（`audit_logs`）**：

- 记录登录成功/失败、退出、配件新增/修改、客户/供应商/用户/模块变更、采购入库、销售出库、客户跟进、看板查看、日志查看；
- 字段包含操作人快照（ID/账号/角色）、动作、模块、资源、HTTP 方法/路径、状态码、成功标记、错误码、脱敏明细、IP、UA、request_id、耗时、UTC 时间；
- 审计只追加，不提供更新/删除接口；写入失败只记录应用错误，不阻断业务响应；
- 明细递归脱敏 `password/token/secret/authorization/cookie` 等键，登录日志不记录密码；
- `boss` 可查全部日志并按账号筛选；`employee` 只能查本人，尝试筛选他人或读取他人日志详情会被拒绝；
- 前端“操作日志”页面复用同一接口：管理员看全量，普通用户看自己的操作轨迹。

### 8. 统一响应与可观测性

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
| `customers` | id, name, phone, city, county, town, village, customer_type, acreage, main_crops(JSON), tags(JSON), note, next_follow_up_at, is_active | 姓名/电话/地区索引；订单按 customer_id 逻辑关联 |
| `suppliers` | id, name, phone, address, contact_person, main_categories(JSON), delivery_days, payment_terms, note, is_active | 姓名/电话索引；采购按 supplier_id 逻辑关联 |
| `customer_followups` | id, customer_id, operator_id, method, content, next_follow_up_at, created_at | customer/operator 逻辑关联；按客户+时间索引 |
| `modules` | id, code, name, path, icon, description, sort_order, is_active, is_admin_only | code/path 唯一；导航排序 |
| `user_modules` | user_id, module_id | 联合主键；用户/模块逻辑关联 |
| `parts` | id, name, model, category, brand, stock, safe_stock, purchase_price, sale_price | 库存/价格非负 CHECK；name/category/brand 索引 |
| `purchase_orders` | id, order_no, supplier_id, total_amount, status, operator_id, remark | order_no 唯一；supplier/operator 逻辑关联 |
| `purchase_items` | id, order_id, part_id, quantity, price | quantity>0；order_id 级联删除 |
| `sale_orders` | id, order_no, customer_id, total_amount, status, operator_id, remark | order_no 唯一；customer/operator 逻辑关联 |
| `sale_items` | id, order_id, part_id, quantity, price | quantity>0；order_id 级联删除 |
| `inventory_logs` | id, part_id, change_type, change_qty, before_stock, after_stock, operator_id, remark | (part_id, created_at) 复合索引 |
| `audit_logs` | id, user_id, username, role, action, module, resource_type/id, method, path, status_code, success, error_code, detail(JSON), ip, user_agent, request_id, duration_ms, created_at | 只追加；(user_id, created_at)、(action, created_at) 索引 |

主键使用 BIGINT（SQLite 测试自动降级为 INTEGER），字符集 utf8mb4。金额 `DECIMAL(12,2) / (14,2)`，全部由应用层 Decimal 计算，不使用浮点。

### ER 关系

```mermaid
erDiagram
    USERS ||--o{ PURCHASE_ORDERS : operates
    USERS ||--o{ SALE_ORDERS : operates
    USERS ||--o{ INVENTORY_LOGS : operates
    USERS ||--o{ AUDIT_LOGS : writes
    CUSTOMERS ||--o{ SALE_ORDERS : places
    CUSTOMERS ||--o{ CUSTOMER_FOLLOWUPS : has
    SUPPLIERS ||--o{ PURCHASE_ORDERS : supplies
    USERS ||--o{ USER_MODULES : granted
    MODULES ||--o{ USER_MODULES : contains
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
| `SEED_BOSS_USERNAME` / `SEED_BOSS_PASSWORD` | `admin` / `Boss@123456` | 初始化管理员账号 |
| `SEED_EMPLOYEE_USERNAME` / `SEED_EMPLOYEE_PASSWORD` | `staff` / `Staff@123456` | `init_db` 可选演示员工；实际账号以管理员创建为准 |

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

先从 `GET /api/v1/suppliers/options` / `GET /api/v1/customers/options` 获取供应商/客户 ID。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/purchases/inbound \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "supplier_id": 101,
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
    "customer_id": 1001,
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

### 7. 经营报表（仅 boss）

```bash
# 指定日期区间（含首尾，业务时区）
curl -G http://127.0.0.1:8000/api/v1/dashboard/report \
  --data-urlencode 'start_date=2026-09-01' \
  --data-urlencode 'end_date=2026-10-01' \
  -H "Authorization: Bearer $TOKEN"

# 兼容旧前端：今日/本月概览
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

初始迁移 `0001` 包含全部表、索引、CHECK 与历史外键；迁移 `0007_drop_foreign_keys` 会删除所有数据库外键。最终结构保留 id 列和索引，表间关联由应用层维护。容器启动时自动执行迁移，**生产环境请关闭 `AUTO_CREATE_TABLES`**，统一走 Alembic。

### 历史演示数据（2022-09-12 ~ 2026-10-01）

项目提供了一套完整数据库快照，包含表结构、模块、客户/供应商、订单、流水和审计：

- SQL：[`sql/seed_2022_09_12_2026_10_01.sql`](sql/seed_2022_09_12_2026_10_01.sql)
- 价格来源与导入说明：[`sql/DATA_SOURCES.md`](sql/DATA_SOURCES.md)
- 统计：[`sql/seed_stats.json`](sql/seed_stats.json)

```bash
# 1. 先备份目标库（快照会 DROP 并重建全部表）
mysqldump -u root -p agri_erp > backup_before_seed.sql

# 2. 直接导入空库/演示库；不要再先跑 alembic
mysql -u erp -p --default-character-set=utf8mb4 agri_erp \
  < sql/seed_2022_09_12_2026_10_01.sql
```

快照行为：

- 文件自带 `alembic_version=0007`、全部表结构和数据；导入空库即可直接运行，不需要先 `alembic upgrade`；
- 会 `DROP` 并重建表，请只用于本地/演示库，不要用于生产库；
- 保留当前演示账号 `admin / Boss@123456`，普通用户 `zhujunjie`、`zhaohua` 及其模块授权；
- 数据规模：126 个 SKU、23 个本地供应商、1,076 个农户客户、193 张采购单、8,820 张销售单、14,451 条销售明细、15,349 条库存流水、16,453 条审计；
- 销售额 2,204,420 元，按参考成本毛利 679,173 元（30.81%），月均约 44,088 元；
- 供应商全部在杞县县城/开封市区/通许/尉氏/兰考/睢县，镇级 0 个；公司制为主，不再使用“批发部/经营部”；
- 客户为 1,076 个农户：968 个完整姓名、65 个“姓+先生/女士”、43 个“未知”；标签只有“核心客户 / 其他”（169 / 907），主要作物统一为“其他”，客户类型统一为“其他”，种植面积统一为 0；
- 新增 76 户由 [`scripts/reshape_customers.py`](scripts/reshape_customers.py) 追加，其中 6 户亲戚标为核心；已有客户按购买次数 >=15 或金额 >=5000 标核心；
- 客户地址拆成市 / 县区 / 乡镇 / 村；客户手机号按开封 0378 号段随机生成，199 开头仅 40 个；供应商电话为 0371/0370 座机或 0378 手机，均随机且唯一；
- 下次跟进字段已恢复，核心客户有跟进日期；客户列表按最近购买时间倒序排列。
- 销售金额按整数元记，60% 的销售单以 0 结尾（抹零），约 1% 以 9 结尾，其余 1~8 随机分布；采购金额和成本仍保留小数；
- 春节闭店：三十、初一、初二、初三、初四不产生销售、采购、库存和审计交易记录，相关单据顺延到初五至初九；销售和采购交易时间均覆盖本地 07:35~20:13；
- 客户姓名、供应商字号和电话均为虚构演示数据，电话不是真实联系方式。

数据口径：

- `parts.purchase_price` = 参考进货价，`parts.sale_price` = 建议零售价；
- `sale_items.price` = 实际成交单价（整数元），`sale_orders.total_amount` = 整单实收（整数元）；
- 所有销售明细实际成交价均不低于商品参考成本；整数化和抹零后，成交价约为建议零售价的 82%~117%；
- 导入后请清理旧缓存或重启 API：`redis-cli DEL erp:parts:cache_version`。

> 注意：数据截止 **2026-10-01**，当前日期是 **2026-11-24**。
> 旧接口 `/dashboard` 的“今日/本月销售额”仍会显示 0；新报表页默认“近 90 天”，可看到 8 月下旬至 10 月初的数据。
> 想看全部历史，在看板选择“全部”，或直接使用销售记录页/`/sales` 接口。

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
pytest                 # 61 个用例
ruff check app tests   # 静态检查
```

测试使用临时 SQLite + fakeredis + FastAPI 依赖覆盖，不依赖本机 MySQL/Redis，覆盖：

- 登录契约：JSON 请求体、参数校验、Swagger 表单端点、旧 JSON 路径兼容；
- 数据库结构预检：完整结构无漂移、缺列/缺表可被检测；
- 登录成功/失败/未带 Token/普通用户越权；
- 配件分页、模糊搜索、分类筛选、缓存命中与版本失效；
- 新增/修改配件的库存流水、库存预警、参数校验；
- 采购入库（库存、金额、流水、供应商校验、缺配件回滚）；
- 销售出库（默认单价、扣减、超卖 409、多明细原子性、重复配件校验）；
- 看板金额、单量、Top 5 排序与权限；经营报表日期区间、毛利/毛利率、分类/排行/趋势；
- 销售记录分页、日期/客户/单号筛选、金额合计、越权与非法日期区间；
- 操作审计：登录/失败/退出、采购/销售/配件写操作、管理员全量、普通用户仅本人、越权详情 404、密码不落库；
- 成交价权限：普通用户改价 403、管理员可改价；
- 现有 Vue 前端契约：`/suppliers/options`、`/customers/options`、`page_size`、`price`、`supplier_id`/`unit_price`、销售单条 payload；
- 角色/模块矩阵：普通用户只可访问管理员分配的模块；配件/供应商写操作仅管理员；客户写操作由 customers 模块控制；用户/模块配置仅管理员；
- 用户/模块：管理员创建普通用户、分配/回收模块、重置密码、启用停用；模块停用后普通用户立即失去 API 权限；
- 客户/供应商：分页、统计、创建/修改、客户跟进、供应商采购统计。

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

**Q：普通员工账号怎么创建？为什么没有默认 `staff`？**

系统只保留一个内置管理员 `admin`（boss）；普通用户统一由管理员登录后在「用户管理」创建，并勾选可用模块。
演示快照里可能已有 `zhujunjie`、`zhaohua` 等历史账号，密码以实际数据库为准；不要假设有默认 `staff`。

如果账号登录不进去：

- 密码未知，或旧系统的密码哈希方案与当前 `SHA-256 + bcrypt` 不同；
- 账号被停用（登录返回 403 `USER_DISABLED`）；
- 账号不存在（登录返回 401 `INVALID_CREDENTIALS`）；
- 普通用户没有分配任何模块时，登录后进入「暂无权限」页，需要管理员在「用户管理」勾选模块。

运维兜底命令：

```bash
# 查看账号和模块
python -m scripts.user_admin list

# 重置已有账号密码并启用
python -m scripts.reset_password --username zhujunjie --activate

# 直接创建一个员工账号（仅运维兜底；业务上建议用管理员页面创建）
python -m scripts.reset_password --username staff01 --password 'Staff01@123' \
  --create --role employee --activate
```

角色权限：

- `boss`：管理员，全部模块 + 用户管理 + 模块配置；
- `employee`：普通用户，只显示管理员分配的模块；访问未分配模块返回 403。

Docker 环境把 `python -m ...` 换成 `docker compose run --rm --entrypoint python api -m ...`。

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
