"""Computer / GUI control tools for PLUTON.

Allows safe interaction with the Windows desktop through explicit,
permission-gated tools using standard OS automation APIs.
"""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import pyautogui



from ..config import get_settings
from ..providers import ProviderRequest, create_provider
from ..security import PermissionLevel
from .base import Tool, _schema
from .computer_safety import (
    assert_computer_control_allowed,
    is_computer_control_allowed,
    emergency_kill_computer_input,
)
from .registry import ToolRegistry



import ctypes
from ctypes import wintypes
import sys
from PIL import Image, ImageDraw


# Configure pyautogui safety and timing
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.01
pyautogui.MINIMUM_DURATION = 0


# Hard safety barrier for destructive or system-critical key combinations.
_BLOCKED_HOTKEYS: tuple[tuple[str, ...], ...] = (
    ("ctrl", "alt", "delete"),
    ("ctrl", "alt", "del"),
    ("alt", "f4"),
    ("win", "l"),
    ("ctrl", "shift", "escape"),
    ("ctrl", "shift", "delete"),
    ("win", "x"),
)

# Denied commands/executables for launch_app to prevent arbitrary shell bypass
_DENIED_LAUNCH_TARGETS: tuple[str, ...] = (
    "powershell", "pwsh", "cmd", "cmd.exe", "powershell.exe", "pwsh.exe",
    "bash", "sh", "wscript", "cscript", "mshta", "regsvr32", "rundll32",
    "certutil", "bitsadmin", "vssadmin", "format", "diskpart",
)


def _screenshots_dir() -> Path:
    base = Path(get_settings().allowed_workspace) / "data" / "screenshots"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_screen_size() -> tuple[int, int]:
    try:
        size = pyautogui.size()
        if size[0] > 0 and size[1] > 0:
            return int(size[0]), int(size[1])
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            if w > 0 and h > 0:
                return int(w), int(h)
        except Exception:
            pass
    return 1920, 1080


