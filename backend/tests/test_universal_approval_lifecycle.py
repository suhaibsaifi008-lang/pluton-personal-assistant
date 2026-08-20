import asyncio
import json
from unittest.mock import MagicMock, patch
import pytest

from app.agent import AgentEngine
from app.database import Base, SessionLocal, engine
from app.models import Activity, Session as SessionModel, Task, TaskStatus
from app.providers.base import AIProvider, ProviderEvent, ProviderRequest, ToolCall
from app.security import PermissionLevel
from app.tools import Tool, ToolRegistry


class ScriptedProvider(AIProvider):
    def __init__(self, turns: list[Any]):
        self.name = "scripted"
        self.turns = list(turns)
        self.turn_index = 0

    @property
    def model(self) -> str:
        return "scripted-model"

    async def respond(self, request: ProviderRequest):
        return None

    async def stream_respond(self, request: ProviderRequest):
        if self.turn_index >= len(self.turns):
            yield ProviderEvent(kind="text_delta", text="Finished all scripted steps.")
            return

        current = self.turns[self.turn_index]
        self.turn_index += 1

        if isinstance(current, list):
            yield ProviderEvent(kind="tool_calls", tool_calls=current, response_id=f"resp_{self.turn_index}")
        elif isinstance(current, str):
            yield ProviderEvent(kind="text_delta", text=current)
        elif isinstance(current, tuple):
            calls, text = current
            if text:
                yield ProviderEvent(kind="text_delta", text=text)
            if calls:
                yield ProviderEvent(kind="tool_calls", tool_calls=calls, response_id=f"resp_{self.turn_index}")


def setup_function():
    Base.metadata.create_all(bind=engine)


