import pytest
from unittest.mock import MagicMock, patch
from app.tools import computer as computer_module
from app.tools.computer import (
    _match_tab_element,
    _close_tab_cdp,
    _close_tab_via_uia,
    _close_browser_tab,
)


class MockTabItem:
    def __init__(self, name: str, is_invokable: bool = True):
        self.Name = name
        self.ControlTypeName = "TabItemControl"
        self._is_invokable = is_invokable
        self._children = []
        if is_invokable:
            mock_close = MagicMock()
            mock_close.Name = "Close"
            mock_close.ControlTypeName = "ButtonControl"
            mock_pat = MagicMock()
            mock_close.GetInvokePattern = MagicMock(return_value=mock_pat)
            self._children = [mock_close]

    def GetChildren(self):
        return self._children

    def GetInvokePattern(self):
        return MagicMock() if self._is_invokable else None


# 1. Exact tab title matching
def test_exact_tab_title_matching():
    tabs = [
        MockTabItem("Claude"),
        MockTabItem("Pluton AI Progress"),
        MockTabItem("127.0.0.1:5173"),
    ]
    matched = _match_tab_element(tabs, "Claude")
    assert matched is not None
    assert matched.Name == "Claude"


# 2. Case-insensitive matching
def test_case_insensitive_matching():
    tabs = [
        MockTabItem("Building a Jarvis-like AI for PC - Claude"),
        MockTabItem("Pluton AI Progress"),
    ]
    matched = _match_tab_element(tabs, "claude")
    assert matched is not None
    assert matched.Name == "Building a Jarvis-like AI for PC - Claude"


# 3. Substring matching
def test_substring_matching():
    tabs = [
        MockTabItem("Building a Jarvis-like AI for PC - Claude"),
        MockTabItem("API Keys - GroqCloud"),
    ]
    matched = _match_tab_element(tabs, "Jarvis-like AI")
    assert matched is not None
    assert matched.Name == "Building a Jarvis-like AI for PC - Claude"


# 4. Truncated title matching
def test_truncated_title_matching():
    tabs = [
        MockTabItem("Build... - Claude"),
        MockTabItem("Pluton AI Progress"),
    ]
    matched = _match_tab_element(tabs, "Building a Jarvis")
    assert matched is not None
    assert matched.Name == "Build... - Claude"


# 5. Multiple similar tabs
def test_multiple_similar_tabs_matches_most_specific():
    tabs = [
        MockTabItem("Claude - General Chat"),
        MockTabItem("Claude - Coding Project"),
    ]
    matched = _match_tab_element(tabs, "Coding Project")
    assert matched is not None
    assert matched.Name == "Claude - Coding Project"


# 6. Requested tab absent
def test_requested_tab_absent_returns_none():
    tabs = [
        MockTabItem("Pluton AI Progress"),
        MockTabItem("127.0.0.1:5173"),
    ]
    matched = _match_tab_element(tabs, "YouTube")
    assert matched is None


# 7. Browser not running safely handles None hwnd
def test_browser_not_running(monkeypatch):
    monkeypatch.setattr(computer_module, "_find_browser_hwnd", lambda *a: None)
    res = _close_tab_via_uia("Claude", "Brave")
    assert res is None


# 8. UI Automation unavailable falls back safely
def test_uia_unavailable_returns_none(monkeypatch):
    monkeypatch.setattr(computer_module, "_find_browser_hwnd", lambda *a: 12345)
    monkeypatch.setattr(computer_module, "_get_browser_tabs_uia", lambda *a: [])
    res = _close_tab_via_uia("Claude", "Brave")
    assert res is None


# 9. CDP unavailable returns None
def test_cdp_unavailable_returns_none(monkeypatch):
    with patch("httpx.get", side_effect=Exception("Connection refused")):
        res = _close_tab_cdp("Claude", "Brave")
        assert res is None


# 10. Safe fallback: CDP -> UIA
def test_safe_fallback_cdp_to_uia(monkeypatch):
    tab = MockTabItem("Building a Jarvis-like AI for PC - Claude")
    monkeypatch.setattr(computer_module, "_close_tab_cdp", lambda *a, **k: None)
    monkeypatch.setattr(computer_module, "_find_browser_hwnd", lambda *a: 12345)
    monkeypatch.setattr(computer_module, "_focus_window_by_title_keyword", lambda *a: True)

    # Initial tabs contain Claude, post-action tabs do not
    call_count = [0]

    def mock_get_tabs(hwnd):
        call_count[0] += 1
        if call_count[0] == 1:
            return [tab]
        return [MockTabItem("Pluton AI Progress")]

    monkeypatch.setattr(computer_module, "_get_browser_tabs_uia", mock_get_tabs)

    res = _close_browser_tab(tab_name="Claude", browser_name="Brave")
    assert res["success"] is True
    assert res["method"] == "ui_automation"
    assert res["closed_tab"] == "Building a Jarvis-like AI for PC - Claude"


# 11. Never closing the wrong tab: tab absent in UIA fails safely
def test_never_close_wrong_tab_when_target_absent(monkeypatch):
    import json
    from app.providers.base import ProviderResponse
    other_tab = MockTabItem("Pluton AI Progress")
    monkeypatch.setattr(computer_module, "_close_tab_cdp", lambda *a, **k: None)
    monkeypatch.setattr(computer_module, "_find_browser_hwnd", lambda *a: 12345)
    monkeypatch.setattr(computer_module, "_focus_window_by_title_keyword", lambda *a: True)
    monkeypatch.setattr(computer_module, "_get_browser_tabs_uia", lambda *a: [other_tab])
    monkeypatch.setattr(computer_module, "_screenshot", lambda: {"captured": True, "path": "test.png", "width": 1920, "height": 1080})

    from unittest.mock import AsyncMock
    fake_provider = MagicMock()
    fake_provider.supports_vision = True
    fake_provider.name = "fake"
    fake_provider.respond = AsyncMock(return_value=ProviderResponse(response_id="r1", text=json.dumps({"found": False, "reason": "Tab 'Claude' not found among visible browser tabs"})))
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)


    monkeypatch.setattr("PIL.Image.open", lambda *a: MagicMock(crop=lambda *c: MagicMock(save=lambda *s: None)))

    res = _close_browser_tab(tab_name="Claude", browser_name="Brave")
    assert res["success"] is False
    assert res["failed_step"] == "locate"
    assert "not found" in res["reason"].lower()



# 12. Full end-to-end UIA closure verification
def test_e2e_uia_closure_success(monkeypatch):
    claude_tab = MockTabItem("Building a Jarvis-like AI for PC - Claude")
    pluton_tab = MockTabItem("Pluton AI Progress")

    monkeypatch.setattr(computer_module, "_find_browser_hwnd", lambda *a: 12345)
    monkeypatch.setattr(computer_module, "_focus_window_by_title_keyword", lambda *a: True)

    calls = [0]
    def mock_tabs(hwnd):
        calls[0] += 1
        return [claude_tab, pluton_tab] if calls[0] == 1 else [pluton_tab]

    monkeypatch.setattr(computer_module, "_get_browser_tabs_uia", mock_tabs)

    res = _close_tab_via_uia("Claude", "Brave")
    assert res is not None
    assert res["success"] is True
    assert res["closed_tab"] == "Building a Jarvis-like AI for PC - Claude"
    assert res["remaining_tabs"] == ["Pluton AI Progress"]
