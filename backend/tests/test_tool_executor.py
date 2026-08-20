import asyncio
import json
import pytest
from sqlalchemy import select

from app.database import SessionLocal, migrate
from app.models import Activity, Task
from app.security import PermissionLevel
from app.tool_executor import ToolExecutionResult, ToolExecutor, persist_activity
from app.tools import Tool, ToolRegistry


def setup_function():
    migrate()


def test_tool_executor_successful_execution():
    db = SessionLocal()
    task = Task(title="test", request="test req", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="test.echo",
            description="Echoes input",
            permission=PermissionLevel.LOW,
            input_schema={"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"], "additionalProperties": False},
            execute=lambda msg: {"echo": msg},
        )
    )
    executor = ToolExecutor(reg)

    res, (ev_name, ev_data) = asyncio.run(
        executor.execute_call(db, task.id, "test.echo", "call_123", {"msg": "hello"}, approved=True)
    )

    assert isinstance(res, ToolExecutionResult)
    assert res.call_id == "call_123"
    assert res.name == "test.echo"
    assert res.status == "completed"
    assert res.observed == {"echo": "hello"}
    assert ev_name == "activity"
    assert ev_data["status"] == "completed"
    assert res.output_payload == {
        "type": "function_call_output",
        "call_id": "call_123",
        "name": "test.echo",
        "output": json.dumps({"echo": "hello"}),
    }
    assert res.message_payload == {
        "role": "tool",
        "tool_call_id": "call_123",
        "content": json.dumps({"echo": "hello"}),
    }

    # Verify Activity in DB
    activities = db.scalars(select(Activity).where(Activity.task_id == task.id)).all()
    assert len(activities) == 1
    assert activities[0].name == "test.echo"
    assert activities[0].status == "completed"
    assert json.loads(activities[0].arguments) == {"msg": "hello"}
    assert json.loads(activities[0].result) == {"echo": "hello"}

    db.close()


def test_tool_executor_denial():
    db = SessionLocal()
    task = Task(title="test", request="test req", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="test.action",
            description="Dangerous",
            permission=PermissionLevel.HIGH,
            input_schema={},
            execute=lambda: {"done": True},
        )
    )
    executor = ToolExecutor(reg)

    res, (ev_name, ev_data) = asyncio.run(
        executor.execute_call(db, task.id, "test.action", "call_denied", {}, approved=False)
    )

    assert res.status == "denied"
    assert res.observed.get("denied") is True
    assert ev_data["status"] == "denied"
    assert "Denied by user" in res.summary

    activities = db.scalars(select(Activity).where(Activity.task_id == task.id)).all()
    assert len(activities) == 1
    assert activities[0].status == "denied"

    db.close()


def test_tool_executor_unknown_tool():
    db = SessionLocal()
    task = Task(title="test", request="test req", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    reg = ToolRegistry()
    executor = ToolExecutor(reg)

    res, (ev_name, ev_data) = asyncio.run(
        executor.execute_call(db, task.id, "nonexistent.tool", "call_err", {}, approved=True)
    )

    assert res.status == "failed"
    assert "Unknown tool" in res.observed.get("error", "")
    assert ev_data["status"] == "failed"

    db.close()


def test_tool_executor_validation_failure():
    db = SessionLocal()
    task = Task(title="test", request="test req", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="test.strict",
            description="Strict args",
            permission=PermissionLevel.LOW,
            input_schema={"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"], "additionalProperties": False},
            execute=lambda count: {"val": count},
        )
    )
    executor = ToolExecutor(reg)

    # Missing required argument
    res, _ = asyncio.run(
        executor.execute_call(db, task.id, "test.strict", "call_v1", {}, approved=True)
    )
    assert res.status == "failed"
    assert "Tool argument validation failed" in res.observed.get("error", "")

    # Wrong type
    res2, _ = asyncio.run(
        executor.execute_call(db, task.id, "test.strict", "call_v2", {"count": "not_an_int"}, approved=True)
    )
    assert res2.status == "failed"
    assert "Tool argument validation failed" in res2.observed.get("error", "")

    db.close()


def test_tool_executor_exception_handling():
    db = SessionLocal()
    task = Task(title="test", request="test req", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    def faulty_exec():
        raise RuntimeError("Disk write fault")

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="test.faulty",
            description="Throws error",
            permission=PermissionLevel.LOW,
            input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            execute=faulty_exec,
        )
    )
    executor = ToolExecutor(reg)

    res, (ev_name, ev_data) = asyncio.run(
        executor.execute_call(db, task.id, "test.faulty", "call_exc", {}, approved=True)
    )

    assert res.status == "failed"
    assert "Disk write fault" in res.observed.get("error", "")
    assert "Execution error: Disk write fault" in res.summary

    db.close()


def test_tool_executor_sanitizes_persisted_secrets():
    db = SessionLocal()
    task = Task(title="test", request="test req", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="test.auth",
            description="Handles tokens",
            permission=PermissionLevel.LOW,
            input_schema={"type": "object", "properties": {"api_key": {"type": "string"}}, "required": ["api_key"], "additionalProperties": False},
            execute=lambda api_key: {"secret_token": "sk-secret123", "status": "authenticated"},
        )
    )
    executor = ToolExecutor(reg)

    res, _ = asyncio.run(
        executor.execute_call(db, task.id, "test.auth", "call_sec", {"api_key": "sk-super-secret-key"}, approved=True)
    )

    # In-memory result preserves output for LLM
    assert res.observed["secret_token"] == "sk-secret123"

    # Persisted DB Activity must redact secrets
    activity = db.scalars(select(Activity).where(Activity.task_id == task.id)).one()
    persisted_args = json.loads(activity.arguments)
    persisted_result = json.loads(activity.result)

    assert persisted_args["api_key"] == "[REDACTED]"
    assert persisted_result["secret_token"] == "[REDACTED]"
    assert persisted_result["status"] == "authenticated"

    db.close()
