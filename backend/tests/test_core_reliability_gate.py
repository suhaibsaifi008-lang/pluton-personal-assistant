"""
PLUTON V2 Core Reliability Gate Test Suite.
Authoritative behavioral verification covering:
- Phase 2: Conversation Reliability (20-case test matrix)
- Phase 3 & 4: Deterministic Windows Action & Real OS Verification (Calculator 10/10)
- Phase 5: Idempotency (10/10 repeated attempts)
- Phase 6: Cancellation Safety (10/10 scenarios)
- Phase 7: Retry / Replan Bounded Safety
- Phase 8: False-Success Rejection (Mandatory Regression)
- Phase 9: Windows App Verification (Notepad 10/10, File Explorer 10/10)
"""

import asyncio
import os
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    IntentDomain,
    Plan,
    PlanStep,
    TargetDomain,
    TaskState,
    ToolResult,
    VerificationResult,
    VerificationStrategy,
)
from app.core.agent_loop import UniversalAgentLoop
from app.database import SessionLocal
from app.kernel.control_kernel import KERNEL
from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
from app.models import Task, TaskStatus
from app.router import FRONT_DOOR_ROUTER, RouteContext
from app.subsystems.computer.domains.app import APP_DOMAIN
from app.verification.verification_engine import VERIFICATION_ENGINE


from app.capabilities.capability_router import CAPABILITY_ROUTER
from app.events.event_bus import EVENT_BUS


# =============================================================================
# PHASE 2: CONVERSATIONAL RELIABILITY TEST MATRIX (20/20)
# =============================================================================

CONVERSATIONAL_20_PROMPTS = [
    ("What is the capital of France?", "factual_question"),
    ("What is 25 * 48?", "calculation"),
    ("Explain how photosynthesis works in plants.", "explanation"),
    ("Compare the differences between Python and JavaScript.", "comparison"),
    ("Can you explain more details about that?", "follow_up"),
    ("What do you think about the future of AI?", "ambiguous_question"),
    ("Why is the sky blue?", "short_question"),
    ("Could you please provide a comprehensive breakdown of the core principles of quantum mechanics including wave-particle duality?", "long_question"),
    ("Hello, how are you doing today?", "casual_conversation"),
    ("Write a short poem about coding at midnight.", "no_tool_creative_writing"),
    ("How does the operating system click event dispatch mechanism work under the hood?", "tool_like_noun_inquiry"),
    ("What is the history of Microsoft Calculator and when was it first released?", "app_name_in_inquiry"),
    ("Why do websites use https://example.com as a standard domain in documentation?", "url_in_inquiry"),
    ("Compare Chrome browser and Brave browser features.", "browser_term_inquiry"),
    ("What is the difference between a binary file and a text file?", "file_term_inquiry"),
    ("What is a terminal emulator in modern operating systems?", "terminal_term_inquiry"),
    ("   Hello PLUTON!   ", "whitespace_padded_input"),
    ("??? What is 10 + 20 ????", "punctuation_calculation"),
    ("What is the open source definition according to OSI?", "open_source_noun_inquiry"),
    ("Can you help me understand how compilers optimize code?", "compiler_inquiry"),
]


@pytest.mark.parametrize("prompt,category", CONVERSATIONAL_20_PROMPTS)
def test_conversational_matrix_routes_without_physical_agent(prompt: str, category: str):
    """Every conversational request must route to conversation/fast plane with requires_computer_agent=False."""
    decision = FRONT_DOOR_ROUTER.route(prompt)
    assert not decision.requires_computer_agent, (
        f"Conversational prompt [{category}] '{prompt}' was misclassified as requiring computer agent! "
        f"Domain: {decision.domain}, Reason: {decision.reason}"
    )


# =============================================================================
# PHASE 3 & 4: DETERMINISTIC WINDOWS ACTION & REAL VERIFICATION (CALCULATOR)
# =============================================================================

def test_calculator_structured_launch_and_verification():
    """Calculator launch must yield structured intent and verify OS presence."""
    task_id = "test_calc_gate_001"
    KERNEL.authorize_task(task_id)

    res = APP_DOMAIN.launch("calculator", reuse_existing=True)
    assert res.get("success") is True, f"Failed to launch calculator: {res}"
    assert res.get("hwnd", 0) > 0, "No valid HWND returned"

    # Real OS Verification
    v_res = VERIFICATION_ENGINE.verify_action(
        strategy=VerificationStrategy.WINDOW_PRESENCE,
        expected_state="Calculator",
        target="calculator",
        hwnd=res.get("hwnd"),
        timeout_seconds=3.0,
    )
    assert v_res.verified is True, f"Verification failed: {v_res.message}"
    assert v_res.observed_state is not None
    KERNEL.revoke_task(task_id)


# =============================================================================
# PHASE 5: IDEMPOTENCY GATE (10/10 REPEATED ATTEMPTS)
# =============================================================================

