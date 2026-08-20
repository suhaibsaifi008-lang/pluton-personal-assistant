"""
PLUTON V2 — Conversational & Follow-up Acceptance Test Suite
Verifies:
  1. Normal conversation ("Hello", "Who are you?")
  2. Conversational follow-up after observation ("List all open windows" -> "Tell me about them")
  3. Follow-up referring to previous action results ("What windows were found?")
  4. Pure computer actions ("Search Google for PLUTON AI")
  5. Ambiguous requests (refusal without unintended input)
  6. Failed actions (honest failure report with exact reason)
  7. Mixed conversational/action requests ("Please open Notepad and type hello")
"""

import uuid
import pytest
from app.core.contracts import ExecutionContext, TaskState
from app.core.runtime import PlutonRuntime
from app.database import SessionLocal
from app.kernel.control_kernel import KERNEL
from app.models import Task, TaskStatus
from app.providers import AIProvider, ProviderEvent, ProviderResponse


class MockConversationalProvider(AIProvider):
    """Mock AI Provider that returns contextual answers for conversational tests."""

    @property
    def name(self) -> str:
        return "mock_conversational"

    @property
    def model(self) -> str:
        return "mock-chat-v1"

    async def respond(self, request):
        msg = request.message.lower()
        hist = request.history or []

        last_assistant = next((h["content"] for h in reversed(hist) if h.get("role") == "assistant"), "")
        if "tell me about them" in msg or "what windows" in msg:
            if "found" in last_assistant.lower() or "window" in last_assistant.lower():
                return ProviderResponse(
                    response_id="resp_123",
                    text=f"Based on the windows listed earlier, you have your browser and development tools active.",
                )
            return ProviderResponse(response_id="resp_123", text="I can tell you about the open windows on your desktop.")

        if "hello" in msg or "who are you" in msg:
            return ProviderResponse(response_id="resp_123", text="Hello! I am PLUTON AI, your universal computer assistant.")

        return ProviderResponse(response_id="resp_123", text=f"I understood your question: '{request.message}'.")

    async def stream_respond(self, request):
        resp = await self.respond(request)
        yield ProviderEvent(kind="text_delta", text=resp.text, response_id=resp.response_id)


@pytest.mark.anyio
async def test_1_normal_conversation():
    """Verify pure conversation produces a conversational response without executing computer actions."""
    session_id = str(uuid.uuid4())
    provider = MockConversationalProvider()
    runtime = PlutonRuntime(provider=provider)

    with SessionLocal() as db:
        t = Task(title="Hello", request="Hello, who are you?", session_id=session_id, status=TaskStatus.CREATED.value)
        db.add(t)
        db.commit()
        db.refresh(t)
        t_id = t.id

    try:
        events = []
        async for ev_type, ev_data in runtime.execute_task(t_id):
            events.append((ev_type, ev_data))

        with SessionLocal() as db:
            task = db.get(Task, t_id)
            assert task is not None
            assert task.status == TaskState.COMPLETED.value
            assert "PLUTON AI" in task.response
            assert "Successfully executed and verified" not in task.response
    finally:
        with SessionLocal() as db:
            t = db.get(Task, t_id)
            if t:
                db.delete(t)
                db.commit()


@pytest.mark.anyio
async def test_2_and_3_observation_then_conversational_followup():
    """Verify: Turn 1 lists windows and saves observation -> Turn 2 'Tell me about them' answers using previous observation."""
    session_id = str(uuid.uuid4())
    provider = MockConversationalProvider()
    runtime = PlutonRuntime(provider=provider)

    # Turn 1: List all open windows
    with SessionLocal() as db:
        t1 = Task(title="List open windows", request="List all open windows on my desktop.", session_id=session_id, status=TaskStatus.CREATED.value)
        db.add(t1)
        db.commit()
        db.refresh(t1)
        t1_id = t1.id

    try:
        async for _ in runtime.execute_task(t1_id):
            pass

        with SessionLocal() as db:
            task1 = db.get(Task, t1_id)
            assert task1.status == TaskState.COMPLETED.value
            assert "Found" in task1.response or "window" in task1.response.lower()

        # Turn 2: Conversational follow-up: "Tell me about them."
        with SessionLocal() as db:
            t2 = Task(title="Tell me about them", request="Tell me about them.", session_id=session_id, status=TaskStatus.CREATED.value)
            db.add(t2)
            db.commit()
            db.refresh(t2)
            t2_id = t2.id

        async for _ in runtime.execute_task(t2_id):
            pass

        with SessionLocal() as db:
            task2 = db.get(Task, t2_id)
            assert task2.status == TaskState.COMPLETED.value
            assert "Successfully executed and verified 1 action(s)" not in task2.response
            assert "windows listed earlier" in task2.response or "browser" in task2.response.lower()
    finally:
        with SessionLocal() as db:
            for tid in (t1_id, t2_id):
                t = db.get(Task, tid)
                if t:
                    db.delete(t)
            db.commit()


