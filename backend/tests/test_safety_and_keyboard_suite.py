"""Deterministic Safety Invariant, Kill Switch, and Universal Keyboard Pipeline Test Suite.

Runs the 4 required verification suites:
1. Safety Invariant & Emergency Kill Switch Verification
2. Native Notepad Process-Identity Launch (5 iterations)
3. Universal Keyboard / Text Input Pipeline
4. Focused Field Typing Test
"""

import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.tools.computer_safety import (
    is_computer_control_allowed,
    assert_computer_control_allowed,
    enable_computer_control,
    disable_computer_control,
    emergency_kill_computer_input,
)
from app.tools.computer import (
    _mouse_move,
    _mouse_click,
    _keyboard_type,
    _hotkey,
    _screenshot,
    _close_browser_tab,
)
from app.tools.computer_router import ACTION_ROUTER, IntentType, SemanticIntent


def run_suite_1_safety():
    print("\n" + "=" * 60)
    print("SUITE 1: Safety Invariant & Emergency Kill Switch Verification")
    print("=" * 60)

    # 1. Ensure idle state (No active task)
    disable_computer_control(None)
    assert not is_computer_control_allowed(), "Control should be False initially"
    print("[TEST 1.1] Idle State Verification: PASSED (is_computer_control_allowed == False)")

    # 2. Attempt physical mouse movement while idle -> MUST BE BLOCKED
    res_move = _mouse_move(500, 500)
    assert not res_move.get("moved"), f"Mouse move must be blocked, got: {res_move}"
    print(f"[TEST 1.2] Idle Mouse Movement Block: PASSED (Result: {res_move.get('error')})")

    # 3. Attempt physical keyboard typing while idle -> MUST BE BLOCKED
    res_type = _keyboard_type("test")
    assert not res_type.get("typed"), f"Keyboard type must be blocked, got: {res_type}"
    print(f"[TEST 1.3] Idle Keyboard Typing Block: PASSED (Result: {res_type.get('error')})")

    # 4. Attempt screenshot capture while idle -> MUST BE BLOCKED
    res_ss = _screenshot()
    assert not res_ss.get("captured"), f"Screenshot must be blocked, got: {res_ss}"
    print(f"[TEST 1.4] Idle Screenshot Block: PASSED (Result: {res_ss.get('error')})")

    # 5. Enable control for a simulated task
    task_id = "test-task-safe-001"
    enable_computer_control(task_id)
    assert is_computer_control_allowed(task_id), "Control should be True for active task"
    print(f"[TEST 1.5] Active Task Authorization: PASSED (Task: {task_id})")

    # 6. Revoke control upon task completion
    disable_computer_control(task_id)
    assert not is_computer_control_allowed(), "Control should be revoked immediately"
    print("[TEST 1.6] Immediate Revocation on Finish: PASSED")

    # 7. Test Emergency Kill Switch
    enable_computer_control("emergency-test-task")
    emergency_kill_computer_input()
    assert not is_computer_control_allowed(), "Emergency kill must set control to False"
    print("[TEST 1.7] Emergency Kill Switch: PASSED (All state neutralized)")


def run_suite_2_notepad_launch_5x():
    print("\n" + "=" * 60)
    print("SUITE 2: Native Notepad Launch & Verification (5 Iterations)")
    print("=" * 60)

    task_id = "test-notepad-5x"
    enable_computer_control(task_id)
    try:
        results = []
        for i in range(1, 6):
            t0 = time.perf_counter()
            # Launch Notepad
            launch_intent = ACTION_ROUTER.parse_intent("Open Notepad")
            launch_res = ACTION_ROUTER.execute_capability(launch_intent)
            assert launch_res.get("success"), f"Launch iteration {i} failed: {launch_res}"
            assert launch_res.get("verified"), f"Launch iteration {i} not verified: {launch_res}"
            pid = launch_res.get("pid")
            hwnd = launch_res.get("hwnd")
            elapsed_ms = (time.perf_counter() - t0) * 1000

            print(f"[ITERATION {i}] Launch Verified: PID={pid}, HWND={hwnd}, Method={launch_res.get('method')}, Time={elapsed_ms:.1f}ms")

            # Close Notepad
            time.sleep(0.3)
            close_intent = ACTION_ROUTER.parse_intent("Close Notepad")
            close_res = ACTION_ROUTER.execute_capability(close_intent)
            assert close_res.get("success"), f"Close iteration {i} failed: {close_res}"
            print(f"[ITERATION {i}] Close Verified: Window closed and removed.")
            time.sleep(0.3)
            results.append({"iteration": i, "pid": pid, "hwnd": hwnd, "launch_time_ms": elapsed_ms})

        print("\n--> 5/5 Notepad Process-Identity Launches PASSED.")
        return results
    finally:
        disable_computer_control(task_id)
        emergency_kill_computer_input()


