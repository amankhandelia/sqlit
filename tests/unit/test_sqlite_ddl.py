"""Unit tests for SQLite adapter DDL introspection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter


def _make_adapter_with_db(tmp_path: Path) -> tuple[SQLiteAdapter, sqlite3.Connection]:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("CREATE VIEW active_users AS SELECT name FROM users")
    conn.commit()
    adapter = SQLiteAdapter()
    return adapter, conn


def test_get_table_ddl_returns_create_statement(tmp_path: Path) -> None:
    adapter, conn = _make_adapter_with_db(tmp_path)

    ddl = adapter.get_table_ddl(conn, "users")

    assert ddl is not None
    assert "CREATE TABLE" in ddl.upper()
    assert "users" in ddl


def test_get_table_ddl_returns_view_definition(tmp_path: Path) -> None:
    adapter, conn = _make_adapter_with_db(tmp_path)

    ddl = adapter.get_table_ddl(conn, "active_users")

    assert ddl is not None
    assert "CREATE VIEW" in ddl.upper()
    assert "active_users" in ddl


def test_get_table_ddl_returns_none_for_missing_table(tmp_path: Path) -> None:
    adapter, conn = _make_adapter_with_db(tmp_path)

    ddl = adapter.get_table_ddl(conn, "does_not_exist")

    assert ddl is None
