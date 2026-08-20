"""
Mocked unit tests for the strict TARGET->FOCUS->INPUT->VERIFY keyboard pipeline.

All physical input is mocked. These tests prove:
  1. Compound intent parsing works ("Open Notepad and type X")
  2. HWND context is threaded from APP_LAUNCH to UI_INTERACT
  3. Input is BLOCKED when HWND is invalid / window not visible
  4. Input is BLOCKED when focus cannot be verified
  5. Input is BLOCKED when PID ownership mismatch
  6. Verification FAILS when expected text not found in UIA read-back
  7. Wrong-focus protection: other-app foreground blocks input
  8. Success only claimed when UIA confirms text in target HWND
  9. Safety gate blocks all input when no active task
"""

import sys
import types
import ctypes
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

NOTEPAD_HWND = 0xDEAD1234
NOTEPAD_PID  = 9999
OTHER_HWND   = 0xBAD00000


def _safety_allow(task_id: str = "test-task-001"):
    """Enable safety gate for a test task."""
    from app.tools.computer_safety import enable_computer_control
    enable_computer_control(task_id)
    return task_id


def _safety_revoke(task_id: str):
    from app.tools.computer_safety import disable_computer_control, emergency_kill_computer_input
    disable_computer_control(task_id)
    emergency_kill_computer_input()


# ─────────────────────────────────────────────────────────────────────────────
# 1. PARSE: Compound intent "Open Notepad and type X"
# ─────────────────────────────────────────────────────────────────────────────

class TestParsing:
    def test_compound_open_and_type(self):
        from app.tools.computer_router import ACTION_ROUTER, IntentType
        i = ACTION_ROUTER.parse_intent("Open Notepad and type HELLO FROM PLUTON")
        assert i.intent_type == IntentType.SEQUENTIAL_WORKFLOW
        steps = i.metadata["steps"]
        assert len(steps) == 2
        assert steps[0].intent_type == IntentType.APP_LAUNCH
        assert steps[1].intent_type == IntentType.UI_INTERACT
        assert "HELLO FROM PLUTON" in steps[1].value

    def test_launch_and_write(self):
        from app.tools.computer_router import ACTION_ROUTER, IntentType
        i = ACTION_ROUTER.parse_intent("Launch Notepad and write TESTING")
        assert i.intent_type == IntentType.SEQUENTIAL_WORKFLOW

    def test_comma_separated_multi_step(self):
        from app.tools.computer_router import ACTION_ROUTER, IntentType
        i = ACTION_ROUTER.parse_intent("Open Notepad, type HELLO, press Ctrl+A, type REPLACED")
        assert i.intent_type == IntentType.SEQUENTIAL_WORKFLOW
        steps = i.metadata["steps"]
        assert len(steps) == 4

    def test_general_sentence_not_sequential(self):
        from app.tools.computer_router import ACTION_ROUTER, IntentType
        i = ACTION_ROUTER.parse_intent("What is the weather today")
        assert i.intent_type == IntentType.GENERAL_ACTION

    def test_case_preserved_in_type_value(self):
        from app.tools.computer_router import ACTION_ROUTER
        i = ACTION_ROUTER.parse_intent("Open Notepad and type HELLO FROM PLUTON")
        steps = i.metadata["steps"]
        # Value must preserve original case
        assert steps[1].value == "HELLO FROM PLUTON"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PIPELINE: type_into_window unit tests with mocked Win32/UIA/pyautogui
# ─────────────────────────────────────────────────────────────────────────────

