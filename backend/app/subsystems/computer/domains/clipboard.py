"""
PLUTON V2 — Clipboard Domain Handler
Implements canonical clipboard capabilities:
clipboard.get, clipboard.set, clipboard.clear.
"""

from __future__ import annotations

import logging
from typing import Any
import pyautogui

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL

logger = logging.getLogger("pluton.computer.clipboard")


class ClipboardDomainHandler:
    """Canonical handler for system clipboard interactions."""

    def get(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get current text from system clipboard."""
        KERNEL.assert_authorized(context.task_id if context else None)
        try:
            import pyperclip
            text = pyperclip.paste()
            return {"success": True, "content": text, "length": len(text)}
        except Exception as e:
            return {"success": False, "error": f"Failed to get clipboard: {e}"}

    def set(self, content: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Set text into system clipboard."""
        KERNEL.assert_authorized(context.task_id if context else None)
        try:
            import pyperclip
            pyperclip.copy(content)
            return {"success": True, "content": content, "length": len(content)}
        except Exception as e:
            return {"success": False, "error": f"Failed to set clipboard: {e}"}

    def clear(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Clear system clipboard."""
        KERNEL.assert_authorized(context.task_id if context else None)
        try:
            import pyperclip
            pyperclip.copy("")
            return {"success": True, "cleared": True}
        except Exception as e:
            return {"success": False, "error": f"Failed to clear clipboard: {e}"}


CLIPBOARD_DOMAIN = ClipboardDomainHandler()
