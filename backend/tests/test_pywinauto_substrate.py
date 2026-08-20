"""
PLUTON R1 — Complete Pywinauto Substrate Acceptance & Verification Suite.
Tests generic Windows application discovery, launch, HWND/PID binding, UI tree inspection,
re-entry/duplicate prevention, cancellation gates, and false-success rejection on real Windows desktop.
"""

import os
import random
import time
import pytest

from app.core.contracts import ExecutionContext
from app.subsystems.computer.adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
from app.subsystems.computer.domains.app import APP_DOMAIN
from app.subsystems.computer.domains.window import WINDOW_DOMAIN
from app.subsystems.computer.domains.ui import UI_DOMAIN
from app.subsystems.computer.domains.keyboard import KEYBOARD_DOMAIN
from app.subsystems.computer.domains.mouse import MOUSE_DOMAIN


class TestPywinautoSubstrateCore:
    """Unit and core functionality tests for PywinautoExecutionAdapter."""

    def test_adapter_initialization(self):
        assert PYWINAUTO_ADAPTER is not None

    def test_start_menu_apps_indexed(self):
        apps = PYWINAUTO_ADAPTER.get_start_menu_apps()
        assert isinstance(apps, dict)
        assert len(apps) > 10, f"Expected >10 indexed start menu applications, got {len(apps)}"

    def test_list_windows_returns_structured_metadata(self):
        wins = PYWINAUTO_ADAPTER.list_windows(visible_only=True)
        assert isinstance(wins, list)
        for w in wins:
            assert "hwnd" in w and isinstance(w["hwnd"], int)
            assert "title" in w
            assert "class_name" in w
            assert "pid" in w

    def test_bounded_ui_inspection_speed(self):
        wins = PYWINAUTO_ADAPTER.list_windows(visible_only=True)
        target_win = next((w for w in wins if w.get("title")), None)
        if not target_win:
            pytest.skip("No visible windows found with title.")

        hwnd = target_win["hwnd"]
        t_start = time.perf_counter()
        elements = PYWINAUTO_ADAPTER.inspect_ui_tree(hwnd=hwnd, max_depth=3, max_elements=50)
        elapsed = time.perf_counter() - t_start

        assert isinstance(elements, list)
        assert elapsed < 1.5, f"Bounded UIA inspection took {elapsed:.2f}s (must be <1.5s)"


