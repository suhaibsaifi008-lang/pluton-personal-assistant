"""
PLUTON V2 — App/UI Interaction & Mandatory Verification Audit Test Suite.

Verifies:
1. Generic UIA element inspection & comprehensive text/value readback (XAML/UWP and Win32).
2. File Explorer visible-window binding and CabinetWClass resolution.
3. Mandatory UI state verification: Tasks CANNOT become COMPLETED unless target UI state matches.
4. Pattern-first execution in UIDomainHandler (InvokePattern, ValuePattern, TogglePattern).
"""

import pytest
from unittest.mock import MagicMock, patch

from app.core.contracts import ExecutionContext, VerificationResult, VerificationStrategy, TaskState
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer.domains.ui import UIDomainHandler
from app.subsystems.computer.domains.app import AppDomainHandler
from app.subsystems.computer.domains.window import WindowDomainHandler
from app.tools.uia_engine import UIAutomationEngine
from app.verification.verification_engine import VerificationEngine


# -----------------------------------------------------------------------------
# 1. Generic Window Finding & Shell Resolution Tests
# -----------------------------------------------------------------------------

def test_find_window_resolves_file_explorer_by_class():
    """Verify find_window resolves File Explorer windows via CabinetWClass even when title is a folder name."""
    engine = UIAutomationEngine()
    fake_windows = [
        {"hwnd": 1001, "title": "Downloads", "class_name": "CabinetWClass", "pid": 4000, "is_active": True},
        {"hwnd": 1002, "title": "", "class_name": "Shell_TrayWnd", "pid": 4000, "is_active": False},
        {"hwnd": 1003, "title": "", "class_name": "Progman", "pid": 4000, "is_active": False},
    ]

    with patch.object(engine, "list_windows", return_value=fake_windows):
        res = engine.find_window("file explorer")
        assert res is not None
        assert res["hwnd"] == 1001
        assert res["class_name"] == "CabinetWClass"

        res_exp = engine.find_window("explorer")
        assert res_exp is not None
        assert res_exp["hwnd"] == 1001

        res_folder = engine.find_window("Downloads")
        assert res_folder is not None
        assert res_folder["hwnd"] == 1001


def test_find_window_resolves_calculator_uwp_window():
    """Verify find_window resolves Calculator whether title or ApplicationFrameWindow matches."""
    engine = UIAutomationEngine()
    fake_windows = [
        {"hwnd": 2001, "title": "Calculator", "class_name": "ApplicationFrameWindow", "pid": 5000, "is_active": True},
    ]

    with patch.object(engine, "list_windows", return_value=fake_windows):
        res = engine.find_window("calculator")
        assert res is not None
        assert res["hwnd"] == 2001

        res_calc = engine.find_window("calc")
        assert res_calc is not None
        assert res_calc["hwnd"] == 2001


# -----------------------------------------------------------------------------
# 2. Generic Element Readback & UI State Extraction Tests
# -----------------------------------------------------------------------------

def test_read_element_state_extracts_live_properties():
    """Verify read_element_state extracts value, text, toggle, and bounding box."""
    engine = UIAutomationEngine()
    fake_elem = MagicMock()
    fake_elem.Name = "Display is 42"
    fake_elem.ControlTypeName = "TextControl"
    fake_elem.AutomationId = "CalculatorResults"
    
    mock_val_pat = MagicMock()
    mock_val_pat.Value = "42"
    fake_elem.GetValuePattern.return_value = mock_val_pat
    fake_elem.GetLegacyIAccessiblePattern.return_value = None
    fake_elem.GetTogglePattern.return_value = None
    fake_elem.GetSelectionItemPattern.return_value = None

    rect_mock = MagicMock()
    rect_mock.left = 100
    rect_mock.top = 200
    rect_mock.width.return_value = 300
    rect_mock.height.return_value = 50
    fake_elem.BoundingRectangle = rect_mock

    with patch.object(engine, "find_ui_element", return_value=(fake_elem, "")):
        state = engine.read_element_state("CalculatorResults", hwnd=2001)
        assert state["found"] is True
        assert state["value"] == "42"
        assert state["automation_id"] == "CalculatorResults"
        assert state["control_type"] == "TextControl"
        assert state["bounding_box"] == [100, 200, 300, 50]


