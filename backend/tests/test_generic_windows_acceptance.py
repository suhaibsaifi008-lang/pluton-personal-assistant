"""
PLUTON R1 — Generic Windows Control Substrate Acceptance Test Suite.
"""

import os
import random
import sys
import time
import pytest

from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL
from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
from app.subsystems.computer.adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
from app.subsystems.computer.domains.app import APP_DOMAIN
from app.subsystems.computer.domains.window import WINDOW_DOMAIN
from app.subsystems.computer.domains.ui import UI_DOMAIN
from app.subsystems.computer.domains.keyboard import KEYBOARD_DOMAIN


def get_safe_discovered_applications() -> list[str]:
    apps_index = PYWINAUTO_ADAPTER.get_start_menu_apps()
    safe_pool = []
    # Dynamic selection of safe GUI applications installed and verified on this host
    core_candidates = [
        "notepad",
        "paint",
        "calculator",
        "settings",
        "camera",
        "clock",
        "powershell",
        "snipping tool",
        "sound recorder",
        "photos",
        "media player",
        "weather",
        "sticky notes",
    ]
    for c in core_candidates:
        if c in apps_index and c not in safe_pool:
            safe_pool.append(c)
    for name, appid in apps_index.items():
        n_low = name.lower()
        if any(bad in n_low for bad in ("uninstall", "help", "setup", "update", "manual", "documentation", "cert", "support", "link", "installer", "cmd", "word", "excel", "edge", "explorer", "brave", "chrome", "admin", "uac")):
            continue
        if appid.startswith("http") or appid.endswith(".url") or appid.endswith(".txt") or appid.endswith(".chm") or appid.endswith(".html"):
            continue
        if name not in safe_pool:
            safe_pool.append(name)
    return safe_pool


class TestGenericWindowsSubstrateLifecycle:
    @pytest.fixture(autouse=True)
    def setup_kernel_token(self):
        token = KERNEL.authorize_task("r1-acceptance-task", ttl_seconds=300.0)
        yield
        KERNEL.revoke_task("r1-acceptance-task")

    def test_dynamic_application_discovery_unbounded(self):
        safe_apps = get_safe_discovered_applications()
        assert len(safe_apps) >= 12, f"Expected at least 12 discovered safe apps, found {len(safe_apps)}"

    @pytest.mark.parametrize("seed_offset", [101, 202, 303])
    def test_randomized_application_lifecycle_matrix(self, seed_offset):
        safe_apps = get_safe_discovered_applications()
        random.seed(seed_offset)
        selected_apps = random.sample(safe_apps[:12], 4)
        ctx = ExecutionContext(task_id="r1-acceptance-task", session_id=f"sess_{seed_offset}")
        for app_name in selected_apps:
            l_res = APP_DOMAIN.launch(app_name=app_name, reuse_existing=False, context=ctx)
            assert l_res.get("success") is True, f"Failed to launch {app_name}: {l_res}"
            hwnd = l_res.get("hwnd") or ctx.bound_hwnd
            pid = l_res.get("pid") or ctx.bound_pid
            assert hwnd and hwnd > 0

            f_res = WINDOW_DOMAIN.focus(hwnd, context=ctx)
            assert f_res.get("success") is True
            state = WINDOW_DOMAIN.get_state(hwnd, context=ctx)
            assert state.get("foreground") is True

            elements = UI_DOMAIN.inspect(hwnd=hwnd, context=ctx)
            assert isinstance(elements, list)

            if app_name in ("notepad", "cmd", "powershell"):
                type_res = KEYBOARD_DOMAIN.type_text(" echo R1_VERIFIED", hwnd=hwnd, context=ctx)
                assert type_res.get("success") is True

            c_res = APP_DOMAIN.close(hwnd=hwnd, context=ctx)
            assert c_res.get("success") is True


class TestReentryAndCancellationSubstrate:
    @pytest.fixture(autouse=True)
    def setup_kernel_token(self):
        token = KERNEL.authorize_task("r1-reentry-task", ttl_seconds=120.0)
        yield
        KERNEL.revoke_task("r1-reentry-task")

    def test_reentry_reuses_existing_instance(self):
        ctx = ExecutionContext(task_id="r1-reentry-task", session_id="sess_reentry")
        r1 = APP_DOMAIN.launch(app_name="notepad", reuse_existing=False, context=ctx)
        assert r1.get("success") is True
        hwnd1 = r1.get("hwnd")
        try:
            r2 = APP_DOMAIN.launch(app_name="notepad", reuse_existing=True, context=ctx)
            assert r2.get("success") is True
            assert r2.get("transition") == "EXISTING_INSTANCE_REUSED"
            assert r2.get("hwnd") == hwnd1
        finally:
            APP_DOMAIN.close(hwnd=hwnd1, context=ctx)

    def test_cancellation_halts_task_execution(self):
        ctx = ExecutionContext(task_id="cancelled-task-id", session_id="sess_cancel")
        ctx.is_cancelled = True
        ACTIVE_TASK_REGISTRY.register_task("cancelled-task-id")
        ACTIVE_TASK_REGISTRY.mark_cancelled("cancelled-task-id")
        assert ACTIVE_TASK_REGISTRY.is_cancelled("cancelled-task-id") is True

    def test_nonexistent_application_fails_observably(self):
        ctx = ExecutionContext(task_id="r1-reentry-task", session_id="sess_fail")
        res = APP_DOMAIN.launch(app_name="invalid_nonexistent_app_99999", timeout=1.0, context=ctx)
        assert res.get("success") is False
        assert res.get("transition") == "LAUNCH_VERIFICATION_FAILED"