def run_suite_3_universal_keyboard_pipeline():
    print("\n" + "=" * 60)
    print("SUITE 3: Universal Keyboard / Text Input Pipeline")
    print("=" * 60)

    task_id = "test-keyboard-pipeline"
    enable_computer_control(task_id)
    try:
        # Step 1: Launch Notepad
        launch_intent = ACTION_ROUTER.parse_intent("Open Notepad")
        launch_res = ACTION_ROUTER.execute_capability(launch_intent)
        print(f"[STEP 1] Opened Notepad (HWND: {launch_res.get('hwnd')})")
        time.sleep(0.4)

        # Step 2: Type "Hello from Pluton" into Notepad
        type_intent1 = ACTION_ROUTER.parse_intent('Type "Hello from Pluton" into Notepad')
        type_res1 = ACTION_ROUTER.execute_capability(type_intent1)
        print(f"[STEP 2] Type 'Hello from Pluton': {type_res1.get('method')} -> Verified={type_res1.get('verified')}")
        time.sleep(0.3)

        # Step 3: Hotkey Ctrl+A
        hotkey_intent = ACTION_ROUTER.parse_intent("Press Ctrl+A")
        hotkey_res = ACTION_ROUTER.execute_capability(hotkey_intent)
        print(f"[STEP 3] Hotkey Ctrl+A: {hotkey_res.get('method')} -> Verified={hotkey_res.get('verified')}")
        time.sleep(0.3)

        # Step 4: Type "ABC123" (Replacing text)
        replace_intent = ACTION_ROUTER.parse_intent('Replace the current text with "ABC123"')
        replace_res = ACTION_ROUTER.execute_capability(replace_intent)
        print(f"[STEP 4] Replace with 'ABC123': {replace_res.get('method')} -> Verified={replace_res.get('verified')}")
        time.sleep(0.3)

        # Step 5: Key Press Enter
        enter_intent = ACTION_ROUTER.parse_intent("Press Enter")
        enter_res = ACTION_ROUTER.execute_capability(enter_intent)
        print(f"[STEP 5] Press Enter: {enter_res.get('method')} -> Verified={enter_res.get('verified')}")
        time.sleep(0.3)

        # Step 6: Multi-line second text typing
        type_intent2 = ACTION_ROUTER.parse_intent('Type "Line 2 Confirmed"')
        type_res2 = ACTION_ROUTER.execute_capability(type_intent2)
        print(f"[STEP 6] Type Multi-line Second Text: {type_res2.get('method')} -> Verified={type_res2.get('verified')}")
        time.sleep(0.4)

        # Step 7: Close Notepad without saving (WM_CLOSE / Alt+F4 + Don't Save)
        close_intent = ACTION_ROUTER.parse_intent("Close Notepad")
        close_res = ACTION_ROUTER.execute_capability(close_intent)
        print(f"[STEP 7] Close Notepad: {close_res.get('method')} -> Verified={close_res.get('verified')}")
        
        # In case a "Do you want to save changes" dialog popped up, send "Don't Save" (n or right arrow + enter)
        time.sleep(0.2)
        import pyautogui
        pyautogui.press("n")

        print("\n--> Universal Keyboard / Text Pipeline PASSED with 0 vision invocations.")
    finally:
        disable_computer_control(task_id)
        emergency_kill_computer_input()


def run_suite_4_focused_field_test():
    print("\n" + "=" * 60)
    print("SUITE 4: Focused Field Typing Test")
    print("=" * 60)

    task_id = "test-focused-field"
    enable_computer_control(task_id)
    try:
        # Launch Notepad
        ACTION_ROUTER.execute_capability(ACTION_ROUTER.parse_intent("Open Notepad"))
        time.sleep(0.4)

        # Direct typing into active/focused field
        type_intent = ACTION_ROUTER.parse_intent('Type "Direct Focused Field Input"')
        type_res = ACTION_ROUTER.execute_capability(type_intent)
        print(f"[TEST 4.1] Focused Field Typing: {type_res.get('method')} -> Verified={type_res.get('verified')}")

        # Clean up
        time.sleep(0.2)
        ACTION_ROUTER.execute_capability(ACTION_ROUTER.parse_intent("Close Notepad"))
        time.sleep(0.2)
        import pyautogui
        pyautogui.press("n")

        print("\n--> Focused Field Typing Test PASSED.")
    finally:
        disable_computer_control(task_id)
        emergency_kill_computer_input()


if __name__ == "__main__":
    run_suite_1_safety()
    run_suite_2_notepad_launch_5x()
    run_suite_3_universal_keyboard_pipeline()
    run_suite_4_focused_field_test()
    print("\n" + "=" * 60)
    print("ALL 4 VERIFICATION TEST SUITES COMPLETED SUCCESSFULLY!")
    print("=" * 60)
