"""
PLUTON V2 — Screen Domain Handler
Implements screen capture and inspection:
screen.capture, screen.inspect.
"""

from __future__ import annotations

import base64
import io
from typing import Any
from PIL import Image
import pyautogui

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL


class ScreenDomainHandler:
    """Canonical handler for display capture and screen region inspection."""

    def capture(self, region: tuple[int, int, int, int] | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Capture screen as PIL Image and base64 string."""
        KERNEL.assert_authorized(context.task_id if context else None)
        screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return {
            "success": True,
            "width": screenshot.width,
            "height": screenshot.height,
            "base64": b64_str,
            "image": screenshot,
        }

    def inspect(self, region: tuple[int, int, int, int] | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Inspect screen geometry, resolution, and monitor bounds."""
        KERNEL.assert_authorized(context.task_id if context else None)
        size = pyautogui.size()
        cap = self.capture(region=region, context=context)
        return {
            "success": True,
            "screen_width": size.width,
            "screen_height": size.height,
            "region": region,
            "image_width": cap.get("width"),
            "image_height": cap.get("height"),
        }


SCREEN_DOMAIN = ScreenDomainHandler()
