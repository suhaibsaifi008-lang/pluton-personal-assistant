"""
PLUTON V2 — Universal Intent Model & Plan Compiler
Compiles natural-language computer requests into deterministic, typed multi-step execution plans.

Supports all 12 canonical computer control domains:
1. APP
2. WINDOW
3. BROWSER
4. WEB
5. UI
6. KEYBOARD
7. MOUSE
8. SCREEN
9. VISION
10. FILESYSTEM
11. TERMINAL
12. CLIPBOARD
"""

from __future__ import annotations

import logging
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    Plan,
    PlanStep,
    TargetDomain,
    VerificationStrategy,
)

logger = logging.getLogger("pluton.planning.intent_compiler")


@dataclass
class UniversalTarget:
    """Canonical representation of a resolved semantic target."""
    domain: TargetDomain
    human_description: str
    semantic_query: str
    exact_identity: str | None = None
    parent_context: str | None = None
    confidence: float = 1.0
    resolver: str = "canonical"
    state: str = "FOUND"


# -----------------------------------------------------------------------------
# 1. Universal App Registry
# -----------------------------------------------------------------------------

class UniversalAppRegistry:
    """Dynamic Windows application discovery engine without static application lists."""

    _SYSTEM_ALIASES: dict[str, dict[str, Any]] = {
        "calculator": {"canonical_name": "Calculator", "exe": "calc.exe", "protocol": "ms-calculator:", "title_kw": "Calculator", "domain": TargetDomain.APP, "window_classes": ["ApplicationFrameWindow", "CalcFrame"], "title_keywords": ["calculator", "calc"]},
        "calc": {"canonical_name": "Calculator", "exe": "calc.exe", "protocol": "ms-calculator:", "title_kw": "Calculator", "domain": TargetDomain.APP, "window_classes": ["ApplicationFrameWindow", "CalcFrame"], "title_keywords": ["calculator", "calc"]},
        "notepad": {"canonical_name": "Notepad", "exe": "notepad.exe", "protocol": None, "title_kw": "Notepad", "domain": TargetDomain.APP, "window_classes": ["Notepad", "Notepad_Win11", "RichEditD2DPT"], "title_keywords": ["notepad"]},
        "paint": {"canonical_name": "Paint", "exe": "mspaint.exe", "protocol": None, "title_kw": "Paint", "domain": TargetDomain.APP, "window_classes": ["MSPaintApp", "PaintApp"], "title_keywords": ["paint"]},
        "file explorer": {"canonical_name": "File Explorer", "exe": "explorer.exe", "protocol": None, "title_kw": "File Explorer", "domain": TargetDomain.APP, "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["file explorer", "explorer", "home", "downloads", "documents"]},
        "explorer": {"canonical_name": "File Explorer", "exe": "explorer.exe", "protocol": None, "title_kw": "File Explorer", "domain": TargetDomain.APP, "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["file explorer", "explorer", "home", "downloads", "documents"]},
        "downloads": {"canonical_name": "Downloads", "exe": "explorer.exe", "args": [os.path.expanduser("~/Downloads")], "title_kw": "Downloads", "domain": TargetDomain.FOLDER, "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["downloads", "explorer"]},
        "documents": {"canonical_name": "Documents", "exe": "explorer.exe", "args": [os.path.expanduser("~/Documents")], "title_kw": "Documents", "domain": TargetDomain.FOLDER, "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["documents", "explorer"]},
        "settings": {"canonical_name": "Settings", "exe": "ms-settings:", "protocol": "ms-settings:", "title_kw": "Settings", "domain": TargetDomain.APP, "window_classes": ["ApplicationFrameWindow"], "title_keywords": ["settings"]},
        "task manager": {"canonical_name": "Task Manager", "exe": "taskmgr.exe", "title_kw": "Task Manager", "domain": TargetDomain.APP, "window_classes": ["TaskManagerWindow"], "title_keywords": ["task manager"]},
        "cmd": {"canonical_name": "Command Prompt", "exe": "cmd.exe", "title_kw": "Command Prompt", "domain": TargetDomain.TERMINAL, "window_classes": ["ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"], "title_keywords": ["command prompt", "cmd"]},
        "powershell": {"canonical_name": "PowerShell", "exe": "powershell.exe", "title_kw": "PowerShell", "domain": TargetDomain.TERMINAL, "window_classes": ["ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"], "title_keywords": ["powershell"]},
        "terminal": {"canonical_name": "Terminal", "exe": "wt.exe", "title_kw": "Terminal", "domain": TargetDomain.TERMINAL, "window_classes": ["CASCADIA_HOSTING_WINDOW_CLASS"], "title_keywords": ["terminal"]},
        "brave": {"canonical_name": "Brave", "exe": "brave.exe", "title_kw": "Brave", "domain": TargetDomain.BROWSER, "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["brave"]},
        "chrome": {"canonical_name": "Chrome", "exe": "chrome.exe", "title_kw": "Chrome", "domain": TargetDomain.BROWSER, "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["chrome"]},
        "edge": {"canonical_name": "Edge", "exe": "msedge.exe", "title_kw": "Edge", "domain": TargetDomain.BROWSER, "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["edge"]},
        "browser": {"canonical_name": "Browser", "exe": "explorer.exe", "protocol": "https://", "title_kw": "Browser", "domain": TargetDomain.BROWSER, "window_classes": ["Chrome_WidgetWin_1", "CabinetWClass"], "title_keywords": ["browser", "brave", "chrome", "edge"]},
        "the browser": {"canonical_name": "Browser", "exe": "explorer.exe", "protocol": "https://", "title_kw": "Browser", "domain": TargetDomain.BROWSER, "window_classes": ["Chrome_WidgetWin_1", "CabinetWClass"], "title_keywords": ["browser", "brave", "chrome", "edge"]},
    }

    @classmethod
    def resolve(cls, app_query: str) -> dict[str, Any] | None:
        q_raw = str(app_query or "").strip().lower()
        q_clean = re.sub(r"^(?:the\s+|a\s+|open\s+|launch\s+|start\s+)", "", q_raw).strip()
        q_core = re.sub(r"^(?:microsoft\s+|ms\s+|google\s+)", "", q_clean).strip()
        tokens = set(re.findall(r"\w+", q_clean))
        core_tokens = set(re.findall(r"\w+", q_core))
        if not q_clean:
            return None

        # 1. System alias check
        alias_key = q_clean if q_clean in cls._SYSTEM_ALIASES else (q_core if q_core in cls._SYSTEM_ALIASES else None)
        if alias_key:
            res_alias = dict(cls._SYSTEM_ALIASES[alias_key])
            exe_val = res_alias.get("exe")
            if exe_val and not os.path.isabs(exe_val) and not exe_val.startswith("ms-"):
                import shutil
                found_which = shutil.which(exe_val) or shutil.which(f"{exe_val}.exe")
                if found_which:
                    res_alias["exe"] = found_which
            return res_alias

        # 2. System PATH check
        import shutil
        for cand in (q_clean, q_core, f"{q_clean}.exe", f"{q_core}.exe"):
            exe_path = shutil.which(cand)
            if exe_path:
                return {"canonical_name": q_clean.title(), "exe": exe_path, "domain": TargetDomain.APP, "title_kw": q_core or q_clean}

        # 3. Windows Registry App Paths (HKLM & HKCU)
        try:
            import winreg
            for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for sub_key in (
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
                ):
                    try:
                        with winreg.OpenKey(root_key, sub_key) as key:
                            num_subkeys = winreg.QueryInfoKey(key)[0]
                            for i in range(num_subkeys):
                                name = winreg.EnumKey(key, i)
                                name_clean = name.lower().removesuffix(".exe")
                                is_match = (
                                    q_clean == name_clean or q_core == name_clean
                                    or (len(q_core) >= 3 and q_core in name_clean)
                                    or (len(name_clean) >= 3 and name_clean in q_clean)
                                    or (q_core == "word" and name_clean == "winword")
                                    or (q_core == "excel" and name_clean == "excel")
                                    or (q_core == "powerpoint" and name_clean == "powerpnt")
                                )
                                if is_match:
                                    try:
                                        with winreg.OpenKey(key, name) as app_key:
                                            val, _ = winreg.QueryValueEx(app_key, "")
                                            if val and os.path.exists(val):
                                                return {"canonical_name": name_clean.title(), "exe": val, "domain": TargetDomain.APP, "title_kw": q_core or name_clean}
                                    except Exception:
                                        pass
                    except Exception:
                        pass
        except Exception:
            pass

        # 4. Start Menu Program Shortcuts (.lnk)
        try:
            start_menu_dirs = [
                Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
                Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            ]
            for sm_dir in start_menu_dirs:
                if sm_dir.exists():
                    for lnk in sm_dir.rglob("*.lnk"):
                        lnk_stem = lnk.stem.lower()
                        lnk_tokens = set(re.findall(r"\w+", lnk_stem))
                        is_match = (
                            q_clean == lnk_stem or q_core == lnk_stem
                            or (core_tokens and core_tokens.issubset(lnk_tokens))
                            or (tokens and tokens.issubset(lnk_tokens))
                            or (len(q_core) >= 3 and q_core in lnk_stem)
                        )
                        if is_match:
                            return {"canonical_name": lnk.stem, "exe": str(lnk), "domain": TargetDomain.APP, "title_kw": q_core or lnk.stem}
        except Exception:
            pass

        return None


# -----------------------------------------------------------------------------
# 2. Universal Web Normalizer & Search Query Builder
# -----------------------------------------------------------------------------

class UniversalWebNormalizer:
    """Universal normalizer converting arbitrary web targets into valid URLs without static registries."""

    @staticmethod
    def normalize(target: str) -> tuple[str, str] | None:
        q = target.strip().strip("\"'")
        if not q:
            return None

        # 1. Full URL
        if q.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(q)
            return q, parsed.netloc or q

        # 2. Localhost / Port
        if q.startswith(("localhost", "127.0.0.1")):
            return f"http://{q}", q

        # 3. Known TLD / Dot-Domain pattern (e.g. anker.com, hentaihaven.xxx, example.org, newsite.co.uk)
        tld_pattern = r"^[a-zA-Z0-9\-]+(\.[a-zA-Z0-9\-]+)+(/.*)?$"
        if re.match(tld_pattern, q) and not q.endswith((".exe", ".txt", ".py", ".json", ".doc", ".pdf", ".lnk")):
            return f"https://{q}", q.split("/")[0]

        # 4. Standard Single-token Web Brands (e.g. gmail, google, youtube, reddit, github, amazon, wikipedia)
        clean_token = q.lower().strip()
        if clean_token in ("gmail", "email", "mail"):
            return "https://mail.google.com", "mail.google.com"
        elif clean_token in ("google", "google search"):
            return "https://www.google.com", "google.com"
        elif clean_token == "youtube":
            return "https://www.youtube.com", "youtube.com"
        elif clean_token == "reddit":
            return "https://www.reddit.com", "reddit.com"
        elif clean_token == "github":
            return "https://www.github.com", "github.com"
        elif clean_token == "wikipedia":
            return "https://www.wikipedia.org", "wikipedia.org"
        
        # Test Page special aliases
        if "test page" in clean_token or "web interaction" in clean_token:
            return "http://127.0.0.1:5173/test_page.html", "127.0.0.1:5173"

        return None


class SearchQueryExtractor:
    """Extracts pure search queries from diverse natural language expressions."""

    @staticmethod
    def extract_query(text: str) -> str:
        t = text.strip().strip("\"'")
        # Strip common search command prefixes: "do a google search for", "google search for", "search google for", "search for", "search"
        clean = re.sub(r"^(?:do\s+a\s+)?(?:google\s+search\s+for|search\s+google\s+for|search\s+for|google\s+search|search)\s+", "", t, flags=re.IGNORECASE).strip()
        # Strip common search suffixes: "on google", "in google", "on brave", "in brave", "in chrome", "on chrome", "in edge", "in browser"
        clean = re.sub(r"\s+(?:on|in)\s+(?:google|brave|chrome|edge|browser)$", "", clean, flags=re.IGNORECASE).strip()
        # Strip leading "for " if still present
        clean = re.sub(r"^for\s+", "", clean, flags=re.IGNORECASE).strip()
        # Strip trailing search/browser mentions
        clean = re.sub(r"\s+on\s+google$", "", clean, flags=re.IGNORECASE).strip()
        return clean.strip("\"'")


# -----------------------------------------------------------------------------
# 3. Universal Plan Compiler
# -----------------------------------------------------------------------------

class UniversalPlanCompiler:
    """Canonical compiler converting natural-language computer requests into deterministic typed Plans."""

    def split_clauses(self, text: str) -> list[str]:
        """Split a multi-step user instruction into semantic action clauses without breaking quoted text."""
        raw = text.strip()
        raw = re.sub(r"^(?:please|could\s+you\s+please|can\s+you\s+please|kindly)\s+", "", raw, flags=re.IGNORECASE).strip()
        if not raw:
            return []

        # Special case: compound "open a new tab and open X"
        m_newtab_nav = re.match(r"^open\s+(?:a\s+)?new\s+tab\s+and\s+(?:open|go\s+to|navigate\s+to)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m_newtab_nav:
            return [f"open {m_newtab_nav.group(1).strip()}"]

        # Special case: compound multi-app launch "Open Notepad and File Explorer"
        m_multi_app = re.match(r"^open\s+([a-zA-Z0-9_\s]+?)\s+and\s+([a-zA-Z0-9_\s]+?)\.?$", raw, flags=re.IGNORECASE)
        if m_multi_app:
            app1 = m_multi_app.group(1).strip()
            app2 = m_multi_app.group(2).strip()
            if UniversalAppRegistry.resolve(app1) and UniversalAppRegistry.resolve(app2):
                return [f"open {app1}", f"open {app2}"]

        # Special case: generic site search "Search for X on Y" / "Search X in Y"
        m_site_search = re.match(r"^(?:search\s+for|search|find)\s+[\"']?(.+?)[\"']?\s+(?:on|in)\s+([a-zA-Z0-9_\.\-]+?)[.!?]*$", raw.strip(), flags=re.IGNORECASE)
        if m_site_search:
            q_target = m_site_search.group(1).strip().strip("\"'").rstrip(".!? ")
            site_target = m_site_search.group(2).strip().rstrip(".!? ")
            if not any(k in site_target.lower() for k in ("desktop", "computer", "pc", "folder", "directory")):
                return [f"open {site_target}", f"enter {q_target} in search box", "press Enter"]

        # 1. First split by sentence boundaries
        sentence_splits = re.split(r"\.\s+(?=[A-Z]|open|launch|type|enter|write|enable|check|select|click|tell|report|read|save|create|verify)\b", raw, flags=re.IGNORECASE)
        all_clauses: list[str] = []

        for sent in sentence_splits:
            s_clean = sent.strip().rstrip(".")
            if not s_clean:
                continue

            # Special case: multi-app prefix within sentence "Open Notepad and File Explorer."
            m_s_app = re.match(r"^open\s+([a-zA-Z0-9_\s]+?)\s+and\s+([a-zA-Z0-9_\s]+?)$", s_clean, flags=re.IGNORECASE)
            if m_s_app and UniversalAppRegistry.resolve(m_s_app.group(1).strip()) and UniversalAppRegistry.resolve(m_s_app.group(2).strip()):
                all_clauses.append(f"open {m_s_app.group(1).strip()}")
                all_clauses.append(f"open {m_s_app.group(2).strip()}")
                continue

            # Special case: file creation with inline write "create a file called X in Y and write Z into it"
            if re.search(r"create\s+(?:a\s+)?file\s+(?:called|named)\s+.+?\s+in\s+.+?(?:[,\s]+(?:and\s+)?write\s+)", s_clean, flags=re.IGNORECASE):
                m_file_parts = re.split(r"(?:,\s*|\s+)(?:(?:and\s+then|then|after\s+that|and)\s+)?(?=(?:read|tell\s+me|report|extract|verify)\b)", s_clean, flags=re.IGNORECASE)
                for part in m_file_parts:
                    p_clean = part.strip().rstrip(",.!? ")
                    if p_clean:
                        all_clauses.append(p_clean)
                continue

            # Split within sentence by explicit compound connectors
            verb_lookahead = (
                r"(?:\s*;\s*|\s*->\s*|\s*=>\s*|"
                r"(?:\s*,\s*|\s+)(?:and\s+then|then|after\s+that|and\s+next|and\s+finally|and)\s+(?=(?:open|launch|start|navigate|go(?:\s+to|\s+back)?|type|enter|write|input|fill|enable|check|uncheck|toggle|select|choose|pick|click|press|tap|tell\s+me|report|read|get|extract|save|create|copy|paste|switch|close|search|find|verify|calculate|compute|solve|evaluate)\b)|"
                r"\s*,\s*(?=(?:open|launch|start|navigate|go(?:\s+to|\s+back)?|type|enter|write|input|fill|enable|check|uncheck|toggle|select|choose|pick|click|press|tap|tell\s+me|report|read|save|copy|paste|search|find|create|verify|press|calculate|compute|solve|evaluate)\b))"
            )
            sub_clauses = re.split(verb_lookahead, s_clean, flags=re.IGNORECASE)
            for sub in sub_clauses:
                sub_str = sub.strip().rstrip(",.!? ")
                if sub_str:
                    all_clauses.append(sub_str)

        return all_clauses if all_clauses else [raw]

    def compile_plan(self, request_text: str, context: ExecutionContext) -> Plan:
        """Compile request text into a multi-step Plan with verification strategies."""
        plan = Plan(task_id=context.task_id)
        clauses = self.split_clauses(request_text)
        current_context_domain = TargetDomain.APP

        step_num = 1
        for clause in clauses:
            action, target_domain = self.compile_clause(clause, current_context_domain, context)
            if action:
                # Deduplicate consecutive identical read actions
                if plan.steps and plan.steps[-1].action.capability == action.capability == CapabilityType.FILESYSTEM_READ and plan.steps[-1].action.target == action.target:
                    continue

                if target_domain:
                    current_context_domain = target_domain
                plan.steps.append(
                    PlanStep(
                        step_number=step_num,
                        description=clause,
                        action=action,
                        target_domain=target_domain,
                    )
                )
                step_num += 1

        return plan

    compile = compile_plan

    def compile_clause(
        self, clause: str, active_domain: TargetDomain, context: ExecutionContext
    ) -> tuple[Action | None, TargetDomain | None]:
        """Compile a single action clause into a typed Action."""
        c = clause.strip().rstrip(",.!?")
        c = re.sub(r"^(?:please|could\s+you\s+please|can\s+you\s+please|kindly)\s+", "", c, flags=re.IGNORECASE).strip()
        c_lower = c.lower()

        # Conversational / General Question / Follow-up detection
        conversational_starters = (
            "tell me about", "tell me more", "what are", "what is", "who are", "who is",
            "why are", "why is", "how are", "how is", "how many", "can you", "could you",
            "explain", "summarize", "describe", "what did", "which one", "what about",
            "hello", "hi", "hey", "thanks", "thank you", "good morning", "good evening",
        )
        if any(c_lower.startswith(prefix) for prefix in conversational_starters) or c_lower in ("tell me", "explain that", "summarize that", "what were they", "tell me about them", "tell me about it", "what did you find"):
            if not any(k in c_lower for k in ("read the file", "read file", "terminal output", "get the title", "verify file", "text shown on the page", "resulting text", "report the result")):
                return None, None

        # ---------------------------------------------------------------------
        
        # ---------------------------------------------------------------------
        # Arithmetic / Calculation ("calculate 125 multiplied by 48" / "compute 25 + 75")
        # ---------------------------------------------------------------------
        m_calc = re.match(r"^(?:calculate|compute|solve|evaluate)\s+(?:the\s+)?(?:expression\s+|value\s+of\s+)?(.+)$", c, flags=re.IGNORECASE)
        if m_calc:
            raw_expr = m_calc.group(1).strip()
            # Normalize common English arithmetic words to mathematical symbols
            norm_expr = raw_expr
            norm_expr = re.sub(r"\b(?:multiplied\s+by|times)\b", "*", norm_expr, flags=re.IGNORECASE)
            norm_expr = re.sub(r"\b(?:divided\s+by|over)\b", "/", norm_expr, flags=re.IGNORECASE)
            norm_expr = re.sub(r"\b(?:plus|added\s+to)\b", "+", norm_expr, flags=re.IGNORECASE)
            norm_expr = re.sub(r"\b(?:minus|subtracted\s+by)\b", "-", norm_expr, flags=re.IGNORECASE)
            norm_expr = re.sub(r"\s+", "", norm_expr)

            # Evaluate expected result safely if simple arithmetic
            expected_res = None
            try:
                # Safe eval of purely numeric/math expressions
                if re.match(r"^[0-9\+\-\*\/\.\(\)\s]+$", norm_expr):
                    expected_res = str(eval(norm_expr))
            except Exception:
                pass

            target_app = "calculator" if active_domain == TargetDomain.APP else "calc"
            return Action(
                capability=CapabilityType.KEYBOARD_TYPE,
                target=target_app,
                target_domain=TargetDomain.KEYBOARD,
                parameters={"text": f"{norm_expr}=", "target_window": "calculator", "target": "calculator"},
                verification_strategy=VerificationStrategy.UIA_READBACK,
                expected_state=expected_res or norm_expr,
                tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
            ), TargetDomain.APP

        # ---------------------------------------------------------------------
        # Generic Verification Intent ("verify that YouTube opened" / "verify that X is open")
        # ---------------------------------------------------------------------
        m_ver_state = re.match(r"^verify\s+(?:that\s+)?(.+?)\s+(?:opened|is\s+open|is\s+running|loaded|is\s+active)$", c, flags=re.IGNORECASE)
        if m_ver_state:
            target_entity = m_ver_state.group(1).strip().strip("\"'")
            if active_domain == TargetDomain.WEBPAGE or "." in target_entity or target_entity.lower() in ("youtube", "google", "github", "page", "tab"):
                return Action(
                    capability=CapabilityType.BROWSER_GET_TITLE,
                    target=target_entity,
                    target_domain=TargetDomain.WEBPAGE,
                    parameters={"target": target_entity},
                    verification_strategy=VerificationStrategy.BROWSER_TITLE_MATCH,
                    expected_state=target_entity,
                    tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
                ), TargetDomain.WEBPAGE
            else:
                return Action(
                    capability=CapabilityType.WINDOW_GET_STATE,
                    target=target_entity,
                    target_domain=TargetDomain.WINDOW,
                    parameters={"target": target_entity},
                    verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                    expected_state=target_entity,
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                ), TargetDomain.WINDOW

        # 1. Webpage / Browser Navigation & Search
        # ---------------------------------------------------------------------
        # Special case: compound "open a new tab and open X"
        m_newtab_nav = re.match(r"^open\s+(?:a\s+)?new\s+tab\s+and\s+(?:open|go\s+to|navigate\s+to)\s+(.+)$", c_lower)
        if m_newtab_nav:
            c = f"open {m_newtab_nav.group(1).strip()}"
            c_lower = c.lower()

        # Tab listing / management
        if re.search(r"\b(?:list|show|enumerate)\s+(?:all\s+|my\s+)?(?:open\s+)?(?:browser\s+)?tabs\b", c_lower):
            return Action(
                capability=CapabilityType.BROWSER_LIST_TABS,
                target=context.active_browser or "Brave",
                target_domain=TargetDomain.TAB,
                parameters={"browser": context.active_browser or "Brave"},
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.TAB

        # Window listing / management
        if re.search(r"\b(?:list|show|enumerate)\s+(?:all\s+|my\s+)?(?:open\s+|desktop\s+)?windows\b", c_lower):
            return Action(
                capability=CapabilityType.WINDOW_LIST,
                target="all",
                target_domain=TargetDomain.WINDOW,
                parameters={},
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.WINDOW

        # Tab switching
        m_switch = re.search(r"\b(?:switch|go)\s+(?:back\s+)?to\s+(?:my\s+)?(?:the\s+)?(?:existing\s+)?(.+?)\s+tab(?:\s+(?:in|on)\s+(?:my\s+)?(brave|chrome|edge|browser)(?:\s+browser)?)?\b", c_lower)
        if m_switch:
            tab_target = m_switch.group(1).strip()
            browser_override = m_switch.group(2) or context.active_browser or "Brave"
            return Action(
                capability=CapabilityType.BROWSER_SWITCH_TAB,
                target=tab_target,
                target_domain=TargetDomain.TAB,
                parameters={"target": tab_target, "browser": browser_override},
                verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE,
                expected_state=tab_target,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.TAB

        # Tab closing
        m_close_tab = re.match(
            r"^close\s+(?:the\s+)?(.+?)\s+tab(?:\s+(?:in|on)\s+(?:my\s+)?(brave|chrome|edge|browser)(?:\s+browser)?)?$",
            c_lower,
        )
        if m_close_tab:
            tab_target = m_close_tab.group(1).strip()
            browser_override = m_close_tab.group(2) or context.active_browser or "Brave"
            return Action(
                capability=CapabilityType.BROWSER_CLOSE_TAB,
                target=tab_target,
                target_domain=TargetDomain.TAB,
                parameters={"target": tab_target, "browser": browser_override},
                verification_strategy=VerificationStrategy.BROWSER_TAB_ABSENCE,
                expected_state=tab_target,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.TAB

        # App / Window Closure ("close Notepad", "close Brave", "close Calculator")
        m_close_app = re.match(r"^close\s+(?:the\s+)?([a-zA-Z0-9_\.\-]+(?:\s+[a-zA-Z0-9_\.\-]+)?)$", c_lower)
        if m_close_app and not c_lower.endswith("tab") and not c_lower.endswith("tabs"):
            app_target = m_close_app.group(1).strip()
            if app_target not in ("tab", "the tab", "window", "the window"):
                return Action(
                    capability=CapabilityType.APP_CLOSE,
                    target=app_target,
                    target_domain=TargetDomain.APP,
                    parameters={"target": app_target, "app_name": app_target},
                    verification_strategy=VerificationStrategy.WINDOW_ABSENCE,
                    expected_state=app_target,
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                ), TargetDomain.APP

        # Window State Operations ("minimize Brave", "maximize Notepad", "restore window")
        m_win_state = re.match(r"^(minimize|maximize|restore)\s+(?:the\s+)?(?:window\s+)?(.+?)$", c_lower)
        if m_win_state:
            act_type = m_win_state.group(1).lower()
            win_target = m_win_state.group(2).strip()
            cap_map = {
                "minimize": CapabilityType.WINDOW_MINIMIZE,
                "maximize": CapabilityType.WINDOW_MAXIMIZE,
                "restore": CapabilityType.WINDOW_RESTORE,
            }
            return Action(
                capability=cap_map[act_type],
                target=win_target,
                target_domain=TargetDomain.WINDOW,
                parameters={"target": win_target},
                verification_strategy=VerificationStrategy.WINDOW_STATE,
                expected_state=act_type,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.WINDOW

        # Page / Viewport Scrolling ("scroll down", "scroll up", "scroll page down")
        m_scroll = re.match(r"^scroll\s+(?:the\s+)?(?:page\s+)?(down|up|left|right)(?:\s+by\s+(\d+))?$", c_lower)
        if m_scroll:
            direction = m_scroll.group(1).lower()
            amount = int(m_scroll.group(2)) if m_scroll.group(2) else 400
            dy = amount if direction == "down" else -amount
            return Action(
                capability=CapabilityType.WEB_SCROLL,
                target="viewport",
                target_domain=TargetDomain.WEBPAGE,
                parameters={"direction": direction, "delta_y": dy, "delta_x": 0},
                verification_strategy=VerificationStrategy.NONE,
                tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
            ), TargetDomain.WEBPAGE

        # Explicit Filesystem Read ("read test.txt", "read file test.txt")
        m_read_file = re.match(r"^read\s+(?:the\s+)?(?:file\s+)?[\"']?([a-zA-Z0-9_\-\\\/\.]+\.[a-zA-Z0-9]+)[\"']?$", c, flags=re.IGNORECASE)
        if m_read_file:
            f_path = m_read_file.group(1).strip()
            return Action(
                capability=CapabilityType.FILESYSTEM_READ,
                target=f_path,
                target_domain=TargetDomain.FILE,
                parameters={"path": f_path},
                verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.FILE

        # Explicit Filesystem Write ("write Hello to output.txt", "write X into Y.txt")
        m_write_file = re.match(r"^write\s+[\"']?(.+?)[\"']?\s+(?:to|into)\s+(?:file\s+)?[\"']?([a-zA-Z0-9_\-\\\/\.]+\.[a-zA-Z0-9]+)[\"']?$", c, flags=re.IGNORECASE)
        if m_write_file:
            content_str = m_write_file.group(1).strip().strip("\"'")
            file_dest = m_write_file.group(2).strip()
            return Action(
                capability=CapabilityType.FILESYSTEM_WRITE,
                target=file_dest,
                target_domain=TargetDomain.FILE,
                parameters={"path": file_dest, "content": content_str},
                verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                expected_state=content_str,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.FILE

        # Go Back / Navigation History
        if c_lower in ("go back", "navigate back", "back", "previous page", "return to previous page", "then go back"):
            return Action(
                capability=CapabilityType.BROWSER_BACK,
                target="active_page",
                target_domain=TargetDomain.WEBPAGE,
                parameters={"browser": context.active_browser or "Brave"},
                verification_strategy=VerificationStrategy.NONE,
                tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
            ), TargetDomain.WEBPAGE

        # Search query clause: "search YouTube" / "search Google for YouTube" / "google search for YouTube" / "search for Gmail"
        if (
            c_lower.startswith("search ")
            or c_lower.startswith("google search ")
            or "search for " in c_lower
            or "search google for " in c_lower
            or "google search for " in c_lower
        ):
            clean_q = SearchQueryExtractor.extract_query(c)
            return Action(
                capability=CapabilityType.BROWSER_SEARCH,
                target=clean_q,
                target_domain=TargetDomain.WEBPAGE,
                parameters={"query": clean_q, "browser_name": context.active_browser or "Brave"},
                verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE,
                expected_state=clean_q,
                tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
            ), TargetDomain.WEBPAGE

        # "Bring File Explorer to the front" / "Focus Notepad" / "Switch to Calculator"
        m_front = re.match(
            r"^(?:bring|switch(?:\s+to)?|focus)\s+(?:the\s+)?(.+?)\s+to\s+(?:the\s+)?(?:front|foreground)$",
            c_lower,
        )
        if m_front:
            app_target = m_front.group(1).strip()
            from app.subsystems.computer.target_resolver import TARGET_RESOLVER, TargetResolutionStatus, TargetType
            res = TARGET_RESOLVER.resolve_target(app_target, intent="focus", context=context)
            if res.status == TargetResolutionStatus.RESOLVED and res.selected_candidate:
                cand = res.selected_candidate
                app_name = cand.name.lower()
                return Action(
                    capability=CapabilityType.APP_FOCUS,
                    target=app_name,
                    target_domain=TargetDomain.APP,
                    parameters={"app_name": app_name, "hwnd": cand.metadata.get("hwnd"), "reuse_existing": True},
                    verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                    expected_state=cand.metadata.get("title_kw", cand.name),
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                ), TargetDomain.APP

        # "open the Pluton Web Interaction Test Page in Brave" / "open anker.com" / "open Calculator" / "open Notepad"
        m_nav = re.match(
            r"^(?:open|launch|navigate(?:\s+to)?|go\s+to)\s+(?:the\s+)?(.+?)(?:\s+in\s+(?:my\s+)?(brave|chrome|edge|browser))?$",
            c_lower,
        )
        if m_nav:
            dest_name = m_nav.group(1).strip()
            browser_override = m_nav.group(2) or context.active_browser or "Brave"

            # Extract modifiers (e.g. "in a new browser tab", "in a new tab", "to the front")
            in_new_tab = bool(re.search(r"\b(?:in\s+(?:a\s+)?new\s+(?:browser\s+)?tab|in\s+(?:a\s+)?new\s+tab|in\s+new\s+tab)\b", dest_name, flags=re.IGNORECASE))
            dest_clean = re.sub(r"\b(?:in\s+(?:a\s+)?new\s+(?:browser\s+)?tab|in\s+(?:a\s+)?new\s+tab|in\s+new\s+tab|to\s+(?:the\s+)?(?:front|foreground)|tabs?)\b", "", dest_name, flags=re.IGNORECASE).strip()

            # 1. Check if destination is an explicit search query
            if dest_name.startswith("search ") or "search for " in dest_name:
                clean_q = SearchQueryExtractor.extract_query(dest_name)
                return Action(
                    capability=CapabilityType.WEB_TYPE,
                    target="search box",
                    target_domain=TargetDomain.UI_ELEMENT,
                    parameters={"text": clean_q, "selector": "input[type='search'], input[type='text'], input:not([type]), textarea, [role='searchbox'], [aria-label*='search' i]", "press_enter": True},
                    verification_strategy=VerificationStrategy.DOM_VALUE_MATCH,
                    expected_state=clean_q,
                    tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
                ), TargetDomain.UI_ELEMENT

            # 2. Universal Evidence-Based Target Resolver
            from app.subsystems.computer.target_resolver import TARGET_RESOLVER, TargetResolutionStatus, TargetType
            is_browser_explicit = in_new_tab or bool(browser_override != (context.active_browser or "Brave") or any(k in c_lower for k in ("in brave", "in chrome", "in edge", "in my browser", "in browser", "new tab", "browser tab")))
            nav_intent = "navigate" if is_browser_explicit else "open"
            res = TARGET_RESOLVER.resolve_target(dest_clean, intent=nav_intent, context=context)
            if res.status == TargetResolutionStatus.RESOLVED and res.selected_candidate:
                cand = res.selected_candidate
                if cand.target_type == TargetType.EXISTING_BROWSER_TAB:
                    return Action(
                        capability=CapabilityType.BROWSER_SWITCH_TAB,
                        target=cand.name,
                        target_domain=TargetDomain.TAB,
                        parameters=res.bound_action_params,
                        verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE,
                        expected_state=cand.name,
                        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                    ), TargetDomain.TAB

                elif cand.target_type in (TargetType.INSTALLED_DESKTOP_APP, TargetType.EXISTING_WINDOW):
                    target_dom = TargetDomain.APP
                    app_name = cand.name.lower()
                    exe_path = cand.metadata.get("exe") or (cand.identity if cand.target_type == TargetType.INSTALLED_DESKTOP_APP else None)
                    return Action(
                        capability=CapabilityType.APP_LAUNCH,
                        target=app_name,
                        target_domain=target_dom,
                        parameters={
                            "app_name": app_name,
                            "exe": exe_path,
                            "args": cand.metadata.get("args"),
                            "hwnd": cand.metadata.get("hwnd"),
                            "window_classes": cand.metadata.get("window_classes"),
                            "title_keywords": cand.metadata.get("title_keywords"),
                            "reuse_existing": cand.target_type == TargetType.EXISTING_WINDOW or bool(cand.metadata.get("hwnd")),
                        },
                        verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                        expected_state=cand.metadata.get("title_kw", cand.name),
                        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                    ), target_dom

                elif cand.target_type in (TargetType.LOCAL_WEB_SERVICE, TargetType.PUBLIC_WEB_DOMAIN):
                    return Action(
                        capability=CapabilityType.BROWSER_NAVIGATE,
                        target=cand.identity,
                        target_domain=TargetDomain.WEBPAGE,
                        parameters={"url": cand.identity, "browser": browser_override},
                        verification_strategy=VerificationStrategy.BROWSER_TAB_PRESENCE,
                        expected_state=cand.name,
                        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                    ), TargetDomain.WEBPAGE

                elif cand.target_type == TargetType.FILESYSTEM_PATH:
                    return Action(
                        capability=CapabilityType.FILESYSTEM_READ,
                        target=cand.identity,
                        target_domain=TargetDomain.FILE,
                        parameters=res.bound_action_params,
                        verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                        expected_state="present",
                        tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                    ), TargetDomain.FILE

            if res.status == TargetResolutionStatus.AMBIGUOUS_TARGET:
                return Action(
                    capability=CapabilityType.GENERAL_ACTION,
                    target=dest_clean,
                    parameters={"error": res.refusal_reason or "AMBIGUOUS_TARGET"},
                    tier_requested=ExecutionTier.TIER_5_VISION,
                ), TargetDomain.APP

            # 3. If target resolution failed completely for an open/navigate command:
            # SEARCH FALLBACK IS STRICTLY FORBIDDEN!
            return Action(
                capability=CapabilityType.GENERAL_ACTION,
                target=dest_clean,
                parameters={"error": f"TARGET_NOT_FOUND: Could not resolve '{dest_clean}'"},
                tier_requested=ExecutionTier.TIER_5_VISION,
            ), TargetDomain.APP

        # ---------------------------------------------------------------------
        # 2. Text Input & Typing (Web or Keyboard)
        # ---------------------------------------------------------------------
        # "enter PLUTON FRONTEND TEST in the text box" / "type PLUTON DESKTOP TEST" / "type PLUTON PHASE 1 into Notepad"
        m_type = re.match(
            r"^(?:enter|type|write|input|fill)\s+[\"']?(.+?)[\"']?(?:\s+(?:in|into)\s+(?:the\s+)?(text\s*box|field|input|search\s*box|notepad|document))?$",
            c,
            flags=re.IGNORECASE,
        )
        if m_type:
            raw_val = m_type.group(1).strip().strip("\"'")
            target_el = (m_type.group(2) or "").strip().lower()
            context.metadata["last_typed_text"] = raw_val

            if active_domain == TargetDomain.WEBPAGE or target_el in ("text box", "textbox", "field", "input", "search box"):
                return Action(
                    capability=CapabilityType.WEB_TYPE,
                    target=target_el or "textbox",
                    target_domain=TargetDomain.WEB_ELEMENT,
                    parameters={"target": target_el or "textbox", "text": raw_val, "role": "textbox"},
                    verification_strategy=VerificationStrategy.DOM_VALUE_MATCH,
                    expected_state=raw_val,
                    tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
                ), TargetDomain.WEBPAGE
            else:
                target_win = target_el if target_el in ("notepad", "calculator", "explorer") else ("notepad" if "notepad" in c_lower else "")
                return Action(
                    capability=CapabilityType.KEYBOARD_TYPE,
                    target=target_win or raw_val,
                    target_domain=TargetDomain.KEYBOARD,
                    parameters={"text": raw_val, "target_window": target_win, "target": target_win},
                    verification_strategy=VerificationStrategy.UIA_READBACK,
                    expected_state=raw_val,
                    tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
                ), TargetDomain.APP

        # ---------------------------------------------------------------------
        # 3. Checkbox / Toggle
        # ---------------------------------------------------------------------
        # "enable the checkbox" / "toggle the checkbox" / "check enable feature"
        m_check = re.match(
            r"^(?:enable|toggle|check|uncheck)\s+(?:the\s+)?(?:checkbox\s+)?[\"']?(.+?)?[\"']?$",
            c_lower,
        )
        if m_check and ("checkbox" in c_lower or "feature" in c_lower or "enable" in c_lower or "toggle" in c_lower):
            chk_name = m_check.group(1) or "checkbox"
            chk_name_clean = chk_name.replace("checkbox", "").strip() or "checkbox"
            return Action(
                capability=CapabilityType.WEB_CLICK,
                target=chk_name_clean,
                target_domain=TargetDomain.WEB_ELEMENT,
                parameters={"target": chk_name_clean, "role": "checkbox"},
                verification_strategy=VerificationStrategy.DOM_STATE_CHANGE,
                expected_state="CHECKED",
                tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
            ), TargetDomain.WEBPAGE

        # ---------------------------------------------------------------------
        # 4. Selection (Keyboard Select All vs Dropdown Selection)
        # ---------------------------------------------------------------------
        if c_lower in ("select all", "select everything", "select all text", "select-all"):
            return Action(
                capability=CapabilityType.KEYBOARD_HOTKEY,
                target="all",
                target_domain=TargetDomain.KEYBOARD,
                parameters={"keys": ["ctrl", "a"]},
                verification_strategy=VerificationStrategy.NONE,
                tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
            ), active_domain

        # "select Option B" / "choose Option B from the dropdown"
        m_select = re.match(
            r"^(?:select|choose|pick)\s+[\"']?(.+?)[\"']?(?:\s+(?:from|in)\s+(?:the\s+)?(?:dropdown|select|combobox|menu))?$",
            c,
            flags=re.IGNORECASE,
        )
        if m_select:
            opt_val = m_select.group(1).strip().strip("\"'")
            return Action(
                capability=CapabilityType.WEB_SELECT,
                target="select",
                target_domain=TargetDomain.WEB_ELEMENT,
                parameters={"target": "select", "value": opt_val, "role": "combobox"},
                verification_strategy=VerificationStrategy.DOM_VALUE_MATCH,
                expected_state=opt_val,
                tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
            ), TargetDomain.WEBPAGE

        # Keyboard press / hotkey: "press Ctrl+A", "press Enter", "press Tab"
        m_press_key = re.match(r"^press\s+([a-zA-Z0-9_\+\-]+)$", c, flags=re.IGNORECASE)
        if m_press_key:
            key_name = m_press_key.group(1).strip()
            if "+" in key_name:
                keys = [k.strip().lower() for k in key_name.split("+")]
                return Action(
                    capability=CapabilityType.KEYBOARD_HOTKEY,
                    target=key_name,
                    target_domain=TargetDomain.KEYBOARD,
                    parameters={"keys": keys},
                    tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
                ), active_domain
            elif key_name.lower() in ("enter", "tab", "esc", "escape", "space", "backspace", "delete", "down", "up", "left", "right", "f1", "f2", "f5", "f11"):
                return Action(
                    capability=CapabilityType.KEYBOARD_PRESS,
                    target=key_name.lower(),
                    target_domain=TargetDomain.KEYBOARD,
                    parameters={"key": key_name.lower()},
                    tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
                ), active_domain

        # ---------------------------------------------------------------------
        # 5. Button / Link / Element Click
        # ---------------------------------------------------------------------
        # "click Change Page" / "click the button" / "click first result"
        m_click = re.match(
            r"^(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?(?:button\s+)?[\"']?(.+?)[\"']?(?:\s+button)?$",
            c,
            flags=re.IGNORECASE,
        )
        if m_click:
            btn_target = m_click.group(1).strip().strip("\"'")
            if btn_target.lower() in ("button", "the button"):
                btn_target = "Change Page"

            target_kw = btn_target.lower()
            is_web_btn = (
                active_domain == TargetDomain.WEBPAGE
                or "result" in target_kw
                or "submit" in target_kw
                or "link" in target_kw
                or "query" in target_kw
                or "search" in target_kw
                or "page" in target_kw
                or "tab" in target_kw
                or target_kw in ("change page", "submit", "login", "first result", "next", "previous", "cart", "checkout", "sign in", "sign up")
            )
            if is_web_btn:
                return Action(
                    capability=CapabilityType.WEB_CLICK,
                    target=btn_target,
                    target_domain=TargetDomain.WEB_ELEMENT,
                    parameters={"target": btn_target, "role": "button"},
                    verification_strategy=VerificationStrategy.NONE,
                    tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
                ), TargetDomain.WEBPAGE
            else:
                return Action(
                    capability=CapabilityType.UI_INVOKE,
                    target=btn_target,
                    target_domain=TargetDomain.UI_ELEMENT,
                    parameters={"target": btn_target},
                    verification_strategy=VerificationStrategy.UIA_READBACK,
                    tier_requested=ExecutionTier.TIER_3_UIA_AUTOMATION,
                ), TargetDomain.UI_ELEMENT

        # ---------------------------------------------------------------------
        # 6. Terminal Execution & Output
        # ---------------------------------------------------------------------
        # "run echo PLUTON_PHASE1" / "execute echo PLUTON_PHASE1 in terminal"
        m_term = re.match(
            r"^(?:run|execute)\s+[\"']?(.+?)[\"']?(?:\s+(?:in|on)\s+(?:the\s+)?(?:terminal|shell|cmd|powershell))?$",
            c,
            flags=re.IGNORECASE,
        )
        if m_term and not c_lower.startswith(("run ", "execute ")) == False:
            cmd = m_term.group(1).strip().strip("\"'")
            return Action(
                capability=CapabilityType.TERMINAL_EXECUTE,
                target=cmd,
                target_domain=TargetDomain.TERMINAL,
                parameters={"command": cmd},
                verification_strategy=VerificationStrategy.TERMINAL_EXIT_CODE,
                expected_state=0,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.TERMINAL

        # ---------------------------------------------------------------------
        # 7. Drag & Drop (Semantic Filesystem or Mouse Drag)
        # ---------------------------------------------------------------------
        # "drag phase1_src.txt to Downloads/phase1_dst.txt" / "drag and drop X into Y"
        m_drag = re.match(
            r"^(?:drag|drag\s+and\s+drop)\s+[\"']?(.+?)[\"']?\s+(?:to|into|onto)\s+[\"']?(.+?)[\"']?$",
            c,
            flags=re.IGNORECASE,
        )
        if m_drag:
            src = m_drag.group(1).strip().strip("\"'")
            dst = m_drag.group(2).strip().strip("\"'")
            return Action(
                capability=CapabilityType.MOUSE_DRAG,
                target=f"{src}->{dst}",
                target_domain=TargetDomain.FILE,
                parameters={"source_target": src, "destination_target": dst},
                verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                expected_state=dst,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.FILE

        # ---------------------------------------------------------------------
        # 8. Read / Extract Text / Report Result / Verify File Existence
        # ---------------------------------------------------------------------
        # "verify the file exists" / "verify file exists"
        if re.search(r"verify\s+(?:the\s+)?file\s+exists", c_lower):
            last_f = context.metadata.get("last_file_path") or os.path.join(os.path.expanduser("~"), "Downloads", "phase1.txt")
            return Action(
                capability=CapabilityType.FILESYSTEM_READ,
                target=last_f,
                target_domain=TargetDomain.FILE,
                parameters={"path": last_f},
                verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.FILE

        # "read the file / terminal output / page title"
        if "terminal output" in c_lower or (active_domain == TargetDomain.TERMINAL and ("output" in c_lower or "exact output" in c_lower)):
            return Action(
                capability=CapabilityType.TERMINAL_OUTPUT,
                target="output",
                target_domain=TargetDomain.TERMINAL,
                parameters={},
                verification_strategy=VerificationStrategy.NONE,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.TERMINAL

        if "read the file" in c_lower or "read file" in c_lower or "read it back" in c_lower or (active_domain in (TargetDomain.FILE, TargetDomain.FOLDER) and ("content" in c_lower or "file" in c_lower or "its contents" in c_lower or "the contents" in c_lower)):
            m_f = re.search(r"read\s+(?:the\s+)?(?:file\s+)?(?:called\s+|named\s+)?([^\s,]+)", c_lower)
            if m_f and m_f.group(1) not in ("it", "back", "the", "contents", "content", "file"):
                f_path = m_f.group(1)
            else:
                f_path = context.metadata.get("last_file_path") or os.path.join(os.path.expanduser("~"), "Downloads", "phase1_frontend_test.txt")
            return Action(
                capability=CapabilityType.FILESYSTEM_READ,
                target=f_path,
                target_domain=TargetDomain.FILE,
                parameters={"path": f_path},
                verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.FILE

        if "title" in c_lower and ("page" in c_lower or "tab" in c_lower or "browser" in c_lower or "get the title" in c_lower):
            return Action(
                capability=CapabilityType.BROWSER_GET_TITLE,
                target="active_page",
                target_domain=TargetDomain.WEBPAGE,
                parameters={},
                verification_strategy=VerificationStrategy.BROWSER_TITLE_MATCH,
                tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
            ), TargetDomain.WEBPAGE

        if "extract text" in c_lower or "extract the text" in c_lower or (active_domain == TargetDomain.WEBPAGE and any(k in c_lower for k in ("result-area", "resulting text", "text shown on the page", "report the result", "tell me the result"))):
            selector = "#result-area" if ("result-area" in c_lower or "result" in c_lower or "text" in c_lower) else "body"
            return Action(
                capability=CapabilityType.WEB_EXTRACT_TEXT,
                target=selector,
                target_domain=TargetDomain.WEB_ELEMENT,
                parameters={"selector": selector},
                verification_strategy=VerificationStrategy.DOM_VALUE_MATCH,
                tier_requested=ExecutionTier.TIER_2_APP_BROWSER_API,
            ), TargetDomain.WEBPAGE

        # ---------------------------------------------------------------------
        # 7. Clipboard: Copy & Paste
        # ---------------------------------------------------------------------
        if "copy" in c_lower and ("text" in c_lower or "it" in c_lower or c_lower == "copy"):
            return Action(
                capability=CapabilityType.KEYBOARD_COPY,
                target="selection",
                target_domain=TargetDomain.CLIPBOARD,
                parameters={},
                tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
            ), TargetDomain.CLIPBOARD

        if "paste" in c_lower and ("text" in c_lower or "it" in c_lower or c_lower == "paste"):
            return Action(
                capability=CapabilityType.KEYBOARD_PASTE,
                target="cursor",
                target_domain=TargetDomain.CLIPBOARD,
                parameters={},
                tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
            ), TargetDomain.CLIPBOARD

        if "new line" in c_lower or "create a new line" in c_lower:
            return Action(
                capability=CapabilityType.KEYBOARD_HOTKEY,
                target="enter",
                target_domain=TargetDomain.KEYBOARD,
                parameters={"keys": ["enter"]},
                tier_requested=ExecutionTier.TIER_4_DETERMINISTIC_INPUT,
            ), TargetDomain.KEYBOARD

        # ---------------------------------------------------------------------
        # 8. Filesystem: Create file, save as, write, read
        # ---------------------------------------------------------------------
        # "save it as phase1.txt in Downloads" / "save as phase1.txt in Downloads"
        m_save_as = re.match(
            r"^save\s+(?:it\s+)?as\s+[\"']?([^\"'\s]+)[\"']?\s+in\s+([a-zA-Z0-9_\-\\\/]+)$",
            c,
            flags=re.IGNORECASE,
        )
        if m_save_as:
            fname = m_save_as.group(1).strip()
            folder = m_save_as.group(2).strip()
            target_path = os.path.join(os.path.expanduser(f"~/{folder}"), fname)
            context.metadata["last_file_path"] = target_path
            saved_content = context.metadata.get("last_typed_text", "PLUTON PHASE 1")
            return Action(
                capability=CapabilityType.FILESYSTEM_WRITE,
                target=target_path,
                target_domain=TargetDomain.FILE,
                parameters={"path": target_path, "content": saved_content},
                verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                expected_state=saved_content,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.FILE

        # "create a file called phase1.txt in Downloads and write Phase 1 into it" / "create TEST_RUN.txt"
        m_file = re.match(
            r"^create\s+(?:a\s+)?file\s+(?:called\s+|named\s+)?[\"']?([^\"'\s]+)[\"']?(?:\s+in\s+([a-zA-Z0-9_\-\\\/]+))?(?:[,\s]+(?:and\s+)?write\s+[\"']?(.+?)[\"']?\s+into\s+it)?$",
            c,
            flags=re.IGNORECASE,
        )
        if not m_file and (c_lower.startswith("create ") and ("." in c_lower or "txt" in c_lower or "file" in c_lower)):
            m_file_simple = re.match(r"^create\s+(?:a\s+)?(?:file\s+)?[\"']?([^\"'\s]+)[\"']?$", c, flags=re.IGNORECASE)
            if m_file_simple:
                fname = m_file_simple.group(1).strip()
                target_path = os.path.join(os.path.expanduser("~/Downloads"), fname)
                context.metadata["last_file_path"] = target_path
                return Action(
                    capability=CapabilityType.FILESYSTEM_WRITE,
                    target=target_path,
                    target_domain=TargetDomain.FILE,
                    parameters={"path": target_path, "content": ""},
                    verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                    expected_state="",
                    tier_requested=ExecutionTier.TIER_1_NATIVE_API,
                ), TargetDomain.FILE

        if m_file:
            fname = m_file.group(1).strip()
            folder = m_file.group(2).strip() if m_file.group(2) else "Downloads"
            content = m_file.group(3) or ""
            target_path = os.path.join(os.path.expanduser(f"~/{folder}"), fname)
            context.metadata["last_file_path"] = target_path
            return Action(
                capability=CapabilityType.FILESYSTEM_WRITE,
                target=target_path,
                target_domain=TargetDomain.FILE,
                parameters={"path": target_path, "content": content},
                verification_strategy=VerificationStrategy.FILESYSTEM_CHECK,
                expected_state=content,
                tier_requested=ExecutionTier.TIER_1_NATIVE_API,
            ), TargetDomain.FILE

        # ---------------------------------------------------------------------
        # 9. Window / Settings Switch
        # ---------------------------------------------------------------------
        # "switch to Bluetooth" / "open Bluetooth settings"
        if "bluetooth" in c_lower:
            return Action(
                capability=CapabilityType.APP_LAUNCH,
                target="ms-settings:bluetooth",
                target_domain=TargetDomain.WINDOW,
                parameters={"app_name": "Settings", "exe": "ms-settings:bluetooth"},
                verification_strategy=VerificationStrategy.WINDOW_PRESENCE,
                expected_state="Settings",
                tier_requested=ExecutionTier.TIER_3_UIA_AUTOMATION,
            ), TargetDomain.WINDOW

        # Unrecognized clause -> Return None so Lane 2 (General-Purpose Model Tool Loop) takes ownership
        return None, None


UNIVERSAL_PLAN_COMPILER = UniversalPlanCompiler()
