"""Real Desktop Validation Runner for PLUTON Generic Capabilities.

Executes each of the 10 user-requested capabilities sequentially on the real live Windows desktop:
1. "Open a new tab in Brave"
2. "Open a new tab in Brave and navigate to https://google.com"
3. "Tell me the title of the currently active browser tab"
4. "Switch to the tab containing Google"
5. "Close the Google tab"
6. "Open Windows Settings"
7. "List all currently open windows"
8. "Switch to the Settings window"
9. "Open Notepad"
10. "Type 'Hello from Pluton' into Notepad"

For each test, records:
- Semantic intent produced
- Selected capability
- Actual execution tier
- Whether vision/screenshot was invoked (proven via call tracking)
- Post-action verification result
- Final user-visible result
- Latency (ms)
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any

# Ensure backend path is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.agent import AgentEngine
from app.database import SessionLocal, migrate
from app.models import Task, TaskStatus
from app.providers import create_provider
from app.tools.computer_router import ACTION_ROUTER, IntentType


logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("validation")

TEST_CASES = [
    ("Open a new tab in Brave", "BROWSER_TAB_CREATE"),
    ("Open a new tab in Brave and navigate to https://google.com", "BROWSER_NAVIGATE"),
    ("Tell me the title of the currently active browser tab", "BROWSER_TAB_LIST"),
    ("Switch to the tab containing Google", "BROWSER_TAB_SWITCH"),
    ("Close the Google tab", "BROWSER_TAB_CLOSE"),
    ("Open Windows Settings", "APP_LAUNCH"),
    ("List all currently open windows", "WINDOW_LIST"),
    ("Switch to the Settings window", "WINDOW_SWITCH"),
    ("Open Notepad", "APP_LAUNCH"),
    ('Type "Hello from Pluton" into Notepad', "UI_INTERACT"),
]


async def run_single_test(prompt: str, expected_intent_str: str) -> dict[str, Any]:
    print("=" * 80)
    print(f"RUNNING TEST: '{prompt}'")
    print("=" * 80)
    
    t_start = time.perf_counter()
    
    # 1. Intent resolution
    intent = ACTION_ROUTER.parse_intent(prompt)
    print(f" -> Semantic Intent : {intent.intent_type.value} | Target: '{intent.target}' | Value: '{intent.value}'")
    
    # 2. Database Task creation
    db = SessionLocal()
    task = Task(title=f"val_{intent.intent_type.value.lower()}", request=prompt, status="PENDING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()
    
    # 3. Execution via AgentEngine
    provider = create_provider()
    engine = AgentEngine(provider=provider)
    
    activities = []
    text_deltas = []
    done_msg = ""
    status = ""
    
    async for event, data in engine.run(task_id):
        if event == "activity":
            activities.append(data)
            print(f"    [ACTIVITY] {data.get('name')} -> {data.get('summary')} (status: {data.get('status')})")
        elif event == "text":
            text_deltas.append(data.get("delta", ""))
        elif event == "done":
            done_msg = data.get("message", "")
            status = data.get("status", "")
            print(f"    [DONE] status={status} | message: {done_msg}")
            
    latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
    
    # 4. Check whether vision tools were invoked
    vision_tools = {
        "computer.gui_action_workflow",
        "computer.locate_element",
        "computer.inspect_screen",
        "computer.screenshot",
        "computer.verify_screen_change",
    }
    invoked_vision = [a["name"] for a in activities if a.get("name") in vision_tools]
    
    # 5. Determine actual execution tier
    primary_act = activities[0]["name"] if activities else "none"
    tier_map = {
        "browser.open_url": "Tier 1: Native Web Browser API",
        "computer.launch_app": "Tier 1: Native OS Startfile / Executable",
        "terminal.run": "Tier 1: Native OS / Explorer",
        "computer.list_browser_tabs": "Tier 3: Windows UI Automation",
        "computer.switch_browser_tab": "Tier 3: Windows UI Automation",
        "computer.close_browser_tab": "Tier 3: Windows UI Automation",
        "computer.list_windows": "Tier 3: Win32 / UI Automation",
        "computer.switch_window": "Tier 3: Win32 / UI Automation",
        "computer.close_window": "Tier 3: Win32 / UI Automation",
        "computer.inspect_ui_tree": "Tier 3: Windows UI Automation",
        "computer.ui_action": "Tier 3: Windows UI Automation",
        "computer.hotkey": "Tier 4: Deterministic Keyboard Input",
        "computer.keyboard_type": "Tier 4: Deterministic Keyboard Input",
        "computer.locate_element": "Tier 5: Vision / Screenshot Grounding",
        "computer.gui_action_workflow": "Tier 5: Vision Grounded Workflow",
        "computer.mouse_click": "Tier 6: Coordinate Mouse Input",
    }
    execution_tier = tier_map.get(primary_act, "Tier 3: Structured Desktop Layer")
    
    # 6. Post-action verification
    verified, ver_msg = ACTION_ROUTER.verify_action_result(intent, post_delay=0.1)
    print(f" -> Post-Action Verification : {verified} ({ver_msg})")
    print(f" -> Execution Tier           : {execution_tier}")
    print(f" -> Vision Invoked           : {bool(invoked_vision)} ({invoked_vision})")
    print(f" -> Latency                  : {latency_ms} ms")
    print(f" -> Final Output             : {done_msg}")
    print()
    
    return {
        "prompt": prompt,
        "intent": intent.intent_type.value,
        "target": intent.target,
        "capability": intent.intent_type.name,
        "execution_tier": execution_tier,
        "vision_invoked": bool(invoked_vision),
        "vision_tools": invoked_vision,
        "verified": verified,
        "verification_msg": ver_msg,
        "final_result": done_msg,
        "status": status,
        "latency_ms": latency_ms,
        "activities": activities,
    }


async def main():
    migrate()
    results = []

    for prompt, expected_intent in TEST_CASES:
        res = await run_single_test(prompt, expected_intent)
        results.append(res)
        await asyncio.sleep(0.5)
        
    print("=" * 80)
    print("VALIDATION SUITE SUMMARY")
    print("=" * 80)
    for r in results:
        print(f"[{'PASS' if r['status'] == 'COMPLETED' and not r['vision_invoked'] else 'WARN'}] {r['prompt']}")
        print(f"   Intent: {r['intent']} | Tier: {r['execution_tier']} | Vision: {r['vision_invoked']} | Verified: {r['verified']} | Latency: {r['latency_ms']}ms")
        
    out_file = os.path.join(os.path.dirname(__file__), "real_desktop_validation_report.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed report saved to: {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
