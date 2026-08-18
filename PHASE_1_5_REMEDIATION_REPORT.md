# PLUTON V2 — PHASE 1.5 REMEDIATION & REGRESSION REPORT

**Date**: August 16, 2026  
**Auditor / Engineer**: Antigravity AI Systems Engineer  
**Status**: All Verified Blocking Findings Remediated & Validated  

---

## 1. Summary of Remediated Findings

| Finding ID | Finding Description | Severity | Remediated Status |
|---|---|---|---|
| **F-01** | Unrestricted Terminal Command Execution | `CRITICAL` | **FIXED** |
| **F-02** | Unrestricted Filesystem Path Traversal & Escapes | `HIGH` | **FIXED** |
| **F-03** | Legacy Tool Bypass in LLM Tool Execution | `HIGH` | **FIXED** |
| **F-04** | Target Resolver Blindly Trusting Non-Existent/Stale HWNDs | `MEDIUM` | **FIXED** |
| **F-05** | Kernel Token Preemption Inconsistency | `MEDIUM` | **FIXED** |
| **F-06** | Filesystem Verification Depth (Content & Min Size) | `MEDIUM` | **FIXED** |

---

## 2. Detailed Remediation Breakdown

### Finding F-01: Terminal Execution Security Boundary (CRITICAL)
* **What was wrong**: `terminal.execute` ran commands directly via `subprocess.run(shell=True)` with no risk classification or policy boundaries.
* **Root cause**: Lack of a security classifier and policy gate prior to shell process spawning.
* **Fix implemented**:
  1. Created `TerminalSecurityPolicy` with extensible risk classification (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  2. Implemented regex AST pattern matching blocking disk destruction (`format`, `diskpart`, `mkfs`, `del /f /s /q C:\*`, `rmdir /s /q C:\*`), obfuscated PowerShell payloads (`-encodedcommand`, `[Convert]::FromBase64String`, `iex(New-Object...)`), registry tampering (`reg delete HKLM`), and fork bombs.
  3. Enforced policy gate: `CRITICAL` is unconditionally denied (`POLICY_DENIED`); `HIGH` requires explicit authorization (`REQUIRES_APPROVAL`).
  4. Added canonical working directory (`cwd`) validation.
* **Files changed**: [`backend/app/subsystems/computer/domains/terminal.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/subsystems/computer/domains/terminal.py)
* **Tests added**: `test_terminal_risk_classifier`, `test_terminal_blocks_critical_commands`, `test_terminal_high_risk_requires_approval` in [`backend/tests/test_phase1_5_remediation.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/tests/test_phase1_5_remediation.py).
* **Final Status**: **FIXED**

---

### Finding F-02: Filesystem Workspace Path Boundaries (HIGH)
* **What was wrong**: `filesystem.read`, `write`, `move`, and `delete` allowed operating on arbitrary system paths (e.g. `C:\Windows\System32\...`) or escaping via `..` traversal.
* **Root cause**: Absence of canonical path containment checks against approved workspace roots.
* **Fix implemented**:
  1. Implemented `FilesystemSecurityPolicy` with configurable approved roots (project root, system temp).
  2. Implemented `validate_path()` resolving canonical paths (`Path(path).resolve()`) and ensuring containment via `root in resolved.parents` or `resolved.is_relative_to(root)`.
  3. Added explicit policy protection preventing direct deletion of approved root directories.
* **Files changed**: [`backend/app/subsystems/computer/domains/filesystem.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/subsystems/computer/domains/filesystem.py)
* **Tests added**: `test_filesystem_policy_path_boundaries`, `test_filesystem_domain_blocks_outside_workspace_write` in [`backend/tests/test_phase1_5_remediation.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/tests/test_phase1_5_remediation.py).
* **Final Status**: **FIXED**

---

### Finding F-03: Legacy Computer Tool Bypasses (HIGH)
* **What was wrong**: Legacy helper functions in `backend/app/tools/computer.py` invoked direct Win32/pyautogui execution rather than delegating into `COMPUTER_ENGINE`.
* **Root cause**: Legacy tools remained standalone implementations rather than pure thin compatibility wrappers.
* **Fix implemented**:
  1. Routed legacy mouse, keyboard, app launch, window control, and browser tab actions to `COMPUTER_ENGINE` domains (`COMPUTER_ENGINE.mouse.*`, `COMPUTER_ENGINE.keyboard.*`, `COMPUTER_ENGINE.app.*`, `COMPUTER_ENGINE.window.*`, `COMPUTER_ENGINE.browser.*`).
* **Files changed**: [`backend/app/tools/computer.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/tools/computer.py)
* **Final Status**: **FIXED**

---

### Finding F-04: Target Resolver Stale HWND Handling (MEDIUM)
* **What was wrong**: Providing an explicit integer HWND in `TargetSpec` returned `RESOLVED` even if the HWND did not exist or was destroyed.
* **Root cause**: `TargetResolver._resolve_window` returned early on `spec.hwnd` without calling `user32.IsWindow()`.
* **Fix implemented**:
  1. Added `ctypes.windll.user32.IsWindow(spec.hwnd)` check. If false, returns `TARGET_NOT_FOUND`.
  2. If `spec.pid` is also supplied, verifies `GetWindowThreadProcessId(spec.hwnd) == spec.pid`.
* **Files changed**: [`backend/app/subsystems/computer/target_resolver.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/subsystems/computer/target_resolver.py)
* **Tests added**: `test_target_resolver_rejects_fake_hwnd` in [`backend/tests/test_phase1_5_remediation.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/tests/test_phase1_5_remediation.py).
* **Final Status**: **FIXED**

---

### Finding F-05: Kernel Token Preemption Consistency (MEDIUM)
* **What was wrong**: Preempting Task A with Task B updated `_active_task_id`, but `token_a.revoked` remained `False`.
* **Root cause**: `ComputerControlKernel.authorize_task` replaced `self._active_token` without explicitly mutating `self._active_token.revoked = True`.
* **Fix implemented**:
  1. Updated `authorize_task` to explicitly call `self._active_token.revoked = True` before creating the new token.
* **Files changed**: [`backend/app/kernel/control_kernel.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/kernel/control_kernel.py)
* **Tests added**: `test_kernel_token_preemption_explicit_revocation` in [`backend/tests/test_phase1_5_remediation.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/tests/test_phase1_5_remediation.py).
* **Final Status**: **FIXED**

---

### Finding F-06: Filesystem Verification Depth (MEDIUM)
* **What was wrong**: `FILESYSTEM_CHECK` only checked whether `p.exists() == expected_exists`.
* **Root cause**: Verification did not inspect byte size or written content metadata.
* **Fix implemented**:
  1. Updated `VerificationEngine.verify_action` for `FILESYSTEM_CHECK` to support `expected_min_bytes` and `expected_content` readback checks.
* **Files changed**: [`backend/app/verification/verification_engine.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/app/verification/verification_engine.py)
* **Tests added**: `test_filesystem_verification_content_and_size` in [`backend/tests/test_phase1_5_remediation.py`](file:///c:/Users/MOHD%20SUHAIB/Downloads/PLUTON-UPDATED/backend/tests/test_phase1_5_remediation.py).
* **Final Status**: **FIXED**

---

## 3. Test Suite Validation Results

| Test Category | Suite | Passed / Total | Result |
|---|---|---|---|
| **Phase 1.5 Remediation** | `test_phase1_5_remediation.py` | **8 / 8** | **PASS** |
| **Core Subsystem Suites** | `test_v2_*.py` + `test_phase1_5_remediation.py` | **35 / 35** | **PASS** |
| **Full Backend Regression** | `pytest backend/tests/ -q` | **340 / 340** | **PASS (100%)** |
| **Frontend Vitest Suite** | `npx vitest run` | **11 / 11** | **PASS (100%)** |
| **Real Desktop Acceptance** | `run_v2_phase1_desktop_acceptance.py` | **6 / 6 Flows** | **PASS (100%)** |
| **Adversarial Probe** | `audit_adversarial_probe.py` | **All Probes Passed** | **PASS** |

---

## 4. Final Gate & Readiness Verdict

### Security Status:
**PASS**

### Architecture Status:
**PASS**

### Regression Status:
**PASS**

### Phase 1.5 Status:
**PASS**

### Phase 2 Ready?
**YES**
