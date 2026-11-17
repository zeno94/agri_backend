.PHONY: help install dev up down logs migrate seed test lint

PY := .venv/bin/python
PIP := .venv/bin/pip

help:
	@echo "install  - 创建虚拟环境并安装依赖"
	@echo "dev      - 本地热重载启动（需先启动 MySQL/Redis）"
	@echo "up       - docker compose 构建并启动全部服务"
	@echo "down     - 停止并移除容器"
	@echo "logs     - 查看 api 日志"
	@echo "migrate  - 执行数据库迁移"
	@echo "seed     - 初始化账号与示例数据"
	@echo "test     - 运行测试"
	@echo "lint     - Ruff 静态检查"

install:
	python3 -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -r requirements-dev.txt

dev:
	$(PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

migrate:
	$(PY) -m alembic upgrade head

seed:
	$(PY) -m app.db.init_db

test:
	$(PY) -m pytest

lint:
	.venv/bin/ruff check app tests
