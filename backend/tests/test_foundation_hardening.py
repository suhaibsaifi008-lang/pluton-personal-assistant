import asyncio
import json
import pytest
from sqlalchemy import select

from app import database, models, security, tools as tools_module
from app.agent import AgentEngine
from app.database import SessionLocal, engine, migrate, Base
from app.models import Activity, Memory, Session as SessionModel, Task
from app.providers import AIProvider, ProviderEvent, ProviderRequest, ProviderResponse, ToolCall
from app.security import PermissionLevel, sanitize_for_storage
from app.tools import Tool


class MockAgentProvider(AIProvider):
    name = "mock"

    def __init__(self, turns):
        self.turns = list(turns)

    @property
    def model(self):
        return "mock-model"

    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse("resp", "ok")

    async def stream_respond(self, request: ProviderRequest):
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            yield ProviderEvent(kind="text_delta", text=turn)
            yield ProviderEvent(kind="tool_calls", tool_calls=[], response_id="resp-final")
        else:
            calls, response_id = turn
            yield ProviderEvent(kind="tool_calls", tool_calls=calls, response_id=response_id)


async def collect(iterator):
    return [(event, data) async for event, data in iterator]


def test_sqlite_wal_mode_and_busy_timeout():
    """Verify that SQLite engine initializes with WAL mode and 5000ms busy timeout."""
    with engine.connect() as conn:
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy_timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        assert str(journal_mode).lower() == "wal"
        assert int(busy_timeout) == 5000


def test_secret_sanitization_in_storage():
    """Verify that sensitive keys, tokens, and authorization headers are redacted."""
    raw_payload = {
        "api_key": "freellmapi-0feb40985062e3aae6bb6149def147205b3bcfdea1a5eae3",
        "secret_token": "sk-proj-1234567890",
        "password": "SuperSecretPassword123!",
        "auth_header": "Bearer my-secret-jwt-token",
        "nested": {
            "credentials": "my-secret-creds",
            "safe_field": "safe_value",
            "url": "https://api.openai.com/v1?api_key=secret",
        },
        "query": "What is the weather today?",
    }
    sanitized = sanitize_for_storage(raw_payload)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["secret_token"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["auth_header"] == "[REDACTED]"
    assert sanitized["nested"]["credentials"] == "[REDACTED]"
    assert sanitized["nested"]["safe_field"] == "safe_value"
    assert sanitized["query"] == "What is the weather today?"


def test_tool_activity_persistence_on_successful_task():
    """Verify that tool activities are saved into the activities table with correct task_id."""
    db = SessionLocal()
    task = Task(title="test activity", request="Check clock", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    clock_call = ToolCall(call_id="call_clock", name="clock.now", arguments={})
    engine_inst = AgentEngine(provider=MockAgentProvider([([clock_call], "resp-1"), "The time is now."]))
    events = asyncio.run(collect(engine_inst.run(task_id)))

    done = [data for event, data in events if event == "done"][0]
    assert done["status"] == "COMPLETED"

    # Query persisted activities
    db = SessionLocal()
    activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id).order_by(Activity.created_at.asc())))
    db.close()

    activity_names = [a.name for a in activities]
    assert "agent.plan" in activity_names
    assert "clock.now" in activity_names
    assert "agent.respond" in activity_names

    clock_act = next(a for a in activities if a.name == "clock.now")
    assert clock_act.status == "completed"
    assert clock_act.task_id == task_id
    assert "now" in (clock_act.result or "")


def test_multiple_tool_activities_in_single_task():
    """Verify multi-step tool execution persists multiple activity records in order."""
    db = SessionLocal()
    task = Task(title="multi activity", request="Multi tool task", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    call1 = ToolCall(call_id="call_1", name="clock.now", arguments={})
    call2 = ToolCall(call_id="call_2", name="system.info", arguments={})
    engine_inst = AgentEngine(provider=MockAgentProvider([
        ([call1], "resp-1"),
        ([call2], "resp-2"),
        "All done.",
    ]))
    asyncio.run(collect(engine_inst.run(task_id)))

    db = SessionLocal()
    activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id).order_by(Activity.created_at.asc())))
    db.close()

    names = [a.name for a in activities]
    assert names == ["agent.plan", "clock.now", "system.info", "agent.respond"]
    for act in activities:
        assert act.task_id == task_id
        assert act.status == "completed"


def test_failed_tool_activity_persistence():
    """Verify that failed tool execution records status='failed' and captures error info."""
    db = SessionLocal()
    task = Task(title="failed activity", request="Read missing file", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    # Unknown tool call
    call = ToolCall(call_id="call_bad", name="nonexistent.tool", arguments={"foo": "bar"})
    engine_inst = AgentEngine(provider=MockAgentProvider([([call], "resp-1"), "Handled failure."]))
    asyncio.run(collect(engine_inst.run(task_id)))

    db = SessionLocal()
    activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id)))
    db.close()

    bad_act = next(a for a in activities if a.name == "nonexistent.tool")
    assert bad_act.status == "failed"
    assert "Unknown tool" in (bad_act.result or "")


def test_existing_tasks_continue_working_with_schema_migration():
    """Verify backward-compatibility: existing tasks without activities remain fully queryable."""
    db = SessionLocal()
    legacy_task = Task(
        title="legacy task",
        request="old request",
        response="old response",
        status="COMPLETED",
    )
    db.add(legacy_task)
    db.commit()
    db.refresh(legacy_task)
    task_id = legacy_task.id

    # Migration is idempotent
    migrate()

    fetched = db.get(Task, task_id)
    assert fetched is not None
    assert fetched.title == "legacy task"
    assert fetched.response == "old response"

    # Querying activities for legacy task returns empty list safely
    activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id)))
    assert activities == []
    db.close()


def test_secrets_redacted_when_stored_in_activity():
    """Verify that tool arguments containing API keys/tokens are automatically sanitized in Activity table."""
    db = SessionLocal()
    task = Task(title="secret test", request="Process secret", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    secret_args = {
        "content": "Bearer super-secret-key-12345",
        "category": "auth",
        "api_key": "freellmapi-0feb40985062e3aae6bb6149def147205b3bcfdea1a5eae3",
    }
    tool_call = ToolCall(call_id="call_secret", name="memory.save", arguments=secret_args)
    engine_inst = AgentEngine(provider=MockAgentProvider([([tool_call], "resp-1"), "Saved."]))
    asyncio.run(collect(engine_inst.run(task_id)))

    db = SessionLocal()
    activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id)))
    db.close()

    mem_act = next(a for a in activities if a.name == "memory.save")
    assert mem_act.arguments is not None
    assert "super-secret-key" not in mem_act.arguments
    assert "freellmapi-0feb40985062e3aae6bb6149def147205b3bcfdea1a5eae3" not in mem_act.arguments
    assert "[REDACTED]" in mem_act.arguments
