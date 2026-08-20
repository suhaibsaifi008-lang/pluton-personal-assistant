import asyncio

import pytest

from app import tools as tools_module
from app.agent import AgentEngine
from app.database import SessionLocal
from app.models import Memory, Session as SessionModel, Task
from app.providers import AIProvider, ProviderEvent, ProviderRequest, ProviderResponse, ToolCall
from app.tools import Tool
from app.security import PermissionLevel


class FakeProvider(AIProvider):
    name = "fake"

    def __init__(self, turns):
        self.turns = list(turns)

    @property
    def model(self):
        return "fake-model"

    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse("resp", "ok")

    async def stream_respond(self, request):
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            yield ProviderEvent(kind="text_delta", text=turn)
            yield ProviderEvent(kind="tool_calls", tool_calls=[], response_id="resp-final")
        else:
            calls, response_id = turn
            yield ProviderEvent(kind="tool_calls", tool_calls=calls, response_id=response_id)


async def collect(iterator):
    return [(event, data) async for event, data in iterator]


def make_task():
    db = SessionLocal()
    task = Task(title="test", request="Do the thing", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()
    return task_id


def load_task(task_id):
    db = SessionLocal()
    task = db.get(Task, task_id)
    db.close()
    return task


@pytest.fixture
def fake_terminal(monkeypatch):
    original = tools_module.TOOLS["terminal.run"]
    calls = {"count": 0}

    def fake_execute(command):
        calls["count"] += 1
        return {"command": command, "exit_code": 0, "output": f"ok: {command}"}

    monkeypatch.setitem(
        tools_module.TOOLS,
        "terminal.run",
        Tool(original.name, original.description, original.permission, original.input_schema, fake_execute),
    )
    return calls


def test_run_completes_with_plain_text():
    task_id = make_task()
    engine = AgentEngine(provider=FakeProvider(["Hello there"]))
    events = asyncio.run(collect(engine.run(task_id)))
    done = [data for event, data in events if event == "done"][0]
    assert done["status"] == "COMPLETED"
    assert done["message"] == "Hello there"
    assert load_task(task_id).status == "COMPLETED"


def test_low_risk_tool_executes_without_confirmation():
    task_id = make_task()
    tool_call = ToolCall(call_id="call_1", name="memory.save", arguments={"content": "user likes tea", "category": "preference"})
    engine = AgentEngine(provider=FakeProvider([([tool_call], "resp-1"), "Saved."]))
    events = asyncio.run(collect(engine.run(task_id)))
    assert not [data for event, data in events if event == "confirmation"]
    done = [data for event, data in events if event == "done"][0]
    assert done["status"] == "COMPLETED"
    db = SessionLocal()
    memories = db.query(Memory).all()
    db.close()
    assert any("tea" in memory.content for memory in memories)


def test_high_risk_tool_pauses_then_approves(fake_terminal):
    task_id = make_task()
    tool_call = ToolCall(call_id="call_1", name="terminal.run", arguments={"command": "list files"})
    engine = AgentEngine(provider=FakeProvider([([tool_call], "resp-1"), "Done with approval."]))
    events = asyncio.run(collect(engine.run(task_id)))

    confirmation = [data for event, data in events if event == "confirmation"][0]
    assert confirmation["confirmations"][0]["name"] == "terminal.run"
    assert confirmation["confirmations"][0]["permission"] == "high"

    paused = load_task(task_id)
    assert paused.status == "CONFIRMING"
    assert paused.checkpoint is not None
    assert fake_terminal["count"] == 0

    engine2 = AgentEngine(provider=FakeProvider(["Done with approval."]))
    events2 = asyncio.run(collect(engine2.resume(task_id, True)))
    done = [data for event, data in events2 if event == "done"][0]
    assert done["status"] == "COMPLETED"
    assert fake_terminal["count"] == 1
    assert load_task(task_id).status == "COMPLETED"


def test_high_risk_tool_denied(fake_terminal):
    task_id = make_task()
    tool_call = ToolCall(call_id="call_1", name="terminal.run", arguments={"command": "list files"})
    engine = AgentEngine(provider=FakeProvider([([tool_call], "resp-1"), "Understood, skipping."]))
    asyncio.run(collect(engine.run(task_id)))

    engine2 = AgentEngine(provider=FakeProvider(["Understood, skipping."]))
    events2 = asyncio.run(collect(engine2.resume(task_id, False)))
    denied = [data for event, data in events2 if event == "activity" and data.get("status") == "denied"]
    assert denied, "expected a denied activity"
    done = [data for event, data in events2 if event == "done"][0]
    assert done["status"] == "COMPLETED"
    assert fake_terminal["count"] == 0


def test_resume_rejects_wrong_state():
    task_id = make_task()
    engine = AgentEngine(provider=FakeProvider([]))
    events = asyncio.run(collect(engine.resume(task_id, True)))
    error = [data for event, data in events if event == "error"][0]
    assert "not waiting" in error["message"]


def test_memory_tools_save_and_recall():
    tools_module._memory_save("user prefers concise answers", "preference")
    result = tools_module._memory_recall("preferences concise", limit=5)
    assert any("concise" in memory["content"] for memory in result["memories"])


def test_agent_context_includes_recalled_memories():
    tools_module._memory_save("user loves dark mode", "preference")
    db = SessionLocal()
    try:
        context = AgentEngine._context(db, "dark mode")
    finally:
        db.close()
    assert "dark mode" in context


def test_session_history_built_from_completed_tasks():
    db = SessionLocal()
    session = SessionModel(title="s")
    db.add(session)
    db.commit()
    db.refresh(session)
    first = Task(title="a", request="question one", response="answer one", status="COMPLETED", session_id=session.id)
    db.add(first)
    db.commit()
    history = AgentEngine._history(db, session.id, exclude_task_id=None)
    db.close()
    assert history == [{"role": "user", "content": "question one"}, {"role": "assistant", "content": "answer one"}]


def test_agent_runs_low_risk_computer_tool_and_pauses_for_high_risk_hotkey():
    task_id = make_task()
    # Step 1: Agent calls computer.screenshot (LOW risk) -> runs directly
    tool_call_low = ToolCall(call_id="call_ss", name="computer.get_active_window", arguments={})
    # Step 2: Agent calls computer.hotkey (HIGH risk) -> triggers confirmation
    tool_call_high = ToolCall(call_id="call_hk", name="computer.hotkey", arguments={"keys": ["ctrl", "s"]})

    engine = AgentEngine(provider=FakeProvider([
        ([tool_call_low], "resp-1"),
        ([tool_call_high], "resp-2"),
        "Saved via shortcut."
    ]))
    events = asyncio.run(collect(engine.run(task_id)))

    # Verify low-risk tool executed without pausing
    activities = [data for event, data in events if event == "activity" and data.get("name") == "computer.get_active_window"]
    assert len(activities) == 1

    # Verify high-risk tool triggered confirmation
    confirmation = [data for event, data in events if event == "confirmation"][0]
    assert confirmation["confirmations"][0]["name"] == "computer.hotkey"
    assert confirmation["confirmations"][0]["permission"] == "high"

    paused = load_task(task_id)
    assert paused.status == "CONFIRMING"

    # Resume with approval
    engine2 = AgentEngine(provider=FakeProvider(["Saved via shortcut."]))
    events2 = asyncio.run(collect(engine2.resume(task_id, True)))
    done = [data for event, data in events2 if event == "done"][0]
    assert done["status"] == "COMPLETED"
    assert load_task(task_id).status == "COMPLETED"