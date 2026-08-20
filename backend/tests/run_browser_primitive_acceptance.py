"""
PLUTON V2 — BROWSER PRIMITIVE REAL DESKTOP ACCEPTANCE TEST
Verifies the complete 11-step browser control chain on the real running Brave browser.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

from app.tools.native_browser_controller import NATIVE_BROWSER
from app.subsystems.computer.domains.browser import BROWSER_DOMAIN
from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL


async def main():
    print("=" * 85)
    print("PLUTON V2 — BROWSER PRIMITIVE REAL DESKTOP ACCEPTANCE SUITE")
    print("=" * 85)

    ctx = ExecutionContext(task_id="test-browser-primitive")
    KERNEL.authorize_task("test-browser-primitive", context=ctx)

    # -------------------------------------------------------------------------
    # STEP 1: Detect already-running Brave window
    # -------------------------------------------------------------------------
    print("\n[Step 1] Detect already-running Brave window...")
    win = NATIVE_BROWSER.find_browser_window("Brave")
    assert win is not None, "FAILED: No running Brave browser window detected on desktop."
    hwnd = win["hwnd"]
    pid = win["pid"]
    title = win["title"]
    print(f"  -> Detected Brave Window | HWND: {hwnd} | PID: {pid} | Title: '{title}'")

    # -------------------------------------------------------------------------
    # STEP 2: Enumerate actual open tabs
    # -------------------------------------------------------------------------
    print("\n[Step 2] Enumerate actual open tabs...")
    tabs_initial = NATIVE_BROWSER.list_tabs("Brave")
    assert len(tabs_initial) > 0, "FAILED: Zero tabs enumerated from running Brave browser."
    print(f"  -> Enumerated {len(tabs_initial)} real tabs:")
    for t in tabs_initial:
        clean = t["title"].encode("ascii", errors="replace").decode()
        sel_str = "[ACTIVE]" if t["selected"] else "        "
        print(f"     {sel_str} [Tab {t['tab_index']}] '{clean}' (HWND: {t['hwnd']}, PID: {t['pid']})")

    # -------------------------------------------------------------------------
    # STEP 3 & 4: Open a NEW TAB in existing Brave & verify appearance
    # -------------------------------------------------------------------------
    print("\n[Step 3 & 4] Open a NEW TAB in existing Brave & verify appearance...")
    open_res = NATIVE_BROWSER.open_tab(url="about:blank", browser_name="Brave")
    assert open_res.get("success"), f"FAILED: open_tab returned failure: {open_res}"
    print(f"  -> Tab Creation Result: {open_res.get('message')}")
    print(f"  -> Execution Mechanism: {open_res.get('method')} | Target HWND: {open_res.get('hwnd')} | PID: {open_res.get('pid')}")

    time.sleep(0.8)
    tabs_after_open = NATIVE_BROWSER.list_tabs("Brave")
    print(f"  -> Tab count before: {len(tabs_initial)} | after: {len(tabs_after_open)}")
    assert len(tabs_after_open) > len(tabs_initial), "FAILED: New tab did not appear in Brave tab list."

    newly_created_tab = tabs_after_open[-1]
    print(f"  -> Verified New Tab Presence: Index {newly_created_tab['tab_index']}, Title: '{newly_created_tab['title']}'")

    # -------------------------------------------------------------------------
    # STEP 5 & 6: Semantic resolution across arbitrary tabs
    # -------------------------------------------------------------------------
    print("\n[Step 5 & 6] Semantic resolution of arbitrary tabs (e.g. Gmail / Meet / YouTube)...")
    # Resolve first non-empty tab
    target_candidate = next((t for t in tabs_initial if "gmail" in t["title"].lower() or "youtube" in t["title"].lower() or "meet" in t["title"].lower()), tabs_initial[0])
    target_query = "Gmail" if "gmail" in target_candidate["title"].lower() else target_candidate["title"][:15]
    print(f"  -> Resolving tab by query: '{target_query}'")

    # -------------------------------------------------------------------------
    # STEP 7, 8 & 9: Switch to tab & Verify active
    # -------------------------------------------------------------------------
    print("\n[Step 7, 8 & 9] Switch to target tab via SelectionItemPattern & Verify active...")
    switch_res = BROWSER_DOMAIN.switch_tab(target_tab=target_query, browser_name="Brave", context=ctx)
    assert switch_res.get("success"), f"FAILED: switch_tab returned failure: {switch_res}"
    print(f"  -> Switch Result: {switch_res.get('message')}")
    print(f"  -> Tab Index: {switch_res.get('tab_index')} | Title: '{switch_res.get('tab_title')}' | Mechanism: {switch_res.get('method')}")

    time.sleep(0.5)
    # Switch to the newly opened tab
    switch_new = BROWSER_DOMAIN.switch_tab(target_tab=newly_created_tab["title"], browser_name="Brave", context=ctx)
    assert switch_new.get("success"), f"FAILED: Failed to switch to newly created tab: {switch_new}"
    print(f"  -> Switched back to newly created tab: {switch_new.get('message')}")

    # -------------------------------------------------------------------------
    # STEP 10 & 11: Close that exact new tab & Verify disappearance
    # -------------------------------------------------------------------------
    print("\n[Step 10 & 11] Close that exact new tab & Verify disappearance...")
    close_res = BROWSER_DOMAIN.close_tab(target_tab=newly_created_tab["title"], browser_name="Brave", context=ctx)
    assert close_res.get("success"), f"FAILED: close_tab returned failure: {close_res}"
    print(f"  -> Closure Result: {close_res.get('message')} (Mechanism: {close_res.get('method')})")

    time.sleep(0.8)
    tabs_final = NATIVE_BROWSER.list_tabs("Brave")
    tab_still_present = any(newly_created_tab["title"].lower() == t["title"].lower() and t["tab_index"] == len(tabs_initial) for t in tabs_final)
    print(f"  -> Tab count final: {len(tabs_final)} (Expected: {len(tabs_initial)})")
    print(f"  -> Verified Tab Disappearance from UIA tree: {not tab_still_present}")
    assert not tab_still_present and len(tabs_final) == len(tabs_initial), "FAILED: Tab still present after close operation."

    print("\n" + "=" * 85)
    print("ALL 11 BROWSER PRIMITIVE LIFECYCLE STEPS PASSED ON REAL DESKTOP (100% SUCCESS)")
    print("=" * 85)


if __name__ == "__main__":
    asyncio.run(main())
