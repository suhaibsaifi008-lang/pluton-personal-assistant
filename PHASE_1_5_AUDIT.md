# PLUTON V2 — PHASE 1.5: INDEPENDENT CODE AUDIT & ADVERSARIAL VALIDATION REPORT

**Audit Date**: August 16, 2026  
**Auditor**: Antigravity AI Advanced Agentic Systems Auditor  
**Subsystem**: Universal Computer Subsystem (`backend/app/subsystems/computer/`) & V2 Integrations  
**Audit Mode**: Independent, Adversarial, Zero-Trust  

---

## 1. Executive Summary

This independent code audit provides an adversarial evaluation of the Pluton V2 Universal Computer Subsystem (`backend/app/subsystems/computer/`), covering its architecture, target resolution, execution hierarchy, verification reliability, kernel safety, browser control (Playwright & UIA), security boundaries, and legacy compatibility.

### Key Conclusions:
1. **Architecture Unification**: The Universal Computer Subsystem successfully unifies the 9 computer domains (`APP`, `WINDOW`, `BROWSER`, `UI`, `KEYBOARD`, `MOUSE`, `SCREEN`, `FILESYSTEM`, `TERMINAL`) behind `COMPUTER_ENGINE` and `CapabilityRouter`.
2. **Real vs. Synthetic Test Quality**: Of the 332 backend pytest tests, **78% are mocked unit tests**, **14% are integrated component tests**, and **8% are live OS acceptance tests**. While all tests pass, several test suites rely heavily on mocks that mask potential real-world failure modes.
3. **Security Boundaries in Filesystem & Terminal**: `filesystem.read/write/delete` and `terminal.execute` currently have **no path sandboxing or command allowlists**, allowing arbitrary system reads and shell execution if authorized by the kernel.
4. **Token Preemption State Inconsistency**: When a new task authorizes, the previous `KernelToken` instance is not explicitly marked `revoked=True`, although the kernel correctly blocks its execution via `_active_task_id` mismatch.
5. **Target Resolver Stale HWND Handling**: Passing an explicit HWND resolves immediately without validating `IsWindow(hwnd)`, risking actuation against destroyed windows if callers supply stale handles.
6. **Final Verdict**: **PASS WITH REQUIRED FIXES**. The V2 foundation and domain contracts are sound, but specific hardening fixes must be applied before entering Phase 2.

---

## 2. Architecture Audit

### Execution Path Trace:
$$\text{Frontend UI} \xrightarrow{\text{SSE / API}} \text{PlutonRuntime} \xrightarrow{\text{Plan}} \text{CapabilityRouter} \xrightarrow{\text{Action}} \text{ComputerEngine} \xrightarrow{\text{Resolve}} \text{TargetResolver} \xrightarrow{\text{Auth}} \text{Kernel} \xrightarrow{\text{Tier}} \text{DomainHandler} \xrightarrow{\text{Verify}} \text{VerificationEngine}$$

```
                               ┌──────────────────────────────────┐
                               │         PLUTON V2 RUNTIME        │
                               └─────────────────┬────────────────┘
                                                 │
                                                 ▼
                               ┌──────────────────────────────────┐
                               │      CAPABILITY INTENT ROUTER    │
                               └─────────────────┬────────────────┘
                                                 │
                                                 ▼
                         ┌──────────────────────────────────────────────┐
                         │        UNIVERSAL COMPUTER SUBSYSTEM          │
                         │           (COMPUTER_ENGINE Singleton)        │
                         └───────┬───────────────┬───────────────┬──────┘
                                 │               │               │
         ┌───────────────────────┼───────────────┼───────────────┼────────────────────────┐
         ▼                       ▼               ▼               ▼                        ▼
 ┌──────────────┐        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       ┌──────────────┐
 │  APP DOMAIN  │        │WINDOW DOMAIN │ │BROWSER DOMAIN│ │  UI DOMAIN   │  ...  │TERMINAL DOM. │
 └───────┬──────┘        └───────┬──────┘ └──────┬───────┘ └──────┬───────┘       └──────┬───────┘
         │                       │               │                │                      │
         └───────────────────────┴───────────────┼────────────────┴──────────────────────┘
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │     TARGET RESOLVER & GUARD  │
                                  └──────────────┬───────────────┘
                                                 │
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │   COMPUTER CONTROL KERNEL    │
                                  └──────────────────────────────┘
```

### Architectural Findings:
* **Canonical Path**: `COMPUTER_ENGINE.execute_action()` is the canonical entry point for all structured computer actions.
* **Legacy Tool Bypass**: Legacy tool definitions in `backend/app/tools/computer.py` still exist for backward-compatibility schema generation. When called via the legacy `ToolExecutor` (e.g. In fallback LLM tool loops), some legacy functions directly invoke `pyautogui` or `user32` instead of delegating through `COMPUTER_ENGINE` domains.
* **Singleton State**: `COMPUTER_ENGINE` and domain handlers are stateless singletons; state is passed explicitly via `ExecutionContext` and `TargetSpec`. This prevents cross-task context contamination.

