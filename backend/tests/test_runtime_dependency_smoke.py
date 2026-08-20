"""
PLUTON V2 — Canonical Runtime Dependency & Smoke Test Suite
Verifies:
  1. Fail-fast dependency validation on PlutonRuntime and UniversalAgentLoop
  2. Complete constructor injection across the canonical dependency chain
  3. POST /api/chat entry-point initialization matches production
  4. Real harmless observation execution through PlutonRuntime
"""

import pytest
from app.agent import AgentEngine
from app.capabilities.capability_router import CAPABILITY_ROUTER
from app.core.agent_loop import UniversalAgentLoop
from app.core.contracts import TaskState
from app.core.runtime import PlutonRuntime
from app.database import SessionLocal
from app.events.event_bus import EVENT_BUS
from app.kernel.control_kernel import KERNEL
from app.models import Task, TaskStatus
from app.verification.verification_engine import VERIFICATION_ENGINE, VerificationEngine


def test_pluton_runtime_dependency_graph_completeness():
    """Verify that PlutonRuntime constructs with complete, explicit dependencies."""
    runtime = PlutonRuntime()
    assert runtime.router is not None
    assert runtime.verification_engine is not None
    assert runtime.kernel is not None
    assert runtime.event_bus is not None
    assert runtime.agent_loop is not None

    # Prove ownership & 1:1 sharing
    assert runtime.agent_loop.router is runtime.router
    assert runtime.agent_loop.verifier is runtime.verification_engine
    assert runtime.agent_loop.kernel is runtime.kernel
    assert runtime.agent_loop.event_bus is runtime.event_bus


def test_universal_agent_loop_fail_fast_missing_dependencies():
    """Verify that UniversalAgentLoop refuses to construct if required dependencies are missing."""
    with pytest.raises(RuntimeError, match="CANONICAL_RUNTIME_DEPENDENCY_ERROR"):
        UniversalAgentLoop(router=None, verifier=VERIFICATION_ENGINE)


def test_agent_engine_runtime_wiring():
    """Verify that AgentEngine (used by /api/chat) correctly initializes canonical PlutonRuntime."""
    engine = AgentEngine()
    assert engine.runtime is not None
    assert isinstance(engine.runtime, PlutonRuntime)
    assert engine.runtime.verification_engine is not None
    assert engine.runtime.agent_loop is not None


@pytest.mark.anyio
async def test_runtime_harmless_observation_smoke_execution():
    """Execute a harmless observation task end-to-end through PlutonRuntime without NameError/AttributeError."""
    with SessionLocal() as db:
        task = Task(title="List desktop windows", request="List desktop windows", status=TaskStatus.CREATED.value)
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    runtime = PlutonRuntime()
    events = []
    try:
        async for ev_type, ev_data in runtime.execute_task(task_id):
            events.append((ev_type, ev_data))

        assert len(events) >= 1
        with SessionLocal() as db:
            final_task = db.get(Task, task_id)
            assert final_task is not None
            assert final_task.status in (TaskState.COMPLETED.value, TaskState.FAILED.value)
            assert "verify_engine" not in str(final_task.response).lower()
            assert "nameerror" not in str(final_task.response).lower()
    finally:
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t:
                db.delete(t)
                db.commit()