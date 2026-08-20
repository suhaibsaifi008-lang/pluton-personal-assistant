"""Capability-level integration tests for Generic Capability Hierarchy & Semantic Computer Control.

Verifies that:
1. Browser tab creation/navigation never invokes screenshot/vision when deterministic mechanisms are available.
2. Browser tab listing, switching, and closing use structured UI Automation before any vision fallback.
3. Desktop UI controls (Invoke, Value, Toggle) execute via UIA patterns.
4. Window management (list, switch, close) executes via Win32 / UIA.
5. File and folder operations execute via native OS / explorer.
6. Vision workflows are restricted to genuine fallbacks when structured elements cannot be located.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.tools.computer_router import ACTION_ROUTER, ComputerActionRouter, IntentType, SemanticIntent


# ------------------------------------------------------------------------------
# 1. Browser Capabilities: Navigation and Tab Creation
# ------------------------------------------------------------------------------

def test_browser_navigation_uses_native_api_without_vision():
    """Verify that 'Open Gmail in Brave' uses browser API without invoking screenshot/vision."""
    intent = ACTION_ROUTER.parse_intent("Open Gmail in Brave browser")
    assert intent.intent_type == IntentType.BROWSER_NAVIGATE
    assert "mail.google.com" in intent.value

    mock_uia = MagicMock()
    mock_uia.list_browser_tabs.return_value = [{"title": "Gmail - Inbox", "selected": True}]
    router = ComputerActionRouter(uia_engine=mock_uia)

    with patch("webbrowser.open", return_value=True) as mock_web_open, \
         patch("app.tools.computer._screenshot") as mock_ss:

        res = router.execute_capability(intent)

        # Must execute via browser_navigation
        assert res["success"] is True
        assert res["method"] == "browser_navigation"
        assert mock_web_open.called
        # Must NEVER take screenshot or invoke vision
        assert not mock_ss.called


def test_browser_tab_creation_uses_keyboard_or_api_without_vision():
    """Verify that 'Open a new tab in Brave' creates a tab without invoking vision."""
    intent = ACTION_ROUTER.parse_intent("Open a new tab in Brave")
    assert intent.intent_type == IntentType.BROWSER_TAB_CREATE

    mock_uia = MagicMock()
    mock_uia.find_window.return_value = {"hwnd": 12345, "title": "Brave"}
    mock_uia.list_browser_tabs.return_value = [{"title": "New Tab", "selected": True}]
    router = ComputerActionRouter(uia_engine=mock_uia)

    with patch("pyautogui.hotkey") as mock_hotkey, \
         patch("app.tools.computer._screenshot") as mock_ss:

        res = router.execute_capability(intent)

        assert res["success"] is True
        assert res["method"] == "keyboard_shortcut"
        assert mock_hotkey.called
        assert not mock_ss.called


# ------------------------------------------------------------------------------
# 2. Browser Tab Management: List, Switch, Close via UIA
# ------------------------------------------------------------------------------

def test_browser_tab_list_uses_uia_without_vision():
    intent = ACTION_ROUTER.parse_intent("What tabs do I have open in Brave?")
    assert intent.intent_type == IntentType.BROWSER_TAB_LIST

    mock_uia = MagicMock()
    mock_uia.list_browser_tabs.return_value = [
        {"title": "Claude", "selected": False},
        {"title": "GitHub", "selected": True},
    ]
    router = ComputerActionRouter(uia_engine=mock_uia)

    with patch("app.tools.computer._screenshot") as mock_ss:
        res = router.execute_capability(intent)

        assert res["success"] is True
        assert res["tab_count"] == 2
        assert res["method"] == "ui_automation"
        assert not mock_ss.called


def test_browser_tab_switch_uses_uia_without_vision():
    intent = ACTION_ROUTER.parse_intent("Switch to the Claude tab in Brave")
    assert intent.intent_type == IntentType.BROWSER_TAB_SWITCH
    assert intent.target == "Claude"

    mock_uia = MagicMock()
    mock_uia.switch_browser_tab.return_value = {"success": True, "method": "ui_automation", "tab": "Claude"}
    mock_uia.list_browser_tabs.return_value = [{"title": "Claude", "selected": True}]
    router = ComputerActionRouter(uia_engine=mock_uia)

    with patch("app.tools.computer._screenshot") as mock_ss:
        res = router.execute_capability(intent)

        assert res["success"] is True
        assert res["method"] == "ui_automation"
        assert mock_uia.switch_browser_tab.called
        assert not mock_ss.called


def test_browser_tab_close_uses_uia_before_vision_fallback():
    intent = ACTION_ROUTER.parse_intent("Close the YouTube tab in Brave")
    assert intent.intent_type == IntentType.BROWSER_TAB_CLOSE

    mock_uia = MagicMock()
    mock_uia.close_browser_tab_uia.return_value = {"success": True, "method": "ui_automation", "closed_tab": "YouTube"}
    router = ComputerActionRouter(uia_engine=mock_uia)

    with patch("app.tools.computer._screenshot") as mock_ss:
        res = router.execute_capability(intent)

        assert res["success"] is True
        assert res["method"] == "ui_automation"
        assert mock_uia.close_browser_tab_uia.called
        # Never calls vision when UIA succeeds
        assert not mock_ss.called


# ------------------------------------------------------------------------------
# 3. Desktop UI Capabilities (Inspection & Interaction via UIA)
# ------------------------------------------------------------------------------

def test_inspect_ui_tree_uses_uia():
    intent = ACTION_ROUTER.parse_intent("What controls are visible on the active window?")
    assert intent.intent_type == IntentType.INSPECT_UI

    mock_uia = MagicMock()
    mock_uia.inspect_ui_tree.return_value = {"window": "Settings", "elements": [{"name": "Bluetooth", "type": "Button"}]}
    router = ComputerActionRouter(uia_engine=mock_uia)

    res = router.execute_capability(intent)
    assert res["success"] is True
    assert mock_uia.inspect_ui_tree.called


def test_ui_element_interaction_uses_uia_pattern():
    intent = ACTION_ROUTER.parse_intent("Click the Save button")
    assert intent.intent_type == IntentType.UI_INTERACT
    assert intent.action_verb == "invoke"
    assert intent.target == "Save"

    mock_uia = MagicMock()
    mock_uia.execute_ui_action.return_value = {"success": True, "method": "pattern_invoke", "target": "Save"}
    router = ComputerActionRouter(uia_engine=mock_uia)

    res = router.execute_capability(intent)
    assert res["success"] is True
    assert res["method"] == "pattern_invoke"
    assert mock_uia.execute_ui_action.called


# ------------------------------------------------------------------------------
# 4. Window Management Capabilities
# ------------------------------------------------------------------------------

def test_window_list_uses_win32_uia():
    intent = ACTION_ROUTER.parse_intent("What windows are currently open?")
    assert intent.intent_type == IntentType.WINDOW_LIST

    mock_uia = MagicMock()
    mock_uia.list_windows.return_value = [{"hwnd": 1, "title": "Brave"}, {"hwnd": 2, "title": "Settings"}]
    mock_uia.get_active_window_info.return_value = {"title": "Brave"}
    router = ComputerActionRouter(uia_engine=mock_uia)

    res = router.execute_capability(intent)
    assert res["success"] is True
    assert res["window_count"] == 2


def test_window_switch_uses_win32_uia():
    intent = ACTION_ROUTER.parse_intent("Switch to Settings window")
    assert intent.intent_type == IntentType.WINDOW_SWITCH
    assert intent.target == "Settings"

    mock_uia = MagicMock()
    mock_uia.find_window.return_value = {"hwnd": 8888, "title": "Settings"}
    mock_uia.focus_window.return_value = True
    mock_uia.get_active_window_info.return_value = {"title": "Settings"}
    router = ComputerActionRouter(uia_engine=mock_uia)

    res = router.execute_capability(intent)
    assert res["success"] is True
    assert res["method"] == "ui_automation"


def test_window_close_uses_win32_uia():
    intent = ACTION_ROUTER.parse_intent("Close Calculator window")
    assert intent.intent_type == IntentType.WINDOW_CLOSE
    assert intent.target == "Calculator"

    mock_uia = MagicMock()
    mock_uia.find_window.return_value = {"hwnd": 9999, "title": "Calculator"}
    mock_uia.close_window.return_value = True
    mock_uia.list_windows.return_value = []
    router = ComputerActionRouter(uia_engine=mock_uia)

    res = router.execute_capability(intent)
    assert res["success"] is True
    assert res["method"] == "ui_automation"


# ------------------------------------------------------------------------------
# 5. File & Folder Operations
# ------------------------------------------------------------------------------

def test_folder_open_uses_native_explorer():
    intent = ACTION_ROUTER.parse_intent("Open Downloads folder")
    assert intent.intent_type == IntentType.FOLDER_OPEN

    mock_uia = MagicMock()
    mock_uia.list_windows.return_value = [{"title": "Downloads", "class_name": "CabinetWClass"}]
    router = ComputerActionRouter(uia_engine=mock_uia)

    with patch("subprocess.Popen") as mock_popen:
        res = router.execute_capability(intent)
        assert res["success"] is True
        assert res["method"] == "native_explorer"
        assert mock_popen.called


def test_file_open_uses_native_startfile():
    intent = ACTION_ROUTER.parse_intent("Open file report.pdf")
    assert intent.intent_type == IntentType.FILE_OPEN

    router = ComputerActionRouter()
    with patch("pathlib.Path.resolve") as mock_resolve, \
         patch("os.startfile") as mock_startfile:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.name = "report.pdf"
        mock_resolve.return_value = mock_path

        res = router.execute_capability(intent)
        assert res["success"] is True
        assert res["method"] == "native_startfile"