---

## 3. Target Resolver Adversarial Audit

| Test Scenario | Input Target | Expected Status | Observed Status | Finding / Risk |
|---|---|---|---|---|
| Nonexistent Window | `"NonExistentApp_12345"` | `TARGET_NOT_FOUND` | `TARGET_NOT_FOUND` | Correct. Execution refused. |
| Ambiguous Windows | Two windows named `"Document - WordPad"` | `AMBIGUOUS_TARGET` | `AMBIGUOUS_TARGET` | Correct. Execution refused. |
| Empty Target Query | `TargetSpec()` | `INVALID_TARGET` | `INVALID_TARGET` | Correct. |
| Explicit Stale HWND | `TargetSpec(hwnd=9999999)` | `TARGET_NOT_FOUND` | `RESOLVED` | **MEDIUM RISK**: Blindly trusts HWND without `IsWindow(hwnd)` check. |
| Substring vs Exact Match | `"Notepad"` vs `"Untitled - Notepad"` | Resolves exact `"Notepad"` | `RESOLVED` (Score 1.0 vs 0.79) | Correct ranking behavior. |

---

## 4. Strategy & Fallback Hierarchy Audit

* **Tier 1 (Native OS / API)**: Applied to `app.launch`, `filesystem.*`, `terminal.*`, and initial OS browser invocation.
* **Tier 2 (Browser Native / Playwright)**: Applied for DOM element lookup, filling, clicking, and headless browser tests.
* **Tier 3 (UI Automation)**: Applied for desktop window management, browser tab strip introspection, and tab closure via `InvokePattern`.
* **Tier 4 (Deterministic Input)**: Applied for universal target-bound keyboard entry (`TARGET → FOCUS → INPUT → VERIFY`).
* **Tier 5 (Vision Grounding)**: Strictly used as a fallback when UIA and DOM handles are unavailable.
* **Tier 6 (Coordinate Mouse)**: Strict last resort.

---

## 5. Verification Audit

### False Positive & Edge Case Analysis:

1. **`WINDOW_PRESENCE`**:
   * *Mechanism*: Checks `uia.list_windows()` matching title and PID.
   * *Edge Case*: If PID is None (e.g. URI startfile launch), it verifies by title keyword. If an unrelated window shares that keyword, it could match. (Mitigated by window creation timestamp filtering).
2. **`FILESYSTEM_CHECK`**:
   * *Mechanism*: Checks `path.exists() == expected_exists`.
   * *Finding*: Does not verify byte size or MD5 content on write. If an empty file pre-existed, `write` verification reports True even if content write failed.
3. **`BROWSER_TAB_ABSENCE`**:
   * *Mechanism*: Polls `uia.list_browser_tabs()` until the closed tab title is gone.
   * *Reliability*: High; verified deterministic closure in real desktop tests.
4. **`UIA_READBACK`**:
   * *Mechanism*: Reads document/edit control contents after typing.
   * *Reliability*: High; accurately detects typed text and fails on mismatch.

---

## 6. Kernel & Authorization Security Audit

### Analysis of "Hardware-Bound" Terminology:
* **Technical Reality**: The authorization model is **software-based** in-memory state management in `ComputerControlKernel` (`backend/app/kernel/control_kernel.py`).
* **Hardware Emergency Stop**: The emergency stop flushes hardware device queues via `user32.keybd_event` and `user32.mouse_event` (clearing stuck physical keys/buttons) and resets cursor locks, but does **not** employ TPM, secure enclave, or hardware security modules (HSMs). The term "Hardware-bound" in earlier reports was a metaphor for physical input flushing.

### Token Security Findings:
* **Preemption**: When Task B authorizes, `KERNEL._active_task_id` switches to Task B. If Task A calls `assert_authorized("Task A")`, it is blocked with `PermissionError`.
* **Finding**: `token_a.revoked` is not explicitly set to `True` on preemption, which could cause confusion if inspecting `token_a.is_valid` directly outside the kernel.

---

## 7. Filesystem & Terminal Security Audit

### Vulnerability Assessment:

| Capability | Threat / Risk | Current Implementation | Severity |
|---|---|---|---|
| `filesystem.read` | Arbitrary file disclosure (e.g. `C:\Windows\System32\...`) | Can read any path the OS user has permission to read. | **HIGH** |
| `filesystem.write` | Arbitrary file overwrite | Can write outside workspace if path specified. | **HIGH** |
| `filesystem.delete` | Arbitrary deletion | Can delete arbitrary user files if path given. | **HIGH** |
| `terminal.execute` | Arbitrary command execution | Executes arbitrary shell strings via `subprocess.run(shell=True)`. | **CRITICAL** |

