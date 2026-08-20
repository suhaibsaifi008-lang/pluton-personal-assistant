import asyncio
import json
import pytest
from sqlalchemy import select

from app.agent import AgentEngine
from app.config import Settings
from app.database import SessionLocal
from app.models import Activity, Task, TaskStatus
from app.providers import AIProvider, ProviderEvent, ProviderRequest, ProviderResponse, ToolCall
from app.tools import TOOLS, Tool, validate_tool_arguments


class MockTurnProvider(AIProvider):
    name = "mock_turn"

    def __init__(self, turns):
        self.turns = list(turns)

    @property
    def model(self):
        return "mock-model"

    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse("resp", "ok")

    async def stream_respond(self, request: ProviderRequest):
        if not self.turns:
            yield ProviderEvent(kind="text_delta", text="No more turns.")
            return
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            yield ProviderEvent(kind="text_delta", text=turn)
            yield ProviderEvent(kind="tool_calls", tool_calls=[], response_id="resp-final")
        else:
            calls, response_id = turn
            yield ProviderEvent(kind="tool_calls", tool_calls=calls, response_id=response_id)


async def collect(iterator):
    return [(event, data) async for event, data in iterator]


# ==========================================
# 1. TOOL ARGUMENT VALIDATION TESTS
# ==========================================

def test_validate_tool_arguments_valid():
    tool = TOOLS["filesystem.read"]
    is_valid, err, args = validate_tool_arguments(tool, {"path": "hello.txt"})
    assert is_valid is True
    assert err is None
    assert args == {"path": "hello.txt"}


def test_validate_tool_arguments_valid_json_string():
    tool = TOOLS["filesystem.read"]
    is_valid, err, args = validate_tool_arguments(tool, '{"path": "hello.txt"}')
    assert is_valid is True
    assert err is None
    assert args == {"path": "hello.txt"}


def test_validate_tool_arguments_malformed_json():
    tool = TOOLS["filesystem.read"]
    is_valid, err, args = validate_tool_arguments(tool, "{bad-json")
    assert is_valid is False
    assert "Malformed JSON" in err


def test_validate_tool_arguments_missing_required():
    tool = TOOLS["filesystem.write"]
    # requires 'path' and 'content'
    is_valid, err, args = validate_tool_arguments(tool, {"path": "test.txt"})
    assert is_valid is False
    assert "Missing required argument" in err
    assert "content" in err


def test_validate_tool_arguments_unexpected_argument():
    tool = TOOLS["filesystem.read"]
    # additionalProperties is False
    is_valid, err, args = validate_tool_arguments(tool, {"path": "test.txt", "unapproved_arg": 123})
    assert is_valid is False
    assert "Unexpected argument" in err
    assert "unapproved_arg" in err


def test_validate_tool_arguments_wrong_type():
    tool = TOOLS["filesystem.read"]
    # path expects string
    is_valid, err, args = validate_tool_arguments(tool, {"path": 12345})
    assert is_valid is False
    assert "must be of type string" in err


def test_validation_failure_does_not_execute_tool(tmp_path):
    executed = []
    fake_tool = Tool(
        name="test.fake",
        description="Fake tool",
        permission=TOOLS["system.info"].permission,
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
        execute=lambda **kwargs: executed.append(kwargs) or {"ok": True},
    )
    is_valid, err, _ = validate_tool_arguments(fake_tool, {"name": 999})
    assert is_valid is False
    assert len(executed) == 0


def test_agent_loop_recovers_from_validation_error(monkeypatch):
    """When a tool validation fails, the agent loop yields an activity and passes the error back in messages."""
    db = SessionLocal()
    task = Task(title="test validation recovery", request="read bad", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    turns = [
        ([ToolCall(call_id="c1", name="filesystem.read", arguments={"wrong_field": "foo"})], "resp-1"),
        "I noticed the arguments were invalid, so here is my final response.",
    ]
    engine = AgentEngine(provider=MockTurnProvider(turns))
    events = asyncio.run(collect(engine.run(task_id)))

    activities = [data for ev, data in events if ev == "activity"]
    assert any("Argument validation failed" in a.get("summary", "") for a in activities)

    done_events = [data for ev, data in events if ev == "done"]
    assert done_events
    assert done_events[0]["status"] == "COMPLETED"
    assert "I noticed the arguments were invalid" in done_events[0]["message"]


# ==========================================
# 2. CIRCUIT BREAKER TESTS
# ==========================================

def test_circuit_breaker_stops_identical_consecutive_calls():
    """Verify that 3 consecutive identical tool calls trip the circuit breaker and terminate."""
    db = SessionLocal()
    task = Task(title="circuit breaker test", request="stuck loop", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    # Provider endlessly yields identical clock.now() calls
    turns = [
        ([ToolCall(call_id="c1", name="clock.now", arguments={})], "resp-1"),
        ([ToolCall(call_id="c2", name="clock.now", arguments={})], "resp-2"),
        ([ToolCall(call_id="c3", name="clock.now", arguments={})], "resp-3"),
        ([ToolCall(call_id="c4", name="clock.now", arguments={})], "resp-4"),
    ]
    engine = AgentEngine(provider=MockTurnProvider(turns))
    events = asyncio.run(collect(engine.run(task_id)))

    done_events = [data for ev, data in events if ev == "done"]
    assert done_events
    assert "repeatedly called with identical arguments" in done_events[0]["message"]

    db = SessionLocal()
    breaker_activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id, Activity.name == "agent.circuit_breaker")))
    assert len(breaker_activities) == 1
    assert "Circuit breaker tripped" in breaker_activities[0].summary
    db.close()


