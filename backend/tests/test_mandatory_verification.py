from unittest.mock import MagicMock, patch
import pytest

from app.tools.computer_router import ComputerActionRouter, IntentType, SemanticIntent
from app.tools.uia_engine import UIAutomationEngine


@pytest.fixture
def mock_uia():
    engine = UIAutomationEngine()
    engine.is_windows = True
    return engine


@pytest.fixture
def router(mock_uia):
    return ComputerActionRouter(uia_engine=mock_uia)


# 1. Verification of Window Creation (App Launch)
def test_verify_window_creation_success(router, mock_uia):
    intent = SemanticIntent(
        intent_type=IntentType.APP_LAUNCH,
        raw_request="Open Settings",
        target="settings",
        expected_outcome="window_created:Settings",
    )
    with patch.object(mock_uia, "list_windows", return_value=[{"title": "Settings", "class_name": "ApplicationFrameWindow"}]):
        verified, msg = router.verify_action_result(intent, post_delay=0.0)
        assert verified is True
        assert "active" in msg


def test_verify_window_creation_failure(router, mock_uia):
    intent = SemanticIntent(
        intent_type=IntentType.APP_LAUNCH,
        raw_request="Open Photoshop",
        target="photoshop",
        expected_outcome="window_created:Photoshop",
    )
    with patch.object(mock_uia, "list_windows", return_value=[{"title": "Brave", "class_name": "Chrome_WidgetWin_1"}]):
        verified, msg = router.verify_action_result(intent, post_delay=0.0)
        assert verified is False
        assert "not found" in msg


# 2. Verification of Browser Tab Creation (Navigation)
def test_verify_browser_tab_navigation(router, mock_uia):
    intent = SemanticIntent(
        intent_type=IntentType.BROWSER_NAVIGATE,
        raw_request="Open Gmail",
        target="Gmail",
        browser="Brave",
        expected_outcome="tab_created:Gmail",
    )
    with patch.object(mock_uia, "list_browser_tabs", return_value=[{"title": "Inbox - Gmail", "selected": True}]):
        verified, msg = router.verify_action_result(intent, post_delay=0.0)
        assert verified is True
        assert "open" in msg


# 3. Verification of Window Closure
def test_verify_window_closure_success(router, mock_uia):
    intent = SemanticIntent(
        intent_type=IntentType.WINDOW_CLOSE,
        raw_request="Close Calculator",
        target="Calculator",
        expected_outcome="window_closed:Calculator",
    )
    with patch.object(mock_uia, "list_windows", return_value=[{"title": "Brave", "class_name": "Chrome_WidgetWin_1"}]):
        verified, msg = router.verify_action_result(intent, post_delay=0.0)
        assert verified is True
        assert "closed" in msg


def test_verify_window_closure_failure(router, mock_uia):
    intent = SemanticIntent(
        intent_type=IntentType.WINDOW_CLOSE,
        raw_request="Close Calculator",
        target="Calculator",
        expected_outcome="window_closed:Calculator",
    )
    with patch.object(mock_uia, "list_windows", return_value=[{"title": "Calculator", "class_name": "CalcFrame"}]):
        verified, msg = router.verify_action_result(intent, post_delay=0.0)
        assert verified is False
        assert "still open" in msg


# 4. Verification of Tab Closure
def test_verify_tab_closure_success(router, mock_uia):
    intent = SemanticIntent(
        intent_type=IntentType.BROWSER_TAB_CLOSE,
        raw_request="Close the Claude tab",
        target="Claude",
        browser="Brave",
        expected_outcome="tab_closed:Claude",
    )
    with patch.object(mock_uia, "list_browser_tabs", return_value=[{"title": "GitHub", "selected": True}]):
        verified, msg = router.verify_action_result(intent, post_delay=0.0)
        assert verified is True
        assert "closed" in msg


# 5. Full Semantic Execution Lifecycle with Verification
def test_execute_semantic_action_app_launch_existing_window(router, mock_uia):
    with patch.object(mock_uia, "find_window", return_value={"hwnd": 1234, "title": "Settings"}):
        with patch.object(mock_uia, "focus_window", return_value=True):
            with patch.object(mock_uia, "list_windows", return_value=[{"title": "Settings", "class_name": "App"}]):
                res = router.execute_semantic_action("Open Settings")
                assert res["success"] is True
                assert res["method"] == "focus_existing_window"
                assert res["verified"] is True


def test_execute_semantic_action_browser_nav(router, mock_uia):
    with patch("webbrowser.open", return_value=True):
        with patch.object(mock_uia, "list_browser_tabs", return_value=[{"title": "Gmail - Inbox", "selected": True}]):
            res = router.execute_semantic_action("Open Gmail")
            assert res["success"] is True
            assert res["verified"] is True
            assert "gmail" in res["message"].lower()

