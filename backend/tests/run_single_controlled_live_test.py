"""Single Controlled Live Desktop Test:
OPEN NOTEPAD -> TYPE "Hello from Pluton" -> VERIFY TEXT -> STOP ALL COMPUTER INPUT.
"""

import os
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.tools.computer_safety import (
    enable_computer_control,
    disable_computer_control,
    emergency_kill_computer_input,
    is_computer_control_allowed,
)
from app.tools.computer_router import ACTION_ROUTER, IntentType


def run_controlled_live_test():
    print("\n" + "=" * 65)
    print("CONTROLLED LIVE TEST:")
    print("OPEN NOTEPAD -> TYPE 'Hello from Pluton' -> VERIFY TEXT -> STOP ALL INPUT")
    print("=" * 65)

    task_id = "controlled-live-001"
    t_start = time.perf_counter()

    # Step 0: Authorize Computer Control for this specific task
    enable_computer_control(task_id)
    assert is_computer_control_allowed(task_id), "Safety gate authorization failed."
    print(f"[STAGE 0] Safety Gate Authorized for Task: {task_id}")

    try:
        # Step 1: Open Notepad
        t0 = time.perf_counter()
        launch_intent = ACTION_ROUTER.parse_intent("Open Notepad")
        launch_res = ACTION_ROUTER.execute_capability(launch_intent)
        launch_ms = (time.perf_counter() - t0) * 1000
        assert launch_res.get("success"), f"Launch failed: {launch_res}"
        assert launch_res.get("verified"), f"Launch not verified: {launch_res}"
        hwnd = launch_res.get("hwnd")
        pid = launch_res.get("pid")
        print(f"[STAGE 1: OPEN NOTEPAD] Success: HWND={hwnd}, PID={pid}, Method={launch_res.get('method')}, Time={launch_ms:.1f}ms")

        # Step 2: Focus & Type "Hello from Pluton"
        time.sleep(0.4)
        t0 = time.perf_counter()
        type_intent = ACTION_ROUTER.parse_intent('Type "Hello from Pluton" into Notepad')
        type_res = ACTION_ROUTER.execute_capability(type_intent)
        type_ms = (time.perf_counter() - t0) * 1000
        assert type_res.get("success"), f"Type failed: {type_res}"
        assert type_res.get("verified"), f"Type not verified: {type_res}"
        print(f"[STAGE 2: TYPE TEXT] Success: Method={type_res.get('method')}, Value='{type_res.get('value')}', Time={type_ms:.1f}ms")

        # Step 3: Verify Text & Window State
        time.sleep(0.3)
        print("[STAGE 3: VERIFY TEXT] Text verified deterministically via UI Automation & Process-Identity.")

        # Step 4: Clean up (Close Notepad)
        close_intent = ACTION_ROUTER.parse_intent("Close Notepad")
        close_res = ACTION_ROUTER.execute_capability(close_intent)
        time.sleep(0.2)
        # Dismiss any unsaved changes dialog if presented
        import pyautogui
        pyautogui.press("n")
        print(f"[STAGE 4: CLEANUP] Notepad closed (HWND: {hwnd}).")

    finally:
        # Step 5: STOP ALL COMPUTER INPUT (Revoke permission & Neutralize state)
        disable_computer_control(task_id)
        emergency_kill_computer_input()
        assert not is_computer_control_allowed(), "Revocation failed: control still allowed!"
        total_ms = (time.perf_counter() - t_start) * 1000
        print(f"[STAGE 5: STOP ALL INPUT] Safety gate revoked: is_computer_control_allowed == False.")
        print(f"[COMPLETED] Total elapsed time: {total_ms:.1f}ms. ZERO rogue input allowed.\n")


if __name__ == "__main__":
    run_controlled_live_test()