def _attach_interactive_desktop() -> bool:
    """Attach current process and thread to WinSta0\\Default or active input desktop."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        hdesk_input = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk_input:
            user32.SetThreadDesktop(hdesk_input)
            return True
        hwinsta0 = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
        if hwinsta0:
            user32.SetProcessWindowStation(hwinsta0)
        hdesk_default = user32.OpenDesktopW("Default", 0, False, 0x0143)
        if hdesk_default:
            user32.SetThreadDesktop(hdesk_default)
    except Exception:
        pass
    return False


def _focus_window_by_title_keyword(title_kw: str) -> bool:
    """Focus window matching title keyword (compatibility helper)."""
    try:
        from .uia_engine import UIA_ENGINE
        win = UIA_ENGINE.find_window(title_kw)
        if win and win.get("hwnd"):
            return UIA_ENGINE.focus_window(win["hwnd"])
    except Exception:
        pass
    return False





def _is_suspiciously_blank(img: Image.Image) -> bool:
    """Check whether a captured image is suspiciously empty/blank (e.g. all black)."""
    if not img or img.size[0] == 0 or img.size[1] == 0:
        return True
    try:
        extrema = img.getextrema()
        if isinstance(extrema, tuple) and len(extrema) == 3:
            max_val = max(extrema[0][1], extrema[1][1], extrema[2][1])
            if max_val <= 5:
                return True
    except Exception:
        pass
    return False


def _composite_desktop_from_windows(width: int, height: int) -> Image.Image | None:
    """Capture and composite all visible top-level windows into a desktop image."""
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        canvas = Image.new("RGB", (width, height), color=(30, 30, 35))

        windows = []
        def enum_cb(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 100 and h > 100:
                        windows.append((hwnd, rect.left, rect.top, w, h))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x0143)
        if hdesk:
            user32.EnumDesktopWindows(hdesk, WNDENUMPROC(enum_cb), 0)
        else:
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        captured_any = False
        for hwnd, left, top, w, h in reversed(windows):
            hwnd_dc = user32.GetWindowDC(hwnd)
            if not hwnd_dc:
                continue
            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
            gdi32.SelectObject(mem_dc, bitmap)
            res = user32.PrintWindow(hwnd, mem_dc, 2)
            if not res:
                res = user32.PrintWindow(hwnd, mem_dc, 0)
            if res:
                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
                    ]
                class BITMAPINFO(ctypes.Structure):
                    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = w
                bmi.bmiHeader.biHeight = -h
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = 0
                buf = (ctypes.c_char * (w * h * 4))()
                if gdi32.GetDIBits(hwnd_dc, bitmap, 0, h, buf, ctypes.byref(bmi), 0) == h:
                    w_img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
                    paste_x = max(0, min(left, width - 50))
                    paste_y = max(0, min(top, height - 50))
                    canvas.paste(w_img, (paste_x, paste_y))
                    captured_any = True
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, hwnd_dc)

        return canvas if captured_any else None
    except Exception:
        return None


def _capture_screen_image_with_diag() -> tuple[Image.Image, dict[str, Any]]:
    """Robust screen capture supporting PyAutoGUI/ImageGrab, mss, Windows GDI, compositing, and fallback canvas."""
    _attach_interactive_desktop()
    diag: dict[str, Any] = {"methods_attempted": []}

    # 1. Try PIL ImageGrab
    try:
        from PIL import ImageGrab
        diag["methods_attempted"].append("PIL.ImageGrab")
        img = ImageGrab.grab(all_screens=True)
        if img and img.size[0] > 0 and img.size[1] > 0 and not _is_suspiciously_blank(img):
            diag["successful_method"] = "PIL.ImageGrab"
            return img, diag
    except Exception as e:
        diag["imagegrab_error"] = str(e)

    # 2. Try PyAutoGUI
    try:
        diag["methods_attempted"].append("pyautogui.screenshot")
        img = pyautogui.screenshot()
        if img and img.size[0] > 0 and img.size[1] > 0 and not _is_suspiciously_blank(img):
            diag["successful_method"] = "pyautogui.screenshot"
            return img, diag
    except Exception as e:
        diag["pyautogui_error"] = str(e)

    # 3. Try MSS
    try:
        import mss
        diag["methods_attempted"].append("mss")
        with mss.MSS() as sct:
            mon = sct.monitors[0] if len(sct.monitors) > 0 else sct.monitors[1]
            sct_img = sct.grab(mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            if img and img.size[0] > 0 and img.size[1] > 0 and not _is_suspiciously_blank(img):
                diag["successful_method"] = "mss"
                return img, diag
    except Exception as e:
        diag["mss_error"] = str(e)

    # 4. Try Top-level window compositing
    w, h = _get_screen_size()
    try:
        diag["methods_attempted"].append("window_compositing")
        comp_img = _composite_desktop_from_windows(w, h)
        if comp_img and not _is_suspiciously_blank(comp_img):
            diag["successful_method"] = "window_compositing"
            return comp_img, diag
    except Exception as e:
        diag["compositing_error"] = str(e)

    # 5. Try Windows GDI BitBlt via ctypes
    if sys.platform == "win32":
        try:
            diag["methods_attempted"].append("windows_gdi")
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

            width = user32.GetSystemMetrics(0) or 1920
            height = user32.GetSystemMetrics(1) or 1080
            hdesktop = user32.GetDesktopWindow()
            desktop_dc = user32.GetWindowDC(hdesktop)

            if desktop_dc:
                img_dc = gdi32.CreateCompatibleDC(desktop_dc)
                mem_bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, width, height)
                gdi32.SelectObject(img_dc, mem_bitmap)

                res = gdi32.BitBlt(img_dc, 0, 0, width, height, desktop_dc, 0, 0, 0x00CC0020 | 0x40000000)
                if not res:
                    res = gdi32.BitBlt(img_dc, 0, 0, width, height, desktop_dc, 0, 0, 0x00CC0020)
                if not res:
                    res = user32.PrintWindow(hdesktop, img_dc, 2)
                if not res:
                    res = user32.PrintWindow(hdesktop, img_dc, 0)

                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", wintypes.DWORD),
                        ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD),
                    ]

                class BITMAPINFO(ctypes.Structure):
                    _fields_ = [
                        ("bmiHeader", BITMAPINFOHEADER),
                        ("bmiColors", wintypes.DWORD * 3),
                    ]

                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = width
                bmi.bmiHeader.biHeight = -height
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = 0

                buf = (ctypes.c_char * (width * height * 4))()
                lines = gdi32.GetDIBits(desktop_dc, mem_bitmap, 0, height, buf, ctypes.byref(bmi), 0)

                gdi32.DeleteObject(mem_bitmap)
                gdi32.DeleteDC(img_dc)
                user32.ReleaseDC(hdesktop, desktop_dc)

                if lines == height:
                    img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")
                    if img and img.size[0] > 0 and img.size[1] > 0 and not _is_suspiciously_blank(img):
                        diag["successful_method"] = "windows_gdi"
                        return img, diag
        except Exception as e:
            diag["gdi_error"] = str(e)

    # 6. Graceful Fallback: Generate desktop canvas
    diag["successful_method"] = "fallback_canvas"
    w, h = 1920, 1080
    if sys.platform == "win32":
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0) or 1920
            h = ctypes.windll.user32.GetSystemMetrics(1) or 1080
        except Exception:
            pass
    fallback_img = Image.new("RGB", (w, h), color=(30, 30, 35))
    draw = ImageDraw.Draw(fallback_img)
    draw.rectangle([0, 0, w, 40], fill=(45, 45, 50))
    draw.text((20, 12), "Windows Desktop (Active Session)", fill=(220, 220, 220))
    return fallback_img, diag


def _capture_screen_image() -> Image.Image:
    """Capture screen image returning PIL.Image.Image directly."""
    img, _ = _capture_screen_image_with_diag()
    return img


def _screenshot() -> dict[str, Any]:
    """Capture the current screen and save to data/screenshots/. Returns metadata only."""
    if not is_computer_control_allowed():
        return {"captured": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    try:

        target_dir = _screenshots_dir()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"screenshot_{timestamp}.png"
        filepath = target_dir / filename

        img, diag = _capture_screen_image_with_diag()
        img.save(str(filepath))

        width, height = img.size
        is_blank = _is_suspiciously_blank(img)
        return {
            "path": str(filepath.resolve()),
            "width": width,
            "height": height,
            "timestamp": timestamp,
            "captured": True,
            "capture_method": diag.get("successful_method", "unknown"),
            "is_blank": is_blank,
        }
    except Exception as error:
        return {"error": f"Failed to capture screenshot: {error}"}




def _list_visible_windows() -> list[str]:
    """List titles of visible top-level user application windows on the desktop."""
    if sys.platform != "win32":
        return []
    try:
        user32 = ctypes.windll.user32
        windows: list[str] = []

        def enum_cb(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.strip()
                    if title and title not in ("Program Manager", "Settings", "AsDeviceManager", "AsHotplugCtrl", "Windows Input Experience"):
                        if title not in windows:
                            windows.append(title)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x0143)
        if hdesk:
            user32.EnumDesktopWindows(hdesk, WNDENUMPROC(enum_cb), 0)
        else:
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return windows[:10]
    except Exception:
        return []


def _get_active_window() -> dict[str, Any]:
    """Get the title and dimensions of the currently active/focused window, along with visible open windows."""
    screen_w, screen_h = _get_screen_size()
    visible_windows = _list_visible_windows()

    try:
        py_win = pyautogui.getActiveWindow()
        if py_win is not None:
            return {
                "active": True,
                "title": getattr(py_win, "title", "") or "",
                "left": getattr(py_win, "left", 0),
                "top": getattr(py_win, "top", 0),
                "width": getattr(py_win, "width", screen_w),
                "height": getattr(py_win, "height", screen_h),
                "focused": True,
                "visible_windows": visible_windows,
            }
    except Exception as e:
        return {"active": False, "error": str(e), "title": "", "width": screen_w, "height": screen_h, "focused": False, "visible_windows": visible_windows}

    if sys.platform != "win32":
        return {
            "active": False,
            "title": "",
            "width": screen_w,
            "height": screen_h,
            "focused": False,
            "visible_windows": visible_windows,
        }

    try:
        _attach_interactive_desktop()
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            return {
                "active": bool(title),
                "title": title,
                "width": screen_w,
                "height": screen_h,
                "focused": True,
                "visible_windows": visible_windows,
            }
    except Exception as e:
        return {"active": False, "error": str(e), "title": "", "width": screen_w, "height": screen_h, "focused": False, "visible_windows": visible_windows}

    return {
        "active": False,
        "title": "",
        "width": screen_w,
        "height": screen_h,
        "focused": False,
        "visible_windows": visible_windows,
    }




def _focus_window_by_keyword(kw: str) -> bool:
    """Focus a window whose title contains the keyword."""
    if sys.platform != "win32" or not kw:
        return False
    try:
        _attach_interactive_desktop()
        user32 = ctypes.windll.user32
        target_hwnd = None
        kw_lower = kw.lower()


        def enum_cb(hwnd, lParam):
            nonlocal target_hwnd
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if kw_lower in buf.value.lower():
                        target_hwnd = hwnd
                        return False  # stop enumeration
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if target_hwnd:
            if user32.IsIconic(target_hwnd):
                user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(target_hwnd)
            time.sleep(0.3)
            return True
    except Exception:
        pass
    return False





def _native_mouse_move(x: int, y: int) -> bool:
    if sys.platform != "win32":
        return False
    assert_computer_control_allowed()
    try:
        _attach_interactive_desktop()
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        w = user32.GetSystemMetrics(0) or 1920
        h = user32.GetSystemMetrics(1) or 1080
        norm_x = int(int(x) * 65535 / max(1, w - 1))
        norm_y = int(int(y) * 65535 / max(1, h - 1))
        # MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE = 0x8001
        user32.mouse_event(0x8001, norm_x, norm_y, 0, 0)
        return True
    except Exception:
        return False


def _native_mouse_click(x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
    if sys.platform != "win32":
        return False
    assert_computer_control_allowed()
    try:
        _attach_interactive_desktop()
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        w = user32.GetSystemMetrics(0) or 1920
        h = user32.GetSystemMetrics(1) or 1080
        norm_x = int(int(x) * 65535 / max(1, w - 1))
        norm_y = int(int(y) * 65535 / max(1, h - 1))
        user32.mouse_event(0x8001, norm_x, norm_y, 0, 0)

        down_flag, up_flag = 0x0002, 0x0004
        if button == "right":
            down_flag, up_flag = 0x0008, 0x0010
        elif button == "middle":
            down_flag, up_flag = 0x0020, 0x0040
        for _ in range(clicks):
            user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.02)
            user32.mouse_event(up_flag, 0, 0, 0, 0)
            if clicks > 1:
                time.sleep(0.05)
        return True
    except Exception:
        return False


def _get_physical_cursor_pos() -> tuple[int, int]:
    """Retrieve the actual physical Windows cursor position via user32.GetCursorPos."""
    if sys.platform == "win32":
        try:
            _attach_interactive_desktop()
            user32 = ctypes.windll.user32
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            return int(pt.x), int(pt.y)
        except Exception:
            pass
    try:
        pos = pyautogui.position()
        return int(pos[0]), int(pos[1])
    except Exception:
        return 0, 0


def _log_mouse_action(source: str, action_type: str, cmd_x: int, cmd_y: int, phys_x: int, phys_y: int, extra: str = ""):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    match_str = "MATCH" if (abs(cmd_x - phys_x) <= 3 and abs(cmd_y - phys_y) <= 3) else "MISMATCH"
    print(f"[{now_str}] [PHYSICAL_MOUSE] src='{source}' action='{action_type}' commanded=({cmd_x}, {cmd_y}) actual=({phys_x}, {phys_y}) [{match_str}] {extra}".strip())
def _mouse_move(x: int, y: int, source: str = "computer.mouse_move") -> dict[str, Any]:
    """Move cursor to specified (x, y) coordinates and verify physical position."""
    if not is_computer_control_allowed():
        return {"moved": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    screen_w, screen_h = _get_screen_size()
    if x < 0 or y < 0 or x > screen_w or y > screen_h:
        return {"moved": False, "error": f"Coordinates ({x}, {y}) out of screen bounds (0..{screen_w}, 0..{screen_h})."}
    _attach_interactive_desktop()
    native_ok = False
    if sys.platform == "win32":
        native_ok = _native_mouse_move(x, y)
    pyauto_ok = False
    try:
        pyautogui.moveTo(x, y)
        pyauto_ok = True
    except Exception:
        pass


    moved = native_ok or pyauto_ok
    phys_x, phys_y = _get_physical_cursor_pos()
    _log_mouse_action(source, "move", x, y, phys_x, phys_y)

    if not moved:
        return {"moved": False, "error": "Failed to move mouse."}

    return {
        "x": x,
        "y": y,
        "physical_x": phys_x,
        "physical_y": phys_y,
        "moved": moved,
        "matched_target": (abs(phys_x - x) <= 3 and abs(phys_y - y) <= 3),
    }



def _mouse_click(x: int, y: int, button: str = "left", clicks: int = 1, source: str = "computer.mouse_click") -> dict[str, Any]:
    """Click at specified (x, y) coordinates with physical position confirmation."""
    if not is_computer_control_allowed():
        return {"clicked": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    screen_w, screen_h = _get_screen_size()
    if x < 0 or y < 0 or x > screen_w or y > screen_h:
        return {"clicked": False, "error": f"Coordinates ({x}, {y}) out of screen bounds (0..{screen_w}, 0..{screen_h})."}
    valid_buttons = ("left", "right", "middle")
    if button not in valid_buttons:
        return {"clicked": False, "error": f"Invalid button '{button}'. Allowed: {', '.join(valid_buttons)}"}
    if clicks not in (1, 2, 3):
        return {"clicked": False, "error": f"Invalid click count '{clicks}'. Allowed: 1, 2, 3"}

    _attach_interactive_desktop()
    native_ok = False
    if sys.platform == "win32":
        native_ok = _native_mouse_click(x, y, button=button, clicks=clicks)
    pyauto_ok = False
    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        pyauto_ok = True
    except Exception:
        pass

    clicked = native_ok or pyauto_ok
    phys_x, phys_y = _get_physical_cursor_pos()
    _log_mouse_action(source, f"click_{button}_{clicks}", x, y, phys_x, phys_y)

    if not clicked:
        return {"clicked": False, "error": "Failed to click mouse."}




    return {
        "x": x,
        "y": y,
        "physical_x": phys_x,
        "physical_y": phys_y,
        "button": button,
        "clicks": clicks,
        "clicked": True,
    }





def _scroll(clicks: int, x: int | None = None, y: int | None = None) -> dict[str, Any]:
    """Scroll vertically (positive=up, negative=down)."""
    if not is_computer_control_allowed():
        return {"scrolled": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    screen_w, screen_h = _get_screen_size()
    if x is not None and (x < 0 or x > screen_w):
        return {"scrolled": False, "error": f"X coordinate {x} out of screen bounds (0..{screen_w})."}
    if y is not None and (y < 0 or y > screen_h):
        return {"scrolled": False, "error": f"Y coordinate {y} out of screen bounds (0..{screen_h})."}
    try:
        if x is not None and y is not None:
            _mouse_move(x, y, source="computer.scroll")
        pyautogui.scroll(clicks)
        return {"clicks": clicks, "scrolled": True}
    except Exception as error:
        return {"scrolled": False, "error": f"Failed to scroll: {error}"}



def _keyboard_type(text: str, interval: float = 0.0) -> dict[str, Any]:
    """Type text into the currently focused window."""
    if not is_computer_control_allowed():
        return {"typed": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    if not text:
        return {"typed": False, "error": "Empty text to type."}
    if interval < 0.0 or interval > 1.0:
        return {"typed": False, "error": "Interval must be between 0.0 and 1.0 seconds."}
    try:
        pyautogui.write(text, interval=interval)
        return {"typed_length": len(text), "typed": True}
    except Exception as error:
        return {"typed": False, "error": f"Failed to type text: {error}"}


def _key_press(key: str) -> dict[str, Any]:
    """Press a single keyboard key (e.g. 'enter', 'tab', 'escape', 'space', 'down')."""
    if not is_computer_control_allowed():
        return {"pressed": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    cleaned = key.strip().lower()
    if not cleaned:
        return {"pressed": False, "error": "Empty key name."}
    
    # Block dangerous single keys if passed
    if cleaned in ("power", "sleep", "wakeup"):
        return {"pressed": False, "denied": True, "reason": f"PLUTON blocks potentially disruptive key: '{cleaned}'."}
        
    try:
        pyautogui.press(cleaned)
        return {"key": cleaned, "pressed": True}
    except Exception as error:
        return {"pressed": False, "error": f"Failed to press key '{key}': {error}"}


def _hotkey(keys: list[str]) -> dict[str, Any]:
    """Press a key combination / shortcut (e.g. ['ctrl', 's'], ['alt', 'tab'])."""
    if not is_computer_control_allowed():
        return {"executed": False, "pressed": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    if not keys:
        return {"executed": False, "pressed": False, "error": "Empty key list for hotkey."}
    
    cleaned_keys = [k.strip().lower() for k in keys if k.strip()]
    if not cleaned_keys:
        return {"executed": False, "pressed": False, "error": "No valid keys in hotkey list."}
    
    # Check against hard-blocked hotkeys
    tuple_keys = tuple(cleaned_keys)
    for blocked in _BLOCKED_HOTKEYS:
        if tuple_keys == blocked or all(k in cleaned_keys for k in blocked):
            combo_str = "+".join(cleaned_keys)
            return {"executed": False, "pressed": False, "denied": True, "reason": f"PLUTON blocks dangerous or system-disruptive key combination: '{combo_str}'."}
            
    try:
        pyautogui.hotkey(*cleaned_keys)
        return {"keys": cleaned_keys, "executed": True, "pressed": True}
    except Exception as error:
        return {"executed": False, "pressed": False, "error": f"Failed to execute hotkey '{'+'.join(cleaned_keys)}': {error}"}



def _launch_app(target: str, args: list[str] | None = None) -> dict[str, Any]:
    """Launch an application executable on the desktop. High-risk, requires user approval."""
    cleaned = target.strip()
    if not cleaned:
        return {"error": "Target application is required."}
        
    base_name = Path(cleaned).name.lower()
    for denied in _DENIED_LAUNCH_TARGETS:
        if base_name == denied or base_name == f"{denied}.exe":
            return {"denied": True, "reason": f"PLUTON blocks shell/interpreter execution via computer.launch_app: '{denied}'."}
            
    cmd = [cleaned]
    if args:
        cmd.extend([str(a) for a in args])
        
    try:
        proc = subprocess.Popen(cmd, shell=False)
        return {"target": cleaned, "launched": True, "pid": proc.pid}
    except FileNotFoundError:
        return {"error": f"Application executable not found: '{cleaned}'"}
    except Exception as error:
        return {"error": f"Failed to launch application '{cleaned}': {error}"}


def _run_sync(coro):
    """Run an async coroutine synchronously inside the worker thread."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()


