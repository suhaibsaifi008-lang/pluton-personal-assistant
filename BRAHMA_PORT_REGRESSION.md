# PLUTON V2 — BROWSER PRIMITIVE & DESKTOP REGRESSION RESULTS

**Date**: August 17, 2026  
**Execution Environment**: Windows 11 Physical Desktop  
**Primary Suite**: `backend/tests/run_browser_primitive_acceptance.py`  
**Result**: **11/11 BROWSER LIFECYCLE STEPS PASSED (100% SUCCESS RATE)**

---

## 1. REAL DESKTOP BROWSER PRIMITIVE ACCEPTANCE RESULTS

```text
=====================================================================================
PLUTON V2 — BROWSER PRIMITIVE REAL DESKTOP ACCEPTANCE SUITE (11 STEPS)
=====================================================================================

[Step 1] Detect already-running Brave window...
  -> Detected Brave Window | HWND: 198216 | PID: 30980 | Title: 'Pluton AI Progress - Brave'

[Step 2] Enumerate actual open tabs...
  -> Enumerated 10 real tabs:
     [ACTIVE] [Tab 0] 'Pluton AI Progress' (HWND: 198216, PID: 30980)
              [Tab 1] '127.0.0.1:5173' (HWND: 198216, PID: 30980)
              [Tab 2] 'Pcell 2026-27 - Google Sheets' (HWND: 198216, PID: 30980)
              [Tab 3] 'Search results - srcasw.placements@rajguru.du.ac.in - Shaheed Rajguru College Mail' (HWND: 198216, PID: 30980)
              [Tab 4] 'indian companies - Brave Search' (HWND: 198216, PID: 30980)
              [Tab 5] 'Inbox (14) - training.placementcell.srcasw@gmail.com - Gmail' (HWND: 198216, PID: 30980)
              [Tab 6] 'company names in noida - Brave Search' (HWND: 198216, PID: 30980)
              [Tab 7] 'Security Verification | LinkedIn' (HWND: 198216, PID: 30980)
              [Tab 8] 'SignalHire' (HWND: 198216, PID: 30980)
              [Tab 9] 'Security Verification | LinkedIn' (HWND: 198216, PID: 30980)

[Step 3 & 4] Open a NEW TAB in existing Brave & verify appearance...
  -> Tab Creation Result: Opened new tab in existing Brave (HWND: 198216) and navigated to 'about:blank'.
  -> Execution Mechanism: existing_browser_tab_create (UIA InvokePattern on 'New Tab' button) | Target HWND: 198216 | PID: 30980
  -> Tab count before: 10 | after: 11
  -> Verified New Tab Presence: Index 10, Title: 'New Tab'

[Step 5 & 6] Semantic resolution of arbitrary tabs (e.g. Gmail / Meet / YouTube)...
  -> Resolving tab by query: 'Gmail'

[Step 7, 8 & 9] Switch to target tab via SelectionItemPattern & Verify active...
  -> Switch Result: Switched to tab 'Inbox (14) - training.placementcell.srcasw@gmail.com - Gmail' in Brave.
  -> Tab Index: 5 | Title: 'Inbox (14) - training.placementcell.srcasw@gmail.com - Gmail' | Mechanism: SelectionItemPattern
  -> Switched back to newly created tab: Switched to tab 'New Tab' in Brave.

[Step 10 & 11] Close that exact new tab & Verify disappearance...
  -> Closure Result: Successfully closed tab 'New Tab' in Brave. (Mechanism: verified_tab_closure via child Close button InvokePattern)
  -> Tab count final: 10 (Expected: 10)
  -> Verified Tab Disappearance from UIA tree: True
```

---

## 2. COMPREHENSIVE ACCEPTANCE & REGRESSION SUMMARY

| Acceptance Suite | Scenarios / Tests | Passed | Failed | Success Rate |
| :--- | :--- | :--- | :--- | :--- |
| **Browser Primitive 11-Step Real Desktop Suite** (`run_browser_primitive_acceptance.py`) | 11 | 11 | 0 | **100%** |
| **Brahma Transplant 10-Test Real Desktop Suite** (`run_brahma_transplant_acceptance.py`) | 10 | 10 | 0 | **100%** |
| **False-Success Regression Suite** (`run_false_success_regression.py`) | 5 | 5 | 0 | **100%** |
| **GUI Workflow Integration Tests** (`test_gui_workflows.py`) | 20 | 20 | 0 | **100%** |
| **Backend Unit & Integration Pytest Suite** (`pytest backend/tests/ -q`) | 346 | 346 | 0 | **100%** |

---

## 3. KEY BROWSER PRIMITIVE ADVANCEMENTS

1. **Zero-Dependency Native COM `IUIAutomation` Bridge**: Direct ctypes COM integration with `CLSID_CUIAutomation` without third-party python wrapper fragility.
2. **Deterministic New Tab Creation in Existing Session**: Invokes the `New Tab` button (`ControlType 50000`) via `InvokePattern.Invoke()` in the running browser's tab strip without spawning duplicate browser processes or calling `webbrowser.open()`.
3. **5-Tier Semantic Tab Resolution**: Matches tabs with exact, case-insensitive, substring, token, and prefix scoring with ambiguity distance protection.
4. **Instant Programmatic Tab Switching**: Uses `SelectionItemPattern.Select()` (`10010`) on the target `TabItemControl` (`50019`) to switch tabs instantaneously on the physical desktop.
5. **Zero-Coordinate Tab Closure**: Locates the tab's child `Close` button and calls `InvokePattern.Invoke()` (`10000`), verifying tab count reduction and tab absence.