def test_idempotency_10_repeated_attempts():
    """Repeatedly launching an already open app must focus the existing window and avoid duplicate instances."""
    task_id = "test_idempotency_gate"
    KERNEL.authorize_task(task_id)

    # Ensure app is initially running
    init_res = APP_DOMAIN.launch("calculator", reuse_existing=True)
    assert init_res.get("success") is True
    first_hwnd = init_res.get("hwnd")

    for attempt in range(1, 11):
        res = APP_DOMAIN.launch("calculator", reuse_existing=True)
        assert res.get("success") is True, f"Attempt {attempt} failed: {res}"
        assert res.get("transition") == "EXISTING_INSTANCE_REUSED", (
            f"Attempt {attempt} spawned duplicate instead of reusing existing instance: {res}"
        )
        assert res.get("hwnd") == first_hwnd, (
            f"Attempt {attempt} returned HWND {res.get('hwnd')} != original HWND {first_hwnd}"
        )

    KERNEL.revoke_task(task_id)


# =============================================================================
# PHASE 6: CANCELLATION SAFETY (10/10 SCENARIOS)
# =============================================================================

def test_cancellation_10_scenarios():
    """Verify that cancellation aborts execution with zero side effects across 10 distinct scenarios."""
    async def _run():
        loop = UniversalAgentLoop(
            router=CAPABILITY_ROUTER,
            verifier=VERIFICATION_ENGINE,
            kernel=KERNEL,
            event_bus=EVENT_BUS,
        )

        for scenario_idx in range(1, 11):
            task_id = f"cancel_scenario_{scenario_idx}"
            ACTIVE_TASK_REGISTRY.register_task(task_id, f"task_{scenario_idx}", "dummy session")
            context = ExecutionContext(task_id=task_id)
            KERNEL.authorize_task(task_id, context=context)

            # Mark cancelled prior to execution
            ACTIVE_TASK_REGISTRY.mark_cancelled(task_id, reason=f"Test cancellation scenario {scenario_idx}")
            context.mark_cancelled("Test cancellation")

            with SessionLocal() as db:
                task = Task(id=task_id, session_id="test_sess", title="Open Calculator", request="Open Calculator", status="RUNNING")
                db.add(task)
                db.commit()

                events = []
                async for ev_type, ev_data in loop.run(db, task, context):
                    events.append((ev_type, ev_data))

                db.refresh(task)
                assert task.status == TaskState.CANCELLED.value, f"Scenario {scenario_idx} task status was {task.status}"
                assert any(ev[0] == "done" and ev[1].get("status") == "CANCELLED" for ev in events), (
                    f"Scenario {scenario_idx} did not emit terminal CANCELLED event: {events}"
                )

            KERNEL.revoke_task(task_id)
            ACTIVE_TASK_REGISTRY.unregister_task(task_id, reason="test_done")

    asyncio.run(_run())


# =============================================================================
# PHASE 7: RETRY / REPLAN BOUNDED SAFETY
# =============================================================================

def test_retry_replan_bounded_safety():
    """A consistently failing action must exhaust retries and reach FAILED state without infinite loop."""
    async def _run():
        loop = UniversalAgentLoop(
            router=CAPABILITY_ROUTER,
            verifier=VERIFICATION_ENGINE,
            kernel=KERNEL,
            event_bus=EVENT_BUS,
        )
        task_id = "test_retry_safety_001"
        context = ExecutionContext(task_id=task_id)
        KERNEL.authorize_task(task_id, context=context)

        # Mock an action that always fails verification
        mock_router = MagicMock()
        mock_router.execute_action = AsyncMock(return_value=ToolResult(
            call_id="call_fail",
            name="app_launch",
            observed={"error": "OS failed to initialize window"},
            status="error",
            summary="Action execution failed",
            raw_arguments={"target": "nonexistent_app"},
        ))
        mock_router.plan_request = MagicMock(return_value=Plan(
            task_id=task_id,
            steps=[PlanStep(
                step_number=1,
                description="Launch non-existent app",
                action=Action(
                    capability=CapabilityType.APP_LAUNCH,
                    target="nonexistent_app",
                    target_domain=TargetDomain.APP,
                    verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                    expected_state="Nonexistent App",
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                ),
            )],
        ))

        loop.router = mock_router
        loop.verifier = MagicMock()
        loop.verifier.verify_action = MagicMock(return_value=VerificationResult(
            verified=False,
            strategy=VerificationStrategy.WINDOW_PRESENCE,
            message="Window not found",
        ))

        with SessionLocal() as db:
            task = Task(id=task_id, session_id="test_sess", title="Open Nonexistent App", request="Open Nonexistent App", status="RUNNING")
            db.add(task)
            db.commit()

            events = []
            t0 = time.perf_counter()
            async for ev_type, ev_data in loop.run(db, task, context):
                events.append((ev_type, ev_data))
            duration = time.perf_counter() - t0

            db.refresh(task)
            assert task.status == TaskState.FAILED.value, f"Task status was {task.status}, expected FAILED"
            assert duration < 10.0, f"Retry loop hung or took too long: {duration}s"
            assert any(ev[0] == "done" and ev[1].get("status") == "FAILED" for ev in events)

        KERNEL.revoke_task(task_id)

    asyncio.run(_run())


