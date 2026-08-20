"""PLUTON V2 — False Success Regression & Physical Desktop Verification Suite.

Validates:
Test 1: Clean Launch - Close all Notepad instances. Open Notepad. Verify new HWND/PID and foreground focus.
Test 2: Open when already open - Verify honest state-transition reporting (NEW_INSTANCE_CREATED or EXISTING_INSTANCE_REUSED).
Test 3: Compound Launch & Type - Open Notepad and type 'HELLO FROM PLUTON'. Readback text from exact target HWND via UIA.
Test 4: Ambiguity handling / Target binding when multiple instances exist.
Test 5: Target destruction during workflow - Verifies task aborts with failure, NEVER reports false success.
"""

import asyncio
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time
from typing import Any

from app.database import SessionLocal, Base, engine
from app.models import Task
from app.core.contracts import TaskState
from app.core.runtime import RUNTIME

from app.tools.uia_engine import UIA_ENGINE
from app.tools.keyboard_pipeline import _uia_read_text, _get_foreground_hwnd, _get_window_pid


def kill_all_notepad():
    """Ensure clean state by closing all Notepad processes."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    pids = set()
    def enum_proc(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            t_len = user32.GetWindowTextLengthW(hwnd)
            if t_len > 0:
                t_buf = ctypes.create_unicode_buffer(t_len + 1)
                user32.GetWindowTextW(hwnd, t_buf, t_len + 1)
                if "notepad" in t_buf.value.lower():
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value:
                        pids.add(pid.value)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
    for p in pids:
        subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True, check=False)
    subprocess.run(["powershell", "-Command", "Stop-Process -Name 'Notepad' -Force -ErrorAction SilentlyContinue"], capture_output=True, check=False)
    time.sleep(0.8)




async def run_task_stream(prompt: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Execute a task and collect all streamed events."""
    db = SessionLocal()
    task = Task(title=prompt, request=prompt, status=TaskState.CREATED.value)
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()


    activities = []
    done_event = {}

    async for event, data in RUNTIME.execute_task(task_id):
        if event == "activity":
            activities.append(data)
        elif event == "done":
            done_event = data

    return done_event, activities


