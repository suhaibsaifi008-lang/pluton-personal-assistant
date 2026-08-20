import asyncio
import pytest

from app.agent import AgentEngine
from app.database import Base, SessionLocal, engine
from app.models import Task, TaskStatus
from app.providers.base import AIProvider, ProviderEvent, ProviderRequest, ToolCall


class RepeatedScreenshotProvider(AIProvider):
    def __init__(self):
        self.name = "test"
        self.call_count = 0


    @property
    def model(self) -> str:
        return "test-model"

    async def respond(self, request: ProviderRequest):
        return None

    async def stream_respond(self, request: ProviderRequest):
        self.call_count += 1
        # Continually requests computer.screenshot
        yield ProviderEvent(
            kind="tool_calls",
            response_id=f"resp_{self.call_count}",
            tool_calls=[
                ToolCall(
                    call_id=f"call_{self.call_count}",
                    name="computer.screenshot",
                    arguments={},
                )
            ],
        )




def setup_function():
    Base.metadata.create_all(bind=engine)


def test_repeated_screenshot_circuit_breaker_trips():
    db = SessionLocal()
    task = Task(title="Repeated Screenshot Test", request="Take a look at the screen and inspect it repeatedly", status=TaskStatus.CREATED.value)
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()




    provider = RepeatedScreenshotProvider()
    agent = AgentEngine(provider=provider)
    agent.max_steps = 10


    events = []
    async def run_test():
        async for event in agent.run(task_id=task_id):
            events.append(event)

    asyncio.run(run_test())
    print("EVENTS:", events)

    db = SessionLocal()
    final_task = db.get(Task, task_id)
    print("FINAL TASK:", final_task.status, final_task.response)
    assert final_task.status == TaskStatus.COMPLETED.value
    assert "screenshot" in final_task.response.lower()
    assert "without making progress" in final_task.response.lower()
    db.close()