# 1. Approval -> Execute -> Resume -> Complete (Executed Exactly Once)
def test_approval_executes_tool_exactly_once_and_resumes():
    db = SessionLocal()
    session = SessionModel(title="Approval Session")
    db.add(session)
    db.commit()
    task = Task(session_id=session.id, title="High Risk Task", request="Run high risk command", status=TaskStatus.CREATED.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    call_count = {"count": 0}

    def mock_high_risk_action():
        call_count["count"] += 1
        return {"status": "executed", "count": call_count["count"]}

    custom_reg = ToolRegistry()
    custom_reg.register(Tool(
        name="test.high_risk",
        description="High risk tool needing approval",
        permission=PermissionLevel.HIGH,
        input_schema={"type": "object"},
        execute=mock_high_risk_action,
    ))

    # Turn 1: Requests test.high_risk
    # Turn 2: Sees output and completes
    provider = ScriptedProvider([
        [ToolCall(call_id="call_hr1", name="test.high_risk", arguments={})],
        "Task completed after user authorized the action.",
    ])

    agent = AgentEngine(provider=provider, registry=custom_reg)

    # Initial Run -> Expect confirmation event
    events_1 = []
    async def run_initial():
        async for ev in agent.run(task_id=task_id):
            events_1.append(ev)

    asyncio.run(run_initial())

    # Verify task is in CONFIRMING state and tool has NOT been executed yet
    assert call_count["count"] == 0
    confirm_events = [data for ev, data in events_1 if ev == "confirmation"]
    assert len(confirm_events) == 1
    assert confirm_events[0]["confirmations"][0]["name"] == "test.high_risk"

    db = SessionLocal()
    task_mid = db.get(Task, task_id)
    assert task_mid.status == TaskStatus.CONFIRMING.value
    db.close()

    # User Approves -> Resume Run
    events_2 = []
    async def run_resume():
        async for ev in agent.resume(task_id=task_id, approved=True):
            events_2.append(ev)

    asyncio.run(run_resume())

    # Verify tool was executed EXACTLY ONCE
    assert call_count["count"] == 1

    # Verify task completed
    done_events = [data for ev, data in events_2 if ev == "done"]
    assert len(done_events) == 1
    assert done_events[0]["status"] == TaskStatus.COMPLETED.value
    assert "completed after user authorized" in done_events[0]["message"]

    db = SessionLocal()
    task_final = db.get(Task, task_id)
    assert task_final.status == TaskStatus.COMPLETED.value
    assert task_final.checkpoint is None
    db.close()


# 2. Denial -> Resume with deterministic denial
def test_denial_resumes_agent_with_denial_result():
    db = SessionLocal()
    session = SessionModel(title="Denial Session")
    db.add(session)
    db.commit()
    task = Task(session_id=session.id, title="Dangerous Task", request="Delete system files", status=TaskStatus.CREATED.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    call_count = {"count": 0}

    def mock_dangerous_action():
        call_count["count"] += 1
        return {"deleted": True}

    custom_reg = ToolRegistry()
    custom_reg.register(Tool(
        name="test.dangerous",
        description="Dangerous tool",
        permission=PermissionLevel.HIGH,
        input_schema={"type": "object"},
        execute=mock_dangerous_action,
    ))

    provider = ScriptedProvider([
        [ToolCall(call_id="call_dang1", name="test.dangerous", arguments={})],
        "Understood. The action was cancelled as you requested.",
    ])

    agent = AgentEngine(provider=provider, registry=custom_reg)

    # Initial Run
    asyncio.run(asyncio.sleep(0.01))
    events_1 = []
    async def run_initial():
        async for ev in agent.run(task_id=task_id):
            events_1.append(ev)

    asyncio.run(run_initial())

    # User Denies -> Resume with approved=False
    events_2 = []
    async def run_deny():
        async for ev in agent.resume(task_id=task_id, approved=False):
            events_2.append(ev)

    asyncio.run(run_deny())

    # Verify tool was NEVER executed
    assert call_count["count"] == 0

    # Verify agent completed with graceful cancellation message
    done_events = [data for ev, data in events_2 if ev == "done"]
    assert len(done_events) == 1
    assert done_events[0]["status"] == TaskStatus.COMPLETED.value
    assert "action was cancelled" in done_events[0]["message"].lower()


# 3. Multiple Sequential Approval-Gated Actions
def test_multiple_sequential_approval_gated_actions():
    db = SessionLocal()
    task = Task(title="Sequential Approvals", request="Perform step 1 and step 2", status=TaskStatus.CREATED.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    executed = []

    def mock_step1():
        executed.append("step1")
        return {"step": 1}

    def mock_step2():
        executed.append("step2")
        return {"step": 2}

    custom_reg = ToolRegistry()
    custom_reg.register(Tool(name="test.step1", description="Step 1", permission=PermissionLevel.HIGH, input_schema={"type": "object"}, execute=mock_step1))
    custom_reg.register(Tool(name="test.step2", description="Step 2", permission=PermissionLevel.HIGH, input_schema={"type": "object"}, execute=mock_step2))

    # Turn 1: Requests step 1
    # Turn 2: Requests step 2
    # Turn 3: Concludes
    provider = ScriptedProvider([
        [ToolCall(call_id="call_s1", name="test.step1", arguments={})],
        [ToolCall(call_id="call_s2", name="test.step2", arguments={})],
        "Both high-risk steps successfully completed.",
    ])

    agent = AgentEngine(provider=provider, registry=custom_reg)

    # Run initial -> pause at step 1
    events_1 = []
    async def run_1():
        async for ev in agent.run(task_id=task_id):
            events_1.append(ev)

    asyncio.run(run_1())
    assert len([d for ev, d in events_1 if ev == "confirmation"]) == 1
    assert executed == []

    # Approve step 1 -> executes step 1, then agent requests step 2 -> pause at step 2
    events_2 = []
    async def run_2():
        async for ev in agent.resume(task_id=task_id, approved=True):
            events_2.append(ev)

    asyncio.run(run_2())
    assert executed == ["step1"]
    assert len([d for ev, d in events_2 if ev == "confirmation"]) == 1

    # Approve step 2 -> executes step 2, then agent completes
    events_3 = []
    async def run_3():
        async for ev in agent.resume(task_id=task_id, approved=True):
            events_3.append(ev)

    asyncio.run(run_3())
    assert executed == ["step1", "step2"]
    done_events = [d for ev, d in events_3 if ev == "done"]
    assert len(done_events) == 1
    assert done_events[0]["status"] == TaskStatus.COMPLETED.value


# 4. Stale / Duplicate Resume Protection
def test_resume_on_non_confirming_task_reports_error():
    db = SessionLocal()
    task = Task(title="Completed Task", request="Already done", status=TaskStatus.COMPLETED.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    agent = AgentEngine()
    events = []
    async def run_invalid():
        async for ev in agent.resume(task_id=task_id, approved=True):
            events.append(ev)

    asyncio.run(run_invalid())
    assert len(events) == 1
    assert events[0][0] == "error"
    assert "not waiting for approval" in events[0][1]["message"]
