# PLUTON V2 — BRAHMA PARITY REMEDIATION PLAN

**Date**: August 16, 2026  
**Goal**: Bring Pluton V2 computer-control into 100% architectural and behavioral parity with the Brahma reference implementation.  
**Rule**: FREEZE Phase 2 until all remediation items are executed and validated on the real desktop.

---

## 1. Remediation Tasks

### Task 1: Eliminate Legacy Telemetry Aliasing (Stop Lying Telemetry)
* **File**: [`backend/app/core/runtime.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/core/runtime.py)
* **Lines**: ~144–157
* **Action**:
  - Remove `_cap_map` which translated `CapabilityType.BROWSER_NAVIGATE` to `"browser.open_url"` and `APP_LAUNCH` to `"computer.launch_app"`.
  - Set activity name directly to the canonical capability value: `act_name = step.action.capability.value` (e.g. `"browser.navigate"`, `"app.launch"`, `"browser.switch_tab"`, `"browser.close_tab"`, `"browser.list_tabs"`, `"keyboard.type"`).

---

### Task 2: Unified Structured Browser Tab Inventory
* **Files**:
  - [`backend/app/tools/uia_engine.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/tools/uia_engine.py) (`list_browser_tabs`)
  - [`backend/app/subsystems/computer/domains/browser.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/subsystems/computer/domains/browser.py) (`list_tabs`)
* **Action**:
  - In `UIAEngine.list_browser_tabs`, ensure every returned tab object contains structured metadata:
    ```python
    {
        "browser": browser_name,
        "hwnd": hwnd,
        "tab_index": idx,
        "title": t_name,
        "selected": is_selected,
        "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom, "width": rect.width(), "height": rect.height()}
    }
    ```
  - Ensure `BrowserDomainHandler.list_tabs` aggregates structured tabs across all active desktop browser instances if `browser_name` is not strictly found.

---

### Task 3: 5-Tier Semantic Tab Targeting & Ambiguity Protection
* **File**: [`backend/app/subsystems/computer/target_resolver.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/subsystems/computer/target_resolver.py)
* **Function**: `TargetResolver._resolve_browser_tab`
* **Action**:
  - Ensure strict scoring weights matching Brahma reference:
    - Exact equality: `1.0`
    - Case-insensitive equality: `0.95`
    - Substring containment: `0.75 + 0.2 * (len(query)/len(title))`
    - All token containment: `0.60`
    - 4-character prefix match: `0.50`
  - Ambiguity Guard: If $|Score_1 - Score_2| < 0.05$ on distinct tab titles $\rightarrow$ return `AMBIGUOUS_TARGET` and refuse execution.
  - Zero-match Guard: If no tab matches $\rightarrow$ return `TARGET_NOT_FOUND` and refuse execution with zero hardware inputs.

---

### Task 4: Real Desktop Acceptance Validation (Suite A through I)
* **File**: [`backend/tests/run_brahma_parity_acceptance.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/tests/run_brahma_parity_acceptance.py)
* **Actions Tested**:
  1. **Test A**: `OPEN NOTEPAD` (App Launch $\rightarrow$ Window Verification)
  2. **Test B**: `TYPE HELLO FROM PLUTON` (Keyboard Type $\rightarrow$ UIA Readback Verification)
  3. **Test C**: `DETECT BRAVE` (Desktop Window Detection)
  4. **Test D**: `LIST MY OPEN BROWSER TABS` (Structured Tab Inventory)
  5. **Test E**: `OPEN GMAIL IN MY BROWSER` (Browser Navigation $\rightarrow$ Tab Presence Verification)
  6. **Test F**: `SWITCH TO MY GMAIL TAB` (Semantic Resolution $\rightarrow$ Active Tab Switch)
  7. **Test G**: `CLOSE THE GMAIL TAB` (Zero-Coordinate UIA Close $\rightarrow$ Tab Absence Verification)
  8. **Test H**: `CLOSE THE NONEXISTENT_TAB_XYZ TAB` (Missing Target $\rightarrow$ `TARGET_NOT_FOUND` Refusal, 0 clicks)
  9. **Test I**: Ambiguous Target Guard (Refusal on Ambiguous Titles, 0 clicks)
