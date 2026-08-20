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
        return UIA_ENGINE.list_windows(visible_only=visible_only)

    list = list_windows

    def find_window(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any] | None:
        """Find a window by title, HWND, or PID."""
        KERNEL.assert_authorized(context.task_id if context else None)
        if isinstance(target, int):
            wins = UIA_ENGINE.list_windows(visible_only=False)
            return next((w for w in wins if w.get("hwnd") == target or w.get("pid") == target), None)
        return UIA_ENGINE.find_window(str(target))

    find = find_window

    def get_foreground_window(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get canonical structured metadata about active foreground window."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return UIA_ENGINE.get_foreground_window()

    def get_state(self, target: str | int | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get structured state of a window or the active foreground window."""
        KERNEL.assert_authorized(context.task_id if context else None)
        attach_interactive_desktop()
        user32 = ctypes.windll.user32

        hwnd = target if isinstance(target, int) else None
        if not hwnd and target:
            win = UIA_ENGINE.find_window(str(target))
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
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = UIA_ENGINE.find_window(str(target))
            if win:
                hwnd = win.get("hwnd")

        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}

        ok = UIA_ENGINE.focus_window(hwnd)
        if context:
            context.bound_hwnd = hwnd
        return {"success": ok, "hwnd": hwnd, "method": "uia_focus"}

    def move(self, target: str | int, x: int, y: int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Move window to (x, y) coordinates."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = UIA_ENGINE.find_window(str(target))
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}

        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        # SetWindowPos with SWP_NOZORDER (0x0004)
        ok = bool(user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004))
        return {"success": ok, "hwnd": hwnd, "x": x, "y": y, "width": w, "height": h}

    def resize(self, target: str | int, width: int, height: int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Resize window to specified width and height."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = UIA_ENGINE.find_window(str(target))
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
        return self._send_sys_command(target, 0xF020)  # SC_MINIMIZE

    def maximize(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Maximize window."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return self._send_sys_command(target, 0xF030)  # SC_MAXIMIZE

    def restore(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Restore window to normal state."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return self._send_sys_command(target, 0xF120)  # SC_RESTORE

    def close(self, target: str | int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Close window gracefully via WM_CLOSE."""
        KERNEL.assert_authorized(context.task_id if context else None)
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = UIA_ENGINE.find_window(str(target))
            if win:
                hwnd = win.get("hwnd")

        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}

        ok = UIA_ENGINE.close_window(hwnd)
        return {"success": ok, "hwnd": hwnd, "method": "uia_close_window"}

    def _send_sys_command(self, target: str | int, cmd: int) -> dict[str, Any]:
        hwnd = target if isinstance(target, int) else None
        if not hwnd:
            win = UIA_ENGINE.find_window(str(target))
            if win:
                hwnd = win.get("hwnd")
        if not hwnd:
            return {"success": False, "error": f"Window '{target}' not found."}

        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            user32.PostMessageW(hwnd, 0x0112, cmd, 0)
            return {"success": True, "hwnd": hwnd, "command": hex(cmd)}

        return {"success": False, "error": "Not supported on non-Windows OS."}


    focus_window = focus
    close_window = close
    window_state = get_state


WINDOW_DOMAIN = WindowDomainHandler()
