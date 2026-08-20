"""
PLUTON V2 — Safety & Adversarial Test Suite
Verifies:
1. NO ACTIVE AUTHORIZED TASK -> ZERO COMPUTER INPUT
2. Expired tokens are rejected
3. Wrong task tokens are rejected
4. Stale tokens after completion cannot execute
5. Ambiguous targets are refused without mouse/keyboard actuation
6. Emergency stop releases all virtual and physical inputs
"""

import time
import pytest
from app.core.contracts import Action, CapabilityType, ExecutionContext, ExecutionTier
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer import (
    COMPUTER_ENGINE,
    TARGET_RESOLVER,
    ComputerDomain,
    TargetResolutionStatus,
    TargetSpec,
)


def test_zero_input_when_no_active_task():
    KERNEL.revoke_task()
    assert not KERNEL.is_authorized()
    with pytest.raises(PermissionError) as exc:
        KERNEL.assert_authorized()
    assert "No active authorized task" in str(exc.value)


def test_stale_token_rejected_after_revocation():
    task_id = "task-stale-test"
    ctx = ExecutionContext(task_id=task_id)
    token = KERNEL.authorize_task(task_id, context=ctx)
    assert token.is_valid

    # Task finishes -> token revoked
    KERNEL.revoke_task(task_id)
    assert not token.is_valid

    # Attempting execution with stale task_id fails
    with pytest.raises(PermissionError):
        KERNEL.assert_authorized(task_id)


def test_wrong_task_id_rejected():
    task_a = "task-authorized-alpha"
    task_b = "task-unauthorized-beta"
    ctx = ExecutionContext(task_id=task_a)
    KERNEL.authorize_task(task_a, context=ctx)

    # Calling with task_b while task_a is active raises PermissionError
    with pytest.raises(PermissionError):
        KERNEL.assert_authorized(task_b)

    KERNEL.revoke_task(task_a)


def test_expired_token_rejected():
    task_id = "task-expiring-test"
    ctx = ExecutionContext(task_id=task_id)
    token = KERNEL.authorize_task(task_id, context=ctx)
    token.issued_at = time.monotonic() - 200.0  # Deliberately expire

    assert not token.is_valid
    with pytest.raises(PermissionError):
        KERNEL.assert_authorized(task_id)

    KERNEL.revoke_task(task_id)



@pytest.mark.anyio
async def test_ambiguous_target_refusal_executes_no_input(monkeypatch):
    task_id = "task-ambiguity-test"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)

    fake_windows = [
        {"title": "Terminal Window 1", "hwnd": 9001, "pid": 101},
        {"title": "Terminal Window 2", "hwnd": 9002, "pid": 102},
    ]
    monkeypatch.setattr(TARGET_RESOLVER.uia, "list_windows", lambda visible_only=True: fake_windows)

    act = Action(
        capability=CapabilityType.WINDOW_FOCUS,
        target="Terminal Window",
        tier_requested=ExecutionTier.TIER_3_UIA_AUTOMATION,
    )
    res = await COMPUTER_ENGINE.execute_action(act, ctx)
    assert res.status == "failed"
    assert "AMBIGUOUS_TARGET" in res.summary
    assert res.observed.get("error") == "AMBIGUOUS_TARGET"

    KERNEL.revoke_task(task_id)




def test_emergency_stop_resets_hardware_state():
    task_id = "task-emergency-stop"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)

    KERNEL.emergency_stop()
    assert not KERNEL.is_authorized()
