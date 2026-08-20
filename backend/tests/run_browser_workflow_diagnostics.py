"""
Comprehensive Diagnostic Probe for Tests A, B, C, D, E
Tests real capability selection, routing, execution, and verification.
"""

import asyncio
import json
from app.core.runtime import RUNTIME
from app.capabilities.capability_router import CAPABILITY_ROUTER
from app.database import SessionLocal
from app.models import Task
from app.core.contracts import ExecutionContext


TEST_PROMPTS = [
    ("Test A", "OPEN GMAIL IN MY BROWSER"),
    ("Test B", "OPEN A NEW TAB AND OPEN GMAIL"),
    ("Test C", "LIST MY OPEN BROWSER TABS"),
    ("Test D", "SWITCH TO MY EXISTING GMAIL TAB"),
    ("Test E", "OPEN GOOGLE IN MY BROWSER"),
]


async def run_diagnostics():
    print("=" * 80)
    print("PLUTON V2 BROWSER WORKFLOW DIAGNOSTIC PROBE")
    print("=" * 80)

    for test_name, prompt in TEST_PROMPTS:
        print(f"\n--- [{test_name}]: '{prompt}' ---")
        ctx = ExecutionContext(task_id=f"diag-{test_name.lower().replace(' ', '-')}")
        
        # 1. Inspect CapabilityRouter intent parsing
        plan = CAPABILITY_ROUTER.plan_request(prompt, ctx)
        print(f"  [Router Plan] Steps count: {len(plan.steps)}")
        for idx, step in enumerate(plan.steps):
            print(f"    Step {idx+1}: Cap={step.action.capability.value} | Target={step.action.target} | Tier={step.action.tier_requested.value} | Strategy={step.action.verification_strategy.value}")

        # 2. Trace execution through PlutonRuntime
        db = SessionLocal()
        task = Task(title=prompt, request=prompt, status="PENDING")
        db.add(task)
        db.commit()
        db.refresh(task)

        events_captured = []
        try:
            async for event, data in RUNTIME.execute_task(task.id):
                events_captured.append((event, data))
                if event in ("activity", "done", "error", "confirmation"):
                    print(f"    [RUNTIME EVENT: {event}] {json.dumps(data, default=str)}")
        except Exception as e:
            print(f"    [RUNTIME EXCEPTION] {type(e).__name__}: {e}")
        finally:
            db.close()


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
