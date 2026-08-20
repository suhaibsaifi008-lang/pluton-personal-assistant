"""
Direct Execution Trace Probe for "OPEN GMAIL TAB IN MY BROWSER"
Runs through PlutonRuntime to see exact events, exceptions, tool invocations, and state transitions.
"""

import asyncio
import json
from app.core.runtime import RUNTIME
from app.database import SessionLocal
from app.models import Task


async def run_trace():
    db = SessionLocal()
    task = Task(title="OPEN GMAIL TAB IN MY BROWSER", request="OPEN GMAIL TAB IN MY BROWSER", status="PENDING")
    db.add(task)
    db.commit()
    db.refresh(task)

    print(f"[PROBE] Created Task ID: {task.id}")
    print(f"[PROBE] Request: {task.request}")
    print("-" * 60)

    try:
        async for event, data in RUNTIME.execute_task(task.id):
            print(f"[EVENT: {event}] {json.dumps(data, default=str)}")
    except Exception as e:
        print(f"[EXCEPTION CAUGHT IN PROBE] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_trace())
