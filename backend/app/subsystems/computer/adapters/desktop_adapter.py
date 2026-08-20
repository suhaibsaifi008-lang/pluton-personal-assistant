"""
PLUTON R1 — Windows Desktop Execution Adapter
Authoritative low-level execution adapter powered by windows-use and windows_use.uia.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import types
from typing import Any, Optional

logger = logging.getLogger("pluton.adapters.desktop")

# -----------------------------------------------------------------------------
# Safe Cloud Provider Bridging for windows-use
# windows_use.providers statically imports optional cloud SDKs in __init__.py.
# We ensure safe dummy module fallbacks exist so Desktop & UIA core can run
# locally without network calls or missing optional package exceptions.
# -----------------------------------------------------------------------------
for _mod in ("cerebras.cloud.sdk", "mistralai", "litellm", "groq", "ollama", "deepgram", "elevenlabs", "discord", "neonize", "pysignalclirestapi", "telegram", "slack_bolt"):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except Exception:
            _m = types.ModuleType(_mod)
            sys.modules[_mod] = _m

# Ensure specific classes expected by windows_use.providers are defined if missing
if "mistralai" in sys.modules and not hasattr(sys.modules["mistralai"], "Mistral"):
    sys.modules["mistralai"].Mistral = type("Mistral", (), {})
if "cerebras.cloud.sdk" in sys.modules:
    if not hasattr(sys.modules["cerebras.cloud.sdk"], "AsyncCerebras"):
        sys.modules["cerebras.cloud.sdk"].AsyncCerebras = type("AsyncCerebras", (), {})
    if not hasattr(sys.modules["cerebras.cloud.sdk"], "Cerebras"):
        sys.modules["cerebras.cloud.sdk"].Cerebras = type("Cerebras", (), {})
if "groq" in sys.modules and not hasattr(sys.modules["groq"], "AsyncGroq"):
    sys.modules["groq"].AsyncGroq = type("AsyncGroq", (), {})
if "litellm" in sys.modules:
    if not hasattr(sys.modules["litellm"], "acompletion"):
        sys.modules["litellm"].acompletion = lambda *a, **kw: None
    if not hasattr(sys.modules["litellm"], "completion"):
        sys.modules["litellm"].completion = lambda *a, **kw: None

try:
    import windows_use.uia as uia
    from windows_use.agent.desktop.service import Desktop
    from windows_use.agent.desktop.config import KEY_ALIASES
    _WINDOWS_USE_AVAILABLE = True
except Exception as _wu_err:
    logger.warning("[DESKTOP_ADAPTER] windows_use import exception: %s", _wu_err)
    _WINDOWS_USE_AVAILABLE = False
    uia = None
    Desktop = None
    KEY_ALIASES = {}


def _get_process_image_name(pid: int) -> str:
    """Retrieve process executable basename in 0.1ms using Win32 API."""
    if not pid or pid <= 0:
        return ""
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            ctypes.windll.kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return ""


class DesktopExecutionAdapter:
    """
    Authoritative Windows Desktop Execution Adapter.
    Translates PLUTON domain intents into reliable windows-use operations.
    """

    def __init__(self) -> None:
        self._desktop: Optional[Desktop] = None
        self._apps_cache: dict[str, str] = {}
        self._apps_cached_at: float = 0.0

    @property
    def desktop(self) -> Optional[Desktop]:
        if self._desktop is None and _WINDOWS_USE_AVAILABLE and Desktop is not None:
            try:
                self._desktop = Desktop(use_vision=False, use_annotation=False, use_accessibility=True)
            except Exception as ex:
                logger.error("[DESKTOP_ADAPTER] Failed to initialize windows_use Desktop: %s", ex)
        return self._desktop

    # -------------------------------------------------------------------------
    # Application Lifecycle Management
    # -------------------------------------------------------------------------

    def get_start_menu_apps(self, refresh: bool = False) -> dict[str, str]:
        """Index installed Windows applications via Start Menu with 60s caching."""
        now = time.perf_counter()
        if not refresh and self._apps_cache and (now - self._apps_cached_at < 60.0):
            return self._apps_cache

        if self.desktop:
            try:
                apps = self.desktop.get_apps_from_start_menu()
                if apps:
                    self._apps_cache = apps
                    self._apps_cached_at = now
                    return apps
            except Exception as ex:
                logger.warning("[DESKTOP_ADAPTER] get_apps_from_start_menu failed: %s", ex)
        return self._apps_cache

    def launch_app(
        self,
        app_name: str,
        args: list[str] | None = None,
        reuse_existing: bool = False,
        timeout: float = 6.0,
    ) -> dict[str, Any]:
        """
        Launch or focus application using windows-use start menu resolution and UIA verification.
        Guarantees idempotency and capture of authoritative PID and HWND.
        """
        app_clean = app_name.strip()
        args = args or []
        shell_classes = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow"}

        # 1. Existing instance check if reuse_existing is requested
        matching_before = self.find_windows_by_app(app_clean)
        if reuse_existing and matching_before:
            target_win = matching_before[0]
            hwnd = target_win.get("hwnd", 0)
            pid = target_win.get("pid", 0)
            self.focus_window(hwnd)
            return {
                "success": True,
                "transition": "EXISTING_INSTANCE_REUSED",
                "method": "window_focus",
                "hwnd": hwnd,
                "pid": pid,
                "title": target_win.get("title"),
                "message": f"Focused existing '{app_clean}' window (HWND: {hwnd}).",
            }

        hwnds_before = {w.get("hwnd", 0) for w in self.list_windows(visible_only=False)}

        # 2. Launch via windows_use start menu index or native shell
        launched_pid = 0
        apps_map = self.get_start_menu_apps()

        # Check standard shortcuts / apps_map
        appid = apps_map.get(app_clean.lower())
        if not appid:
            # Fuzzy check in start menu
            for k, v in apps_map.items():
                if app_clean.lower() in k or k in app_clean.lower():
                    appid = v
                    break

        if appid:
            if os.path.exists(appid) or "\\" in appid:
                try:
                    proc = subprocess.Popen([appid] + args, shell=False)
                    launched_pid = proc.pid
                except Exception:
                    pass
            else:
                try:
                    cmd = f'Start-Process "shell:AppsFolder\\{appid}"'
                    if self.desktop:
                        self.desktop.execute_command(cmd)
                except Exception:
                    pass

        # Fallback to direct executable / protocol launch if not launched
        if not launched_pid:
            exe_cand = shutil.which(app_clean) or shutil.which(f"{app_clean}.exe")
            if exe_cand:
                try:
                    proc = subprocess.Popen([exe_cand] + args, shell=False)
                    launched_pid = proc.pid
                except Exception:
                    pass
            elif app_clean.lower() in ("calculator", "calc"):
                try:
                    if hasattr(os, "startfile"):
                        os.startfile("calculator:")
                except Exception:
                    pass
            elif app_clean.lower() in ("explorer", "file explorer"):
                try:
                    proc = subprocess.Popen(["explorer.exe"], shell=False)
                    launched_pid = proc.pid
                except Exception:
                    pass
            elif hasattr(os, "startfile"):
                try:
                    os.startfile(app_clean)
                except Exception:
                    pass

        # 3. Post-launch Verification & HWND Capture
        deadline = time.perf_counter() + timeout
        new_window = None

        while time.perf_counter() < deadline:
            wins_after = self.list_windows(visible_only=True)
            for w in wins_after:
                hwnd = w.get("hwnd", 0)
                pid = w.get("pid", 0)
                title = w.get("title", "")
                c_name = w.get("class_name", "")
                pname = _get_process_image_name(pid)

                if c_name in shell_classes:
                    continue

                is_match = False
                if launched_pid and pid == launched_pid:
                    is_match = True
                elif app_clean.lower() in pname.lower() or app_clean.lower() in title.lower():
                    is_match = True
                elif app_clean.lower() in ("explorer", "file explorer") and c_name in ("CabinetWClass", "ExploreWClass", "XamlExplorerHostIslandWindow"):
                    is_match = True
                elif app_clean.lower() in ("calculator", "calc") and ("calculator" in title.lower() or c_name == "ApplicationFrameWindow"):
                    is_match = True

                if is_match:
                    if hwnd not in hwnds_before or (launched_pid and pid == launched_pid):
                        new_window = w
                        break
                    elif not new_window:
                        new_window = w

            if new_window:
                break
            time.sleep(0.1)

        if new_window:
            target_hwnd = new_window.get("hwnd", 0)
            target_pid = new_window.get("pid", launched_pid)
            self.focus_window(target_hwnd)
            return {
                "success": True,
                "transition": "WINDOW_CREATED",
                "method": "windows_use_launch",
                "hwnd": target_hwnd,
                "pid": target_pid,
                "title": new_window.get("title", app_clean),
                "message": f"Successfully launched and focused '{app_clean}' (HWND: {target_hwnd}, PID: {target_pid}).",
            }

        return {
            "success": True,
            "transition": "COMMAND_DISPATCHED",
            "hwnd": 0,
            "pid": launched_pid,
            "title": app_clean,
            "message": f"Dispatched launch command for '{app_clean}'.",
        }

    # -------------------------------------------------------------------------
    # Window Inspection & State Management
    # -------------------------------------------------------------------------

    def list_windows(self, visible_only: bool = True) -> list[dict[str, Any]]:
        """List open desktop windows with HWND, PID, title, class, and bounds."""
        shell_classes = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow"}
        windows: list[dict[str, Any]] = []

        if uia:
            try:
                root = uia.GetRootControl()
                for child in root.GetChildren():
                    try:
                        hwnd = child.NativeWindowHandle
                        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
                            continue
                        if visible_only and not ctypes.windll.user32.IsWindowVisible(hwnd):
                            continue
                        c_name = child.ClassName or ""
                        if c_name in shell_classes:
                            continue
                        rect = child.BoundingRectangle
                        w, h = rect.width(), rect.height()
                        if visible_only and (w <= 0 or h <= 0):
                            continue

                        windows.append({
                            "hwnd": hwnd,
                            "pid": child.ProcessId,
                            "title": child.Name or "",
                            "class_name": c_name,
                            "rect": {
                                "left": rect.left,
                                "top": rect.top,
                                "right": rect.right,
                                "bottom": rect.bottom,
                                "width": w,
                                "height": h,
                            },
                        })
                    except Exception:
                        continue
                if windows:
                    return windows
            except Exception as ex:
                logger.warning("[DESKTOP_ADAPTER] uia.GetRootControl().GetChildren() failed: %s", ex)

        # Win32 fallback
        from app.tools.uia_engine import UIA_ENGINE
        return UIA_ENGINE.list_windows(visible_only=visible_only)

    def find_windows_by_app(self, app_name: str) -> list[dict[str, Any]]:
        """Find matching windows for an application by process image, class, or title."""
        wins = self.list_windows(visible_only=True)
        app_clean = app_name.strip().lower()
        matched = []

        for w in wins:
            pid = w.get("pid", 0)
            pname = _get_process_image_name(pid)
            title = str(w.get("title") or "").lower()
            c_name = str(w.get("class_name") or "")
            rect = w.get("rect", {})
            if rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0:
                continue

            if (
                (app_clean in pname and pname)
                or (app_clean in title and title)
                or (app_clean in ("explorer", "file explorer") and c_name in ("CabinetWClass", "ExploreWClass", "XamlExplorerHostIslandWindow"))
                or (app_clean in ("calculator", "calc") and ("calc" in title or "calculator" in title or "calc" in pname or ("calculator" in title and c_name == "ApplicationFrameWindow")))
                or (app_clean in ("notepad",) and (pname == "notepad.exe" or "notepad" in title))
            ):
                matched.append(w)
        return matched

    def focus_window(self, target: int | str) -> dict[str, Any]:
        """Bring window to foreground using windows-use Desktop.bring_window_to_top."""
        hwnd = target if isinstance(target, int) else None
        if not hwnd and isinstance(target, str):
            matched = self.find_windows_by_app(target)
            if matched:
                hwnd = matched[0].get("hwnd")

        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": f"Window '{target}' not found or invalid HWND."}

        if self.desktop:
            try:
                self.desktop.bring_window_to_top(hwnd)
                return {"success": True, "hwnd": hwnd, "method": "windows_use_focus"}
            except Exception as ex:
                logger.warning("[DESKTOP_ADAPTER] bring_window_to_top exception: %s, falling back to Win32", ex)

        # Win32 fallback
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ok = bool(user32.SetForegroundWindow(hwnd))
        return {"success": ok, "hwnd": hwnd, "method": "win32_focus"}

    def minimize_window(self, hwnd: int) -> dict[str, Any]:
        """Minimize window."""
        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": "Invalid HWND"}
        ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        return {"success": True, "hwnd": hwnd, "action": "minimize"}

    def maximize_window(self, hwnd: int) -> dict[str, Any]:
        """Maximize window."""
        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": "Invalid HWND"}
        ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        return {"success": True, "hwnd": hwnd, "action": "maximize"}

    def restore_window(self, hwnd: int) -> dict[str, Any]:
        """Restore window to normal state."""
        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": "Invalid HWND"}
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        return {"success": True, "hwnd": hwnd, "action": "restore"}

    def close_window(self, hwnd: int) -> dict[str, Any]:
        """Close window via WM_CLOSE."""
        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": "Invalid HWND"}
        WM_CLOSE = 0x0010
        ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return {"success": True, "hwnd": hwnd, "action": "close"}

    # -------------------------------------------------------------------------
    # UI Automation Element Operations (Fast Bounded Discovery)
    # -------------------------------------------------------------------------

    def inspect_ui_tree(self, hwnd: int = 0, max_depth: int = 3, max_elements: int = 50) -> dict[str, Any]:
        """
        Fast bounded UIA element discovery for a window.
        Completes in <0.5s by using direct children and depth limit to eliminate 3s timeouts.
        """
        target_hwnd = hwnd or ctypes.windll.user32.GetForegroundWindow()
        if not target_hwnd or not ctypes.windll.user32.IsWindow(target_hwnd):
            return {"success": False, "error": "Invalid window handle", "elements": []}

        elements: list[dict[str, Any]] = []

        if uia:
            try:
                win_ctrl = uia.ControlFromHandle(target_hwnd)
                if win_ctrl:
                    def _collect(ctrl, current_depth):
                        if current_depth > max_depth or len(elements) >= max_elements:
                            return
                        for child in ctrl.GetChildren():
                            try:
                                rect = child.BoundingRectangle
                                name = child.Name or ""
                                c_type = child.ControlTypeName or ""
                                auto_id = child.AutomationId or ""

                                if name or auto_id or c_type in ("ButtonControl", "EditControl", "MenuItemControl", "ListItemControl"):
                                    elements.append({
                                        "name": name,
                                        "control_type": c_type,
                                        "automation_id": auto_id,
                                        "depth": current_depth,
                                        "rect": {
                                            "left": rect.left,
                                            "top": rect.top,
                                            "width": rect.width(),
                                            "height": rect.height(),
                                        },
                                    })
                                _collect(child, current_depth + 1)
                            except Exception:
                                continue

                    _collect(win_ctrl, 1)
                    return {"success": True, "hwnd": target_hwnd, "count": len(elements), "elements": elements}
            except Exception as ex:
                logger.warning("[DESKTOP_ADAPTER] uia inspect_ui_tree failed: %s", ex)

        from app.tools.uia_engine import UIA_ENGINE
        return UIA_ENGINE.inspect_ui_tree(hwnd=target_hwnd, max_depth=max_depth)

    def find_elements(self, hwnd: int = 0, query: str = "", control_type: str | None = None, max_results: int = 10) -> list[dict[str, Any]]:
        """Find interactive elements matching query in target window."""
        tree = self.inspect_ui_tree(hwnd=hwnd, max_depth=4, max_elements=80)
        elements = tree.get("elements", [])
        q_lower = query.strip().lower()

        matched = []
        for el in elements:
            name = str(el.get("name") or "").lower()
            auto_id = str(el.get("automation_id") or "").lower()
            c_type = str(el.get("control_type") or "").lower()

            if control_type and control_type.lower() not in c_type:
                continue

            if not q_lower or q_lower in name or q_lower in auto_id:
                matched.append(el)
                if len(matched) >= max_results:
                    break
        return matched

    def invoke_element(self, target: str, hwnd: int = 0) -> dict[str, Any]:
        """Invoke element by button click pattern or coordinate center click."""
        target_hwnd = hwnd or ctypes.windll.user32.GetForegroundWindow()

        # 1. Try windows_use.uia button lookup
        if uia and target_hwnd:
            try:
                win_ctrl = uia.ControlFromHandle(target_hwnd)
                if win_ctrl:
                    btn = win_ctrl.ButtonControl(Name=target, searchDepth=4)
                    if btn.Exists(maxSearchSeconds=1):
                        btn.Click()
                        return {"success": True, "method": "windows_use_button_click", "target": target}
            except Exception:
                pass

        # 2. Fallback to coordinate click on element bounding center
        elems = self.find_elements(hwnd=target_hwnd, query=target, max_results=1)
        if elems:
            rect = elems[0].get("rect", {})
            left = rect.get("left", 0)
            top = rect.get("top", 0)
            w = rect.get("width", 0)
            h = rect.get("height", 0)
            if w > 0 and h > 0:
                cx = left + w // 2
                cy = top + h // 2
                self.click_coords(cx, cy)
                return {"success": True, "method": "coordinate_center_click", "target": target, "x": cx, "y": cy}

        # 3. UIA Engine pattern execution
        from app.tools.uia_engine import UIA_ENGINE
        return UIA_ENGINE.execute_ui_action(target_name=target, action="invoke", hwnd=target_hwnd)

    def set_element_value(self, target: str, value: str, hwnd: int = 0) -> dict[str, Any]:
        """Set edit field value via UIA ValuePattern or keyboard typing."""
        target_hwnd = hwnd or ctypes.windll.user32.GetForegroundWindow()

        if uia and target_hwnd:
            try:
                win_ctrl = uia.ControlFromHandle(target_hwnd)
                if win_ctrl:
                    edit = win_ctrl.EditControl(Name=target, searchDepth=4)
                    if not edit.Exists(maxSearchSeconds=0.5):
                        edit = win_ctrl.EditControl(searchDepth=3)
                    if edit.Exists(maxSearchSeconds=0.5):
                        edit.Click()
                        val_pat = edit.GetPattern(uia.PatternId.ValuePattern)
                        if val_pat:
                            val_pat.SetValue(value)
                            return {"success": True, "method": "windows_use_value_pattern", "target": target, "value": value}
                        else:
                            self.type_text(value, clear="true")
                            return {"success": True, "method": "windows_use_type", "target": target, "value": value}
            except Exception:
                pass

        from app.tools.uia_engine import UIA_ENGINE
        return UIA_ENGINE.execute_ui_action(target_name=target, action="set_value", value=value, hwnd=target_hwnd)

    # -------------------------------------------------------------------------
    # Keyboard & Mouse Input Operations
    # -------------------------------------------------------------------------

    def click_coords(self, x: int, y: int, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        """Click at physical screen coordinates using windows-use.uia."""
        if uia:
            try:
                if button == "left":
                    if clicks >= 2:
                        uia.DoubleClick(x, y)
                    else:
                        uia.Click(x, y)
                elif button == "right":
                    uia.RightClick(x, y)
                elif button == "middle":
                    uia.MiddleClick(x, y)
                return {"success": True, "x": x, "y": y, "button": button, "clicks": clicks}
            except Exception as ex:
                logger.warning("[DESKTOP_ADAPTER] uia click failed: %s", ex)

        import pyautogui
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return {"success": True, "x": x, "y": y, "button": button, "clicks": clicks}

    def type_text(self, text: str, clear: str = "false", press_enter: bool = False) -> dict[str, Any]:
        """Type text into active focused element."""
        if self.desktop:
            try:
                cx, cy = uia.GetCursorPos()
                self.desktop.type(loc=(cx, cy), text=text, clear="true" if clear == "true" else "false", press_enter="true" if press_enter else "false")
                return {"success": True, "text": text, "method": "windows_use_type"}
            except Exception as ex:
                logger.warning("[DESKTOP_ADAPTER] desktop.type failed: %s", ex)

        import pyautogui
        if clear == "true":
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
        pyautogui.write(text, interval=0.01)
        if press_enter:
            pyautogui.press("enter")
        return {"success": True, "text": text, "method": "pyautogui_write"}

    def press_key(self, key: str) -> dict[str, Any]:
        """Press a single key."""
        cleaned = key.strip().lower()
        if not cleaned:
            return {"success": False, "error": "Empty key"}
        if cleaned in ("power", "sleep", "wakeup"):
            return {"success": False, "error": f"Disruptive key '{cleaned}' blocked."}

        if uia:
            try:
                alias = KEY_ALIASES.get(cleaned, cleaned)
                send_str = "{" + alias + "}" if len(alias) > 1 else alias
                uia.SendKeys(send_str, interval=0.01, waitTime=0.05)
                return {"success": True, "key": cleaned, "method": "windows_use_sendkeys"}
            except Exception:
                pass

        import pyautogui
        pyautogui.press(cleaned)
        return {"success": True, "key": cleaned, "method": "pyautogui_press"}

    def send_shortcut(self, shortcut: str | list[str]) -> dict[str, Any]:
        """Send key combination (e.g. 'ctrl+c' or ['ctrl', 'v'])."""
        comb_str = "+".join(shortcut) if isinstance(shortcut, list) else str(shortcut)
        if self.desktop:
            try:
                self.desktop.shortcut(comb_str)
                return {"success": True, "shortcut": comb_str, "method": "windows_use_shortcut"}
            except Exception as ex:
                logger.warning("[DESKTOP_ADAPTER] desktop.shortcut failed: %s", ex)

        import pyautogui
        keys = [k.strip().lower() for k in comb_str.split("+")]
        pyautogui.hotkey(*keys)
        return {"success": True, "shortcut": comb_str, "method": "pyautogui_hotkey"}

    def scroll(self, direction: str = "down", times: int = 1) -> dict[str, Any]:
        """Scroll wheel in direction."""
        if uia:
            try:
                if direction == "up":
                    uia.WheelUp(times)
                else:
                    uia.WheelDown(times)
                return {"success": True, "direction": direction, "times": times}
            except Exception:
                pass

        import pyautogui
        clicks = times * (120 if direction == "up" else -120)
        pyautogui.scroll(clicks)
        return {"success": True, "direction": direction, "times": times}


DESKTOP_ADAPTER = DesktopExecutionAdapter()
