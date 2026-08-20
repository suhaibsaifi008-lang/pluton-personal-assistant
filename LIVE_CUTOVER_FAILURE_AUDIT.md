# PLUTON V2 — LIVE CUTOVER & FAILURE INVESTIGATION AUDIT

**Date**: August 16, 2026  
**Auditor / Systems Engineer**: Antigravity AI Systems Engineer  
**Scope**: Live User Workflow Failure: `OPEN GMAIL TAB IN MY BROWSER`  
**Status**: Root Cause Identified & Independently Verified across Tests A–E  

---

## 1. Reproduction

* **Exact User Request**: `OPEN GMAIL TAB IN MY BROWSER`
* **Observed UI Behavior**: 
  - The UI showed initial messages and tool activity.
  - The interaction abruptly terminated with: `BodyStreamBuffer was aborted`.
  - Assistant message rendered: `BodyStreamBuffer was aborted`.
  - The desktop browser state was ambiguous (URL opened via unverified OS shell handler).

---

## 2. Complete Execution Trace

```
Frontend (User Types "OPEN GMAIL TAB IN MY BROWSER")
 ↓
fetch('/api/chat', { signal: controller.signal }) [api.ts:41]
 ↓
main.py: async def chat() -> StreamingResponse(_stream_response) [main.py:134]
 ↓
PlutonRuntime.execute_task(task_id) [runtime.py:100]
 ↓
CapabilityRouter.plan_request("OPEN GMAIL TAB IN MY BROWSER") [capability_router.py:132]
 ↓ (Regex failed on trailing words "tab in my browser" -> GENERAL_ACTION)
PlutonRuntime._run_llm_loop [runtime.py:342]
 ↓ (Exposes 33 flat, uncoordinated ToolRegistry definitions to LLM)
LLM Provider: Model selects 'computer.list_browser_tabs' then 'browser.open_url'
 ↓
ToolExecutor.execute_call("browser.open_url", {"url": "https://mail.google.com"}) [tool_executor.py:80]
 ↓
tools/browser.py: _browser_open_url -> webbrowser.open("https://mail.google.com") [browser.py:24]
 ↓ (Python OS shell wrapper executes, completely bypassing COMPUTER_ENGINE.browser)
LLM continues multi-turn reasoning / tool loops (screenshots, UIA retries)
 ↓ (Duration exceeds client timeout or connection closes prematurely)
Frontend: AbortController fires OR SSE connection drops
 ↓
ReadableStreamDefaultReader.read() throws DOMException: BodyStreamBuffer was aborted [api.ts:62]
 ↓
App.tsx catches error and renders: "BodyStreamBuffer was aborted" [App.tsx:180]
```

---

## 3. First Point of Divergence

The first point where execution diverged from the canonical V2 architecture occurred at **`CapabilityRouter._parse_single_action` (`capability_router.py:178`)**:
1. The regex pattern for browser navigation strictly expected single-word destinations:
   `^(?:navigate\s+to|go\s+to|open|visit)\s+(https?://\S+|[a-z0-9\-_.]+\.[a-z]{2,}(?:/\S*)?|[a-z0-9\-_]+)$`
2. Because the user input contained `"gmail tab in my browser"`, the regex failed to extract the destination (`gmail`).
3. The request fell through to `GENERAL_ACTION` (Tier 5 Vision), triggering the multi-turn LLM reasoning fallback loop instead of the canonical V2 capability execution pipeline.

---

## 4. Root Cause Analysis

Three distinct compounding defects caused this failure:

### Root Cause 1: Tool Registry Definition Pollution & Dual-Path Legacy Shadowing (HIGH)
* **File**: [`backend/app/tools/registry.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/tools/registry.py), [`backend/app/tools/browser.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/tools/browser.py)
* **Mechanism**: When falling back to LLM tool dispatch, the LLM is supplied with **33 flat, uncoordinated legacy tools** (`browser.open_url`, `app.launch`, `computer.list_browser_tabs`, `computer.screenshot`, etc.).
* `browser.open_url` in `tools/browser.py` invokes Python's standard `webbrowser.open()`. It does **not** route through `COMPUTER_ENGINE.browser`, does not capture PID/HWND, does not use Playwright/UIA, and performs zero postcondition verification.

