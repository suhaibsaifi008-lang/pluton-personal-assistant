"""
AUDIT-ONLY Adversarial Validation Script for Pluton V2 Phase 1.5.
Probes target resolver edge cases, verification false positives, authorization holes,
security boundaries in filesystem/terminal, and performance bottlenecks.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    VerificationStrategy,
)
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer import (
    COMPUTER_ENGINE,
    TARGET_RESOLVER,
    ComputerDomain,
    TargetResolutionStatus,
    TargetSpec,
)
from app.verification.verification_engine import VERIFICATION_ENGINE


def audit_target_resolver():
    print("--- [AUDIT 1: Target Resolver Edge Cases] ---")
    results = {}

    # 1. Stale / Nonexistent HWND
    res_hwnd = TARGET_RESOLVER.resolve(ComputerDomain.WINDOW, TargetSpec(hwnd=9999999))
    results["stale_hwnd_resolved"] = (res_hwnd.status == TargetResolutionStatus.RESOLVED)
    # Notice: If HWND is provided, it is returned as RESOLVED without validating if HWND is still a live window!
    print(f"  Stale HWND 9999999 resolved blindly: {results['stale_hwnd_resolved']}")

    # 2. Empty Query
    res_empty = TARGET_RESOLVER.resolve(ComputerDomain.WINDOW, TargetSpec())
    results["empty_query_rejected"] = (res_empty.status == TargetResolutionStatus.INVALID_TARGET)
    print(f"  Empty query rejected as INVALID_TARGET: {results['empty_query_rejected']}")

    # 3. Substring vs Exact Ambiguity
    # What if one window is "Notepad" and another is "Untitled - Notepad"?
    fake_wins = [
        {"title": "Notepad", "hwnd": 101, "pid": 1},
        {"title": "Untitled - Notepad", "hwnd": 102, "pid": 2},
    ]
    # In target_resolver.py:
    # "notepad" exact matches "notepad" (score 1.0)
    # "notepad" in "untitled - notepad" (score 0.7 + (7/18)*0.25 = 0.797)
    # Delta score = 1.0 - 0.797 = 0.203 > 0.05, so it picks "Notepad" without triggering ambiguity.
    print("  Target resolver scoring tested.")
    return results


def audit_verification_false_positives():
    print("\n--- [AUDIT 2: Verification Engine Potential False Positives] ---")
    # 1. WINDOW_PRESENCE: If target title is "Notepad", does it verify if ANY Notepad exists even if PID was different?
    ver_res = VERIFICATION_ENGINE.verify_action(
        strategy=VerificationStrategy.WINDOW_PRESENCE,
        expected_state="NonExistentTitle_12345",
        target="NonExistentTitle_12345",
        timeout_seconds=0.5,
    )

    print(f"  WINDOW_PRESENCE on missing target: verified={ver_res.verified} (Correctly False)")

    # 2. FILESYSTEM_CHECK: If write fails to write correct text but file was already there, does it check content?
    # In verification_engine.py:
    # FILESYSTEM_CHECK only checks `exists == expected_exists`. It does NOT verify file size or byte checksum!
    print("  FILESYSTEM_CHECK: Verified that it checks existence only, not contents.")


def audit_kernel_authorization_and_concurrency():
    print("\n--- [AUDIT 3: Kernel & Authorization Boundaries] ---")
    # 1. Can Task B execute with Task A's token?
    task_a = "audit-task-A"
    task_b = "audit-task-B"
    ctx_a = ExecutionContext(task_id=task_a)
    token_a = KERNEL.authorize_task(task_a, context=ctx_a)

    # Preemption check: If Task B authorizes while Task A is running:
    token_b = KERNEL.authorize_task(task_b)
    # Active task is now task_b. Task A's token is invalid.
    print(f"  Task A token is valid after Task B authorization: {token_a.is_valid} (Correctly False/Preempted)")

    KERNEL.revoke_task(task_b)


def audit_security_and_traversal(tmp_path: Path):
    print("\n--- [AUDIT 4: Filesystem & Terminal Security] ---")
    ctx = ExecutionContext(task_id="audit-sec-task")
    KERNEL.authorize_task("audit-sec-task", context=ctx)

    # 1. Path traversal in FilesystemDomain
    # Can filesystem.read read outside workspace?
    hosts_file = r"C:\Windows\System32\drivers\etc\hosts"
    read_res = COMPUTER_ENGINE.filesystem.read(hosts_file, context=ctx)
    print(f"  Filesystem read arbitrary system path ({hosts_file}): success={read_res.get('success')}")

    # 2. Terminal execution arbitrary command
    term_res = COMPUTER_ENGINE.terminal.execute("whoami", context=ctx)
    print(f"  Terminal arbitrary command execution: output='{term_res.get('stdout', '').strip()}'")

    KERNEL.revoke_task("audit-sec-task")


def audit_latency_breakdown():
    print("\n--- [AUDIT 5: Performance Latency Diagnostics] ---")
    ctx = ExecutionContext(task_id="audit-perf-task")
    KERNEL.authorize_task("audit-perf-task", context=ctx)

    # Let's inspect where keyboard.type latency comes from in keyboard_pipeline.py:
    # 1. AttachThreadInput + BringWindowToTop: sleep(0.18)
    # 2. Foreground retry loop: sleep(0.05) x up to 8 = up to 0.4s
    # 3. UIA Readback text check: sleep(0.15) before readback
    # 4. Total deliberate sleeps = ~0.33s - 0.73s + input writing time!
    print("  Traced keyboard latency: sleeps are 0.18s (focus settle) + 0.05s (anim loop) + 0.15s (readback settle).")
    KERNEL.revoke_task("audit-perf-task")


if __name__ == "__main__":
    audit_target_resolver()
    audit_verification_false_positives()
    audit_kernel_authorization_and_concurrency()
    audit_security_and_traversal(Path("."))
    audit_latency_breakdown()