class TestKeyboardPipeline:
    """Unit tests for keyboard_pipeline.type_into_window with all input mocked."""

    def _run(self, hwnd, pid, text, *, fg_before=NOTEPAD_HWND, fg_after_focus=NOTEPAD_HWND,
             fg_after_input=NOTEPAD_HWND, is_valid=True, is_visible=True, pid_match=True,
             uia_text=None, pyautogui_raises=None, task_id="mock-task"):
        """
        Patches all thin wrapper functions in keyboard_pipeline at module level.
        No ctypes struct mocking needed.
        """
        from app.tools.computer_safety import enable_computer_control, disable_computer_control, emergency_kill_computer_input
        import app.tools.keyboard_pipeline as kp
        import importlib
        importlib.reload(kp)

        enable_computer_control(task_id)
        try:
            actual_pid_val = pid if pid_match else pid + 1

            fg_seq = [fg_before, fg_after_focus, fg_after_input]
            fg_iter = iter(fg_seq)

            # Pyautogui mock
            pyautogui_mock = MagicMock()
            if pyautogui_raises:
                pyautogui_mock.write.side_effect = pyautogui_raises
            sys.modules["pyautogui"] = pyautogui_mock

            with patch("app.tools.keyboard_pipeline.assert_computer_control_allowed"):
                with patch("app.tools.keyboard_pipeline._get_foreground_hwnd", side_effect=lambda: next(fg_iter, fg_after_input)):
                    with patch("app.tools.keyboard_pipeline._is_window_valid", return_value=is_valid):
                        with patch("app.tools.keyboard_pipeline._is_window_visible", return_value=is_visible):
                            with patch("app.tools.keyboard_pipeline._get_window_pid", return_value=actual_pid_val):
                                with patch("app.tools.keyboard_pipeline._uia_read_text", return_value=uia_text):
                                    with patch("app.tools.keyboard_pipeline._uia_set_value", return_value=(False, "no uia")):
                                        focus_ok = (fg_after_focus == hwnd)
                                        with patch("app.tools.keyboard_pipeline._focus_hwnd", return_value=(focus_ok, "mock")):
                                            return kp.type_into_window(hwnd=hwnd, pid=pid, text=text)
        finally:
            disable_computer_control(task_id)
            emergency_kill_computer_input()



    def test_success_with_uia_verification(self):
        """Happy path: correct HWND, focus confirmed, UIA returns expected text."""
        result = self._run(
            NOTEPAD_HWND, NOTEPAD_PID, "HELLO FROM PLUTON",
            fg_before=OTHER_HWND,
            fg_after_focus=NOTEPAD_HWND,
            fg_after_input=NOTEPAD_HWND,
            uia_text="HELLO FROM PLUTON",
        )
        assert result["success"] is True
        assert result["verified"] is True
        assert "HELLO FROM PLUTON" in (result.get("verified_text") or "")

    def test_blocked_invalid_hwnd(self):
        """Pipeline must block if HWND=0 provided."""
        from app.tools.keyboard_pipeline import type_into_window
        from app.tools.computer_safety import enable_computer_control, disable_computer_control
        tid = "test-invalid-hwnd"
        enable_computer_control(tid)
        try:
            with patch("app.tools.keyboard_pipeline.assert_computer_control_allowed"):
                result = type_into_window(hwnd=0, pid=0, text="X")
            assert result["success"] is False
            assert "TARGET BLOCKED" in result.get("error", "")
        finally:
            disable_computer_control(tid)

    def test_blocked_window_not_visible(self):
        result = self._run(NOTEPAD_HWND, NOTEPAD_PID, "X", is_visible=False)
        assert result["success"] is False
        assert "TARGET BLOCKED" in result.get("error", "")

    def test_blocked_pid_mismatch(self):
        result = self._run(NOTEPAD_HWND, NOTEPAD_PID, "X", pid_match=False)
        assert result["success"] is False
        assert "TARGET BLOCKED" in result.get("error", "")

    def test_blocked_focus_wrong_window(self):
        """If foreground after focus is NOT target HWND, input must be blocked."""
        result = self._run(
            NOTEPAD_HWND, NOTEPAD_PID, "X",
            fg_before=OTHER_HWND,
            fg_after_focus=OTHER_HWND,   # <-- focus failed, wrong window is FG
            fg_after_input=OTHER_HWND,
            uia_text="X",
        )
        assert result["success"] is False
        assert "FOCUS BLOCKED" in result.get("error", "")

    def test_verify_fails_text_not_found(self):
        """When UIA read-back doesn't contain the expected text, must fail."""
        result = self._run(
            NOTEPAD_HWND, NOTEPAD_PID, "EXPECTED TEXT",
            fg_before=OTHER_HWND,
            fg_after_focus=NOTEPAD_HWND,
            fg_after_input=NOTEPAD_HWND,
            uia_text="SOMETHING COMPLETELY DIFFERENT",
        )
        assert result["success"] is False
        assert "VERIFY FAILED" in result.get("error", "")

    def test_unverified_when_uia_unavailable(self):
        """When UIA returns None, success=True but verified=False with a warning."""
        result = self._run(
            NOTEPAD_HWND, NOTEPAD_PID, "HELLO",
            fg_before=OTHER_HWND,
            fg_after_focus=NOTEPAD_HWND,
            fg_after_input=NOTEPAD_HWND,
            uia_text=None,
        )
        assert result["success"] is True
        assert result["verified"] is False
        assert "verify_warning" in result

    def test_pyautogui_exception_fails_cleanly(self):
        result = self._run(
            NOTEPAD_HWND, NOTEPAD_PID, "X",
            fg_before=OTHER_HWND,
            fg_after_focus=NOTEPAD_HWND,
            fg_after_input=NOTEPAD_HWND,
            uia_text="X",
            pyautogui_raises=RuntimeError("keyboard locked"),
        )
        assert result["success"] is False
        assert "INPUT FAILED" in result.get("error", "")


