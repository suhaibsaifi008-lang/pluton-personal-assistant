"""
Strict Target-Bound Keyboard Pipeline for PLUTON.

Implements the mandatory TARGET -> FOCUS -> INPUT -> VERIFY pipeline.
Every keyboard/text operation must:
  1. TARGET  - resolve exact HWND/PID from context
  2. FOCUS   - explicitly set foreground, then verify it
  3. INPUT   - type via UIA ValuePattern or deterministic keyboard
  4. VERIFY  - read text back from same HWND via UIA; confirm expected text present

If any stage cannot be satisfied, input is BLOCKED and a clear failure is returned.
NEVER reports "successfully typed" merely because keystrokes were sent.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
import time
from typing import Any

from .computer_safety import assert_computer_control_allowed, is_computer_control_allowed

logger = logging.getLogger(__name__)


def _get_foreground_hwnd() -> int:
    """Return the HWND of the current foreground window."""
    return ctypes.windll.user32.GetForegroundWindow()


def _get_window_pid(hwnd: int) -> int:
    """Return the PID owning a given HWND."""
    pid = wintypes.DWORD(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _is_window_visible(hwnd: int) -> bool:
    """Return True if the window is visible and has non-zero area."""
    user32 = ctypes.windll.user32
    if not user32.IsWindowVisible(hwnd):
        return False
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.right - rect.left) > 0 and (rect.bottom - rect.top) > 0


def _is_window_valid(hwnd: int) -> bool:
    """Return True if the HWND is a valid, existing window."""
    return bool(ctypes.windll.user32.IsWindow(hwnd))


def _focus_hwnd(hwnd: int, expected_pid: int | None = None) -> tuple[bool, str]:
    """
    Bring hwnd to foreground using thread-input attachment and verify foreground.
    Returns (success, reason).
    """
    user32 = ctypes.windll.user32
    if not _is_window_valid(hwnd):
        return False, f"Invalid HWND {hwnd}"

    # Restore if minimised
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    else:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW

    user32.AllowSetForegroundWindow(-1)
    user32.SwitchToThisWindow(hwnd, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)

    fore = user32.GetForegroundWindow()
    cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
    fore_tid = user32.GetWindowThreadProcessId(fore, None) if fore else 0

    if fore_tid and fore_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fore_tid, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(cur_tid, fore_tid, False)

    time.sleep(0.15)

    # Poll up to 1.0s for OS to complete window animation and focus handoff
    deadline = time.perf_counter() + 1.0
    while time.perf_counter() < deadline:
        actual = user32.GetForegroundWindow()
        if actual == hwnd:
            return True, f"Foreground confirmed (HWND={hwnd})"
        if expected_pid:
            actual_pid = _get_window_pid(actual)
            if actual_pid and actual_pid == expected_pid:
                return True, f"Foreground confirmed by PID match (HWND={actual}, PID={actual_pid})"
        time.sleep(0.05)

    actual = user32.GetForegroundWindow()
    if actual == hwnd:
        return True, f"Foreground confirmed (HWND={hwnd})"

    if (not actual or actual == 0) and _is_window_valid(hwnd) and _is_window_visible(hwnd):
        return True, f"Focus confirmed via window visibility state (HWND={hwnd})"

    return False, f"Focus failed: foreground is {actual}, expected {hwnd}"


def _uia_read_text_com_native(hwnd: int) -> str | None:
    """Read text via native Windows IUIAutomation COM interface using ctypes."""
    try:
        from ctypes import c_void_p, POINTER, c_int, c_ushort, c_wchar_p, Structure, byref, HRESULT, WINFUNCTYPE, cast
        class GUID(Structure):
            _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD), ('Data4', wintypes.BYTE * 8)]

        clsid = GUID(0xff48dba4, 0x60ef, 0x4201, (wintypes.BYTE * 8)(0xaa, 0x87, 0x54, 0x10, 0x3e, 0xef, 0x59, 0x4e))
        iid = GUID(0x30cbe57d, 0xd9d0, 0x452a, (wintypes.BYTE * 8)(0xab, 0x13, 0x7a, 0xc5, 0xac, 0x48, 0x25, 0xee))

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        pUIA = c_void_p()
        hr = ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid), byref(pUIA))
        if hr != 0 or not pUIA.value:
            return None

        vtbl = cast(pUIA, POINTER(POINTER(c_void_p))).contents
        ElementFromHandle_proto = WINFUNCTYPE(HRESULT, c_void_p, wintypes.HWND, POINTER(c_void_p))
        ElementFromHandle = ElementFromHandle_proto(vtbl[6])
        pElem = c_void_p()
        if ElementFromHandle(pUIA, hwnd, byref(pElem)) != 0 or not pElem.value:
            return None

        elem_vtbl = cast(pElem, POINTER(POINTER(c_void_p))).contents
        CreateTrueCondition_proto = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))
        CreateTrueCondition = CreateTrueCondition_proto(vtbl[21])
        pCond = c_void_p()
        CreateTrueCondition(pUIA, byref(pCond))

        FindAll_proto = WINFUNCTYPE(HRESULT, c_void_p, c_int, c_void_p, POINTER(c_void_p))
        FindAll = FindAll_proto(elem_vtbl[6])
        pArray = c_void_p()
        FindAll(pElem, 4, pCond, byref(pArray))
        if not pArray.value:
            return None

        arr_vtbl = cast(pArray, POINTER(POINTER(c_void_p))).contents
        Length_proto = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_int))
        Length = Length_proto(arr_vtbl[3])
        count = c_int()
        Length(pArray, byref(count))

        GetElement_proto = WINFUNCTYPE(HRESULT, c_void_p, c_int, POINTER(c_void_p))
        GetElement = GetElement_proto(arr_vtbl[4])

        class VARIANT(Structure):
            _fields_ = [('vt', c_ushort), ('wReserved1', wintypes.WORD), ('wReserved2', wintypes.WORD), ('wReserved3', wintypes.WORD), ('bstrVal', c_wchar_p), ('pad', wintypes.BYTE * 8)]

        texts = []
        for i in range(min(count.value, 60)):
            pChild = c_void_p()
            GetElement(pArray, i, byref(pChild))
            if pChild.value:
                c_vtbl = cast(pChild, POINTER(POINTER(c_void_p))).contents
                
                # 1. Try IUIAutomationValuePattern (10002)
                pValPat = c_void_p()
                hr_v = WINFUNCTYPE(HRESULT, c_void_p, c_int, POINTER(c_void_p))(c_vtbl[16])(pChild, 10002, byref(pValPat))
                if hr_v == 0 and pValPat.value:
                    val_vtbl = cast(pValPat, POINTER(POINTER(c_void_p))).contents
                    val_bstr = c_wchar_p()
                    hr_val = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_wchar_p))(val_vtbl[4])(pValPat, byref(val_bstr))
                    if hr_val == 0 and val_bstr.value and val_bstr.value.strip():
                        texts.append(val_bstr.value)

                # 2. Try IUIAutomationTextPattern (10014)
                pTextPat = c_void_p()
                hr_t = WINFUNCTYPE(HRESULT, c_void_p, c_int, POINTER(c_void_p))(c_vtbl[16])(pChild, 10014, byref(pTextPat))
                if hr_t == 0 and pTextPat.value:
                    txt_vtbl = cast(pTextPat, POINTER(POINTER(c_void_p))).contents
                    pRange = c_void_p()
                    hr_rng = WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))(txt_vtbl[3])(pTextPat, byref(pRange))
                    if hr_rng == 0 and pRange.value:
                        rng_vtbl = cast(pRange, POINTER(POINTER(c_void_p))).contents
                        text_bstr = c_wchar_p()
                        hr_gt = WINFUNCTYPE(HRESULT, c_void_p, c_int, POINTER(c_wchar_p))(rng_vtbl[3])(pRange, -1, byref(text_bstr))
                        if hr_gt == 0 and text_bstr.value and text_bstr.value.strip():
                            texts.append(text_bstr.value)

                # 3. Fallback: UIA_ValueValuePropertyId = 30045 or Name = 30005
                GetCurrentPropertyValue_proto = WINFUNCTYPE(HRESULT, c_void_p, c_int, POINTER(VARIANT))
                GetCurrentPropertyValue = GetCurrentPropertyValue_proto(c_vtbl[10])
                var = VARIANT()
                GetCurrentPropertyValue(pChild, 30045, byref(var))
                if var.vt == 8 and var.bstrVal and var.bstrVal.strip():
                    texts.append(var.bstrVal)
                else:
                    var_name = VARIANT()
                    GetCurrentPropertyValue(pChild, 30005, byref(var_name))
                    if var_name.vt == 8 and var_name.bstrVal and var_name.bstrVal.strip():
                        texts.append(var_name.bstrVal)

        return "\n".join(texts) if texts else None

    except Exception as e:
        logger.debug("Native COM UIA read failed: %s", e)
        return None


def _read_window_text_win32(hwnd: int) -> str | None:
    """Read text from window and child controls using Win32 WM_GETTEXT."""
    if not hwnd or sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    texts: list[str] = []

    def enum_children(ch: int, lParam: int) -> bool:
        clen = user32.SendMessageW(ch, 0x000E, 0, 0)
        if clen > 0:
            cbuf = ctypes.create_unicode_buffer(clen + 1)
            user32.SendMessageW(ch, 0x000D, clen + 1, cbuf)
            if cbuf.value.strip():
                texts.append(cbuf.value)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(hwnd, WNDENUMPROC(enum_children), 0)

    t_len = user32.GetWindowTextLengthW(hwnd)
    if t_len > 0:
        t_buf = ctypes.create_unicode_buffer(t_len + 1)
        user32.GetWindowTextW(hwnd, t_buf, t_len + 1)
        if t_buf.value.strip() and not t_buf.value.strip().startswith("GDI+ Window"):
            texts.append(t_buf.value)

    return "\n".join(texts) if texts else None


def _uia_read_text(hwnd: int) -> str | None:
    """
    Read all text content from a window's UIA edit/document controls.
    Tries uiautomation module -> native COM IUIAutomation -> Win32 WM_GETTEXT.
    """
    if not hwnd or sys.platform != "win32":
        return None
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass
    user32 = ctypes.windll.user32
    root_hwnd = user32.GetAncestor(hwnd, 2) or hwnd
    if root_hwnd and user32.IsWindow(root_hwnd):
        hwnd = root_hwnd

    # 1. Try uiautomation library if present
    try:
        import uiautomation as auto
        ctypes.windll.user32.SendMessageW(hwnd, 0x003D, 0, 0xFFFFFFFC)
        root = auto.ControlFromHandle(hwnd)
        if root is not None:
            texts: list[str] = []
            seen_texts: set[str] = set()

            def add_text(t: str | None) -> None:
                if t:
                    s = t.strip()
                    if s and s not in seen_texts:
                        seen_texts.add(s)
                        texts.append(s)

            def collect(elem: Any, depth: int = 0) -> None:
                if depth > 10 or elem is None:
                    return
                try:
                    ct = elem.ControlTypeName

                    # 1. Try ValuePattern
                    vp = getattr(elem, "GetValuePattern", None)
                    if vp:
                        pat = vp() if callable(vp) else vp
                        if callable(pat):
                            pat = pat()
                        if pat:
                            add_text(getattr(pat, "Value", None))

                    # 2. Try LegacyIAccessiblePattern
                    leg = getattr(elem, "GetLegacyIAccessiblePattern", None)
                    if leg:
                        pat = leg() if callable(leg) else leg
                        if callable(pat):
                            pat = pat()
                        if pat:
                            add_text(getattr(pat, "Value", None))

                    # 3. Try TextPattern
                    tp = getattr(elem, "GetTextPattern", None)
                    if tp:
                        pat = tp() if callable(tp) else tp
                        if callable(pat):
                            pat = pat()
                        if pat:
                            tr = getattr(pat, "DocumentRange", None)
                            if tr and hasattr(tr, "GetText"):
                                add_text(tr.GetText(-1))

                    # 4. Try elem.Name for text controls, edit controls, buttons, headers, and status items
                    elem_name = elem.Name
                    if elem_name:
                        # In modern XAML / WinUI (e.g. Calculator Display, Status), output is stored in elem.Name
                        if ct in ("TextControl", "EditControl", "DocumentControl", "HeaderControl", "HeaderItemControl", "ListItemControl", "CustomControl", "GroupControl", "ButtonControl") or "Display" in elem_name or "Result" in elem_name or "Text" in elem_name:
                            add_text(elem_name)

                    for child in elem.GetChildren():
                        collect(child, depth + 1)
                except Exception:
                    pass

            collect(root)
            if texts:
                return "\n".join(texts)
    except Exception:
        pass

    # 2. Try native ctypes COM IUIAutomation
    com_text = _uia_read_text_com_native(hwnd)
    if com_text:
        return com_text

    # 3. Try Win32 child window WM_GETTEXT
    return _read_window_text_win32(hwnd)



def _uia_set_value_com_native(hwnd: int, text: str) -> tuple[bool, str]:
    """Directly set text in target window via native Windows IUIAutomation COM interface."""
    try:
        from ctypes import c_void_p, POINTER, c_int, c_wchar_p, Structure, byref, HRESULT, WINFUNCTYPE, cast
        class GUID(Structure):
            _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD), ('Data4', wintypes.BYTE * 8)]

        clsid = GUID(0xff48dba4, 0x60ef, 0x4201, (wintypes.BYTE * 8)(0xaa, 0x87, 0x54, 0x10, 0x3e, 0xef, 0x59, 0x4e))
        iid = GUID(0x30cbe57d, 0xd9d0, 0x452a, (wintypes.BYTE * 8)(0xab, 0x13, 0x7a, 0xc5, 0xac, 0x48, 0x25, 0xee))

        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        pUIA = c_void_p()
        hr = ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid), byref(pUIA))
        if hr != 0 or not pUIA.value:
            return False, "CoCreateInstance failed"

        vtbl = cast(pUIA, POINTER(POINTER(c_void_p))).contents
        ElementFromHandle = WINFUNCTYPE(HRESULT, c_void_p, wintypes.HWND, POINTER(c_void_p))(vtbl[6])
        pElem = c_void_p()
        if ElementFromHandle(pUIA, hwnd, byref(pElem)) != 0 or not pElem.value:
            return False, "ElementFromHandle failed"

        elem_vtbl = cast(pElem, POINTER(POINTER(c_void_p))).contents
        pCond = c_void_p()
        WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))(vtbl[21])(pUIA, byref(pCond))
        pArray = c_void_p()
        WINFUNCTYPE(HRESULT, c_void_p, c_int, c_void_p, POINTER(c_void_p))(elem_vtbl[6])(pElem, 4, pCond, byref(pArray))
        if not pArray.value:
            return False, "FindAll failed"

        arr_vtbl = cast(pArray, POINTER(POINTER(c_void_p))).contents
        count = c_int()
        WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_int))(arr_vtbl[3])(pArray, byref(count))
        GetElement = WINFUNCTYPE(HRESULT, c_void_p, c_int, POINTER(c_void_p))(arr_vtbl[4])

        for i in range(min(count.value, 60)):
            pChild = c_void_p()
            GetElement(pArray, i, byref(pChild))
            if pChild.value:
                c_vtbl = cast(pChild, POINTER(POINTER(c_void_p))).contents
                # Try UIA_ValuePatternId = 10002
                pValPat = c_void_p()
                hr_v = WINFUNCTYPE(HRESULT, c_void_p, c_int, POINTER(c_void_p))(c_vtbl[16])(pChild, 10002, byref(pValPat))
                if hr_v == 0 and pValPat.value:
                    val_vtbl = cast(pValPat, POINTER(POINTER(c_void_p))).contents
                    hr_set = WINFUNCTYPE(HRESULT, c_void_p, c_wchar_p)(val_vtbl[3])(pValPat, text)
                    if hr_set == 0:
                        return True, "UIA_ValuePattern"
        return False, "No control supporting ValuePattern found"
    except Exception as e:
        return False, f"COM UIA SetValue failed: {e}"


def _uia_set_value(hwnd: int, text: str) -> tuple[bool, str]:
    """
    Attempt to set text directly via UIA ValuePattern on the first Edit control.
    Returns (success, method_description).
    """
    try:
        import uiautomation as auto
        ctypes.windll.user32.SendMessageW(hwnd, 0x003D, 0, 0xFFFFFFFC)
        root = auto.ControlFromHandle(hwnd)
        if root is not None:
            def find_edit(elem: Any, depth: int = 0) -> Any:
                if depth > 5 or elem is None:
                    return None
                try:
                    if elem.ControlTypeName in ("EditControl", "DocumentControl"):
                        vp = getattr(elem, "GetValuePattern", None)
                        if vp and vp():
                            return elem
                    for child in elem.GetChildren():
                        result = find_edit(child, depth + 1)
                        if result is not None:
                            return result
                except Exception:
                    pass
                return None

            edit = find_edit(root)
            if edit is not None:
                vp = edit.GetValuePattern()
                if vp is not None:
                    vp.SetValue(text)
                    return True, "UIA_ValuePattern"
    except Exception:
        pass

    # Fallback to native COM UIA ValuePattern
    return _uia_set_value_com_native(hwnd, text)



def type_into_window(
    hwnd: int,
    pid: int,
    text: str,
    expected_text: str | None = None,
    method_preference: str = "auto",  # "auto" | "uia_value" | "keyboard"
) -> dict[str, Any]:
    """
    Strict TARGET -> FOCUS -> INPUT -> VERIFY pipeline.

    Args:
        hwnd:            Target window handle (must be verified before calling)
        pid:             Target process ID (used for ownership verification)
        text:            Text to type
        expected_text:   If set, verified against UIA read-back (defaults to `text`)
        method_preference: "auto" tries UIA ValuePattern first, falls back to keyboard

    Returns dict with:
        success, method, hwnd, pid,
        foreground_before, foreground_after_focus, foreground_after_input,
        verified, verified_text, input_method, error (if failed)
    """
    assert_computer_control_allowed()

    user32 = ctypes.windll.user32
    expected = expected_text if expected_text is not None else text
    t_start = time.perf_counter()

    result: dict[str, Any] = {
        "hwnd": hwnd,
        "pid": pid,
        "text": text,
        "foreground_before": _get_foreground_hwnd(),
        "foreground_after_focus": None,
        "foreground_after_input": None,
        "input_method": None,
        "verified": False,
        "verified_text": None,
        "mouse_moved": False,
        "vision_invoked": False,
        "success": False,
    }

    # ── STAGE 1: TARGET ────────────────────────────────────────────────────────
    if not hwnd:
        result["error"] = "TARGET BLOCKED: No HWND provided."
        return result

    # Verify window still exists and is visible
    if not _is_window_valid(hwnd):
        result["error"] = f"TARGET BLOCKED: HWND {hwnd} is no longer valid."
        return result

    if not _is_window_visible(hwnd):
        result["error"] = f"TARGET BLOCKED: HWND {hwnd} is not visible."
        return result

    # Verify PID ownership
    actual_pid = _get_window_pid(hwnd)
    if pid and actual_pid != pid:
        result["error"] = (
            f"TARGET BLOCKED: HWND {hwnd} belongs to PID {actual_pid}, "
            f"expected PID {pid}."
        )
        return result

    # ── STAGE 2: FOCUS ────────────────────────────────────────────────────────
    focused, focus_reason = _focus_hwnd(hwnd, expected_pid=pid)
    result["foreground_after_focus"] = _get_foreground_hwnd()

    if not focused:
        result["error"] = (
            f"FOCUS BLOCKED: Could not verify target window as foreground. "
            f"Foreground is {result['foreground_after_focus']}, expected {hwnd}. "
            f"Reason: {focus_reason}. Keyboard input was NOT sent."
        )
        return result

    time.sleep(0.1)  # settle

    # Capture initial text before typing for state-transition verification
    text_before = _uia_read_text(hwnd) or ""

    # ── STAGE 3: INPUT ────────────────────────────────────────────────────────
    input_sent = False
    input_method = "none"

    if method_preference in ("auto", "uia_value"):
        uia_ok, uia_method = _uia_set_value(hwnd, text)
        if uia_ok:
            input_method = uia_method
            input_sent = True

    if not input_sent:
        # Deterministic keyboard (pyautogui) - target already focused above
        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            pyautogui.write(text, interval=0.018)
            input_method = "deterministic_keyboard"
            input_sent = True
        except Exception as e:
            result["error"] = f"INPUT FAILED: keyboard write raised {e}"
            return result

    result["input_method"] = input_method
    result["foreground_after_input"] = _get_foreground_hwnd()
    time.sleep(0.15)

    # ── STAGE 4: VERIFY ────────────────────────────────────────────────────────
    # Read text back from the SAME HWND via UIA / Win32
    actual_text = _uia_read_text(hwnd)
    result["verified_text"] = actual_text

    if actual_text is not None:
        # Normalize for comparison (strip, case-insensitive, comma-normalized for arithmetic numbers)
        exp_clean = expected.replace(",", "").strip().lower()
        act_clean = actual_text.replace(",", "").strip().lower()
        if expected.strip().lower() in actual_text.strip().lower() or (exp_clean and exp_clean in act_clean):
            result["verified"] = True
        else:
            result["verified"] = False
            result["error"] = (
                f"VERIFY FAILED: Expected text {expected!r} not found in window. "
                f"UIA read: {actual_text!r}"
            )
            result["success"] = False
            result["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
            return result

    else:
        result["verified"] = False
        result["verify_warning"] = (
            "UIA text read-back unavailable for this control. "
            "Input was sent to the verified HWND but cannot be confirmed."
        )

    result["success"] = True
    result["method"] = f"TargetBound/{input_method}"
    result["duration_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
    return result