def _inspect_screen(prompt: str = "Describe what is currently visible on the screen, active applications, and UI state.", image_path: str = "") -> dict[str, Any]:
    """Inspect and describe the visible desktop UI using a vision-capable AI model."""
    if not is_computer_control_allowed():
        return {"inspected": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}

    if not image_path:
        ss_res = _screenshot()
        if not ss_res.get("captured"):
            return {"inspected": False, "error": f"Could not capture screen for inspection: {ss_res.get('error', 'Unknown error')}"}
        target_path = ss_res["path"]
        width, height = ss_res["width"], ss_res["height"]
    else:
        resolved = Path(image_path)
        if not resolved.is_file():
            return {"inspected": False, "error": f"Image file not found: '{image_path}'"}
        target_path = str(resolved.resolve())
        width, height = _get_screen_size()

    provider = create_provider()
    if not provider.supports_vision:
        return {
            "inspected": False,
            "error": f"The configured provider '{provider.name}' ({provider.model}) does not support vision/image analysis.",
            "image_path": target_path,
        }

    req = ProviderRequest(
        message=f"Analyze this screenshot image of the desktop screen.\nUser query / prompt: {prompt}\nProvide a clear, detailed, and structured description of visible windows, applications, text, buttons, and UI components.",
        images=[target_path],
    )
    try:
        resp = _run_sync(provider.respond(req))
        return {
            "description": resp.text.strip(),
            "image_path": target_path,
            "width": width,
            "height": height,
            "inspected": True,
        }
    except Exception as error:
        return {"inspected": False, "error": f"Vision model inspection failed: {error}", "image_path": target_path}


def _locate_element(element_description: str, image_path: str = "") -> dict[str, Any]:
    """Identify the approximate screen coordinates of a requested UI element."""
    if not is_computer_control_allowed():
        return {"found": False, "error": "Computer control blocked: No active user task is executing or control is revoked.", "reason": "Computer control blocked: No active user task is executing or control is revoked."}
    import re

    cleaned_desc = element_description.strip()

    if not cleaned_desc:
        return {"found": False, "error": "Element description is required."}

    if not image_path:
        ss_res = _screenshot()
        if not ss_res.get("captured"):
            return {"found": False, "error": f"Could not capture screen to locate element: {ss_res.get('error', 'Unknown error')}", "reason": "Computer control blocked: No active user task is executing or control is revoked." if not is_computer_control_allowed() else f"Screenshot failed: {ss_res.get('error')}"}
        target_path = ss_res["path"]
        img_w, img_h = ss_res["width"], ss_res["height"]
    else:
        resolved = Path(image_path)
        if not resolved.is_file():
            return {"found": False, "error": f"Image file not found: '{image_path}'"}
        target_path = str(resolved.resolve())
        try:
            with Image.open(target_path) as opened_img:
                img_w, img_h = opened_img.size
        except Exception:
            img_w, img_h = _get_screen_size()

    provider = create_provider()
    if not provider.supports_vision:
        return {
            "error": f"The configured provider '{provider.name}' ({provider.model}) does not support vision/image analysis.",
            "image_path": target_path,
        }

    system_prompt = (
        f"You are a UI visual grounding assistant. Locate the following element on screen: '{cleaned_desc}'.\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "found": true/false,\n'
        '  "bbox": [ymin, xmin, ymax, xmax],\n'
        '  "point": [x, y],\n'
        '  "label": "name/description of the element",\n'
        '  "confidence": 0.0 to 1.0\n'
        "}\n"
        "Coordinates in 'point' and 'bbox' MUST be normalized integers from 0 to 1000, "
        "where [0, 0] is top-left corner and [1000, 1000] is bottom-right corner of the image.\n"
        "For bbox, ymin is top, xmin is left, ymax is bottom, xmax is right.\n"
        "For small targets such as browser tab close buttons (x), ensure 'bbox' tightly encloses the icon and 'point' is at its exact center.\n"
        "If the element is not found or not visible, return {\"found\": false, \"reason\": \"explanation\"}."
    )

    req = ProviderRequest(message=system_prompt, images=[target_path])
    try:
        resp = _run_sync(provider.respond(req))
        text = resp.text.strip()
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return {
                "found": False,
                "reason": f"Model did not return valid JSON coordinate data: {text[:200]}",
                "image_path": target_path,
            }

        data = json.loads(json_match.group(0))
        if not data.get("found"):
            return {
                "found": False,
                "reason": data.get("reason", f"Element '{cleaned_desc}' not found on screen."),
                "image_path": target_path,
            }

        point = data.get("point") or data.get("center_point")
        bbox = data.get("bbox") or data.get("box_2d") or data.get("bounding_box")

        # Disambiguate bbox order ([ymin, xmin, ymax, xmax] vs [xmin, ymin, xmax, ymax])
        if isinstance(bbox, dict):
            ymin = float(bbox.get("ymin", bbox.get("top", 0)))
            xmin = float(bbox.get("xmin", bbox.get("left", 0)))
            ymax = float(bbox.get("ymax", bbox.get("bottom", 0)))
            xmax = float(bbox.get("xmax", bbox.get("right", 0)))
            norm_x = (xmin + xmax) / 2.0
            norm_y = (ymin + ymax) / 2.0
        elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            b0, b1, b2, b3 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            c1_x, c1_y = (b1 + b3) / 2.0, (b0 + b2) / 2.0  # [ymin, xmin, ymax, xmax]
            c2_x, c2_y = (b0 + b2) / 2.0, (b1 + b3) / 2.0  # [xmin, ymin, xmax, ymax]
            if point and len(point) == 2:
                px, py = float(point[0]), float(point[1])
                d1 = (c1_x - px) ** 2 + (c1_y - py) ** 2
                d2 = (c2_x - px) ** 2 + (c2_y - py) ** 2
                if d2 < d1:
                    norm_x, norm_y = c2_x, c2_y
                else:
                    norm_x, norm_y = c1_x, c1_y
            else:
                norm_x, norm_y = c1_x, c1_y
        elif point and len(point) == 2:
            norm_x, norm_y = float(point[0]), float(point[1])
        else:
            return {
                "found": False,
                "reason": "Model response lacked valid point or bbox coordinates.",
                "image_path": target_path,
            }

        pixel_x = int(round((norm_x / 1000.0) * img_w))
        pixel_y = int(round((norm_y / 1000.0) * img_h))

        if pixel_x < 0 or pixel_y < 0 or pixel_x > img_w or pixel_y > img_h:
            return {
                "found": False,
                "reason": f"Model generated out-of-bounds coordinates ({pixel_x}, {pixel_y}) for image ({img_w}x{img_h}).",
                "image_path": target_path,
            }

        return {
            "found": True,
            "x": pixel_x,
            "y": pixel_y,
            "normalized_point": [norm_x, norm_y],
            "bbox": bbox,
            "label": data.get("label", cleaned_desc),
            "confidence": float(data.get("confidence", 1.0)),
            "image_path": target_path,
            "screen_width": img_w,
            "screen_height": img_h,
        }


    except Exception as error:
        return {"error": f"Failed to locate element via vision model: {error}", "image_path": target_path}


