import asyncio
import json
import pytest
from sqlalchemy import select

from app import database, models
from app.agent import AgentEngine
from app.database import SessionLocal, reconcile_stale_tasks
from app.models import Activity, Task, TaskStatus
from app.providers import AIProvider, ProviderEvent, ProviderRequest, ProviderResponse, ToolCall


class MockSlowProvider(AIProvider):
    name = "mock_slow"

    @property
    def model(self):
        return "mock-model"

    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse("resp", "ok")

    async def stream_respond(self, request: ProviderRequest):
        # Simulate long-running stream that can be cancelled
        yield ProviderEvent(kind="text_delta", text="Starting...")
        await asyncio.sleep(5.0)
        yield ProviderEvent(kind="text_delta", text="Finished.")


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
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            yield ProviderEvent(kind="text_delta", text=turn)
            yield ProviderEvent(kind="tool_calls", tool_calls=[], response_id="resp-final")
        else:
            calls, response_id = turn
            yield ProviderEvent(kind="tool_calls", tool_calls=calls, response_id=response_id)


async def collect(iterator):
    return [(event, data) async for event, data in iterator]


def test_startup_reconciliation_stale_running():
    """Verify that tasks left in RUNNING on server startup are marked FAILED."""
    db = SessionLocal()
    task = Task(title="stale running", request="do work", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    reconcile_stale_tasks()

    db = SessionLocal()
    reconciled = db.get(Task, task_id)
    assert reconciled.status == TaskStatus.FAILED.value
    assert "interrupted" in reconciled.response.lower()

    # Activity recorded
    activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id)))
    assert any(a.name == "system.reconciliation" and a.status == "failed" for a in activities)
    db.close()


def test_startup_reconciliation_stale_confirming_valid():
    """Verify that CONFIRMING tasks with valid checkpoints remain CONFIRMING (recoverable)."""
    db = SessionLocal()
    checkpoint = json.dumps({
        "message": "dangerous action",
        "previous_response_id": "resp-1",
        "steps": 1,
        "pending": [{"call_id": "call_1", "name": "terminal.run", "arguments": {"command": "dir"}}],
    })
    task = Task(title="stale confirming", request="run cmd", status=TaskStatus.CONFIRMING.value, checkpoint=checkpoint)
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    reconcile_stale_tasks()

    db = SessionLocal()
    reconciled = db.get(Task, task_id)
    assert reconciled.status == TaskStatus.CONFIRMING.value
    assert reconciled.checkpoint == checkpoint
    db.close()


def test_startup_reconciliation_stale_confirming_corrupted():
    """Verify that CONFIRMING tasks with missing/corrupted checkpoints are marked FAILED."""
    db = SessionLocal()
    task = Task(title="corrupted confirming", request="bad checkpoint", status=TaskStatus.CONFIRMING.value, checkpoint="invalid-json")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()

    reconcile_stale_tasks()

    db = SessionLocal()
    reconciled = db.get(Task, task_id)
    assert reconciled.status == TaskStatus.FAILED.value
    assert "corrupted" in reconciled.response.lower() or "missing" in reconciled.response.lower()
    db.close()


def test_startup_reconciliation_terminal_states_untouched():
    """Verify that COMPLETED, FAILED, and CANCELLED tasks are untouched by reconciliation."""
    db = SessionLocal()
    completed = Task(title="c", request="r", status=TaskStatus.COMPLETED.value, response="Done.")
    failed = Task(title="f", request="r", status=TaskStatus.FAILED.value, response="Error.")
    cancelled = Task(title="x", request="r", status=TaskStatus.CANCELLED.value, response="Cancelled.")
    db.add_all([completed, failed, cancelled])
    db.commit()
    c_id, f_id, x_id = completed.id, failed.id, cancelled.id
    db.close()

    # Reconcile twice to test idempotency
    reconcile_stale_tasks()
    reconcile_stale_tasks()

    db = SessionLocal()
    assert db.get(Task, c_id).status == TaskStatus.COMPLETED.value
    assert db.get(Task, c_id).response == "Done."
    assert db.get(Task, f_id).status == TaskStatus.FAILED.value
    assert db.get(Task, f_id).response == "Error."
    assert db.get(Task, x_id).status == TaskStatus.CANCELLED.value
    assert db.get(Task, x_id).response == "Cancelled."
    db.close()


def test_illegal_state_transition_rejection():
    """Verify that attempting to run() a task in terminal state produces an error and is rejected."""
    db = SessionLocal()
    task = Task(title="terminal run test", request="do work", status=TaskStatus.COMPLETED.value, response="Done.")
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    engine = AgentEngine(provider=MockTurnProvider(["new answer"]))
    events = asyncio.run(collect(engine.run(task_id)))

    error_events = [data for ev, data in events if ev == "error"]
    assert error_events
    assert "terminal state" in error_events[0]["message"].lower()

    # Task in DB remained COMPLETED
    db = SessionLocal()
    assert db.get(Task, task_id).status == TaskStatus.COMPLETED.value
    assert db.get(Task, task_id).response == "Done."
    db.close()


def test_illegal_resume_transition_rejection():
    """Verify that attempting to resume() a task not in CONFIRMING status is rejected."""
    db = SessionLocal()
    task = Task(title="illegal resume", request="do work", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    engine = AgentEngine(provider=MockTurnProvider([]))
    events = asyncio.run(collect(engine.resume(task_id, True)))

    error_events = [data for ev, data in events if ev == "error"]
    assert error_events
    assert "not waiting for approval" in error_events[0]["message"].lower()
    db.close()


def test_asyncio_cancellation_marks_task_cancelled():
    """Verify that asyncio.CancelledError during execution marks task CANCELLED and re-raises."""
    db = SessionLocal()
    task = Task(title="cancellation test", request="slow task", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    engine = AgentEngine(provider=MockSlowProvider())

    async def run_and_cancel():
        gen = engine.run(task_id)
        # Consume first event
        await anext(gen)
        # Cancel generator
        await gen.aclose()

    asyncio.run(run_and_cancel())

    db = SessionLocal()
    cancelled_task = db.get(Task, task_id)
    assert cancelled_task.status == TaskStatus.CANCELLED.value
    assert "cancelled" in cancelled_task.response.lower()

    activities = list(db.scalars(select(Activity).where(Activity.task_id == task_id)))
    assert any(a.name == "agent.cancel" and a.status == "cancelled" for a in activities)
    db.close()


def test_cancellation_exception_is_not_swallowed():
    """Verify that if a background coroutine is cancelled, CancelledError propagates."""
    db = SessionLocal()
    task = Task(title="propagate cancel", request="slow task", status=TaskStatus.RUNNING.value)
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    engine = AgentEngine(provider=MockSlowProvider())

    async def task_runner():
        async for _ in engine.run(task_id):
            pass

    async def main_canceller():
        t = asyncio.create_task(task_runner())
        await asyncio.sleep(0.05)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(main_canceller())

    db = SessionLocal()
    assert db.get(Task, task_id).status == TaskStatus.CANCELLED.value
    db.close()
