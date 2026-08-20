"""
PLUTON V2 — Window Domain Handler
Implements canonical window lifecycle & state manipulation:
window.list, window.find, window.focus, window.move, window.resize, window.minimize, window.maximize, window.restore, window.close, window.get_state.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import time
from typing import Any

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL
from app.tools.uia_engine import UIA_ENGINE, attach_interactive_desktop


class WindowDomainHandler:
    """Canonical handler for window inspection and state manipulation."""

    def list_windows(self, visible_only: bool = True, context: ExecutionContext | None = None) -> list[dict[str, Any]]:
        """List open top-level desktop windows."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        return PYWINAUTO_ADAPTER.list_windows(visible_only=visible_only)

    list = list_windows

    def find_window(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any] | None:
        """Find a window by title, HWND, or PID."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        if isinstance(target, int):
            wins = PYWINAUTO_ADAPTER.list_windows(visible_only=False)
            return next((w for w in wins if w.get("hwnd") == target or w.get("pid") == target), None)
        matched = PYWINAUTO_ADAPTER.find_windows_by_app(str(target))
        if matched:
            return matched[0]
        wins = PYWINAUTO_ADAPTER.list_windows(visible_only=False)
        t_low = str(target).lower()
        return next((w for w in wins if t_low in str(w.get("title", "")).lower()), None)

    find = find_window

    def get_foreground_window(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get canonical structured metadata about active foreground window."""
        KERNEL.assert_authorized(context.task_id if context else None)
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindow(hwnd):
            return {"active": False, "hwnd": 0, "title": "", "class_name": "", "pid": 0}
        t_len = user32.GetWindowTextLengthW(hwnd)
        t_buf = ctypes.create_unicode_buffer(t_len + 1)
        user32.GetWindowTextW(hwnd, t_buf, t_len + 1)
        c_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, c_buf, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return {"active": True, "hwnd": hwnd, "title": t_buf.value.strip(), "class_name": c_buf.value.strip(), "pid": pid.value}

    def get_state(self, target: str | int | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get structured state of a window or the active foreground window."""
        KERNEL.assert_authorized(context.task_id if context else None)
        attach_interactive_desktop()
        user32 = ctypes.windll.user32

        hwnd = target if isinstance(target, int) else None
        if not hwnd and target:
            win = self.find_window(target, context=context)
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            hwnd = user32.GetForegroundWindow()

        if not hwnd or not user32.IsWindow(hwnd):
            return {"active": False, "hwnd": 0, "title": "", "state": "not_found"}

        t_len = user32.GetWindowTextLengthW(hwnd)
        t_buf = ctypes.create_unicode_buffer(t_len + 1)
        user32.GetWindowTextW(hwnd, t_buf, t_len + 1)
        title = t_buf.value.strip()

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        is_minimized = bool(user32.IsIconic(hwnd))
        is_zoomed = bool(user32.IsZoomed(hwnd))
        state_str = "minimized" if is_minimized else ("maximized" if is_zoomed else "normal")

        return {
            "hwnd": hwnd,
            "title": title,
            "state": state_str,
            "visible": bool(user32.IsWindowVisible(hwnd)),
            "foreground": user32.GetForegroundWindow() == hwnd,
            "rect": {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            },
        }

    def focus(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Bring window to foreground by HWND or title."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        res = PYWINAUTO_ADAPTER.focus_window(target)
        if res.get("success") and context and res.get("hwnd"):
            context.bound_hwnd = res["hwnd"]
        return res

    def move(self, target: str | int, x: int, y: int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Move window to (x, y) coordinates."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = self.find_window(str(target), context=context)
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}

        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        ok = bool(user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004))
        return {"success": ok, "hwnd": hwnd, "x": x, "y": y, "width": w, "height": h}

    def resize(self, target: str | int, width: int, height: int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Resize window to specified width and height."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = self.find_window(str(target), context=context)
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}

        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        x = rect.left
        y = rect.top

        ok = bool(user32.SetWindowPos(hwnd, 0, x, y, width, height, 0x0004))
        return {"success": ok, "hwnd": hwnd, "width": width, "height": height}

    def minimize(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Minimize window."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = self.find_window(str(target), context=context)
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}
        ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        return {"success": True, "hwnd": hwnd, "method": "win32_minimize"}

    def maximize(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Maximize window."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = self.find_window(str(target), context=context)
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}
        ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        return {"success": True, "hwnd": hwnd, "method": "win32_maximize"}

    def restore(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Restore window to normal state."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = self.find_window(str(target), context=context)
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return {"success": True, "hwnd": hwnd, "method": "win32_restore"}

    def close(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Close window gracefully via WM_CLOSE."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = self.find_window(str(target), context=context)
            if win:
                hwnd = win.get("hwnd")
        return PYWINAUTO_ADAPTER.close_window(hwnd) if hwnd else {"success": False, "error": f"Window '{target}' not found."}


    focus_window = focus
    close_window = close
    window_state = get_state


WINDOW_DOMAIN = WindowDomainHandler()
