"""
PLUTON V2 — Critical Safety Incident Containment Test Suite
Formally verifies the 10 Security & Zero-Input Invariants (A through J).
"""

import asyncio
import os
import sys
import time
import pytest
import pyautogui

from app.database import SessionLocal, reconcile_stale_tasks
from app.models import Task, TaskStatus
from app.core.contracts import ExecutionContext, CapabilityType
from app.kernel.control_kernel import KERNEL
from app.kernel.input_interceptor import PHYSICAL_INPUT_INTERCEPTOR, ComputerControlDenied
from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
from app.subsystems.computer.domains.mouse import MOUSE_DOMAIN
from app.subsystems.computer.domains.keyboard import KEYBOARD_DOMAIN
from app.subsystems.computer.domains.screen import SCREEN_DOMAIN


@pytest.fixture(autouse=True)
def clean_security_state():
    """Ensure kernel and task registry are clean before and after every test."""
    KERNEL.emergency_stop()
    ACTIVE_TASK_REGISTRY.purge_all(reason="test_setup")
    PHYSICAL_INPUT_INTERCEPTOR.reset_audit_log()
    yield
    KERNEL.emergency_stop()
    ACTIVE_TASK_REGISTRY.purge_all(reason="test_teardown")
    PHYSICAL_INPUT_INTERCEPTOR.reset_audit_log()


# -----------------------------------------------------------------------------
# Invariant H: Unauthorized Direct Input Hard Blocked with ComputerControlDenied
# -----------------------------------------------------------------------------

def test_unauthorized_pyautogui_mouse_click_hard_blocked():
    """Assert that direct pyautogui.click() raises ComputerControlDenied when idle."""
    assert not KERNEL.is_authorized()

    with pytest.raises(ComputerControlDenied) as exc_info:
        pyautogui.click(100, 100)

    assert "CRITICAL_SAFETY_VIOLATION" in str(exc_info.value)
    assert "mouse.click" in str(exc_info.value)

    # Check audit log recorded the blocked event
    records = PHYSICAL_INPUT_INTERCEPTOR.get_audit_log()
    assert len(records) >= 1
    assert records[-1]["authorized"] is False
    assert records[-1]["input_type"] == "mouse.click"


def test_unauthorized_pyautogui_keyboard_type_hard_blocked():
    """Assert that direct pyautogui.write() raises ComputerControlDenied when idle."""
    assert not KERNEL.is_authorized()

    with pytest.raises(ComputerControlDenied) as exc_info:
        pyautogui.write("malicious rogue text")

    assert "CRITICAL_SAFETY_VIOLATION" in str(exc_info.value)
    assert "keyboard.type" in str(exc_info.value)


def test_unauthorized_domain_handler_calls_hard_blocked():
    """Assert that calling MOUSE_DOMAIN or KEYBOARD_DOMAIN directly raises ComputerControlDenied when idle."""
    assert not KERNEL.is_authorized()

    with pytest.raises(ComputerControlDenied):
        MOUSE_DOMAIN.click(200, 200)

    with pytest.raises(ComputerControlDenied):
        KEYBOARD_DOMAIN.type("rogue keystrokes")

    with pytest.raises(ComputerControlDenied):
        SCREEN_DOMAIN.capture()


# -----------------------------------------------------------------------------
# Invariant A: Idle Desktop Invariant — Zero Physical Input When Idle
# -----------------------------------------------------------------------------

def test_idle_desktop_zero_input_invariant():
    """Verify that when Pluton is idle, exactly zero active tasks exist and any input attempt fails."""
    assert ACTIVE_TASK_REGISTRY.count() == 0
    assert not KERNEL.is_authorized()

    audit_before = len(PHYSICAL_INPUT_INTERCEPTOR.get_audit_log())
    time.sleep(0.1)
    audit_after = len(PHYSICAL_INPUT_INTERCEPTOR.get_audit_log())

    assert audit_after == audit_before == 0


# -----------------------------------------------------------------------------
# Invariant B & C: Post-Completion and Post-Cancellation Invariants
# -----------------------------------------------------------------------------

def test_post_completion_token_revocation_and_zero_input():
    """Verify that after a task completes, its token is revoked and subsequent input is blocked."""
    task_id = "test-completed-task-1"
    token = KERNEL.authorize_task(task_id, ttl_seconds=60.0)
    assert KERNEL.is_authorized(task_id)
    assert ACTIVE_TASK_REGISTRY.count() == 1

    # Simulate completion
    KERNEL.revoke_task(task_id)
    assert not KERNEL.is_authorized(task_id)
    assert ACTIVE_TASK_REGISTRY.count() == 0

    # Input attempt after completion must be hard blocked
    with pytest.raises(ComputerControlDenied):
        pyautogui.click(50, 50)


