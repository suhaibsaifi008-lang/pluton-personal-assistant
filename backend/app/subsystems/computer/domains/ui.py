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
        from ..adapters.desktop_adapter import DESKTOP_ADAPTER
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = DESKTOP_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        eff_depth = max_depth if max_depth != 4 else depth
        res = DESKTOP_ADAPTER.inspect_ui_tree(hwnd=target_hwnd, max_depth=min(eff_depth, 3))
        return res.get("elements", [])

    def find(self, query: str, hwnd: int = 0, window_query: str = "", control_type: str | None = None, context: ExecutionContext | None = None) -> list[dict[str, Any]]:
        """Find matching UI elements in target window or window matching window_query."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.desktop_adapter import DESKTOP_ADAPTER
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = DESKTOP_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        return DESKTOP_ADAPTER.find_elements(hwnd=target_hwnd, query=query, control_type=control_type, max_results=10)

    def invoke(self, target: str, hwnd: int = 0, window_query: str = "", target_element: str = "", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Invoke element default action (e.g. Button click) via windows-use pattern or coordinate fallback."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.desktop_adapter import DESKTOP_ADAPTER
        target_name = target_element or target or ""
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = DESKTOP_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        return DESKTOP_ADAPTER.invoke_element(target=target_name, hwnd=target_hwnd)

    def set_value(self, target: str = "", value: str = "", hwnd: int = 0, window_query: str = "", target_element: str = "", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Set edit/input value via UIA ValuePattern or keyboard typing."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.desktop_adapter import DESKTOP_ADAPTER
        target_name = target_element or target or ""
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            matched = DESKTOP_ADAPTER.find_windows_by_app(window_query)
            if matched:
                target_hwnd = matched[0].get("hwnd", 0)
        return DESKTOP_ADAPTER.set_element_value(target=target_name, value=value, hwnd=target_hwnd)

    def toggle(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Toggle checkbox or switch via UIA TogglePattern."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        act_res = UIA_ENGINE.execute_ui_action(target_name=target, action="toggle", hwnd=target_hwnd)
        if act_res.get("success"):
            return act_res
        return self.invoke(target, hwnd=hwnd, context=context)

    def select(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Select item in list or dropdown via UIA SelectionItemPattern."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        act_res = UIA_ENGINE.execute_ui_action(target_name=target, action="select", value=target, hwnd=target_hwnd)
        if act_res.get("success"):
            return act_res
        return self.invoke(target, hwnd=hwnd, context=context)

    def expand(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Expand tree or menu item."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        act_res = UIA_ENGINE.execute_ui_action(target_name=target, action="expand", hwnd=target_hwnd)
        if act_res.get("success"):
            return act_res
        return self.invoke(target, hwnd=hwnd, context=context)

    def collapse(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Collapse tree or menu item."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        act_res = UIA_ENGINE.execute_ui_action(target_name=target, action="collapse", hwnd=target_hwnd)
        if act_res.get("success"):
            return act_res
        return self.invoke(target, hwnd=hwnd, context=context)

    def focus(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Focus specific UI element."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        elems = UIA_ENGINE.find_elements_by_query(hwnd=target_hwnd, query=target, max_results=1)
        if not elems:
            return {"success": False, "error": f"UI element '{target}' not found."}
        return {"success": True, "element": elems[0]}

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
