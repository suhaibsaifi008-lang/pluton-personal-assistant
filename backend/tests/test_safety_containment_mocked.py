"""Comprehensive Mocked Safety Invariant & Containment Unit Test Suite.

All physical input (Win32, PyAutoGUI, UIA, screenshots) is 100% mocked.
No real desktop or physical actions occur during this suite.

Covers:
1. Complete idle blocking for mouse, keyboard, UIA, screenshot, and vision tools.
2. Immediate revocation on completion, cancellation, error/exception, timeout, and disconnection.
3. Background worker containment (threads/workers cannot retain or execute input after task ends).
"""

import asyncio
import concurrent.futures
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.tools.computer_safety import (
    is_computer_control_allowed,
    assert_computer_control_allowed,
    enable_computer_control,
    disable_computer_control,
    emergency_kill_computer_input,
)
from app.tools.computer import (
    _mouse_move,
    _mouse_click,
    _keyboard_type,
    _hotkey,
    _key_press,
    _screenshot,
    _inspect_screen,
    _locate_element,
    _gui_action_workflow,
    _close_browser_tab,
)
from app.tools.uia_engine import UIAutomationEngine
from app.tools.computer_router import ComputerActionRouter, IntentType, SemanticIntent


# ==============================================================================
# 1. IDLE STATE BLOCKING TESTS (ZERO INPUT PERMITTED)
# ==============================================================================

class TestIdleStateContainment:
    """Verify that all computer control functions are strictly blocked when no task is active."""

    def setup_method(self):
        disable_computer_control(None)

    def test_idle_status(self):
        assert not is_computer_control_allowed(), "Control must be False in idle state"

    @patch("ctypes.windll.user32.SetCursorPos")
    @patch("pyautogui.moveTo")
    def test_mouse_move_blocked_when_idle(self, mock_pyauto, mock_win32):
        res = _mouse_move(100, 200)
        assert res.get("moved") is False
        assert "Computer control blocked" in res.get("error", "")
        mock_win32.assert_not_called()
        mock_pyauto.assert_not_called()

    @patch("ctypes.windll.user32.mouse_event")
    @patch("pyautogui.click")
    def test_mouse_click_blocked_when_idle(self, mock_pyauto, mock_win32):
        res = _mouse_click(100, 200)
        assert res.get("clicked") is False
        assert "Computer control blocked" in res.get("error", "")
        mock_win32.assert_not_called()
        mock_pyauto.assert_not_called()

    @patch("pyautogui.write")
    def test_keyboard_type_blocked_when_idle(self, mock_write):
        res = _keyboard_type("secret input")
        assert res.get("typed") is False
        assert "Computer control blocked" in res.get("error", "")
        mock_write.assert_not_called()

    @patch("pyautogui.hotkey")
    def test_hotkey_blocked_when_idle(self, mock_hotkey):
        res = _hotkey(["ctrl", "t"])
        assert res.get("executed") is False
        assert "Computer control blocked" in res.get("error", "")
        mock_hotkey.assert_not_called()

    @patch("pyautogui.press")
    def test_key_press_blocked_when_idle(self, mock_press):
        res = _key_press("enter")
        assert res.get("pressed") is False
        assert "Computer control blocked" in res.get("error", "")
        mock_press.assert_not_called()

    @patch("app.tools.computer._capture_screen_image_with_diag")
    def test_screenshot_blocked_when_idle(self, mock_capture):
        res = _screenshot()
        assert not res.get("captured", False)
        assert "Computer control blocked" in res.get("error", "")
        mock_capture.assert_not_called()

    @patch("app.tools.computer.create_provider")
    def test_inspect_screen_blocked_when_idle(self, mock_provider):
        res = _inspect_screen("what is here?")
        assert not res.get("inspected", False)
        assert "Computer control blocked" in res.get("error", "")
        mock_provider.assert_not_called()

    @patch("app.tools.computer.create_provider")
    def test_locate_element_blocked_when_idle(self, mock_provider):
        res = _locate_element("Submit button")
        assert res.get("found") is False
        assert "Computer control blocked" in res.get("reason", "")
        mock_provider.assert_not_called()

    @patch("app.tools.computer._screenshot")
    def test_gui_action_workflow_blocked_when_idle(self, mock_ss):
        res = _gui_action_workflow(target_element="Save", action="click")
        assert res.get("success") is not True
        assert "Computer control blocked" in res.get("error", "")
        mock_ss.assert_not_called()

    @patch("app.tools.computer._screenshot")
    def test_close_browser_tab_blocked_when_idle(self, mock_ss):
        res = _close_browser_tab(tab_name="Claude", browser_name="Brave")
        assert res.get("success") is not True
        assert "Computer control blocked" in res.get("error", "")
        mock_ss.assert_not_called()

    def test_uia_focus_window_blocked_when_idle(self):
        engine = UIAutomationEngine()
        res = engine.focus_window(12345)
        assert res is False

    def test_uia_close_window_blocked_when_idle(self):
        engine = UIAutomationEngine()
        res = engine.close_window(12345)
        assert res is False

    def test_uia_execute_ui_action_blocked_when_idle(self):
        engine = UIAutomationEngine()
        res = engine.execute_ui_action(target_name="Save", action="invoke")
        assert res.get("success") is False
        assert "Computer control blocked" in res.get("error", "")

    def test_router_capability_blocked_when_idle(self):
        router = ComputerActionRouter()
        intent = router.parse_intent("Open Notepad")
        res = router.execute_capability(intent)
        assert res.get("success") is False
        assert "Computer control blocked" in res.get("error", "")


