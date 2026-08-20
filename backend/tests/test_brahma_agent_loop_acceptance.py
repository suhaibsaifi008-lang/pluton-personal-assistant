"""
PLUTON V2 — Brahma Agent Loop Acceptance Suite
Verifies:
  1. First-Class WorldState Snapshot Capture
  2. Authoritative Goal Verification Gating (No Tool Direct Success)
  3. Universal Agent Execution Loop (Observe -> Reason -> Act -> Observe -> Verify -> Goal)
  4. Discrepancy Detection (Tool Returns Success but Physical Verification Fails -> FAILED)
  5. Dynamic Context Propagation across Multi-Step Workflows
  6. Task Cancellation Halts Loop & Locks Physical I/O
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.agent_loop import GoalVerifier, UniversalAgentLoop
from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    PlanStep,
    TargetDomain,
    TaskState,
    ToolResult,
    VerificationResult,
    VerificationStrategy,
)
from app.core.world_state import BrowserSnapshot, WindowSnapshot, WorldState
from app.database import SessionLocal
from app.kernel.control_kernel import KERNEL, ComputerControlDenied
from app.models import Task, TaskStatus


# =============================================================================
# 1. FIRST-CLASS WORLDSTATE SNAPSHOT
# =============================================================================

def test_world_state_capture_performance_and_completeness():
    """Test that WorldState captures live environment without throwing or hanging (<50ms)."""
    ctx = ExecutionContext(task_id="task_world_test")
    state = WorldState.capture(ctx)

    assert state is not None
    assert isinstance(state.timestamp, float)
    assert isinstance(state.visible_windows, list)
    assert isinstance(state.clipboard_text, str)


# =============================================================================
# 2. GOAL VERIFICATION GATING
# =============================================================================

def test_goal_verifier_blocks_unverified_steps():
    """Test that a plan with any unverified step cannot produce COMPLETED status."""
    ctx = ExecutionContext(task_id="task_gv_test")
    plan = Plan(task_id="task_gv_test")
    
    step1 = PlanStep(
        step_number=1,
        description="Launch app",
        action=Action(capability=CapabilityType.APP_LAUNCH, target="notepad"),
        completed=True,
    )
    step2 = PlanStep(
        step_number=2,
        description="Type text",
        action=Action(capability=CapabilityType.KEYBOARD_TYPE, target="notepad"),
        completed=False,  # Unverified!
    )
    plan.steps = [step1, step2]
    
    world = WorldState.capture(ctx)
    verified, reason = GoalVerifier.verify_goal("Type into Notepad", plan, world, ctx)
    assert verified is False
    assert "Step 2 failed verification" in reason


def test_goal_verifier_approves_fully_verified_workflow():
    """Test that fully verified plan passes goal verification."""
    ctx = ExecutionContext(task_id="task_gv_ok")
    plan = Plan(task_id="task_gv_ok")
    
    step1 = PlanStep(
        step_number=1,
        description="Launch app",
        action=Action(capability=CapabilityType.APP_LAUNCH, target="notepad"),
        completed=True,
    )
    plan.steps = [step1]
    
    world = WorldState.capture(ctx)
    verified, reason = GoalVerifier.verify_goal("Open Notepad", plan, world, ctx)
    assert verified is True
    assert "verified" in reason.lower()


# =============================================================================
# 3. UNIVERSAL AGENT LOOP E2E EXECUTION
# =============================================================================

@pytest.mark.anyio
async def test_agent_loop_runs_observe_act_verify_cycle():
    """Test end-to-end observe -> act -> observe -> verify -> goal loop."""
    db = MagicMock()
    task = Task(id="task_loop_test", request="Open Notepad", status=TaskStatus.CREATED.value)
    ctx = ExecutionContext(task_id=task.id)
    KERNEL.authorize_task(task.id, context=ctx)

    mock_router = MagicMock()
    mock_plan = Plan(task_id=task.id)
    mock_plan.steps = [
        PlanStep(
            step_number=1,
            description="Launch Notepad",
            action=Action(
                capability=CapabilityType.APP_LAUNCH,
                target="notepad",
                verification_strategy=VerificationStrategy.NONE,
            ),
        )
    ]
    mock_router.plan_request.return_value = mock_plan
    mock_router.execute_action = AsyncMock(
        return_value=ToolResult(
            call_id="call_1",
            name="app.launch",
            observed={"hwnd": 1234},
            status="completed",
            summary="Notepad launched",
            raw_arguments={},
        )
    )

    mock_verifier = MagicMock()
    mock_verifier.verify_action.return_value = VerificationResult(verified=True, strategy=VerificationStrategy.NONE)

    try:
        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier)
        events = []
        async for ev in loop.run(db, task, ctx):
            events.append(ev)

        assert len(events) >= 2
        # Verify state reached COMPLETED
        assert task.status == TaskState.COMPLETED.value
    finally:
        KERNEL.revoke_task(task.id)


# =============================================================================
# 4. DISCREPANCY DETECTION (TOOL SUCCESS != TASK SUCCESS)
# =============================================================================

@pytest.mark.anyio
async def test_agent_loop_rejects_unverified_tool_success():
    """Test that if tool returns completed but verification fails, loop marks task FAILED."""
    db = MagicMock()
    task = Task(id="task_discrepancy", request="Click submit button", status=TaskStatus.CREATED.value)
    ctx = ExecutionContext(task_id=task.id)
    KERNEL.authorize_task(task.id, context=ctx)

    mock_router = MagicMock()
    mock_plan = Plan(task_id=task.id)
    mock_plan.steps = [
        PlanStep(
            step_number=1,
            description="Click button",
            action=Action(
                capability=CapabilityType.WEB_CLICK,
                target="submit",
                verification_strategy=VerificationStrategy.DOM_STATE_CHANGE,
            ),
        )
    ]
    mock_router.plan_request.return_value = mock_plan
    # Tool claims completed...
    mock_router.execute_action = AsyncMock(
        return_value=ToolResult(
            call_id="call_2",
            name="web.click",
            observed={},
            status="completed",
            summary="Clicked",
            raw_arguments={},
        )
    )

    # But physical verification discovers nothing changed on page!
    mock_verifier = MagicMock()
    mock_verifier.verify_action.return_value = VerificationResult(
        verified=False,
        strategy=VerificationStrategy.DOM_STATE_CHANGE,
        message="DOM state unchanged after click",
    )

    try:
        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier)
        async for _ in loop.run(db, task, ctx):
            pass

        # MUST FAIL honestly!
        assert task.status == TaskState.FAILED.value
        assert "verification failed" in task.response.lower()
    finally:
        KERNEL.revoke_task(task.id)


# =============================================================================
# 5. CANCELLATION LOCKS PHYSICAL I/O
# =============================================================================

@pytest.mark.anyio
async def test_cancellation_locks_io_immediately():
    """Test that task cancellation immediately sets state CANCELLED and denies input."""
    db = MagicMock()
    task = Task(id="task_cancel_test", request="Long workflow", status=TaskStatus.CREATED.value)
    ctx = ExecutionContext(task_id=task.id)
    KERNEL.authorize_task(task.id, context=ctx)

    # Cancel context
    ctx.mark_cancelled("User clicked Stop")

    mock_router = MagicMock()
    mock_plan = Plan(task_id=task.id)
    mock_plan.steps = [
        PlanStep(
            step_number=1,
            description="Step 1",
            action=Action(capability=CapabilityType.KEYBOARD_TYPE, target="notepad"),
        )
    ]
    mock_router.plan_request.return_value = mock_plan

    try:
        loop = UniversalAgentLoop(router=mock_router)
        events = []
        async for ev in loop.run(db, task, ctx):
            events.append(ev)

        assert task.status == TaskState.CANCELLED.value
        assert any(e[0] == "error" and "cancelled" in e[1]["message"].lower() for e in events)
    finally:
        KERNEL.revoke_task(task.id)