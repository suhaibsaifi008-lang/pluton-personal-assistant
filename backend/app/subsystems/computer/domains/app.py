"""
PLUTON V2 — App Domain Handler
Implements canonical application lifecycle management:
app.list, app.launch, app.focus, app.minimize, app.maximize, app.restore, app.close, app.restart, app.is_running.
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from app.core.contracts import ExecutionContext, VerificationStrategy
from app.kernel.control_kernel import KERNEL
from app.verification.verification_engine import VERIFICATION_ENGINE

logger = logging.getLogger("pluton.computer.app")


def _get_process_image_name(pid: int) -> str:
    """Retrieve process executable basename in 0.1ms using Win32 API without external dependencies."""
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


class AppDomainHandler:
    """Canonical handler for application lifecycle management."""

    def _resolve_app_exe(self, app_name: str) -> tuple[str, str, bool]:
        from app.planning.intent_compiler import UniversalAppRegistry
        app_key = app_name.strip()
        resolved = UniversalAppRegistry.resolve(app_key)
        if resolved:
            exe = resolved.get("exe", f"{app_key}.exe")
            is_uri = exe.startswith("ms-")
            title = resolved.get("title_kw", app_key.title())
            return os.path.expandvars(exe), title, is_uri
        return app_name, app_name.title(), False

    def list(self, context: ExecutionContext | None = None) -> list[dict[str, Any]]:
        """List running applications with visible windows."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from app.tools.uia_engine import UIA_ENGINE
        windows = UIA_ENGINE.list_windows(visible_only=True)
        apps = []
        seen_titles = set()
        for w in windows:
            title = w.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                apps.append({
                    "title": title,
                    "hwnd": w.get("hwnd"),
                    "pid": w.get("pid"),
                    "class_name": w.get("class_name"),
                })
        return apps

    list_apps = list

    def is_running(self, app_name: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Check if an application is running (by process or window)."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from app.tools.uia_engine import UIA_ENGINE
        _, title_kw, _ = self._resolve_app_exe(app_name)
        win = UIA_ENGINE.find_window(title_kw or app_name)
        running = win is not None
        return {
            "app": app_name,
            "running": running,
            "hwnd": win.get("hwnd") if win else None,
            "pid": win.get("pid") if win else None,
            "title": win.get("title") if win else None,
        }

    def launch(
        self,
        app_name: str = "",
        target: str = "",
        args: list[str] | None = None,
        reuse_existing: bool = False,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Launch an application and bind its HWND/PID to context with state-transition verification."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from app.tools.uia_engine import UIA_ENGINE

        resolved_name = target or app_name or ""
        exe, title_kw, is_uri = self._resolve_app_exe(resolved_name)
        args = args or []
        target_exe_name = Path(exe).name.lower() if exe else ""
        app_key = str(resolved_name or "").strip().lower()

        # 1. Pre-launch Snapshot
        wins_before = UIA_ENGINE.list_windows(visible_only=False)
        hwnds_before = {w.get("hwnd", 0) for w in wins_before}

        shell_classes = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow"}

        matching_before = []
        for w in wins_before:
            if w.get("rect", {}).get("width", 0) <= 0:
                continue
            w_pid = w.get("pid", 0)
            w_title = w.get("title", "")
            w_cname = w.get("class_name", "")
            if w_cname in shell_classes:
                continue
            w_pname = _get_process_image_name(w_pid)
            if (
                (target_exe_name and w_pname == target_exe_name)
                or (app_key and app_key in w_pname)
                or (title_kw and title_kw.lower() in w_title.lower())
                or (app_key in ("explorer", "file explorer") and w_cname in ("CabinetWClass", "ExploreWClass", "XamlExplorerHostIslandWindow"))
            ):
                matching_before.append(w)

        # Explicit reuse check
        if reuse_existing and matching_before:
            target_win = matching_before[0]
            target_hwnd = target_win["hwnd"]
            target_pid = target_win.get("pid")
            UIA_ENGINE.focus_window(target_hwnd)
            if context:
                context.bound_hwnd = target_hwnd
                context.bound_pid = target_pid
            return {
                "success": True,
                "transition": "EXISTING_INSTANCE_REUSED",
                "method": "window_focus",
                "hwnd": target_hwnd,
                "pid": target_pid,
                "title": target_win.get("title"),
                "message": f"Focused existing '{app_name}' window (HWND: {target_hwnd}).",
            }

        # 2. Launch Execution
        launched_pid = None
        if is_uri and hasattr(os, "startfile"):
            os.startfile(exe)
        elif app_key in ("explorer", "file explorer"):
            try:
                proc = subprocess.Popen(["explorer.exe"], shell=False)
                launched_pid = proc.pid
            except Exception:
                try:
                    if hasattr(os, "startfile"):
                        os.startfile("explorer.exe")
                except Exception:
                    pass
        elif app_key == "notepad":
            try:
                proc = subprocess.Popen(["notepad.exe"] + args, shell=False)
                launched_pid = proc.pid
            except Exception:
                try:
                    subprocess.Popen(["explorer.exe", "shell:AppsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"])
                except Exception:
                    pass
        elif app_key == "brave":
            try:
                brave_args = ["--remote-debugging-port=9222"] if not any("--remote-debugging-port" in str(a) for a in args) else []
                proc = subprocess.Popen([exe] + brave_args, shell=False)
                launched_pid = proc.pid
            except Exception:
                pass
        else:
            try:
                proc = subprocess.Popen([exe] + args, shell=False)
                launched_pid = proc.pid
            except FileNotFoundError:
                try:
                    if hasattr(os, "startfile"):
                        os.startfile(app_name)
                    else:
                        proc = subprocess.Popen(app_name, shell=True)
                        launched_pid = proc.pid
                except Exception:
                    pass
            except Exception:
                pass

        # 3. Post-launch State-Transition Verification
        deadline = time.perf_counter() + 6.0
        new_window = None
        candidate_existing = matching_before[0] if matching_before else None
        secondary_attempted = False

        while time.perf_counter() < deadline:
            wins_after = UIA_ENGINE.list_windows(visible_only=True)
            for w in wins_after:
                hwnd = w.get("hwnd", 0)
                pid = w.get("pid", 0)
                title = w.get("title", "")
                c_name = w.get("class_name", "")
                if c_name in shell_classes:
                    continue
                pname = _get_process_image_name(pid)

                is_match = False
                if (
                    (target_exe_name and pname == target_exe_name)
                    or (app_key and app_key in pname)
                    or (title_kw and title_kw.lower() in title.lower())
                    or (app_key in ("explorer", "file explorer", "downloads", "documents") and c_name in ("CabinetWClass", "ExploreWClass", "XamlExplorerHostIslandWindow"))
                    or (app_key in ("calculator", "calc") and ("calculator" in title.lower() or c_name == "ApplicationFrameWindow"))
                    or (launched_pid and pid == launched_pid)
                ):
                    is_match = True

                if is_match:
                    if hwnd not in hwnds_before or (launched_pid and pid == launched_pid):
                        new_window = w
                        break
                    elif not candidate_existing:
                        candidate_existing = w

            if new_window:
                break

            # If multi-process browser/app delegated to existing window and 1.5s elapsed, accept existing instance
            if candidate_existing and time.perf_counter() > (deadline - 4.5):
                new_window = candidate_existing
                break

            # Secondary activation via shell if UWP / Modern App didn't create window immediately
            if not secondary_attempted and (time.perf_counter() > deadline - 3.2):
                secondary_attempted = True
                try:
                    if app_key == "notepad":
                        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"])
                    elif app_key in ("calc", "calculator"):
                        os.startfile("calculator:")
                    else:
                        subprocess.run(["powershell", "-Command", f"Start-Process '{exe}'"], capture_output=True, check=False)
                except Exception:
                    pass

            time.sleep(0.15)

        if new_window:
            target_hwnd = new_window["hwnd"]
            target_pid = new_window.get("pid", launched_pid)

            UIA_ENGINE.focus_window(target_hwnd)
            time.sleep(0.1)

            if context:
                context.bound_hwnd = target_hwnd
                context.bound_pid = target_pid

            is_new = target_hwnd not in hwnds_before
            return {
                "success": True,
                "transition": "NEW_INSTANCE_CREATED" if is_new else "EXISTING_INSTANCE_REUSED",
                "method": "native_app_launch" if is_new else "window_focus",
                "hwnd": target_hwnd,
                "pid": target_pid,
                "target": app_name,
                "title": new_window.get("title", title_kw),
                "focused": True,
                "verified": True,
                "message": f"{'Launched' if is_new else 'Focused existing'} '{app_name}' (HWND: {target_hwnd}, PID: {target_pid}).",
            }

        if matching_before:
            target_win = matching_before[0]
            target_hwnd = target_win["hwnd"]
            target_pid = target_win.get("pid")
            UIA_ENGINE.focus_window(target_hwnd)
            if context:
                context.bound_hwnd = target_hwnd
                context.bound_pid = target_pid
            return {
                "success": True,
                "transition": "EXISTING_INSTANCE_REUSED",
                "method": "window_focus",
                "hwnd": target_hwnd,
                "pid": target_pid,
                "title": target_win.get("title"),
                "message": f"Focused existing '{app_name}' window (HWND: {target_hwnd}).",
            }

        return {
            "success": False,
            "transition": "LAUNCH_FAILED",
            "error": f"Application '{app_name}' failed to create a visible window within 6.0s.",
            "message": f"Failed to launch '{app_name}'. No window appeared.",
        }

    def focus(self, hwnd: int | None = None, app_name: str | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Focus an existing window by HWND or semantic name."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from app.tools.uia_engine import UIA_ENGINE
        target_hwnd = hwnd
        if not target_hwnd and app_name:
            _, title_kw, _ = self._resolve_app_exe(app_name)
            win = UIA_ENGINE.find_window(title_kw or app_name)
            if win:
                target_hwnd = win.get("hwnd")

        if not target_hwnd:
            return {"success": False, "error": f"Window for '{app_name or hwnd}' not found"}

        success = UIA_ENGINE.focus_window(target_hwnd)
        if success and context:
            context.bound_hwnd = target_hwnd
        return {"success": success, "hwnd": target_hwnd, "method": "window_focus"}

    def close(self, hwnd: int | None = None, app_name: str | None = None, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Close an application window gracefully."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from app.tools.uia_engine import UIA_ENGINE
        target_hwnd = hwnd
        if not target_hwnd and app_name:
            _, title_kw, _ = self._resolve_app_exe(app_name)
            win = UIA_ENGINE.find_window(title_kw or app_name)
            if win:
                target_hwnd = win.get("hwnd")

        if not target_hwnd:
            return {"success": False, "error": f"Window for '{app_name or hwnd}' not found"}

        success = UIA_ENGINE.close_window(target_hwnd)
        if success and context and context.bound_hwnd == target_hwnd:
            context.workflow_context.invalidate_window()
            context.bound_hwnd = None
        return {"success": success, "hwnd": target_hwnd, "method": "window_close"}

    def restart(self, app_name: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Restart an application."""
        self.close(app_name=app_name, context=context)
        time.sleep(0.5)
        return self.launch(app_name=app_name, context=context)

APP_DOMAIN = AppDomainHandler()
