"""Universal Computer-Control Safety Gate & Emergency Kill Switch.

Enforces the Hard Safety Invariant:
NO ACTIVE USER TASK -> ZERO INPUT
(No mouse, no keyboard, no screenshots, no vision actions, no UIA actions, no retries).

This module delegates directly to the canonical V2 ComputerControlKernel.
"""

from typing import Any
from ..kernel.control_kernel import KERNEL



def enable_computer_control(task_id: str) -> None:
    """Explicitly enable computer control bound to the specified active task."""
    KERNEL.authorize_task(task_id)


def disable_computer_control(task_id: str | None = None) -> None:
    """Revoke computer control immediately."""
    KERNEL.revoke_task(task_id)


def is_computer_control_allowed(task_id: str | None = None) -> bool:
    """Check whether computer control is currently permitted."""
    return KERNEL.is_authorized(task_id)


def assert_computer_control_allowed(task_id: str | None = None) -> None:
    """Raise PermissionError if computer control is not explicitly permitted."""
    KERNEL.assert_authorized(task_id)


def emergency_kill_computer_input() -> dict[str, Any]:
    """Emergency function: instantly halts all mouse/keyboard input and releases held state."""
    return KERNEL.emergency_stop()


class ComputerControlContext:
    """Context manager for task-scoped computer control."""

    def __init__(self, task_id: str):
        self.task_id = task_id

    def __enter__(self):
        enable_computer_control(self.task_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        disable_computer_control(self.task_id)
        emergency_kill_computer_input()
