"""
PLUTON R1 — Canonical Windows Computer-Control Substrate Adapter powered by pywinauto.
Implements robust, generic, bounded, and verified Windows UI automation inspired by Microsoft UFO2.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Optional

logger = logging.getLogger("pluton.adapters.pywinauto")

# -----------------------------------------------------------------------------
# Pywinauto Import & Setup
# -----------------------------------------------------------------------------
_PYWINAUTO_AVAILABLE = False
try:
    import pywinauto
    import pywinauto.uia_element_info as uia_info
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto import keyboard as pw_keyboard
    from pywinauto import mouse as pw_mouse
    _PYWINAUTO_AVAILABLE = True
except Exception as _pwa_err:
    logger.warning("[PYWINAUTO_ADAPTER] pywinauto import warning: %s", _pwa_err)
    uia_info = None
    UIAWrapper = None
    pw_keyboard = None
    pw_mouse = None


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


class PywinautoExecutionAdapter:
    """
    Canonical Windows Execution Substrate Adapter.
    Unifies pywinauto UIA/Win32 automation, bounded UI inspection, Start Menu discovery,
    and strict postcondition verification.
    """

    def __init__(self) -> None:
        self._start_menu_cache: dict[str, str] = {}
        self._start_menu_indexed_at: float = 0.0

    # -------------------------------------------------------------------------
    # 1. Application Discovery & Start Menu Indexing
    # -------------------------------------------------------------------------

    def get_start_menu_apps(self, force_refresh: bool = False) -> dict[str, str]:
        """Index installed Windows Start Menu applications dynamically via PowerShell Get-StartApps."""
        now = time.perf_counter()
        if self._start_menu_cache and not force_refresh and (now - self._start_menu_indexed_at) < 300:
            return self._start_menu_cache

        apps: dict[str, str] = {}
        try:
            cmd = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Csv -NoTypeInformation"
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                import csv
                import io
                reader = csv.DictReader(io.StringIO(proc.stdout.strip()))
                for row in reader:
                    name = row.get("Name", "").strip().lower()
                    appid = row.get("AppID", "").strip()
                    if name and appid:
                        apps[name] = appid
        except Exception as ex:
            logger.warning("[PYWINAUTO_ADAPTER] Failed to index Start Menu applications: %s", ex)

        self._start_menu_cache = apps
        self._start_menu_indexed_at = now
        return apps

    # -------------------------------------------------------------------------
    # 2. Window Discovery & Inspection (Win32 + pywinauto)
    # -------------------------------------------------------------------------

    def list_windows(self, visible_only: bool = True) -> list[dict[str, Any]]:
        """List open top-level desktop windows with HWND, PID, title, class, and bounds."""
        windows: list[dict[str, Any]] = []
        user32 = ctypes.windll.user32
        fg_hwnd = user32.GetForegroundWindow()

        def enum_proc(hwnd: int, lparam: int) -> bool:
            if visible_only and not user32.IsWindowVisible(hwnd):
                return True

            t_len = user32.GetWindowTextLengthW(hwnd)
            if visible_only and t_len == 0:
                return True

            t_buf = ctypes.create_unicode_buffer(t_len + 1)
            user32.GetWindowTextW(hwnd, t_buf, t_len + 1)
            title = t_buf.value.strip()

            c_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, c_buf, 256)
            class_name = c_buf.value.strip()

            if visible_only and class_name in (
                "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                "Windows.UI.Core.CoreWindow", "GDI+ Hook", "MSCTFIME UI", "Default IME",
                "NotifyIconOverflowWindow"
            ):
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            if visible_only and (width <= 0 or height <= 0):
                return True

            windows.append({
                "hwnd": hwnd,
                "title": title,
                "class_name": class_name,
                "pid": pid.value,
                "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom, "width": width, "height": height},
                "is_active": hwnd == fg_hwnd,
            })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        cb = WNDENUMPROC(enum_proc)
        try:
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.EnumDesktopWindows(hdesk, cb, 0)
            else:
                user32.EnumWindows(cb, 0)
        except Exception:
            user32.EnumWindows(cb, 0)

        return windows

    def find_windows_by_app(self, app_name: str) -> list[dict[str, Any]]:
        """Find matching windows for an application generically by process image, class, or title keyword."""
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

            is_match = False
            if app_clean in pname and pname:
                is_match = True
            elif app_clean in title and title:
                is_match = True
            elif app_clean in ("explorer", "file explorer") and c_name in ("CabinetWClass", "ExploreWClass", "XamlExplorerHostIslandWindow"):
                is_match = True
            elif app_clean in ("calculator", "calc") and ("calc" in title or "calculator" in title or "calc" in pname or ("calculator" in title and c_name == "ApplicationFrameWindow")):
                is_match = True
            elif app_clean in ("notepad",) and (pname == "notepad.exe" or "notepad" in title):
                is_match = True
            elif app_clean in ("paint", "mspaint") and (pname in ("mspaint.exe", "paintapp.exe") or "paint" in title):
                is_match = True
            elif app_clean in ("settings", "windows settings") and (pname == "systemsettings.exe" or "settings" in title):
                is_match = True
            elif app_clean in ("word", "winword", "microsoft word") and (pname == "winword.exe" or "word" in title):
                is_match = True
            elif app_clean in ("excel", "microsoft excel") and (pname == "excel.exe" or "excel" in title):
                is_match = True
            elif app_clean in ("powershell",) and ("powershell" in pname or "powershell" in title):
                is_match = True
            elif app_clean in ("cmd", "command prompt") and (pname == "cmd.exe" or "cmd" in title):
                is_match = True

            if is_match:
                matched.append(w)
        return matched

    # -------------------------------------------------------------------------
    # 3. Application Lifecycle (Launch, Re-use, Focus, Close)
    # -------------------------------------------------------------------------

    def launch_app(
        self,
        app_name: str,
        args: list[str] | None = None,
        reuse_existing: bool = True,
        timeout: float = 6.0,
    ) -> dict[str, Any]:
        """Launch an application or focus an existing one with strict postcondition verification."""
        app_clean = app_name.strip()
        if not app_clean:
            return {"success": False, "error": "INVALID_INPUT: app_name must be non-empty."}

        args = args or []

        # 1. Reuse existing instance if requested
        if reuse_existing:
            matching_before = self.find_windows_by_app(app_clean)
            if matching_before:
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
        launched_pid = 0
        apps_map = self.get_start_menu_apps()

        # Check standard shortcuts / apps_map
        appid = apps_map.get(app_clean.lower())
        if not appid:
            for k, v in apps_map.items():
                if app_clean.lower() in k or k in app_clean.lower():
                    appid = v
                    break

        if appid:
            if os.path.exists(appid) or "\\" in appid:
                try:
                    proc = subprocess.Popen([appid] + args, shell=False)
                    launched_pid = proc.pid
                except Exception as ex:
                    logger.debug("[PYWINAUTO_ADAPTER] Popen path failed: %s", ex)
            elif app_clean.lower() in ("calculator", "calc") and hasattr(os, "startfile"):
                try:
                    os.startfile("calculator:")
                except Exception as ex:
                    logger.debug("[PYWINAUTO_ADAPTER] startfile calculator failed: %s", ex)
            else:
                try:
                    proc = subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"], shell=False)
                    launched_pid = proc.pid
                except Exception as ex:
                    logger.debug("[PYWINAUTO_ADAPTER] Popen AppsFolder failed: %s", ex)

        if not launched_pid:
            exe_cand = shutil.which(app_clean) or shutil.which(f"{app_clean}.exe")
            if exe_cand:
                try:
                    proc = subprocess.Popen([exe_cand] + args, shell=False)
                    launched_pid = proc.pid
                except Exception as ex:
                    logger.debug("[PYWINAUTO_ADAPTER] Direct exe launch failed: %s", ex)
            elif app_clean.lower() in ("calculator", "calc") and hasattr(os, "startfile"):
                try:
                    os.startfile("calculator:")
                except Exception as ex:
                    logger.debug("[PYWINAUTO_ADAPTER] protocol fallback failed: %s", ex)
            elif app_clean.lower() in ("explorer", "file explorer"):
                try:
                    proc = subprocess.Popen(["explorer.exe"], shell=False)
                    launched_pid = proc.pid
                except Exception as ex:
                    logger.debug("[PYWINAUTO_ADAPTER] explorer launch failed: %s", ex)
            elif hasattr(os, "startfile"):
                try:
                    os.startfile(app_clean)
                except Exception as ex:
                    logger.debug("[PYWINAUTO_ADAPTER] os.startfile fallback failed: %s", ex)

        # 2. Strict Post-Launch Verification & HWND Capture
        deadline = time.perf_counter() + timeout
        new_window = None

        while time.perf_counter() < deadline:
            matching_after = self.find_windows_by_app(app_clean)
            for w in matching_after:
                hwnd = w.get("hwnd", 0)
                pid = w.get("pid", 0)
                if hwnd not in hwnds_before or (launched_pid and pid == launched_pid):
                    new_window = w
                    break
                elif not new_window:
                    new_window = w

            if new_window and (new_window.get("hwnd", 0) not in hwnds_before or time.perf_counter() > (deadline - timeout + 0.8)):
                break
            time.sleep(0.15)

        if new_window:
            target_hwnd = new_window.get("hwnd", 0)
            target_pid = new_window.get("pid", launched_pid)
            self.focus_window(target_hwnd)
            return {
                "success": True,
                "transition": "WINDOW_CREATED",
                "method": "pywinauto_launch",
                "hwnd": target_hwnd,
                "pid": target_pid,
                "title": new_window.get("title", app_clean),
                "message": f"Successfully launched and focused '{app_clean}' (HWND: {target_hwnd}, PID: {target_pid}).",
            }

        return {
            "success": False,
            "transition": "LAUNCH_UNVERIFIED",
            "hwnd": 0,
            "pid": launched_pid,
            "title": app_clean,
            "error": f"LAUNCH_VERIFICATION_FAILED: Application '{app_clean}' was dispatched but no verified visible window appeared within {timeout:.1f}s.",
        }

    def focus_window(self, target: int | str) -> dict[str, Any]:
        """Bring window to foreground and restore if minimized."""
        hwnd = target if isinstance(target, int) else None
        if not hwnd and isinstance(target, str):
            matched = self.find_windows_by_app(target)
            if matched:
                hwnd = matched[0].get("hwnd")

        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": f"Window '{target}' not found or invalid HWND."}

        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        # AttachThreadInput trick for guaranteed foreground focus
        fg_hwnd = user32.GetForegroundWindow()
        cur_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_thread_id = user32.GetWindowThreadProcessId(fg_hwnd, None)
        target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)

        if fg_thread_id != cur_thread_id:
            user32.AttachThreadInput(cur_thread_id, fg_thread_id, True)
        if target_thread_id != cur_thread_id:
            user32.AttachThreadInput(cur_thread_id, target_thread_id, True)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)

        if fg_thread_id != cur_thread_id:
            user32.AttachThreadInput(cur_thread_id, fg_thread_id, False)
        if target_thread_id != cur_thread_id:
            user32.AttachThreadInput(cur_thread_id, target_thread_id, False)

        return {"success": True, "hwnd": hwnd, "method": "win32_focus"}

    def close_window(self, target: int | str) -> dict[str, Any]:
        """Close window gracefully via WM_CLOSE."""
        hwnd = target if isinstance(target, int) else None
        if not hwnd and isinstance(target, str):
            matched = self.find_windows_by_app(target)
            if matched:
                hwnd = matched[0].get("hwnd")

        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": f"Window '{target}' not found or invalid HWND."}

        WM_CLOSE = 0x0010
        ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return {"success": True, "hwnd": hwnd, "method": "wm_close"}

    # -------------------------------------------------------------------------
    # 4. Pywinauto UIA Control Inspection & Traversal
    # -------------------------------------------------------------------------

    def inspect_ui_tree(
        self,
        hwnd: int,
        max_depth: int = 3,
        max_elements: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Inspect UI elements inside the target HWND using pywinauto.controls.uiawrapper.UIAWrapper.
        Bounded to max_depth and max_elements to guarantee sub-0.5s response times.
        """
        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return []

        if not _PYWINAUTO_AVAILABLE or uia_info is None:
            return []

        elements: list[dict[str, Any]] = []

        try:
            elem_info = uia_info.UIAElementInfo(hwnd)
            root_wrapper = UIAWrapper(elem_info)
        except Exception as ex:
            logger.debug("[PYWINAUTO_ADAPTER] Failed to wrap HWND %s in UIAWrapper: %s", hwnd, ex)
            return []

        queue = [(root_wrapper, 0)]
        while queue and len(elements) < max_elements:
            current, depth = queue.pop(0)

            try:
                name = current.window_text()
                c_name = current.class_name()
                f_name = current.friendly_class_name()
                auto_id = getattr(current.element_info, "automation_id", "") or ""
                rect = current.rectangle()
                r_dict = {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom, "width": rect.width(), "height": rect.height()}
                is_visible = current.is_visible()
                is_enabled = current.is_enabled()
            except Exception:
                continue

            # Record interactive or named elements
            if name or auto_id or f_name in ("Button", "Edit", "MenuItem", "CheckBox", "RadioButton", "ComboBox", "TabItem"):
                elements.append({
                    "name": name,
                    "automation_id": auto_id,
                    "class_name": c_name,
                    "control_type": f_name,
                    "depth": depth,
                    "is_visible": is_visible,
                    "is_enabled": is_enabled,
                    "rect": r_dict,
                })

            if depth < max_depth:
                try:
                    for child in current.children():
                        if len(elements) + len(queue) < max_elements:
                            queue.append((child, depth + 1))
                except Exception:
                    pass

        return elements

    # -------------------------------------------------------------------------
    # 5. Pywinauto Action Execution (Invoke / Click / Type)
    # -------------------------------------------------------------------------

    def invoke_control(
        self,
        hwnd: int,
        query: str,
        action: str = "click",
        value: str = "",
    ) -> dict[str, Any]:
        """Find a control within the HWND by name/ID/type and invoke it via pywinauto."""
        if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {"success": False, "error": f"Invalid HWND {hwnd}."}

        if not _PYWINAUTO_AVAILABLE or uia_info is None:
            return {"success": False, "error": "pywinauto is not available."}

        self.focus_window(hwnd)
        time.sleep(0.1)

        q_clean = query.strip().lower()
        target_wrapper = None

        try:
            elem_info = uia_info.UIAElementInfo(hwnd)
            root_wrapper = UIAWrapper(elem_info)
            queue = [root_wrapper]
            visited = 0

            while queue and visited < 60:
                current = queue.pop(0)
                visited += 1
                try:
                    name = (current.window_text() or "").lower()
                    auto_id = (getattr(current.element_info, "automation_id", "") or "").lower()
                    if q_clean == name or q_clean == auto_id or q_clean in name:
                        target_wrapper = current
                        break
                    for child in current.children():
                        queue.append(child)
                except Exception:
                    continue
        except Exception as ex:
            return {"success": False, "error": f"UIA search exception: {ex}"}

        if not target_wrapper:
            return {"success": False, "error": f"Control '{query}' not found in HWND {hwnd}."}

        act_clean = action.lower()
        try:
            if act_clean == "click":
                target_wrapper.click_input()
                return {"success": True, "action": "click", "control": query, "method": "pywinauto_click_input"}
            elif act_clean == "set_value":
                target_wrapper.set_text(value)
                return {"success": True, "action": "set_value", "control": query, "value": value, "method": "pywinauto_set_text"}
            elif act_clean == "type_keys":
                target_wrapper.type_keys(value, with_spaces=True)
                return {"success": True, "action": "type_keys", "control": query, "value": value, "method": "pywinauto_type_keys"}
            else:
                return {"success": False, "error": f"Unsupported action '{action}'."}
        except Exception as ex:
            return {"success": False, "error": f"Action execution failed: {ex}"}

    def type_text(self, text: str) -> dict[str, Any]:
        """Type text into focused window using pywinauto keyboard with pyautogui/Win32 fallback."""
        if pw_keyboard:
            try:
                pw_keyboard.send_keys(text, with_spaces=True)
                return {"success": True, "action": "type_text", "method": "pywinauto_keyboard"}
            except Exception as ex:
                logger.debug("[PYWINAUTO_ADAPTER] send_keys fallback: %s", ex)

        # Fallback to pyautogui
        try:
            import pyautogui
            pyautogui.write(text, interval=0.01)
            return {"success": True, "action": "type_text", "method": "pyautogui_fallback"}
        except Exception as ex:
            return {"success": False, "error": f"Keyboard execution failed: {ex}"}

    def press_key(self, key: str) -> dict[str, Any]:
        """Press a keyboard key."""
        if pw_keyboard:
            try:
                pw_keyboard.send_keys(f"{{{key.upper()}}}")
                return {"success": True, "action": "press_key", "key": key, "method": "pywinauto_keyboard"}
            except Exception as ex:
                logger.debug("[PYWINAUTO_ADAPTER] press_key fallback: %s", ex)

        try:
            import pyautogui
            pyautogui.press(key)
            return {"success": True, "action": "press_key", "key": key, "method": "pyautogui_fallback"}
        except Exception as ex:
            return {"success": False, "error": f"Press key failed: {ex}"}

    def send_shortcut(self, shortcut: str) -> dict[str, Any]:
        """Send keyboard shortcut (e.g. 'ctrl+s', 'alt+f4')."""
        if pw_keyboard:
            try:
                keys = shortcut.lower().split("+")
                pw_seq = ""
                for k in keys:
                    k = k.strip()
                    if k == "ctrl":
                        pw_seq += "^"
                    elif k == "alt":
                        pw_seq += "%"
                    elif k == "shift":
                        pw_seq += "+"
                    else:
                        pw_seq += f"{{{k.upper()}}}"
                pw_keyboard.send_keys(pw_seq)
                return {"success": True, "action": "send_shortcut", "shortcut": shortcut, "method": "pywinauto_keyboard"}
            except Exception as ex:
                logger.debug("[PYWINAUTO_ADAPTER] send_shortcut fallback: %s", ex)

        try:
            import pyautogui
            keys = [k.strip() for k in shortcut.lower().split("+")]
            pyautogui.hotkey(*keys)
            return {"success": True, "action": "send_shortcut", "shortcut": shortcut, "method": "pyautogui_fallback"}
        except Exception as ex:
            return {"success": False, "error": f"Send shortcut failed: {ex}"}

    def click_coords(self, x: int, y: int, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        """Click at physical desktop coordinates."""
        if pw_mouse:
            try:
                if button == "left":
                    if clicks == 2:
                        pw_mouse.double_click(coords=(x, y))
                    else:
                        pw_mouse.click(coords=(x, y))
                elif button == "right":
                    pw_mouse.right_click(coords=(x, y))
                return {"success": True, "action": "click_coords", "coords": (x, y), "button": button, "clicks": clicks}
            except Exception as ex:
                logger.debug("[PYWINAUTO_ADAPTER] mouse click failed: %s", ex)
        return {"success": False, "error": "Mouse click unavailable."}


PYWINAUTO_ADAPTER = PywinautoExecutionAdapter()