def test_uia_read_text_extracts_xaml_and_button_names():
    """Verify _uia_read_text traverses UIA tree and collects displayed Name from XAML controls."""
    from app.tools.keyboard_pipeline import _uia_read_text

    mock_child1 = MagicMock()
    mock_child1.ControlTypeName = "TextControl"
    mock_child1.Name = "Display is 100"
    mock_child1.GetValuePattern.return_value = None
    mock_child1.GetLegacyIAccessiblePattern.return_value = None
    mock_child1.GetTextPattern.return_value = None
    mock_child1.GetChildren.return_value = []

    mock_child2 = MagicMock()
    mock_child2.ControlTypeName = "EditControl"
    mock_child2.Name = "Search input"
    mock_val_pat = MagicMock()
    mock_val_pat.Value = "PLUTON TEST"
    mock_child2.GetValuePattern.return_value = lambda: mock_val_pat
    mock_child2.GetLegacyIAccessiblePattern.return_value = None
    mock_child2.GetTextPattern.return_value = None
    mock_child2.GetChildren.return_value = []

    mock_root = MagicMock()
    mock_root.ControlTypeName = "WindowControl"
    mock_root.Name = "Test Window"
    mock_root.GetValuePattern.return_value = None
    mock_root.GetLegacyIAccessiblePattern.return_value = None
    mock_root.GetTextPattern.return_value = None
    mock_root.GetChildren.return_value = [mock_child1, mock_child2]

    with patch("uiautomation.ControlFromHandle", return_value=mock_root):
        text = _uia_read_text(1234)
        assert text is not None
        assert "Display is 100" in text
        assert "PLUTON TEST" in text


# -----------------------------------------------------------------------------
# 3. Mandatory UI State Verification Tests
# -----------------------------------------------------------------------------

def test_mandatory_verification_fails_when_actual_state_mismatches():
    """Verify that verify_action returns verified=False when expected UI state is not present."""
    verifier = VerificationEngine()
    mock_uia = MagicMock()
    mock_uia.read_window_text.return_value = "Display is 15"
    mock_uia.read_element_state.return_value = {"found": True, "value": "15", "text": "Display is 15"}
    mock_uia.get_foreground_window.return_value = {"hwnd": 2001}
    verifier._uia = mock_uia

    res = verifier.verify_action(
        strategy=VerificationStrategy.UIA_READBACK,
        expected_state="42",
        hwnd=2001,
        timeout_seconds=0.3,
    )
    assert res.verified is False
    assert "did not contain expected text '42'" in res.message


def test_mandatory_verification_succeeds_when_actual_state_matches():
    """Verify that verify_action returns verified=True when expected UI state matches."""
    verifier = VerificationEngine()
    mock_uia = MagicMock()
    mock_uia.read_window_text.return_value = "Display is 42\nStandard Mode"
    mock_uia.get_foreground_window.return_value = {"hwnd": 2001}
    verifier._uia = mock_uia

    res = verifier.verify_action(
        strategy=VerificationStrategy.UIA_READBACK,
        expected_state="42",
        hwnd=2001,
        timeout_seconds=0.3,
    )
    assert res.verified is True
    assert "Verified text '42'" in res.message


# -----------------------------------------------------------------------------
# 4. UIDomainHandler Pattern-First Execution
# -----------------------------------------------------------------------------

def test_ui_domain_invoke_uses_native_patterns_first():
    """Verify UIDomainHandler.invoke executes native UIA patterns first and attaches observed state."""
    handler = UIDomainHandler()
    token = KERNEL.authorize_task("task_test_ui_invoke")

    ctx = ExecutionContext(task_id="task_test_ui_invoke", bound_hwnd=2001)

    with patch("app.subsystems.computer.domains.ui.UIA_ENGINE") as mock_engine:
        mock_engine.execute_ui_action.return_value = {
            "success": True,
            "method": "InvokePattern",
            "element": "Equals",
        }
        mock_engine.read_window_text.return_value = "Display is 42"

        res = handler.invoke("Equals", hwnd=2001, context=ctx)
        assert res["success"] is True
        assert res["method"] == "InvokePattern"
        assert res["observed_state"] == "Display is 42"

    KERNEL.revoke_task("task_test_ui_invoke")
