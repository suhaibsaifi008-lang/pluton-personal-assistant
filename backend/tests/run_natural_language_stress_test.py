"""Phase 2: Natural Language Capability Stress Test Runner.

Executes 40 varied natural-language requests covering browser, window management,
application launching, desktop UI, and file/folder operations against the live desktop.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("stress_test")


STRESS_TEST_PROMPTS = [
    # --- Category 1: Browser Navigation & Tabs (10 requests) ---
    "Get me a fresh browser tab in Brave.",
    "Open a new tab and take me to YouTube.",
    "Go to https://github.com in my browser.",
    "Navigate to reddit.com.",
    "Which page am I looking at right now?",
    "What tabs are currently open in Brave?",
    "Switch back to the YouTube tab.",
    "Go over to the GitHub tab.",
    "Close the YouTube tab.",
    "Close the Reddit tab in Brave.",
    
    # --- Category 2: Window Management & Focus (8 requests) ---
    "What programs do I currently have open?",
    "Show me all running applications.",
    "Bring Brave to the front.",
    "Bring up the Settings window.",
    "Switch back to Brave.",
    "Focus the Notepad window.",
    "Close the Calculator window.",
    "Close Settings window.",
    
    # --- Category 3: Application Launching (8 requests) ---
    "Open Windows settings.",
    "Launch Calculator.",
    "Start Notepad.",
    "Open File Explorer.",
    "Run Windows Terminal.",
    "Open Command Prompt.",
    "Launch Task Manager.",
    "Open Calculator app.",
    
    # --- Category 4: Desktop UI & Text Input (8 requests) ---
    "Write Hello World into Notepad.",
    'Type "Antigravity AI is running" into Notepad.',
    "Inspect the UI elements on screen.",
    "What controls are visible in the active window?",
    "Click the File menu.",
    "Turn Bluetooth on.",
    "Toggle Dark mode.",
    'Enter "search query" into search box.',
    
    # --- Category 5: Files & Directories (6 requests) ---
    "Open Downloads folder.",
    "Explore Documents directory.",
    "Open Desktop folder.",
    "Open file notes.txt.",
    "Show Downloads directory.",
    "Open Documents folder.",
]

TIER_MAP = {
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

VISION_TOOLS = {
    "computer.gui_action_workflow",
    "computer.locate_element",
    "computer.inspect_screen",
    "computer.screenshot",
    "computer.verify_screen_change",
}


async def execute_stress_prompt(idx: int, total: int, prompt: str) -> dict[str, Any]:
    print("-" * 80)
    print(f"[{idx}/{total}] STRESS TEST: \"{prompt}\"")
    print("-" * 80)
    
    t_start = time.perf_counter()
    intent = ACTION_ROUTER.parse_intent(prompt)
    print(f"  -> Intent: {intent.intent_type.value} | Target: '{intent.target}' | Value: '{intent.value}'")
    
    db = SessionLocal()
    task = Task(title=f"stress_{idx}_{intent.intent_type.value.lower()}", request=prompt, status="PENDING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()
    
    provider = create_provider()
    engine = AgentEngine(provider=provider)
    
    activities = []
    done_msg = ""
    status = ""
    
    async for event, data in engine.run(task_id):
        if event == "activity":
            activities.append(data)
            print(f"     [ACTIVITY] {data.get('name')} (status: {data.get('status')})")
        elif event == "done":
            done_msg = data.get("message", "")
            status = data.get("status", "")
            print(f"     [DONE] status={status} | message: {done_msg[:90]}...")
            
    latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
    
    invoked_vision = [a["name"] for a in activities if a.get("name") in VISION_TOOLS]
    primary_act = activities[0]["name"] if activities else "none"
    tier = TIER_MAP.get(primary_act, "Tier 3: Structured Desktop Layer")
    verified, ver_msg = ACTION_ROUTER.verify_action_result(intent, post_delay=0.05)
    
    return {
        "id": idx,
        "request": prompt,
        "intent": intent.intent_type.value,
        "target": intent.target,
        "value": intent.value,
        "capability": intent.intent_type.name,
        "execution_tier": tier,
        "vision_invoked": bool(invoked_vision),
        "vision_tools": invoked_vision,
        "verified": verified,
        "verification_msg": ver_msg,
        "status": status,
        "outcome": done_msg,
        "latency_ms": latency_ms,
        "activities": [a.get("name") for a in activities],
    }


async def main():
    migrate()
    total = len(STRESS_TEST_PROMPTS)
    results = []
    
    print(f"Starting Natural Language Capability Stress Test across {total} requests...")
    for idx, prompt in enumerate(STRESS_TEST_PROMPTS, 1):
        res = await execute_stress_prompt(idx, total, prompt)

        results.append(res)
        await asyncio.sleep(0.3)
        
    out_file = os.path.join(os.path.dirname(__file__), "stress_test_report.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
        
    print("\n" + "=" * 80)
    print("STRESS TEST SUMMARY")
    print("=" * 80)
    for r in results:
        print(f"[{r['id']:02d}] [{r['status']}] {r['request']}")
        print(f"     Intent: {r['intent']:<18} | Tier: {r['execution_tier'][:25]:<25} | Vision: {str(r['vision_invoked']):<5} | Latency: {r['latency_ms']}ms")
    print(f"\nReport written to: {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
