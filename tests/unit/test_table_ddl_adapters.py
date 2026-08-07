"""Unit tests for get_table_ddl across MSSQL, Snowflake, and DuckDB adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import duckdb
import pytest


# --------------------------------------------------------------------------- MSSQL


class TestMSSQLGetTableDDL:
    """MSSQL adapter get_table_ddl: views via OBJECT_DEFINITION, tables reconstructed."""

    @pytest.fixture
    def adapter(self):
        with patch.dict("sys.modules", {"mssql_python": MagicMock()}):
            from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

            return SQLServerAdapter()

    def _make_conn(self, fetchone_side_effects, fetchall_side_effects):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = fetchone_side_effects
        cursor.fetchall.side_effect = fetchall_side_effects
        return conn, cursor

    def test_view_returns_object_definition(self, adapter):
        conn, cursor = self._make_conn(
            fetchone_side_effects=[("CREATE VIEW dbo.v AS SELECT 1",)],
            fetchall_side_effects=[],
        )

        ddl = adapter.get_table_ddl(conn, "v", database="TestDB", schema="dbo")

        assert ddl == "CREATE VIEW dbo.v AS SELECT 1"

    def test_table_reconstructs_create_statement(self, adapter):
        # First fetchone (view check) returns NULL -> not a view.
        # Then fetchall returns column rows, then fetchall returns PK rows.
        column_rows = [
            ("id", "int", None, 10, 0, "NO", None),
            ("name", "varchar", 50, None, None, "YES", None),
            ("price", "decimal", None, 10, 2, "YES", "0"),
        ]
        pk_rows = [("id",)]
        conn, cursor = self._make_conn(
            fetchone_side_effects=[(None,)],
            fetchall_side_effects=[column_rows, pk_rows],
        )

        ddl = adapter.get_table_ddl(conn, "Products", database="TestDB", schema="dbo")

        assert ddl is not None
        assert ddl.startswith("CREATE TABLE [dbo].[Products] (\n")
        assert "[id] int NOT NULL" in ddl
        assert "[name] varchar(50)" in ddl
        assert "[price] decimal(10, 2) DEFAULT 0" in ddl
        assert "CONSTRAINT [PK_Products] PRIMARY KEY ([id])" in ddl

    def test_table_returns_none_when_no_columns(self, adapter):
        conn, cursor = self._make_conn(
            fetchone_side_effects=[(None,)],
            fetchall_side_effects=[[]],  # no columns
        )

        ddl = adapter.get_table_ddl(conn, "Missing", database="TestDB", schema="dbo")

        assert ddl is None

    def test_table_without_primary_key_omits_constraint(self, adapter):
        column_rows = [("id", "int", None, 10, 0, "NO", None)]
        conn, cursor = self._make_conn(
            fetchone_side_effects=[(None,)],
            fetchall_side_effects=[column_rows, []],  # no PK rows
        )

        ddl = adapter.get_table_ddl(conn, "NoPK", database="TestDB", schema="dbo")

        assert ddl is not None
        assert "PRIMARY KEY" not in ddl

    def test_uses_database_context_switch(self, adapter):
        conn, cursor = self._make_conn(
            fetchone_side_effects=[(None,)],
            fetchall_side_effects=[[("id", "int", None, 10, 0, "NO", None)], []],
        )

        adapter.get_table_ddl(conn, "T", database="TestDB", schema="dbo")

        first_sql = cursor.execute.call_args_list[0][0][0]
        assert first_sql == "USE [TestDB]"

    def test_type_str_handles_varchar_max(self, adapter):
        assert adapter._mssql_type_str("varchar", -1, None, None) == "varchar(MAX)"
        assert adapter._mssql_type_str("nvarchar", 100, None, None) == "nvarchar(100)"
        assert adapter._mssql_type_str("decimal", None, 10, 2) == "decimal(10, 2)"
        assert adapter._mssql_type_str("int", None, None, None) == "int"


# ----------------------------------------------------------------------- Snowflake


class TestSnowflakeGetTableDDL:
    """Snowflake adapter get_table_ddl uses the GET_DDL function."""

    def _make_adapter(self):
        with patch.dict("sys.modules", {"snowflake.connector": MagicMock()}):
            from sqlit.domains.connections.providers.snowflake.adapter import SnowflakeAdapter

            return SnowflakeAdapter()

    def _make_conn(self, fetchone_side_effects):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.side_effect = fetchone_side_effects
        return conn, cursor

    def test_table_ddl_returned_on_first_try(self):
        adapter = self._make_adapter()
        conn, cursor = self._make_conn([("CREATE TABLE mydb.PUBLIC.users (id INT)",)])

        ddl = adapter.get_table_ddl(conn, "users", database="mydb", schema="PUBLIC")

        assert ddl == "CREATE TABLE mydb.PUBLIC.users (id INT)"
        # Only one execute call needed.
        assert cursor.execute.call_count == 1
        cursor.execute.assert_called_once_with("SELECT GET_DDL(?, ?)", ("TABLE", "mydb.PUBLIC.users"))

    def test_falls_back_to_view_when_table_returns_null(self):
        adapter = self._make_adapter()
        conn, cursor = self._make_conn([(None,), ("CREATE VIEW mydb.PUBLIC.v AS SELECT 1",)])

        ddl = adapter.get_table_ddl(conn, "v", database="mydb", schema="PUBLIC")

        assert ddl == "CREATE VIEW mydb.PUBLIC.v AS SELECT 1"
        assert cursor.execute.call_count == 2
        second_call_args = cursor.execute.call_args_list[1][0]
        assert second_call_args == ("SELECT GET_DDL(?, ?)", ("VIEW", "mydb.PUBLIC.v"))

    def test_returns_none_when_both_types_return_null(self):
        adapter = self._make_adapter()
        conn, cursor = self._make_conn([(None,), (None,)])

        ddl = adapter.get_table_ddl(conn, "missing", database="mydb", schema="PUBLIC")

        assert ddl is None

    def test_qualified_name_omits_database_when_none(self):
        adapter = self._make_adapter()
        conn, cursor = self._make_conn([("CREATE TABLE PUBLIC.users (id INT)",)])

        adapter.get_table_ddl(conn, "users", database=None, schema="PUBLIC")

        cursor.execute.assert_called_once_with("SELECT GET_DDL(?, ?)", ("TABLE", "PUBLIC.users"))

    def test_skips_type_on_exception_and_tries_next(self):
        adapter = self._make_adapter()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        # First execute (TABLE) raises, second (VIEW) returns a row.
        cursor.execute.side_effect = [Exception("boom"), None]
        cursor.fetchone.side_effect = [("CREATE VIEW s.v AS SELECT 1",)]

        ddl = adapter.get_table_ddl(conn, "v", database=None, schema="s")

        assert ddl == "CREATE VIEW s.v AS SELECT 1"


# ------------------------------------------------------------------------- DuckDB


class TestDuckDBGetTableDDL:
    """DuckDB adapter get_table_ddl reads duckdb_tables()/duckdb_views() sql column."""

    @pytest.fixture
    def tmp_db(self, tmp_path):
        db = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL)")
        conn.execute("CREATE VIEW active_users AS SELECT name FROM users")
        yield conn
        conn.close()

    def test_table_ddl_from_duckdb_tables(self, tmp_db):
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        ddl = adapter.get_table_ddl(tmp_db, "users", schema="main")

        assert ddl is not None
        assert "CREATE TABLE" in ddl.upper()
        assert "users" in ddl

    def test_view_ddl_from_duckdb_views(self, tmp_db):
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        ddl = adapter.get_table_ddl(tmp_db, "active_users", schema="main")

        assert ddl is not None
        assert "active_users" in ddl

    def test_returns_none_for_missing_object(self, tmp_db):
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        ddl = adapter.get_table_ddl(tmp_db, "does_not_exist", schema="main")

        assert ddl is None

    def test_defaults_to_main_schema(self, tmp_db):
        from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        # schema=None should default to "main" and still find the table.
        ddl = adapter.get_table_ddl(tmp_db, "users", schema=None)

        assert ddl is not None
        assert "users" in ddl
