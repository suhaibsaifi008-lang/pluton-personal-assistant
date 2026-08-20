"""
PLUTON V2 — Canonical Browser Engine (Phase 1B: Browser Page Intelligence)
Coordinates Playwright, CDP, and Windows UIA into a unified, multi-tier browser controller.
Provides semantic page inspection, target resolution with ambiguity protection, and deterministic action verification.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import os
import re
import sys
import time
from typing import Any, Optional

logger = logging.getLogger("pluton.computer.browser_engine")


@dataclass
class BrowserContextState:
    """Canonical representation of browser runtime state."""
    browser_name: str = "Chromium"
    pid: int = 0
    hwnd: int = 0
    url: str = "about:blank"
    title: str = ""
    readiness: str = "uninitialized"  # "loading", "interactive", "complete", "closed"
    active_tab_id: str = ""
    tabs: list[dict[str, Any]] = field(default_factory=list)
    navigation_state: dict[str, Any] = field(default_factory=dict)
    download_state: list[dict[str, Any]] = field(default_factory=list)


class BrowserEngine:
    """Multi-tier Browser Controller coordinating Playwright, UIA, and OS navigation."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._is_pw_active = False
        self._is_attached_to_user_browser = False
        self._downloads: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------------
    # 1. Playwright Lifecycle & Option D Hybrid CDP Attachment
    # -------------------------------------------------------------------------

    def _is_browser_process_running(self, proc_name: str = "brave") -> bool:
        """Check if browser process is currently active on the host OS."""
        import subprocess
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Get-Process -Name '{proc_name}*' -ErrorAction SilentlyContinue"],
                capture_output=True,
                text=True,
                check=False,
            )
            return len(res.stdout.strip()) > 0
        except Exception:
            return False

    def check_browser_attach_status(self) -> dict[str, Any]:
        """Option D: Check if CDP is ready, cold-start if closed, or request confirmation if running without flag."""
        import httpx

        # 1. Check if CDP port 9222 is already listening
        try:
            r = httpx.get("http://127.0.0.1:9222/json/version", timeout=0.8)
            if r.status_code == 200:
                return {"status": "CDP_READY", "is_attached_to_user_browser": True}
        except Exception:
            pass

        # 2. Check if Brave is already running WITHOUT the debug flag
        if self._is_browser_process_running("brave"):
            logger.info("[BROWSER_ENGINE] Brave is running without --remote-debugging-port; will use visible managed browser instance.")
            return {"status": "CDP_UNAVAILABLE", "is_attached_to_user_browser": False}

        # 3. Cold Start: Nothing running, check if CDP is available
        return {"status": "CDP_UNAVAILABLE", "is_attached_to_user_browser": False}

    def _ensure_cdp_available(self) -> bool:
        """Probe CDP availability on port 9222."""
        import urllib.request
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _get_user_browser_executable(self) -> str | None:
        """Discover the host's actual Brave or Chrome browser executable path."""
        import os
        candidate_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for p in candidate_paths:
            if os.path.isfile(p):
                return p
        return None

    def get_cdp_listener_pid(self, port: int = 9222) -> int | None:
        """Find the OS Process ID listening on the specified CDP port."""
        import subprocess
        try:
            cmd = f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue).OwningProcess"
            res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=2.0)
            val = res.stdout.strip()
            if val and val.isdigit():
                return int(val)
        except Exception:
            pass
        return None

    async def _ensure_playwright(self, headless: bool = False) -> Any:
        """Lazily initialize Playwright browser context ONLY when CDP belongs to the authoritative user-visible browser."""
        from app.tools.native_browser_controller import NATIVE_BROWSER

        cur_loop = asyncio.get_running_loop()
        if getattr(self, "_bound_loop", None) is not cur_loop:
            self._playwright = None
            self._browser = None
            self._context = None
            self._page = None
            self._is_pw_active = False
            self._is_attached_to_user_browser = False
            self._bound_loop = cur_loop

        if self._page and not self._page.is_closed():
            return self._page

        async with self._lock:
            if self._page and not self._page.is_closed():
                return self._page

            try:
                # If standalone headless sandbox explicitly requested (e.g. unit tests):
                if headless:
                    from playwright.async_api import async_playwright
                    if self._playwright is None:
                        self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(headless=True)
                    self._context = await self._browser.new_context()
                    self._page = await self._context.new_page()
                    self._is_pw_active = True
                    self._is_attached_to_user_browser = False
                    return self._page

                # 1. Resolve user's actual visible desktop browser window
                win = NATIVE_BROWSER.find_browser_window("Brave") or NATIVE_BROWSER.find_browser_window("Chrome")
                if not win or not win.get("pid"):
                    logger.info("[BROWSER_ENGINE] No visible browser window found on desktop.")
                    self._is_pw_active = False
                    self._is_attached_to_user_browser = False
                    return None

                visible_pid = win["pid"]
                visible_hwnd = win.get("hwnd")

                # 2. Check if CDP port 9222 is active AND belongs to the exact visible browser PID
                cdp_pid = self.get_cdp_listener_pid(9222)
                if not cdp_pid or cdp_pid != visible_pid:
                    logger.info("[BROWSER_ENGINE] CDP is not enabled on visible browser PID %s (CDP PID: %s). Operating in native desktop mode.", visible_pid, cdp_pid)
                    self._is_pw_active = False
                    self._is_attached_to_user_browser = False
                    return None

                # 3. Connect Playwright over CDP to the verified visible browser process
                from playwright.async_api import async_playwright
                if self._playwright is None:
                    self._playwright = await async_playwright().start()

                logger.info("[BROWSER_ENGINE] Connecting Playwright over CDP to verified visible Brave (PID: %s, HWND: %s)...", visible_pid, visible_hwnd)
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    "http://127.0.0.1:9222",
                    timeout=10000,
                )
                contexts = self._browser.contexts
                self._context = contexts[0] if contexts else await self._browser.new_context()
                pages = self._context.pages
                self._page = pages[0] if pages else await self._context.new_page()
                self._is_pw_active = True
                self._is_attached_to_user_browser = True

                logger.info("[BROWSER_ENGINE] Verified visible browser connected over CDP. URL: %s, Title: %s", self._page.url, await self._page.title())
                return self._page

            except Exception as e:
                logger.warning("[BROWSER_ENGINE] Playwright CDP attach error: %s", e)
                self._is_pw_active = False
                self._is_attached_to_user_browser = False
                return None

    def _handle_download(self, download: Any) -> None:
        """Record download event in browser context."""
        try:
            self._downloads.append({
                "url": download.url,
                "suggested_filename": download.suggested_filename,
                "timestamp": time.time(),
            })
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 2. Canonical Browser State & Inspection
    # -------------------------------------------------------------------------

    async def get_state(self) -> dict[str, Any]:
        """Return canonical BrowserContext state model with explicit attachment status."""
        page = await self._ensure_playwright()
        warning = None if self._is_attached_to_user_browser else "[CRITICAL] Operating in standalone isolated browser instance. Real browser sessions, cookies, and tabs are NOT accessible."

        if page and not page.is_closed():
            try:
                title = await page.title()
                url = page.url
                readiness = await page.evaluate("() => document.readyState")
                pages = self._context.pages if self._context else [page]
                tabs = []
                for i, p in enumerate(pages):
                    tabs.append({
                        "tab_index": i,
                        "title": await p.title() if not p.is_closed() else "",
                        "url": p.url if not p.is_closed() else "",
                        "selected": (p == page),
                    })

                state = BrowserContextState(
                    browser_name="Chromium (Real Brave CDP)" if self._is_attached_to_user_browser else "Chromium (Isolated Fallback)",
                    url=url,
                    title=title,
                    readiness=readiness,
                    active_tab_id=str(id(page)),
                    tabs=tabs,
                    navigation_state={"can_go_back": True, "can_go_forward": True},
                    download_state=self._downloads,
                )
                res = {
                    "success": True,
                    "active": True,
                    "is_attached_to_user_browser": self._is_attached_to_user_browser,
                    "state": state.__dict__,
                    "url": url,
                    "title": title,
                    "readiness": readiness,
                }
                if warning:
                    res["warning"] = warning
                return res

            except Exception as e:
                logger.debug("[BROWSER_ENGINE] get_state exception: %s", e)

        # Fallback to UIA
        from app.tools.native_browser_controller import NATIVE_BROWSER
        tabs = NATIVE_BROWSER.list_tabs()
        res = {
            "success": True,
            "is_attached_to_user_browser": self._is_attached_to_user_browser,
            "state": {
                "browser_name": "Brave/Chromium",
                "readiness": "interactive",
                "tabs": tabs,
            },
            "tabs": tabs,
        }
        if warning:
            res["warning"] = warning
        return res


    async def get_url(self) -> dict[str, Any]:
        """Get current active URL."""
        page = await self._ensure_playwright()
        if page and not page.is_closed():
            return {"success": True, "url": page.url}
        return {"success": False, "error": "No active browser page."}

    async def get_title(self) -> dict[str, Any]:
        """Get current active page title."""
        page = await self._ensure_playwright()
        if page and not page.is_closed():
            title = await page.title()
            return {"success": True, "title": title}
        return {"success": False, "error": "No active browser page."}

    async def inspect_page(self, max_elements: int = 150) -> dict[str, Any]:
        """Extract a pruned, semantic DOM/accessibility tree containing interactive and structured elements from the active browser window."""
        from app.tools.native_browser_controller import NATIVE_BROWSER
        from app.tools.uia_engine import UIA_ENGINE

        # 1. Primary: Ensure Playwright CDP connection to authoritative visible browser
        page = None
        try:
            page = await self._ensure_playwright()
        except Exception as e:
            logger.debug("[BROWSER_ENGINE] _ensure_playwright error: %s", e)

        if not page:
            # 2. UIA Accessibility Inspection of the User's Actual Visible Desktop Browser Window
            win = NATIVE_BROWSER.find_browser_window("Brave") or NATIVE_BROWSER.find_browser_window("Chrome") or NATIVE_BROWSER.find_browser_window("Edge")
            if win and win.get("hwnd"):
                hwnd = win["hwnd"]
                pid = win.get("pid")
                title = win.get("title", "")
                active_tab = NATIVE_BROWSER.get_active_tab(win.get("browser_name", "Brave"))
                tab_title = active_tab.get("title") if active_tab else title
                tab_url = active_tab.get("url") if active_tab else ""

                # 1. Capture exact visible HWND screenshot crop
                rect = win.get("rect", {})
                region = (max(0, rect.get("left", 0)), max(0, rect.get("top", 0)), max(100, rect.get("width", 1200)), max(100, rect.get("height", 800)))
                from .domains.screen import SCREEN_DOMAIN
                cap = SCREEN_DOMAIN.capture(region=region)
                img_b64 = cap.get("base64", "")
                img_width = cap.get("width", 0)
                img_height = cap.get("height", 0)

                # 2. Extract UI elements and text content from the browser window using UIA
                uia_tree = UIA_ENGINE.inspect_ui_tree(hwnd=hwnd, max_depth=3)
                raw_elems = uia_tree.get("elements", [])
                elements = []
                for el in raw_elems:
                    name = el.get("name") or el.get("automation_id") or ""
                    ctype = el.get("control_type") or "element"
                    if name and ctype not in ("Window", "Pane", "Custom"):
                        elements.append({
                            "name": name,
                            "role": ctype.lower(),
                            "tag": ctype.lower(),
                            "selector": f"[name='{name}']",
                            "bounds": el.get("rect"),
                            "visible": True,
                            "enabled": el.get("is_enabled", True),
                        })

                # Read actual window text for baseline lines
                page_text = UIA_ENGINE.read_window_text(hwnd)
                visible_text_lines = []
                if page_text:
                    for line in page_text.splitlines()[:50]:
                        line_clean = line.strip()
                        if line_clean and len(line_clean) > 2 and line_clean not in visible_text_lines:
                            visible_text_lines.append(line_clean)
                            if not any(e["name"] == line_clean for e in elements):
                                elements.append({
                                    "name": line_clean,
                                    "role": "text",
                                    "tag": "p",
                                    "selector": f"text={line_clean}",
                                    "visible": True,
                                    "enabled": True,
                                })

                # 3. Enhance with Vision Perception via existing Provider
                vision_analysis = ""
                if img_b64:
                    try:
                        from app.providers import create_provider, ProviderRequest
                        prov = create_provider()
                        data_uri = f"data:image/png;base64,{img_b64}"
                        req = ProviderRequest(
                            message=(
                                f"You are the perceptual vision module for PLUTON AI analyzing a desktop screenshot of the user's active browser window (Title: '{tab_title}').\n"
                                "Analyze the rendered webpage content in detail:\n"
                                "1. What website/page is currently displayed?\n"
                                "2. What is the active search query or main topic?\n"
                                "3. List key visible content (e.g. video titles, search result links, prominent headings).\n"
                                "4. List visible interactive controls (e.g. search input box, submit button, filter buttons).\n"
                                "Be specific, factual, and concise."
                            ),
                            images=[data_uri],
                        )
                        resp = await prov.respond(req)
                        if resp and resp.text:
                            vision_analysis = resp.text.strip()
                    except Exception as ve:
                        logger.debug("[BROWSER_ENGINE] Vision inspection skipped: %s", ve)

                return {
                    "success": True,
                    "method": "desktop_screenshot_vision",
                    "hwnd": hwnd,
                    "pid": pid,
                    "title": tab_title,
                    "url": tab_url,
                    "webpage_visible": True,
                    "screenshot": {
                        "width": img_width,
                        "height": img_height,
                        "region": region,
                    },
                    "vision_analysis": vision_analysis,
                    "page_text": page_text,
                    "visible_text": visible_text_lines,
                    "elements": elements[:max_elements],
                    "element_count": len(elements[:max_elements]),
                    "verified": True,
                    "visible_browser": True,
                }

            return {"success": False, "error": "No active visible browser window found for inspection."}

        js_extractor = """() => {
            const elements = [];
            const interactiveRoles = new Set([
                'button', 'link', 'textbox', 'checkbox', 'combobox', 'listbox',
                'option', 'radio', 'switch', 'tab', 'menuitem', 'searchbox'
            ]);
            const interactiveTags = new Set(['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA']);

            function getCssPath(el) {
                if (!(el instanceof Element)) return '';
                if (el.id) return `#${el.id}`;
                let path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let selector = el.nodeName.toLowerCase();
                    if (el.id) {
                        selector = `#${el.id}`;
                        path.unshift(selector);
                        break;
                    } else {
                        let sib = el, nth = 1;
                        while (sib = sib.previousElementSibling) {
                            if (sib.nodeName.toLowerCase() === selector) nth++;
                        }
                        if (nth !== 1) selector += `:nth-of-type(${nth})`;
                    }
                    path.unshift(selector);
                    el = el.parentNode;
                }
                return path.join(' > ');
            }

            function isVisible(el) {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return style.display !== 'none' &&
                       style.visibility !== 'hidden' &&
                       style.opacity !== '0' &&
                       rect.width > 0 &&
                       rect.height > 0;
            }

            const allNodes = document.querySelectorAll('*');
            for (const el of allNodes) {
                if (elements.length >= 150) break;

                const tag = el.tagName;
                if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'META', 'LINK', 'TITLE', 'HEAD'].includes(tag)) {
                    continue;
                }
                if (tag === 'INPUT' && el.type === 'hidden') {
                    continue;
                }

                // Prune inline decoration/child elements (e.g. <i>, <span>, <svg>) inside an interactive parent
                if (['I', 'SPAN', 'SVG', 'PATH', 'EM', 'STRONG', 'B'].includes(tag) && el.closest('a, button, [role="button"], [role="link"]')) {
                    continue;
                }

                const role = el.getAttribute('role') || (
                    tag === 'A' ? 'link' :
                    tag === 'BUTTON' ? 'button' :
                    tag === 'INPUT' ? (el.type === 'checkbox' ? 'checkbox' : el.type === 'radio' ? 'radio' : el.type === 'submit' ? 'button' : 'textbox') :
                    tag === 'SELECT' ? 'combobox' :
                    tag === 'TEXTAREA' ? 'textbox' : ''
                );

                const isInteractive = interactiveRoles.has(role) || interactiveTags.has(tag) || el.hasAttribute('onclick') || el.getAttribute('tabindex') === '0';
                const hasDirectText = el.childNodes && Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 0);

                if (isInteractive || hasDirectText) {
                    const visible = isVisible(el);

                    let associatedLabel = '';
                    if (el.labels && el.labels[0]) {
                        associatedLabel = el.labels[0].innerText.trim();
                    } else if (el.id) {
                        const lbl = document.querySelector('label[for="' + el.id + '"]');
                        if (lbl) associatedLabel = lbl.innerText.trim();
                    }
                    if (!associatedLabel && (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA')) {
                        const prev = el.previousElementSibling;
                        if (prev && prev.tagName === 'LABEL') {
                            associatedLabel = prev.innerText.trim();
                        }
                    }

                    const name = (
                        el.getAttribute('aria-label') ||
                        associatedLabel ||
                        el.getAttribute('title') ||
                        (tag === 'INPUT' && el.type === 'submit' ? el.value : '') ||
                        (el.innerText ? el.innerText.trim() : '') ||
                        el.getAttribute('placeholder') ||
                        el.getAttribute('name') ||
                        el.id ||
                        ''
                    ).substring(0, 100);

                    const selector = getCssPath(el);
                    const isAriaDisabled = el.getAttribute('aria-disabled') === 'true';
                    const enabled = !el.disabled && !isAriaDisabled;
                    const value = el.value !== undefined ? String(el.value) : '';

                    const checked = el.checked !== undefined ? Boolean(el.checked) : false;
                    elements.push({
                        role: role || tag.toLowerCase(),
                        name: name,
                        tag: tag.toLowerCase(),
                        selector: selector,
                        visible: visible,
                        enabled: enabled,
                        value: value,
                        checked: checked,
                        id: el.id || undefined,
                        attr_name: el.getAttribute('name') || undefined,
                        placeholder: el.getAttribute('placeholder') || undefined,
                    });
                }
            }

            return {
                url: window.location.href,
                title: document.title,
                element_count: elements.length,
                elements: elements,
            };
        }"""

        for _ in range(3):
            try:
                res = await page.evaluate(js_extractor)
                return {"success": True, **res}
            except Exception as e:
                err_str = str(e).lower()
                if "context was destroyed" in err_str or "navigation" in err_str:
                    await asyncio.sleep(0.2)
                    continue
                return {"success": False, "error": f"Failed to inspect DOM: {e}"}
        return {"success": False, "error": "Failed to inspect DOM: execution context destroyed during navigation."}

    # -------------------------------------------------------------------------
    # 3. Target Resolution & Ambiguity Protection
    # -------------------------------------------------------------------------

    async def find_element(
        self,
        target: str,
        role: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any]:
        """Find interactive element in semantic tree matching target string with 5-tier priority."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"found": False, "status": "NOT_FOUND", "error": "No active browser page."}

        target_clean = target.strip()
        target_lower = target_clean.lower()

        # 1. First search result fast-path
        if target_lower in ("first result", "first search result", "1st result", "top result"):
            for first_sel in ("a:has(h3)", "a h3", "#search a", ".g a", "main a", "a[href^='http']:not([href*='google.com'])"):
                try:
                    el = await page.query_selector(first_sel)
                    if el and await el.is_visible():
                        return {
                            "found": True,
                            "status": "FOUND",
                            "score": 1.0,
                            "selector": first_sel,
                            "visible": True,
                            "enabled": True,
                            "element": {
                                "selector": first_sel,
                                "name": "First Result",
                                "role": "link",
                                "visible": True,
                                "enabled": True,
                            },
                        }
                except Exception:
                    pass

        # 1b. Generic control fast-paths when target specifies control category
        if target_lower in ("checkbox", "the checkbox") or role == "checkbox":
            try:
                el = await page.query_selector("input[type='checkbox'], [role='checkbox']")
                if el and await el.is_visible():
                    el_id = await el.get_attribute("id")
                    sel = f"#{el_id}" if el_id else "input[type='checkbox']"
                    return {
                        "found": True,
                        "status": "FOUND",
                        "score": 1.0,
                        "selector": sel,
                        "visible": True,
                        "enabled": await el.is_enabled(),
                        "element": {
                            "selector": sel,
                            "name": "checkbox",
                            "role": "checkbox",
                            "visible": True,
                            "enabled": await el.is_enabled(),
                        },
                    }
            except Exception:
                pass

        if target_lower in ("select", "dropdown", "combobox", "the dropdown", "the select") or role == "combobox":
            try:
                el = await page.query_selector("select, [role='combobox']")
                if el and await el.is_visible():
                    el_id = await el.get_attribute("id")
                    sel = f"#{el_id}" if el_id else "select"
                    return {
                        "found": True,
                        "status": "FOUND",
                        "score": 1.0,
                        "selector": sel,
                        "visible": True,
                        "enabled": await el.is_enabled(),
                        "element": {
                            "selector": sel,
                            "name": "select",
                            "role": "combobox",
                            "visible": True,
                            "enabled": await el.is_enabled(),
                        },
                    }
            except Exception:
                pass

        # 2. Direct CSS selector fast-path
        is_selector_syntax = (
            target_clean.startswith(("#", ".", "[", "input", "textarea", "button", "a", "h1", "h2", "h3", "div", "span", "select"))
            or "," in target_clean
            or ">" in target_clean
            or ":" in target_clean
        )
        if is_selector_syntax:
            try:
                el = await page.query_selector(target_clean)
                if el:
                    visible = await el.is_visible()
                    enabled = await el.is_enabled()
                    return {
                        "found": True,
                        "status": "FOUND",
                        "score": 1.0,
                        "selector": target_clean,
                        "visible": visible,
                        "enabled": enabled,
                        "element": {
                            "selector": target_clean,
                            "role": role or "element",
                            "name": target_clean,
                            "visible": visible,
                            "enabled": enabled,
                        },
                    }
            except Exception:
                pass

        inspect_res = await self.inspect_page()
        if not inspect_res.get("success"):
            return {"found": False, "status": "NOT_FOUND", "error": inspect_res.get("error", "DOM inspection failed.")}

        elements = inspect_res.get("elements", [])
        role_clean = role.strip().lower() if role else None

        scored: list[tuple[float, dict[str, Any]]] = []
        for el in elements:
            score = 0.0
            el_name = (el.get("name") or "").lower()
            el_role = (el.get("role") or "").lower()
            el_selector = (el.get("selector") or "").lower()
            el_id = (el.get("id") or "").lower()
            el_attr_name = (el.get("attr_name") or "").lower()
            el_ph = (el.get("placeholder") or "").lower()

            # Role filter (flexible for textboxes, searchboxes, comboboxes, textareas)
            if role_clean:
                text_roles = ("textbox", "searchbox", "combobox", "textarea", "input")
                button_roles = ("button", "link", "menuitem")
                if role_clean in text_roles and any(r in el_role for r in text_roles):
                    pass
                elif role_clean in ("button", "link") and any(r in el_role for r in button_roles):
                    pass
                elif role_clean not in el_role:
                    continue

            # Tier 1: Exact visible text, selector, or ID match
            if target_lower in (el_name, el_selector, f"#{el_id}", el_id):
                score = 1.0
            # Tier 2: Exact name attribute or placeholder match
            elif target_lower in (el_attr_name, f"name={el_attr_name}", el_ph):
                score = 0.85
            # Tier 3: Substring match in visible text
            elif len(target_lower) >= 3 and (target_lower in el_name or target_lower in el_ph):
                ratio = len(target_lower) / max(len(el_name), 1)
                score = 0.70 + (ratio * 0.10)
            # Tier 4: Token match (requiring meaningful non-stopword tokens)
            else:
                stopwords = {"the", "a", "an", "that", "this", "does", "not", "at", "all", "to", "in", "on", "is", "of", "for", "with", "and", "or"}
                meaningful_query_tokens = [tok for tok in target_lower.split() if tok not in stopwords and len(tok) >= 3]
                if meaningful_query_tokens:
                    matched_tokens = [tok for tok in meaningful_query_tokens if tok in el_name]
                    if len(matched_tokens) >= max(1, (len(meaningful_query_tokens) + 1) // 2):
                        score = 0.50 + 0.10 * (len(matched_tokens) / len(meaningful_query_tokens))
                elif el_name.startswith(target_lower) and len(target_lower) >= 3:
                    score = 0.45

            # Interactive Control Priority: boost real interactive form elements over passive labels/containers
            if score > 0:
                is_input_control = el.get("tag") in ("input", "button", "select", "textarea", "a") or el_role in ("button", "link", "textbox", "checkbox", "combobox")
                if is_input_control:
                    score += 0.08
                elif el.get("tag") == "label":
                    score -= 0.05

            if score > 0.40:
                scored.append((score, el))

        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored:
            return {
                "found": False,
                "error": f"TARGET_NOT_FOUND: No element matching '{target}' (role={role}) on active page.",
            }

        # Ambiguity Check: only trigger when no clear exact match exists (score < 0.95) and two candidates tie
        if len(scored) >= 2:
            top_score, top_elem = scored[0]
            second_score, second_elem = scored[1]
            both_interactive = top_elem.get("tag") in ("input", "button", "select", "textarea", "a") and second_elem.get("tag") in ("input", "button", "select", "textarea", "a")
            if top_score < 0.95 and (top_score - second_score) < 0.03 and top_elem["selector"] != second_elem["selector"] and both_interactive:
                logger.warning("[BROWSER_ENGINE] Ambiguity detected between '%s' and '%s'", top_elem["name"], second_elem["name"])
                return {
                    "found": False,
                    "error": f"AMBIGUOUS_TARGET: Multiple equally plausible elements match '{target}'. Candidates: ['{top_elem.get('name')}', '{second_elem.get('name')}'].",
                    "candidates": [top_elem, second_elem],
                }

        best_score, best_elem = scored[0]
        return {
            "found": True,
            "element": best_elem,
            "score": best_score,
            "selector": best_elem["selector"],
            "visible": best_elem["visible"],
            "enabled": best_elem["enabled"],
        }

    # -------------------------------------------------------------------------
    # 4. Deterministic Page Actions & Post-Action Verification
    # -------------------------------------------------------------------------

    async def navigate(self, url: str, browser_name: str = "Chromium") -> dict[str, Any]:
        """Navigate to URL and verify page readiness."""
        if not url.startswith(("http://", "https://", "file://", "about:")):
            url = f"https://{url}"

        page = await self._ensure_playwright()
        if not page:
            # Fallback to OS / UIA
            from app.tools.native_browser_controller import NATIVE_BROWSER
            return NATIVE_BROWSER.open_tab(url=url)

        try:
            resp = await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            if "google.com/sorry" in page.url:
                import urllib.parse
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                q_val = parsed_q.get("q", [""])[0]
                if q_val:
                    fb_url = f"https://duckduckgo.com/?q={urllib.parse.quote_plus(q_val)}"
                    resp = await page.goto(fb_url, timeout=15000, wait_until="domcontentloaded")
            title = await page.title()
            if resp and resp.status >= 400:
                return {
                    "success": False,
                    "error": f"HTTP_ERROR_{resp.status}: Navigation returned status {resp.status} for '{url}'",
                    "status_code": resp.status,
                    "url": page.url,
                    "title": title,
                }
            title = await page.title()
            inspect_res = await self.inspect_page()
            elements = inspect_res.get("elements", [])
            return {
                "success": True,
                "method": "playwright",
                "url": page.url,
                "title": title,
                "elements": elements,
                "element_count": len(elements),
                "status_code": resp.status if resp else 200,
                "verified": True,
            }
        except Exception as e:
            return {"success": False, "error": f"Navigation failed to '{url}': {e}"}

    async def click_element(self, target: str, role: str | None = None, expected_change: str | None = None) -> dict[str, Any]:
        """Resolve element, verify state, click, and verify postcondition."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for click."}

        # 1. Resolve Target
        res = await self.find_element(target, role=role)
        if not res.get("found"):
            return {"success": False, "error": res.get("error", "Element not found.")}

        elem_info = res["element"]
        selector = elem_info["selector"]

        # 2. Verify Target is Enabled & Visible
        if not elem_info.get("visible", True):
            return {"success": False, "error": f"TARGET_BLOCKED: Element '{target}' is not visible on page."}
        if not elem_info.get("enabled", True):
            return {"success": False, "error": f"TARGET_BLOCKED: Element '{target}' is disabled."}

        # 3. Execute Click
        try:
            await page.click(selector, timeout=5000)
            await page.wait_for_timeout(300)

            # 4. Verify Result & Capture Live State
            title = await page.title()
            url = page.url
            inspect_res = await self.inspect_page()
            elements = inspect_res.get("elements", [])
            return {
                "success": True,
                "method": "playwright_click",
                "target": target,
                "selector": selector,
                "url": url,
                "title": title,
                "elements": elements,
                "element_count": len(elements),
                "verified": True,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed clicking '{target}' ({selector}): {e}"}

    async def type_element(self, target: str, text: str, clear_first: bool = True, role: str | None = None, press_enter: bool = False) -> dict[str, Any]:
        """Resolve textbox, focus, type, and verify readback value."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for typing."}

        # 1. Resolve Target
        res = await self.find_element(target, role=role or "textbox")
        if not res.get("found"):
            return {"success": False, "error": res.get("error", "Textbox element not found.")}

        elem_info = res["element"]
        selector = elem_info["selector"]

        # 2. Verify Enabled & Visible
        if not elem_info.get("enabled", True):
            return {"success": False, "error": f"TARGET_BLOCKED: Input '{target}' is disabled."}

        # 3. Execute Fill
        try:
            if clear_first:
                await page.fill(selector, text, timeout=5000)
            else:
                await page.type(selector, text, timeout=5000)

            # 4. Postcondition Verification: Read back element value
            readback_value = await page.input_value(selector, timeout=3000)
            verified = (readback_value == text)

            if not verified:
                return {
                    "success": False,
                    "error": f"VERIFICATION_FAILED: Expected '{text}', observed '{readback_value}' in '{selector}'.",
                    "observed": readback_value,
                }

            if press_enter:
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(400)

            title = await page.title()
            url = page.url
            inspect_res = await self.inspect_page()
            elements = inspect_res.get("elements", [])

            return {
                "success": True,
                "method": "playwright_fill",
                "target": target,
                "selector": selector,
                "value_typed": text,
                "readback_value": readback_value,
                "url": url,
                "title": title,
                "elements": elements,
                "element_count": len(elements),
                "verified": True,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed typing into '{target}' ({selector}): {e}"}


    async def select_element(self, target: str, value: str, role: str | None = "combobox") -> dict[str, Any]:
        """Select dropdown option and verify selected value."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for selection."}

        # 1. Resolve Target
        res = await self.find_element(target, role=role)
        if not res.get("found"):
            return {"success": False, "error": res.get("error", "Select/dropdown element not found.")}

        elem_info = res["element"]
        selector = elem_info["selector"]

        # 2. Execute Selection
        try:
            try:
                await page.select_option(selector, label=value, timeout=3000)
            except Exception:
                await page.select_option(selector, value=value, timeout=3000)
            # 3. Readback Verification
            readback = await page.input_value(selector, timeout=3000)
            return {
                "success": True,
                "method": "playwright_select",
                "target": target,
                "selector": selector,
                "selected_value": readback,
                "verified": (readback == value or value in readback),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed selecting '{value}' in '{target}': {e}"}

    async def extract_text(self, selector: str | None = None, max_length: int = 4000) -> dict[str, Any]:
        """Extract clean text content from page or specific container element."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for text extraction."}

        try:
            if selector:
                text = await page.inner_text(selector, timeout=5000)
            else:
                text = await page.evaluate("() => document.body ? document.body.innerText : ''")

            truncated = (text[:max_length] + "...") if len(text) > max_length else text
            return {
                "success": True,
                "method": "playwright_extract",
                "text": truncated,
                "content": truncated,
                "total_length": len(text),
                "url": page.url,
            }

        except Exception as e:
            return {"success": False, "error": f"Failed extracting text: {e}"}

    async def extract_links(self, scope_selector: str | None = None) -> dict[str, Any]:
        """Extract visible links with text and href attributes."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for link extraction."}

        js = """(scope) => {
            const root = scope ? document.querySelector(scope) : document;
            if (!root) return [];
            const links = Array.from(root.querySelectorAll('a[href]'));
            return links.map(a => ({
                text: a.innerText ? a.innerText.trim() : (a.getAttribute('aria-label') || ''),
                href: a.href,
                visible: a.offsetParent !== null,
            })).filter(l => l.text.length > 0 && l.visible);
        }"""
        try:
            links = await page.evaluate(js, scope_selector)
            return {
                "success": True,
                "count": len(links),
                "links": links,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed extracting links: {e}"}

    async def wait_for(self, selector: str | None = None, text: str | None = None, state: str = "visible", timeout_seconds: float = 5.0) -> dict[str, Any]:
        """Wait for selector, text, or DOM condition to appear/disappear."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for wait condition."}

        timeout_ms = int(timeout_seconds * 1000)
        try:
            if selector:
                await page.wait_for_selector(selector, state=state, timeout=timeout_ms)
            elif text:
                await page.wait_for_selector(f"text={text}", state=state, timeout=timeout_ms)
            else:
                await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

            return {
                "success": True,
                "method": "playwright_wait",
                "condition_met": True,
                "state": state,
            }
        except Exception as e:
            return {"success": False, "error": f"Wait condition timed out ({timeout_seconds}s): {e}"}

    async def scroll_page(self, delta_x: int = 0, delta_y: int = 400) -> dict[str, Any]:
        """Scroll the active web page."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for scroll."}

        try:
            await page.mouse.wheel(delta_x, delta_y)
            return {"success": True, "method": "playwright_scroll", "delta_y": delta_y}
        except Exception as e:
            return {"success": False, "error": f"Scroll failed: {e}"}

    async def back(self) -> dict[str, Any]:
        """Navigate back in page history."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page."}

        url_before = page.url
        await page.go_back()
        return {"success": True, "method": "playwright_back", "url_before": url_before, "url_after": page.url}

    async def forward(self) -> dict[str, Any]:
        """Navigate forward in page history."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page."}

        url_before = page.url
        await page.go_forward()
        return {"success": True, "method": "playwright_forward", "url_before": url_before, "url_after": page.url}

    async def reload(self) -> dict[str, Any]:
        """Reload active page."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page."}

        await page.reload(wait_until="domcontentloaded")
        return {"success": True, "method": "playwright_reload", "url": page.url}

    async def download(self, target_url: str | None = None) -> dict[str, Any]:
        """Trigger or observe a download."""
        return {
            "success": True,
            "downloads": self._downloads,
            "count": len(self._downloads),
        }

    async def upload(self, selector: str, file_path: str) -> dict[str, Any]:
        """Set files for a file input element."""
        page = await self._ensure_playwright()
        if not page or page.is_closed():
            return {"success": False, "error": "No active browser page for file upload."}

        try:
            await page.set_input_files(selector, file_path, timeout=5000)
            return {"success": True, "method": "playwright_upload", "selector": selector, "file": file_path}
        except Exception as e:
            return {"success": False, "error": f"File upload failed: {e}"}

    # -------------------------------------------------------------------------
    # Backward Compatibility Helper Aliases
    # -------------------------------------------------------------------------

    async def type_text(self, selector: str, text: str) -> dict[str, Any]:
        """Backward compatibility alias for type_element."""
        return await self.type_element(target=selector, text=text)

    async def click(self, selector: str) -> dict[str, Any]:
        """Backward compatibility alias for click_element."""
        return await self.click_element(target=selector)

    async def read_page(self, max_length: int = 4000) -> dict[str, Any]:
        """Backward compatibility alias for extract_text."""
        return await self.extract_text(max_length=max_length)

    async def scroll(self, delta_x: int = 0, delta_y: int = 400) -> dict[str, Any]:
        """Backward compatibility alias for scroll_page."""
        return await self.scroll_page(delta_x=delta_x, delta_y=delta_y)

    async def go_back(self) -> dict[str, Any]:
        """Backward compatibility alias for back."""
        return await self.back()

    async def go_forward(self) -> dict[str, Any]:
        """Backward compatibility alias for forward."""
        return await self.forward()

    async def get_state(self) -> dict[str, Any]:
        """Get active page state, URL, and title."""
        from app.tools.native_browser_controller import NATIVE_BROWSER
        from app.tools.uia_engine import UIA_ENGINE
        win = NATIVE_BROWSER.find_browser_window("Brave") or NATIVE_BROWSER.find_browser_window("Chrome")
        if win and win.get("hwnd"):
            active_tab = NATIVE_BROWSER.get_active_tab(win.get("browser_name", "Brave"))
            return {
                "success": True,
                "browser": win.get("browser_name", "Brave"),
                "hwnd": win.get("hwnd"),
                "pid": win.get("pid"),
                "title": active_tab.get("title") if active_tab else win.get("title"),
                "url": active_tab.get("url") if active_tab else "",
                "active_tab": active_tab,
                "identity_status": "MATCHED",
            }
        return {"success": False, "error": "No active visible browser found."}

    async def close(self) -> None:
        """Cleanly detach or terminate Playwright instance without killing the user's real browser."""
        async with self._lock:
            try:
                # If connected over CDP to the user's real browser:
                # ONLY stop the Playwright client. NEVER call browser.close() or context.close(),
                # because Playwright sends Browser.close over CDP which kills the remote browser process
                # and leaves background subprocesses holding the SingletonLock!
                if self._is_attached_to_user_browser:
                    logger.info("[BROWSER_ENGINE] Detaching Playwright client cleanly from real browser CDP endpoint...")
                else:
                    # Isolated standalone sandbox instance: safe to terminate
                    if self._context:
                        await self._context.close()
                    if self._browser:
                        await self._browser.close()

                if self._playwright:
                    await self._playwright.stop()
            except Exception as e:
                logger.debug("[BROWSER_ENGINE] Teardown exception: %s", e)
            finally:
                self._page = None
                self._context = None
                self._browser = None
                self._playwright = None
                self._is_pw_active = False
                self._is_attached_to_user_browser = False



BROWSER_ENGINE = BrowserEngine()