# =============================================================================
# PHASE 8: FALSE-SUCCESS REJECTION (MANDATORY REGRESSION)
# =============================================================================

def test_false_success_rejection_mandatory_regression():
    """When action reports completed but verification fails, task must transition to FAILED, NEVER COMPLETED."""
    async def _run():
        loop = UniversalAgentLoop(
            router=CAPABILITY_ROUTER,
            verifier=VERIFICATION_ENGINE,
            kernel=KERNEL,
            event_bus=EVENT_BUS,
        )
        task_id = "test_false_success_001"
        context = ExecutionContext(task_id=task_id)
        KERNEL.authorize_task(task_id, context=context)

        mock_router = MagicMock()
        # Action falsely reports completed
        mock_router.execute_action = AsyncMock(return_value=ToolResult(
            call_id="call_fake_success",
            name="app_launch",
            observed={"launched": True, "pid": 99999},
            status="completed",
            summary="Launched app successfully",
            raw_arguments={"target": "ghost_app"},
        ))
        mock_router.plan_request = MagicMock(return_value=Plan(
            task_id=task_id,
            steps=[PlanStep(
                step_number=1,
                description="Launch ghost app",
                action=Action(
                    capability=CapabilityType.APP_LAUNCH,
                    target="ghost_app",
                    target_domain=TargetDomain.APP,
                    verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                    expected_state="Ghost App",
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                ),
            )],
        ))

        loop.router = mock_router
        # Verification accurately detects absence
        loop.verifier = MagicMock()
        loop.verifier.verify_action = MagicMock(return_value=VerificationResult(
            verified=False,
            strategy=VerificationStrategy.WINDOW_PRESENCE,
            observed_state=None,
            expected_state="Ghost App",
            message="Window 'ghost_app' was NOT found in OS window tree.",
        ))

        with SessionLocal() as db:
            task = Task(id=task_id, session_id="test_sess", title="Open Ghost App", request="Open Ghost App", status="RUNNING")
            db.add(task)
            db.commit()

            events = []
            async for ev_type, ev_data in loop.run(db, task, context):
                events.append((ev_type, ev_data))

            db.refresh(task)
            assert task.status == TaskState.FAILED.value, (
                f"False success bug detected! Task status was '{task.status}' instead of 'FAILED'."
            )
            assert task.status != TaskState.COMPLETED.value
            assert any(ev[0] == "done" and ev[1].get("status") == "FAILED" for ev in events)

        KERNEL.revoke_task(task_id)

    asyncio.run(_run())


# =============================================================================
# PHASE 9: WINDOWS APP VERIFICATION (NOTEPAD & FILE EXPLORER)
# =============================================================================

def test_notepad_10_verification_gate():
    """Verify Notepad launch and window presence across 10 trials."""
    task_id = "test_notepad_gate"
    KERNEL.authorize_task(task_id)

    for trial in range(1, 11):
        res = APP_DOMAIN.launch("notepad", reuse_existing=True)
        assert res.get("success") is True, f"Notepad trial {trial} failed: {res}"
        hwnd = res.get("hwnd")
        assert hwnd and hwnd > 0

        v_res = VERIFICATION_ENGINE.verify_action(
            strategy=VerificationStrategy.WINDOW_PRESENCE,
            expected_state="Notepad",
            target="notepad",
            hwnd=hwnd,
            timeout_seconds=2.0,
        )
        assert v_res.verified is True, f"Notepad trial {trial} verification failed: {v_res.message}"

    KERNEL.revoke_task(task_id)


def test_file_explorer_10_verification_gate():
    """Verify File Explorer launch and window presence across 10 trials."""
    task_id = "test_explorer_gate"
    KERNEL.authorize_task(task_id)

    for trial in range(1, 11):
        res = APP_DOMAIN.launch("file explorer", reuse_existing=True)
        assert res.get("success") is True, f"File Explorer trial {trial} failed: {res}"
        hwnd = res.get("hwnd")
        assert hwnd and hwnd > 0

        v_res = VERIFICATION_ENGINE.verify_action(
            strategy=VerificationStrategy.WINDOW_PRESENCE,
            expected_state="File Explorer",
            target="file explorer",
            hwnd=hwnd,
            timeout_seconds=2.0,
        )
        assert v_res.verified is True, f"File Explorer trial {trial} verification failed: {v_res.message}"

    KERNEL.revoke_task(task_id)