### Root Cause 2: Frontend Stream Abort on Extended Multi-Turn LLM Loops (HIGH)
* **File**: [`frontend/src/api.ts`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/frontend/src/api.ts), [`frontend/src/App.tsx`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/frontend/src/App.tsx)
* **Mechanism**: In `api.ts:34`, `setTimeout(() => controller.abort(), 90000)` aborts the fetch after 90 seconds. When the LLM enters an unguided multi-turn loop (e.g. taking screenshots, inspecting vision, switching tabs), the stream duration exceeds the threshold or drops. When `reader.read()` is aborted, Blink/WebKit throws `BodyStreamBuffer was aborted`. `App.tsx` renders this raw runtime error directly to the user.

### Root Cause 3: Intent Parser Brittleness for Natural Browser Phrasing (MEDIUM)
* **File**: [`backend/app/capabilities/capability_router.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/capabilities/capability_router.py)
* **Mechanism**: `_parse_single_action` failed to recognize conversational variations such as `"open gmail in my browser"`, `"open gmail tab"`, or `"open a new tab and open gmail"`, forcing deterministic requests into ambiguous LLM fallbacks.

---

## 5. Investigation of `BodyStreamBuffer was aborted`

* **Exact Origin**: Browser Fetch API (`ReadableStreamDefaultReader.read()` in `frontend/src/api.ts:62`).
* **Trigger Mechanism**:
  1. Frontend `AbortController` aborted the request due to a timeout or user navigation.
  2. The server-side SSE HTTP stream closed abruptly when an unhandled exception occurred or connection reset during an extended LLM turn.
  3. In both cases, reading from an aborted `ReadableStream` produces the exact browser exception `TypeError: BodyStreamBuffer was aborted`.

---

## 6. Capability Discovery & Tool Audit Table

| Tool Name | Source File | Canonical V2? | Legacy? | Execution Path |
|---|---|---|---|---|
| `browser.open_url` | `app/tools/browser.py` | ❌ No | ✅ Yes | `webbrowser.open()` (OS Shell) |
| `app.launch` | `app/tools/browser.py` | ❌ No | ✅ Yes | `subprocess.Popen` / `os.startfile` |
| `computer.list_browser_tabs` | `app/tools/computer.py` | ❌ No | ✅ Yes | Direct UIA / `UIA_ENGINE` |
| `computer.switch_browser_tab`| `app/tools/computer.py` | ❌ No | ✅ Yes | Direct UIA / `UIA_ENGINE` |
| `computer.close_browser_tab` | `app/tools/computer.py` | ❌ No | ✅ Yes | Direct UIA / Vision fallback |
| `computer.screenshot` | `app/tools/computer.py` | ❌ No | ✅ Yes | `ctypes.windll.gdi32` |
| `computer.inspect_screen` | `app/tools/computer.py` | ❌ No | ✅ Yes | Vision Provider API |
| `computer.mouse_click` | `app/tools/computer.py` | ❌ No | ✅ Yes | `COMPUTER_ENGINE.mouse.click` |
| `computer.keyboard_type` | `app/tools/computer.py` | ❌ No | ✅ Yes | `COMPUTER_ENGINE.keyboard.type` |
| `browser.navigate` | `app/subsystems/computer/` | ✅ **Yes** | ❌ No | `COMPUTER_ENGINE.browser.navigate` |
| `browser.list_tabs` | `app/subsystems/computer/` | ✅ **Yes** | ❌ No | `COMPUTER_ENGINE.browser.list_tabs` |
| `window.focus` | `app/subsystems/computer/` | ✅ **Yes** | ❌ No | `COMPUTER_ENGINE.window.focus` |

---

## 7. Real Browser Workflow Test Matrix (Tests A–E)

| Test | Request Prompt | Router Decision | Actual Tool Executed | Browser Instance | Verification | User Result |
|---|---|---|---|---|---|---|
| **Test A** | `OPEN GMAIL IN MY BROWSER` | `GENERAL_ACTION` | `browser.open_url` | Default OS Browser | None | Completed |
| **Test B** | `OPEN A NEW TAB AND OPEN GMAIL` | `GENERAL_ACTION` | `browser.open_url` | Default OS Browser | None | Completed |
| **Test C** | `LIST MY OPEN BROWSER TABS` | `GENERAL_ACTION` | `computer.list_browser_tabs` | Brave UIA | UIA Count | Completed (0 tabs) |
| **Test D** | `SWITCH TO MY EXISTING GMAIL TAB` | `GENERAL_ACTION` | 14-turn loop (UIA, Screenshot, Vision, `browser.open_url`) | Brave UIA | UIA tree check failed | Failed / Fallback response |
| **Test E** | `OPEN GOOGLE IN MY BROWSER` | `GENERAL_ACTION` | `browser.open_url` | Default OS Browser | None | Completed |

---

## 8. Existing Browser Control vs New Browser Instance

* **New / Default Browser**: Handled via `browser.open_url` calling OS shell `webbrowser.open()`. It opens a new tab in the running browser or starts a new instance, but Pluton has zero handle or verification over it.
* **Existing Browser (UIA Inspection)**: `UIA_ENGINE.list_browser_tabs` searches for top-level windows named `Brave`, `Chrome`, or `Edge`. If the browser is minimized, off-screen, or uses custom tab strips without accessibility trees, UIA returns 0 tabs, causing the LLM to get trapped in an open-ended screenshot/vision loop.

---

## 9. Cancellation & Abort Safety

* **Backend Behavior on Client Disconnect**:
  - `PlutonRuntime.execute_task` catches `asyncio.CancelledError` and `GeneratorExit` (`runtime.py:234`).
  - Calls `KERNEL.emergency_stop()`.
  - Sets `task.status = CANCELLED`.
  - Cancels execution cleanly without leaking orphan keyboard/mouse held keys.
* **Stream Exception Handling in Frontend**:
  - When the fetch aborts, `api.ts` lets `BodyStreamBuffer was aborted` escape into `App.tsx`, which writes the raw exception text to the chat UI.

---

## 10. Summary of Severity & Recommended Fixes

| Issue ID | Description | Severity | Recommended Fix |
|---|---|---|---|
| **I-01** | Tool Registry exposes 33 uncoordinated legacy tools to LLM instead of canonical V2 capabilities. | `HIGH` | Expose only canonical V2 capability tools to the LLM that delegate exclusively through `COMPUTER_ENGINE`. |
| **I-02** | `browser.open_url` bypasses `COMPUTER_ENGINE.browser` and `VerificationEngine`. | `HIGH` | Route all browser navigation through `COMPUTER_ENGINE.browser.navigate` with Playwright/UIA integration and deterministic verification. |
| **I-03** | `CapabilityRouter._parse_single_action` regex does not match natural conversational browser requests. | `MEDIUM` | Expand intent parser regexes to recognize `"open <site> in my browser"`, `"open <site> tab"`, and compound new tab requests. |
| **I-04** | Raw `BodyStreamBuffer was aborted` string displayed in chat UI on stream abort. | `LOW` | Catch `AbortError` / stream disconnects in `api.ts` and `App.tsx` to display a clean user-friendly notification. |

---

## 11. Final Status & Decisions

* **Phase 1 Subsystem Status**: **`STILL VALID`** (`COMPUTER_ENGINE` primitives and domains are sound; the defect is in capability exposure, router regex matching, and legacy tool registry shadowing).
* **Phase 2 Status**: **`BLOCKED`** (Remains blocked until capability discovery, router matching, and end-to-end browser workflows are cleanly remediated and verified live).