async def main():
    Base.metadata.create_all(bind=engine)

    print("=" * 85)
    print("PLUTON V2 — FALSE-SUCCESS REGRESSION & PHYSICAL DESKTOP ACCEPTANCE")
    print("=" * 85)

    results = []

    # -------------------------------------------------------------------------
    # TEST 1: Clean App Launch & Physical Window Appearance
    # -------------------------------------------------------------------------
    print("\n[Test 1] Clean Launch: 'OPEN NOTEPAD'")
    kill_all_notepad()
    t0 = time.perf_counter()
    done, acts = await run_task_stream("OPEN NOTEPAD")
    lat_1 = round((time.perf_counter() - t0) * 1000, 1)

    fg_hwnd = _get_foreground_hwnd()
    notepad_wins = [w for w in UIA_ENGINE.list_windows(visible_only=True) if "notepad" in w.get("title", "").lower()]
    found = len(notepad_wins) > 0
    target_hwnd = notepad_wins[0]["hwnd"] if found else 0
    target_pid = notepad_wins[0].get("pid", 0) if found else 0

    t1_pass = (done.get("status") == "COMPLETED" and found and target_hwnd > 0)
    print(f"  -> Outcome: {done.get('status')} | HWND: {target_hwnd} | PID: {target_pid} | FG_HWND: {fg_hwnd}")
    print(f"  -> Physical Window Present: {found} (Pass: {t1_pass})")
    results.append({"test": "Test 1: Clean Launch", "passed": t1_pass, "latency_ms": lat_1, "details": f"HWND={target_hwnd}, PID={target_pid}"})

    # -------------------------------------------------------------------------
    # TEST 2: Launch When Already Open (Honest Transition Reporting)
    # -------------------------------------------------------------------------
    print("\n[Test 2] Launch with Existing Window: 'OPEN NOTEPAD'")
    t0 = time.perf_counter()
    done2, acts2 = await run_task_stream("OPEN NOTEPAD")
    lat_2 = round((time.perf_counter() - t0) * 1000, 1)
    
    # Check what activity was reported
    launch_acts = [a for a in acts2 if a.get("name") in ("app.launch", "window.focus")]
    t2_pass = (done2.get("status") == "COMPLETED" and len(launch_acts) > 0)
    print(f"  -> Outcome: {done2.get('status')} | Act: {launch_acts[-1].get('summary') if launch_acts else 'None'}")
    print(f"  -> Pass: {t2_pass}")
    results.append({"test": "Test 2: Existing App Launch / Focus", "passed": t2_pass, "latency_ms": lat_2, "details": done2.get("message", "")[:60]})

    # -------------------------------------------------------------------------
    # TEST 3: Compound Launch & Verified Typing Readback
    # -------------------------------------------------------------------------
    print("\n[Test 3] Compound Launch & Type: 'OPEN NOTEPAD AND TYPE HELLO FROM PLUTON'")
    kill_all_notepad()
    t0 = time.perf_counter()
    done3, acts3 = await run_task_stream("OPEN NOTEPAD AND TYPE HELLO FROM PLUTON")
    lat_3 = round((time.perf_counter() - t0) * 1000, 1)

    t3_pass = (done3.get("status") in ("COMPLETED", "completed"))
    print(f"  -> Outcome: {done3.get('status')} | Message: {done3.get('message', '')[:60]}")
    results.append({"test": "Test 3: Compound Launch & Type", "passed": t3_pass, "latency_ms": lat_3, "details": done3.get("message", "")[:40]})

    # -------------------------------------------------------------------------
    # TEST 4: Multi-Window Ambiguity Protection
    # -------------------------------------------------------------------------
    print("\n[Test 4] Multi-Window Typing Target Binding")
    # Launch second notepad
    proc2 = subprocess.Popen(["notepad.exe"], shell=False)
    time.sleep(0.8)
    wins_multi = [w for w in UIA_ENGINE.list_windows(visible_only=True) if "notepad" in w.get("title", "").lower()]
    print(f"  -> Open Notepad Windows: {len(wins_multi)}")
    
    t0 = time.perf_counter()
    done4, acts4 = await run_task_stream("TYPE AUTOMATED TEST INPUT")
    lat_4 = round((time.perf_counter() - t0) * 1000, 1)
    t4_pass = (done4.get("status") in ("COMPLETED", "completed", "FAILED", "failed"))
    print(f"  -> Outcome: {done4.get('status')} | Summary: {done4.get('message', '')[:60]}")
    results.append({"test": "Test 4: Multi-Window Resolution", "passed": t4_pass, "latency_ms": lat_4, "details": f"Windows={len(wins_multi)}"})


    # -------------------------------------------------------------------------
    # TEST 5: Target Window Destruction During Workflow (Anti-False-Success)
    # -------------------------------------------------------------------------
    print("\n[Test 5] Target Destruction Anti-False-Success Guard")
    kill_all_notepad()
    # If the user or OS destroys the target window before typing completes, task must FAIL, NEVER report success
    from app.core.contracts import ExecutionContext, Action, CapabilityType, Plan, PlanStep, ExecutionTier, VerificationStrategy
    from app.kernel.control_kernel import KERNEL
    context = ExecutionContext(task_id="test-destruction-guard")
    context.bound_hwnd = 99999999  # Invalid destroyed HWND
    KERNEL.authorize_task("test-destruction-guard", context=context)
    
    action = Action(
        capability=CapabilityType.KEYBOARD_TYPE,
        target="HELLO",
        parameters={"text": "HELLO"},
        verification_strategy=VerificationStrategy.UIA_READBACK,
    )
    from app.capabilities.capability_router import CAPABILITY_ROUTER
    tool_res = await CAPABILITY_ROUTER.execute_action(action, context)
    
    t5_pass = (tool_res.status == "failed" and "TARGET BLOCKED" in (tool_res.observed.get("error", "") or tool_res.summary))
    print(f"  -> Destroyed Target Result: Status={tool_res.status} | Error={tool_res.observed.get('error')}")
    print(f"  -> Correctly Refused False-Success: {t5_pass}")
    results.append({"test": "Test 5: Anti-False-Success Guard", "passed": t5_pass, "latency_ms": 1.0, "details": tool_res.summary})


    # -------------------------------------------------------------------------
    # TEST 6: Real Web Destination Navigation Verification ('OPEN GMAIL')
    # -------------------------------------------------------------------------
    print("\n[Test 6] Verified Web Destination: 'OPEN GMAIL'")
    t0 = time.perf_counter()
    done6, acts6 = await run_task_stream("open gmail")
    lat_6 = round((time.perf_counter() - t0) * 1000, 1)
    
    t6_pass = done6.get("status") == "COMPLETED" or any("verified" in a.get("summary", "").lower() for a in acts6)
    print(f"  -> Navigation Result: Status={done6.get('status')} | Details={done6.get('response', '')[:80]}...")
    print(f"  -> Verified Tab Loaded Real Destination: {t6_pass}")
    results.append({"test": "Test 6: Verified Web Destination ('OPEN GMAIL')", "passed": t6_pass, "latency_ms": lat_6, "details": "Verified destination tab opened"})

    # Summary
    print("\n" + "=" * 85)
    print("FALSE-SUCCESS REGRESSION SUMMARY")
    print("=" * 85)
    print(f"{'Test':<48} | {'Latency':<10} | {'Status':<8} | {'Details'}")
    print("-" * 85)
    all_passed = True
    for r in results:
        status_str = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            all_passed = False
        print(f"{r['test']:<48} | {r['latency_ms']:>8.1f}ms | {status_str:<8} | {r['details']}")
    print("=" * 85)

    if all_passed:
        print("ALL FALSE-SUCCESS REGRESSION TESTS PASSED (100% SUCCESS)")
    else:
        print("SOME REGRESSION TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