def test_post_cancellation_token_revocation_and_zero_input():
    """Verify that after task cancellation, its token is revoked and subsequent input is blocked."""
    task_id = "test-cancelled-task-1"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)
    assert KERNEL.is_authorized(task_id)

    # Mark cancelled
    ctx.mark_cancelled("User requested stop")
    assert not KERNEL.is_authorized(task_id)

    # Input attempt after cancellation must be hard blocked
    with pytest.raises(ComputerControlDenied):
        pyautogui.press("enter")


# -----------------------------------------------------------------------------
# Invariant D: SSE Disconnect Handling
# -----------------------------------------------------------------------------

def test_sse_disconnect_revokes_token_and_purges_registry():
    """Verify that simulating an SSE disconnect revokes the token and purges the task."""
    task_id = "test-disconnect-task-1"
    KERNEL.authorize_task(task_id)
    assert KERNEL.is_authorized(task_id)
    assert ACTIVE_TASK_REGISTRY.count() == 1

    # Simulate disconnect handler execution
    KERNEL.revoke_task(task_id)
    ACTIVE_TASK_REGISTRY.mark_cancelled(task_id, reason="client_disconnected")
    ACTIVE_TASK_REGISTRY.unregister_task(task_id, reason="client_disconnected")

    assert not KERNEL.is_authorized(task_id)
    assert ACTIVE_TASK_REGISTRY.count() == 0

    with pytest.raises(ComputerControlDenied):
        pyautogui.moveTo(500, 500)


# -----------------------------------------------------------------------------
# Invariant E: Approval Waiting Invariant — Zero Input While Awaiting Confirmation
# -----------------------------------------------------------------------------

def test_approval_waiting_zero_input_invariant():
    """Verify that while a task is in CONFIRMING status awaiting approval, no physical input is authorized."""
    task_id = "test-confirming-task-1"
    db = SessionLocal()
    task = Task(title="approval test", request="dangerous action", status=TaskStatus.CONFIRMING.value)
    db.add(task)
    db.commit()
    db.close()

    # While awaiting confirmation, kernel token is not active
    assert not KERNEL.is_authorized(task_id)

    with pytest.raises(ComputerControlDenied):
        pyautogui.write("should not execute")


# -----------------------------------------------------------------------------
# Invariant F & G: Stale Task Database Recovery & Server Restart Invariant
# -----------------------------------------------------------------------------

def test_stale_task_recovery_and_restart_invariant():
    """Verify that stale tasks in DB are sanitized on startup and no token survives."""
    db = SessionLocal()
    stale_1 = Task(title="stale running", request="work", status=TaskStatus.RUNNING.value)
    stale_2 = Task(title="stale executing", request="work", status="EXECUTING")
    db.add_all([stale_1, stale_2])
    db.commit()
    db.refresh(stale_1)
    db.refresh(stale_2)
    t1_id, t2_id = stale_1.id, stale_2.id
    db.close()

    # Simulate server startup reconciliation
    reconcile_stale_tasks()

    db = SessionLocal()
    t1_after = db.get(Task, t1_id)
    t2_after = db.get(Task, t2_id)
    assert t1_after.status in (TaskStatus.CANCELLED.value, TaskStatus.FAILED.value)
    assert t2_after.status in (TaskStatus.CANCELLED.value, TaskStatus.FAILED.value)
    db.close()

    assert not KERNEL.is_authorized()
    assert ACTIVE_TASK_REGISTRY.count() == 0


# -----------------------------------------------------------------------------
# Invariant I: Duplicate Execution Isolation
# -----------------------------------------------------------------------------

def test_duplicate_task_execution_isolation():
    """Verify that two concurrent or sequential tasks receive isolated tokens and do not collide."""
    task_1 = "task-isolation-1"
    task_2 = "task-isolation-2"

    token_1 = KERNEL.authorize_task(task_1)
    assert KERNEL.is_authorized(task_1)
    assert not KERNEL.is_authorized(task_2)

    # Authorizing task_2 preempts and revokes task_1
    token_2 = KERNEL.authorize_task(task_2)
    assert KERNEL.is_authorized(task_2)
    assert not KERNEL.is_authorized(task_1)


# -----------------------------------------------------------------------------
# Invariant J: Emergency Kill Switch
# -----------------------------------------------------------------------------

def test_emergency_kill_switch_immediate_halt():
    """Verify that emergency_stop immediately revokes all tokens, cancels tasks, and blocks all input."""
    task_id = "test-kill-switch-task"
    KERNEL.authorize_task(task_id)
    assert KERNEL.is_authorized(task_id)

    res = KERNEL.emergency_stop()
    assert res["stopped"] is True
    assert res["revoked_task"] == task_id
    assert not KERNEL.is_authorized(task_id)
    assert ACTIVE_TASK_REGISTRY.count() == 0

    with pytest.raises(ComputerControlDenied):
        pyautogui.click(10, 10)