def test_circuit_breaker_allows_distinct_tool_arguments():
    """Verify that calling the same tool with different arguments is NOT blocked by circuit breaker."""
    db = SessionLocal()
    task = Task(title="distinct args test", request="read multiple", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    turns = [
        ([ToolCall(call_id="c1", name="filesystem.read", arguments={"path": "file1.txt"})], "resp-1"),
        ([ToolCall(call_id="c2", name="filesystem.read", arguments={"path": "file2.txt"})], "resp-2"),
        ([ToolCall(call_id="c3", name="filesystem.read", arguments={"path": "file3.txt"})], "resp-3"),
        "Finished reading all files.",
    ]
    engine = AgentEngine(provider=MockTurnProvider(turns))
    events = asyncio.run(collect(engine.run(task_id)))

    done_events = [data for ev, data in events if ev == "done"]
    assert done_events
    assert "Finished reading all files." in done_events[0]["message"]


def test_circuit_breaker_allows_different_tools():
    """Verify that calling different tools in succession is NOT blocked."""
    db = SessionLocal()
    task = Task(title="different tools test", request="multi tool", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    turns = [
        ([ToolCall(call_id="c1", name="clock.now", arguments={})], "resp-1"),
        ([ToolCall(call_id="c2", name="system.info", arguments={})], "resp-2"),
        ([ToolCall(call_id="c3", name="clock.now", arguments={})], "resp-3"),
        "Done with system overview.",
    ]
    engine = AgentEngine(provider=MockTurnProvider(turns))
    events = asyncio.run(collect(engine.run(task_id)))

    done_events = [data for ev, data in events if ev == "done"]
    assert done_events
    assert "Done with system overview." in done_events[0]["message"]


# ==========================================
# 3. CONTEXT BUDGETING TESTS
# ==========================================

def test_history_short_stays_intact():
    db = SessionLocal()
    task1 = Task(session_id="sess-short", title="t1", request="Hello", response="Hi there!", status="COMPLETED")
    task2 = Task(session_id="sess-short", title="t2", request="What is 2+2?", response="It is 4.", status="COMPLETED")
    db.add_all([task1, task2])
    db.commit()

    history = AgentEngine._history(db, "sess-short", exclude_task_id=None, limit_turns=10, max_tokens=4000)
    assert len(history) == 4
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Hi there!"}
    assert history[2] == {"role": "user", "content": "What is 2+2?"}
    assert history[3] == {"role": "assistant", "content": "It is 4."}
    db.close()


def test_history_sliding_window_trims_oldest_turns():
    db = SessionLocal()
    session_id = "sess-long"
    for i in range(10):
        t = Task(session_id=session_id, title=f"t{i}", request=f"Req {i}", response=f"Resp {i}", status="COMPLETED")
        db.add(t)
    db.commit()

    # Limit to 3 turns
    history = AgentEngine._history(db, session_id, exclude_task_id=None, limit_turns=3, max_tokens=4000)
    assert len(history) == 6
    assert history[0]["content"] == "Req 7"
    assert history[1]["content"] == "Resp 7"
    assert history[4]["content"] == "Req 9"
    assert history[5]["content"] == "Resp 9"
    db.close()


def test_history_token_budget_trims_large_history():
    db = SessionLocal()
    session_id = "sess-budget"
    # Create an old turn with huge text (10,000 characters)
    t1 = Task(session_id=session_id, title="t1", request="Old large query", response="X" * 10000, status="COMPLETED")
    # Create a new turn with small text (100 characters)
    t2 = Task(session_id=session_id, title="t2", request="New small query", response="Short answer", status="COMPLETED")
    db.add_all([t1, t2])
    db.commit()

    # Set budget to 200 tokens (~800 chars)
    history = AgentEngine._history(db, session_id, exclude_task_id=None, limit_turns=10, max_tokens=200)
    # t1 exceeds the budget, so only t2 should be retained
    assert len(history) == 2
    assert history[0]["content"] == "New small query"
    assert history[1]["content"] == "Short answer"
    db.close()


def test_memory_context_limit_and_budgeting():
    db = SessionLocal()
    ctx = AgentEngine._context(db, "search term", max_chars=500)
    # Should be a string
    assert isinstance(ctx, str)
    assert len(ctx) <= 500
    db.close()
