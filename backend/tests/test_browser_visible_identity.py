"""
Tests for PLUTON V2 Visible Browser Identity & Verification Invariants.
Verifies:
- Visible tab identity tracking (BrowserTabIdentity)
- Mismatched visible tab fails verification
- browser.get_title reads from active visible browser tab
- web.find resolves against active visible browser tab
- BROWSER_TARGET_UNBOUND returned when browser is not running
"""

import asyncio
from app.core.contracts import (
    BrowserTabIdentity,
    ExecutionContext,
    VerificationStrategy,
)
from app.subsystems.computer.domains.browser import BROWSER_DOMAIN
from app.subsystems.computer.domains.web import WEB_DOMAIN
from app.verification.verification_engine import VERIFICATION_ENGINE


def test_browser_tab_identity_model():
    """Verify BrowserTabIdentity contains all required canonical tracking fields."""
    ident = BrowserTabIdentity(
        browser_name="Brave",
        browser_pid=1234,
        browser_hwnd=5678,
        tab_index=2,
        tab_title="Gmail - Google Search",
        tab_url="https://www.google.com/search?q=Gmail",
        is_active=True,
        identity_status="MATCHED",
    )
    assert ident.browser_name == "Brave"
    assert ident.browser_pid == 1234
    assert ident.browser_hwnd == 5678
    assert ident.tab_index == 2
    assert ident.identity_status == "MATCHED"


def test_mismatched_visible_tab_fails_verification(monkeypatch):
    """Verify that if the visible browser tab does not match expected state, verification fails."""
    from app.tools.native_browser_controller import NATIVE_BROWSER

    monkeypatch.setattr(
        NATIVE_BROWSER,
        "get_active_tab",
        lambda browser_name="Brave": {
            "browser": "Brave",
            "hwnd": 722796,
            "tab_index": 2,
            "title": "127.0.0.1:5173 - Pluton AI",
            "selected": True,
        },
    )

    res = VERIFICATION_ENGINE.verify_action(
        strategy=VerificationStrategy.BROWSER_TITLE_MATCH,
        target="Gmail",
        expected_state="Gmail",
        metadata={"browser": "Brave"},
        timeout_seconds=0.5,
    )
    assert res.verified is False
    assert "not found" in res.message.lower()


def test_browser_get_title_reads_active_visible_tab(monkeypatch):
    """Verify that browser.get_title reads the title directly from the visible active tab."""
    from app.tools.native_browser_controller import NATIVE_BROWSER

    monkeypatch.setattr(
        NATIVE_BROWSER,
        "get_active_tab",
        lambda browser_name="Brave": {
            "browser": "Brave",
            "hwnd": 722796,
            "pid": 23640,
            "tab_index": 5,
            "title": "Inbox (6) - heenasaifi.0091@gmail.com - Gmail - Memory usage - 193 MB",
            "selected": True,
        },
    )

    context = ExecutionContext(task_id="pytest-test-task", active_browser="Brave")
    res = asyncio.run(BROWSER_DOMAIN.get_title(context=context))

    assert res["success"] is True
    assert "Inbox (6) - heenasaifi.0091@gmail.com - Gmail" in res["title"]
    assert res["identity_status"] == "MATCHED"
    assert res["browser_hwnd"] == 722796


def test_web_find_first_result_resolves_cleanly(monkeypatch):
    """Verify that web.find('first result') resolves cleanly against active browser."""
    from app.tools.native_browser_controller import NATIVE_BROWSER

    monkeypatch.setattr(
        NATIVE_BROWSER,
        "get_active_tab",
        lambda browser_name="Brave": {
            "browser": "Brave",
            "hwnd": 722796,
            "tab_index": 5,
            "title": "Gmail - Google Search",
            "selected": True,
        },
    )

    context = ExecutionContext(task_id="pytest-test-task", active_browser="Brave")
    res = asyncio.run(WEB_DOMAIN.find(target="first result", role="link", context=context))

    assert res["found"] is True
    assert res["status"] == "FOUND"
    assert res["identity_status"] == "MATCHED"


def test_unbound_browser_returns_clean_error(monkeypatch):
    """Verify that when no browser window exists, BROWSER_TARGET_UNBOUND is returned."""
    from app.tools.native_browser_controller import NATIVE_BROWSER

    monkeypatch.setattr(NATIVE_BROWSER, "find_browser_window", lambda browser_name="Brave": None)
    monkeypatch.setattr(NATIVE_BROWSER, "get_active_tab", lambda browser_name="Brave": None)

    context = ExecutionContext(task_id="pytest-test-task", active_browser="Brave")
    res = asyncio.run(BROWSER_DOMAIN.get_title(context=context))

    assert res["success"] is False
    assert "BROWSER_TARGET_UNBOUND" in res["error"]
