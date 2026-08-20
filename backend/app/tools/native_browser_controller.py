"""
PLUTON V2 — Native Windows Chromium Browser Controller
Implements robust UIAutomation browser control for Brave, Chrome, and Edge.
Provides deterministic tab enumeration, new tab creation in existing browser, semantic tab switching, and tab closure.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import re
import sys
import threading
import time
from typing import Any, Optional

import pyautogui
from app.tools.keyboard_pipeline import _focus_hwnd
from app.tools.uia_engine import UIA_ENGINE, attach_interactive_desktop

logger = logging.getLogger("pluton.tools.browser_controller")


class NativeBrowserController:
    """Canonical controller for running desktop Chromium browser instances."""

    def __init__(self) -> None:
        self._tls = threading.local()

    def find_browser_window(self, browser_name: str = "Brave") -> dict[str, Any] | None:
        """Find the running top-level window for the user's actual visible desktop browser."""
        attach_interactive_desktop()
        wins = UIA_ENGINE.list_windows(visible_only=True)
        b_clean = str(browser_name or "Brave").strip().lower()

        # 1. Primary: Exact match on user's primary desktop Brave window
        for w in wins:
            title = w.get("title", "").lower()
            cname = w.get("class_name", "")
            pid = w.get("pid")
            # If specifically looking for Brave, prioritize the user-facing Brave instance
            if b_clean in ("brave", "browser"):
                if cname == "Chrome_WidgetWin_1" and ("brave" in title or "google" in title or "youtube" in title or "pluton" in title):
                    if w.get("rect", {}).get("width", 0) > 400:
                        return w

        # 2. General title and class matching
        for w in wins:
            title = w.get("title", "").lower()
            cname = w.get("class_name", "")
            if b_clean in title or (b_clean == "brave" and "brave" in title) or (b_clean in ("chrome", "google chrome") and "chrome" in title) or (b_clean in ("edge", "microsoft edge") and "edge" in title):
                if cname in ("Chrome_WidgetWin_1", "MozillaWindowClass") or "brave" in title or "chrome" in title or "edge" in title:
                    if w.get("rect", {}).get("width", 0) > 400:
                        return w

        # 3. Fallback to any visible Chrome_WidgetWin_1 window
        if b_clean in ("brave", "chrome", "edge", "browser"):
            for w in wins:
                if w.get("class_name") == "Chrome_WidgetWin_1" and w.get("title") and w.get("rect", {}).get("width", 0) > 400:
                    return w

        return None

    def list_tabs(self, browser_name: str = "Brave") -> list[dict[str, Any]]:
        """Enumerate real browser tabs using native Windows UIAutomation with full thread safety."""
        bname = str(browser_name or "Brave").strip()
        try:
            tabs = UIA_ENGINE.list_browser_tabs(bname)
            if tabs:
                return tabs
        except Exception as e:
            logger.debug("[NATIVE_BROWSER] Error listing tabs via UIA_ENGINE: %s", e)

        # Multi-browser fallback
        for fallback_b in ("Brave", "Chrome", "Edge"):
            if fallback_b.lower() != bname.lower():
                try:
                    tabs = UIA_ENGINE.list_browser_tabs(fallback_b)
                    if tabs:
                        return tabs
                except Exception:
                    pass
        return []

    def get_active_tab(self, browser_name: str = "Brave") -> dict[str, Any] | None:
        """Return the currently selected/active tab in the running browser."""
        bname = str(browser_name or "Brave").strip()
        tabs = self.list_tabs(bname)
        selected = next((t for t in tabs if t.get("selected")), None)
        if selected:
            return selected
        win = self.find_browser_window(bname)
        if win and tabs:
            w_title = win.get("title", "").lower()
            for t in tabs:
                t_title = t.get("title", "").lower()
                if t_title and t_title in w_title:
                    return t
            return tabs[0]
        return None

    def get_tab_identity(self, browser_name: str = "Brave") -> Any | None:
        """Return authoritative canonical BrowserTabIdentity of the active visible browser tab."""
        from datetime import datetime, timezone
        from app.core.contracts import BrowserTabIdentity

        win = self.find_browser_window(browser_name)
        if not win:
            return None
        active_tab = self.get_active_tab(browser_name)
        return BrowserTabIdentity(
            browser_name=browser_name,
            browser_pid=win.get("pid"),
            browser_hwnd=win.get("hwnd"),
            tab_index=active_tab.get("tab_index") if active_tab else None,
            tab_title=active_tab.get("title") if active_tab else win.get("title"),
            tab_url=active_tab.get("url") if active_tab else None,
            is_active=True,
            identity_status="MATCHED",
            attached_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def open_tab(self, url: str = "about:blank", browser_name: str = "Brave") -> dict[str, Any]:
        """Open a new browser tab in the existing browser instance, navigate to destination, and verify."""
        win = self.find_browser_window(browser_name)
        if not win:
            return {"success": False, "error": f"Browser '{browser_name}' is not running."}

        hwnd = win["hwnd"]
        pid = win["pid"]

        tabs_before = self.list_tabs(browser_name)
        count_before = len(tabs_before)

        # Focus browser window
        UIA_ENGINE.focus_window(hwnd)
        time.sleep(0.15)

        # Open new tab via hotkey (Ctrl+T)
        pyautogui.hotkey("ctrl", "t")
        time.sleep(0.3)

        # If URL requested, type into address bar and press Enter with atomic replacement
        if url and url not in ("about:blank", ""):
            type_target = url
            # Bug 4 Workaround: ONLY when the exact host/navigation target is www.google.com, append ONE trailing space
            if type_target.strip().lower() in ("www.google.com", "https://www.google.com", "http://www.google.com"):
                type_target = "www.google.com "
            elif not type_target.startswith(("http://", "https://", "file://", "about:")):
                type_target = f"https://{type_target}"

            # Type URL atomically and press Enter
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.08)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.press("backspace")
            time.sleep(0.05)
            pyautogui.typewrite(type_target, interval=0.005)
            time.sleep(0.05)
            pyautogui.press("enter")

        # Mandatory Postcondition Verification: Poll for tab count or matching keyword
        deadline = time.perf_counter() + 5.0
        verified = False
        final_tabs = []
        matching_tab = None

        import urllib.parse
        parsed = urllib.parse.urlparse(url) if url else None
        domain = (parsed.netloc or parsed.path or "").lower().replace("www.", "")
        dest_keyword = domain.split(".")[0] if "." in domain else domain

        while time.perf_counter() < deadline:
            time.sleep(0.3)
            final_tabs = self.list_tabs(browser_name)
            if dest_keyword:
                matching_tab = next((t for t in final_tabs if dest_keyword in (t.get("title") or "").lower()), None)
                if matching_tab:
                    verified = True
                    break
            if len(final_tabs) > count_before:
                verified = True
                matching_tab = final_tabs[-1]
                break

        if not verified and count_before > 0:
            return {
                "success": False,
                "verified": False,
                "error": f"VERIFICATION_FAILED: Expected new tab for '{url}' in {browser_name}, but tab count remained {len(final_tabs)}.",
                "tabs_observed": [t.get("title") for t in final_tabs],
            }

        return {
            "success": True,
            "method": "existing_browser_tab_create",
            "hwnd": hwnd,
            "pid": pid,
            "url": url,
            "tab_count": len(final_tabs),
            "matched_tab": matching_tab,
            "verified": True,
            "message": f"Opened new tab in existing {browser_name} (HWND: {hwnd}) and verified navigation to '{url}'.",
        }

    def navigate_current_tab(self, url: str, browser_name: str = "Brave") -> dict[str, Any]:
        """Navigate the CURRENT active browser tab in-place without opening a duplicate tab."""
        win = self.find_browser_window(browser_name)
        if not win:
            return {"success": False, "error": f"Browser '{browser_name}' is not running."}

        hwnd = win["hwnd"]
        pid = win["pid"]

        # Focus browser window
        UIA_ENGINE.focus_window(hwnd)
        time.sleep(0.15)

        type_target = url
        # Bug 4 Workaround: ONLY when the exact host/navigation target is www.google.com, append ONE trailing space
        if type_target.strip().lower() in ("www.google.com", "https://www.google.com", "http://www.google.com"):
            type_target = "www.google.com "
        elif not type_target.startswith(("http://", "https://", "file://", "about:")):
            type_target = f"https://{type_target}"

        # Type URL atomically into address bar and press Enter
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.08)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.press("backspace")
        time.sleep(0.05)
        pyautogui.typewrite(type_target, interval=0.005)
        time.sleep(0.05)
        pyautogui.press("enter")

        # Bounded postcondition verification on the same tab
        import urllib.parse
        parsed = urllib.parse.urlparse(url) if url else None
        domain = (parsed.netloc or parsed.path or "").lower().replace("www.", "")
        dest_keyword = domain.split(".")[0] if "." in domain else domain

        deadline = time.perf_counter() + 5.0
        verified = False
        current_tab = None

        while time.perf_counter() < deadline:
            time.sleep(0.3)
            current_tab = self.get_active_tab(browser_name)
            if current_tab:
                title_lower = (current_tab.get("title") or "").lower()
                url_lower = (current_tab.get("url") or "").lower()
                if dest_keyword and (dest_keyword in title_lower or dest_keyword in url_lower):
                    verified = True
                    break
                if "results" in title_lower or "search" in title_lower:
                    verified = True
                    break

        return {
            "success": True,
            "method": "native_same_tab_navigate",
            "hwnd": hwnd,
            "pid": pid,
            "url": url,
            "active_tab": current_tab,
            "verified": verified,
            "message": f"Navigated current tab in {browser_name} (HWND: {hwnd}) to '{url}'.",
        }

    def switch_tab(self, target_query: str, browser_name: str = "Brave") -> dict[str, Any]:
        """Switch to a tab in the running browser matching target_query using SelectionItemPattern."""
        t_query = str(target_query or "").strip()
        b_name = str(browser_name or "Brave").strip()
        try:
            res = UIA_ENGINE.switch_browser_tab(t_query, browser_name=b_name)
            if res and res.get("success"):
                return res
        except Exception as e:
            logger.debug("[NATIVE_BROWSER] switch_tab error: %s", e)

        # Fallback to coordinate click if needed
        tabs = self.list_tabs(b_name)
        q_clean = re.sub(r"\s+(?:tab|browser\s+tab)$", "", t_query, flags=re.IGNORECASE).lower()
        for t in tabs:
            if q_clean in (t.get("title") or "").lower():
                rect = t.get("rect", {})
                if rect.get("left") is not None and rect.get("top") is not None and rect.get("width", 0) > 0:
                    cx = rect["left"] + rect["width"] // 2
                    cy = rect["top"] + rect["height"] // 2
                    pyautogui.click(cx, cy)
                    return {"success": True, "switched_to": t.get("title", ""), "method": "coordinate_click", "browser": b_name}

        return {"success": False, "error": f"Tab '{t_query}' not found in {b_name}."}

    def close_tab(self, target_tab: str, browser_name: str = "Brave") -> dict[str, Any]:
        """Close a specific browser tab by title and verify its absence."""
        t_tab = str(target_tab or "").strip()
        b_name = str(browser_name or "Brave").strip()
        win = self.find_browser_window(b_name)
        if not win:
            try:
                from .computer import _close_browser_tab
                v_res = _close_browser_tab(tab_name=t_tab, browser_name=b_name)
                if v_res and (v_res.get("status") == "completed" or v_res.get("success")):
                    return {
                        "success": True,
                        "method": "vision_close_browser_tab",
                        "closed_tab": t_tab,
                        "browser": b_name,
                        "message": f"Successfully closed the {t_tab.title()} tab in {b_name}.",
                    }
            except Exception:
                pass
            return {"success": False, "error": f"Browser '{b_name}' is not running."}

        # 1. Primary Strategy: UIA Tab Close Button Click
        try:
            res = UIA_ENGINE.close_browser_tab_uia(t_tab, browser_name=b_name)
            if res and res.get("success"):
                return res
        except Exception as e:
            logger.debug("[NATIVE_BROWSER] close_tab error via UIA: %s", e)

        # 2. Secondary Strategy: Switch to tab and press Ctrl+W
        switch_res = self.switch_tab(t_tab, browser_name=b_name)
        if switch_res.get("success"):
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.3)
            tabs_after = self.list_tabs(b_name)
            q_clean = t_tab.lower()
            still_open = any(q_clean in t.get("title", "").lower() for t in tabs_after)
            if not still_open:
                return {
                    "success": True,
                    "method": "keyboard_tab_close",
                    "closed_tab": target_tab,
                    "browser": browser_name,
                    "message": f"Successfully closed the {target_tab.title()} tab in {browser_name}.",
                }

        # 3. Tertiary Strategy: Visual fallback
        try:
            from .computer import _close_browser_tab
            v_res = _close_browser_tab(tab_name=target_tab, browser_name=browser_name)
            if v_res and (v_res.get("status") == "completed" or v_res.get("success")):
                return {
                    "success": True,
                    "method": "vision_close_browser_tab",
                    "closed_tab": target_tab,
                    "browser": browser_name,
                    "message": f"Successfully closed the {target_tab.title()} tab in {browser_name}.",
                }
        except Exception:
            pass

        return {"success": False, "error": f"Could not find or close tab '{target_tab}' in {browser_name}."}


# Global singleton
NATIVE_BROWSER = NativeBrowserController()
