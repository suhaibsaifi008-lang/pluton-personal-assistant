"""
PLUTON V2 — Phase 1B Adaptive Dynamic Replanning Acceptance Test Suite
Verifies bounded retry budget (max 3 attempts), failure classification, WorldState refresh,
materially different alternative strategy selection, safety/ambiguity gating, partial success recovery,
and mandatory postcondition verification.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.agent_loop import UniversalAgentLoop
from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    RiskLevel,
    Plan,
    PlanStep,
    TargetDomain,
    TaskState,
    ToolResult,
    VerificationResult,
    VerificationStrategy,
)
from app.core.world_state import BrowserSnapshot, WindowSnapshot, WorldState
from app.events.event_bus import EventBus
from app.kernel.control_kernel import ControlKernel
from app.models import Task, TaskStatus
from app.planning.replan_contracts import FailureClassification, ReplanContext, ReplanDecision
from app.planning.replan_engine import classify_step_failure, REPLAN_ENGINE, ReplanEngine


# =============================================================================
# 1. Failure Classification Tests
# =============================================================================

def test_failure_classification_taxonomies():
    """Verify that failure messages and tool observed outputs map to authoritative taxonomy."""
    act = Action(capability=CapabilityType.WINDOW_FOCUS, target="Notepad")

    # Ambiguity
    c1, _ = classify_step_failure(act, "failed", {"error": "AMBIGUOUS_TARGET: 2 windows"}, False, "")
    assert c1 == FailureClassification.AMBIGUOUS_TARGET

    # Target Not Found
    c2, _ = classify_step_failure(act, "failed", {"error": "TARGET_NOT_FOUND: no match"}, False, "")
    assert c2 == FailureClassification.TARGET_NOT_FOUND

    # Stale Target
    c3, _ = classify_step_failure(act, "failed", {"error": "Window HWND 999 is dead or stale"}, False, "")
    assert c3 == FailureClassification.TARGET_STALE

    # Timeout
    c4, _ = classify_step_failure(act, "failed", {"error": "Operation timed out after 30s"}, False, "")
    assert c4 == FailureClassification.TIMEOUT

    # Permission Denied
    c5, _ = classify_step_failure(act, "failed", {"error": "PERMISSION_DENIED: User confirmation required"}, False, "")
    assert c5 == FailureClassification.PERMISSION_DENIED

    # Verification Failed
    c6, _ = classify_step_failure(act, "completed", {}, False, "Window presence verification failed")
    assert c6 in (FailureClassification.POSTCONDITION_FAILED, FailureClassification.VERIFICATION_FAILED)


# =============================================================================
# 2. Replan Engine Strategy Selection & Gating Tests
# =============================================================================

def test_replan_refuses_ambiguity_and_permission_denied():
    """Verify that replan engine refuses to guess or bypass ambiguity/permission refusals."""
    engine = ReplanEngine(max_attempts=3)
    act = Action(capability=CapabilityType.WINDOW_FOCUS, target="Calc")

    ctx_ambig = ReplanContext(
        task_id="t_ambig",
        step_number=1,
        original_action=act,
        attempt_number=1,
        failure_classification=FailureClassification.AMBIGUOUS_TARGET,
        failure_diagnostic="Multiple matching targets",
    )
    dec_ambig = engine.generate_replan(ctx_ambig)
    assert dec_ambig.should_replan is False
    assert dec_ambig.selected_strategy == "REFUSE_GATED_FAILURE"

    ctx_perm = ReplanContext(
        task_id="t_perm",
        step_number=1,
        original_action=act,
        attempt_number=1,
        failure_classification=FailureClassification.PERMISSION_DENIED,
        failure_diagnostic="Action requires explicit user confirmation",
    )
    dec_perm = engine.generate_replan(ctx_perm)
    assert dec_perm.should_replan is False
    assert dec_perm.selected_strategy == "REFUSE_GATED_FAILURE"


def test_replan_browser_strategy_escalation():
    """Verify browser navigation failure transitions from existing tab reuse to fresh tab."""
    engine = ReplanEngine(max_attempts=3)
    act = Action(capability=CapabilityType.BROWSER_NAVIGATE, target="https://example.com", parameters={"reuse_existing": True})

    ctx = ReplanContext(
        task_id="t_browser",
        step_number=1,
        original_action=act,
        attempt_number=1,
        prior_strategies=["browser.navigate"],
        failure_classification=FailureClassification.POSTCONDITION_FAILED,
        failure_diagnostic="Navigation failed in existing tab",
    )
    dec1 = engine.generate_replan(ctx)
    assert dec1.should_replan is True
    assert dec1.selected_strategy == "browser_fresh_tab"
    assert dec1.new_action is not None
    assert dec1.new_action.parameters.get("force_new_tab") is True

    # Next attempt (attempt 2 -> 3)
    ctx2 = ReplanContext(
        task_id="t_browser",
        step_number=1,
        original_action=act,
        attempt_number=2,
        prior_strategies=["browser.navigate", "browser_fresh_tab"],
        failure_classification=FailureClassification.EXECUTION_FAILED,
        failure_diagnostic="Browser tab crash",
    )
    dec2 = engine.generate_replan(ctx2)
    assert dec2.should_replan is True
    assert dec2.selected_strategy == "browser_system_launch"


def test_replan_stale_window_invalidation():
    """Verify stale window failure invalidates the bound HWND and generates a fresh launch."""
    engine = ReplanEngine(max_attempts=3)
    act = Action(capability=CapabilityType.WINDOW_FOCUS, target="Notepad", parameters={"hwnd": 12345})
    exec_ctx = ExecutionContext(task_id="t_stale", bound_hwnd=12345)

    ctx = ReplanContext(
        task_id="t_stale",
        step_number=1,
        original_action=act,
        attempt_number=1,
        prior_strategies=["window.focus"],
        failure_classification=FailureClassification.TARGET_STALE,
        failure_diagnostic="Window HWND 12345 is dead",
        execution_context=exec_ctx,
    )
    dec = engine.generate_replan(ctx)
    assert dec.should_replan is True
    assert dec.selected_strategy == "app_relaunch_or_rediscover"
    assert "hwnd:12345" in dec.invalidated_targets
    assert dec.new_action.capability == CapabilityType.APP_LAUNCH
    assert "hwnd" not in dec.new_action.parameters


# =============================================================================
# 3. UniversalAgentLoop Observe-Act-Verify-Replan Execution Scenarios
# =============================================================================

def test_scenario_a_original_success():
    """Scenario A: Normal step succeeds on first attempt without triggering replan."""
    async def run():
        mock_router = MagicMock()
        mock_router.plan_request.return_value = Plan(
            task_id="t_a",
            steps=[PlanStep(step_number=1, description="Open Calc", action=Action(capability=CapabilityType.APP_LAUNCH, target="calc", verification_strategy=VerificationStrategy.WINDOW_PRESENCE, expected_state="Calculator"))],
        )
        mock_router.execute_action = AsyncMock(return_value=ToolResult(call_id="c1", name="app.launch", observed={"hwnd": 100}, status="completed", summary="Calculator launched.", raw_arguments={}))

        mock_verifier = MagicMock()
        mock_verifier.verify_action.return_value = VerificationResult(verified=True, strategy=VerificationStrategy.WINDOW_PRESENCE, message="Window verified")

        mock_kernel = MagicMock()
        mock_bus = MagicMock()
        mock_db = MagicMock()

        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier, kernel=mock_kernel, event_bus=mock_bus)
        task = Task(id="t_a", request="Open Calculator", session_id="s1")
        context = ExecutionContext(task_id="t_a")

        events = [e async for e in loop.run(mock_db, task, context)]
        assert task.status == TaskState.COMPLETED.value
        assert mock_router.execute_action.call_count == 1
        replan_events = [e for e in events if e[0] == "activity" and e[1].get("name") == "agent.replan"]
        assert len(replan_events) == 0

    asyncio.run(run())


def test_scenario_b_one_failure_then_replan_success():
    """Scenario B: Attempt 1 fails verification -> replan selects alternative strategy -> Attempt 2 succeeds."""
    async def run():
        mock_router = MagicMock()
        mock_router.plan_request.return_value = Plan(
            task_id="t_b",
            steps=[PlanStep(step_number=1, description="Open Tab", action=Action(capability=CapabilityType.BROWSER_NAVIGATE, target="https://unique-unopened-site.org", verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE, expected_state="unique-unopened-site"))],
        )

        # Call 1 fails verification; Call 2 succeeds
        mock_router.execute_action = AsyncMock(side_effect=[
            ToolResult(call_id="c1", name="browser.navigate", observed={"error": "Tab timed out"}, status="completed", summary="Navigation timed out.", raw_arguments={}),
            ToolResult(call_id="c2", name="browser.navigate", observed={"url": "https://unique-unopened-site.org"}, status="completed", summary="Opened in fresh tab.", raw_arguments={}),
        ])

        mock_verifier = MagicMock()
        mock_verifier.verify_action.side_effect = [
            VerificationResult(verified=False, strategy=VerificationStrategy.BROWSER_TAB_PRESENCE, message="Tab presence not found"),
            VerificationResult(verified=True, strategy=VerificationStrategy.BROWSER_TAB_PRESENCE, message="Pluton tab verified"),
        ]

        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier, kernel=MagicMock(), event_bus=MagicMock())
        task = Task(id="t_b", request="Open Pluton", session_id="s1")
        context = ExecutionContext(task_id="t_b")

        events = [e async for e in loop.run(MagicMock(), task, context)]
        assert task.status == TaskState.COMPLETED.value
        assert mock_router.execute_action.call_count == 2
        replan_events = [e for e in events if e[0] == "activity" and e[1].get("name") == "agent.replan"]
        assert len(replan_events) == 1
        assert replan_events[0][1]["diagnostics"]["selected_strategy"] == "browser_fresh_tab"

    asyncio.run(run())


def test_scenario_c_two_failures_then_third_success():
    """Scenario C: Attempt 1 fails, Attempt 2 fails, Attempt 3 succeeds; exactly 3 attempts executed."""
    async def run():
        mock_router = MagicMock()
        mock_router.plan_request.return_value = Plan(
            task_id="t_c",
            steps=[PlanStep(step_number=1, description="Open Webpage", action=Action(capability=CapabilityType.BROWSER_NAVIGATE, target="https://site.org", verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE, expected_state="Site"))],
        )

        mock_router.execute_action = AsyncMock(side_effect=[
            ToolResult(call_id="c1", name="browser.navigate", observed={"error": "Failed 1"}, status="failed", summary="Failed 1", raw_arguments={}),
            ToolResult(call_id="c2", name="browser.navigate", observed={"error": "Failed 2"}, status="failed", summary="Failed 2", raw_arguments={}),
            ToolResult(call_id="c3", name="browser.navigate", observed={"url": "https://site.org"}, status="completed", summary="Success on 3", raw_arguments={}),
        ])

        mock_verifier = MagicMock()
        mock_verifier.verify_action.side_effect = [
            VerificationResult(verified=False, strategy=VerificationStrategy.BROWSER_TAB_PRESENCE, message="Fail 1"),
            VerificationResult(verified=False, strategy=VerificationStrategy.BROWSER_TAB_PRESENCE, message="Fail 2"),
            VerificationResult(verified=True, strategy=VerificationStrategy.BROWSER_TAB_PRESENCE, message="Success 3"),
        ]

        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier, kernel=MagicMock(), event_bus=MagicMock())
        task = Task(id="t_c", request="Open Site", session_id="s1")
        context = ExecutionContext(task_id="t_c")

        events = [e async for e in loop.run(MagicMock(), task, context)]
        assert task.status == TaskState.COMPLETED.value
        assert mock_router.execute_action.call_count == 3

    asyncio.run(run())


def test_scenario_d_retry_budget_exhaustion():
    """Scenario D: All attempts fail -> stops strictly at 3 attempts with FAILED status and no 4th call."""
    async def run():
        mock_router = MagicMock()
        mock_router.plan_request.return_value = Plan(
            task_id="t_d",
            steps=[PlanStep(step_number=1, description="Open App", action=Action(capability=CapabilityType.APP_LAUNCH, target="dead_app", verification_strategy=VerificationStrategy.WINDOW_PRESENCE, expected_state="DeadApp"))],
        )

        mock_router.execute_action = AsyncMock(return_value=ToolResult(
            call_id="c_fail", name="app.launch", observed={"error": "Cannot start dead_app"}, status="failed", summary="Cannot start", raw_arguments={},
        ))

        mock_verifier = MagicMock()
        mock_verifier.verify_action.return_value = VerificationResult(verified=False, strategy=VerificationStrategy.WINDOW_PRESENCE, message="Window not found")

        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier, kernel=MagicMock(), event_bus=MagicMock())
        task = Task(id="t_d", request="Open Dead App", session_id="s1")
        context = ExecutionContext(task_id="t_d")

        events = [e async for e in loop.run(MagicMock(), task, context)]
        assert task.status == TaskState.FAILED.value
        # Must be strictly 3 attempts (attempt 1 + 2 replan retries)
        assert mock_router.execute_action.call_count == 3
        assert "Workflow halted at step 1" in task.response

    asyncio.run(run())


def test_scenario_f_partial_success_idempotency():
    """Scenario F: Partial success detected in refreshed WorldState advances step without duplicate re-execution."""
    async def run():
        mock_router = MagicMock()
        mock_router.plan_request.return_value = Plan(
            task_id="t_f",
            steps=[PlanStep(step_number=1, description="Open Notepad", action=Action(capability=CapabilityType.APP_LAUNCH, target="notepad", verification_strategy=VerificationStrategy.WINDOW_PRESENCE, expected_state="Notepad"))],
        )

        # Initial tool execution threw verification timeout error, but the window actually launched!
        mock_router.execute_action = AsyncMock(return_value=ToolResult(
            call_id="c1", name="app.launch", observed={"error": "Verification readback timeout"}, status="completed", summary="Timed out waiting for confirmation", raw_arguments={},
        ))

        mock_verifier = MagicMock()
        mock_verifier.verify_action.return_value = VerificationResult(verified=False, strategy=VerificationStrategy.WINDOW_PRESENCE, message="Initial timeout")

        # Mock WorldState capture to show that Notepad window IS present now
        fake_world = WorldState(
            visible_windows=[WindowSnapshot(hwnd=5555, title="Untitled - Notepad", class_name="Notepad", pid=1234, is_foreground=True)]
        )

        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier, kernel=MagicMock(), event_bus=MagicMock())
        task = Task(id="t_f", request="Open Notepad", session_id="s1")
        context = ExecutionContext(task_id="t_f")

        with patch.object(WorldState, "capture", return_value=fake_world), \
             patch.object(WorldState, "refresh_relevant_state", return_value=fake_world):
            events = [e async for e in loop.run(MagicMock(), task, context)]

        assert task.status == TaskState.COMPLETED.value
        # Since partial success was recognized, no second physical launch was performed!
        assert mock_router.execute_action.call_count == 1

    asyncio.run(run())


def test_scenario_j_false_success_protection():
    """Scenario J: Rejects completion if tool claims completed but verification fails and replan fails."""
    async def run():
        mock_router = MagicMock()
        mock_router.plan_request.return_value = Plan(
            task_id="t_j",
            steps=[PlanStep(step_number=1, description="Click Unresponsive Button", action=Action(capability=CapabilityType.UI_INVOKE, target="btnSave", verification_strategy=VerificationStrategy.UIA_READBACK, expected_state="Saved"))],
        )

        # Tool claims completed, but verification repeatedly fails!
        mock_router.execute_action = AsyncMock(return_value=ToolResult(
            call_id="c_lie", name="ui.invoke", observed={"clicked": True}, status="completed", summary="Clicked button", raw_arguments={},
        ))

        mock_verifier = MagicMock()
        mock_verifier.verify_action.return_value = VerificationResult(verified=False, strategy=VerificationStrategy.UIA_READBACK, message="Element state never changed to 'Saved'")

        loop = UniversalAgentLoop(router=mock_router, verifier=mock_verifier, kernel=MagicMock(), event_bus=MagicMock())
        task = Task(id="t_j", request="Save Document", session_id="s1")
        context = ExecutionContext(task_id="t_j")

        events = [e async for e in loop.run(MagicMock(), task, context)]
        assert task.status == TaskState.FAILED.value
        assert "Physical verification failed" in task.response or "Element state never changed" in task.response

    asyncio.run(run())