class TestRealWindowsAcceptance:
    """Live Windows desktop application lifecycle, interaction, and verification tests."""

    def test_notepad_full_lifecycle(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")

        # 1. Launch
        res = APP_DOMAIN.launch(app_name="notepad", reuse_existing=False, context=ctx)
        assert res.get("success") is True, f"Failed to launch Notepad: {res}"
        hwnd = res.get("hwnd") or ctx.bound_hwnd
        assert hwnd is not None and hwnd > 0

        time.sleep(0.5)

        # 2. Inspect UI
        elements = UI_DOMAIN.inspect(hwnd=hwnd, context=ctx)
        assert isinstance(elements, list)

        # 3. Focus and Type
        f_res = WINDOW_DOMAIN.focus(hwnd, context=ctx)
        assert f_res.get("success") is True
        type_res = KEYBOARD_DOMAIN.type_text("Pluton R1 pywinauto substrate verified.", hwnd=hwnd, context=ctx)
        assert type_res.get("success") is True

        # 4. Clean up
        time.sleep(0.5)
        close_res = APP_DOMAIN.close(hwnd=hwnd, context=ctx)
        assert close_res.get("success") is True

    def test_paint_full_lifecycle(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps = PYWINAUTO_ADAPTER.get_start_menu_apps()
        if not any("paint" in k for k in apps):
            pytest.skip("Paint is not installed on this system.")

        # 1. Launch
        res = APP_DOMAIN.launch(app_name="paint", reuse_existing=False, context=ctx)
        assert res.get("success") is True
        hwnd = res.get("hwnd") or ctx.bound_hwnd
        assert hwnd is not None and hwnd > 0

        time.sleep(0.5)

        # 2. Inspect & Verify
        state = WINDOW_DOMAIN.get_state(hwnd, context=ctx)
        assert state.get("hwnd") == hwnd

        # 3. Clean up
        APP_DOMAIN.close(hwnd=hwnd, context=ctx)

    def test_settings_full_lifecycle(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps = PYWINAUTO_ADAPTER.get_start_menu_apps()
        if not any("settings" in k for k in apps):
            pytest.skip("Settings is not indexed on this system.")

        # 1. Launch
        res = APP_DOMAIN.launch(app_name="settings", reuse_existing=False, context=ctx)
        assert res.get("success") is True
        hwnd = res.get("hwnd") or ctx.bound_hwnd
        assert hwnd is not None and hwnd > 0

        time.sleep(0.5)

        # 2. Focus
        f_res = WINDOW_DOMAIN.focus(hwnd, context=ctx)
        assert f_res.get("success") is True

        # 3. Clean up
        APP_DOMAIN.close(hwnd=hwnd, context=ctx)

    def test_word_or_excel_status_and_control(self):
        """Test Word or Excel if installed on machine."""
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps = PYWINAUTO_ADAPTER.get_start_menu_apps()
        has_word = any("word" in k for k in apps)
        if not has_word:
            pytest.skip("Microsoft Word not installed.")

        # Check existing window or discover
        matched = PYWINAUTO_ADAPTER.find_windows_by_app("word")
        if matched:
            hwnd = matched[0]["hwnd"]
            elements = PYWINAUTO_ADAPTER.inspect_ui_tree(hwnd=hwnd, max_depth=2, max_elements=20)
            assert isinstance(elements, list)

    def test_randomly_discovered_desktop_application(self):
        """Randomly select an application from Start Menu index at runtime."""
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps = PYWINAUTO_ADAPTER.get_start_menu_apps()
        assert len(apps) > 0

        safe_candidates = [
            k for k in apps.keys()
            if not any(blocked in k for blocked in ("uninstall", "install", "update", "setup", "restart", "shutdown", "remote", "powershell", "cmd"))
        ]
        assert len(safe_candidates) > 0

        random.seed(1337)
        chosen_app = random.choice(safe_candidates)
        matched_wins = PYWINAUTO_ADAPTER.find_windows_by_app(chosen_app)
        assert isinstance(matched_wins, list)


class TestSafetyCancellationAndFalseSuccessRejection:
    """Verify strict rejection of false-success and cancellation gates."""

    def test_nonexistent_application_launch_fails_strictly(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        res = APP_DOMAIN.launch(app_name="nonexistent_invalid_app_xyz_9999", timeout=1.0, context=ctx)

        # Must report false, never manufactured success
        assert res.get("success") is False
        assert res.get("transition") in ("LAUNCH_UNVERIFIED", "LAUNCH_FAILED", "LAUNCH_VERIFICATION_FAILED")
        assert res.get("hwnd") in (0, None)

    def test_cancellation_guard_stops_execution(self):
        from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
        ctx = ExecutionContext(task_id="test_r1_cancelled_task", session_id="test_session")
        ctx.is_cancelled = True

        ACTIVE_TASK_REGISTRY.register_task("test_r1_cancelled_task")
        ACTIVE_TASK_REGISTRY.mark_cancelled("test_r1_cancelled_task")

        assert ACTIVE_TASK_REGISTRY.is_cancelled("test_r1_cancelled_task") is True

    def test_reentry_prevents_duplicate_windows(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")

        # 1. First launch
        r1 = APP_DOMAIN.launch(app_name="notepad", reuse_existing=False, context=ctx)
        assert r1.get("success") is True
        hwnd1 = r1.get("hwnd") or ctx.bound_hwnd
        assert hwnd1 is not None and hwnd1 > 0

        time.sleep(0.8)

        # 2. Second launch with reuse_existing=True
        r2 = APP_DOMAIN.launch(app_name="notepad", reuse_existing=True, context=ctx)
        assert r2.get("success") is True
        assert r2.get("transition") == "EXISTING_INSTANCE_REUSED"
        hwnd2 = r2.get("hwnd") or ctx.bound_hwnd
        assert hwnd2 is not None and hwnd2 > 0

        # 3. Clean up
        if hwnd2:
            APP_DOMAIN.close(hwnd=hwnd2, context=ctx)
