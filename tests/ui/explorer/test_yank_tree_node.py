"""Tests for the explorer tree yank menu (y)."""

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


def _make_column_info(name: str, data_type: str) -> MagicMock:
    info = MagicMock()
    info.name = name
    info.data_type = data_type
    return info


class TestYankTreeNodeMenu:
    """action_yank_tree_node opens a submenu rather than copying directly."""

    def _make_mixin(
        self,
        node: MockTreeNode,
        *,
        table_ddl: str | None = None,
        columns: list[MagicMock] | None = None,
    ) -> TreeMixin:
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=node)
        mixin._session = MagicMock() if (table_ddl is not None or columns is not None) else None

        schema_service = MagicMock()
        schema_service.get_table_ddl.return_value = table_ddl
        schema_service.list_columns.return_value = columns or []
        mixin._get_schema_service = MagicMock(
            return_value=schema_service if (table_ddl is not None or columns is not None) else None
        )

        copied: list[str] = []
        mixin._copy_tree_text = lambda text, *, what: copied.append(text)
        mixin._copy_tree_text_calls = copied  # type: ignore[attr-defined]

        leader_menus: list[str] = []
        mixin._start_leader_pending = lambda menu: leader_menus.append(menu)
        mixin._leader_menus = leader_menus  # type: ignore[attr-defined]
        mixin._cancel_leader_pending = lambda: None
        mixin._yank_target_node = None
        return mixin

    def test_yank_column_opens_cy_menu(self) -> None:
        node = MockTreeNode(
            data=ColumnNode(database=None, schema="public", table="users", name="email"),
        )
        mixin = self._make_mixin(node)

        mixin.action_yank_tree_node()

        assert mixin._leader_menus == ["cy"]
        assert mixin._yank_target_node is node

    def test_yank_table_opens_ty_menu(self) -> None:
        node = MockTreeNode(
            data=TableNode(database=None, schema="public", name="users"),
        )
        mixin = self._make_mixin(node)

        mixin.action_yank_tree_node()

        assert mixin._leader_menus == ["ty"]
        assert mixin._yank_target_node is node

    def test_yank_view_opens_ty_menu(self) -> None:
        node = MockTreeNode(
            data=ViewNode(database=None, schema="public", name="active_users"),
        )
        mixin = self._make_mixin(node)

        mixin.action_yank_tree_node()

        assert mixin._leader_menus == ["ty"]

    def test_yank_does_nothing_on_unsupported_node(self) -> None:
        from sqlit.domains.explorer.domain.tree_nodes import FolderNode

        node = MockTreeNode(data=FolderNode(folder_type="tables"))
        mixin = self._make_mixin(node)

        mixin.action_yank_tree_node()

        assert mixin._leader_menus == []
        assert mixin._copy_tree_text_calls == []

    def test_yank_does_nothing_without_node(self) -> None:
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=None)
        mixin._copy_tree_text = MagicMock()
        mixin._start_leader_pending = MagicMock()

        mixin.action_yank_tree_node()

        mixin._copy_tree_text.assert_not_called()
        mixin._start_leader_pending.assert_not_called()


class TestTyNameAction:
    """action_ty_name copies the qualified/bare table or view name."""

    def _make_mixin(self, node: MockTreeNode) -> TreeMixin:
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=node)
        copied: list[str] = []
        mixin._copy_tree_text = lambda text, *, what: copied.append(text)
        mixin._copy_tree_text_calls = copied  # type: ignore[attr-defined]
        mixin._cancel_leader_pending = lambda: None
        mixin._yank_target_node = node
        return mixin

    def test_copies_qualified_table_name(self) -> None:
        node = MockTreeNode(data=TableNode(database=None, schema="public", name="users"))
        mixin = self._make_mixin(node)

        mixin.action_ty_name()

        assert mixin._copy_tree_text_calls == ["public.users"]

    def test_copies_bare_table_name_without_schema(self) -> None:
        node = MockTreeNode(data=TableNode(database=None, schema="", name="users"))
        mixin = self._make_mixin(node)

        mixin.action_ty_name()

        assert mixin._copy_tree_text_calls == ["users"]

    def test_copies_view_name(self) -> None:
        node = MockTreeNode(data=ViewNode(database=None, schema="public", name="active_users"))
        mixin = self._make_mixin(node)

        mixin.action_ty_name()

        assert mixin._copy_tree_text_calls == ["public.active_users"]

    def test_clears_yank_target_after(self) -> None:
        node = MockTreeNode(data=TableNode(database=None, schema="public", name="users"))
        mixin = self._make_mixin(node)

        mixin.action_ty_name()

        assert mixin._yank_target_node is None


