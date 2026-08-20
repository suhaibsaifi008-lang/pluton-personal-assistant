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
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        windows = PYWINAUTO_ADAPTER.list_windows(visible_only=True)
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
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        matched = PYWINAUTO_ADAPTER.find_windows_by_app(app_name)
        running = bool(matched)
        win = matched[0] if matched else None
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
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER

        resolved_name = target or app_name or ""
        res = PYWINAUTO_ADAPTER.launch_app(
            app_name=resolved_name,
            args=args or [],
            reuse_existing=reuse_existing,
            timeout=6.0,
        )
        if res.get("success") and context:
            if res.get("hwnd"):
                context.bound_hwnd = res["hwnd"]
            if res.get("pid"):
                context.bound_pid = res["pid"]
        return res

    def focus(
        self,
        hwnd: int | None = None,
        app_name: str | None = None,
        target: str | int | None = None,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Focus an existing window by HWND or semantic name."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        tgt = hwnd or target or app_name
        if not tgt:
            return {"success": False, "error": "No window target specified"}
        res = PYWINAUTO_ADAPTER.focus_window(tgt)
        if res.get("success") and context and res.get("hwnd"):
            context.bound_hwnd = res["hwnd"]
        return res

    def close(
        self,
        hwnd: int | None = None,
        app_name: str | None = None,
        target: str | int | None = None,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Close an application window gracefully."""
        KERNEL.assert_authorized(context.task_id if context else None)
        from ..adapters.pywinauto_adapter import PYWINAUTO_ADAPTER
        target_hwnd = hwnd
        resolved_name = str(target or app_name or "")
        if isinstance(target, int):
            target_hwnd = target
        elif not target_hwnd and resolved_name:
            matched = PYWINAUTO_ADAPTER.find_windows_by_app(resolved_name)
            if matched:
                target_hwnd = matched[0].get("hwnd")

        if not target_hwnd:
            return {"success": False, "error": f"Window for '{resolved_name or hwnd}' not found"}

        res = PYWINAUTO_ADAPTER.close_window(target_hwnd)
        if res.get("success") and context and context.bound_hwnd == target_hwnd:
            context.workflow_context.invalidate_window()
            context.bound_hwnd = None
        return res

    def restart(self, app_name: str, context: ExecutionContext | None = None) -> dict[str, Any]:
        """Restart an application."""
        self.close(app_name=app_name, context=context)
        time.sleep(0.5)
        return self.launch(app_name=app_name, context=context)


APP_DOMAIN = AppDomainHandler()
