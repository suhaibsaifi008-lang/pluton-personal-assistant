"""
Discovery Source for Installed Windows Desktop Applications
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any, Optional
from ..contracts import TargetCandidate, TargetType
from .base import DiscoverySource

logger = logging.getLogger("pluton.target_resolver.desktop_app")

_WINDIR = os.environ.get("WINDIR", "C:\\Windows")
_SYSTEM_ALIASES: dict[str, dict[str, Any]] = {
    "calculator": {"canonical_name": "Calculator", "exe": "calc.exe", "protocol": "ms-calculator:", "title_kw": "Calculator", "window_classes": ["ApplicationFrameWindow", "CalcFrame"], "title_keywords": ["calculator", "calc"]},
    "calc": {"canonical_name": "Calculator", "exe": "calc.exe", "protocol": "ms-calculator:", "title_kw": "Calculator", "window_classes": ["ApplicationFrameWindow", "CalcFrame"], "title_keywords": ["calculator", "calc"]},
    "notepad": {"canonical_name": "Notepad", "exe": os.path.join(_WINDIR, "notepad.exe"), "protocol": None, "title_kw": "Notepad", "window_classes": ["Notepad", "Notepad_Win11", "RichEditD2DPT"], "title_keywords": ["notepad"]},
    "paint": {"canonical_name": "Paint", "exe": os.path.join(_WINDIR, "mspaint.exe"), "protocol": None, "title_kw": "Paint", "window_classes": ["MSPaintApp", "PaintApp"], "title_keywords": ["paint"]},
    "file explorer": {"canonical_name": "File Explorer", "exe": os.path.join(_WINDIR, "explorer.exe"), "protocol": None, "title_kw": "File Explorer", "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["file explorer", "explorer", "home", "downloads", "documents"]},
    "explorer": {"canonical_name": "File Explorer", "exe": os.path.join(_WINDIR, "explorer.exe"), "protocol": None, "title_kw": "File Explorer", "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["file explorer", "explorer", "home", "downloads", "documents"]},
    "downloads": {"canonical_name": "Downloads", "exe": os.path.join(_WINDIR, "explorer.exe"), "args": [os.path.expanduser("~/Downloads")], "title_kw": "Downloads", "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["downloads", "explorer"]},
    "documents": {"canonical_name": "Documents", "exe": os.path.join(_WINDIR, "explorer.exe"), "args": [os.path.expanduser("~/Documents")], "title_kw": "Documents", "window_classes": ["CabinetWClass", "XamlExplorerHostIslandWindow", "ExploreWClass"], "title_keywords": ["documents", "explorer"]},
    "settings": {"canonical_name": "Settings", "exe": "ms-settings:", "protocol": "ms-settings:", "title_kw": "Settings", "window_classes": ["ApplicationFrameWindow"], "title_keywords": ["settings"]},
    "task manager": {"canonical_name": "Task Manager", "exe": os.path.join(_WINDIR, "System32", "taskmgr.exe"), "title_kw": "Task Manager", "window_classes": ["TaskManagerWindow"], "title_keywords": ["task manager"]},
    "cmd": {"canonical_name": "Command Prompt", "exe": os.path.join(_WINDIR, "System32", "cmd.exe"), "title_kw": "Command Prompt", "window_classes": ["ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"], "title_keywords": ["command prompt", "cmd"]},
    "powershell": {"canonical_name": "PowerShell", "exe": os.path.join(_WINDIR, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"), "title_kw": "PowerShell", "window_classes": ["ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"], "title_keywords": ["powershell"]},
    "terminal": {"canonical_name": "Terminal", "exe": "wt.exe", "title_kw": "Terminal", "window_classes": ["CASCADIA_HOSTING_WINDOW_CLASS"], "title_keywords": ["terminal"]},
    "brave": {"canonical_name": "Brave", "exe": "brave.exe", "title_kw": "Brave", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["brave"]},
    "brave browser": {"canonical_name": "Brave", "exe": "brave.exe", "title_kw": "Brave", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["brave"]},
    "chrome": {"canonical_name": "Chrome", "exe": "chrome.exe", "title_kw": "Chrome", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["chrome"]},
    "chrome browser": {"canonical_name": "Chrome", "exe": "chrome.exe", "title_kw": "Chrome", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["chrome"]},
    "google chrome": {"canonical_name": "Chrome", "exe": "chrome.exe", "title_kw": "Chrome", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["chrome"]},
    "edge": {"canonical_name": "Edge", "exe": "msedge.exe", "title_kw": "Edge", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["edge"]},
    "edge browser": {"canonical_name": "Edge", "exe": "msedge.exe", "title_kw": "Edge", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["edge"]},
    "microsoft edge": {"canonical_name": "Edge", "exe": "msedge.exe", "title_kw": "Edge", "window_classes": ["Chrome_WidgetWin_1"], "title_keywords": ["edge"]},
    "browser": {"canonical_name": "Browser", "exe": os.path.join(_WINDIR, "explorer.exe"), "protocol": "https://", "title_kw": "Browser", "window_classes": ["Chrome_WidgetWin_1", "CabinetWClass"], "title_keywords": ["browser", "brave", "chrome", "edge"]},
    "the browser": {"canonical_name": "Browser", "exe": os.path.join(_WINDIR, "explorer.exe"), "protocol": "https://", "title_kw": "Browser", "window_classes": ["Chrome_WidgetWin_1", "CabinetWClass"], "title_keywords": ["browser", "brave", "chrome", "edge"]},
}


class DesktopAppDiscoverySource(DiscoverySource):
    name = "desktop_app"

    async def discover_candidates(self, query: str, context: Optional[Any] = None) -> list[TargetCandidate]:
        candidates: list[TargetCandidate] = []
        q_raw = str(query or "").strip().lower()
        q_clean = re.sub(r"^(?:the\s+|a\s+|open\s+|launch\s+|start\s+)", "", q_raw).strip()
        q_core = re.sub(r"^(?:microsoft\s+|ms\s+|google\s+)", "", q_clean).strip()
        tokens = set(re.findall(r"\w+", q_clean))
        core_tokens = set(re.findall(r"\w+", q_core))
        if not q_clean and not q_raw:
            return candidates

        # 1. System alias check
        alias_key = q_clean if q_clean in _SYSTEM_ALIASES else (q_core if q_core in _SYSTEM_ALIASES else None)
        if alias_key:
            meta = dict(_SYSTEM_ALIASES[alias_key])
            exe_val = meta.get("exe")
            if exe_val and not os.path.isabs(exe_val) and not exe_val.startswith("ms-"):
                found_which = shutil.which(exe_val) or shutil.which(f"{exe_val}.exe")
                if found_which:
                    meta["exe"] = found_which
            candidates.append(
                TargetCandidate(
                    target_type=TargetType.INSTALLED_DESKTOP_APP,
                    identity=meta["exe"],
                    name=meta["canonical_name"],
                    source=self.name,
                    metadata=meta,
                    score=1.0,
                    matched_tokens=(q_clean,),
                )
            )
            return candidates

        # 2. System PATH check
        for cand in (q_clean, q_core, f"{q_clean}.exe", f"{q_core}.exe"):
            exe_path = shutil.which(cand)
            if exe_path:
                candidates.append(
                    TargetCandidate(
                        target_type=TargetType.INSTALLED_DESKTOP_APP,
                        identity=exe_path,
                        name=q_clean.title(),
                        source=self.name,
                        metadata={"exe": exe_path, "canonical_name": q_clean.title(), "title_kw": q_core or q_clean},
                        score=0.95,
                        matched_tokens=(q_clean,),
                    )
                )
                return candidates

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
                                                candidates.append(
                                                    TargetCandidate(
                                                        target_type=TargetType.INSTALLED_DESKTOP_APP,
                                                        identity=val,
                                                        name=name_clean.title(),
                                                        source=self.name,
                                                        metadata={"exe": val, "canonical_name": name_clean.title(), "title_kw": q_core or name_clean},
                                                        score=0.90,
                                                        matched_tokens=(q_clean,),
                                                    )
                                                )
                                                return candidates
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
                            candidates.append(
                                TargetCandidate(
                                    target_type=TargetType.INSTALLED_DESKTOP_APP,
                                    identity=str(lnk),
                                    name=lnk.stem,
                                    source=self.name,
                                    metadata={"exe": str(lnk), "canonical_name": lnk.stem, "title_kw": q_core or lnk.stem},
                                    score=0.88,
                                    matched_tokens=(q_clean,),
                                )
                            )
                            return candidates
        except Exception:
            pass

        return candidates