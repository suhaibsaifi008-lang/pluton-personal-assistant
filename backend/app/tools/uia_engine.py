"""General Windows UI Automation Engine for PLUTON.

Provides robust, structured desktop application control, semantic element resolution,
UI tree inspection, and pattern-based UI interactions without relying on screen coordinates.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import difflib
import logging
import os
import re
import sys
import time
from typing import Any, Callable, Sequence

from .computer_safety import assert_computer_control_allowed, is_computer_control_allowed

logger = logging.getLogger(__name__)


# Cache desktop handle to prevent unnecessary attachment calls
_DESKTOP_ATTACHED = False


def attach_interactive_desktop() -> bool:
    """Ensure current thread can access interactive desktop windows."""
    if sys.platform != "win32":
        return True
    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            return True
    except Exception:
        pass
    return False


class UIAutomationEngine:
    """High-level engine for Windows UI Automation and structured desktop application control."""

    def __init__(self) -> None:
        self.is_windows = sys.platform == "win32"

    # --------------------------------------------------------------------------
    # Window & Process Management
    # --------------------------------------------------------------------------

    def list_windows(self, visible_only: bool = True) -> list[dict[str, Any]]:
        """List all top-level windows on the interactive desktop."""
        if not self.is_windows:
            return []

        attach_interactive_desktop()
        user32 = ctypes.windll.user32
        windows: list[dict[str, Any]] = []

        def enum_proc(hwnd: int, lParam: int) -> bool:
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

            # Ignore shell tooltips, GDI+ helper windows, or invisible system windows
            if visible_only and (
                class_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow", "GDI+ Hook", "MSCTFIME UI", "Default IME")
                or title.startswith("GDI+ Window")
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
                "is_active": hwnd == user32.GetForegroundWindow(),
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

    def find_window(self, query: str) -> dict[str, Any] | None:
        """Find the best-matching window by title, process, application keyword, or shell class."""
        if not query or not self.is_windows:
            return None

        windows = self.list_windows(visible_only=True)
        q = query.strip().lower()

        # 1. Exact title match (case-insensitive)
        for win in windows:
            if win["title"].lower() == q:
                return win

        # 2. Substring match in title
        for win in windows:
            if q in win["title"].lower():
                return win

        # 3. Shell Window / File Explorer mapping (CabinetWClass / ExploreWClass)
        if q in ("file explorer", "explorer", "windows explorer", "folder"):
            for win in windows:
                if win.get("class_name") in ("CabinetWClass", "ExploreWClass"):
                    return win

        # 4. Modern UWP / WinUI Application Frame mapping
        if q in ("calculator", "calc"):
            for win in windows:
                if "calculator" in win.get("title", "").lower() or (win.get("class_name") == "ApplicationFrameWindow" and "calc" in win.get("title", "").lower()):
                    return win

        # 5. Class name match (e.g. 'CabinetWClass', 'Chrome_WidgetWin_1')
        for win in windows:
            if q in win["class_name"].lower():
                return win

        # 6. Token match: all tokens present in title
        tokens = [tok for tok in q.split() if len(tok) >= 2]
        if tokens:
            for win in windows:
                if all(tok in win["title"].lower() for tok in tokens):
                    return win

        # 7. Fuzzy match on title
        titles = [win["title"] for win in windows if win["title"]]
        matches = difflib.get_close_matches(query, titles, n=1, cutoff=0.5)
        if matches:
            for win in windows:
                if win["title"] == matches[0]:
                    return win

        return None

    def focus_window(self, hwnd: int) -> bool:
        """Bring target window to foreground and attach input."""
        if not self.is_windows or not hwnd or not is_computer_control_allowed():
            return False

        attach_interactive_desktop()
        user32 = ctypes.windll.user32
        try:
            # Standard Win32 workaround to allow foreground transition
            user32.keybd_event(0, 0, 0, 0)
            # Restore if minimized
            if user32.IsIconic(hwnd) or user32.GetForegroundWindow() != hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            else:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW

            # Attach thread input to bypass foreground lock restrictions
            fore_hwnd = user32.GetForegroundWindow()
            cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0

            if fore_thread and fore_thread != cur_thread:
                user32.AttachThreadInput(cur_thread, fore_thread, True)

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

            if fore_thread and fore_thread != cur_thread:
                user32.AttachThreadInput(cur_thread, fore_thread, False)

            # Poll for up to 0.8s for window focus transition to complete
            deadline = time.perf_counter() + 0.8
            while time.perf_counter() < deadline:
                active_h = user32.GetForegroundWindow()
                if active_h == hwnd:
                    return True
                time.sleep(0.05)

            return user32.GetForegroundWindow() == hwnd
        except Exception as e:
            logger.debug("Error focusing window %s: %s", hwnd, e)
            return False



    def close_window(self, hwnd: int) -> bool:
        """Safely close a window using WM_CLOSE."""
        if not self.is_windows or not hwnd or not is_computer_control_allowed():
            return False
        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.3)
        return not bool(user32.IsWindow(hwnd))


    def get_foreground_window(self) -> dict[str, Any]:
        """Get canonical structured metadata about the currently focused desktop window."""
        if not self.is_windows:
            return {"active": False, "hwnd": 0, "pid": 0, "title": "", "process": "", "class_name": "", "visibility": False}

        attach_interactive_desktop()
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindow(hwnd):
            return {"active": False, "hwnd": 0, "pid": 0, "title": "", "process": "", "class_name": "", "visibility": False}

        # Resolve root ancestor to avoid child/GDI+ helper window trapping
        root_hwnd = user32.GetAncestor(hwnd, 2)
        if root_hwnd and user32.IsWindow(root_hwnd):
            hwnd = root_hwnd

        t_len = user32.GetWindowTextLengthW(hwnd)
        t_buf = ctypes.create_unicode_buffer(t_len + 1)
        user32.GetWindowTextW(hwnd, t_buf, t_len + 1)
        title = t_buf.value.strip()

        c_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, c_buf, 256)
        class_name = c_buf.value.strip()

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        return {
            "active": True,
            "hwnd": hwnd,
            "pid": pid.value,
            "title": title,
            "process": class_name,
            "class_name": class_name,
            "visibility": bool(user32.IsWindowVisible(hwnd) and w > 0 and h > 0),
            "rect": {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
                "width": w,
                "height": h,
            },
            "is_active": True,
        }

    get_active_window_info = get_foreground_window

    def window_state(self, hwnd: int) -> dict[str, Any]:
        """Get structured window state (minimized, maximized, normal)."""
        if not self.is_windows or not hwnd:
            return {"hwnd": 0, "state": "not_found", "active": False}
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return {"hwnd": hwnd, "state": "invalid", "active": False}
        is_minimized = bool(user32.IsIconic(hwnd))
        is_zoomed = bool(user32.IsZoomed(hwnd))
        state_str = "minimized" if is_minimized else ("maximized" if is_zoomed else "normal")
        return {
            "hwnd": hwnd,
            "state": state_str,
            "visible": bool(user32.IsWindowVisible(hwnd)),
            "foreground": user32.GetForegroundWindow() == hwnd,
        }

    def inspect_tree(self, hwnd: int | None = None, max_depth: int = 4) -> dict[str, Any]:
        """Inspect UI Automation accessibility tree."""
        return self.inspect_ui_tree(hwnd=hwnd, max_depth=max_depth)

    def find_element(self, query: str, hwnd: int | None = None, control_type: str | None = None) -> dict[str, Any] | None:
        """Find single element matching query."""
        elems = self.find_elements_by_query(query=query, hwnd=hwnd, control_type=control_type, max_results=1)
        return elems[0] if elems else None

    def find_elements(self, query: str, hwnd: int | None = None, control_type: str | None = None) -> list[dict[str, Any]]:
        """Find all elements matching query."""
        return self.find_elements_by_query(query=query, hwnd=hwnd, control_type=control_type, max_results=10)

    def invoke(self, element_id: str | int, hwnd: int | None = None) -> dict[str, Any]:
        """Invoke element action."""
        return self.execute_ui_action(target_name=str(element_id), action="invoke", hwnd=hwnd)

    def set_value(self, element_id: str | int, value: str, hwnd: int | None = None) -> dict[str, Any]:
        """Set edit value."""
        return self.execute_ui_action(target_name=str(element_id), action="set_value", value=value, hwnd=hwnd)

    def toggle(self, element_id: str | int, hwnd: int | None = None) -> dict[str, Any]:
        """Toggle checkbox or switch."""
        return self.execute_ui_action(target_name=str(element_id), action="toggle", hwnd=hwnd)

    def select(self, element_id: str | int, value: str | None = None, hwnd: int | None = None) -> dict[str, Any]:
        """Select item in list or dropdown."""
        return self.execute_ui_action(target_name=str(element_id), action="select", value=value, hwnd=hwnd)

    def expand_collapse(self, element_id: str | int, expand: bool = True, hwnd: int | None = None) -> dict[str, Any]:
        """Expand or collapse item."""
        act = "expand" if expand else "collapse"
        return self.execute_ui_action(target_name=str(element_id), action=act, hwnd=hwnd)

    def focus(self, element_id: str | int, hwnd: int | None = None) -> dict[str, Any]:
        """Focus specific UI element."""
        elem, err = self.find_ui_element(name=str(element_id), hwnd=hwnd)
        if elem is None:
            return {"success": False, "error": err}
        try:
            elem.SetFocus()
            return {"success": True, "element": (elem.Name or str(element_id)).strip()}
        except Exception as e:
            return {"success": False, "error": f"Failed to focus element: {e}"}

    def read_window_text(self, hwnd: int | None = None) -> str:
        """Read all accessible text content from a window (Win32, UWP, XAML, or Shell)."""
        if not self.is_windows:
            return ""
        target_hwnd = hwnd or (self.get_foreground_window().get("hwnd") or 0)
        if not target_hwnd:
            return ""
        from .keyboard_pipeline import _uia_read_text
        return _uia_read_text(target_hwnd) or ""

    def read_element_state(self, target_name: str | None = None, hwnd: int | None = None) -> dict[str, Any]:
        """Read detailed live state (text, value, toggle, selection, focus) of a target UI element."""
        if not self.is_windows:
            return {"error": "Windows platform required"}
        target_hwnd = hwnd or (self.get_foreground_window().get("hwnd") or 0)
        elem, err = self.find_ui_element(name=target_name, hwnd=target_hwnd)
        if elem is None:
            return {"found": False, "error": err}

        elem_name = (elem.Name or "").strip()
        c_type = elem.ControlTypeName
        auto_id = (elem.AutomationId or "").strip()
        rect = elem.BoundingRectangle

        val_str = ""
        vp = getattr(elem, "GetValuePattern", lambda: None)()
        if vp:
            try:
                val_str = vp.Value or ""
            except Exception:
                pass

        if not val_str:
            leg = getattr(elem, "GetLegacyIAccessiblePattern", lambda: None)()
            if leg:
                try:
                    val_str = leg.Value or ""
                except Exception:
                    pass

        toggle_state = None
        tp = getattr(elem, "GetTogglePattern", lambda: None)()
        if tp:
            try:
                toggle_state = tp.ToggleState
            except Exception:
                pass

        is_selected = None
        sp = getattr(elem, "GetSelectionItemPattern", lambda: None)()
        if sp:
            try:
                is_selected = bool(sp.IsSelected)
            except Exception:
                pass

        return {
            "found": True,
            "name": elem_name,
            "control_type": c_type,
            "automation_id": auto_id,
            "value": val_str,
            "text": elem_name if not val_str else val_str,
            "toggle_state": toggle_state,
            "is_selected": is_selected,
            "bounding_box": [rect.left, rect.top, rect.width(), rect.height()] if rect else None,
        }

    # --------------------------------------------------------------------------
    # UI Automation Tree & Element Resolution
    # --------------------------------------------------------------------------

    def _get_root_control(self, hwnd: int | None = None) -> Any:
        """Get UIA Control from HWND or Desktop Root."""
        if not self.is_windows:
            return None
        try:
            import uiautomation as auto
            if hwnd:
                # Trigger Chromium / Win32 AX engine
                ctypes.windll.user32.SendMessageW(hwnd, 0x003D, 0, 0xFFFFFFFC)
                return auto.ControlFromHandle(hwnd)
            return auto.GetRootControl()
        except Exception as e:
            logger.debug("Failed to get UIA root control: %s", e)
            return None

    def inspect_ui_tree(
        self,
        hwnd: int | None = None,
        max_depth: int = 5,
        max_elements: int = 150,
        control_types: Sequence[str] | None = None,
        include_unnamed: bool = False,
    ) -> dict[str, Any]:
        """Inspect and return a pruned, structured summary of UI controls for a window or desktop."""
        if not self.is_windows:
            return {"error": "UI Automation requires Windows platform."}

        root = self._get_root_control(hwnd)
        if root is None:
            return {"error": f"Could not acquire UIA control from HWND {hwnd}."}

        elements: list[dict[str, Any]] = []
        filter_types_lower = {ct.lower() for ct in control_types} if control_types else None

        def walk(elem: Any, depth: int) -> None:
            if depth > max_depth or len(elements) >= max_elements or elem is None:
                return

            try:
                c_type = elem.ControlTypeName
                name = (elem.Name or "").strip()
                auto_id = (elem.AutomationId or "").strip()

                # Determine if element should be included
                type_match = True
                if filter_types_lower:
                    type_match = any(ft in c_type.lower() for ft in filter_types_lower)

                has_info = bool(name or auto_id or "tab" in c_type.lower() or "button" in c_type.lower() or "edit" in c_type.lower())
                should_include = type_match and (include_unnamed or has_info)

                if should_include:
                    rect = elem.BoundingRectangle
                    elem_dict: dict[str, Any] = {
                        "type": c_type,
                        "name": name,
                        "depth": depth,
                        "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom, "width": rect.width(), "height": rect.height()},
                    }
                    if auto_id:
                        elem_dict["automation_id"] = auto_id

                    # Check pattern capabilities
                    supported_patterns = []
                    for pat_name, pat_method in [
                        ("invoke", "GetInvokePattern"),
                        ("value", "GetValuePattern"),
                        ("toggle", "GetTogglePattern"),
                        ("select_item", "GetSelectionItemPattern"),
                        ("expand_collapse", "GetExpandCollapsePattern"),
                    ]:
                        try:
                            pat = getattr(elem, pat_method, None)
                            if pat and pat():
                                supported_patterns.append(pat_name)
                        except Exception:
                            pass
                    if supported_patterns:
                        elem_dict["patterns"] = supported_patterns

                    elements.append(elem_dict)

                for child in elem.GetChildren():
                    walk(child, depth + 1)
            except Exception:
                pass

        walk(root, 0)

        win_info = self.get_active_window_info() if not hwnd else {"hwnd": hwnd}
        return {
            "window": win_info,
            "element_count": len(elements),
            "elements": elements,
            "truncated": len(elements) >= max_elements,
        }

    def find_ui_elements(
        self,
        name: str | None = None,
        control_type: str | None = None,
        automation_id: str | None = None,
        hwnd: int | None = None,
        max_results: int = 20,
    ) -> list[tuple[Any, float, str]]:
        """Search UIA tree and return matching elements sorted by relevance score (elem, score, matched_name)."""
        if not self.is_windows:
            return []

        root = self._get_root_control(hwnd)
        if root is None:
            return []

        matches: list[tuple[Any, float, str]] = []
        name_clean = name.strip().lower() if name else ""
        type_clean = control_type.strip().lower() if control_type else ""
        id_clean = automation_id.strip().lower() if automation_id else ""
        tokens = [t for t in name_clean.split() if len(t) >= 2] if name_clean else []

        def evaluate_elem(elem: Any, depth: int) -> None:
            if depth > 10 or len(matches) >= 100 or elem is None:
                return

            try:
                c_type = elem.ControlTypeName
                elem_name = (elem.Name or "").strip()
                elem_id = (elem.AutomationId or "").strip()
                elem_name_lower = elem_name.lower()

                # Control type filter
                if type_clean and type_clean not in c_type.lower():
                    # If user requested 'button', also match 'ButtonControl' etc.
                    pass
                elif not type_clean or type_clean in c_type.lower():
                    score = 0.0

                    if id_clean and elem_id.lower() == id_clean:
                        score += 1.0

                    if name_clean:
                        # Exact match
                        if elem_name_lower == name_clean:
                            score += 1.0
                        # Exact normalized match
                        elif re.sub(r"\s+", " ", elem_name_lower) == re.sub(r"\s+", " ", name_clean):
                            score += 0.95
                        # Substring match
                        elif name_clean in elem_name_lower:
                            score += 0.85
                        # All tokens match
                        elif tokens and all(tok in elem_name_lower for tok in tokens):
                            score += 0.80
                        # Prefix match
                        elif len(name_clean) >= 4 and elem_name_lower.startswith(name_clean[:4]):
                            score += 0.70
                        else:
                            ratio = difflib.SequenceMatcher(None, name_clean, elem_name_lower).ratio()
                            if ratio >= 0.75:
                                score += ratio * 0.75

                    if score > 0.4:
                        matches.append((elem, score, elem_name))


                children = []
                try:
                    children = elem.GetChildren()
                except (Exception, SystemError, WindowsError):
                    children = []
                for child in children:
                    evaluate_elem(child, depth + 1)
            except (Exception, SystemError, WindowsError):
                pass


        evaluate_elem(root, 0)

        # Sort descending by match score
        matches.sort(key=lambda item: item[1], reverse=True)
        return matches[:max_results]

    def find_elements_by_query(
        self,
        query: str = "",
        hwnd: int | None = None,
        control_type: str | None = None,
        automation_id: str | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Find matching UI elements by query string and return serialized metadata dicts."""
        matches = self.find_ui_elements(
            name=query,
            control_type=control_type,
            automation_id=automation_id,
            hwnd=hwnd,
            max_results=max_results,
        )
        results = []
        for elem, score, matched_name in matches:
            try:
                rect = elem.BoundingRectangle
                c_type = elem.ControlTypeName
                auto_id = (elem.AutomationId or "").strip()
                results.append({
                    "name": matched_name,
                    "control_type": c_type,
                    "automation_id": auto_id,
                    "confidence": score,
                    "bounding_rectangle": [rect.left, rect.top, rect.width(), rect.height()],
                    "rect": {"left": rect.left, "top": rect.top, "width": rect.width(), "height": rect.height()},
                })
            except Exception:
                pass
        return results

    def find_ui_element(
        self,
        name: str | None = None,
        control_type: str | None = None,
        automation_id: str | None = None,
        hwnd: int | None = None,
    ) -> tuple[Any | None, str]:
        """Find a single unique UI element. Reports ambiguity if multiple conflicting elements exist."""
        candidates = self.find_ui_elements(
            name=name,
            control_type=control_type,
            automation_id=automation_id,
            hwnd=hwnd,
            max_results=5,
        )

        if not candidates:
            return None, f"No UI element found matching name='{name}', type='{control_type}'."

        best_elem, best_score, best_name = candidates[0]

        # Ambiguity detection: check if runner-up candidate is equally plausible
        if len(candidates) > 1 and best_score < 0.95:
            second_elem, second_score, second_name = candidates[1]
            if abs(best_score - second_score) < 0.05 and best_name.lower() != second_name.lower():
                names = [c[2] for c in candidates[:3]]
                return None, f"Ambiguous match: multiple elements matched query '{name}' ({', '.join(names)}). Please be more specific."

        return best_elem, ""

    # --------------------------------------------------------------------------
    # Semantic UI Pattern Action Execution
    # --------------------------------------------------------------------------

    def execute_ui_action(
        self,
        target_name: str,
        action: str = "invoke",
        control_type: str | None = None,
        value: str | None = None,
        hwnd: int | None = None,
    ) -> dict[str, Any]:
        """Execute a structured UI action on a target element using native UIA patterns."""
        if not is_computer_control_allowed():
            return {"success": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
        if not self.is_windows:
            return {"success": False, "error": "Windows UI Automation is only available on Windows."}


        # Step 1: Resolve element
        elem, err = self.find_ui_element(name=target_name, control_type=control_type, hwnd=hwnd)
        if elem is None:
            return {"success": False, "failed_step": "locate", "reason": err}

        elem_name = (elem.Name or target_name).strip()
        c_type = elem.ControlTypeName
        rect = elem.BoundingRectangle

        action_clean = action.strip().lower()

        # Step 2: Execute pattern
        try:
            if action_clean in ("invoke", "click"):
                # Try InvokePattern
                inv = getattr(elem, "GetInvokePattern", lambda: None)()
                if inv:
                    inv.Invoke()
                    return {"success": True, "method": "InvokePattern", "element": elem_name, "type": c_type}

                # Try TogglePattern (for checkboxes/toggle buttons)
                tog = getattr(elem, "GetTogglePattern", lambda: None)()
                if tog:
                    tog.Toggle()
                    return {"success": True, "method": "TogglePattern", "element": elem_name, "type": c_type}

                # Try SelectionItemPattern (for tabs, list items)
                sel_item = getattr(elem, "GetSelectionItemPattern", lambda: None)()
                if sel_item:
                    sel_item.Select()
                    return {"success": True, "method": "SelectionItemPattern", "element": elem_name, "type": c_type}

                # Fallback to direct UIA click if bounding rectangle is valid
                rect = getattr(elem, "BoundingRectangle", None)
                if rect and rect.width() > 0 and rect.height() > 0:
                    elem.Click()
                    return {"success": True, "method": "UIA_Click", "element": elem_name, "type": c_type}
                return {"success": False, "reason": f"Element '{elem_name}' has no clickable bounding rectangle or invoke pattern."}


            elif action_clean in ("set_value", "type", "enter_text"):
                val_to_set = value or ""
                # Try ValuePattern
                val_pat = getattr(elem, "GetValuePattern", lambda: None)()
                if val_pat:
                    val_pat.SetValue(val_to_set)
                    return {"success": True, "method": "ValuePattern", "element": elem_name, "value_set": val_to_set}

                # Fallback: focus and send keys
                elem.SetFocus()
                time.sleep(0.05)
                import pyautogui
                pyautogui.write(val_to_set, interval=0.0)
                return {"success": True, "method": "FocusAndType", "element": elem_name, "value_set": val_to_set}

            elif action_clean in ("toggle", "check", "uncheck"):
                tog = getattr(elem, "GetTogglePattern", lambda: None)()
                if tog:
                    tog.Toggle()
                    return {"success": True, "method": "TogglePattern", "element": elem_name}
                inv = getattr(elem, "GetInvokePattern", lambda: None)()
                if inv:
                    inv.Invoke()
                    return {"success": True, "method": "InvokePattern", "element": elem_name}
                elem.Click()
                return {"success": True, "method": "UIA_Click", "element": elem_name}

            elif action_clean in ("select", "switch_tab"):
                sel_item = getattr(elem, "GetSelectionItemPattern", lambda: None)()
                if sel_item:
                    sel_item.Select()
                    return {"success": True, "method": "SelectionItemPattern", "element": elem_name}
                inv = getattr(elem, "GetInvokePattern", lambda: None)()
                if inv:
                    inv.Invoke()
                    return {"success": True, "method": "InvokePattern", "element": elem_name}
                elem.Click()
                return {"success": True, "method": "UIA_Click", "element": elem_name}

            elif action_clean in ("expand", "collapse"):
                exp_pat = getattr(elem, "GetExpandCollapsePattern", lambda: None)()
                if exp_pat:
                    if action_clean == "expand":
                        exp_pat.Expand()
                    else:
                        exp_pat.Collapse()
                    return {"success": True, "method": "ExpandCollapsePattern", "element": elem_name, "action": action_clean}
                elem.Click()
                return {"success": True, "method": "UIA_Click", "element": elem_name}

            else:
                return {"success": False, "error": f"Unsupported UI action '{action}'."}

        except Exception as e:
            return {"success": False, "failed_step": "execution", "error": f"Error executing '{action}' on '{elem_name}': {e}"}

    # --------------------------------------------------------------------------
    # Specialized Browser Tab Operations
    # --------------------------------------------------------------------------

    def list_browser_tabs(self, browser_name: str = "Brave") -> list[dict[str, Any]]:
        """List all open tabs in a Chromium browser (Brave, Chrome, Edge) without taking screenshots."""
        if not self.is_windows:
            return []

        # Find browser window (with multi-browser fallback)
        win = self.find_window(browser_name)
        active_bname = browser_name
        if not win and browser_name in ("Brave", "Chrome", "Edge"):
            for fallback_b in ("Brave", "Chrome", "Edge", "Google Chrome", "Microsoft Edge"):
                win = self.find_window(fallback_b)
                if win:
                    active_bname = fallback_b
                    break

        if not win:
            return []

        hwnd = win["hwnd"]
        root = self._get_root_control(hwnd)
        if root is None:
            return []

        tabs: list[dict[str, Any]] = []

        def scan_tabs(elem: Any, depth: int) -> None:
            if depth > 8 or elem is None:
                return
            try:
                if elem.ControlTypeName == "TabItemControl":
                    t_name = (elem.Name or "").strip()
                    rect = elem.BoundingRectangle
                    is_selected = False
                    try:
                        sel_pat = elem.GetSelectionItemPattern()
                        if sel_pat:
                            is_selected = bool(sel_pat.IsSelected)
                    except Exception:
                        pass

                    tabs.append({
                        "browser": active_bname,
                        "hwnd": hwnd,
                        "tab_index": len(tabs),
                        "title": t_name,
                        "selected": is_selected,
                        "rect": {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom,
                            "width": rect.width(),
                            "height": rect.height(),
                        },
                    })
                    return

                for child in elem.GetChildren():
                    scan_tabs(child, depth + 1)
            except Exception:
                pass

        scan_tabs(root, 0)
        return tabs


    def switch_browser_tab(self, tab_query: str, browser_name: str = "Brave") -> dict[str, Any]:
        """Switch to a specific browser tab by title using SelectionItemPattern."""
        if not self.is_windows:
            return {"success": False, "error": "Windows UI Automation required."}

        win = self.find_window(browser_name)
        if not win:
            return {"success": False, "reason": f"Browser '{browser_name}' window not found."}

        self.focus_window(win["hwnd"])
        root = self._get_root_control(win["hwnd"])
        if not root:
            return {"success": False, "reason": "Could not access browser UIA tree."}

        # Search for matching TabItemControl
        q = tab_query.strip().lower()
        matched_tab = None

        def find_tab(elem: Any, depth: int) -> None:
            nonlocal matched_tab
            if depth > 8 or matched_tab is not None or elem is None:
                return
            try:
                if elem.ControlTypeName == "TabItemControl":
                    t_name = (elem.Name or "").lower()
                    if q in t_name or (len(q) >= 4 and t_name.startswith(q[:4])):
                        matched_tab = elem
                        return
                for child in elem.GetChildren():
                    find_tab(child, depth + 1)
            except Exception:
                pass

        find_tab(root, 0)

        if not matched_tab:
            return {"success": False, "reason": f"Tab '{tab_query}' not found in {browser_name}."}

        try:
            sel_pat = matched_tab.GetSelectionItemPattern()
            if sel_pat:
                sel_pat.Select()
            else:
                matched_tab.Click()
            return {"success": True, "switched_to": matched_tab.Name, "browser": browser_name}
        except Exception as e:
            return {"success": False, "error": f"Failed to switch tab: {e}"}

    def close_browser_tab_uia(self, tab_name: str, browser_name: str = "Brave") -> dict[str, Any] | None:
        """Close a specific browser tab via UIA InvokePattern on its child close button."""
        if not self.is_windows:
            return None

        win = self.find_window(browser_name)
        if not win:
            return None

        hwnd = win["hwnd"]
        self.focus_window(hwnd)
        root = self._get_root_control(hwnd)
        if not root:
            return None

        tabs: list[Any] = []

        def scan(elem: Any, depth: int) -> None:
            if depth > 8 or elem is None:
                return
            try:
                if elem.ControlTypeName == "TabItemControl":
                    tabs.append(elem)
                    return
                for child in elem.GetChildren():
                    scan(child, depth + 1)
            except Exception:
                pass

        scan(root, 0)
        if not tabs:
            return None

        available_titles = [getattr(t, "Name", "") for t in tabs]
        q = tab_name.strip().lower()

        # Semantic matching
        matched_elem = None
        for t in tabs:
            t_name = getattr(t, "Name", "") or ""
            if t_name.strip().lower() == q:
                matched_elem = t
                break
        if not matched_elem:
            for t in tabs:
                t_name = getattr(t, "Name", "") or ""
                if q in t_name.lower():
                    matched_elem = t
                    break
        if not matched_elem:
            tokens = [tok for tok in q.split() if len(tok) >= 2]
            if tokens:
                for t in tabs:
                    t_name = getattr(t, "Name", "") or ""
                    if all(tok in t_name.lower() for tok in tokens):
                        matched_elem = t
                        break
        if not matched_elem and len(q) >= 4:
            for t in tabs:
                t_name = getattr(t, "Name", "") or ""
                if t_name.lower().startswith(q[:4]):
                    matched_elem = t
                    break

        if not matched_elem:
            logger.debug("Tab '%s' not matched in UIA tabs %s", tab_name, available_titles)
            return None

        matched_title = getattr(matched_elem, "Name", tab_name)

        # Invoke child Close button
        closed = False
        try:
            for child in matched_elem.GetChildren():
                if child.Name == "Close":
                    inv = child.GetInvokePattern()
                    if inv:
                        inv.Invoke()
                        closed = True
                    else:
                        child.Click()
                        closed = True
                    break
        except Exception as e:
            logger.debug("Error invoking child close button: %s", e)

        if not closed:
            try:
                inv = matched_elem.GetInvokePattern()
                if inv:
                    inv.Invoke()
                    closed = True
            except Exception:
                pass

        time.sleep(0.3)

        # Post-action verification
        tabs_after: list[Any] = []
        scan(root, 0)
        remaining_titles = [getattr(t, "Name", "") for t in tabs_after]

        verified_gone = not any(
            matched_title.lower() == r.lower() or (q in r.lower() and len(q) > 3)
            for r in remaining_titles
        )

        if verified_gone:
            return {
                "success": True,
                "method": "ui_automation",
                "tab_name": tab_name,
                "browser_name": browser_name,
                "closed_tab": matched_title,
                "remaining_tabs": remaining_titles,
                "message": f"Successfully closed the {tab_name} tab in {browser_name} via Windows UI Automation.",
            }
        else:
            return {
                "success": False,
                "failed_step": "verification",
                "method": "ui_automation",
                "reason": f"Tab '{matched_title}' was invoked but remains open on tab bar.",
                "remaining_tabs": remaining_titles,
            }


# Singleton engine instance
UIA_ENGINE = UIAutomationEngine()
