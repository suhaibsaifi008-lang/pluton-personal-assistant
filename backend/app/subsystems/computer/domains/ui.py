"""
PLUTON V2 — UI Domain Handler
Implements semantic UIA element operations:
ui.inspect, ui.find, ui.invoke, ui.set_value, ui.toggle, ui.select, ui.expand, ui.collapse, ui.focus.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL
from app.tools.uia_engine import UIA_ENGINE

logger = logging.getLogger("pluton.computer.ui")


class UIDomainHandler:
    """Canonical handler for Windows UI Automation element interactions."""

    def inspect(self, hwnd: int = 0, depth: int = 4, window_query: str = "", max_depth: int = 4, context: ExecutionContext | None = None) -> list[dict[str, Any]]:
        """Inspect accessibility control tree for target window or window matching window_query."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = PYWINAUTO_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        eff_depth = max_depth if max_depth != 4 else depth
        return PYWINAUTO_ADAPTER.inspect_ui_tree(hwnd=target_hwnd, max_depth=min(eff_depth, 3))

    def find(self, query: str, hwnd: int = 0, window_query: str = "", control_type: str | None = None, context: ExecutionContext | None = None) -> list[dict[str, Any]]:
        """Find matching UI elements in target window or window matching window_query."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = PYWINAUTO_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        elements = PYWINAUTO_ADAPTER.inspect_ui_tree(hwnd=target_hwnd, max_depth=3)
        q_low = query.strip().lower()
        return [
            e for e in elements
            if q_low in e.get("name", "").lower() or q_low in e.get("automation_id", "").lower() or (control_type and control_type.lower() in e.get("control_type", "").lower())
        ]

    def invoke(self, target: str, hwnd: int = 0, window_query: str = "", target_element: str = "", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Invoke element default action (e.g. Button click) via pywinauto."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        target_name = target_element or target or ""
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = PYWINAUTO_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        return PYWINAUTO_ADAPTER.invoke_control(hwnd=target_hwnd, query=target_name, action="click")

    def set_value(self, target: str = "", value: str = "", hwnd: int = 0, window_query: str = "", target_element: str = "", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Set edit/input value via pywinauto."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        target_name = target_element or target or ""
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = PYWINAUTO_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        return PYWINAUTO_ADAPTER.invoke_control(hwnd=target_hwnd, query=target_name, action="set_value", value=value)

    def toggle(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Toggle checkbox or switch via pywinauto."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return self.invoke(target, hwnd=hwnd, context=context)

    def select(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Select item in list or dropdown via pywinauto."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return self.invoke(target, hwnd=hwnd, context=context)

    def expand(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Expand tree or menu item."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return self.invoke(target, hwnd=hwnd, context=context)

    def collapse(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Collapse tree or menu item."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return self.invoke(target, hwnd=hwnd, context=context)

    def focus(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Focus specific UI element."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if target_hwnd:
            PYWINAUTO_ADAPTER.focus_window(target_hwnd)
        return {"success": True, "target": target, "hwnd": target_hwnd}

    def find_element(self, query: str, hwnd: int = 0, control_type: str | None = None, context: ExecutionContext | None = None) -> dict[str, Any] | None:
        """Find single matching UI element."""
        elems = self.find(query=query, hwnd=hwnd, control_type=control_type, context=context)
        return elems[0] if elems else None

    def expand_collapse(self, target: str, expand: bool = True, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Expand or collapse tree or menu item."""
        if expand:
            return self.expand(target, hwnd=hwnd, context=context)
        return self.collapse(target, hwnd=hwnd, context=context)

    inspect_tree = inspect
    find_elements = find


UI_DOMAIN = UIDomainHandler()