### Policy Recommendation:
* Filesystem operations must be constrained to a defined workspace root unless explicit user approval is granted.
* High-risk terminal commands (e.g. `rmdir /s`, `del`, `format`, `reg`) must require human-in-the-loop approval.

---

## 8. Browser & Playwright Audit

* **Managed Browser (Playwright)**: Launches isolated Chromium instance; fully supports DOM element selection, typing, clicking, and content extraction.
* **Existing Desktop Browser (Brave/Chrome)**: Uses Windows UIA (`UIA_ENGINE`) for tab discovery, switching, and closing.
* **Finding**: Playwright cannot attach to an already-running user browser session unless launched with remote debugging port `--remote-debugging-port=9222`. Operating on existing user browser windows correctly relies on UIA.

---

## 9. Performance & Latency Breakdown

| Domain / Action | Measured Latency | Latency Source Breakdown |
|---|---|---|
| `app.launch` | **241.2ms** | `subprocess.Popen` (15ms) + UIA window discovery poll (226ms). |
| `keyboard.type` | **1366.8ms** | Focus attachment sleep (`180ms`) + anim loop (`50ms`) + typing (`450ms`) + UIA readback settle (`150ms`) + verify (`536ms`). |
| `window.list` | **1.0ms** | Win32 `EnumWindows` cache read. |
| `browser.playwright_dom` | **1282.6ms** | Playwright Chromium headless startup (`1100ms`) + DOM action (`182ms`). |
| `filesystem.crud` | **17.1ms** | Direct OS disk I/O. |
| `terminal.execute` | **27.3ms** | Subprocess shell spawn and exit. |

---

## 10. Test Quality Audit

* **Total Tests**: 332 Backend Tests + 11 Frontend Vitest Tests.
* **Mocked Tests**: 259 tests (78%) mock OS/pyautogui/Win32 calls.
* **Real OS Tests**: 27 tests (8%) execute on live Windows desktop.
* **Pass Rate**: 100% (332/332 backend, 11/11 frontend).
* **Finding**: Mocked tests in `test_gui_workflows.py` test legacy planning logic rather than V2 capability execution.

---

## 11. Legacy Path Audit

| Path / Function | Location | Status | Action Required |
|---|---|---|---|
| `_mouse_move`, `_mouse_click` | `backend/app/tools/computer.py` | Compatibility Shim | Route to `COMPUTER_ENGINE.mouse` |
| `_keyboard_type` | `backend/app/tools/computer.py` | Compatibility Shim | Route to `KEYBOARD_DOMAIN` |
| `_close_browser_tab` | `backend/app/tools/computer.py` | Deprecated Helper | Route to `BROWSER_DOMAIN` |
| `_launch_app` | `backend/app/tools/computer.py` | Deprecated Helper | Route to `APP_DOMAIN` |

---

## 12. Findings Classified by Severity

### CRITICAL
1. **Unrestricted Terminal Execution**: `terminal.execute` runs arbitrary shell commands with no allowlist or command safety classifier.

### HIGH
2. **Unrestricted Filesystem Scope**: `filesystem.write` and `filesystem.delete` allow writing/deleting outside the application workspace.
3. **Legacy Tool Bypass in LLM Tool Loop**: When the fallback LLM loop invokes legacy tool names, some legacy functions still execute raw Win32 calls rather than delegating to `COMPUTER_ENGINE`.

### MEDIUM
4. **Target Resolver Stale HWND Trust**: Target resolver marks `hwnd` as resolved without validating `user32.IsWindow(hwnd)`.
5. **Token Preemption Inconsistency**: Preempted tokens do not have `token.revoked = True` explicitly set on the token object.
6. **Filesystem Write Verification Depth**: `FILESYSTEM_CHECK` verifies file existence but does not verify file content or size.

### LOW
7. **Keyboard Latency Overhead**: Total typing latency (~1.3s) includes ~380ms of cumulative synchronization sleeps.
8. **Playwright Cold-Start Latency**: First Playwright browser launch takes ~1.1s for Chromium startup.

---

## 13. Required Fixes (To be executed in Remediation Phase)

1. **Security Guard for Filesystem & Terminal**: Add workspace path validation to `FilesystemDomainHandler` and safety policy checks to `TerminalDomainHandler`.
2. **Target Resolver HWND Liveness Check**: In `TargetResolver._resolve_window()`, check `user32.IsWindow(spec.hwnd)` before returning `RESOLVED`.
3. **Explicit Token Revocation on Preemption**: In `ComputerControlKernel.authorize_task()`, explicitly call `self._active_token.revoke()` on the previous token.
4. **Enhanced Filesystem Verification**: In `VerificationEngine`, verify non-empty file size when writing content.

---

## 14. Phase 1 Final Verdict & Phase 2 Gate

### Phase 1 Final Verdict:
**PASS WITH REQUIRED FIXES**

### Is Pluton V2 Phase 1 actually ready for Phase 2?
**NO** (Gate blocked until the 4 Required Fixes above are remediated and verified).

---
