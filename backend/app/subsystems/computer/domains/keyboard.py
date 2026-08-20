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
        """Type text into window using verified TARGET -> FOCUS -> INPUT pipeline."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER

        target_app = target_window or (target if target and any(k in target.lower() for k in ("notepad", "calc", "explorer", "cmd", "wordpad", "word", "paint")) else None)
        target_hwnd = hwnd

        if target_app:
            matched = PYWINAUTO_ADAPTER.find_windows_by_app(target_app)
            if matched:
                target_hwnd = matched[0]["hwnd"]
                target_pid = matched[0].get("pid", 0)
                if context:
                    context.bound_hwnd = target_hwnd
                    context.bound_pid = target_pid
                    context.workflow_context.active_hwnd = target_hwnd
                    context.workflow_context.active_pid = target_pid

        if not target_hwnd and context:
            target_hwnd = context.bound_hwnd or 0

        if target_hwnd:
            PYWINAUTO_ADAPTER.focus_window(target_hwnd)

        return PYWINAUTO_ADAPTER.type_text(text=text)

    type = type_text

    def press(self, key: str, target_window: str | None = None, context: ExecutionContext | None = None, **kwargs: Any) -> dict[str, Any]:
        """Press a single key."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        if target_window:
            PYWINAUTO_ADAPTER.focus_window(target_window)
        return PYWINAUTO_ADAPTER.press_key(key)

    def hotkey(self, keys: list[str] | str, target_window: str | None = None, context: ExecutionContext | None = None, **kwargs: Any) -> dict[str, Any]:
        """Execute key combination (e.g. ['ctrl', 'a'] or 'ctrl+c')."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        if target_window:
            PYWINAUTO_ADAPTER.focus_window(target_window)
        shortcut_str = "+".join(keys) if isinstance(keys, list) else str(keys)
        return PYWINAUTO_ADAPTER.send_shortcut(shortcut_str)

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
