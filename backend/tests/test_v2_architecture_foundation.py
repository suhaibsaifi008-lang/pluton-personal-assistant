"""PLUTON V2 Architecture-Level Foundation Test Suite.

Validates all core contracts, state machine, computer-control kernel, capability router,
verification engine, memory store, artifact manager, and unified event model.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.contracts import (
    Action,
    Artifact,
    ArtifactType,
    CapabilityType,
    EventType,
    ExecutionContext,
    ExecutionTier,
    MemoryCategory,
    MemoryRecord,
    RiskLevel,
    Plan,
    PlanStep,
    TaskEvent,
    TaskState,
    VerificationResult,
    VerificationStrategy,
)
from app.kernel.control_kernel import ComputerControlKernel, KernelToken, KERNEL
from app.verification.verification_engine import VerificationEngine, VERIFICATION_ENGINE
from app.capabilities.capability_router import CapabilityRouter, CAPABILITY_ROUTER
from app.artifacts.artifact_manager import ArtifactManager
from app.events.event_bus import TaskEventBus, EVENT_BUS


# -----------------------------------------------------------------------------
# 1. State Machine & Contracts Tests
# -----------------------------------------------------------------------------

def test_task_state_machine_contracts():
    assert TaskState.CREATED.value == "CREATED"
    assert TaskState.PLANNING.value == "PLANNING"
    assert TaskState.EXECUTING.value == "EXECUTING"
    assert TaskState.VERIFYING.value == "VERIFYING"
    assert TaskState.AWAITING_APPROVAL.value == "AWAITING_APPROVAL"
    assert TaskState.COMPLETED.value == "COMPLETED"
    assert TaskState.FAILED.value == "FAILED"
    assert TaskState.CANCELLED.value == "CANCELLED"
    assert TaskState.TIMED_OUT.value == "TIMED_OUT"


def test_action_and_plan_contracts():
    action = Action(
        capability=CapabilityType.KEYBOARD_TYPE,
        target="Hello World",
        parameters={"text": "Hello World"},
        verification_strategy=VerificationStrategy.UIA_READBACK,
        expected_state="Hello World",
    )
    assert action.capability == CapabilityType.KEYBOARD_TYPE
    assert action.tier_requested == ExecutionTier.TIER_1_NATIVE_API

    step = PlanStep(step_number=1, description="Type text", action=action)
    plan = Plan(task_id="test-task-1", steps=[step])
    assert len(plan.steps) == 1
    assert plan.current_step == step
    assert not plan.is_finished
    plan.current_step_index = 1
    assert plan.is_finished


# -----------------------------------------------------------------------------
# 2. Computer Control Kernel Safety Invariant Tests
# -----------------------------------------------------------------------------

def test_kernel_zero_input_invariant_when_idle():
    kernel = ComputerControlKernel()
    assert not kernel.is_authorized()
    assert not kernel.is_authorized("random-task-id")

    with pytest.raises(PermissionError) as exc:
        kernel.assert_authorized("random-task-id", capability=CapabilityType.KEYBOARD_TYPE)
    assert "Computer control BLOCKED" in str(exc.value)


def test_kernel_task_token_authorization_and_revocation():
    kernel = ComputerControlKernel()
    token = kernel.authorize_task("task-123", ttl_seconds=60.0)
    assert token.task_id == "task-123"
    assert kernel.is_authorized("task-123")
    assert not kernel.is_authorized("other-task-456")

    # Revocation
    kernel.revoke_task("task-123")
    assert not kernel.is_authorized("task-123")
    assert not token.is_valid


def test_kernel_emergency_stop():
    kernel = ComputerControlKernel()
    kernel.authorize_task("task-danger", ttl_seconds=60.0)
    assert kernel.is_authorized("task-danger")

    stop_res = kernel.emergency_stop()
    assert stop_res["stopped"] is True
    assert stop_res["revoked_task"] == "task-danger"
    assert not kernel.is_authorized("task-danger")


def test_kernel_token_expiry():
    token = KernelToken(task_id="expired-task", ttl_seconds=0.01)
    time.sleep(0.02)
    assert not token.is_valid


# -----------------------------------------------------------------------------
# 3. Verification Engine Tests
# -----------------------------------------------------------------------------

def test_verification_window_presence_mocked():
    mock_uia = MagicMock()
    mock_uia.list_windows.return_value = [{"hwnd": 12345, "title": "Untitled - Notepad", "pid": 999}]
    verifier = VerificationEngine(uia_engine=mock_uia)

    result = verifier.verify_action(
        strategy=VerificationStrategy.WINDOW_PRESENCE,
        expected_state="Notepad",
        target="Notepad",
        timeout_seconds=0.5,
    )
    assert result.verified is True
    assert result.strategy == VerificationStrategy.WINDOW_PRESENCE
    assert result.observed_state["hwnd"] == 12345


def test_verification_window_absence_mocked():
    mock_uia = MagicMock()
    mock_uia.list_windows.return_value = []
    verifier = VerificationEngine(uia_engine=mock_uia)

    result = verifier.verify_action(
        strategy=VerificationStrategy.WINDOW_ABSENCE,
        expected_state="absent",
        target="Calculator",
        timeout_seconds=0.5,
    )
    assert result.verified is True
    assert result.observed_state == "closed"


def test_verification_browser_tab_absence_mocked():
    mock_uia = MagicMock()
    mock_uia.list_browser_tabs.return_value = [{"title": "GitHub", "tab_number": 1}]
    verifier = VerificationEngine(uia_engine=mock_uia)

    result = verifier.verify_action(
        strategy=VerificationStrategy.BROWSER_TAB_ABSENCE,
        expected_state="absent",
        target="Google",
        metadata={"browser": "Brave"},
        timeout_seconds=0.5,
    )
    assert result.verified is True


def test_verification_filesystem_check(tmp_path):
    test_file = tmp_path / "test_artifact.txt"
    test_file.write_text("sample content")

    verifier = VerificationEngine()
    result_exist = verifier.verify_action(
        strategy=VerificationStrategy.FILESYSTEM_CHECK,
        expected_state=True,
        target=str(test_file),
    )
    assert result_exist.verified is True

    result_not_exist = verifier.verify_action(
        strategy=VerificationStrategy.FILESYSTEM_CHECK,
        expected_state=True,
        target=str(tmp_path / "nonexistent.txt"),
    )
    assert result_not_exist.verified is False


# -----------------------------------------------------------------------------
# 4. Capability Router Planning Tests
# -----------------------------------------------------------------------------

def test_capability_router_plans_compound_workflow():
    router = CapabilityRouter()
    ctx = ExecutionContext(task_id="test-compound-1")

    prompt = "Open Notepad, type Hello from Pluton, press Ctrl+A, type Replacement text, press Enter, type Second line"
    plan = router.plan_request(prompt, ctx)

    assert len(plan.steps) == 6
    assert plan.steps[0].action.capability == CapabilityType.APP_LAUNCH
    assert plan.steps[1].action.capability == CapabilityType.KEYBOARD_TYPE
    assert plan.steps[1].action.parameters["text"] == "Hello from Pluton"
    assert plan.steps[2].action.capability == CapabilityType.KEYBOARD_HOTKEY
    assert plan.steps[3].action.capability == CapabilityType.KEYBOARD_TYPE
    assert plan.steps[4].action.capability == CapabilityType.KEYBOARD_PRESS
    assert plan.steps[5].action.capability == CapabilityType.KEYBOARD_TYPE


def test_capability_router_plans_browser_close_tab():
    router = CapabilityRouter()
    ctx = ExecutionContext(task_id="test-tab-close")

    plan = router.plan_request("close the Google tab in Brave", ctx)
    assert len(plan.steps) == 1
    assert plan.steps[0].action.capability == CapabilityType.BROWSER_CLOSE_TAB
    assert plan.steps[0].action.target == "google"


# -----------------------------------------------------------------------------
# 5. Artifact Manager Tests
# -----------------------------------------------------------------------------

def test_artifact_manager_store_and_lookup(tmp_path):
    mgr = ArtifactManager(base_dir=tmp_path)
    art = mgr.store_artifact(
        task_id="task-art-1",
        name="summary_report.md",
        artifact_type=ArtifactType.REPORT,
        content="# Execution Summary\nAll tests passed.",
    )
    assert art.name == "summary_report.md"
    assert art.artifact_type == ArtifactType.REPORT
    assert Path(art.file_path).exists()

    found_path = mgr.get_artifact_path("task-art-1", "summary_report.md")
    assert found_path is not None
    assert found_path.read_text(encoding="utf-8").startswith("# Execution Summary")


# -----------------------------------------------------------------------------
# 6. Event Bus Tests
# -----------------------------------------------------------------------------

def test_event_bus_pub_sub():
    bus = TaskEventBus()
    q = bus.subscribe("task-stream-1")

    ev = bus.emit(EventType.ACTION_STARTED, "task-stream-1", {"capability": "app.launch"})
    assert ev.event_type == EventType.ACTION_STARTED
    assert not q.empty()

    received = q.get_nowait()
    assert received.event_type == EventType.ACTION_STARTED
    sse = received.to_sse_dict()
    assert sse["event"] == "activity"

    bus.unsubscribe("task-stream-1", q)
