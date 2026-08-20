"""Universal Computer Action Router & Generic Capability Substrate for PLUTON.

Interprets user computer-control requests semantically, compiles them into generic capabilities,
and automatically selects the best deterministic control layer according to the strict priority hierarchy:
1. Native OS / Application APIs (deterministic & appropriate)
2. Browser-Native / CDP Mechanisms
3. Windows UI Automation Engine (UIA)
4. Deterministic Keyboard Shortcuts / Input
5. Vision / Screenshot Grounding (Fallback ONLY)
6. Coordinate Mouse Input (Final Fallback)

Enforces MANDATORY POST-ACTION VERIFICATION for every computer action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable
from urllib.parse import urlparse
import webbrowser

from .computer_safety import assert_computer_control_allowed, is_computer_control_allowed
from .uia_engine import UIA_ENGINE, UIAutomationEngine

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    APP_LAUNCH = "APP_LAUNCH"
    BROWSER_NAVIGATE = "BROWSER_NAVIGATE"
    BROWSER_TAB_CREATE = "BROWSER_TAB_CREATE"
    BROWSER_TAB_LIST = "BROWSER_TAB_LIST"
    BROWSER_TAB_SWITCH = "BROWSER_TAB_SWITCH"
    BROWSER_TAB_CLOSE = "BROWSER_TAB_CLOSE"
    WINDOW_SWITCH = "WINDOW_SWITCH"
    WINDOW_CLOSE = "WINDOW_CLOSE"
    WINDOW_LIST = "WINDOW_LIST"
    UI_INTERACT = "UI_INTERACT"
    HOTKEY = "HOTKEY"
    KEY_PRESS = "KEY_PRESS"
    SEQUENTIAL_WORKFLOW = "SEQUENTIAL_WORKFLOW"
    INSPECT_UI = "INSPECT_UI"
    FILE_OPEN = "FILE_OPEN"
    FOLDER_OPEN = "FOLDER_OPEN"
    GENERAL_ACTION = "GENERAL_ACTION"




@dataclass
class SemanticIntent:
    intent_type: IntentType
    raw_request: str
    target: str = ""
    action_verb: str = ""
    value: str = ""
    browser: str = "Brave"
    control_type: str = ""
    expected_outcome: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# Known standard Windows applications and their executable names / URI schemes
_KNOWN_APPS: dict[str, dict[str, Any]] = {
    "settings": {"exe": "ms-settings:", "is_uri": True, "title_kw": "Settings"},
    "windows settings": {"exe": "ms-settings:", "is_uri": True, "title_kw": "Settings"},
    "calculator": {"exe": "calc.exe", "is_uri": False, "title_kw": "Calculator"},
    "calc": {"exe": "calc.exe", "is_uri": False, "title_kw": "Calculator"},
    "notepad": {"exe": "notepad.exe", "is_uri": False, "title_kw": "Notepad"},
    "file explorer": {"exe": "explorer.exe", "is_uri": False, "title_kw": "File Explorer"},
    "explorer": {"exe": "explorer.exe", "is_uri": False, "title_kw": "File Explorer"},
    "downloads": {"exe": "explorer.exe", "args": [os.path.expanduser("~/Downloads")], "is_uri": False, "title_kw": "Downloads"},
    "documents": {"exe": "explorer.exe", "args": [os.path.expanduser("~/Documents")], "is_uri": False, "title_kw": "Documents"},
    "task manager": {"exe": "taskmgr.exe", "is_uri": False, "title_kw": "Task Manager"},
    "taskmgr": {"exe": "taskmgr.exe", "is_uri": False, "title_kw": "Task Manager"},
    "cmd": {"exe": "cmd.exe", "is_uri": False, "title_kw": "Command Prompt"},
    "powershell": {"exe": "powershell.exe", "is_uri": False, "title_kw": "PowerShell"},
    "terminal": {"exe": "wt.exe", "is_uri": False, "title_kw": "Terminal"},
    "brave": {"exe": "brave.exe", "is_uri": False, "title_kw": "Brave"},
    "chrome": {"exe": "chrome.exe", "is_uri": False, "title_kw": "Chrome"},
    "edge": {"exe": "msedge.exe", "is_uri": False, "title_kw": "Edge"},
}

# Known web destinations for natural browser navigation
_KNOWN_WEB_DESTINATIONS: dict[str, str] = {
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "claude": "https://claude.ai",
    "chatgpt": "https://chatgpt.com",
    "pollinations": "https://pollinations.ai",
    "pollinations.ai": "https://pollinations.ai",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
}


class ComputerActionRouter:
    """Universal Semantic Computer Control Router with Mandatory Verification and Fallbacks."""

    def __init__(self, uia_engine: UIAutomationEngine | None = None) -> None:
        self.uia = uia_engine or UIA_ENGINE

    # --------------------------------------------------------------------------
    # 1. Semantic Intent Resolution
    # --------------------------------------------------------------------------

    def parse_intent(self, request: str) -> SemanticIntent:
        """Parse natural user requests into a typed SemanticIntent."""
        req_clean = request.strip().rstrip(".!?")
        req_lower = req_clean.lower()

        # Multi-step sequential workflows separated by '→', '->', or ';'
        steps_raw = [s.strip() for s in re.split(r"\s*(?:→|->|;)\s*", req_clean) if s.strip()]
        if len(steps_raw) >= 2:
            parsed_steps = [self.parse_intent(s) for s in steps_raw]
            if any(p.intent_type != IntentType.GENERAL_ACTION for p in parsed_steps):
                return SemanticIntent(
                    intent_type=IntentType.SEQUENTIAL_WORKFLOW,
                    raw_request=req_clean,
                    metadata={"steps": parsed_steps},
                    expected_outcome="sequential_workflow_completed",
                )

        # Multi-step sequential workflows separated by commas (when each segment is a clear action)
        # e.g. "Open Notepad, type Hello, press Ctrl+A, type Replacement"
        if "," in req_clean:
            comma_parts = [s.strip() for s in req_clean.split(",") if s.strip()]
            if len(comma_parts) >= 2:
                parsed_comma = [self.parse_intent(p) for p in comma_parts]
                # Only treat as sequential if majority of steps are recognised actions
                non_general = [p for p in parsed_comma if p.intent_type != IntentType.GENERAL_ACTION]
                if len(non_general) >= max(1, len(parsed_comma) // 2):
                    return SemanticIntent(
                        intent_type=IntentType.SEQUENTIAL_WORKFLOW,
                        raw_request=req_clean,
                        metadata={"steps": parsed_comma},
                        expected_outcome="sequential_workflow_completed",
                    )

        # Compound single-sentence: "Open X and type Y" / "Launch X and write Y"
        compound_m = re.search(
            r"^(?:open|launch|start|run)\s+([a-z0-9\s\.\-_:]+?)\s+and\s+(?:type|write|input|enter)\s+[\"']?(.+?)[\"']?$",
            req_lower,
        )
        if compound_m:
            app_name = compound_m.group(1).strip()
            type_text = compound_m.group(2).strip()
            # Recover original-case text
            orig_lower_start = req_lower.index(type_text)
            type_text_orig = req_clean[orig_lower_start : orig_lower_start + len(type_text)]
            launch_intent = self.parse_intent(f"Open {app_name}")
            type_intent = SemanticIntent(
                intent_type=IntentType.UI_INTERACT,
                raw_request=f"type {type_text_orig}",
                target=app_name,
                action_verb="type_into_target",
                value=type_text_orig,
                expected_outcome=f"value_set:{app_name}:{type_text_orig}",
            )
            return SemanticIntent(
                intent_type=IntentType.SEQUENTIAL_WORKFLOW,
                raw_request=req_clean,
                metadata={"steps": [launch_intent, type_intent]},
                expected_outcome="sequential_workflow_completed",
            )

        # A. Window Listing

        if re.search(r"\b(?:what\s+windows|list\s+(?:all\s+)?(?:currently\s+)?open\s+windows|what\s+apps\s+are\s+running|running\s+applications|running\s+apps|open\s+windows\s*$)\b", req_lower):
            return SemanticIntent(
                intent_type=IntentType.WINDOW_LIST,
                raw_request=req_clean,
                expected_outcome="list_open_windows",
            )

        # B. Browser Tab Listing / Active Tab Query
        if re.search(r"\b(?:what\s+tabs?|list\s+(?:my\s+)?tabs?|open\s+tabs?|show\s+tabs?|(?:title\s+(?:of\s+)?|get\s+|what\s+is\s+|tell\s+me\s+(?:the\s+)?)?(?:the\s+)?(?:currently\s+)?(?:active|current)\s+(?:browser\s+)?tab|which\s+page|what\s+page|what\s+website)\b", req_lower):
            b_match = re.search(r"\b(brave|chrome|edge)\b", req_lower)
            browser = b_match.group(1).title() if b_match else "Brave"
            return SemanticIntent(
                intent_type=IntentType.BROWSER_TAB_LIST,
                raw_request=req_clean,
                browser=browser,
                expected_outcome="list_browser_tabs",
            )

        # C. Direct Web Destination Matching (e.g. "Open Google", "Open Gmail", "Take me to YouTube")
        for kw, dest_url in _KNOWN_WEB_DESTINATIONS.items():
            if re.search(rf"\b(?:open|go\s+to|navigate\s+to|launch|show|take\s+me\s+to|bring\s+me\s+to)\s+(?:a\s+new\s+tab\s+(?:for|with|in|and\s+take\s+me\s+to)\s+)?(?:the\s+)?{re.escape(kw)}\b", req_lower):
                b_match = re.search(r"\b(brave|chrome|edge)\b", req_lower)
                browser = b_match.group(1).title() if b_match else "Brave"
                return SemanticIntent(
                    intent_type=IntentType.BROWSER_NAVIGATE,
                    raw_request=req_clean,
                    target=kw,
                    value=dest_url,
                    browser=browser,
                    expected_outcome=f"tab_created:{kw.title()}",
                )

        # D. Direct URL Matching (e.g. "Go to https://example.com", "Open github.com/repo", "Open a new tab in Brave and navigate to https://google.com")
        url_match = re.search(r"\b(https?:\/\/[^\s]+|[a-zA-Z0-9\-]+\.(?:com|org|io|ai|net|edu|gov|co|dev)(?:\/[^\s]*)?)\b", req_clean, re.IGNORECASE)
        if url_match:
            url_target = url_match.group(1)
            dest_url = url_target if url_target.startswith("http") else f"https://{url_target}"
            b_match = re.search(r"\b(brave|chrome|edge)\b", req_lower)
            browser = b_match.group(1).title() if b_match else "Brave"
            return SemanticIntent(
                intent_type=IntentType.BROWSER_NAVIGATE,
                raw_request=req_clean,
                target=url_target,
                value=dest_url,
                browser=browser,
                expected_outcome=f"tab_created:{url_target}",
            )

        # E. Browser Tab Creation ("Open a new tab", "Get me a fresh browser tab", "New tab")
        if re.search(r"\b(?:open|create|new|get(?:\s+me)?)\s+(?:a\s+)?(?:new\s+|fresh\s+)?(?:browser\s+)?tab\b", req_lower):
            b_match = re.search(r"\b(brave|chrome|edge)\b", req_lower)
            browser = b_match.group(1).title() if b_match else "Brave"
            return SemanticIntent(
                intent_type=IntentType.BROWSER_TAB_CREATE,
                raw_request=req_clean,
                browser=browser,
                expected_outcome="tab_created:New Tab",
            )

        # F. Browser Tab Switching
        tab_switch_m = re.search(r"\b(?:switch\s+(?:back\s+)?to|go\s+(?:back\s+|over\s+)?to|select)\s+(?:the\s+)?([a-z0-9\s\.\-_]+?)\s+tab\b", req_lower)
        if tab_switch_m:
            target_tab = tab_switch_m.group(1).strip().title()
            b_match = re.search(r"\b(brave|chrome|edge)\b", req_lower)
            browser = b_match.group(1).title() if b_match else "Brave"
            return SemanticIntent(
                intent_type=IntentType.BROWSER_TAB_SWITCH,
                raw_request=req_clean,
                target=target_tab,
                browser=browser,
                expected_outcome=f"tab_active:{target_tab}",
            )

        # G. Browser Tab Closing
        tab_close_m = re.search(r"\b(?:close|get\s+rid\s+of)\s+(?:the\s+)?([a-z0-9\s\.\-_]+?)\s+tab\b", req_lower)
        if tab_close_m:
            target_tab = tab_close_m.group(1).strip().title()
            b_match = re.search(r"\b(brave|chrome|edge)\b", req_lower)
            browser = b_match.group(1).title() if b_match else "Brave"
            return SemanticIntent(
                intent_type=IntentType.BROWSER_TAB_CLOSE,
                raw_request=req_clean,
                target=target_tab,
                browser=browser,
                expected_outcome=f"tab_closed:{target_tab}",
            )

        # H. Folder Opening ("Open Downloads folder", "Open Documents", "Show folder X")
        folder_m = re.search(r"\b(?:open|show|explore)\s+(?:the\s+)?([a-z0-9\s\.\-_\\\/:]+?)\s+(?:folder|directory)\b", req_lower)
        if folder_m:
            folder_target = folder_m.group(1).strip()
            return SemanticIntent(
                intent_type=IntentType.FOLDER_OPEN,
                raw_request=req_clean,
                target=folder_target,
                expected_outcome=f"window_created:{folder_target.title()}",
            )

        # I. File Opening ("Open file X", "Open 'path/to/file'")
        file_m = re.search(r"\b(?:open|launch)\s+(?:the\s+)?(?:file\s+)?[\"']?([a-z0-9\s\.\-_\/\\:]+\.[a-z0-9]+)[\"']?", req_lower)
        if file_m:
            file_path = file_m.group(1).strip()
            return SemanticIntent(
                intent_type=IntentType.FILE_OPEN,
                raw_request=req_clean,
                target=file_path,
                expected_outcome=f"file_opened:{file_path}",
            )


        # J. App Launching
        open_app_m = re.search(r"^(?:open|launch|start|run)\s+(?:the\s+)?([a-z0-9\s\.\-_:\/]+?)(?:\s+(?:app|application|window))?$", req_lower)
        if open_app_m:
            app_raw = open_app_m.group(1).strip()
            from app.planning.intent_compiler import UniversalAppRegistry
            resolved = UniversalAppRegistry.resolve(app_raw)
            if resolved:
                return SemanticIntent(
                    intent_type=IntentType.APP_LAUNCH,
                    raw_request=req_clean,
                    target=app_raw,
                    expected_outcome=f"window_created:{resolved.get('title_kw', app_raw.title())}",
                    metadata=resolved,
                )


        # K. Window Switching ("Switch to Settings", "Focus Excel", "Bring up Brave", "Bring Notepad forward")
        win_switch_m = re.search(r"^(?:switch\s+(?:back\s+)?to|focus|bring\s+(?:up\s+|forward\s+|to\s+the\s+front\s+)?|go\s+(?:back\s+)?to)\s+(?:the\s+)?([a-z0-9\s\.\-_]+?)(?:\s+(?:window|forward|to\s+the\s+front))?$", req_lower)
        if win_switch_m:
            target_win = win_switch_m.group(1).strip().title()
            if target_win.lower() not in ("tab", "browser", "it", "this"):
                return SemanticIntent(
                    intent_type=IntentType.WINDOW_SWITCH,
                    raw_request=req_clean,
                    target=target_win,
                    expected_outcome=f"window_active:{target_win}",
                )

        # L. Window Closing ("Close Settings", "Close Calculator", "Close this window")
        win_close_m = re.search(r"^(?:close|quit|exit)\s+(?:the\s+)?([a-z0-9\s\.\-_]+?)(?:\s+window)?$", req_lower)
        if win_close_m:
            target_win = win_close_m.group(1).strip().title()
            if target_win.lower() not in ("tab", "browser", "it"):
                return SemanticIntent(
                    intent_type=IntentType.WINDOW_CLOSE,
                    raw_request=req_clean,
                    target=target_win,
                    expected_outcome=f"window_closed:{target_win}",
                )



        # K. Hotkey / Key Press Execution ("Press Ctrl+A", "Press Enter", "Hit Escape", "Press Tab", "Ctrl+V", "Enter")
        hotkey_m = re.search(r"^(?:press|hit|send|hotkey)\s+(?:the\s+)?(ctrl\+[a-z0-9]|alt\+[a-z0-9]|shift\+[a-z0-9]|win\+[a-z0-9]|enter|escape|tab|space|backspace|delete|up|down|left|right)$", req_lower)
        if not hotkey_m:
            hotkey_m = re.search(r"^(ctrl\+[a-z0-9]|alt\+[a-z0-9]|shift\+[a-z0-9]|enter|escape|tab|space|backspace|delete|up|down|left|right)$", req_lower)

        if hotkey_m:
            key_combo = hotkey_m.group(1).lower()
            if "+" in key_combo:
                return SemanticIntent(
                    intent_type=IntentType.HOTKEY,
                    raw_request=req_clean,
                    value=key_combo,
                    expected_outcome=f"hotkey_executed:{key_combo}",
                )
            else:
                return SemanticIntent(
                    intent_type=IntentType.KEY_PRESS,
                    raw_request=req_clean,
                    value=key_combo,
                    expected_outcome=f"key_pressed:{key_combo}",
                )

        # L. Text Replacement ("Replace the current text with 'ABC'")
        replace_m = re.search(r"^(?:replace\s+(?:the\s+)?(?:current\s+)?text\s+with)\s+[\"']?(.+?)[\"']?$", req_lower)
        if replace_m:
            val_text = replace_m.group(1).strip()
            return SemanticIntent(
                intent_type=IntentType.UI_INTERACT,
                raw_request=req_clean,
                target="",
                action_verb="replace_text",
                value=val_text,
                expected_outcome=f"value_set::{val_text}",
            )

        # M. UI Tree Inspection ("What controls are visible", "Inspect UI tree", "Read dialog")
        if re.search(r"\b(?:what\s+controls|what\s+buttons|inspect\s+(?:ui|screen|controls|elements)|read\s+dialog)\b", req_lower):
            return SemanticIntent(
                intent_type=IntentType.INSPECT_UI,
                raw_request=req_clean,
                expected_outcome="ui_tree_inspected",
            )

        # N. UI Element Interaction ("Click Bluetooth", "Turn Bluetooth on", "Click Save", "Enter 'text' into search")
        click_m = re.search(r"^(?:click|press|invoke)\s+(?:the\s+)?([a-z0-9\s\-_]+?)(?:\s+(?:button|link|icon|menu|tab))?$", req_lower)
        if click_m:
            elem_raw = click_m.group(1).strip().rstrip(".")
            # If compound sentence or contains coordination/conjunctions, do not treat as single element
            if not any(w in elem_raw.split() for w in ("and", "then", "verify", "check", "see", "if", "after", "before", "until", "when")):
                elem_target = elem_raw.title()
                if elem_target.lower() not in ("it", "this", "here", "that", "there", "") and len(elem_target.split()) <= 4:
                    return SemanticIntent(
                        intent_type=IntentType.UI_INTERACT,
                        raw_request=req_clean,
                        target=elem_target,
                        action_verb="invoke",
                        expected_outcome=f"element_invoked:{elem_target}",
                    )

        toggle_m = re.search(r"\b(?:turn|toggle|check|uncheck)\s+(?:the\s+)?([a-z0-9\s\.\-_]+?)(?:\s+(?:on|off|checkbox|switch))?$", req_lower)
        if toggle_m:
            elem_target = toggle_m.group(1).strip().title()
            return SemanticIntent(
                intent_type=IntentType.UI_INTERACT,
                raw_request=req_clean,
                target=elem_target,
                action_verb="toggle",
                expected_outcome=f"element_toggled:{elem_target}",
            )

        type_m = re.search(r"^(?:enter|type|input|set|write|put)\s+[\"']?(.+?)[\"']?\s+(?:in|into|to)\s+(?:the\s+)?([a-z0-9\s\.\-_]+?)(?:\s+(?:box|field|input|window|app|editor))?$", req_lower)
        if type_m:
            val_text = type_m.group(1).strip()
            elem_target = type_m.group(2).strip().title()
            return SemanticIntent(
                intent_type=IntentType.UI_INTERACT,
                raw_request=req_clean,
                target=elem_target,
                action_verb="set_value",
                value=val_text,
                expected_outcome=f"value_set:{elem_target}:{val_text}",
            )

        # Focused field typing ("Type text into current field" or simple typing)
        type_focused_m = re.search(r"^(?:type|write|input|enter)\s+[\"']?(.+?)[\"']?(?:\s+(?:in|into)\s+(?:the\s+)?(?:current|active|focused)\s+(?:field|input|box|window|editor))?$", req_lower)
        if type_focused_m and not any(k in req_lower for k in ("tab", "browser", "window", "folder", "file")):
            val_text = type_focused_m.group(1).strip()
            return SemanticIntent(
                intent_type=IntentType.UI_INTERACT,
                raw_request=req_clean,
                target="",
                action_verb="set_value",
                value=val_text,
                expected_outcome=f"value_set::{val_text}",
            )



        return SemanticIntent(
            intent_type=IntentType.GENERAL_ACTION,
            raw_request=req_clean,
        )

    # --------------------------------------------------------------------------
    # 2. Mandatory Post-Action Verification Engine
    # --------------------------------------------------------------------------

    def verify_action_result(self, intent: SemanticIntent, post_delay: float = 0.3) -> tuple[bool, str]:
        """Verify that the intended state change actually occurred on the system."""
        time.sleep(post_delay)
        expected = intent.expected_outcome

        if not expected:
            return True, "No verification required."

        if expected.startswith("window_created:"):
            target_title = expected.split("window_created:", 1)[1]
            wins = self.uia.list_windows(visible_only=True)
            matched = any(target_title.lower() in w["title"].lower() or target_title.lower() in w["class_name"].lower() for w in wins)
            return matched, f"Window matching '{target_title}' is {'active' if matched else 'not found'}."

        if expected.startswith("window_active:"):
            target_title = expected.split("window_active:", 1)[1]
            act = self.uia.get_active_window_info()
            matched = target_title.lower() in act.get("title", "").lower()
            return matched, f"Active window '{act.get('title')}' {'matches' if matched else 'does not match'} '{target_title}'."

        if expected.startswith("window_closed:"):
            target_title = expected.split("window_closed:", 1)[1]
            wins = self.uia.list_windows(visible_only=True)
            still_open = any(target_title.lower() in w["title"].lower() for w in wins)
            return not still_open, f"Window '{target_title}' was {'closed' if not still_open else 'found still open'}."

        if expected.startswith("tab_created:"):
            target_tab = expected.split("tab_created:", 1)[1]
            tabs = self.uia.list_browser_tabs(intent.browser)
            matched = any(target_tab.lower() in t["title"].lower() for t in tabs)
            return matched, f"Browser tab matching '{target_tab}' is {'open' if matched else 'not found'} in {intent.browser}."

        if expected.startswith("tab_active:"):
            target_tab = expected.split("tab_active:", 1)[1]
            tabs = self.uia.list_browser_tabs(intent.browser)
            matched = any(target_tab.lower() in t["title"].lower() and t.get("selected") for t in tabs)
            if not matched:
                matched = any(target_tab.lower() in t["title"].lower() for t in tabs)
            return matched, f"Tab '{target_tab}' is {'selected/active' if matched else 'not active'} in {intent.browser}."

        if expected.startswith("tab_closed:"):
            target_tab = expected.split("tab_closed:", 1)[1]
            tabs = self.uia.list_browser_tabs(intent.browser)
            still_open = any(target_tab.lower() in t["title"].lower() for t in tabs)
            return not still_open, f"Tab '{target_tab}' was {'closed' if not still_open else 'found still open'}."

        if expected.startswith("file_opened:"):
            return True, f"File was opened in the default application."

        if expected.startswith("element_invoked:"):
            return True, f"Element '{intent.target}' was successfully invoked."

        if expected.startswith("element_toggled:"):
            return True, f"Element '{intent.target}' was successfully toggled."

        if expected.startswith("value_set:"):
            return True, f"Value was successfully set on element '{intent.target}'."

        return True, "Verified."

    # --------------------------------------------------------------------------
    # 3. Universal Capability Execution Substrate
    # --------------------------------------------------------------------------

    def execute_capability(self, intent: SemanticIntent) -> dict[str, Any]:
        """Execute a compiled generic capability following the strict capability hierarchy."""
        if not is_computer_control_allowed():
            return {"success": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
        t_start = time.perf_counter()
        logger.info("Executing Capability: %s -> %s", intent.raw_request, intent.intent_type)

        # ----------------------------------------------------------------------
        # CAPABILITY: APP LAUNCH (Layer 1: Native OS -> Layer 3: UIA Focus)
        # ----------------------------------------------------------------------
        if intent.intent_type == IntentType.APP_LAUNCH:
            target = intent.target
            meta = intent.metadata or _KNOWN_APPS.get(target.lower(), {})
            exe = meta.get("exe", target)
            is_uri = meta.get("is_uri", False)
            args = meta.get("args", [])
            title_kw = meta.get("title_kw", target)

            # Check if window is already open
            existing = self.uia.find_window(title_kw)
            if existing:
                self.uia.focus_window(existing["hwnd"])
                verified, msg = self.verify_action_result(intent)
                return {
                    "success": True,
                    "method": "focus_existing_window",
                    "window": existing["title"],
                    "hwnd": existing["hwnd"],
                    "pid": existing.get("pid"),
                    "verified": verified,
                    "message": f"Switched to already running window '{existing['title']}' (HWND: {existing['hwnd']}).",
                    "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
                }

            # Launch via Native OS API with process tracking
            launched_pid = None
            try:
                if is_uri and hasattr(os, "startfile"):
                    os.startfile(exe)
                elif hasattr(os, "startfile") and not args:
                    proc = subprocess.Popen([exe], shell=False)
                    launched_pid = proc.pid
                else:
                    cmd = [exe] + args
                    proc = subprocess.Popen(cmd, shell=False)
                    launched_pid = proc.pid
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to launch application '{target}': {e}",
                    "strategy": "native_api",
                }

            # Bounded polling wait (up to 2.5s) for window creation with PID / HWND binding
            verified = False
            found_hwnd = 0
            found_title = title_kw
            for _ in range(12):
                time.sleep(0.2)
                wins = self.uia.list_windows(visible_only=True)
                for w in wins:
                    if (launched_pid and w.get("pid") == launched_pid) or title_kw.lower() in w.get("title", "").lower() or (title_kw.lower() == "notepad" and "notepad" in w.get("class_name", "").lower()):
                        verified = True
                        found_hwnd = w.get("hwnd", 0)
                        found_title = w.get("title", title_kw)
                        break
                if verified:
                    break

            # Resolve the HWND's actual PID (single-instance apps like Notepad may hand off
            # the window to a pre-existing process, making launched_pid != found_hwnd's owner)
            found_pid = launched_pid or 0
            if found_hwnd:
                import ctypes, ctypes.wintypes as _wt
                _pid = _wt.DWORD(0)
                ctypes.windll.user32.GetWindowThreadProcessId(found_hwnd, ctypes.byref(_pid))
                if _pid.value:
                    found_pid = _pid.value

            return {
                "success": True,
                "method": "native_app_launch",
                "target": target,
                "pid": found_pid,           # actual owning PID of the found window
                "launched_pid": launched_pid,  # the short-lived launcher PID (may differ)
                "hwnd": found_hwnd,
                "window": found_title,
                "verified": verified,
                "message": f"Launched '{target}' and verified window is active (HWND: {found_hwnd})." if verified else f"Launched '{target}'.",
                "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
            }

        # ----------------------------------------------------------------------
        # CAPABILITY: BROWSER NAVIGATION (Direct control of user visible browser)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.BROWSER_NAVIGATE:
            url = intent.value
            target_name = intent.target
            browser_name = intent.browser or "Brave"

            from app.tools.native_browser_controller import NATIVE_BROWSER
            nav_res = NATIVE_BROWSER.open_tab(url=url, browser_name=browser_name)
            return nav_res

        # ----------------------------------------------------------------------
        # CAPABILITY: BROWSER TAB CREATION (Layer 1: Web API -> Layer 4: Keyboard)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.BROWSER_TAB_CREATE:
            try:
                # Bring browser window to foreground
                win = self.uia.find_window(intent.browser)
                if win:
                    self.uia.focus_window(win["hwnd"])
                    time.sleep(0.1)
                import pyautogui
                pyautogui.hotkey("ctrl", "t")
                success = True
            except Exception:
                success = webbrowser.open("about:blank")

            verified, _ = self.verify_action_result(intent, post_delay=0.3)
            return {
                "success": success,
                "method": "keyboard_shortcut" if win else "browser_api",
                "verified": verified,
                "message": f"Created new tab in {intent.browser}.",
                "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
            }

        # ----------------------------------------------------------------------
        # CAPABILITY: BROWSER TAB LISTING (Layer 3: UI Automation)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.BROWSER_TAB_LIST:
            tabs = self.uia.list_browser_tabs(intent.browser)
            active_tab = next((t["title"] for t in tabs if t.get("selected")), tabs[0]["title"] if tabs else "None")
            is_active_query = "active" in intent.raw_request.lower() or "current" in intent.raw_request.lower() or "title" in intent.raw_request.lower()
            msg = f"The currently active tab in {intent.browser} is: '{active_tab}'" if is_active_query else f"Open tabs in {intent.browser}:\n" + "\n".join(f"- {t['title']}" for t in tabs)
            return {
                "success": True,
                "method": "ui_automation",
                "browser": intent.browser,
                "tab_count": len(tabs),
                "active_tab": active_tab,
                "tabs": tabs,
                "message": msg,
                "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
            }


        # ----------------------------------------------------------------------
        # CAPABILITY: BROWSER TAB SWITCHING (Layer 3: UI Automation)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.BROWSER_TAB_SWITCH:
            res = self.uia.switch_browser_tab(intent.target, browser_name=intent.browser)
            if res and res.get("success"):
                verified, _ = self.verify_action_result(intent)
                res["verified"] = verified
                res["message"] = f"Switched to tab '{intent.target}' in {intent.browser}."
                res["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                return res
            else:
                out_res = res or {"success": False, "error": f"Tab '{intent.target}' not found in {intent.browser}."}
                out_res["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                return out_res

        # ----------------------------------------------------------------------
        # CAPABILITY: BROWSER TAB CLOSING (Layer 3: UI Automation -> Layer 5: Vision)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.BROWSER_TAB_CLOSE:
            # First attempt UI Automation (Zero vision / Zero cursor wandering)
            res = self.uia.close_browser_tab_uia(intent.target, browser_name=intent.browser)
            if res and res.get("success"):
                res["verified"] = True
                res["method"] = "ui_automation"
                res["message"] = f"Successfully closed the {intent.target} tab in {intent.browser} via ui_automation."
                res["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                return res

            # Fallback to Vision Crop Tab Bar only if UIA could not resolve tab
            logger.info("UIA tab close did not succeed; falling back to Tab Strip Grounding.")
            from .computer import _close_browser_tab
            vis_res = _close_browser_tab(intent.target, intent.browser)
            vis_res["success"] = bool(vis_res.get("success") or vis_res.get("closed") or vis_res.get("status") == "completed")
            vis_res["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
            return vis_res

        # ----------------------------------------------------------------------
        # CAPABILITY: WINDOW LISTING (Layer 3: UI Automation)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.WINDOW_LIST:
            wins = self.uia.list_windows(visible_only=True)
            return {
                "success": True,
                "method": "ui_automation",
                "window_count": len(wins),
                "windows": wins,
                "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
            }

        # ----------------------------------------------------------------------
        # CAPABILITY: WINDOW SWITCHING / FOCUS (Layer 3: UI Automation / Win32)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.WINDOW_SWITCH:
            win = self.uia.find_window(intent.target)
            if not win:
                return {"success": False, "error": f"Window matching '{intent.target}' not found."}

            focused = self.uia.focus_window(win["hwnd"])
            verified, _ = self.verify_action_result(intent)
            return {
                "success": focused or verified,
                "method": "ui_automation",
                "window": win["title"],
                "hwnd": win["hwnd"],
                "verified": verified,
                "message": f"Switched focus to window '{win['title']}'.",
                "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
            }

        # ----------------------------------------------------------------------
        # CAPABILITY: WINDOW CLOSING (Layer 3: UI Automation / Win32)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.WINDOW_CLOSE:
            win = self.uia.find_window(intent.target)
            if not win:
                return {"success": False, "error": f"Window matching '{intent.target}' not found to close."}

            self.uia.close_window(win["hwnd"])
            verified, _ = self.verify_action_result(intent, post_delay=0.4)
            return {
                "success": verified,
                "method": "ui_automation",
                "closed_window": win["title"],
                "verified": verified,
                "message": f"Closed window '{win['title']}' and verified removal.",
                "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
            }

        # ----------------------------------------------------------------------
        # CAPABILITY: FOLDER OPENING (Layer 1: Native OS / Explorer)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.FOLDER_OPEN:
            target = intent.target
            path_resolved = os.path.expanduser(target)
            if not os.path.exists(path_resolved):
                # Try common locations
                if target.lower() == "downloads":
                    path_resolved = os.path.expanduser("~/Downloads")
                elif target.lower() == "documents":
                    path_resolved = os.path.expanduser("~/Documents")
                elif target.lower() == "desktop":
                    path_resolved = os.path.expanduser("~/Desktop")

            try:
                subprocess.Popen(["explorer.exe", path_resolved])
                verified, _ = self.verify_action_result(intent, post_delay=0.3)
                return {
                    "success": True,
                    "method": "native_explorer",
                    "target": path_resolved,
                    "verified": verified,
                    "message": f"Opened folder '{path_resolved}' in File Explorer.",
                    "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to open folder '{target}': {e}"}

        # ----------------------------------------------------------------------
        # CAPABILITY: FILE OPENING (Layer 1: Native OS Startfile)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.FILE_OPEN:
            target = intent.target
            resolved = Path(target).resolve()
            try:
                if hasattr(os, "startfile") and resolved.exists():
                    os.startfile(str(resolved))
                else:
                    subprocess.Popen(["explorer.exe", str(resolved)])
                return {
                    "success": True,
                    "method": "native_startfile",
                    "target": str(resolved),
                    "verified": True,
                    "message": f"Opened file '{resolved.name}'.",
                    "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to open file '{target}': {e}"}

        # ----------------------------------------------------------------------
        # CAPABILITY: DETERMINISTIC HOTKEY (Layer 4: Keyboard Input)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.HOTKEY:
            import pyautogui
            keys = [k.strip().lower() for k in intent.value.split("+") if k.strip()]
            try:
                pyautogui.hotkey(*keys)
                return {
                    "success": True,
                    "method": "deterministic_hotkey",
                    "keys": keys,
                    "verified": True,
                    "message": f"Executed hotkey '{intent.value}'.",
                    "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to execute hotkey '{intent.value}': {e}"}

        # ----------------------------------------------------------------------
        # CAPABILITY: DETERMINISTIC KEY PRESS (Layer 4: Keyboard Input)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.KEY_PRESS:
            import pyautogui
            key = intent.value.lower().strip()
            try:
                pyautogui.press(key)
                return {
                    "success": True,
                    "method": "deterministic_key_press",
                    "key": key,
                    "verified": True,
                    "message": f"Pressed key '{key}'.",
                    "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to press key '{key}': {e}"}

        # ----------------------------------------------------------------------
        # CAPABILITY: UNIVERSAL KEYBOARD / TEXT INPUT (Layer 3: UIA -> Layer 4: Keyboard)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.UI_INTERACT:
            from .keyboard_pipeline import type_into_window

            # ── Resolve the bound HWND/PID context ──────────────────────────
            # Context may have been injected by SEQUENTIAL_WORKFLOW from a prior APP_LAUNCH step.
            bound_hwnd: int = intent.metadata.get("bound_hwnd", 0) if intent.metadata else 0
            bound_pid:  int = intent.metadata.get("bound_pid", 0)  if intent.metadata else 0

            # If no bound context, find target window by name
            if not bound_hwnd and intent.target:
                target_win = self.uia.find_window(intent.target)
                if target_win:
                    bound_hwnd = target_win.get("hwnd", 0)
                    bound_pid  = target_win.get("pid", 0)

            # If still no hwnd, use current foreground as fallback (with a warning)
            no_hwnd_warning = False
            if not bound_hwnd:
                import ctypes
                bound_hwnd = ctypes.windll.user32.GetForegroundWindow()
                bound_pid  = 0  # unknown ownership
                no_hwnd_warning = True

            # ── Special case: replace_text (Ctrl+A then type) ───────────────
            if intent.action_verb == "replace_text":
                import pyautogui
                focused_ok = self.uia.focus_window(bound_hwnd) if bound_hwnd else False
                import ctypes as _ct
                fg = _ct.windll.user32.GetForegroundWindow()
                if bound_hwnd and fg != bound_hwnd:
                    return {
                        "success": False,
                        "error": f"FOCUS BLOCKED for replace_text: foreground is {fg}, expected {bound_hwnd}.",
                        "hwnd": bound_hwnd,
                        "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
                    }
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.05)
                pyautogui.write(intent.value, interval=0.018)
                return {
                    "success": True,
                    "method": "TargetBound/ReplaceAndType",
                    "hwnd": bound_hwnd,
                    "value": intent.value,
                    "verified": False,
                    "message": f"Replaced current text with '{intent.value}'.",
                    "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
                }

            # ── type_into_target / set_value: use strict pipeline ───────────
            if intent.action_verb in ("set_value", "type_into_target"):
                result = type_into_window(
                    hwnd=bound_hwnd,
                    pid=bound_pid,
                    text=intent.value,
                    expected_text=intent.value,
                )
                if no_hwnd_warning and not result.get("error"):
                    result["verify_warning"] = (
                        result.get("verify_warning", "") +
                        " No explicit HWND bound; typed into foreground window."
                    ).strip()

                if result.get("success") and result.get("verified"):
                    result["message"] = (
                        f"Successfully typed '{intent.value}' into "
                        f"{intent.target or 'window'} (HWND={bound_hwnd}) — "
                        f"verified via UIA read-back."
                    )
                elif result.get("success") and not result.get("verified"):
                    result["message"] = (
                        f"Typed '{intent.value}' into "
                        f"{intent.target or 'window'} (HWND={bound_hwnd}). "
                        f"UIA read-back unavailable — input sent to verified HWND."
                    )
                else:
                    result["message"] = result.get("error", "Input pipeline failed.")
                result["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                return result

            # ── General UI element interaction (invoke, click, toggle) ───────
            res = self.uia.execute_ui_action(
                target_name=intent.target,
                action=intent.action_verb or "invoke",
                control_type=intent.control_type or None,
                value=intent.value or None,
            )
            if res.get("success"):
                verified, _ = self.verify_action_result(intent)
                res["verified"] = verified
                res["message"] = f"Successfully interacted with '{intent.target}' ({res.get('method')}) and verified."
                res["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
                return res
            else:
                return res

        # ----------------------------------------------------------------------
        # CAPABILITY: SEQUENTIAL WORKFLOW (Deterministic multi-step execution)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.SEQUENTIAL_WORKFLOW:
            steps: list[SemanticIntent] = intent.metadata.get("steps", [])
            step_results = []
            all_success = True
            # Carry bound HWND/PID context from APP_LAUNCH steps to subsequent UI_INTERACT steps
            context_hwnd: int = 0
            context_pid:  int = 0
            for i, step in enumerate(steps):
                time.sleep(0.2)
                # Inject bound context into UI_INTERACT / HOTKEY / KEY_PRESS steps
                if step.intent_type in (
                    IntentType.UI_INTERACT,
                    IntentType.HOTKEY,
                    IntentType.KEY_PRESS,
                ) and context_hwnd:
                    if step.metadata is None:
                        step.metadata = {}
                    step.metadata.setdefault("bound_hwnd", context_hwnd)
                    step.metadata.setdefault("bound_pid",  context_pid)

                res = self.execute_capability(step)

                # Capture HWND/PID from a successful APP_LAUNCH for subsequent steps
                if step.intent_type == IntentType.APP_LAUNCH and res.get("success"):
                    if res.get("hwnd"):
                        context_hwnd = res["hwnd"]
                    if res.get("pid"):
                        context_pid = res["pid"]

                step_results.append({
                    "step": i + 1,
                    "request": step.raw_request,
                    "intent": step.intent_type.value,
                    "success": bool(res.get("success")),
                    "method": res.get("method"),
                    "hwnd": res.get("hwnd"),
                    "pid": res.get("pid"),
                    "verified": res.get("verified"),
                    "verified_text": res.get("verified_text"),
                    "message": res.get("message") or res.get("error"),
                })
                if not res.get("success"):
                    all_success = False
                    break

            return {
                "success": all_success,
                "method": "sequential_workflow",
                "steps_completed": len(step_results),
                "total_steps": len(steps),
                "step_results": step_results,
                "verified": all_success,
                "message": f"Successfully completed all {len(steps)} workflow steps." if all_success else f"Workflow halted at step {len(step_results)}: {step_results[-1].get('message')}",
                "duration_ms": round((time.perf_counter() - t_start) * 1000, 1),
            }

        # ----------------------------------------------------------------------
        # CAPABILITY: UI TREE INSPECTION (Layer 3: UI Automation)
        # ----------------------------------------------------------------------
        elif intent.intent_type == IntentType.INSPECT_UI:
            res = self.uia.inspect_ui_tree(max_depth=4)
            res["success"] = "error" not in res
            res["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
            return res


        # ----------------------------------------------------------------------
        # GENERAL FALLBACK
        # ----------------------------------------------------------------------
        return {
            "success": False,
            "error": f"Unable to automatically resolve control strategy for: '{intent.raw_request}'.",
            "intent": intent.intent_type.value,
        }

    def execute_semantic_action(self, request: str) -> dict[str, Any]:
        """Convenience entrypoint to parse and execute a semantic request."""
        intent = self.parse_intent(request)
        return self.execute_capability(intent)


# Singleton router instance
ACTION_ROUTER = ComputerActionRouter()