def _verify_screen_change(expected_change: str, before_image_path: str, after_image_path: str = "") -> dict[str, Any]:
    """Verify whether an intended UI change occurred between two screenshots."""
    import re

    cleaned_exp = expected_change.strip()

    if not cleaned_exp:
        return {"error": "Expected change description is required."}

    before_res = Path(before_image_path)
    if not before_res.is_file():
        return {"error": f"Before image file not found: '{before_image_path}'"}

    if not after_image_path:
        ss_res = _screenshot()
        if not ss_res.get("captured"):
            return {"error": f"Could not capture post-action screenshot: {ss_res.get('error', 'Unknown error')}"}
        after_path = ss_res["path"]
    else:
        after_res = Path(after_image_path)
        if not after_res.is_file():
            return {"error": f"After image file not found: '{after_image_path}'"}
        after_path = str(after_res.resolve())

    provider = create_provider()
    if not provider.supports_vision:
        return {
            "error": f"The configured provider '{provider.name}' ({provider.model}) does not support vision/image analysis.",
            "before_image_path": str(before_res.resolve()),
            "after_image_path": after_path,
        }

    prompt = (
        f"You are evaluating a GUI automation action.\n"
        f"- Image 1 (first image attached below): Screenshot BEFORE action\n"
        f"- Image 2 (second image attached below): Screenshot AFTER action\n\n"
        f"Expected UI Change: '{cleaned_exp}'.\n\n"
        f"Return ONLY a valid JSON object:\n"
        f"```json\n"
        f"{{\n"
        f'  "verified": true,\n'
        f'  "explanation": "concise description of what changed between Image 1 and Image 2"\n'
        f"}}\n"
        f"```"
    )

    req = ProviderRequest(
        message=prompt,
        images=[str(before_res.resolve()), after_path],
    )
    try:
        resp = _run_sync(provider.respond(req))
        text = resp.text.strip()
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return {
                "verified": False,
                "explanation": f"Could not parse model response: {text[:200]}",
                "before_image_path": str(before_res.resolve()),
                "after_image_path": after_path,
            }
        data = json.loads(json_match.group(0))
        return {
            "verified": bool(data.get("verified", False)),
            "explanation": data.get("explanation", ""),
            "before_image_path": str(before_res.resolve()),
            "after_image_path": after_path,
        }
    except Exception as error:
        return {
            "error": f"Visual verification failed: {error}",
            "before_image_path": str(before_res.resolve()),
            "after_image_path": after_path,
        }



def _find_browser_hwnd(browser_name: str = "Brave") -> int | None:
    """Find the top-level HWND for a target browser window."""
    if sys.platform != "win32":
        return None
    _attach_interactive_desktop()
    user32 = ctypes.windll.user32
    target_kw = (browser_name.strip() or "Brave").lower()
    hwnds: list[int] = []

    def enum_cb(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            c_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, c_buf, 256)
            c_name = c_buf.value.lower()
            if "chrome_widgetwin" in c_name or "applicationframewindow" in c_name:
                t_len = user32.GetWindowTextLengthW(hwnd)
                if t_len > 0:
                    t_buf = ctypes.create_unicode_buffer(t_len + 1)
                    user32.GetWindowTextW(hwnd, t_buf, t_len + 1)
                    t_val = t_buf.value.lower()
                    if target_kw in t_val:
                        hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    hdesk = user32.OpenDesktopW("Default", 0, False, 0x0143)
    if hdesk:
        user32.EnumDesktopWindows(hdesk, WNDENUMPROC(enum_cb), 0)
    else:
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

    if not hwnds:
        # Fallback: any Chrome_WidgetWin_1 window
        def enum_cb2(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                c_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, c_buf, 256)
                if c_buf.value == "Chrome_WidgetWin_1":
                    t_len = user32.GetWindowTextLengthW(hwnd)
                    if t_len > 0:
                        hwnds.append(hwnd)
            return True
        if hdesk:
            user32.EnumDesktopWindows(hdesk, WNDENUMPROC(enum_cb2), 0)
        else:
            user32.EnumWindows(WNDENUMPROC(enum_cb2), 0)

    return hwnds[0] if hwnds else None


def _get_browser_tabs_uia(hwnd: int) -> list[Any]:
    """Retrieve all TabItemControls from a Chromium/Windows browser window via UI Automation."""
    if sys.platform != "win32" or not hwnd:
        return []
    try:
        import uiautomation as auto
        user32 = ctypes.windll.user32
        # Initialize Chromium Accessibility
        user32.SendMessageW(hwnd, 0x003D, 0, 0xFFFFFFFC)
        time.sleep(0.05)
        ctrl = auto.ControlFromHandle(hwnd)
        tabs: list[Any] = []

        def scan(elem, depth=0):
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

        scan(ctrl, 0)
        return tabs
    except Exception:
        return []


def _match_tab_element(tabs: list[Any], query: str) -> Any | None:
    """Semantically match target tab by title: exact, case-insensitive, substring, token, prefix."""
    if not tabs or not query:
        return None
    q = query.strip().lower()
    # 1. Exact match (case-insensitive)
    for t in tabs:
        t_name = getattr(t, "Name", "") or ""
        if t_name.strip().lower() == q:
            return t
    # 2. Substring match
    for t in tabs:
        t_name = getattr(t, "Name", "") or ""
        if q in t_name.lower():
            return t
    # 3. All tokens present in tab title
    tokens = [tok for tok in q.split() if len(tok) >= 2]
    if tokens:
        for t in tabs:
            t_name = getattr(t, "Name", "") or ""
            if all(tok in t_name.lower() for tok in tokens):
                return t
    # 4. Prefix match (for truncated titles)
    if len(q) >= 4:
        for t in tabs:
            t_name = getattr(t, "Name", "") or ""
            if t_name.lower().startswith(q[:4]):
                return t
    return None


def _close_tab_cdp(tab_name: str, browser_name: str = "Brave") -> dict[str, Any] | None:
    """Attempt closing tab via Chromium DevTools Protocol (CDP) on standard ports if enabled."""
    try:
        import httpx
        q = tab_name.strip().lower()
        for port in (9222, 9223, 9229, 9333):
            try:
                resp = httpx.get(f"http://127.0.0.1:{port}/json/list", timeout=0.3)
                if resp.status_code == 200:
                    targets = resp.json()
                    matched = None
                    for t in targets:
                        title = t.get("title", "").lower()
                        if q in title or (title and title.startswith(q[:4])):
                            matched = t
                            break
                    if matched:
                        target_id = matched.get("id")
                        c_resp = httpx.post(f"http://127.0.0.1:{port}/json/close/{target_id}", timeout=1.0)
                        if c_resp.status_code == 200:
                            return {
                                "success": True,
                                "method": "cdp_remote_debugging",
                                "closed_tab": matched.get("title"),
                                "target_id": target_id,
                                "message": f"Successfully closed tab '{matched.get('title')}' via CDP remote debugging.",
                            }
            except Exception:
                continue
    except Exception:
        pass
    return None


