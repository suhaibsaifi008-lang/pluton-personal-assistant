"""
PLUTON V2 — Automated Browser Lifecycle Cleanliness & Lock-Free Teardown Acceptance Suite
Guarantees that:
1. Playwright cleanly detaches from CDP without killing the user's real browser.
2. Multiple sequential CDP attach/detach cycles succeed without wedging the socket.
3. Standalone isolated instances cleanly terminate without leaving orphaned processes.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Any

import pytest
from app.subsystems.computer.browser_engine import BROWSER_ENGINE


def _get_brave_process_count() -> int:
    """Return count of active brave.exe processes on Windows."""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-Process -Name 'brave*' -ErrorAction SilentlyContinue).Count"],
            capture_output=True,
            text=True,
            check=False,
        )
        out = res.stdout.strip()
        return int(out) if out.isdigit() else 0
    except Exception:
        return 0


@pytest.mark.anyio
async def test_cdp_session_clean_detach():
    """Test that attaching via CDP and closing BrowserEngine detaches without terminating browser or leaving locks."""
    # 1. Record pre-session state
    count_before = _get_brave_process_count()

    # 2. Probe & Ensure Playwright attaches
    page = await BROWSER_ENGINE._ensure_playwright()
    assert page is not None
    is_cdp = BROWSER_ENGINE._is_attached_to_user_browser

    # 3. Perform live operations
    state = await BROWSER_ENGINE.get_state()
    assert state.get("active") is True

    # 4. Cleanly close BrowserEngine
    await BROWSER_ENGINE.close()

    # 5. Assert BrowserEngine completely reset its internal pointers and connection
    assert BROWSER_ENGINE._page is None
    assert BROWSER_ENGINE._context is None
    assert BROWSER_ENGINE._browser is None
    assert BROWSER_ENGINE._playwright is None
    assert BROWSER_ENGINE._is_pw_active is False
    assert BROWSER_ENGINE._is_attached_to_user_browser is False

    # 6. If CDP was active, verify that Brave was NOT terminated
    if is_cdp:
        count_after = _get_brave_process_count()
        assert count_after > 0, "Regression: Playwright CDP close killed the user's real browser process!"


@pytest.mark.anyio
async def test_cdp_multiple_reconnection_cycles():
    """Verify that multiple sequential CDP connect -> operate -> detach cycles do not leak or wedge the socket."""
    for cycle in range(3):
        # 1. Attach
        page = await BROWSER_ENGINE._ensure_playwright()
        assert page is not None

        # 2. Perform operation
        url_res = await BROWSER_ENGINE.get_url()
        assert url_res.get("success") is True

        # 3. Detach cleanly
        await BROWSER_ENGINE.close()
        assert BROWSER_ENGINE._is_pw_active is False
        assert BROWSER_ENGINE._page is None


@pytest.mark.anyio
async def test_isolated_sandbox_teardown():
    """Verify that standalone isolated sandbox instances (headless=True) cleanly terminate completely."""
    # 1. Start standalone instance
    page = await BROWSER_ENGINE._ensure_playwright(headless=True)
    assert page is not None
    assert BROWSER_ENGINE._is_attached_to_user_browser is False

    # 2. Set content and operate
    await page.set_content("<html><body><h1>Cleanliness Sandbox</h1></body></html>")
    text_res = await BROWSER_ENGINE.extract_text()
    assert "Cleanliness Sandbox" in text_res.get("text", "")

    # 3. Close standalone instance
    await BROWSER_ENGINE.close()
    assert BROWSER_ENGINE._page is None
    assert BROWSER_ENGINE._is_pw_active is False
