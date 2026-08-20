from unittest.mock import MagicMock, patch
import pytest

from app.tools.computer import (
    _list_windows,
    _switch_window,
    _close_window,
    _inspect_ui_tree,
    _ui_action,
    _list_browser_tabs,
    _switch_browser_tab,
)
from app.tools.uia_engine import UIA_ENGINE


def test_list_windows_tool():
    mock_wins = [
        {"hwnd": 1001, "title": "Brave Browser", "class_name": "Chrome_WidgetWin_1", "pid": 1234},
        {"hwnd": 1002, "title": "Settings", "class_name": "ApplicationFrameWindow", "pid": 5678},
    ]
    with patch.object(UIA_ENGINE, "list_windows", return_value=mock_wins):
        with patch.object(UIA_ENGINE, "get_active_window_info", return_value={"active": True, "title": "Brave Browser"}):
            res = _list_windows()
            assert res["window_count"] == 2
            assert len(res["windows"]) == 2
            assert res["active_window"]["title"] == "Brave Browser"


def test_switch_window_tool_found():
    with patch.object(UIA_ENGINE, "find_window", return_value={"hwnd": 1002, "title": "Settings"}):
        with patch.object(UIA_ENGINE, "focus_window", return_value=True):
            res = _switch_window("Settings")
            assert res["success"] is True
            assert res["window"] == "Settings"


def test_switch_window_tool_not_found():
    with patch.object(UIA_ENGINE, "find_window", return_value=None):
        res = _switch_window("Photoshop")
        assert res["success"] is False
        assert "not found" in res["reason"]


def test_close_window_tool():
    with patch.object(UIA_ENGINE, "find_window", return_value={"hwnd": 1002, "title": "Calculator"}):
        with patch.object(UIA_ENGINE, "close_window", return_value=True):
            res = _close_window("Calculator")
            assert res["success"] is True
            assert res["closed_window"] == "Calculator"


def test_inspect_ui_tree_tool():
    mock_tree = {
        "element_count": 3,
        "elements": [
            {"type": "ButtonControl", "name": "Save"},
            {"type": "ButtonControl", "name": "Cancel"},
        ],
    }
    with patch.object(UIA_ENGINE, "find_window", return_value={"hwnd": 1001, "title": "Notepad"}):
        with patch.object(UIA_ENGINE, "inspect_ui_tree", return_value=mock_tree):
            res = _inspect_ui_tree(window_query="Notepad")
            assert res["element_count"] == 3
            assert len(res["elements"]) == 2


def test_ui_action_tool_invoke():
    mock_res = {"success": True, "method": "InvokePattern", "element": "Submit"}
    with patch.object(UIA_ENGINE, "execute_ui_action", return_value=mock_res):
        res = _ui_action(target_element="Submit", action="invoke")
        assert res["success"] is True
        assert res["method"] == "InvokePattern"


def test_list_browser_tabs_tool():
    mock_tabs = [
        {"title": "Claude", "selected": True},
        {"title": "GitHub", "selected": False},
    ]
    with patch.object(UIA_ENGINE, "list_browser_tabs", return_value=mock_tabs):
        res = _list_browser_tabs(browser_name="Brave")
        assert res["browser"] == "Brave"
        assert res["tab_count"] == 2
        assert res["tabs"][0]["title"] == "Claude"


def test_switch_browser_tab_tool():
    mock_res = {"success": True, "switched_to": "GitHub", "browser": "Brave"}
    with patch.object(UIA_ENGINE, "switch_browser_tab", return_value=mock_res):
        res = _switch_browser_tab(tab_name="GitHub", browser_name="Brave")
        assert res["success"] is True
        assert res["switched_to"] == "GitHub"
