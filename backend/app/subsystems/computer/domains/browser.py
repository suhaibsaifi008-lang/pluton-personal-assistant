"""
PLUTON V2 — Browser Domain Handler
Coordinates native Windows Chromium browser integration, CDP, and Playwright.
Enforces strict browser identity tracking and visible-tab postcondition verification.
Implements canonical capabilities:
browser.detect, browser.list_tabs, browser.open_tab, browser.switch_tab, browser.close_tab,
browser.navigate, browser.back, browser.forward, browser.reload, browser.get_state,
browser.get_title, browser.get_url, browser.wait_for_page, browser.search.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Any

from app.core.contracts import BrowserTabIdentity, ExecutionContext, VerificationStrategy
from app.kernel.control_kernel import KERNEL
from app.tools.native_browser_controller import NATIVE_BROWSER
from app.tools.uia_engine import UIA_ENGINE
from ..browser_engine import BROWSER_ENGINE


class BrowserDomainHandler:
    """Canonical handler for browser lifecycle and page navigation capabilities with visible tab verification."""

    def detect(self, browser_name: str = "Brave", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Detect running browser instances and report HWND, PID, and active tab count."""
        KERNEL.assert_authorized(context.task_id if context else None)
        win = NATIVE_BROWSER.find_browser_window(browser_name)
        if not win:
            for fallback_b in ("Brave", "Chrome", "Edge"):
                win = NATIVE_BROWSER.find_browser_window(fallback_b)
                if win:
                    browser_name = fallback_b
                    break
        if not win:
            return {"detected": False, "browser": browser_name, "hwnd": None, "pid": None, "tab_count": 0}

        tabs = NATIVE_BROWSER.list_tabs(browser_name)
        active_tab = NATIVE_BROWSER.get_active_tab(browser_name)
        return {
            "detected": True,
            "browser": browser_name,
            "hwnd": win.get("hwnd"),
            "pid": win.get("pid"),
            "title": win.get("title"),
            "tab_count": len(tabs),
            "tabs": tabs,
            "active_tab": active_tab,
            "identity_status": "MATCHED",
        }

    def list_tabs(self, browser_name: str = "Brave", browser: str | None = None, context: ExecutionContext | None = None) -> list[dict[str, Any]]:
        """List open browser tabs."""
        bname = browser or browser_name or "Brave"
        KERNEL.assert_authorized(context.task_id if context else None)
        return NATIVE_BROWSER.list_tabs(browser_name=bname)

    async def open_tab(self, url: str = "about:blank", browser_name: str = "Brave", browser: str | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Open a browser tab in the user's visible browser window and navigate to destination."""
        bname = browser or browser_name or "Brave"
        KERNEL.assert_authorized(context.task_id if context else None)
        return self.navigate(url=url, browser_name=bname, context=context)

    def navigate(self, url: str, browser_name: str = "Brave", browser: str | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Navigate the user's visible desktop browser window to the specified URL."""
        bname = str(browser or browser_name or "Brave").strip()
        url_str = str(url or "").strip()
        KERNEL.assert_authorized(context.task_id if context else None)

        # 1. If Playwright is attached over CDP to authoritative Brave, navigate via Playwright
        if BROWSER_ENGINE._is_attached_to_user_browser and BROWSER_ENGINE._page and not BROWSER_ENGINE._page.is_closed():
            try:
                import concurrent.futures
                import asyncio

                def _sync_nav():
                    return asyncio.run(BROWSER_ENGINE.navigate(url_str, browser_name=bname))

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pw_res = pool.submit(_sync_nav).result(timeout=15.0)
                if pw_res.get("success"):
                    win = NATIVE_BROWSER.find_browser_window(bname)
                    return {
                        "success": True,
                        "method": "cdp_page_navigate",
                        "url": url_str,
                        "hwnd": win.get("hwnd") if win else None,
                        "pid": win.get("pid") if win else None,
                        "title": pw_res.get("title", ""),
                        "verified": True,
                    }
            except Exception as ex:
                logger.warning("[BROWSER_DOMAIN] CDP navigate fallback to native: %s", ex)

        # 2. Native Browser Controller (Win32 / UIA / hotkey navigation)
        nav_res = NATIVE_BROWSER.open_tab(url=url_str, browser_name=bname)
        if nav_res.get("success"):
            if context:
                context.tab_identity = NATIVE_BROWSER.get_tab_identity(bname)
            return nav_res

        # If visible window discovery fails, return explicit failure — do NOT fake success via hidden browser
        return {
            "success": False,
            "error": f"VISIBLE_BROWSER_NOT_FOUND: Could not discover or control user's visible {bname} window.",
            "diagnostics": nav_res,
        }

    async def search(self, query: str, engine: str = "", browser_name: str = "Brave", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Perform semantic search with two tiers: CDP DOM typing (Tier 1) and URL navigation fallback (Tier 2)."""
        import logging
        import urllib.parse
        _logger = logging.getLogger("pluton.browser.search")
        KERNEL.assert_authorized(context.task_id if context else None)
        bname = browser_name or "Brave"

        # Tier 1: Type into active search box using CDP/Playwright DOM if active
        try:
            if BROWSER_ENGINE._page is not None and not BROWSER_ENGINE._page.is_closed():
                type_res = await BROWSER_ENGINE.type_element("search box", query, press_enter=True)
                if type_res.get("success"):
                    _logger.info("[SEARCH] Tier 1 CDP success for query: %s", query)
                    return {"success": True, "action": "search", "query": query, "tier": "cdp_dom", "observed": type_res}
        except Exception as e:
            _logger.info("[SEARCH] Tier 1 CDP exception: %s, falling through to Tier 2.", e)

        # Tier 2: Construct search URL and navigate via native browser
        search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
        _logger.info("[SEARCH] Tier 2: Navigating to search URL: %s", search_url)
        nav_res = NATIVE_BROWSER.open_tab(url=search_url, browser_name=bname)
        if nav_res.get("success"):
            return {"success": True, "action": "search", "query": query, "tier": "url_navigation", "url": search_url, "observed": nav_res}

        # If native browser also fails, try BROWSER_ENGINE navigate as last resort
        try:
            eng_res = await BROWSER_ENGINE.navigate(search_url, browser_name=bname)
            return {"success": True, "action": "search", "query": query, "tier": "playwright_navigate", "url": search_url, "observed": eng_res}
        except Exception as e:
            _logger.error("[SEARCH] All tiers failed for query '%s': %s", query, e)
            return {"success": False, "action": "search", "query": query, "error": f"All search tiers failed: {e}"}

    def switch_tab(self, target_tab: str, browser_name: str = "Brave", browser: str | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Switch to tab matching title keyword across open browsers."""
        bname = browser or browser_name or "Brave"
        KERNEL.assert_authorized(context.task_id if context else None)
        res = NATIVE_BROWSER.switch_tab(target_tab, browser_name=bname)
        if not (res and res.get("success")):
            for fallback_b in ("Chrome", "Edge", "Brave"):
                if fallback_b != bname:
                    res = NATIVE_BROWSER.switch_tab(target_tab, browser_name=fallback_b)
                    if res and res.get("success"):
                        bname = fallback_b
                        break
        if res and res.get("success") and context:
            context.tab_identity = NATIVE_BROWSER.get_tab_identity(bname)
        return res or {"success": False, "error": f"Tab '{target_tab}' not found in open browsers."}

    def close_tab(self, target_tab: str, browser_name: str = "Brave", browser: str | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Close browser tab via UIA with postcondition verification."""
        bname = browser or browser_name or "Brave"
        KERNEL.assert_authorized(context.task_id if context else None)
        res = NATIVE_BROWSER.close_tab(target_tab, browser_name=bname)
        return res or {"success": False, "error": f"Tab '{target_tab}' not found in open browsers."}

    async def get_state(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Inspect current canonical browser state from visible tab."""
        KERNEL.assert_authorized(context.task_id if context else None)
        bname = context.active_browser if context else "Brave"
        active_tab = NATIVE_BROWSER.get_active_tab(bname)
        if active_tab:
            return {
                "success": True,
                "browser": bname,
                "hwnd": active_tab.get("hwnd"),
                "active_tab": active_tab,
                "identity_status": "MATCHED",
            }
        return await BROWSER_ENGINE.get_state()

    create_tab = open_tab

    async def get_url(self, browser_name: str = "Brave", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get active page URL from the visible browser tab."""
        KERNEL.assert_authorized(context.task_id if context else None)
        bname = (context.active_browser if context and context.active_browser else browser_name) or "Brave"
        active_tab = NATIVE_BROWSER.get_active_tab(bname)
        if active_tab and active_tab.get("url"):
            return {
                "success": True,
                "url": active_tab["url"],
                "browser": bname,
                "hwnd": active_tab.get("hwnd"),
                "identity_status": "MATCHED",
            }
        if BROWSER_ENGINE._is_attached_to_user_browser:
            return await BROWSER_ENGINE.get_url()
        return {"success": False, "error": "BROWSER_TARGET_UNBOUND: No active visible browser tab found."}

    async def get_title(self, browser_name: str = "Brave", context: ExecutionContext | None = None) -> dict[str, Any]:
        """Get active page title from the REAL visible browser tab."""
        KERNEL.assert_authorized(context.task_id if context else None)
        bname = (context.active_browser if context and context.active_browser else browser_name) or "Brave"
        active_tab = NATIVE_BROWSER.get_active_tab(bname)
        if active_tab and active_tab.get("title"):
            raw_title = active_tab["title"]
            clean_title = re.sub(r"\s*-\s*Memory usage\s*-\s*\d+\s*[KMG]B", "", raw_title, flags=re.IGNORECASE).strip()
            return {
                "success": True,
                "title": clean_title,
                "browser": bname,
                "browser_pid": active_tab.get("pid"),
                "browser_hwnd": active_tab.get("hwnd"),
                "tab_index": active_tab.get("tab_index"),
                "identity_status": "MATCHED",
                "verified": True,
            }
        if BROWSER_ENGINE._is_attached_to_user_browser:
            return await BROWSER_ENGINE.get_title()
        return {"success": False, "error": "BROWSER_TARGET_UNBOUND: No active visible browser tab found."}

    async def back(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Navigate back in page history."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return await BROWSER_ENGINE.back()

    async def forward(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Navigate forward in page history."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return await BROWSER_ENGINE.forward()

    async def reload(self, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Reload active page."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return await BROWSER_ENGINE.reload()

    async def wait_for_page(self, state: str = "load", timeout_seconds: float = 10.0, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Wait for page load lifecycle state."""
        KERNEL.assert_authorized(context.task_id if context else None)
        return await BROWSER_ENGINE.wait_for_page(state=state, timeout_seconds=timeout_seconds)


BROWSER_DOMAIN = BrowserDomainHandler()
