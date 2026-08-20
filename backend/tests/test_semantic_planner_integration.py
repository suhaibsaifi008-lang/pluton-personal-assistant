"""
PLUTON V2 — Semantic Planner Runtime Integration Test Suite.
Verifies end-to-end integration between Semantic Planner, CapabilityRouter,
TargetResolver, and UniversalAgentLoop.
"""

import pytest
from app.capabilities import CAPABILITY_ROUTER
from app.core.contracts import ExecutionContext, TaskState
from app.planning.semantic import PLANNER_ROUTER, SEMANTIC_PLANNER


def test_planner_router_synchronous_execution():
    """Verify CapabilityRouter.plan_request routes through Semantic Planner / Router seamlessly."""
    ctx = ExecutionContext(task_id="t_router_sync")
    req = "Open Notepad and type 'System operational'."

    plan = CAPABILITY_ROUTER.plan_request(req, ctx)
    assert len(plan.steps) == 2
    assert plan.steps[0].action.capability.value == "app.launch"
    assert "notepad" in plan.steps[0].action.target.lower()
    assert plan.steps[1].action.capability.value == "keyboard.type"
    assert "System operational" in plan.steps[1].action.parameters.get("text", "")


def test_semantic_telemetry_recording():
    """Verify planning telemetry records latency, step counts, and validation status."""
    ctx = ExecutionContext(task_id="t_telemetry")
    CAPABILITY_ROUTER.plan_request("Open Calculator", ctx)

    assert len(SEMANTIC_PLANNER.telemetry_history) > 0
    latest = SEMANTIC_PLANNER.telemetry_history[-1]
    assert latest.latency_ms >= 0.0
    assert latest.validation_passed is True
    assert latest.step_count >= 1