"""
PLUTON V2 — First-Class WorldState Subsystem
Captures and represents live, authoritative snapshots of the physical desktop,
windows, active browser, tabs, UI elements, filesystem, terminal, and clipboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
import sys
import time
from typing import Any, Optional

from app.core.contracts import ExecutionContext

logger = logging.getLogger("pluton.core.world_state")


@dataclass
class WindowSnapshot:
    hwnd: int
    title: str
    class_name: str
    pid: int
    is_foreground: bool = False


@dataclass
class BrowserSnapshot:
    browser_name: str = ""
    hwnd: int = 0
    pid: int = 0
    active_tab_id: str = ""
    active_url: str = ""
    active_title: str = ""
    cdp_connected: bool = False
    visible_elements: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LocalServiceInfo:
    host: str = "127.0.0.1"
    port: int = 0
    protocol: str = "http"
    title: Optional[str] = None
    application_name: Optional[str] = None
    pid: Optional[int] = None
    url: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class WorldState:
    """Live snapshot of the operating environment at a single point in time."""
    timestamp: float = field(default_factory=time.time)
    focused_window: Optional[WindowSnapshot] = None
    visible_windows: list[WindowSnapshot] = field(default_factory=list)
    browser_session: Optional[BrowserSnapshot] = None
    local_services: list[LocalServiceInfo] = field(default_factory=list)
    clipboard_text: str = ""
    filesystem_verified_paths: dict[str, bool] = field(default_factory=dict)
    active_terminal_pid: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def capture(cls, context: Optional[ExecutionContext] = None) -> WorldState:
        """Capture live physical state across all subsystems safely and quickly (<30ms)."""
        state = cls()
        
        # 1. Window & UI Automation state
        try:
            from app.tools.uia_engine import UIA_ENGINE
            fg = UIA_ENGINE.get_foreground_window()
            if fg and fg.get("hwnd"):
                state.focused_window = WindowSnapshot(
                    hwnd=fg["hwnd"],
                    title=fg.get("title", ""),
                    class_name=fg.get("class_name", ""),
                    pid=fg.get("pid", 0),
                    is_foreground=True,
                )
            
            # List visible top-level windows
            raw_wins = UIA_ENGINE.list_windows(visible_only=True)
            for w in raw_wins[:15]:
                if w.get("hwnd"):
                    state.visible_windows.append(
                        WindowSnapshot(
                            hwnd=w["hwnd"],
                            title=w.get("title", ""),
                            class_name=w.get("class_name", ""),
                            pid=w.get("pid", 0),
                            is_foreground=(w.get("hwnd") == (state.focused_window.hwnd if state.focused_window else 0)),
                        )
                    )
        except Exception as e:
            logger.debug("[WORLD_STATE] Window capture non-critical error: %s", e)

        # 2. Browser session state
        try:
            from app.tools.native_browser_controller import NATIVE_BROWSER
            active_b = getattr(context, "active_browser", None)
            if active_b:
                tabs = NATIVE_BROWSER.list_tabs(active_b)
                if tabs:
                    active_tab = tabs[0]
                    state.browser_session = BrowserSnapshot(
                        browser_name=active_b,
                        hwnd=active_tab.get("hwnd", 0),
                        pid=active_tab.get("pid", 0),
                        active_tab_id=str(active_tab.get("id", "")),
                        active_url=active_tab.get("url", ""),
                        active_title=active_tab.get("title", ""),
                        cdp_connected=False,
                    )
        except Exception as e:
            logger.debug("[WORLD_STATE] Browser capture non-critical error: %s", e)

        # 3. Clipboard state
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    state.clipboard_text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass

        return state

    @classmethod
    def refresh_relevant_state(
        cls,
        context: Optional[ExecutionContext] = None,
        failure_classification: Any = None,
        invalidated_targets: Optional[list[str]] = None,
    ) -> WorldState:
        """Targeted lightweight refresh of state relevant to the failure."""
        state = cls.capture(context)

        # Reconcile invalidated targets
        if invalidated_targets and context:
            for inv in invalidated_targets:
                if inv.startswith("hwnd:"):
                    try:
                        h = int(inv.split(":", 1)[1])
                        if context.bound_hwnd == h:
                            context.workflow_context.invalidate_window()
                            context.bound_hwnd = None
                    except Exception:
                        pass
                elif inv.startswith("url:") or inv.startswith("tab:"):
                    context.workflow_context.invalidate_tab()

        return state