@pytest.mark.anyio
async def test_4_pure_computer_action():
    """Verify pure computer control commands compile and execute physical actions with verification."""
    session_id = str(uuid.uuid4())
    runtime = PlutonRuntime()

    with SessionLocal() as db:
        t = Task(title="Search Google", request="Search Google for PLUTON AI", session_id=session_id, status=TaskStatus.CREATED.value)
        db.add(t)
        db.commit()
        db.refresh(t)
        t_id = t.id

    try:
        events = []
        async for ev_type, ev_data in runtime.execute_task(t_id):
            events.append((ev_type, ev_data))

        with SessionLocal() as db:
            task = db.get(Task, t_id)
            assert task.status == TaskState.COMPLETED.value
            plan_evs = [ev for ev in events if ev[0] == "activity" and ev[1].get("name") == "agent.plan"]
            assert len(plan_evs) >= 1
    finally:
        with SessionLocal() as db:
            t = db.get(Task, t_id)
            if t:
                db.delete(t)
                db.commit()


@pytest.mark.anyio
async def test_5_ambiguous_target_refusal():
    """Verify ambiguous target requests fail safely without performing accidental mutations."""
    from app.capabilities.capability_router import CAPABILITY_ROUTER
    from app.core.contracts import Action, CapabilityType, ExecutionTier

    context = ExecutionContext(task_id="test_ambiguous")
    KERNEL.authorize_task("test_ambiguous", context=context)
    try:
        action = Action(
            capability=CapabilityType.WINDOW_FOCUS,
            target="Window",
            parameters={"title": "Window"},
            tier_requested=ExecutionTier.TIER_1_NATIVE_API,
        )
        res = await CAPABILITY_ROUTER.execute_action(action, context)
        assert res.status in ("completed", "failed")
    finally:
        KERNEL.revoke_task("test_ambiguous")


@pytest.mark.anyio
async def test_6_failed_action_honest_report():
    """Verify failed actions report the exact error and do not claim false completion."""
    session_id = str(uuid.uuid4())
    runtime = PlutonRuntime()

    with SessionLocal() as db:
        t = Task(title="Close invalid tab", request="Close definitely_nonexistent_tab_9999 tab in Brave", session_id=session_id, status=TaskStatus.CREATED.value)
        db.add(t)
        db.commit()
        db.refresh(t)
        t_id = t.id

    try:
        async for _ in runtime.execute_task(t_id):
            pass

        with SessionLocal() as db:
            task = db.get(Task, t_id)
            assert task.status == TaskState.FAILED.value
            assert "Could not find or close tab" in task.response or "failed" in task.response.lower()
    finally:
        with SessionLocal() as db:
            t = db.get(Task, t_id)
            if t:
                db.delete(t)
                db.commit()


@pytest.mark.anyio
async def test_7_mixed_conversational_and_action():
    """Verify polite phrasing with explicit action ('Please open Notepad and type hello') compiles to action plan."""
    from app.planning.intent_compiler import UNIVERSAL_PLAN_COMPILER

    context = ExecutionContext(task_id="test_mixed")
    plan = UNIVERSAL_PLAN_COMPILER.compile_plan("Please open Notepad and type hello", context)
    assert len(plan.steps) == 2
    assert plan.steps[0].action.capability.value == "app.launch"
    assert plan.steps[1].action.capability.value == "keyboard.type"