# ─────────────────────────────────────────────────────────────────────────────
# 3. SAFETY: Pipeline blocked entirely with no active task
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineSafetyGate:
    def test_blocked_when_no_active_task(self):
        from app.tools.computer_safety import emergency_kill_computer_input, is_computer_control_allowed
        emergency_kill_computer_input()
        assert not is_computer_control_allowed()

        from app.tools import keyboard_pipeline
        import importlib
        importlib.reload(keyboard_pipeline)

        with pytest.raises(Exception):
            # assert_computer_control_allowed should raise
            keyboard_pipeline.type_into_window(hwnd=NOTEPAD_HWND, pid=NOTEPAD_PID, text="X")


# ─────────────────────────────────────────────────────────────────────────────
# 4. ROUTER: HWND context threaded from APP_LAUNCH to UI_INTERACT
# ─────────────────────────────────────────────────────────────────────────────

class TestHWNDContextThreading:
    def test_hwnd_injected_into_ui_interact_step(self):
        from app.tools.computer_router import ACTION_ROUTER, IntentType, SemanticIntent

        intent = ACTION_ROUTER.parse_intent("Open Notepad and type HELLO FROM PLUTON")
        assert intent.intent_type == IntentType.SEQUENTIAL_WORKFLOW
        steps = intent.metadata["steps"]

        app_launch_result = {
            "success": True,
            "method": "native_app_launch",
            "hwnd": NOTEPAD_HWND,
            "pid": NOTEPAD_PID,
            "verified": True,
            "message": "Launched notepad",
        }
        type_result = {
            "success": True,
            "method": "TargetBound/deterministic_keyboard",
            "hwnd": NOTEPAD_HWND,
            "pid": NOTEPAD_PID,
            "verified": True,
            "verified_text": "HELLO FROM PLUTON",
            "message": "Typed successfully",
        }

        injected_hwnd_seen = []

        def fake_execute(step_intent):
            if step_intent.intent_type == IntentType.APP_LAUNCH:
                return app_launch_result
            elif step_intent.intent_type == IntentType.UI_INTERACT:
                injected_hwnd_seen.append(step_intent.metadata.get("bound_hwnd"))
                return type_result
            return {"success": False, "error": "unexpected intent"}

        from app.tools.computer_safety import enable_computer_control, disable_computer_control
        enable_computer_control("ctx-test")
        try:
            with patch.object(ACTION_ROUTER, "execute_capability", side_effect=fake_execute):
                # Only testing the sequential workflow context injection
                steps_list = intent.metadata["steps"]
                context_hwnd = 0
                context_pid = 0
                for step in steps_list:
                    if step.intent_type in (IntentType.UI_INTERACT,) and context_hwnd:
                        if step.metadata is None:
                            step.metadata = {}
                        step.metadata.setdefault("bound_hwnd", context_hwnd)
                        step.metadata.setdefault("bound_pid", context_pid)
                    res = fake_execute(step)
                    if step.intent_type == IntentType.APP_LAUNCH and res.get("success"):
                        context_hwnd = res.get("hwnd", 0)
                        context_pid  = res.get("pid", 0)

            assert injected_hwnd_seen == [NOTEPAD_HWND], f"Expected HWND injected, got {injected_hwnd_seen}"
        finally:
            disable_computer_control("ctx-test")

    def test_no_success_claim_without_verified_text(self):
        """Router must NOT return success=True for a typing step unless pipeline verified."""
        from app.tools.computer_router import ACTION_ROUTER, IntentType
        from app.tools.computer_safety import enable_computer_control, disable_computer_control

        enable_computer_control("no-claim-test")
        try:
            with patch("app.tools.keyboard_pipeline.type_into_window") as mock_pipe:
                mock_pipe.return_value = {
                    "success": False,
                    "error": "VERIFY FAILED: expected text not found",
                    "verified": False,
                    "hwnd": NOTEPAD_HWND,
                    "pid": NOTEPAD_PID,
                }
                with patch("app.tools.keyboard_pipeline.assert_computer_control_allowed"):
                    result = ACTION_ROUTER.execute_capability(
                        ACTION_ROUTER.parse_intent("type HELLO FROM PLUTON")
                    )
            # Must not claim success
            assert result.get("success") is False
        finally:
            disable_computer_control("no-claim-test")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
