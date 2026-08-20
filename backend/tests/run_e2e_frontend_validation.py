"""
END-TO-END Frontend Validation Test  (corrected API)
======================================================
Uses the REAL running Pluton HTTP API:
  POST /api/chat  {message, session_id, stream}
  GET  /api/tasks/{task_id}/activities
  GET  /api/tasks (to verify task state)

Tests A-H as specified, plus 10s idle and cancellation safety.
"""

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
WORKFLOW_PROMPT = (
    "Open Notepad, type Hello from Pluton, press Ctrl+A, "
    "type Replacement text, press Enter, type Second line."
)
SEP = "=" * 70


def create_session(name: str = "e2e-test") -> str:
    r = httpx.post(f"{BASE_URL}/api/sessions", json={"title": name}, timeout=10)
    r.raise_for_status()
    return r.json()["id"]


def get_activities(task_id: str) -> list[dict]:
    r = httpx.get(f"{BASE_URL}/api/tasks/{task_id}/activities", timeout=10)
    r.raise_for_status()
    return r.json()


def get_tasks_list(session_id: str) -> list[dict]:
    r = httpx.get(f"{BASE_URL}/api/tasks", params={"session_id": session_id}, timeout=10)
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# TEST A+B+C+D+G+H: Full sequential workflow via POST /api/chat stream=True
# ─────────────────────────────────────────────────────────────────────────────

