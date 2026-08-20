"""PLUTON V2 Computer Control Kernel.

The Kernel is the authoritative security boundary for all physical and OS-level
computer control (mouse, keyboard, UIA, screen capture, process interaction).

Hard Invariant:
    NO ACTIVE AUTHORIZED TASK = ZERO COMPUTER INPUT
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pyautogui

from ..core.contracts import CapabilityType, ExecutionContext

logger = logging.getLogger("pluton.kernel")

# PyAutoGUI baseline safety configuration
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.01
pyautogui.MINIMUM_DURATION = 0


@dataclass
class KernelToken:
    task_id: str
    issued_at: float = field(default_factory=time.monotonic)
    ttl_seconds: float = 120.0
    revoked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        if self.revoked:
            return False
        return (time.monotonic() - self.issued_at) < self.ttl_seconds


from .input_interceptor import ComputerControlDenied, PHYSICAL_INPUT_INTERCEPTOR
from .task_registry import ACTIVE_TASK_REGISTRY


class ComputerControlKernel:
    """Universal gatekeeper for all desktop, keyboard, mouse, and screen interactions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_token: KernelToken | None = None
        self._active_context: ExecutionContext | None = None

    # -------------------------------------------------------------------------
    # Authorization & Lifecycle Management
    # -------------------------------------------------------------------------

    def authorize_task(self, task_id: str, ttl_seconds: float = 120.0, context: ExecutionContext | None = None) -> KernelToken:
        """Issue an authorized kernel capability token bound exclusively to a task."""
        if isinstance(ttl_seconds, ExecutionContext):
            context = ttl_seconds
            ttl_seconds = 120.0
        with self._lock:

            # If an existing token is active for a different task, revoke and flush input
            if self._active_token and self._active_token.task_id != task_id:
                logger.warning("[KERNEL] Preempting active token for task %s with new task %s", self._active_token.task_id, task_id)
                self._active_token.revoked = True
                ACTIVE_TASK_REGISTRY.mark_cancelled(self._active_token.task_id, reason="preempted")
                self._emergency_flush_inputs()

            token = KernelToken(task_id=task_id, ttl_seconds=ttl_seconds)
            self._active_token = token
            self._active_context = context or ExecutionContext(task_id=task_id, timeout_seconds=ttl_seconds)
            ACTIVE_TASK_REGISTRY.register_task(task_id=task_id, session_id=getattr(context, "session_id", None) if context else None)
            logger.info("[KERNEL] Authorized computer-control token for task: %s (TTL: %.1fs)", task_id, ttl_seconds)
            return token

    def revoke_task(self, task_id: str | None = None) -> None:
        """Revoke computer-control authorization and flush any held input state."""
        with self._lock:
            if self._active_token is None:
                return

            if task_id is None or self._active_token.task_id == task_id:
                old_id = self._active_token.task_id
                self._active_token.revoked = True
                self._active_token = None
                self._active_context = None
                ACTIVE_TASK_REGISTRY.unregister_task(old_id, reason="revoked")
                self._emergency_flush_inputs()
                logger.info("[KERNEL] Revoked computer-control authorization for task: %s", old_id)

    def is_authorized(self, task_id: str | None = None) -> bool:
        """Check if computer control is actively authorized."""
        with self._lock:
            if not self._active_token or not self._active_token.is_valid:
                return False
            if task_id is not None and self._active_token.task_id != task_id:
                return False
            if self._active_context and self._active_context.is_cancelled:
                return False
            return True

    def assert_authorized(self, task_id: str | None = None, capability: CapabilityType | None = None) -> None:
        """Raise ComputerControlDenied immediately if the hard invariant is violated."""
        with self._lock:
            if not self.is_authorized(task_id):
                cap_str = f" for '{capability.value}'" if capability else ""
                active_id = self._active_token.task_id if self._active_token else "NONE"
                raise ComputerControlDenied(
                    f"Computer control BLOCKED{cap_str}: No active authorized task. "
                    f"(Requested task: {task_id or 'ANY'}, Active task: {active_id})"
                )

    # -------------------------------------------------------------------------
    # Emergency Stop & Input Flush
    # -------------------------------------------------------------------------

    def emergency_stop(self) -> dict[str, Any]:
        """Instantly revokes all capability tokens, releases all keys/mouse buttons, and halts input."""
        with self._lock:
            old_task = self._active_token.task_id if self._active_token else None
            if self._active_token:
                self._active_token.revoked = True
                self._active_token = None
            if self._active_context:
                self._active_context.mark_cancelled("Emergency stop triggered")
                self._active_context = None

            purged = ACTIVE_TASK_REGISTRY.purge_all(reason="emergency_kill_switch")
            self._emergency_flush_inputs()
            logger.warning("[KERNEL] EMERGENCY KILL SWITCH TRIGGERED: All input halted and held keys released (purged tasks: %s).", purged)
            return {
                "stopped": True,
                "revoked_task": old_task,
                "purged_tasks": purged,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Computer control revoked, all workers halted, and physical inputs flushed.",
            }

    def _emergency_flush_inputs(self) -> None:
        """Release physically held mouse buttons and modifier keys ONLY if they are currently down."""
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                # VK_LBUTTON = 0x01, VK_RBUTTON = 0x02, VK_MBUTTON = 0x04
                if user32.GetAsyncKeyState(0x01) & 0x8000:
                    user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
                if user32.GetAsyncKeyState(0x02) & 0x8000:
                    user32.mouse_event(0x0010, 0, 0, 0, 0)  # MOUSEEVENTF_RIGHTUP
                if user32.GetAsyncKeyState(0x04) & 0x8000:
                    user32.mouse_event(0x0040, 0, 0, 0, 0)  # MOUSEEVENTF_MIDDLEUP

                # Release modifier keys ONLY if physically held down (VK_CONTROL=0x11, VK_MENU=0x12, VK_SHIFT=0x10, VK_LWIN=0x5B, VK_RWIN=0x5C)
                for vk in (0x11, 0x12, 0x10, 0x5B, 0x5C):
                    if user32.GetAsyncKeyState(vk) & 0x8000:
                        user32.keybd_event(vk, 0, 0x0002, 0)  # KEYEVENTF_KEYUP
            except Exception:
                pass


# Global singleton instance
KERNEL = ComputerControlKernel()
ControlKernel = ComputerControlKernel


def emergency_stop_all_computer_control() -> dict[str, Any]:
    """Universal emergency stop helper callable from endpoints or tools."""
    return KERNEL.emergency_stop()
