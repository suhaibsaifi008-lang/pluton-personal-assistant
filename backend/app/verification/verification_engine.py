"""
PLUTON V2 First-Class Verification Engine.

Provides authoritative, structured verification of physical actions and desktop state.

Invariants:
- "Tool executed successfully" != "User outcome achieved"
- Always prioritize structured OS/UIA verification before vision fallback.
- Mandatory verification for every state transition.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from app.core.contracts import VerificationResult, VerificationStrategy

logger = logging.getLogger("pluton.verification")


class VerificationEngine:
    """Universal state verifier for desktop, window, browser, filesystem, terminal, clipboard, and UI actions."""

    def __init__(self, uia_engine: Any = None) -> None:
        self._uia = uia_engine

    @property
    def uia(self) -> Any:
        if self._uia is None:
            from app.tools.uia_engine import UIA_ENGINE
            self._uia = UIA_ENGINE
        return self._uia

    def verify_action(
        self,
        strategy: VerificationStrategy,
        expected_state: Any,
        target: str = "",
        hwnd: int | None = None,
        pid: int | None = None,
        timeout_seconds: float = 4.0,
        metadata: dict[str, Any] | None = None,
    ) -> VerificationResult:
        """Execute the chosen verification strategy against live system state."""
        t_start = time.perf_counter()
        meta = metadata or {}

        if strategy == VerificationStrategy.NONE:
            return VerificationResult(
                verified=True,
                strategy=strategy,
                message="No explicit verification requested.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 1. UI Automation Text Read-back Verification
        # ---------------------------------------------------------------------
        # ---------------------------------------------------------------------
        # 1. UI Automation Text Read-back Verification
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.UIA_READBACK:
            target_hwnd = hwnd or (context.workflow_context.active_hwnd if context else None)
            if not target_hwnd and target:
                win = self.uia.find_window(target)
                if win:
                    target_hwnd = win.get("hwnd")
            if not target_hwnd:
                target_hwnd = self.uia.get_foreground_window().get("hwnd") or 0
            if not target_hwnd:
                return VerificationResult(
                    verified=False,
                    strategy=strategy,
                    message="UIA verification failed: No target or active foreground HWND found.",
                    latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                )
            self.uia.focus_window(target_hwnd)
            expected_text = str(expected_state or "")
            target_element = meta.get("target_element") or meta.get("element")

            deadline = time.perf_counter() + timeout_seconds
            observed_text = ""
            while time.perf_counter() < deadline:
                # 1. Check specific target element if requested
                if target_element:
                    elem_state = self.uia.read_element_state(target_name=target_element, hwnd=target_hwnd)
                    if elem_state.get("found"):
                        val_or_text = (elem_state.get("value") or elem_state.get("text") or "").strip()
                        if expected_text.lower() in val_or_text.lower() or val_or_text.lower() in expected_text.lower():
                            return VerificationResult(
                                verified=True,
                                strategy=strategy,
                                observed_state=elem_state,
                                expected_state=expected_text,
                                message=f"Verified element '{target_element}' state is '{val_or_text}' (expected: '{expected_text}').",
                                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                            )

                # 2. General window accessible text scan
                read_val = self.uia.read_window_text(target_hwnd)
                if read_val:
                    observed_text = read_val
                    obs_clean = " ".join(observed_text.lower().split())
                    exp_clean = " ".join(expected_text.lower().split())
                    obs_no_comma = obs_clean.replace(",", "").replace(" ", "")
                    exp_no_comma = exp_clean.replace(",", "").replace(" ", "")

                    # A. Substring / clean string match
                    if exp_clean in obs_clean or (exp_no_comma and exp_no_comma in obs_no_comma):
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state=observed_text,
                            expected_state=expected_text,
                            message=f"Verified text '{expected_text}' in target window (HWND: {target_hwnd}).",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )

                    # B. Calculator "Display is <num>" regex extract
                    m_disp = re.search(r"display\s+is\s+([0-9,\.\-]+)", obs_clean, flags=re.IGNORECASE)
                    if m_disp:
                        disp_val = m_disp.group(1).replace(",", "").strip()
                        if exp_no_comma and (exp_no_comma == disp_val or exp_no_comma in disp_val):
                            return VerificationResult(
                                verified=True,
                                strategy=strategy,
                                observed_state={"display_value": disp_val, "raw": observed_text},
                                expected_state=expected_text,
                                message=f"Verified Calculator display is '{disp_val}' (expected: '{expected_text}').",
                                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                            )
                        try:
                            if float(disp_val) == float(exp_no_comma):
                                return VerificationResult(
                                    verified=True,
                                    strategy=strategy,
                                    observed_state={"display_value": disp_val, "raw": observed_text},
                                    expected_state=expected_text,
                                    message=f"Verified numeric equivalence '{disp_val}' == '{expected_text}' in Calculator.",
                                    latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                                )
                        except Exception:
                            pass
                time.sleep(0.15)

            # Classify failure outcome
            win_exists = bool(self.uia.list_windows(visible_only=True))
            if observed_text:
                fail_diag = "APP_OPEN_ACTION_FAILED: Window is open but expected text/result was not found."
            elif win_exists:
                fail_diag = "DATA_UNAVAILABLE: Target window exists but accessibility text could not be read."
            else:
                fail_diag = "GENUINE_FAILURE: Target window was closed or absent."

            return VerificationResult(
                verified=False,
                strategy=strategy,
                observed_state=observed_text,
                expected_state=expected_text,
                message=f"UIA text readback failed ({fail_diag}): Expected '{expected_text}'.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 2. Window Presence Verification
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.WINDOW_PRESENCE:
            title_kw = str(target or expected_state or "").lower()
            expected_classes = [c.lower() for c in (meta.get("window_classes") or [])]
            expected_title_kws = [k.lower() for k in (meta.get("title_keywords") or [])]
            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                wins = self.uia.list_windows(visible_only=True)
                for w in wins:
                    c_name = w.get("class_name", "")
                    c_name_lower = c_name.lower()
                    w_title = w.get("title", "").lower()
                    is_match = False

                    if pid and w.get("pid") == pid:
                        is_match = True
                    elif hwnd and w.get("hwnd") == hwnd:
                        is_match = True
                    elif title_kw and title_kw in w_title:
                        is_match = True
                    elif expected_classes and c_name_lower in expected_classes:
                        is_match = True
                    elif expected_title_kws and any(k in w_title for k in expected_title_kws):
                        is_match = True

                    if is_match:
                        found_hwnd = w.get("hwnd", 0)
                        found_title = w.get("title", "")
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state={"hwnd": found_hwnd, "title": found_title, "pid": w.get("pid"), "class_name": c_name},
                            expected_state=target,
                            message=f"Verified window '{found_title}' is open and active (HWND: {found_hwnd}).",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )
                time.sleep(0.2)

            return VerificationResult(
                verified=False,
                strategy=strategy,
                expected_state=target,
                message=f"Window matching '{target}' was not found within {timeout_seconds}s.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 3. Window Absence Verification (Window Closure)
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.WINDOW_ABSENCE:
            title_kw = str(target or expected_state or "").lower()
            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                wins = self.uia.list_windows(visible_only=True)
                matching = [w for w in wins if (hwnd and w.get("hwnd") == hwnd) or (title_kw and title_kw in w.get("title", "").lower())]
                if not matching:
                    return VerificationResult(
                        verified=True,
                        strategy=strategy,
                        observed_state="closed",
                        expected_state="absent",
                        message=f"Verified window '{target}' has been closed.",
                        latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                    )
                time.sleep(0.2)

            return VerificationResult(
                verified=False,
                strategy=strategy,
                observed_state="still_open",
                expected_state="absent",
                message=f"Window '{target}' remained open after close attempt.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 4. Window State Verification (Minimized, Maximized, Foreground)
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.WINDOW_STATE:
            exp_state = str(expected_state or "").lower()
            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                from app.subsystems.computer.domains.window import WINDOW_DOMAIN
                st = WINDOW_DOMAIN.get_state(hwnd or target)
                if st.get("active") is not False:
                    if exp_state in (st.get("state", "").lower(), "foreground" if st.get("foreground") else ""):
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state=st,
                            expected_state=exp_state,
                            message=f"Verified window state is '{exp_state}'.",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )
                time.sleep(0.15)

            return VerificationResult(
                verified=False,
                strategy=strategy,
                expected_state=exp_state,
                message=f"Window state did not transition to '{exp_state}'.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 5. Browser Tab Presence & Navigation Verification
        # ---------------------------------------------------------------------
        if strategy in (VerificationStrategy.BROWSER_TAB_PRESENCE, VerificationStrategy.BROWSER_URL_MATCH):
            browser_name = meta.get("browser", "Brave")
            raw_target = str(expected_state or target or "").lower()
            keywords = [raw_target]
            if raw_target.startswith("http") or "." in raw_target:
                import urllib.parse
                parsed = urllib.parse.urlparse(raw_target)
                domain = parsed.netloc or parsed.path
                parts = [p for p in domain.split(".") if p not in ("www", "com", "org", "net", "io", "ai", "https:", "http:")]
                keywords.extend(parts)

            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                from app.tools.native_browser_controller import NATIVE_BROWSER
                active_t = NATIVE_BROWSER.get_active_tab(browser_name)
                if active_t:
                    t_title = active_t.get("title", "").lower()
                    if any(kw in t_title for kw in keywords if kw):
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state=active_t,
                            expected_state=raw_target,
                            message=f"Verified browser tab '{active_t.get('title')}' is active in {browser_name}.",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )

                win = NATIVE_BROWSER.find_browser_window(browser_name)
                if win:
                    w_title = win.get("title", "").lower()
                    if any(kw in w_title for kw in keywords if kw):
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state=win,
                            expected_state=raw_target,
                            message=f"Verified browser window '{win.get('title')}' in {browser_name}.",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )

                tabs = self.uia.list_browser_tabs(browser_name)
                if not tabs and browser_name == "Brave":
                    for fallback_b in ("Chrome", "Edge"):
                        tabs = self.uia.list_browser_tabs(fallback_b)
                        if tabs:
                            browser_name = fallback_b
                            break

                for t in tabs:
                    title = t.get("title", "").lower()
                    if any(kw in title for kw in keywords if kw):
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state=t,
                            expected_state=raw_target,
                            message=f"Verified browser tab '{t.get('title')}' is present in {browser_name}.",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )
                time.sleep(0.25)

            return VerificationResult(
                verified=False,
                strategy=strategy,
                expected_state=raw_target,
                message=f"Tab '{raw_target}' not found in {browser_name} after {timeout_seconds}s.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 5b. Browser Title Match Verification (Visible Active Tab)
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.BROWSER_TITLE_MATCH:
            browser_name = meta.get("browser", "Brave")
            target_kw = str(target or expected_state or "").lower()
            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                from app.tools.native_browser_controller import NATIVE_BROWSER
                active_tab = NATIVE_BROWSER.get_active_tab(browser_name)
                if active_tab:
                    cur_title = (active_tab.get("title") or "").lower()
                    if target_kw in cur_title or any(part in cur_title for part in target_kw.split() if len(part) >= 3):
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state=active_tab,
                            expected_state=target_kw,
                            message=f"Verified visible browser tab title is '{active_tab.get('title')}' in {browser_name}.",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )
                time.sleep(0.25)

            return VerificationResult(
                verified=False,
                strategy=strategy,
                expected_state=target_kw,
                message=f"Visible tab title matching '{target_kw}' not found in {browser_name}.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 5c. Browser URL Match Verification
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.BROWSER_URL_MATCH:
            browser_name = meta.get("browser", "Brave")
            target_url = str(target or expected_state or "").lower()
            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                from app.tools.native_browser_controller import NATIVE_BROWSER
                active_tab = NATIVE_BROWSER.get_active_tab(browser_name)
                if active_tab and active_tab.get("url"):
                    if target_url in active_tab["url"].lower():
                        return VerificationResult(
                            verified=True,
                            strategy=strategy,
                            observed_state=active_tab,
                            expected_state=target_url,
                            message=f"Verified visible browser URL is '{active_tab.get('url')}'.",
                            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                        )
                time.sleep(0.25)

            return VerificationResult(
                verified=False,
                strategy=strategy,
                expected_state=target_url,
                message=f"Visible URL matching '{target_url}' not found in {browser_name}.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 6. Browser Tab Absence Verification (Tab Closure)
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.BROWSER_TAB_ABSENCE:
            browser_name = meta.get("browser", "Brave")
            target_tab = str(target or expected_state or "").lower()
            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                tabs = self.uia.list_browser_tabs(browser_name)
                matching = [t for t in tabs if target_tab in t.get("title", "").lower()]
                if not matching:
                    return VerificationResult(
                        verified=True,
                        strategy=strategy,
                        observed_state="closed",
                        expected_state="absent",
                        message=f"Verified tab '{target}' is no longer present in {browser_name}.",
                        latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                    )
                time.sleep(0.25)

            return VerificationResult(
                verified=False,
                strategy=strategy,
                observed_state="still_present",
                expected_state="absent",
                message=f"Tab '{target}' was still found open in {browser_name}.",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 7. Filesystem Check Verification
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.FILESYSTEM_CHECK:
            path_str = str(target or expected_state or "")
            expected_exists = meta.get("expected_exists", True)
            if str(expected_state).lower() in ("absent", "deleted", "false"):
                expected_exists = False
            p = Path(path_str)
            exists = p.exists()
            verified = (exists == expected_exists)
            obs_state: dict[str, Any] = {"exists": exists, "path": str(p)}

            if exists and expected_exists and p.is_file():
                st_size = p.stat().st_size
                obs_state["size_bytes"] = st_size
                min_bytes = meta.get("expected_min_bytes")
                if min_bytes is not None and st_size < min_bytes:
                    verified = False
                    obs_state["error"] = f"Size mismatch: found {st_size} bytes, expected at least {min_bytes}"

                exp_content = meta.get("expected_content")
                if exp_content is not None:
                    try:
                        actual_content = p.read_text(encoding="utf-8", errors="replace")
                        if actual_content != exp_content:
                            verified = False
                            obs_state["error"] = "Content mismatch between written and actual text."
                    except Exception as e:
                        verified = False
                        obs_state["error"] = f"Could not read content: {e}"

            return VerificationResult(
                verified=verified,
                strategy=strategy,
                observed_state=obs_state,
                expected_state={"exists": expected_exists, **meta},
                message=f"Filesystem check for '{p}': verified={verified} (exists={exists}, size={obs_state.get('size_bytes', 0)}B).",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 8. Terminal Exit Code Verification
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.TERMINAL_EXIT_CODE:
            expected_code = int(expected_state if expected_state is not None else 0)
            actual_code = int(meta.get("exit_code", -1))
            verified = (actual_code == expected_code)
            return VerificationResult(
                verified=verified,
                strategy=strategy,
                observed_state={"exit_code": actual_code},
                expected_state={"exit_code": expected_code},
                message=f"Terminal execution returned exit code {actual_code} (expected: {expected_code}).",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 9. Clipboard Match Verification
        # ---------------------------------------------------------------------
        if strategy == VerificationStrategy.CLIPBOARD_MATCH:
            exp_content = str(expected_state or "")
            from app.subsystems.computer.domains.clipboard import CLIPBOARD_DOMAIN
            deadline = time.perf_counter() + max(0.5, timeout_seconds)
            actual_content = ""
            verified = False
            while True:
                clip = CLIPBOARD_DOMAIN.get()
                actual_content = clip.get("content", "")
                if exp_content in actual_content:
                    verified = True
                    break
                if time.perf_counter() >= deadline:
                    break
                time.sleep(0.05)

            return VerificationResult(
                verified=verified,
                strategy=strategy,
                observed_state={"clipboard": actual_content},
                expected_state={"expected": exp_content},
                message=f"Clipboard content match verified={verified} (observed: '{actual_content[:60]}').",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        # ---------------------------------------------------------------------
        # 11. DOM Value Match & DOM State Change Verification (Browser Elements)
        # ---------------------------------------------------------------------
        if strategy in (VerificationStrategy.DOM_VALUE_MATCH, VerificationStrategy.DOM_STATE_CHANGE):
            exp_val = str(expected_state or "").strip().lower()
            from app.subsystems.computer.browser_engine import BROWSER_ENGINE

            # If tool execution already captured DOM verification result in metadata
            if meta.get("verified") is True:
                return VerificationResult(
                    verified=True,
                    strategy=strategy,
                    observed_state=meta.get("observed_value") or meta.get("value") or exp_val,
                    expected_state=expected_state,
                    message=f"Verified DOM state matches '{expected_state}'.",
                    latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                )

            # Check metadata success status
            success_status = meta.get("success", True)
            return VerificationResult(
                verified=bool(success_status),
                strategy=strategy,
                observed_state=meta,
                expected_state=expected_state,
                message=f"Verified DOM interaction for '{target}' (status={success_status}).",
                latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
            )

        return VerificationResult(
            verified=False,
            strategy=strategy,
            message=f"Unsupported verification strategy: {strategy.value}",
            latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
        )


VERIFICATION_ENGINE = VerificationEngine()
