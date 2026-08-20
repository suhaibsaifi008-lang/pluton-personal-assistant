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
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            win = UIA_ENGINE.find_window(window_query)
            if win:
                target_hwnd = win.get("hwnd", 0)
        eff_depth = max_depth if max_depth != 4 else depth
        res = UIA_ENGINE.inspect_ui_tree(hwnd=target_hwnd, max_depth=eff_depth)
        return res.get("elements", [])

    def find(self, query: str, hwnd: int = 0, window_query: str = "", control_type: str | None = None, context: ExecutionContext | None = None) -> list[dict[str, Any]]:
        """Find matching UI elements in target window or window matching window_query."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)
        if not target_hwnd and window_query:
            win = UIA_ENGINE.find_window(window_query)
            if win:
                target_hwnd = win.get("hwnd", 0)
        return UIA_ENGINE.find_elements_by_query(hwnd=target_hwnd, query=query, control_type=control_type, max_results=10)

    def invoke(self, target: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Invoke element default action (e.g. Button click) via UIA native patterns with coordinate fallback."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)

        # 1. Try native UIA pattern execution
        act_res = UIA_ENGINE.execute_ui_action(target_name=target, action="invoke", hwnd=target_hwnd)
        if act_res.get("success"):
            obs_text = UIA_ENGINE.read_window_text(target_hwnd)
            return {
                "success": True,
                "method": act_res.get("method", "uia_pattern"),
                "element": act_res.get("element", target),
                "observed_state": obs_text,
            }

        # 2. Fallback: coordinate click on element bounding center
        elems = UIA_ENGINE.find_elements_by_query(hwnd=target_hwnd, query=target, max_results=1)
        if not elems:
            return {"success": False, "error": f"UI element '{target}' not found."}

        elem_meta = elems[0]
        bounds = elem_meta.get("bounding_rectangle") or elem_meta.get("rect")
        if bounds:
            if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
                left, top, w, h = bounds
                cx, cy = left + w // 2, top + h // 2
            elif isinstance(bounds, dict):
                cx = bounds.get("left", 0) + bounds.get("width", 0) // 2
                cy = bounds.get("top", 0) + bounds.get("height", 0) // 2
            else:
                return {"success": False, "error": "Element has no valid screen bounds."}

            from .mouse import MOUSE_DOMAIN
            click_res = MOUSE_DOMAIN.click(cx, cy, context=context)
            obs_text = UIA_ENGINE.read_window_text(target_hwnd)
            return {
                "success": True,
                "method": "uia_element_click",
                "element": elem_meta,
                "click": click_res,
                "observed_state": obs_text,
            }

        return {"success": False, "error": "Element has no valid screen bounds."}

    def set_value(self, target: str, value: str, hwnd: int = 0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Set edit/input value via UIA ValuePattern or keyboard typing."""
        KERNEL.assert_authorized(context.task_id if context else None)
        target_hwnd = hwnd or (context.bound_hwnd if context else 0)

        # Try native UIA ValuePattern first
        act_res = UIA_ENGINE.execute_ui_action(target_name=target, action="set_value", value=value, hwnd=target_hwnd)
        if act_res.get("success"):
            obs_text = UIA_ENGINE.read_window_text(target_hwnd)
            return {
                "success": True,
                "method": act_res.get("method", "ValuePattern"),
                "element": act_res.get("element", target),
                "value_set": value,
                "observed_state": obs_text,
            }

        from app.tools.keyboard_pipeline import type_into_window
        return type_into_window(hwnd=target_hwnd, text=value, expected_text=value)

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
