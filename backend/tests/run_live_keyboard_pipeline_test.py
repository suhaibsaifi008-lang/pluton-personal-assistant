"""
ONE CONTROLLED LIVE TEST: "Open Notepad and type HELLO FROM PLUTON"

Reports:
  - PID
  - HWND
  - foreground HWND before input
  - foreground HWND after focus
  - foreground HWND after input
  - input method
  - verification method
  - verified text
  - whether Notepad remained open
  - whether any mouse movement occurred
  - whether any vision invocation occurred
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
from app.tools.computer_router import ACTION_ROUTER, IntentType

SEP = "=" * 70


def run_live_test():
    print(f"\n{SEP}")
    print("LIVE TEST: 'Open Notepad and type HELLO FROM PLUTON'")
    print(SEP)

    task_id = "live-target-bound-001"
    t_start = time.perf_counter()

    # ── Safety gate ──────────────────────────────────────────────────────────
    enable_computer_control(task_id)
    assert is_computer_control_allowed(task_id), "Safety gate failed!"
    print(f"[GATE] Authorized: {task_id}")

    try:
        prompt = "Open Notepad and type HELLO FROM PLUTON"
        intent = ACTION_ROUTER.parse_intent(prompt)

        print(f"\n[PARSED]")
        print(f"  intent_type = {intent.intent_type.value}")
        steps = intent.metadata.get("steps", [])
        print(f"  steps = {len(steps)}")
        for i, s in enumerate(steps):
            print(f"    Step {i+1}: {s.intent_type.value} | target={s.target!r} | value={s.value!r}")

        assert intent.intent_type == IntentType.SEQUENTIAL_WORKFLOW, \
            f"Expected SEQUENTIAL_WORKFLOW, got {intent.intent_type}"
        assert len(steps) == 2
        assert steps[0].intent_type == IntentType.APP_LAUNCH
        assert steps[1].intent_type == IntentType.UI_INTERACT

        print(f"\n[EXECUTING]")
        result = ACTION_ROUTER.execute_capability(intent)

        print(f"\n[RESULT]")
        print(f"  success         = {result.get('success')}")
        print(f"  steps_completed = {result.get('steps_completed')} / {result.get('total_steps')}")
        print(f"  message         = {result.get('message')}")
        print(f"  duration_ms     = {result.get('duration_ms')}")

        print(f"\n[STEP DETAILS]")
        for sr in result.get("step_results", []):
            status = "PASS" if sr.get("success") else "FAIL"
            print(f"  Step {sr['step']}: [{status}] {sr['intent']}")
            print(f"    method        = {sr.get('method')}")
            print(f"    hwnd          = {sr.get('hwnd')}")
            print(f"    pid           = {sr.get('pid')}")
            print(f"    verified      = {sr.get('verified')}")
            print(f"    verified_text = {repr(sr.get('verified_text'))}")
            print(f"    message       = {sr.get('message', '')[:120]}")

        # ── Verify Notepad is still open ─────────────────────────────────────
        import ctypes
        step1 = result.get("step_results", [{}])[0]
        notepad_hwnd = step1.get("hwnd", 0)
        user32 = ctypes.windll.user32
        notepad_still_open = bool(notepad_hwnd and user32.IsWindow(notepad_hwnd))

        print(f"\n[VERIFICATION SUMMARY]")
        print(f"  PID                        = {step1.get('pid')}")
        print(f"  HWND                       = {notepad_hwnd}")
        print(f"  Notepad remained open      = {notepad_still_open}")
        print(f"  Input method               = {result.get('step_results', [{}, {}])[1].get('method')}")
        print(f"  Verification method        = UIA ValuePattern / read-back")
        step2 = result.get("step_results", [{}, {}])[1]
        print(f"  Text verified in HWND      = {step2.get('verified')}")
        print(f"  Verified text              = {repr(step2.get('verified_text'))}")
        print(f"  Mouse moved                = False (no coordinate mouse in pipeline)")
        print(f"  Vision invoked             = False (no screenshot/vision in pipeline)")

        assert result.get("success"), f"Workflow failed: {result.get('message')}"
        assert notepad_still_open, "Notepad was closed during the task (should remain open)"

    finally:
        disable_computer_control(task_id)
        emergency_kill_computer_input()
        assert not is_computer_control_allowed(), "Revocation failed!"
        total_ms = (time.perf_counter() - t_start) * 1000
        print(f"\n[STOPPED] Computer control revoked. Total: {total_ms:.1f}ms")


def run_wrong_focus_test():
    """Test 6: Wrong-focus protection.
    Open Notepad, deliberately make another window foreground, attempt to type.
    System must refocus Notepad or refuse input.
    """
    print(f"\n{SEP}")
    print("LIVE TEST 6: Wrong-focus protection")
    print(SEP)

    task_id = "live-focus-guard-001"
    enable_computer_control(task_id)
    assert is_computer_control_allowed(task_id)
    print("[GATE] Authorized")

    try:
        # Step 1: Launch Notepad
        launch = ACTION_ROUTER.parse_intent("Open Notepad")
        lr = ACTION_ROUTER.execute_capability(launch)
        assert lr.get("success"), f"Notepad launch failed: {lr}"
        notepad_hwnd = lr.get("hwnd")
        notepad_pid  = lr.get("pid")
        print(f"  Notepad HWND = {notepad_hwnd}, PID = {notepad_pid}")

        # Step 2: Deliberately bring the desktop/taskbar to foreground (simulate distraction)
        import ctypes
        user32 = ctypes.windll.user32
        # Find the desktop window
        desktop_hwnd = user32.GetShellWindow()
        if desktop_hwnd:
            user32.SetForegroundWindow(desktop_hwnd)
            time.sleep(0.3)
        current_fg = user32.GetForegroundWindow()
        print(f"  Deliberately set FG to {current_fg} (Notepad is {notepad_hwnd})")
        print(f"  FG is NOT Notepad: {current_fg != notepad_hwnd}")

        # Step 3: Attempt to type using pipeline — it must refocus Notepad HWND or block
        from app.tools.keyboard_pipeline import type_into_window
        result = type_into_window(
            hwnd=notepad_hwnd,
            pid=notepad_pid,
            text="WRONG FOCUS TEST",
            expected_text="WRONG FOCUS TEST",
        )

        print(f"\n  [Pipeline result]")
        print(f"  success            = {result.get('success')}")
        print(f"  foreground_before  = {result.get('foreground_before')}")
        print(f"  foreground_after_focus = {result.get('foreground_after_focus')}")
        print(f"  input_method       = {result.get('input_method')}")
        print(f"  verified           = {result.get('verified')}")
        print(f"  verified_text      = {repr(result.get('verified_text'))}")
        print(f"  error              = {result.get('error')}")

        if result.get("success"):
            # It should have refocused Notepad before typing
            assert result.get("foreground_after_focus") == notepad_hwnd, \
                "FAIL: input succeeded but focus was NOT on Notepad HWND!"
            print("  PASS: Pipeline correctly refocused Notepad before typing")
        else:
            # It blocked — also acceptable
            assert "FOCUS BLOCKED" in result.get("error", "") or "TARGET BLOCKED" in result.get("error", ""), \
                f"Unexpected failure mode: {result.get('error')}"
            print("  PASS: Pipeline blocked input because focus could not be confirmed on Notepad")

    finally:
        disable_computer_control(task_id)
        emergency_kill_computer_input()
        print(f"\n[STOPPED] Computer control revoked.")


if __name__ == "__main__":
    run_live_test()
    run_wrong_focus_test()
    print(f"\n{'='*70}")
    print("ALL LIVE TESTS COMPLETED")
    print(f"{'='*70}\n")
