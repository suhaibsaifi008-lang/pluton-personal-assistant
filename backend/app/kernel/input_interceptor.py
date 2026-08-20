"""
PLUTON V2 — Lowest-Boundary Physical Input Interceptor
Intercepts and validates ALL low-level mouse, keyboard, and screen capture calls.

Hard Invariant:
    if not KERNEL.is_authorized(task_id):
        raise ComputerControlDenied(...)
"""

from __future__ import annotations

import functools
import inspect
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import pyautogui

logger = logging.getLogger("pluton.kernel.interceptor")


class ComputerControlDenied(PermissionError, RuntimeError):
    """Raised when any computer input is attempted without an active authorized user task."""
    pass


@dataclass
class InputAuditRecord:
    timestamp: str
    task_id: str | None
    input_type: str
    caller: str
    authorized: bool
    details: dict[str, Any]


class PhysicalInputInterceptor:
    """Guards the absolute lowest computer input boundary before the OS driver."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._audit_log: list[InputAuditRecord] = []
        self._is_hooked = False
        self._orig_pyautogui_funcs: dict[str, Any] = {}

    def install_hooks(self) -> None:
        """Wrap PyAutoGUI low-level physical functions with the Kernel authorization check."""
        with self._lock:
            if self._is_hooked:
                return

            funcs_to_wrap = [
                ("click", "mouse.click"),
                ("rightClick", "mouse.right_click"),
                ("doubleClick", "mouse.double_click"),
                ("tripleClick", "mouse.triple_click"),
                ("middleClick", "mouse.middle_click"),
                ("mouseDown", "mouse.down"),
                ("mouseUp", "mouse.up"),
                ("moveTo", "mouse.move"),
                ("moveRel", "mouse.move"),
                ("dragTo", "mouse.drag"),
                ("dragRel", "mouse.drag"),
                ("scroll", "mouse.scroll"),
                ("hscroll", "mouse.scroll"),
                ("vscroll", "mouse.scroll"),
                ("write", "keyboard.type"),
                ("typewrite", "keyboard.type"),
                ("press", "keyboard.press"),
                ("keyDown", "keyboard.key_down"),
                ("keyUp", "keyboard.key_up"),
                ("hotkey", "keyboard.hotkey"),
                ("screenshot", "screen.capture"),
            ]

            for func_name, input_type in funcs_to_wrap:
                if hasattr(pyautogui, func_name):
                    orig_func = getattr(pyautogui, func_name)
                    self._orig_pyautogui_funcs[func_name] = orig_func
                    setattr(pyautogui, func_name, self._create_guarded_wrapper(orig_func, input_type, func_name))

            self._is_hooked = True
            logger.info("[INPUT_INTERCEPTOR] Installed lowest-boundary physical input interceptors on %d PyAutoGUI functions.", len(funcs_to_wrap))

    def _create_guarded_wrapper(self, orig_func: Callable[..., Any], input_type: str, func_name: str) -> Callable[..., Any]:
        @functools.wraps(orig_func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from .control_kernel import KERNEL
            # Check Kernel Authorization
            active_token = getattr(KERNEL, "_active_token", None)
            is_valid = KERNEL.is_authorized()
            task_id = active_token.task_id if (active_token and active_token.is_valid) else None

            caller_frame = inspect.currentframe()
            caller_desc = "unknown"
            if caller_frame and caller_frame.f_back:
                f_back = caller_frame.f_back
                caller_desc = f"{f_back.f_code.co_filename}:{f_back.f_lineno} ({f_back.f_code.co_name})"

            # Record audit event
            audit_entry = InputAuditRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                task_id=task_id,
                input_type=input_type,
                caller=caller_desc,
                authorized=is_valid,
                details={"args": str(args)[:100], "kwargs": str(kwargs)[:100]},
            )
            with self._lock:
                self._audit_log.append(audit_entry)
                if len(self._audit_log) > 1000:
                    self._audit_log.pop(0)

            if not is_valid:
                err_msg = (
                    f"CRITICAL_SAFETY_VIOLATION: Unauthorized physical computer input '{input_type}' "
                    f"attempted while Pluton is idle (Caller: {caller_desc}). Hard blocked."
                )
                logger.error("[INPUT_INTERCEPTOR] %s", err_msg)
                raise ComputerControlDenied(err_msg)

            # Authorized -> execute low-level physical input
            return orig_func(*args, **kwargs)

        return wrapper

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return structured audit logs for developer inspection."""
        with self._lock:
            return [
                {
                    "timestamp": r.timestamp,
                    "task_id": r.task_id,
                    "input_type": r.input_type,
                    "caller": r.caller,
                    "authorized": r.authorized,
                    "details": r.details,
                }
                for r in self._audit_log[-limit:]
            ]

    def reset_audit_log(self) -> None:
        with self._lock:
            self._audit_log.clear()


PHYSICAL_INPUT_INTERCEPTOR = PhysicalInputInterceptor()
# Install automatically on module load
PHYSICAL_INPUT_INTERCEPTOR.install_hooks()