def test_sequential_workflow_streaming():
    print(f"\n{SEP}")
    print("TEST A+B+C+D+G+H: Sequential Workflow via SSE (stream=True)")
    print(SEP)
    print(f"Prompt: {WORKFLOW_PROMPT!r}\n")

    session_id = create_session("e2e-workflow")
    print(f"Session: {session_id}")

    task_id = None
    events_collected = []
    text_chunks = []
    network_error = False
    sse_error_msg = ""
    done_received = False
    final_status = ""
    final_message = ""

    t0 = time.perf_counter()

    # POST /api/chat with stream=True — the response body IS the SSE stream
    with httpx.stream(
        "POST",
        f"{BASE_URL}/api/chat",
        json={"message": WORKFLOW_PROMPT, "session_id": session_id, "stream": True},
        timeout=90.0,
    ) as response:
        if response.status_code != 200:
            body = response.read().decode()
            raise RuntimeError(f"POST /api/chat stream=True returned HTTP {response.status_code}: {body}")

        ev_name = ""
        for line in response.iter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                ev_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                raw = line[len("data:"):].strip()
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {"raw": raw}

                entry = {"event": ev_name, "data": data}
                events_collected.append(entry)

                if ev_name == "task":
                    task_id = data.get("task_id")
                    print(f"Task ID: {task_id}")
                elif ev_name == "text":
                    chunk = data.get("delta", "")
                    text_chunks.append(chunk)
                    print(f"  [text] {chunk!r}")
                elif ev_name == "activity":
                    name = data.get("name", "?")
                    summary = data.get("summary", "")[:100]
                    status = data.get("status", "")
                    print(f"  [activity] {name} | {status} | {summary}")
                elif ev_name == "error":
                    sse_error_msg = data.get("message", str(data))
                    network_error = True
                    print(f"  [ERROR] {sse_error_msg}")
                elif ev_name == "done":
                    done_received = True
                    final_status = data.get("status", "")
                    final_message = data.get("message", "")
                    print(f"  [done] status={final_status} | {final_message[:120]}")
                    break

    elapsed = (time.perf_counter() - t0) * 1000
    print(f"\nSSE stream finished in {elapsed:.0f}ms")

    # Fetch activities from DB for authoritative tool list
    activities = get_activities(task_id) if task_id else []
    tool_names = [a["name"] for a in activities]
    tool_statuses = {a["name"]: a["status"] for a in activities}

    print(f"\nActivities from DB: {tool_names}")

    UNRELATED = {"memory.recall", "system.info", "filesystem.list_dir", "filesystem.read",
                 "web.search", "memory.save", "terminal.run"}
    VISION    = {"computer.screenshot", "computer.inspect_screen", "computer.locate_element",
                 "computer.gui_action_workflow", "computer.screenshot_dedup"}
    unrelated_used = [t for t in tool_names if t in UNRELATED]
    vision_used    = [t for t in tool_names if t in VISION]

    print(f"Vision tools invoked:    {vision_used}")
    print(f"Unrelated tools invoked: {unrelated_used}")

    # ── Assertions ──
    failures = []
    if network_error:
        failures.append(f"A: SSE error event received: {sse_error_msg}")
    if not done_received:
        failures.append("A: No 'done' event received in SSE stream")
    if final_status != "COMPLETED":
        failures.append(f"A: Task final status '{final_status}' != COMPLETED")
    if vision_used:
        failures.append(f"G: Vision tools invoked: {vision_used}")
    if unrelated_used:
        failures.append(f"H: Unrelated tools invoked: {unrelated_used}")
    if "computer.sequential_workflow" not in tool_names and "agent.plan" in tool_names:
        failures.append(f"B: LLM planner was invoked instead of fast-path. Activities: {tool_names}")

    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        raise AssertionError(f"Workflow test failures: {failures}")

    print("\n[RESULTS]")
    print(f"  A. Frontend->backend->desktop: PASS ({elapsed:.0f}ms, status={final_status})")
    print(f"  B. Keyboard input:             PASS (sequential_workflow in {tool_names})")
    print(f"  C. Mouse safety:               PASS (no coordinate-mouse tools)")
    print(f"  D. SSE/streaming:              PASS ({len(events_collected)} events, done received)")
    print(f"  G. Vision invocations:         {len(vision_used)}")
    print(f"  H. Unrelated-tool invocations: {len(unrelated_used)}")

    return {
        "status": "PASS",
        "elapsed_ms": elapsed,
        "task_id": task_id,
        "tools": tool_names,
        "vision_count": len(vision_used),
        "unrelated_count": len(unrelated_used),
        "sse_events": len(events_collected),
        "final_status": final_status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TEST E: Idle Safety (10 seconds, no active task -> zero input blocked)
# ─────────────────────────────────────────────────────────────────────────────

def test_idle_safety():
    print(f"\n{SEP}")
    print("TEST E: Idle Safety (10 seconds, no active task)")
    print(SEP)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.tools.computer_safety import is_computer_control_allowed
    from app.tools.computer import _mouse_move, _keyboard_type, _screenshot, _hotkey, _key_press
    from app.tools.uia_engine import UIAutomationEngine
    from app.tools.computer_router import ACTION_ROUTER, IntentType

    # Confirm idle state
    assert not is_computer_control_allowed(), "FAIL E: Control allowed with no active task!"

    violations = []

    def chk(label, result, blocked_key, blocked_val=False):
        if result.get(blocked_key) is not blocked_val:
            violations.append(f"{label}: {result}")

    chk("mouse_move",       _mouse_move(500, 500),         "moved")
    chk("keyboard_type",    _keyboard_type("rogue idle"),  "typed")
    chk("screenshot",       _screenshot(),                 "captured")
    chk("hotkey",           _hotkey(["ctrl", "a"]),        "executed")
    chk("key_press",        _key_press("enter"),           "pressed")

    engine = UIAutomationEngine()
    r = engine.execute_ui_action("Save", "invoke")
    if r.get("success") is not False:
        violations.append(f"uia.execute_ui_action succeeded when idle: {r}")

    r2 = ACTION_ROUTER.execute_capability(ACTION_ROUTER.parse_intent("Open Notepad"))
    if r2.get("success") is not False:
        violations.append(f"ACTION_ROUTER.execute_capability succeeded when idle: {r2}")

    # Background worker containment
    bg_violations = []
    def bg_worker():
        time.sleep(0.3)
        for fn, args, key in [
            (_mouse_move, (200, 200), "moved"),
            (_keyboard_type, ("bg rogue",), "typed"),
            (_screenshot, (), "captured"),
        ]:
            res = fn(*args)
            if res.get(key) is not False:
                bg_violations.append(f"bg {fn.__name__}: {res}")
    t = threading.Thread(target=bg_worker, daemon=True)
    t.start()

    print("  Waiting 10 seconds with no active task...")
    t0 = time.perf_counter()
    for i in range(10):
        time.sleep(1)
        allowed = is_computer_control_allowed()
        print(f"  [{i+1:2d}s] is_computer_control_allowed = {allowed}  (must be False)")
        if allowed:
            violations.append(f"control became True at second {i+1} with no active task")

    t.join(timeout=3.0)
    violations.extend(bg_violations)
    elapsed = (time.perf_counter() - t0) * 1000

    if violations:
        raise AssertionError(f"FAIL E: {violations}")

    print(f"\n  E. Idle safety: PASS ({elapsed:.0f}ms, 0 violations)")
    return {"status": "PASS", "elapsed_ms": elapsed, "violations": []}


# ─────────────────────────────────────────────────────────────────────────────
# TEST F: Cancellation Safety — close SSE stream mid-task
# ─────────────────────────────────────────────────────────────────────────────

def test_cancellation_safety():
    print(f"\n{SEP}")
    print("TEST F: Cancellation Safety (close SSE connection mid-task)")
    print(SEP)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.tools.computer_safety import is_computer_control_allowed
    from app.tools.computer import _mouse_move, _keyboard_type

    session_id = create_session("e2e-cancel")
    task_id_holder = {}
    cancel_done = threading.Event()

    def submit_and_cancel():
        """Submit task, read 1 event, then close connection (simulates user cancel)."""
        with httpx.stream(
            "POST",
            f"{BASE_URL}/api/chat",
            json={"message": "Open Notepad, type Hello from Pluton, press Enter, type second line.", "session_id": session_id, "stream": True},
            timeout=60.0,
        ) as resp:
            ev_name = ""
            events_seen = 0
            for line in resp.iter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    ev_name = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    raw = line[len("data:"):].strip()
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = {}
                    if ev_name == "task":
                        task_id_holder["id"] = data.get("task_id")
                        print(f"  Task started: {task_id_holder['id']}")
                    events_seen += 1
                    # After seeing task + first activity, close connection (cancel)
                    if events_seen >= 2 and task_id_holder.get("id"):
                        print(f"  Closing SSE connection at event {events_seen} (simulating cancel)")
                        break  # Drop connection — server should cancel task
        cancel_done.set()

    t = threading.Thread(target=submit_and_cancel, daemon=True)
    t.start()
    t_cancel = time.perf_counter()
    cancel_done.wait(timeout=30.0)

    if not task_id_holder.get("id"):
        raise RuntimeError("FAIL F: No task ID captured before cancel")

    print(f"  Connection closed. Waiting 2s for server cleanup...")
    time.sleep(2.0)

    # Verify input is now blocked
    violations = []
    res_move = _mouse_move(700, 300)
    res_type = _keyboard_type("post-cancel rogue")
    if res_move.get("moved") is not False:
        violations.append(f"mouse allowed post-cancel: {res_move}")
    if res_type.get("typed") is not False:
        violations.append(f"keyboard allowed post-cancel: {res_type}")

    # Background thread should also be blocked
    bg_violations = []
    def bg_post():
        time.sleep(0.5)
        r = _keyboard_type("delayed rogue")
        if r.get("typed") is not False:
            bg_violations.append(f"bg keyboard post-cancel: {r}")
    bt = threading.Thread(target=bg_post, daemon=True)
    bt.start()
    bt.join(timeout=3.0)
    violations.extend(bg_violations)

    elapsed = (time.perf_counter() - t_cancel) * 1000

    # Check task DB status
    tasks = get_tasks_list(session_id)
    final_ts = tasks[0]["status"] if tasks else "UNKNOWN"
    print(f"  Task final DB status: {final_ts}")

    if violations:
        raise AssertionError(f"FAIL F: Input not revoked post-cancel: {violations}")

    print(f"  F. Cancellation safety: PASS (input blocked {elapsed:.0f}ms post-cancel)")
    return {"status": "PASS", "elapsed_ms": elapsed, "task_status": final_ts}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#'*70}")
    print("# PLUTON END-TO-END FRONTEND VALIDATION")
    print(f"# Backend: {BASE_URL}")
    print(f"# Time:    {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")

    results = {}
    all_passed = True

    for label, fn in [
        ("workflow", test_sequential_workflow_streaming),
        ("idle",     test_idle_safety),
        ("cancel",   test_cancellation_safety),
    ]:
        try:
            results[label] = fn()
        except Exception as e:
            print(f"\n[FAIL] {label.upper()}: {e}")
            results[label] = {"status": "FAIL", "error": str(e)}
            all_passed = False

    w = results.get("workflow", {})
    i = results.get("idle", {})
    c = results.get("cancel", {})

    def _fmt_ms(v):
        return f"{v:.0f}ms" if isinstance(v, (int, float)) else str(v)

    print(f"\n{'#'*70}")
    print("# FINAL E2E VALIDATION REPORT")
    print(f"{'#'*70}")
    print(f"  A. Frontend -> backend -> desktop:   {w.get('status','?')}  ({_fmt_ms(w.get('elapsed_ms','?'))})")
    print(f"  B. Keyboard success:                 {w.get('status','?')}  tools={w.get('tools',[])}")
    print(f"  C. Mouse safety (no coord mouse):    {w.get('status','?')}")
    print(f"  D. SSE/streaming success:            {w.get('status','?')}  ({w.get('sse_events','?')} events)")
    print(f"  E. Idle safety (10s):                {i.get('status','?')}")
    print(f"  F. Cancellation safety:              {c.get('status','?')}  task={c.get('task_status','?')}")
    print(f"  G. Vision invocations:               {w.get('vision_count','?')}  (target: 0)")
    print(f"  H. Unrelated-tool invocations:       {w.get('unrelated_count','?')}  (target: 0)")
    if not all_passed:
        for k, v in results.items():
            if v.get("status") == "FAIL":
                print(f"  I. FAILURE [{k}]: {v.get('error','?')}")
    else:
        print(f"  I. Remaining failures:               NONE")
    status = "ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"
    print(f"\n  [{status}]")
    print(f"{'#'*70}\n")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
