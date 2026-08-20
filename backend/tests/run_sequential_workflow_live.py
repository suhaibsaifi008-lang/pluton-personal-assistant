"""
Controlled live test: Full sequential workflow
Open Notepad -> type Hello from Pluton -> Ctrl+A -> type Replacement text -> Enter -> type Second line -> verify -> stop all input
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.computer_safety import (
    enable_computer_control,
    disable_computer_control,
    emergency_kill_computer_input,
    is_computer_control_allowed,
)
from app.tools.computer_router import ACTION_ROUTER


def run():
    print("\n" + "=" * 70)
    print("CONTROLLED LIVE WORKFLOW TEST")
    print("Open Notepad -> type -> Ctrl+A -> replace -> Enter -> type Second line")
    print("=" * 70)

    task_id = "live-workflow-001"
    t_start = time.perf_counter()

    enable_computer_control(task_id)
    assert is_computer_control_allowed(task_id), "Safety gate failed to authorize!"
    print(f"[GATE] Authorized task: {task_id}")

    try:
        prompt = "Open Notepad -> type Hello from Pluton -> Ctrl+A -> type Replacement text -> Enter -> type Second line"
        intent = ACTION_ROUTER.parse_intent(prompt)
        steps = intent.metadata.get("steps", [])

        print(f"\n[PARSED] {intent.intent_type.value} with {len(steps)} steps:")
        for i, s in enumerate(steps):
            print(f"  Step {i+1}: {s.intent_type.value} | '{s.raw_request}' | val={s.value!r}")

        print("\n[EXECUTING] Sequential workflow...")
        result = ACTION_ROUTER.execute_capability(intent)

        print("\n[RESULT]")
        print(f"  success       = {result.get('success')}")
        print(f"  steps_completed = {result.get('steps_completed')} / {result.get('total_steps')}")
        print(f"  message       = {result.get('message')}")
        print(f"  duration_ms   = {result.get('duration_ms')}")

        print("\n[STEP DETAILS]")
        for sr in result.get("step_results", []):
            status = "PASS" if sr.get("success") else "FAIL"
            print(f"  Step {sr['step']}: [{status}] {sr['intent']} | method={sr.get('method')} | {sr.get('message', '')[:80]}")

        assert result.get("success"), f"Workflow did not succeed: {result.get('message')}"

    finally:
        disable_computer_control(task_id)
        emergency_kill_computer_input()
        assert not is_computer_control_allowed(), "Revocation failed!"
        total_ms = (time.perf_counter() - t_start) * 1000
        print(f"\n[STOPPED] All computer input revoked. Total time: {total_ms:.1f}ms")


if __name__ == "__main__":
    run()
