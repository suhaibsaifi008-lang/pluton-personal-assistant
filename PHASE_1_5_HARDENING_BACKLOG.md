# PLUTON V2 — PHASE 1.5 HARDENING BACKLOG

**Status**: Non-Blocking Engineering Items (Post-Phase 1 Freeze)  
**Target Window**: Phase 3 / Platform Hardening Milestone  

---

## Overview

The Pluton V2 Universal Computer Subsystem is frozen as the canonical computer execution substrate. The following items are documented as engineering hardening enhancements that do not block Phase 2 (Agent Intelligence & Closed-Loop Planning Layer).

---

### H-01 — Terminal Process Isolation & Sandboxing
* **Current Implementation**: Subprocess shell execution with structured `TerminalSecurityPolicy` risk classification, AST regex pattern denial, and approval gates.
* **Target Hardening**: Evaluate running arbitrary/untrusted shell executions within an isolated worker process or container boundary (e.g. Windows AppContainer, lightweight Windows Sandbox / Docker worker) to achieve OS-level process virtualization.
* **Priority**: Medium / Platform Hardening.

---

### H-02 — Filesystem TOCTOU (Time-of-Check to Time-of-Use) Protection
* **Current Implementation**: Canonical path resolution and boundary containment validation prior to disk mutation.
* **Target Hardening**: Evaluate race conditions between path validation and filesystem write/delete operations in high-concurrency environments using OS file handles / atomic directory operations (`os.O_NOFOLLOW` / `FILE_FLAG_OPEN_REPARSE_POINT`).
* **Priority**: Low / Concurrency Milestone.

---

### H-03 — Windows Reparse Point & Junction Safety
* **Current Implementation**: Resolved paths check `is_relative_to` / parent chain against approved workspace roots.
* **Target Hardening**: Add dedicated regression suites for Windows NTFS directory junctions, symbolic links, and volume mount points to ensure resolved target paths never escape approved roots via symlink pivoting.
* **Priority**: Low / Security Hardening.

---

### H-04 — High-Concurrency Stress Testing
* **Current Implementation**: Single-task preemption and mutual exclusion via `ComputerControlKernel` lock.
* **Target Hardening**: Add high-throughput stress tests simulating:
  - Rapid task queueing and cancellation under load.
  - Multi-threaded background tasks attempting preemption.
  - Simultaneous Playwright headless contexts and UIA inspection pipelines.
* **Priority**: Medium / Scalability Milestone.

---

### H-05 — Dynamic Recovery & Crash Invariants
* **Current Implementation**: Direct exception capture and verification timeout reporting.
* **Target Hardening**: Expand the runtime to gracefully recover and enter a stable state if:
  - Target application crashes mid-actuation (e.g. `STATUS_ACCESS_VIOLATION`).
  - Browser process terminates unexpectedly while a DOM handle is open.
  - Verification times out due to OS desktop lock (`Winlogon` / `UAC` secure desktop).
* **Priority**: Integrated directly into Phase 2 Recovery Engine.

---

### H-06 — Multi-Browser Real Desktop Acceptance
* **Current Implementation**: Verified live desktop tests for Notepad, Brave UIA tab control, and headless Playwright Chromium.
* **Target Hardening**: Expand the live desktop test matrix to include:
  - Multi-window browser configurations (e.g. 3 Brave windows with 20 tabs across different profiles).
  - Existing user login sessions with 2FA / SSO prompts.
  - Dynamic SPAs with heavy shadow DOM and WebGL components.
  - Browser crash and session restore scenarios.
* **Priority**: Low / End-to-End QA.

---

### H-07 — Multi-Monitor & Mixed DPI Desktop Targeting
* **Current Implementation**: Primary monitor metrics and standard DPI awareness.
* **Target Hardening**: Test and validate coordinate translation and window placement across:
  - Mixed-DPI multi-monitor setups (e.g. 4K primary at 150% scaling, 1080p secondary at 100% scaling).
  - Minimized / snapped / virtual desktop window placements (`IVirtualDesktopManager`).
* **Priority**: Low / Desktop UX.
