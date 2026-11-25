"""数据库结构预检测试（不依赖 MySQL）。"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.schema import _find_missing_schema_parts


def _sqlite_engine():
    return create_engine("sqlite://", poolclass=StaticPool)


def test_complete_schema_has_no_drift():
    engine = _sqlite_engine()
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            assert _find_missing_schema_parts(conn) == []
    finally:
        engine.dispose()


def test_missing_columns_and_tables_are_detected():
    engine = _sqlite_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50))"))
            conn.commit()
            missing = _find_missing_schema_parts(conn)
    finally:
        engine.dispose()

    assert "users.is_active" in missing
    assert "users.password_hash" in missing
    assert "parts（整表）" in missing


def test_models_do_not_declare_database_foreign_keys():
    foreign_keys = [
        (table.name, fk.parent.name, fk.target_fullname)
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
    ]
    assert foreign_keys == []
