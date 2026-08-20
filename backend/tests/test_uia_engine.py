from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from app.tools.uia_engine import UIAutomationEngine


class MockRect:
    def __init__(self, left=10, top=20, right=110, bottom=70):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class MockUIAElement:
    def __init__(
        self,
        name: str = "",
        control_type: str = "ButtonControl",
        automation_id: str = "",
        children: list[MockUIAElement] | None = None,
        patterns: dict[str, Any] | None = None,
    ):
        self.Name = name
        self.ControlTypeName = control_type
        self.AutomationId = automation_id
        self.BoundingRectangle = MockRect()
        self._children = children or []
        self._patterns = patterns or {}

    def GetChildren(self):
        return self._children

    def GetInvokePattern(self):
        return self._patterns.get("invoke")

    def GetValuePattern(self):
        return self._patterns.get("value")

    def GetTogglePattern(self):
        return self._patterns.get("toggle")

    def GetSelectionItemPattern(self):
        return self._patterns.get("selection_item")

    def GetExpandCollapsePattern(self):
        return self._patterns.get("expand_collapse")

    def Click(self):
        pass

    def SetFocus(self):
        pass


@pytest.fixture
def uia_engine():
    engine = UIAutomationEngine()
    engine.is_windows = True
    return engine


# 1. Semantic element finding & scoring
def test_find_ui_elements_exact_match(uia_engine):
    btn1 = MockUIAElement(name="Save File", control_type="ButtonControl")
    btn2 = MockUIAElement(name="Cancel", control_type="ButtonControl")
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[btn1, btn2])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        matches = uia_engine.find_ui_elements(name="Save File")
        assert len(matches) >= 1
        assert matches[0][0] == btn1
        assert matches[0][1] >= 0.95


def test_find_ui_elements_case_insensitive_and_substring(uia_engine):
    btn = MockUIAElement(name="Settings and Preferences", control_type="ButtonControl")
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[btn])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        matches = uia_engine.find_ui_elements(name="settings")
        assert len(matches) >= 1
        assert matches[0][0] == btn
        assert matches[0][1] >= 0.8


def test_find_ui_element_ambiguity_guard(uia_engine):
    btn1 = MockUIAElement(name="Save Document A", control_type="ButtonControl")
    btn2 = MockUIAElement(name="Save Document B", control_type="ButtonControl")
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[btn1, btn2])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        elem, err = uia_engine.find_ui_element(name="Save Document")
        assert elem is None
        assert "ambiguous" in err.lower()


def test_find_ui_element_missing_returns_error(uia_engine):
    btn = MockUIAElement(name="Submit", control_type="ButtonControl")
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[btn])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        elem, err = uia_engine.find_ui_element(name="Delete Account")
        assert elem is None
        assert "no ui element found" in err.lower()


# 2. Pattern Invocations
def test_execute_ui_action_invoke_pattern(uia_engine):
    mock_inv = MagicMock()
    btn = MockUIAElement(name="Save", control_type="ButtonControl", patterns={"invoke": mock_inv})
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[btn])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        res = uia_engine.execute_ui_action(target_name="Save", action="invoke")
        assert res["success"] is True
        assert res["method"] == "InvokePattern"
        mock_inv.Invoke.assert_called_once()


def test_execute_ui_action_value_pattern(uia_engine):
    mock_val = MagicMock()
    edit = MockUIAElement(name="Search", control_type="EditControl", patterns={"value": mock_val})
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[edit])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        res = uia_engine.execute_ui_action(target_name="Search", action="set_value", value="Hello World")
        assert res["success"] is True
        assert res["method"] == "ValuePattern"
        mock_val.SetValue.assert_called_once_with("Hello World")


def test_execute_ui_action_toggle_pattern(uia_engine):
    mock_tog = MagicMock()
    chk = MockUIAElement(name="Enable Dark Mode", control_type="CheckBoxControl", patterns={"toggle": mock_tog})
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[chk])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        res = uia_engine.execute_ui_action(target_name="Enable Dark Mode", action="toggle")
        assert res["success"] is True
        assert res["method"] == "TogglePattern"
        mock_tog.Toggle.assert_called_once()


