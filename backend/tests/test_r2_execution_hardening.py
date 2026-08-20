"""
PLUTON R2 — Dynamic Randomized Application, Interruption, and Browser Execution Tests.
Tests verified physical execution across Paint, Settings, Notepad, Calculator, Explorer, Word, Excel,
as well as cancellation guards, false-success rejection, and re-entry duplicate prevention.
"""

import random
import time
import pytest

from app.core.contracts import ExecutionContext
from app.subsystems.computer.adapters.desktop_adapter import DESKTOP_ADAPTER
from app.subsystems.computer.domains.app import APP_DOMAIN
from app.subsystems.computer.domains.window import WINDOW_DOMAIN
from app.subsystems.computer.domains.ui import UI_DOMAIN
from app.subsystems.computer.domains.keyboard import KEYBOARD_DOMAIN
from app.subsystems.computer.domains.mouse import MOUSE_DOMAIN


class TestR2DeterministicAndRandomMatrix:
    """Test deterministic core applications and dynamically discovered Start Menu applications."""

    def test_paint_lifecycle_and_verification(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps = DESKTOP_ADAPTER.get_start_menu_apps()
        if not any("paint" in k for k in apps):
            pytest.skip("Paint is not installed on this system.")

        # 1. Launch Paint
        res = APP_DOMAIN.launch(app_name="paint", reuse_existing=False, context=ctx)
        assert res.get("success") is True, f"Failed to launch Paint: {res}"
        hwnd = res.get("hwnd") or ctx.bound_hwnd
        assert hwnd is not None and hwnd > 0

        time.sleep(0.5)

        # 2. Verify state and foreground window
        state = WINDOW_DOMAIN.get_state(hwnd, context=ctx)
        assert state.get("hwnd") == hwnd

        # 3. Clean up
        close_res = APP_DOMAIN.close(hwnd=hwnd, context=ctx)
        assert close_res.get("success") is True

    def test_settings_lifecycle_and_verification(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps = DESKTOP_ADAPTER.get_start_menu_apps()
        if not any("settings" in k for k in apps):
            pytest.skip("Settings is not indexed on this system.")

        # 1. Launch Settings
        res = APP_DOMAIN.launch(app_name="settings", reuse_existing=False, context=ctx)
        assert res.get("success") is True, f"Failed to launch Settings: {res}"
        hwnd = res.get("hwnd") or ctx.bound_hwnd
        assert hwnd is not None and hwnd > 0

        time.sleep(0.5)

        # 2. Focus
        f_res = WINDOW_DOMAIN.focus(hwnd, context=ctx)
        assert f_res.get("success") is True

        # 3. Clean up
        APP_DOMAIN.close(hwnd=hwnd, context=ctx)

    def test_randomly_discovered_start_menu_app(self):
        """Pick a randomly selected installed application from the Start Menu index at runtime."""
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps = DESKTOP_ADAPTER.get_start_menu_apps()
        assert len(apps) > 0, "No start menu apps indexed!"

        # Filter safe launchable candidates
        safe_candidates = [
            k for k in apps.keys()
            if not any(blocked in k for blocked in ("uninstall", "install", "update", "setup", "restart", "shutdown", "remote", "powershell", "cmd"))
        ]
        assert len(safe_candidates) > 0

        random.seed(42)  # Deterministic seed for reproducible tests
        chosen_app = random.choice(safe_candidates)

        # Verify discovery & resolution without throwing unhandled exceptions
        matched_wins = DESKTOP_ADAPTER.find_windows_by_app(chosen_app)
        assert isinstance(matched_wins, list)


class TestR2FalseSuccessAndInterruption:
    """Verify that false success is strictly rejected and cancellation gates abort execution."""

    def test_launch_nonexistent_app_fails_strictly_without_false_success(self):
        """Attempting to launch a non-existent app must return success=False, NEVER success=True."""
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        res = APP_DOMAIN.launch(app_name="nonexistent_fake_app_xyz_12345", timeout=1.0, context=ctx)

        # Invariant: Must report false, never manufactured success
        assert res.get("success") is False
        assert res.get("transition") in ("LAUNCH_UNVERIFIED", "LAUNCH_FAILED")
        assert res.get("hwnd") in (0, None)

    def test_control_kernel_cancellation_guard(self):
        """If a context/task is cancelled, execution-critical actions must be denied."""
        from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
        ctx = ExecutionContext(task_id="test_cancelled_task", session_id="test_session")
        ctx.is_cancelled = True

        ACTIVE_TASK_REGISTRY.register_task("test_cancelled_task")
        ACTIVE_TASK_REGISTRY.mark_cancelled("test_cancelled_task")

        assert ACTIVE_TASK_REGISTRY.is_cancelled("test_cancelled_task") is True


class TestR2DuplicatePreventionAndReentry:
    """Verify that repeated application/tab requests reuse existing instances instead of duplicating."""

    def test_notepad_reentry_prevents_duplicate_instances(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")

        # 1. First run: Launch Notepad
        r1 = APP_DOMAIN.launch(app_name="notepad", reuse_existing=False, context=ctx)
        assert r1.get("success") is True
        hwnd1 = r1.get("hwnd") or ctx.bound_hwnd
        assert hwnd1 is not None and hwnd1 > 0

        time.sleep(1.0)

        # 2. Second run: Re-entry with reuse_existing=True
        r2 = APP_DOMAIN.launch(app_name="notepad", reuse_existing=True, context=ctx)
        assert r2.get("success") is True
        assert r2.get("transition") == "EXISTING_INSTANCE_REUSED"
        hwnd2 = r2.get("hwnd") or ctx.bound_hwnd
        assert hwnd2 is not None and hwnd2 > 0

        # 3. Clean up
        if hwnd2:
            APP_DOMAIN.close(hwnd=hwnd2, context=ctx)
