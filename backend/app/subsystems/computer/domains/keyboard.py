"""
PLUTON V2 — Keyboard Domain Handler
Implements canonical keyboard input:
keyboard.type, keyboard.press, keyboard.hotkey, keyboard.copy, keyboard.paste, keyboard.cut, keyboard.undo, keyboard.redo.
"""

from __future__ import annotations

from typing import Any
import pyautogui

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL
from app.tools.keyboard_pipeline import type_into_window


class KeyboardDomainHandler:
    """Canonical handler for verified target-bound keyboard input."""

    def type_text(
        self,
        text: str,
        hwnd: int = 0,
        pid: int = 0,
        target: str | None = None,
        target_window: str | None = None,
        expected_text: str | None = None,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Type text into window using verified TARGET -> FOCUS -> INPUT -> VERIFY pipeline."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from app.tools.uia_engine import UIA_ENGINE

        target_app = target_window or (target if target and any(k in target.lower() for k in ("notepad", "calc", "explorer", "cmd", "wordpad")) else None)
        target_hwnd = hwnd
        target_pid = pid

        if target_app:
            found_win = UIA_ENGINE.find_window(target_app)
            if found_win:
                target_hwnd = found_win["hwnd"]
                target_pid = found_win.get("pid", 0)
                if context:
                    context.bound_hwnd = target_hwnd
                    context.bound_pid = target_pid
                    context.workflow_context.active_hwnd = target_hwnd
                    context.workflow_context.active_pid = target_pid

        if not target_hwnd:
            target_hwnd = context.bound_hwnd if context else 0
            target_pid = context.bound_pid if context else 0

        return type_into_window(
            hwnd=target_hwnd,
            pid=target_pid,
            text=text,
            expected_text=expected_text or text,
        )

    type = type_text

    def press(self, key: str, target_window: str | None = None, context: ExecutionContext | None = None, **kwargs: Any) -> dict[str, Any]:
        """Press a single key."""
        KERNEL.assert_authorized(context.task_id if context else None)
        cleaned = key.strip().lower()
        if not cleaned:
            return {"success": False, "error": "Empty key name."}
        if cleaned in ("power", "sleep", "wakeup"):
            return {"success": False, "error": f"Disruptive key '{cleaned}' blocked."}

        if target_window:
            from app.tools.uia_engine import UIA_ENGINE
            UIA_ENGINE.focus_window(target_window)

        pyautogui.press(cleaned)
        return {"success": True, "key": cleaned}

    def hotkey(self, keys: list[str] | str, target_window: str | None = None, context: ExecutionContext | None = None, **kwargs: Any) -> dict[str, Any]:
        """Execute key combination (e.g. ['ctrl', 'a'] or 'ctrl+c')."""
        KERNEL.assert_authorized(context.task_id if context else None)
        key_list = keys.split("+") if isinstance(keys, str) else list(keys)
        clean_keys = [k.strip().lower() for k in key_list if k.strip()]
        if not clean_keys:
            return {"success": False, "error": "Empty hotkey list."}

        if target_window:
            from app.tools.uia_engine import UIA_ENGINE
            UIA_ENGINE.focus_window(target_window)

        pyautogui.hotkey(*clean_keys)
        return {"success": True, "keys": clean_keys}

    def copy(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Execute Ctrl+C with clipboard settlement."""
        import time
        res = self.hotkey(["ctrl", "c"], context=context)
        time.sleep(0.05)
        return res

    def paste(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Execute Ctrl+V with input settlement."""
        import time
        res = self.hotkey(["ctrl", "v"], context=context)
        time.sleep(0.05)
        return res

    def cut(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Execute Ctrl+X with clipboard settlement."""
        import time
        res = self.hotkey(["ctrl", "x"], context=context)
        time.sleep(0.05)
        return res

    def undo(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Execute Ctrl+Z."""
        return self.hotkey(["ctrl", "z"], context=context)

    def redo(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Execute Ctrl+Y."""
        return self.hotkey(["ctrl", "y"], context=context)


KEYBOARD_DOMAIN = KeyboardDomainHandler()