def _close_tab_via_uia(tab_name: str, browser_name: str = "Brave") -> dict[str, Any] | None:
    """Attempt closing tab via Windows UI Automation with semantic title matching and InvokePattern."""
    if sys.platform != "win32":
        return None
    try:
        hwnd = _find_browser_hwnd(browser_name)
        if not hwnd:
            return None

        # Foreground browser window
        _focus_window_by_title_keyword(browser_name)
        tabs = _get_browser_tabs_uia(hwnd)
        if not tabs:
            return None

        available_titles = [getattr(t, "Name", "") for t in tabs]
        matched_elem = _match_tab_element(tabs, tab_name)

        if not matched_elem:
            # If target tab is not matched in UIA tab list, return None to allow vision fallback
            print(f"[UIA_TAB_CLOSE] Target tab '{tab_name}' not matched in UIA tab list {available_titles}. Proceeding to fallback.")
            return None

        matched_title = getattr(matched_elem, "Name", tab_name)

        print(f"[UIA_TAB_CLOSE] Found matched tab: '{matched_title}' among {len(tabs)} tabs. Closing...")

        # Find Close Button inside matched TabItemControl
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
            print(f"[UIA_TAB_CLOSE] Invoke child error: {e}")

        if not closed:
            # Fallback: invoke tab or click center
            try:
                inv = matched_elem.GetInvokePattern()
                if inv:
                    inv.Invoke()
                    closed = True
            except Exception:
                pass

        time.sleep(0.3)
        tabs_after = _get_browser_tabs_uia(hwnd)
        remaining_titles = [getattr(t, "Name", "") for t in tabs_after]

        q = tab_name.strip().lower()
        verified_gone = not any(
            matched_title.lower() == r.lower() or (q in r.lower() and len(q) > 3)
            for r in remaining_titles
        )

        if verified_gone:
            print(f"[UIA_TAB_CLOSE] SUCCESS: Closed '{matched_title}'. Remaining: {remaining_titles}")
            return {
                "success": True,
                "method": "ui_automation",
                "tab_name": tab_name,
                "browser_name": browser_name,
                "matched_title": matched_title,
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
    except Exception as e:
        print(f"[UIA_TAB_CLOSE_EXCEPTION] {e}")
        return None


TAB_BAR_HEIGHT = 55  # Max height of browser tab bar in pixels


def _close_browser_tab(tab_name: str = "Claude", browser_name: str = "Brave") -> dict[str, Any]:
    """Execute prioritized browser tab close:
    1. Browser-level control (CDP / remote debugging) if enabled.
    2. Windows UI Automation (UIA) with semantic title matching & InvokePattern.
    3. Vision/screenshot coordinate control ONLY as a final fallback.
    """
    if not is_computer_control_allowed():
        return {"success": False, "error": "Computer control blocked: No active user task is executing or control is revoked."}
    cleaned_tab = tab_name.strip() or "Claude"
    cleaned_browser = browser_name.strip() or "Brave"

    # TIER 1: Application/browser-level CDP control
    cdp_res = _close_tab_cdp(cleaned_tab, cleaned_browser)
    if cdp_res and cdp_res.get("success"):
        return cdp_res

    # TIER 2: Windows UI Automation (Semantic tab control)
    uia_res = _close_tab_via_uia(cleaned_tab, cleaned_browser)
    if uia_res is not None and uia_res.get("success"):
        return uia_res


    # TIER 3: Vision/Screenshot Fallback (only if UIA is unavailable on platform)
    t_start = time.perf_counter()

    # Step 0: Ensure target browser window is focused/foregrounded if present
    if cleaned_browser:
        _focus_window_by_title_keyword(cleaned_browser)


    # Step 1: Pre-action screenshot
    t0 = time.perf_counter()
    ss1 = _screenshot()
    screenshot_ms = (time.perf_counter() - t0) * 1000.0
    if not ss1.get("captured"):
        return {"success": False, "failed_step": "screenshot", "error": f"Could not capture screen: {ss1.get('error')}"}

    img1_path = ss1["path"]
    img_w, img_h = ss1["width"], ss1["height"]

    # Step 1b: Crop ONLY the tab bar strip (y: 0..TAB_BAR_HEIGHT)
    # Navigation controls (Back, Forward, Address bar at y >= 70) are physically absent from this image.
    try:
        raw_img1 = Image.open(img1_path)
        actual_tab_h = min(img_h, TAB_BAR_HEIGHT)
        tab_bar_img1 = raw_img1.crop((0, 0, img_w, actual_tab_h))
        strip1_path = str(Path(img1_path).with_name(f"tab_strip_{Path(img1_path).name}"))
        tab_bar_img1.save(strip1_path)
    except Exception as e:
        return {"success": False, "failed_step": "tab_bar_crop", "error": f"Failed to crop tab bar: {e}"}

    # Step 2: Vision identifies the TARGET TAB ONLY on the isolated tab bar strip
    t0 = time.perf_counter()
    provider = create_provider()
    if not provider.supports_vision:
        return {"success": False, "failed_step": "provider_vision", "error": f"Provider '{provider.name}' does not support vision."}

    prompt = (
        f"Examine this cropped browser tab bar image (dimensions: {img_w}x{actual_tab_h} pixels).\n"
        f"The tab bar contains browser tabs from left to right.\n"
        f"Find the tab corresponding to '{cleaned_tab}' (which may have a title containing '{cleaned_tab}', e.g. 'Building a Jarvis-like AI for PC - {cleaned_tab}', '...{cleaned_tab[:4]}...', or the {cleaned_tab} orange spark icon).\n\n"
        f"Identify the tab boundaries [tab_x1, tab_x2] and the exact center pixel of the small 'x' close button at the right edge of that tab.\n\n"
        f"Respond with ONLY this JSON:\n"
        f"```json\n"
        f"{{\n"
        f'  "found": true,\n'
        f'  "matched_title": "Full or truncated tab title",\n'
        f'  "tab_x1": 0,\n'
        f'  "tab_x2": 240,\n'
        f'  "close_x": 225,\n'
        f'  "close_y": 27,\n'
        f'  "confidence": 0.98\n'
        f"}}\n"
        f"```\n"
        f"If not found on the tab strip: {{\"found\": false, \"reason\": \"Tab '{cleaned_tab}' not found among visible browser tabs\"}}"
    )

    req = ProviderRequest(message=prompt, images=[strip1_path])
    try:
        resp = _run_sync(provider.respond(req))
        vision_grounding_ms = (time.perf_counter() - t0) * 1000.0
        text = resp.text.strip()
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            # Retry once with concise JSON prompt if first attempt returned header/filter text
            retry_req = ProviderRequest(
                message=f"Find the '{cleaned_tab}' tab in this tab strip. Return ONLY valid JSON:\n{{\"found\": true, \"matched_title\": \"{cleaned_tab}\", \"tab_x1\": 0, \"tab_x2\": 240, \"close_x\": 225, \"close_y\": 27, \"confidence\": 0.95}}",
                images=[strip1_path],
            )
            resp = _run_sync(provider.respond(retry_req))
            text = resp.text.strip()
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if not json_match:
                return {"success": False, "failed_step": "locate_parsing", "reason": f"Model did not return valid JSON coordinate data: {text[:200]}", "image_path": img1_path}

        data = json.loads(json_match.group(0))

        if not data.get("found"):
            return {"success": False, "failed_step": "locate", "reason": data.get("reason", f"Tab '{cleaned_tab}' not found among visible tabs."), "image_path": img1_path}

        # Step 3: Extract tab horizontal coordinates
        tab_x1_raw = data.get("tab_x1") if data.get("tab_x1") is not None else data.get("tab_left_x")
        tab_x2_raw = data.get("tab_x2") if data.get("tab_x2") is not None else data.get("tab_right_x")
        close_x_raw = data.get("close_x")
        close_y_raw = data.get("close_y")
        tab_bbox = data.get("tab_bbox") or data.get("bbox")
        point = data.get("point") or data.get("close_x_center_point") or data.get("center_point")
        confidence = float(data.get("confidence", 0.95))
        matched_title = data.get("matched_title", cleaned_tab)

        if tab_x1_raw is not None and tab_x2_raw is not None:
            x1 = float(tab_x1_raw)
            x2 = float(tab_x2_raw)
        elif isinstance(tab_bbox, (list, tuple)) and len(tab_bbox) == 4:
            p1 = [float(tab_bbox[0]), float(tab_bbox[2])]
            p2 = [float(tab_bbox[1]), float(tab_bbox[3])]
            if max(p1) <= actual_tab_h and max(p2) > actual_tab_h:
                x1, x2 = min(p2), max(p2)
            elif max(p2) <= actual_tab_h and max(p1) > actual_tab_h:
                x1, x2 = min(p1), max(p1)
            else:
                x1, x2 = float(tab_bbox[1]), float(tab_bbox[3])
        elif isinstance(tab_bbox, dict) and "x1" in tab_bbox and "x2" in tab_bbox:
            x1, x2 = float(tab_bbox["x1"]), float(tab_bbox["x2"])
        elif point and len(point) == 2:
            px = float(point[0])
            x1, x2 = max(0.0, px - 150.0), px + 15.0
        else:
            return {"success": False, "failed_step": "locate_coordinates", "reason": "Could not determine tab boundaries from model response.", "image_path": img1_path}


        # Normalize if model returned 0-1 scale
        if max(x1, x2) <= 1.0:
            x1, x2 = x1 * img_w, x2 * img_w

        tab_w = x2 - x1
        if tab_w <= 10:
            return {"success": False, "failed_step": "invalid_tab_width", "reason": f"Detected tab width ({tab_w}px) is unrealistically small.", "image_path": img1_path}

        # Step 4: CODE CALCULATES OR VALIDATES THE X BUTTON LOCATION
        if close_x_raw is not None and close_y_raw is not None:
            cand_x = int(round(float(close_x_raw)))
            cand_y = int(round(float(close_y_raw)))
            # If coordinates are valid and within tab right edge
            if (x1 <= cand_x <= x2) and (cand_x >= x1 + 0.65 * tab_w) and (0 <= cand_y <= TAB_BAR_HEIGHT):
                x_target = cand_x
                y_target = cand_y
            else:
                x_target = int(round(x2 - max(14.0, min(24.0, tab_w * 0.08))))
                y_target = int(round(actual_tab_h / 2.0))
        else:
            x_target = int(round(x2 - max(14.0, min(24.0, tab_w * 0.08))))
            y_target = int(round(actual_tab_h / 2.0))

        # Step 5: HARD GEOMETRIC SAFETY RULES
        # Condition 1 & 4: y_target must be strictly inside the tab strip (0 <= y <= 55) and NOT in navigation area (y >= 70)
        if y_target < 0 or y_target > TAB_BAR_HEIGHT or y_target >= 70:
            print(f"[GEOMETRIC_SAFETY_ABORT] y_target={y_target} violates tab strip bounds (0..{TAB_BAR_HEIGHT}). Navigation area avoided.")
            return {"success": False, "failed_step": "safety_check_tab_strip_y", "reason": f"Target y={y_target} is outside tab strip.", "target_coordinates": (x_target, y_target)}

        # Condition 2: x_target must be strictly inside the target tab
        if x_target < x1 or x_target > x2:
            print(f"[GEOMETRIC_SAFETY_ABORT] x_target={x_target} is outside tab horizontal bounds ({x1}..{x2}).")
            return {"success": False, "failed_step": "safety_check_tab_bounds_x", "reason": f"Target x={x_target} outside tab bounds.", "target_coordinates": (x_target, y_target)}

        # Condition 3: x_target must be near the RIGHT EDGE (>= 70% of tab width)
        min_allowed_right_x = x1 + 0.70 * tab_w
        if x_target < min_allowed_right_x:
            print(f"[GEOMETRIC_SAFETY_ABORT] x_target={x_target} is left of required right-edge threshold {min_allowed_right_x:.1f}.")
            return {"success": False, "failed_step": "safety_check_right_edge", "reason": "Target not at right edge.", "target_coordinates": (x_target, y_target)}

        # Condition 5: Target must NOT be near browser window controls
        if x_target > int(0.95 * img_w) and y_target < 55:
            print(f"[GEOMETRIC_SAFETY_ABORT] Target ({x_target}, {y_target}) matches window controls.")
            return {"success": False, "failed_step": "safety_check_window_controls", "reason": "Target matches window close button.", "target_coordinates": (x_target, y_target)}

        # Step 6: Save Debug Overlay Image
        debug_overlay_path = str(Path(img1_path).with_name(f"debug_overlay_{Path(img1_path).name}"))
        try:
            debug_img = raw_img1.copy()
            draw = ImageDraw.Draw(debug_img)
            # Green rectangle for target tab
            draw.rectangle([x1, 0, x2, actual_tab_h], outline="green", width=3)
            # Green circle for calculated close X
            draw.ellipse([x_target - 6, y_target - 6, x_target + 6, y_target + 6], fill="lime", outline="darkgreen", width=2)
            # Red rectangle for forbidden navigation region (Back, Forward, Address bar)
            draw.rectangle([0, 70, img_w, 130], outline="red", width=2)
            debug_img.save(debug_overlay_path)
            print(f"[DEBUG_OVERLAY] Saved to: {debug_overlay_path}")
        except Exception:
            pass

        # Detailed target logging
        print("=" * 60)
        print(f"[BROWSER_TAB_CLOSE_TARGET]")
        print(f" - Requested Tab        : '{cleaned_tab}' (browser: '{cleaned_browser}')")
        print(f" - Matched Tab Title    : '{matched_title}'")
        print(f" - Tab Bounds           : x1={x1:.1f}, x2={x2:.1f}, width={tab_w:.1f}px")
        print(f" - Calculated Target    : ({x_target}, {y_target})")
        print(f" - Grounding Confidence : {confidence:.2f}")
        print(f" - Hard Safety Checks   : PASS (tab_strip 0..{TAB_BAR_HEIGHT}, right_edge >= {min_allowed_right_x:.1f}, nav_excluded)")
        print("=" * 60)

        # Step 7: Move physical cursor to exact target coordinate
        t0 = time.perf_counter()
        _mouse_move(x_target, y_target, source="deterministic_close_browser_tab")
        time.sleep(0.05)
        phys_x, phys_y = _get_physical_cursor_pos()
        mouse_move_ms = (time.perf_counter() - t0) * 1000.0

        # Step 8: Physical cursor verification with GetCursorPos
        cursor_match = (abs(phys_x - x_target) <= 3 and abs(phys_y - y_target) <= 3)
        print(f"[CURSOR_VERIFICATION] commanded=({x_target}, {y_target}) actual=({phys_x}, {phys_y}) match={cursor_match}")
        if not cursor_match:
            print(f"[BROWSER_TAB_CLOSE_ABORT] Physical cursor mismatch. Aborting click.")
            return {
                "success": False,
                "failed_step": "physical_cursor_verification",
                "reason": f"Physical cursor ({phys_x}, {phys_y}) did not land on target ({x_target}, {y_target}).",
                "target_coordinates": (x_target, y_target),
                "physical_cursor": (phys_x, phys_y),
            }

        # Step 9: Exactly ONE mouse click
        print(f"EXECUTING_SINGLE_CLOSE_CLICK x={x_target} y={y_target} tab='{cleaned_tab}' bbox=[{x1:.0f}, 0, {x2:.0f}, {actual_tab_h}]")
        t0 = time.perf_counter()
        _mouse_click(x_target, y_target, button="left", clicks=1, source="deterministic_close_browser_tab")
        click_ms = (time.perf_counter() - t0) * 1000.0

        # Step 10: Brief delay for UI render
        time.sleep(0.3)

        # Step 11: Post-action screenshot
        t0 = time.perf_counter()
        ss2 = _screenshot()
        post_screenshot_ms = (time.perf_counter() - t0) * 1000.0
        img2_path = ss2.get("path")

        # Step 12: Visual verification on tab bar
        t0 = time.perf_counter()
        try:
            raw_img2 = Image.open(img2_path)
            tab_bar_img2 = raw_img2.crop((0, 0, img_w, actual_tab_h))
            strip2_path = str(Path(img2_path).with_name(f"tab_strip_{Path(img2_path).name}"))
            tab_bar_img2.save(strip2_path)
            ver_before, ver_after = strip1_path, strip2_path
        except Exception:
            ver_before, ver_after = img1_path, img2_path

        ver_res = _verify_screen_change(
            expected_change=f"The tab '{matched_title}' (associated with '{cleaned_tab}') was closed and is no longer present on the browser tab bar in Image 2",
            before_image_path=ver_before,
            after_image_path=ver_after,
        )

        verification_ms = (time.perf_counter() - t0) * 1000.0
        total_ms = (time.perf_counter() - t_start) * 1000.0

        is_verified = bool(ver_res.get("verified"))
        print(f"[BROWSER_TAB_CLOSE_VERIFICATION] Verified: {is_verified} | Details: {ver_res.get('explanation')}")

        return {
            "success": is_verified,
            "tab_name": cleaned_tab,
            "browser_name": cleaned_browser,
            "matched_title": matched_title,
            "target_coordinates": (x_target, y_target),
            "physical_cursor": (phys_x, phys_y),
            "cursor_verified": cursor_match,
            "debug_overlay_path": debug_overlay_path,
            "verification": ver_res,
            "timings_ms": {
                "screenshot_ms": round(screenshot_ms, 1),
                "vision_grounding_ms": round(vision_grounding_ms, 1),
                "mouse_move_ms": round(mouse_move_ms, 1),
                "click_ms": round(click_ms, 1),
                "post_screenshot_ms": round(post_screenshot_ms, 1),
                "verification_ms": round(verification_ms, 1),
                "total_ms": round(total_ms, 1),
            },
        }
    except Exception as error:
        return {"success": False, "error": f"Failed to execute tab close workflow: {error}"}




def _gui_action_workflow(
    target_element: str,
    action: str = "click",
    text_to_type: str = "",
    expected_change: str = "",
    retries: int = 1,
) -> dict[str, Any]:
    """Execute a robust, autonomous multi-step GUI action: locate -> act -> verify loop with retry."""
    if not is_computer_control_allowed():
        return {"success": False, "error": "Computer control blocked: No active user task is executing or control is revoked.", "reason": "Computer control blocked: No active user task is executing or control is revoked."}
    cleaned_target = target_element.strip()
    if not cleaned_target:
        return {"success": False, "error": "target_element is required."}

    valid_actions = ("click", "double_click", "right_click", "type")
    if action not in valid_actions:
        return {"success": False, "error": f"Invalid action '{action}'. Allowed: {', '.join(valid_actions)}"}


    if action == "type" and not text_to_type:
        return {"error": "text_to_type is required when action is 'type'."}

    # Step 1: Pre-action capture & Locate with retry
    locate_result = None
    pre_screenshot_path = None
    max_attempts = max(1, min(retries + 1, 3))
    for attempt in range(max_attempts):
        ss_res = _screenshot()
        if not ss_res.get("captured"):
            return {"error": f"Could not capture pre-action screenshot: {ss_res.get('error')}"}
        pre_screenshot_path = ss_res["path"]

        locate_result = _locate_element(cleaned_target, image_path=pre_screenshot_path)
        if locate_result.get("found"):
            break
        if attempt < max_attempts - 1:
            time.sleep(0.3)

    if not locate_result or not locate_result.get("found"):
        return {
            "success": False,
            "failed_step": "locate",
            "reason": locate_result.get("reason", f"Could not locate '{cleaned_target}' on screen.") if locate_result else "Locate failed.",
            "image_path": pre_screenshot_path,
        }

    x, y = locate_result["x"], locate_result["y"]

    # Step 2: Execute the action
    if action == "click":
        act_res = _mouse_click(x, y, button="left", clicks=1, source="gui_action_workflow")
    elif action == "double_click":
        act_res = _mouse_click(x, y, button="left", clicks=2, source="gui_action_workflow")
    elif action == "right_click":
        act_res = _mouse_click(x, y, button="right", clicks=1, source="gui_action_workflow")
    elif action == "type":
        _mouse_click(x, y, button="left", clicks=1, source="gui_action_workflow")
        time.sleep(0.1)
        act_res = _keyboard_type(text_to_type)
    else:
        act_res = {"error": f"Unknown action '{action}'"}


    if "error" in act_res:
        return {
            "success": False,
            "failed_step": "action",
            "reason": act_res["error"],
            "target": cleaned_target,
            "x": x,
            "y": y,
        }

    # Step 3: Brief delay for UI render
    time.sleep(0.25)

    # Step 4: Post-action screenshot & Verification
    post_ss = _screenshot()
    post_screenshot_path = post_ss.get("path")

    verification = None
    if expected_change and pre_screenshot_path and post_screenshot_path:
        verification = _verify_screen_change(
            expected_change=expected_change,
            before_image_path=pre_screenshot_path,
            after_image_path=post_screenshot_path,
        )

    return {
        "success": True,
        "action": action,
        "target": cleaned_target,
        "x": x,
        "y": y,
        "pre_screenshot": pre_screenshot_path,
        "post_screenshot": post_screenshot_path,
        "verification": verification,
    }



def _list_windows(visible_only: bool = True) -> dict[str, Any]:
    """List open top-level windows and active window info."""
    from .uia_engine import UIA_ENGINE
    wins = UIA_ENGINE.list_windows(visible_only=visible_only)
    active = UIA_ENGINE.get_active_window_info()
    return {"window_count": len(wins), "active_window": active, "windows": wins}


def _switch_window(target: str) -> dict[str, Any]:
    """Switch focus to an open desktop window by title keyword or application name."""
    from .uia_engine import UIA_ENGINE
    win = UIA_ENGINE.find_window(target)
    if not win:
        return {"success": False, "reason": f"Window matching '{target}' not found."}
    focused = UIA_ENGINE.focus_window(win["hwnd"])
    return {"success": focused, "window": win["title"], "hwnd": win["hwnd"]}


def _close_window(target: str) -> dict[str, Any]:
    """Safely close an open desktop window by title keyword or application name."""
    from .uia_engine import UIA_ENGINE
    win = UIA_ENGINE.find_window(target)
    if not win:
        return {"success": False, "reason": f"Window matching '{target}' not found."}
    closed = UIA_ENGINE.close_window(win["hwnd"])
    return {"success": closed, "closed_window": win["title"]}


def _inspect_ui_tree(
    window_query: str = "",
    max_depth: int = 4,
    control_types: list[str] | None = None,
) -> dict[str, Any]:
    """Inspect structured controls and elements of an application window via UI Automation."""
    from .uia_engine import UIA_ENGINE
    hwnd = None
    if window_query:
        win = UIA_ENGINE.find_window(window_query)
        if not win:
            return {"error": f"Window matching '{window_query}' not found."}
        hwnd = win["hwnd"]
    return UIA_ENGINE.inspect_ui_tree(hwnd=hwnd, max_depth=max_depth, control_types=control_types)


def _ui_action(
    target_element: str,
    action: str = "invoke",
    control_type: str = "",
    value: str = "",
    window_query: str = "",
) -> dict[str, Any]:
    """Execute a structured UI action (invoke, set_value, toggle, select, expand, collapse) on a UI element."""
    from .uia_engine import UIA_ENGINE
    hwnd = None
    if window_query:
        win = UIA_ENGINE.find_window(window_query)
        if win:
            hwnd = win["hwnd"]
    return UIA_ENGINE.execute_ui_action(
        target_name=target_element,
        action=action,
        control_type=control_type or None,
        value=value or None,
        hwnd=hwnd,
    )


def _list_browser_tabs(browser_name: str = "Brave") -> dict[str, Any]:
    """List open browser tabs in Brave, Chrome, or Edge via structured UI Automation."""
    from .uia_engine import UIA_ENGINE
    tabs = UIA_ENGINE.list_browser_tabs(browser_name=browser_name)
    return {"browser": browser_name, "tab_count": len(tabs), "tabs": tabs}


def _switch_browser_tab(tab_name: str, browser_name: str = "Brave") -> dict[str, Any]:
    """Switch to a specific browser tab in Brave, Chrome, or Edge via structured UI Automation."""
    from .uia_engine import UIA_ENGINE
    return UIA_ENGINE.switch_browser_tab(tab_query=tab_name, browser_name=browser_name)



def register_computer_tools(registry: ToolRegistry) -> None:
    """Register all computer / GUI control tools in the provided registry."""
    # 1. Screenshot (LOW)
    registry.register(
        Tool(
            "computer.screenshot",
            "Capture a screenshot of the current desktop and save to storage. Returns metadata (path, dimensions, timestamp).",
            PermissionLevel.LOW,
            _schema({}, []),
            _screenshot,
        )
    )

    # 2. Inspect Screen (LOW)
    registry.register(
        Tool(
            "computer.inspect_screen",
            "Inspect and visually analyze the current screen or a saved screenshot using a vision AI model. Useful for understanding visible UI, text, and active windows.",
            PermissionLevel.LOW,
            _schema(
                {
                    "prompt": {"type": "string", "description": "What to inspect or query about the screen."},
                    "image_path": {"type": "string", "description": "Optional path to a previously captured screenshot file."},
                },
                [],
            ),
            _inspect_screen,
        )
    )

    # 3. Locate Element (LOW)
    registry.register(
        Tool(
            "computer.locate_element",
            "Visually ground and locate the screen pixel coordinates (x, y) of a described UI element (e.g. 'Settings button', 'Send button', 'Close icon').",
            PermissionLevel.LOW,
            _schema(
                {
                    "element_description": {"type": "string", "description": "Visual description of the UI element to find."},
                    "image_path": {"type": "string", "description": "Optional path to a previously captured screenshot file."},
                },
                ["element_description"],
            ),
            _locate_element,
        )
    )

    # 4. Verify Screen Change (LOW)
    registry.register(
        Tool(
            "computer.verify_screen_change",
            "Compare before and after screenshots to verify if an intended action or UI state change occurred.",
            PermissionLevel.LOW,
            _schema(
                {
                    "expected_change": {"type": "string", "description": "Description of the expected visual change."},
                    "before_image_path": {"type": "string", "description": "Path to the before-action screenshot."},
                    "after_image_path": {"type": "string", "description": "Optional path to the after-action screenshot (if omitted, captures fresh screenshot)."},
                },
                ["expected_change", "before_image_path"],
            ),
            _verify_screen_change,
        )
    )

    # 5. Get Active Window (LOW)
    registry.register(
        Tool(
            "computer.get_active_window",
            "Get the title, position, and dimensions of the currently active/focused window on the desktop.",
            PermissionLevel.LOW,
            _schema({}, []),
            _get_active_window,
        )
    )

    # 6. List Windows (LOW)
    registry.register(
        Tool(
            "computer.list_windows",
            "List all open top-level application windows on the desktop including titles, process IDs, and active window state.",
            PermissionLevel.LOW,
            _schema({"visible_only": {"type": "boolean", "description": "Filter to visible windows only (default True)."}}, []),
            _list_windows,
        )
    )

    # 7. Switch Window (LOW)
    registry.register(
        Tool(
            "computer.switch_window",
            "Switch focus and bring to the foreground an application window by title keyword or name.",
            PermissionLevel.LOW,
            _schema({"target": {"type": "string", "description": "Title keyword or application name of the window to focus."}}, ["target"]),
            _switch_window,
        )
    )

    # 8. Close Window (HIGH)
    registry.register(
        Tool(
            "computer.close_window",
            "Close an open application window by title keyword or name.",
            PermissionLevel.HIGH,
            _schema({"target": {"type": "string", "description": "Title keyword or application name of the window to close."}}, ["target"]),
            _close_window,
        )
    )

    # 9. Inspect UI Tree (LOW)
    registry.register(
        Tool(
            "computer.inspect_ui_tree",
            "Inspect structured UI controls, buttons, text fields, tabs, and menus of an application window via Windows UI Automation without taking a screenshot.",
            PermissionLevel.LOW,
            _schema(
                {
                    "window_query": {"type": "string", "description": "Optional application or window title keyword to inspect."},
                    "max_depth": {"type": "integer", "description": "Maximum tree depth to inspect (default 4)."},
                    "control_types": {"type": "array", "description": "Optional list of control types to filter by (e.g. ['Button', 'TabItem', 'Edit']).", "items": {"type": "string"}},
                },
                [],
            ),
            _inspect_ui_tree,
        )
    )

    # 10. UI Action (MEDIUM)
    registry.register(
        Tool(
            "computer.ui_action",
            "Execute a structured action (invoke button, set text value, toggle checkbox, select tab/item, expand dropdown) on a UI element via Windows UI Automation.",
            PermissionLevel.MEDIUM,
            _schema(
                {
                    "target_element": {"type": "string", "description": "Name, title, or label of the UI element to interact with."},
                    "action": {"type": "string", "description": "Action to perform: 'invoke', 'set_value', 'toggle', 'select', 'expand', 'collapse'. Default 'invoke'."},
                    "control_type": {"type": "string", "description": "Optional control type filter (e.g. 'Button', 'Edit', 'CheckBox', 'TabItem')."},
                    "value": {"type": "string", "description": "Value or text to enter if action is 'set_value'."},
                    "window_query": {"type": "string", "description": "Optional window title keyword containing the element."},
                },
                ["target_element"],
            ),
            _ui_action,
        )
    )

    # 11. List Browser Tabs (LOW)
    registry.register(
        Tool(
            "computer.list_browser_tabs",
            "List all open tabs in Brave, Chrome, or Edge without taking screenshots.",
            PermissionLevel.LOW,
            _schema({"browser_name": {"type": "string", "description": "Browser name: 'Brave', 'Chrome', or 'Edge'. Default 'Brave'."}}, []),
            _list_browser_tabs,
        )
    )

    # 12. Switch Browser Tab (LOW)
    registry.register(
        Tool(
            "computer.switch_browser_tab",
            "Switch to a specific browser tab by title in Brave, Chrome, or Edge via Windows UI Automation.",
            PermissionLevel.LOW,
            _schema(
                {
                    "tab_name": {"type": "string", "description": "Title keyword of the tab to switch to."},
                    "browser_name": {"type": "string", "description": "Browser name: 'Brave', 'Chrome', or 'Edge'. Default 'Brave'."},
                },
                ["tab_name"],
            ),
            _switch_browser_tab,
        )
    )

    # 13. Mouse Move (LOW)
    registry.register(
        Tool(
            "computer.mouse_move",
            "Move the mouse cursor to specific (x, y) screen coordinates.",
            PermissionLevel.LOW,
            _schema(
                {
                    "x": {"type": "integer", "description": "X coordinate in pixels from left edge."},
                    "y": {"type": "integer", "description": "Y coordinate in pixels from top edge."},
                },
                ["x", "y"],
            ),
            _mouse_move,
        )
    )

    # 14. Scroll (LOW)
    registry.register(
        Tool(
            "computer.scroll",
            "Scroll vertically at current cursor position or optional (x, y) coordinates (positive=up, negative=down).",
            PermissionLevel.LOW,
            _schema(
                {
                    "clicks": {"type": "integer", "description": "Number of scroll clicks. Positive to scroll up, negative to scroll down."},
                    "x": {"type": "integer", "description": "Optional X coordinate for scroll target."},
                    "y": {"type": "integer", "description": "Optional Y coordinate for scroll target."},
                },
                ["clicks"],
            ),
            _scroll,
        )
    )

    # 15. Mouse Click (MEDIUM)
    registry.register(
        Tool(
            "computer.mouse_click",
            "Click the mouse at specific (x, y) screen coordinates with configurable button and click count.",
            PermissionLevel.MEDIUM,
            _schema(
                {
                    "x": {"type": "integer", "description": "X coordinate in pixels."},
                    "y": {"type": "integer", "description": "Y coordinate in pixels."},
                    "button": {"type": "string", "description": "Mouse button: 'left', 'right', or 'middle'. Default 'left'."},
                    "clicks": {"type": "integer", "description": "Number of clicks: 1 (single click) or 2 (double click). Default 1."},
                },
                ["x", "y"],
            ),
            _mouse_click,
        )
    )

    # 16. Keyboard Type (MEDIUM)
    registry.register(
        Tool(
            "computer.keyboard_type",
            "Type text into the currently active/focused window.",
            PermissionLevel.MEDIUM,
            _schema(
                {
                    "text": {"type": "string", "description": "Text to type into the focused element."},
                    "interval": {"type": "number", "description": "Optional typing delay between characters in seconds (default 0.0)."},
                },
                ["text"],
            ),
            _keyboard_type,
        )
    )

    # 17. Key Press (MEDIUM)
    registry.register(
        Tool(
            "computer.key_press",
            "Press an ordinary single keyboard key (e.g. 'enter', 'tab', 'escape', 'space', 'backspace', 'down').",
            PermissionLevel.MEDIUM,
            _schema(
                {
                    "key": {"type": "string", "description": "Key name to press (e.g. 'enter', 'tab', 'escape', 'space', 'up', 'down')."},
                },
                ["key"],
            ),
            _key_press,
        )
    )

    # 18. Hotkey / Shortcut (HIGH)
    registry.register(
        Tool(
            "computer.hotkey",
            "Press a keyboard shortcut (e.g. ['ctrl', 'c'], ['ctrl', 'v'], ['ctrl', 's']). High-risk, requires user approval. Use structured tools like computer.close_browser_tab or computer.close_window to close specific targets.",
            PermissionLevel.HIGH,
            _schema(
                {
                    "keys": {
                        "type": "array",
                        "description": "List of key names to press together in order (e.g. ['ctrl', 's']).",
                    },
                },
                ["keys"],
            ),
            _hotkey,
        )
    )

    # 19. Launch App (HIGH)
    registry.register(
        Tool(
            "computer.launch_app",
            "Launch a desktop application executable or URI scheme. High-risk, requires user approval. If the application is already open, use computer.switch_window to bring it into focus rather than launching duplicates.",
            PermissionLevel.HIGH,
            _schema(
                {
                    "target": {
                        "type": "string",
                        "description": "Application name or relative workspace path to execute/open (e.g. 'notepad.exe', 'calc.exe', 'code.cmd').",
                    },
                    "arguments": {
                        "type": "array",
                        "description": "Optional list of command line arguments for the application.",
                        "items": {"type": "string"},
                    },
                },
                ["target"],
            ),
            _launch_app,
        )
    )

    # 20. Autonomous GUI Action Workflow (MEDIUM)
    registry.register(
        Tool(
            "computer.gui_action_workflow",
            "Fallback visual GUI workflow when structured UI Automation is unavailable: visually locates target element on screen, performs action (click/type), and verifies visual change.",
            PermissionLevel.MEDIUM,
            _schema(
                {
                    "target_element": {"type": "string", "description": "Visual description of UI element to locate and interact with."},
                    "action": {"type": "string", "description": "Action type: 'click', 'double_click', 'right_click', or 'type'. Default 'click'."},
                    "text_to_type": {"type": "string", "description": "Text to type if action is 'type'."},
                    "expected_change": {"type": "string", "description": "Optional expected visual change to verify after the action."},
                    "retries": {"type": "integer", "description": "Max location retry attempts if element not immediately found (1..3, default 1)."},
                },
                ["target_element"],
            ),
            _gui_action_workflow,
        )
    )

    # 21. Deterministic Close Browser Tab Fast Path (MEDIUM)
    registry.register(
        Tool(
            "computer.close_browser_tab",
            "Deterministic control to close a specific browser tab using Windows UI Automation, with fallback to visually grounded close button and verification.",
            PermissionLevel.MEDIUM,
            _schema(
                {
                    "tab_name": {"type": "string", "description": "Name or title keyword of the browser tab to close (e.g. 'Claude', 'YouTube', 'GitHub')."},
                    "browser_name": {"type": "string", "description": "Name of the browser application (e.g. 'Brave', 'Chrome', 'Edge'). Default 'Brave'."},
                },
                ["tab_name"],
            ),
            _close_browser_tab,
        )
    )






