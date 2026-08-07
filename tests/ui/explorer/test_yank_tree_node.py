"""Tests for the explorer tree yank action (y)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from sqlit.domains.explorer.domain.tree_nodes import ColumnNode, TableNode, ViewNode
from sqlit.domains.explorer.ui.mixins.tree import TreeMixin


@dataclass
class MockTreeNode:
    label: str = ""
    data: object | None = None


class MockTree:
    def __init__(self, cursor_node: MockTreeNode | None = None) -> None:
        self.root = MockTreeNode("root")
        self.cursor_node = cursor_node


class TestYankTreeNode:
    """action_yank_tree_node should copy column names or table DDL."""

    def _make_mixin(
        self,
        node: MockTreeNode,
        *,
        table_ddl: str | None = None,
    ) -> TreeMixin:
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=node)
        mixin._session = MagicMock() if table_ddl is not None else None

        schema_service = MagicMock()
        schema_service.get_table_ddl.return_value = table_ddl
        mixin._get_schema_service = MagicMock(return_value=schema_service if table_ddl is not None else None)

        copied: list[str] = []
        mixin._copy_tree_text = lambda text, *, what: copied.append(text)
        mixin._copy_tree_text_calls = copied  # type: ignore[attr-defined]
        return mixin

    def test_yank_column_copies_column_name(self) -> None:
        node = MockTreeNode(
            data=ColumnNode(database=None, schema="public", table="users", name="email"),
        )
        mixin = self._make_mixin(node)

        mixin.action_yank_tree_node()

        assert mixin._copy_tree_text_calls == ["email"]

    def test_yank_table_copies_ddl_when_available(self) -> None:
        node = MockTreeNode(
            data=TableNode(database=None, schema="public", name="users"),
        )
        ddl = "CREATE TABLE public.users (id INTEGER PRIMARY KEY, name TEXT)"
        mixin = self._make_mixin(node, table_ddl=ddl)

        mixin.action_yank_tree_node()

        assert mixin._copy_tree_text_calls == [ddl]
        # Schema service should have been asked for the right table.
        mixin._get_schema_service.return_value.get_table_ddl.assert_called_once_with(
            None, "public", "users"
        )

    def test_yank_view_copies_ddl_when_available(self) -> None:
        node = MockTreeNode(
            data=ViewNode(database=None, schema="public", name="active_users"),
        )
        ddl = "CREATE VIEW public.active_users AS SELECT * FROM users"
        mixin = self._make_mixin(node, table_ddl=ddl)

        mixin.action_yank_tree_node()

        assert mixin._copy_tree_text_calls == [ddl]

    def test_yank_table_falls_back_to_qualified_name_when_ddl_unavailable(self) -> None:
        node = MockTreeNode(
            data=TableNode(database=None, schema="public", name="users"),
        )
        # No session/schema service -> DDL unavailable
        mixin = self._make_mixin(node, table_ddl=None)

        mixin.action_yank_tree_node()

        assert mixin._copy_tree_text_calls == ["public.users"]

    def test_yank_table_falls_back_to_bare_name_when_no_schema(self) -> None:
        node = MockTreeNode(
            data=TableNode(database=None, schema="", name="users"),
        )
        mixin = self._make_mixin(node, table_ddl=None)

        mixin.action_yank_tree_node()

        assert mixin._copy_tree_text_calls == ["users"]

    def test_yank_does_nothing_on_unsupported_node(self) -> None:
        # A folder node is not a yank target.
        from sqlit.domains.explorer.domain.tree_nodes import FolderNode

        node = MockTreeNode(data=FolderNode(folder_type="tables"))
        mixin = self._make_mixin(node)

        mixin.action_yank_tree_node()

        assert mixin._copy_tree_text_calls == []

    def test_yank_does_nothing_without_node(self) -> None:
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=None)
        mixin._copy_tree_text = MagicMock()

        mixin.action_yank_tree_node()

        mixin._copy_tree_text.assert_not_called()


class TestYankTreeNodeClipboard:
    """_copy_tree_text should push to the system clipboard and notify."""

    def _make_mixin(self) -> TreeMixin:
        mixin = object.__new__(TreeMixin)
        mixin.notify = MagicMock()
        mixin.copy_to_clipboard = MagicMock()
        return mixin

    def test_copy_tree_text_uses_system_clipboard_and_osc52(self, monkeypatch) -> None:
        mixin = self._make_mixin()

        calls: list[str] = []
        monkeypatch.setattr(
            "sqlit.shared.ui.clipboard.copy_to_system_clipboard",
            lambda text: calls.append(text) or True,
        )

        mixin._copy_tree_text("hello", what="Column name")

        assert calls == ["hello"]
        mixin.copy_to_clipboard.assert_called_once_with("hello")
        mixin.notify.assert_called_once_with("Column name copied")

    def test_copy_tree_text_notifies_on_failure(self, monkeypatch) -> None:
        mixin = self._make_mixin()
        mixin.copy_to_clipboard = MagicMock(side_effect=RuntimeError("osc52 unavailable"))

        monkeypatch.setattr(
            "sqlit.shared.ui.clipboard.copy_to_system_clipboard",
            lambda text: False,
        )

        mixin._copy_tree_text("hello", what="Column name")

        mixin.notify.assert_called_once_with("Failed to copy column name", severity="error")