class TestTyDdlAction:
    """action_ty_ddl copies the DDL, falling back to the name."""

    def _make_mixin(self, node: MockTreeNode, *, ddl: str | None) -> TreeMixin:
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=node)
        schema_service = MagicMock()
        schema_service.get_table_ddl.return_value = ddl
        mixin._get_schema_service = MagicMock(return_value=schema_service)
        copied: list[str] = []
        mixin._copy_tree_text = lambda text, *, what: copied.append(text)
        mixin._copy_tree_text_calls = copied  # type: ignore[attr-defined]
        mixin._cancel_leader_pending = lambda: None
        mixin._yank_target_node = node
        return mixin

    def test_copies_ddl_when_available(self) -> None:
        node = MockTreeNode(data=TableNode(database=None, schema="public", name="users"))
        ddl = "CREATE TABLE public.users (id INTEGER PRIMARY KEY, name TEXT)"
        mixin = self._make_mixin(node, ddl=ddl)

        mixin.action_ty_ddl()

        assert mixin._copy_tree_text_calls == [ddl]
        mixin._get_schema_service.return_value.get_table_ddl.assert_called_once_with(
            None, "public", "users"
        )

    def test_falls_back_to_name_when_ddl_unavailable(self) -> None:
        node = MockTreeNode(data=TableNode(database=None, schema="public", name="users"))
        mixin = self._make_mixin(node, ddl=None)

        mixin.action_ty_ddl()

        assert mixin._copy_tree_text_calls == ["public.users"]


class TestCyActions:
    """action_cy_name / action_cy_type copy column name / data type."""

    def _make_mixin(self, node: MockTreeNode, *, columns: list[MagicMock]) -> TreeMixin:
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=node)
        schema_service = MagicMock()
        schema_service.list_columns.return_value = columns
        mixin._get_schema_service = MagicMock(return_value=schema_service)
        copied: list[str] = []
        mixin._copy_tree_text = lambda text, *, what: copied.append(text)
        mixin._copy_tree_text_calls = copied  # type: ignore[attr-defined]
        mixin.notify = MagicMock()
        mixin._cancel_leader_pending = lambda: None
        mixin._yank_target_node = node
        return mixin

    def test_cy_name_copies_column_name(self) -> None:
        node = MockTreeNode(
            data=ColumnNode(database=None, schema="public", table="users", name="email"),
        )
        mixin = self._make_mixin(node, columns=[])

        mixin.action_cy_name()

        assert mixin._copy_tree_text_calls == ["email"]

    def test_cy_type_copies_data_type(self) -> None:
        node = MockTreeNode(
            data=ColumnNode(database=None, schema="public", table="users", name="email"),
        )
        mixin = self._make_mixin(
            node, columns=[_make_column_info("email", "VARCHAR(255)")]
        )

        mixin.action_cy_type()

        assert mixin._copy_tree_text_calls == ["VARCHAR(255)"]
        mixin._get_schema_service.return_value.list_columns.assert_called_once_with(
            None, "public", "users"
        )

    def test_cy_type_warns_when_unavailable(self) -> None:
        node = MockTreeNode(
            data=ColumnNode(database=None, schema="public", table="users", name="email"),
        )
        mixin = self._make_mixin(node, columns=[])

        mixin.action_cy_type()

        assert mixin._copy_tree_text_calls == []
        mixin.notify.assert_called_once_with("Column data type unavailable", severity="warning")

    def test_cy_type_warns_without_schema_service(self) -> None:
        node = MockTreeNode(
            data=ColumnNode(database=None, schema="public", table="users", name="email"),
        )
        mixin = object.__new__(TreeMixin)
        mixin.object_tree = MockTree(cursor_node=node)
        mixin._get_schema_service = MagicMock(return_value=None)
        mixin._copy_tree_text = MagicMock()
        mixin.notify = MagicMock()
        mixin._cancel_leader_pending = lambda: None
        mixin._yank_target_node = node

        mixin.action_cy_type()

        mixin._copy_tree_text.assert_not_called()
        mixin.notify.assert_called_once_with("Column data type unavailable", severity="warning")


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
