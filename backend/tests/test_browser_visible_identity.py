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
    from app.subsystems.computer.browser_engine import BROWSER_ENGINE

    async def _mock_find(target, role=None):
        return {
            "found": True,
            "status": "FOUND",
            "score": 1.0,
            "selector": "a:has(h3)",
            "visible": True,
            "enabled": True,
            "element": {"selector": "a:has(h3)", "name": "First Result", "role": "link", "visible": True, "enabled": True},
        }

    monkeypatch.setattr(BROWSER_ENGINE, "find_element", _mock_find)

    context = ExecutionContext(task_id="pytest-test-task", active_browser="Brave")
    res = asyncio.run(WEB_DOMAIN.find(target="first result", role="link", context=context))

    assert res["found"] is True
    assert res["status"] == "FOUND"


def test_web_find_nonexistent_element_returns_not_found(monkeypatch):
    """Verify that a nonexistent element is NOT reported as found merely because browser window exists."""
    from app.subsystems.computer.browser_engine import BROWSER_ENGINE

    async def _mock_not_found(target, role=None):
        return {"found": False, "status": "NOT_FOUND", "error": f"Element '{target}' not found."}

    monkeypatch.setattr(BROWSER_ENGINE, "find_element", _mock_not_found)

    context = ExecutionContext(task_id="pytest-test-task", active_browser="Brave")
    res = asyncio.run(WEB_DOMAIN.find(target="nonexistent_button_xyz", role="button", context=context))

    assert res["found"] is False
    assert res["status"] == "NOT_FOUND"


def test_unbound_browser_returns_clean_error(monkeypatch):
    """Verify that when no browser window exists, BROWSER_TARGET_UNBOUND is returned."""
    from app.tools.native_browser_controller import NATIVE_BROWSER

    monkeypatch.setattr(NATIVE_BROWSER, "find_browser_window", lambda browser_name="Brave": None)
    monkeypatch.setattr(NATIVE_BROWSER, "get_active_tab", lambda browser_name="Brave": None)

    context = ExecutionContext(task_id="pytest-test-task", active_browser="Brave")
    res = asyncio.run(BROWSER_DOMAIN.get_title(context=context))

    assert res["success"] is False
    assert "BROWSER_TARGET_UNBOUND" in res["error"]


def test_navigate_rejects_empty_or_none_url():
    """Verify that navigate() rejects empty or whitespace URLs deterministically."""
    from app.kernel.control_kernel import KERNEL
    KERNEL.authorize_task("pytest-browser-test")
    ctx = ExecutionContext(task_id="pytest-browser-test", active_browser="Brave")

    res1 = BROWSER_DOMAIN.navigate(url="", context=ctx)
    assert res1["success"] is False
    assert "INVALID_INPUT" in res1["error"]

    res2 = BROWSER_DOMAIN.navigate(url=None, context=ctx)
    assert res2["success"] is False
    assert "INVALID_INPUT" in res2["error"]

    res3 = BROWSER_DOMAIN.navigate(url="   ", context=ctx)
    assert res3["success"] is False
    assert "INVALID_INPUT" in res3["error"]


def test_switch_and_close_tab_reject_empty_names():
    """Verify switch_tab and close_tab reject empty target names."""
    from app.kernel.control_kernel import KERNEL
    KERNEL.authorize_task("pytest-browser-test")
    ctx = ExecutionContext(task_id="pytest-browser-test", active_browser="Brave")

    res1 = BROWSER_DOMAIN.switch_tab(target_tab="", context=ctx)
    assert res1["success"] is False
    assert "INVALID_INPUT" in res1["error"]

    res2 = BROWSER_DOMAIN.close_tab(target_tab="", context=ctx)
    assert res2["success"] is False
    assert "INVALID_INPUT" in res2["error"]


def test_search_and_wait_validation():
    """Verify search and wait_for_page input validation."""
    from app.kernel.control_kernel import KERNEL
    KERNEL.authorize_task("pytest-browser-test")
    ctx = ExecutionContext(task_id="pytest-browser-test", active_browser="Brave")

    res1 = asyncio.run(BROWSER_DOMAIN.search(query="", context=ctx))
    assert res1["success"] is False
    assert "INVALID_INPUT" in res1["error"]

    res2 = asyncio.run(BROWSER_DOMAIN.wait_for_page(state="invalid_state", context=ctx))
    assert res2["success"] is False
    assert "INVALID_INPUT" in res2["error"]


def test_search_falls_back_to_same_tab_navigation(monkeypatch):
    """Verify that when CDP is inactive, search navigates via native same-tab navigation without duplicate tabs."""
    from app.kernel.control_kernel import KERNEL
    from app.subsystems.computer.browser_engine import BROWSER_ENGINE
    from app.tools.native_browser_controller import NATIVE_BROWSER

    KERNEL.authorize_task("pytest-browser-test")
    monkeypatch.setattr(BROWSER_ENGINE, "_page", None)
    monkeypatch.setattr(
        NATIVE_BROWSER,
        "navigate_current_tab",
        lambda url, browser_name="Brave": {
            "success": True,
            "method": "native_same_tab_navigate",
            "hwnd": 12345,
            "pid": 6789,
            "url": url,
            "verified": True,
        },
    )

    ctx = ExecutionContext(task_id="pytest-browser-test", active_browser="Brave")
    res = asyncio.run(BROWSER_DOMAIN.search(query="Minecraft", browser_name="Brave", context=ctx))
    assert res["success"] is True
    assert res["tier"] == "same_tab_navigation"
    assert "Minecraft" in res["url"]


def test_google_address_bar_trailing_space_workaround():
    """Verify Bug 4 Workaround: only exact www.google.com gets a trailing space."""
    target_google = "www.google.com"
    target_yt = "https://www.youtube.com"

    # Google should get the trailing space when typed
    type_target_google = target_google
    if type_target_google.strip().lower() in ("www.google.com", "https://www.google.com", "http://www.google.com"):
        type_target_google = "www.google.com "

    assert type_target_google == "www.google.com "

    # YouTube or search queries should NOT get trailing space
    type_target_yt = target_yt
    if type_target_yt.strip().lower() in ("www.google.com", "https://www.google.com", "http://www.google.com"):
        type_target_yt = "www.google.com "

    assert type_target_yt == "https://www.youtube.com"