# ==============================================================================
# 2. LIFECYCLE REVOCATION TRANSITIONS
# ==============================================================================

class TestLifecycleRevocation:
    """Verify immediate revocation on completion, error, cancellation, and disconnection."""

    def test_task_completion_lifecycle(self):
        task_id = "task-completed-001"
        enable_computer_control(task_id)
        assert is_computer_control_allowed(task_id) is True

        # Simulate task completion
        disable_computer_control(task_id)
        assert is_computer_control_allowed() is False
        assert is_computer_control_allowed(task_id) is False

    def test_task_cancellation_lifecycle(self):
        task_id = "task-cancelled-002"
        enable_computer_control(task_id)
        assert is_computer_control_allowed(task_id) is True

        # Cancellation triggers emergency kill and disable
        emergency_kill_computer_input()
        disable_computer_control(task_id)
        assert is_computer_control_allowed() is False

    def test_task_error_lifecycle(self):
        task_id = "task-error-003"
        enable_computer_control(task_id)
        assert is_computer_control_allowed(task_id) is True

        # Exception in task execution -> finally block runs emergency kill & disable
        try:
            raise RuntimeError("Unexpected tool failure")
        except Exception:
            emergency_kill_computer_input()
            disable_computer_control(task_id)

        assert is_computer_control_allowed() is False

    def test_task_timeout_or_generator_close(self):
        task_id = "task-timeout-004"
        enable_computer_control(task_id)
        assert is_computer_control_allowed(task_id) is True

        # Disconnection or generator close
        emergency_kill_computer_input()
        disable_computer_control(task_id)
        assert is_computer_control_allowed() is False


# ==============================================================================
# 3. BACKGROUND WORKER CONTAINMENT TESTS
# ==============================================================================

class TestBackgroundWorkerContainment:
    """Verify that background workers/threads cannot retain or execute input after task ends."""

    def test_background_worker_blocked_post_task(self):
        task_id = "task-bg-001"
        enable_computer_control(task_id)

        worker_results = []

        def background_worker():
            # Wait for task to end
            time.sleep(0.1)
            # Try issuing physical input
            res_move = _mouse_move(300, 300)
            res_type = _keyboard_type("rogue background input")
            worker_results.append((res_move, res_type))

        thread = threading.Thread(target=background_worker)
        thread.start()

        # End the task immediately
        disable_computer_control(task_id)
        emergency_kill_computer_input()

        thread.join(timeout=2.0)

        assert len(worker_results) == 1
        res_move, res_type = worker_results[0]
        assert res_move.get("moved") is False
        assert "Computer control blocked" in res_move.get("error", "")
        assert res_type.get("typed") is False
        assert "Computer control blocked" in res_type.get("error", "")

    def test_concurrent_unauthorized_threads(self):
        disable_computer_control(None)

        def worker_attempt():
            return _keyboard_type("unauthorized text").get("typed", False)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_attempt) for _ in range(10)]
            results = [f.result() for f in futures]

        assert not any(results), "Zero unauthorized background attempts should succeed"
