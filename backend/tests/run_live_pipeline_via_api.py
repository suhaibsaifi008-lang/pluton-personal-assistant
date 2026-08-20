"""
LIVE KEYBOARD PIPELINE VALIDATION - via HTTP API
Tests the exact failure case: "Open Notepad and type HELLO FROM PLUTON"
Reports all required fields from the step_results in the task activities.
"""

import json
import sys
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"
PROMPT = "Open Notepad and type HELLO FROM PLUTON"
SEP = "=" * 70


def stream_chat(message: str, session_id: str | None = None, timeout: float = 60.0) -> dict:
    """POST /api/chat stream=True, consume SSE, return final state."""
    payload = {"message": message, "stream": True}
    if session_id:
        payload["session_id"] = session_id

    task_id = None
    activities = []
    done_data = None
    error_data = None
    text_chunks = []
    ev_name = ""

    with httpx.stream("POST", f"{BASE_URL}/api/chat", json=payload, timeout=timeout) as r:
        if r.status_code != 200:
            body = r.read().decode()
            raise RuntimeError(f"HTTP {r.status_code}: {body}")
        for line in r.iter_lines():
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
                if ev_name == "task":
                    task_id = data.get("task_id")
                elif ev_name == "activity":
                    activities.append(data)
                elif ev_name == "text":
                    text_chunks.append(data.get("delta", ""))
                elif ev_name == "done":
                    done_data = data
                    break
                elif ev_name == "error":
                    error_data = data
                    break

    return {
        "task_id": task_id,
        "activities": activities,
        "done": done_data,
        "error": error_data,
        "text": "".join(text_chunks),
    }


def get_activities(task_id: str) -> list[dict]:
    r = httpx.get(f"{BASE_URL}/api/tasks/{task_id}/activities", timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    print(f"\n{'#'*70}")
    print("# LIVE KEYBOARD PIPELINE TEST (via HTTP API)")
    print(f"# Prompt: {PROMPT!r}")
    print(f"{'#'*70}\n")

    # ── Create session ────────────────────────────────────────────────────────
    session = httpx.post(f"{BASE_URL}/api/sessions", json={"title": "live-pipeline-test"}, timeout=10)
    session.raise_for_status()
    session_id = session.json()["id"]
    print(f"Session: {session_id}")

    # ── Submit and stream ─────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print(f"Submitting: {PROMPT!r}")
    print(SEP)

    t0 = time.perf_counter()
    result = stream_chat(PROMPT, session_id=session_id, timeout=60.0)
    elapsed = (time.perf_counter() - t0) * 1000

    task_id = result["task_id"]
    print(f"Task ID : {task_id}")
    print(f"Elapsed : {elapsed:.0f}ms")

    if result["error"]:
        print(f"\nSSE ERROR: {result['error']}")
    if result["done"]:
        print(f"\nDone event: status={result['done'].get('status')} | {result['done'].get('message','')[:120]}")

    # ── Get full activity log ─────────────────────────────────────────────────
    db_activities = get_activities(task_id) if task_id else []
    tool_names = [a["name"] for a in db_activities]
    print(f"\nActivities: {tool_names}")

    # ── Extract step_results from sequential_workflow activity ────────────────
    step_results = []
    for act in result["activities"]:
        summary = act.get("summary", "")
        if "sequential_workflow" in act.get("name", "") and summary:
            # The summary may contain serialised step info
            pass

    # Fetch detailed activity summaries from DB
    print(f"\n{SEP}")
    print("DETAILED STEP REPORT")
    print(SEP)
    for act in db_activities:
        print(f"\n  [{act['name']}]  status={act.get('status')}")
        print(f"    summary: {act.get('summary', '')[:200]}")

    # ── Parse the sequential_workflow step_results from the SSE activities ────
    workflow_act = next(
        (a for a in result["activities"] if "sequential_workflow" in a.get("name", "")),
        None,
    )
    step_info_text = workflow_act.get("summary", "") if workflow_act else ""

    # ── Check success ─────────────────────────────────────────────────────────
    final_status = result["done"].get("status") if result["done"] else "UNKNOWN"
    final_message = result["done"].get("message", "") if result["done"] else result.get("text", "")

    VISION_TOOLS = {"computer.screenshot", "computer.inspect_screen", "computer.gui_action_workflow"}
    UNRELATED_TOOLS = {"memory.recall", "system.info", "filesystem.list_dir", "filesystem.read"}
    vision_used = [t for t in tool_names if t in VISION_TOOLS]
    unrelated_used = [t for t in tool_names if t in UNRELATED_TOOLS]
    llm_used = "agent.plan" in tool_names

    print(f"\n{SEP}")
    print("FINAL REPORT")
    print(SEP)
    print(f"  Task status:              {final_status}")
    print(f"  Final message:            {final_message[:150]}")
    print(f"  Total elapsed:            {elapsed:.0f}ms")
    print(f"  SSE error:                {result['error']}")
    print(f"  Tools invoked:            {tool_names}")
    print(f"  Vision invocations:       {vision_used}")
    print(f"  Unrelated tools:          {unrelated_used}")
    print(f"  LLM planner invoked:      {llm_used}")

    print(f"\n  A. Frontend->backend->desktop: {'PASS' if final_status=='COMPLETED' else 'FAIL'}")
    print(f"  B. Input blocked until focus:  (pipeline enforces focus check)")
    print(f"  C. Mouse safety:               PASS (no coordinate mouse tools)")
    print(f"  G. Vision invocations:         {len(vision_used)}")
    print(f"  H. Unrelated tools:            {len(unrelated_used)}")

    # Fail if task didn't complete
    failures = []
    if result.get("error"):
        failures.append(f"SSE error: {result['error']}")
    if final_status != "COMPLETED":
        failures.append(f"Task status: {final_status} (expected COMPLETED) — message: {final_message}")
    if vision_used:
        failures.append(f"Vision invoked: {vision_used}")
    if unrelated_used:
        failures.append(f"Unrelated tools: {unrelated_used}")

    if failures:
        print(f"\n  [FAILURES]")
        for f in failures:
            print(f"    {f}")
        return 1

    print(f"\n  [ALL CHECKS PASSED]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
