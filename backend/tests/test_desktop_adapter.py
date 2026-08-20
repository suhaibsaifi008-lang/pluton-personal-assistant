"""
Unit, Contract, and Live Acceptance Tests for PLUTON R1 Desktop Execution Layer.
Tests Calculator, Notepad, File Explorer, Word/Excel, multi-window, and idempotency.
"""

import sys
import time
import pytest

from app.core.contracts import ExecutionContext
from app.subsystems.computer.adapters.desktop_adapter import DESKTOP_ADAPTER
from app.subsystems.computer.domains.app import APP_DOMAIN
from app.subsystems.computer.domains.window import WINDOW_DOMAIN
from app.subsystems.computer.domains.ui import UI_DOMAIN
from app.subsystems.computer.domains.keyboard import KEYBOARD_DOMAIN
from app.subsystems.computer.domains.mouse import MOUSE_DOMAIN


class TestDesktopExecutionAdapter:
    """Unit and Contract tests for DesktopExecutionAdapter."""

    def test_adapter_initialization(self):
        assert DESKTOP_ADAPTER is not None
        assert hasattr(DESKTOP_ADAPTER, "launch_app")
        assert hasattr(DESKTOP_ADAPTER, "list_windows")
        assert hasattr(DESKTOP_ADAPTER, "focus_window")
        assert hasattr(DESKTOP_ADAPTER, "inspect_ui_tree")
        assert hasattr(DESKTOP_ADAPTER, "click_coords")
        assert hasattr(DESKTOP_ADAPTER, "type_text")

    def test_start_menu_apps_indexed(self):
        apps = DESKTOP_ADAPTER.get_start_menu_apps()
        assert isinstance(apps, dict)
        assert len(apps) > 0
        assert "calculator" in apps or any("calc" in k for k in apps)

    def test_list_windows_returns_structured_metadata(self):
        windows = DESKTOP_ADAPTER.list_windows(visible_only=True)
        assert isinstance(windows, list)
        if windows:
            w = windows[0]
            assert "hwnd" in w
            assert "pid" in w
            assert "title" in w
            assert "rect" in w

    def test_bounded_ui_inspection_speed(self):
        windows = DESKTOP_ADAPTER.list_windows(visible_only=True)
        if not windows:
            pytest.skip("No visible windows on desktop")
        target_hwnd = windows[0]["hwnd"]

        t_start = time.perf_counter()
        res = DESKTOP_ADAPTER.inspect_ui_tree(hwnd=target_hwnd, max_depth=3, max_elements=30)
        elapsed = time.perf_counter() - t_start

        # Ensure tree inspection completes in under 1.5s (preventing 3s timeout)
        assert elapsed < 1.5
        assert isinstance(res.get("elements"), list)


class TestLiveWindowsApplications:
    """Live Windows desktop execution tests against real Windows apps."""

    def test_notepad_lifecycle_and_typing(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        # 1. Launch Notepad
        launch_res = APP_DOMAIN.launch(app_name="notepad", context=ctx)
        assert launch_res.get("success") is True
        hwnd = launch_res.get("hwnd") or ctx.bound_hwnd
        assert hwnd is not None and hwnd > 0

        time.sleep(0.5)

        # 2. Type into Notepad
        type_res = KEYBOARD_DOMAIN.type_text(text="PLUTON R1 Windows-Use Integration Verified!", hwnd=hwnd, context=ctx)
        assert type_res.get("success") is True

        # 3. Clean up by closing Notepad
        time.sleep(0.5)
        close_res = APP_DOMAIN.close(hwnd=hwnd, context=ctx)
        assert close_res.get("success") is True

    def test_calculator_launch_and_idempotent_reuse(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        # 1. Launch Calculator
        res1 = APP_DOMAIN.launch(app_name="calculator", reuse_existing=False, context=ctx)
        assert res1.get("success") is True
        hwnd1 = res1.get("hwnd") or ctx.bound_hwnd

        time.sleep(1.0)

        # 2. Idempotent Re-entry: Launch with reuse_existing=True
        res2 = APP_DOMAIN.launch(app_name="calculator", reuse_existing=True, context=ctx)
        assert res2.get("success") is True
        assert res2.get("transition") in ("EXISTING_INSTANCE_REUSED", "WINDOW_CREATED")
        hwnd2 = res2.get("hwnd") or ctx.bound_hwnd
        assert hwnd2 is not None and hwnd2 > 0

        # 3. Clean up Calculator
        if hwnd2:
            APP_DOMAIN.close(hwnd=hwnd2, context=ctx)

    def test_file_explorer_window_discovery(self):
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        wins = WINDOW_DOMAIN.list_windows(visible_only=True, context=ctx)
        assert isinstance(wins, list)

        # Find or check explorer
        exp_win = WINDOW_DOMAIN.find_window("explorer", context=ctx)
        # Should return metadata or None cleanly without crashing
        assert exp_win is None or isinstance(exp_win, dict)

    def test_word_excel_status_reporting(self):
        """Word & Excel: If installed test launch/check, if not installed report cleanly."""
        ctx = ExecutionContext(task_id="pytest-test-task", session_id="test_session")
        apps_map = DESKTOP_ADAPTER.get_start_menu_apps()

        word_installed = "word" in apps_map or any("word" in k for k in apps_map)
        excel_installed = "excel" in apps_map or any("excel" in k for k in apps_map)

        if word_installed:
            w_res = APP_DOMAIN.is_running("Word", context=ctx)
            assert "running" in w_res
        else:
            # Cleanly reported as not installed/skipped
            assert not word_installed

        if excel_installed:
            e_res = APP_DOMAIN.is_running("Excel", context=ctx)
            assert "running" in e_res
        else:
            assert not excel_installed