def test_execute_ui_action_selection_item_pattern(uia_engine):
    mock_sel = MagicMock()
    tab = MockUIAElement(name="General Settings", control_type="TabItemControl", patterns={"selection_item": mock_sel})
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[tab])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        res = uia_engine.execute_ui_action(target_name="General Settings", action="select")
        assert res["success"] is True
        assert res["method"] == "SelectionItemPattern"
        mock_sel.Select.assert_called_once()


def test_execute_ui_action_expand_collapse_pattern(uia_engine):
    mock_exp = MagicMock()
    combo = MockUIAElement(name="Font Size", control_type="ComboBoxControl", patterns={"expand_collapse": mock_exp})
    root = MockUIAElement(name="Root", control_type="PaneControl", children=[combo])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        res_exp = uia_engine.execute_ui_action(target_name="Font Size", action="expand")
        assert res_exp["success"] is True
        mock_exp.Expand.assert_called_once()

        res_col = uia_engine.execute_ui_action(target_name="Font Size", action="collapse")
        assert res_col["success"] is True
        mock_exp.Collapse.assert_called_once()


# 3. UI Tree Inspection
def test_inspect_ui_tree_pruning_and_depth(uia_engine):
    child1 = MockUIAElement(name="Button 1", control_type="ButtonControl")
    child2 = MockUIAElement(name="Edit 1", control_type="EditControl")
    group = MockUIAElement(name="Header Group", control_type="GroupControl", children=[child1, child2])
    root = MockUIAElement(name="App Window", control_type="WindowControl", children=[group])

    with patch.object(uia_engine, "_get_root_control", return_value=root):
        res = uia_engine.inspect_ui_tree(max_depth=3)
        assert "elements" in res
        assert res["element_count"] >= 3
        names = [e["name"] for e in res["elements"]]
        assert "Button 1" in names
        assert "Edit 1" in names


# 4. Browser Tabs Listing & Switching
def test_list_browser_tabs_via_uia(uia_engine):
    mock_sel1 = MagicMock(IsSelected=True)
    mock_sel2 = MagicMock(IsSelected=False)
    tab1 = MockUIAElement(name="Claude", control_type="TabItemControl", patterns={"selection_item": mock_sel1})
    tab2 = MockUIAElement(name="Gmail", control_type="TabItemControl", patterns={"selection_item": mock_sel2})
    tab_ctrl = MockUIAElement(name="Tab Strip", control_type="TabControl", children=[tab1, tab2])
    root = MockUIAElement(name="Brave", control_type="PaneControl", children=[tab_ctrl])

    with patch.object(uia_engine, "find_window", return_value={"hwnd": 1234, "title": "Brave"}):
        with patch.object(uia_engine, "_get_root_control", return_value=root):
            tabs = uia_engine.list_browser_tabs(browser_name="Brave")
            assert len(tabs) == 2
            assert tabs[0]["title"] == "Claude"
            assert tabs[0]["selected"] is True
            assert tabs[1]["title"] == "Gmail"
            assert tabs[1]["selected"] is False


def test_switch_browser_tab_via_uia(uia_engine):
    mock_sel = MagicMock()
    tab = MockUIAElement(name="Gmail - Inbox", control_type="TabItemControl", patterns={"selection_item": mock_sel})
    root = MockUIAElement(name="Brave", control_type="PaneControl", children=[tab])

    with patch.object(uia_engine, "find_window", return_value={"hwnd": 1234, "title": "Brave"}):
        with patch.object(uia_engine, "focus_window", return_value=True):
            with patch.object(uia_engine, "_get_root_control", return_value=root):
                res = uia_engine.switch_browser_tab(tab_query="Gmail", browser_name="Brave")
                assert res["success"] is True
                assert "Gmail - Inbox" in res["switched_to"]
                mock_sel.Select.assert_called_once()
