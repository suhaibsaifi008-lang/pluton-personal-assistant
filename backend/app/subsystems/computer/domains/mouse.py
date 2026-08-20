"""
PLUTON V2 — Mouse Domain Handler (Hardened)
Implements canonical mouse interactions:
mouse.move, mouse.click, mouse.double_click, mouse.right_click, mouse.drag, mouse.scroll, mouse.position.
Enforces strict target validation, boundary checks, and authorization gating.
"""

from __future__ import annotations

import logging
import pyautogui
from typing import Any

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL

logger = logging.getLogger("pluton.computer.mouse")


class MouseDomainHandler:
    """Canonical handler for mouse movement and interaction with strict target validation."""

    def _get_screen_bounds(self) -> tuple[int, int]:
        """Return (width, height) of primary screen."""
        try:
            return pyautogui.size()
        except Exception:
            return (1920, 1080)

    def _validate_coordinates(self, x: int, y: int) -> bool:
        """Ensure coordinates are within valid physical screen bounds."""
        w, h = self._get_screen_bounds()
        return 0 <= x <= w and 0 <= y <= h

    def move(self, x: int, y: int, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Move mouse cursor to specific coordinates."""
        KERNEL.assert_authorized(context.task_id if context else None)
        if not self._validate_coordinates(x, y):
            return {"success": False, "error": f"Coordinates ({x}, {y}) out of physical screen bounds."}

        pyautogui.moveTo(x, y)
        return {"success": True, "x": x, "y": y}

    def click(
        self,
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        clicks: int = 1,
        target_description: str | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Click mouse button at verified coordinates."""
        KERNEL.assert_authorized(context.task_id if context else None)

        if x is None or y is None:
            return {
                "success": False,
                "error": "Coordinate mouse action rejected: Explicit (x, y) screen coordinates required. Blind clicking prohibited.",
            }

        if not self._validate_coordinates(x, y):
            return {
                "success": False,
                "error": f"Coordinate mouse click rejected: Target ({x}, {y}) is out of physical screen bounds.",
            }

        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return {
            "success": True,
            "x": x,
            "y": y,
            "button": button,
            "clicks": clicks,
            "target": target_description or f"({x}, {y})",
        }

    def double_click(
        self,
        x: int | None = None,
        y: int | None = None,
        target_description: str | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Double click left mouse button at target coordinates."""
        return self.click(x=x, y=y, button="left", clicks=2, target_description=target_description, context=context)

    def right_click(
        self,
        x: int | None = None,
        y: int | None = None,
        target_description: str | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Right click mouse button at target coordinates."""
        return self.click(x=x, y=y, button="right", clicks=1, target_description=target_description, context=context)

    def drag(
        self,
        start_x: int = 0,
        start_y: int = 0,
        end_x: int = 0,
        end_y: int = 0,
        source_target: str | None = None,
        destination_target: str | None = None,
        duration: float = 0.3,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Drag mouse from start to end coordinates, or semantic source to destination with state verification."""
        KERNEL.assert_authorized(context.task_id if context else None)

        # 1. Semantic Filesystem Drag & Drop
        if source_target and destination_target:
            import os
            from pathlib import Path
            src_p = Path(source_target).resolve()
            dst_p = Path(destination_target).resolve()
            if src_p.exists():
                # Verify BEFORE state
                if not src_p.exists():
                    return {"success": False, "error": f"DRAG_FAILED: Source target '{source_target}' does not exist before drag."}

                from .filesystem import FILESYSTEM_DOMAIN
                move_res = FILESYSTEM_DOMAIN.move(str(src_p), str(dst_p), context=context)

                # Verify AFTER state
                dst_verified = dst_p.exists() or (dst_p.is_dir() and (dst_p / src_p.name).exists())
                src_absent = not src_p.exists()
                if move_res.get("success") and dst_verified and src_absent:
                    return {
                        "success": True,
                        "method": "semantic_drag_drop",
                        "source": str(src_p),
                        "destination": str(dst_p),
                        "verified": True,
                        "message": f"Successfully dragged '{src_p.name}' into '{dst_p}' and verified destination existence.",
                    }
                return {"success": False, "error": f"DRAG_VERIFY_FAILED: After drag state mismatch: {move_res}"}

        # 2. Coordinate-based Mouse Drag
        if not self._validate_coordinates(start_x, start_y) or not self._validate_coordinates(end_x, end_y):
            return {"success": False, "error": f"Drag coordinates ({start_x}, {start_y}) -> ({end_x}, {end_y}) out of screen bounds."}

        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragTo(end_x, end_y, duration=duration)
        return {"success": True, "from": (start_x, start_y), "to": (end_x, end_y), "method": "coordinate_drag"}

    def scroll(
        self,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """Scroll vertical wheel at position."""
        KERNEL.assert_authorized(context.task_id if context else None)
        if x is not None and y is not None:
            if self._validate_coordinates(x, y):
                pyautogui.moveTo(x, y)
        pyautogui.scroll(clicks)
        return {"success": True, "clicks": clicks}

    def position(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get current mouse cursor position."""
        KERNEL.assert_authorized(context.task_id if context else None)
        pos = pyautogui.position()
        return {"success": True, "x": pos.x, "y": pos.y}


MOUSE_DOMAIN = MouseDomainHandler()
