"""
PLUTON V2 — Canonical Computer Engine
The central orchestrator for all computer subsystems and domains under the V2 runtime.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.core.contracts import (
    Action,
    CapabilityType,
    ExecutionContext,
    ExecutionTier,
    ToolResult,
)
from app.kernel.control_kernel import KERNEL

from .contracts import (
    ComputerDomain,
    PerformanceMetrics,
    TargetResolutionResult,
    TargetResolutionStatus,
    TargetSpec,
)
from .domains.app import APP_DOMAIN
from .domains.window import WINDOW_DOMAIN
from .domains.browser import BROWSER_DOMAIN
from .domains.web import WEB_DOMAIN
from .domains.ui import UI_DOMAIN
from .domains.keyboard import KEYBOARD_DOMAIN
from .domains.mouse import MOUSE_DOMAIN
from .domains.screen import SCREEN_DOMAIN
from .domains.vision import VISION_DOMAIN
from .domains.filesystem import FILESYSTEM_DOMAIN
from .domains.terminal import TERMINAL_DOMAIN
from .domains.clipboard import CLIPBOARD_DOMAIN
from .target_resolver import TARGET_RESOLVER

logger = logging.getLogger("pluton.computer.engine")

LEGACY_COMPUTER_API_CALLS = 0


class ComputerEngine:
    """Canonical Universal Computer Subsystem Engine."""

    def __init__(self) -> None:
        self.app = APP_DOMAIN
        self.window = WINDOW_DOMAIN
        self.browser = BROWSER_DOMAIN
        self.web = WEB_DOMAIN
        self.ui = UI_DOMAIN
        self.keyboard = KEYBOARD_DOMAIN
        self.mouse = MOUSE_DOMAIN
        self.screen = SCREEN_DOMAIN
        self.vision = VISION_DOMAIN
        self.filesystem = FILESYSTEM_DOMAIN
        self.terminal = TERMINAL_DOMAIN
        self.clipboard = CLIPBOARD_DOMAIN
        self.resolver = TARGET_RESOLVER

    # -------------------------------------------------------------------------
    # Canonical Execution Dispatcher
    # -------------------------------------------------------------------------

    async def execute_action(self, action: Action, context: ExecutionContext) -> ToolResult:
        """Execute a computer action through the appropriate domain handler with telemetry."""
        t_start = time.perf_counter()
        metrics = PerformanceMetrics(
            execution_tier=action.tier_requested.value,
        )

        # 1. Hardware-bound Kernel Token Authorization & Cancellation Gate
        from app.kernel.task_registry import ACTIVE_TASK_REGISTRY
        if getattr(context, "is_cancelled", False) or (context.task_id and ACTIVE_TASK_REGISTRY.is_cancelled(context.task_id)):
            return ToolResult(
                call_id=action.id,
                name=action.capability.value,
                observed={"error": "CANCELLED", "reason": "Task was cancelled before execution."},
                status="cancelled",
                summary="Task cancelled before physical execution.",
                raw_arguments=action.parameters,
            )
        KERNEL.assert_authorized(context.task_id)

        # 2. Resolve Domain from Capability
        domain = self._map_capability_to_domain(action.capability)
        params = action.parameters or {}

        # 3. Explicit Target Resolution
        t_resolve_start = time.perf_counter()
        target_spec = self._build_target_spec(action, domain)
        resolve_res = self.resolver.resolve(domain, target_spec)
        metrics.target_resolution_latency_ms = (time.perf_counter() - t_resolve_start) * 1000.0

        if (
            resolve_res.status == TargetResolutionStatus.AMBIGUOUS_TARGET
            and action.capability not in (
                CapabilityType.BROWSER_GET_TITLE,
                CapabilityType.BROWSER_GET_URL,
                CapabilityType.BROWSER_GET_STATE,
                CapabilityType.BROWSER_LIST_TABS,
                CapabilityType.WINDOW_LIST,
                CapabilityType.APP_LIST,
                CapabilityType.TERMINAL_OUTPUT,
            )
        ):
            return ToolResult(
                call_id=action.id,
                name=action.capability.value,
                observed={"error": "AMBIGUOUS_TARGET", "reason": resolve_res.reason, "candidates": [c.name for c in resolve_res.candidates]},
                status="failed",
                summary=f"AMBIGUOUS_TARGET: Refusing execution because multiple targets match '{target_spec.semantic_name or target_spec.raw_query}'.",
                raw_arguments=action.parameters,
            )
        elif resolve_res.status == TargetResolutionStatus.TARGET_NOT_FOUND and action.capability in (
            CapabilityType.WINDOW_FOCUS,
            CapabilityType.WINDOW_CLOSE,
            CapabilityType.BROWSER_SWITCH_TAB,
            CapabilityType.UI_INVOKE,
        ):
            return ToolResult(
                call_id=action.id,
                name=action.capability.value,
                observed={"error": "TARGET_NOT_FOUND", "reason": resolve_res.reason},
                status="failed",
                summary=f"TARGET_NOT_FOUND: Could not find target '{target_spec.semantic_name or target_spec.raw_query}'.",
                raw_arguments=action.parameters,
            )

        # 4. Domain Dispatch
        t_exec_start = time.perf_counter()
        observed_result: dict[str, Any] = {}
        strategy_name = "native_api"

        try:
            # =================================================================
            # APP Domain
            # =================================================================
            if action.capability == CapabilityType.APP_LIST:
                observed_result = {"success": True, "apps": self.app.list(context=context)}
                strategy_name = "app_list"

                app_target = params.get("app_name", action.target)
                args = params.get("args", [])
                observed_result = self.app.launch(app_target, args=args, context=context)
                strategy_name = "app_launch"
                if isinstance(observed_result, dict):
                    if observed_result.get("hwnd"):
                        context.bound_hwnd = observed_result["hwnd"]
                        context.workflow_context.active_hwnd = observed_result["hwnd"]
                    if observed_result.get("pid"):
                        context.bound_pid = observed_result["pid"]
                        context.workflow_context.active_pid = observed_result["pid"]

            elif action.capability == CapabilityType.APP_FOCUS:
                observed_result = self.app.focus(action.target, context=context)
                strategy_name = "app_focus"

            elif action.capability == CapabilityType.APP_MINIMIZE:
                observed_result = self.app.minimize(action.target, context=context)
                strategy_name = "app_minimize"

            elif action.capability == CapabilityType.APP_MAXIMIZE:
                observed_result = self.app.maximize(action.target, context=context)
                strategy_name = "app_maximize"

            elif action.capability == CapabilityType.APP_RESTORE:
                observed_result = self.app.restore(action.target, context=context)
                strategy_name = "app_restore"

            elif action.capability == CapabilityType.APP_CLOSE:
                observed_result = self.app.close(action.target, context=context)
                strategy_name = "app_close"

            elif action.capability == CapabilityType.APP_RESTART:
                observed_result = self.app.restart(action.target, context=context)
                strategy_name = "app_restart"

            elif action.capability == CapabilityType.APP_IS_RUNNING:
                observed_result = self.app.is_running(action.target, context=context)
                strategy_name = "app_is_running"

            # =================================================================
            # WINDOW Domain
            # =================================================================
            elif action.capability == CapabilityType.WINDOW_LIST:
                wins = self.window.list_windows(visible_only=params.get("visible_only", True), context=context)
                win_titles = [w.get("title") for w in wins if w.get("title")]
                if win_titles:
                    msg = f"Found {len(wins)} open window(s):\n" + "\n".join(f"- {w.get('title')} (HWND: {w.get('hwnd')})" for w in wins)
                else:
                    msg = f"Found {len(wins)} open window(s)."
                observed_result = {"success": True, "windows": wins, "count": len(wins), "message": msg}
                strategy_name = "uia_window_list"

            elif action.capability == CapabilityType.WINDOW_FIND:
                win = self.window.find(action.target, context=context)
                observed_result = {"success": win is not None, "window": win}
                strategy_name = "uia_window_find"

            elif action.capability == CapabilityType.WINDOW_FOCUS:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                observed_result = self.window.focus(target_hwnd, context=context)
                strategy_name = "uia_window_focus"

            elif action.capability == CapabilityType.WINDOW_MOVE:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                x = params.get("x", 0)
                y = params.get("y", 0)
                observed_result = self.window.move(target_hwnd, x=x, y=y, context=context)
                strategy_name = "win32_window_move"

            elif action.capability == CapabilityType.WINDOW_RESIZE:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                w = params.get("width", 800)
                h = params.get("height", 600)
                observed_result = self.window.resize(target_hwnd, width=w, height=h, context=context)
                strategy_name = "win32_window_resize"

            elif action.capability == CapabilityType.WINDOW_MINIMIZE:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                observed_result = self.window.minimize(target_hwnd, context=context)
                strategy_name = "uia_window_minimize"

            elif action.capability == CapabilityType.WINDOW_MAXIMIZE:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                observed_result = self.window.maximize(target_hwnd, context=context)
                strategy_name = "uia_window_maximize"

            elif action.capability == CapabilityType.WINDOW_RESTORE:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                observed_result = self.window.restore(target_hwnd, context=context)
                strategy_name = "uia_window_restore"

            elif action.capability == CapabilityType.WINDOW_CLOSE:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                observed_result = self.window.close(target_hwnd, context=context)
                strategy_name = "uia_window_close"

            elif action.capability == CapabilityType.WINDOW_GET_STATE:
                target_hwnd = resolve_res.target.hwnd if resolve_res.target else action.target
                observed_result = self.window.get_state(target_hwnd, context=context)
                strategy_name = "uia_window_get_state"

            # =================================================================
            # BROWSER Domain (Navigation & Tab Control)
            # =================================================================
            elif action.capability == CapabilityType.BROWSER_DETECT:
                browser_name = params.get("browser", context.active_browser)
                observed_result = self.browser.detect(browser_name=browser_name, context=context)
                strategy_name = "browser_detect"

            elif action.capability == CapabilityType.BROWSER_NAVIGATE:
                url = params.get("url", action.target)
                browser_name = params.get("browser", context.active_browser)
                observed_result = await self.browser.navigate(url, browser_name=browser_name, context=context)
                strategy_name = observed_result.get("method", "browser_navigate")

            elif action.capability == CapabilityType.BROWSER_SEARCH:
                q = params.get("query", action.target)
                engine = params.get("engine", "google")
                browser_name = params.get("browser", context.active_browser)
                observed_result = await self.browser.search(query=q, engine=engine, browser_name=browser_name, context=context)
                strategy_name = "browser_search"

            elif action.capability == CapabilityType.BROWSER_OPEN_TAB:
                url = params.get("url", "about:blank")
                browser_name = params.get("browser", context.active_browser)
                observed_result = await self.browser.open_tab(url=url, browser_name=browser_name, context=context)
                strategy_name = "browser_open_tab"

            elif action.capability == CapabilityType.BROWSER_CLOSE_TAB:
                target_tab = params.get("target_tab", params.get("target", action.target))
                browser_name = params.get("browser", context.active_browser)
                observed_result = self.browser.close_tab(target_tab, browser_name=browser_name, context=context)
                strategy_name = "uia_close_tab"

            elif action.capability == CapabilityType.BROWSER_LIST_TABS:
                browser_name = params.get("browser", context.active_browser)
                tabs = self.browser.list_tabs(browser_name=browser_name, context=context)
                if tabs:
                    msg = f"Found {len(tabs)} open tab(s) in {browser_name or 'browser'}:\n" + "\n".join(f"- {t.get('title', 'Untitled')} ({t.get('url', '')})" for t in tabs)
                else:
                    msg = f"No open tabs found in {browser_name or 'browser'}."
                observed_result = {"success": True, "tabs": tabs, "count": len(tabs), "message": msg}
                strategy_name = "uia_list_tabs"

            elif action.capability == CapabilityType.BROWSER_SWITCH_TAB:
                target_tab = params.get("target_tab", params.get("target", action.target))
                browser_name = params.get("browser", context.active_browser)
                observed_result = self.browser.switch_tab(target_tab, browser_name=browser_name, context=context)
                strategy_name = "uia_switch_tab"

            elif action.capability in (CapabilityType.BROWSER_GET_STATE, CapabilityType.BROWSER_GET_PAGE_STATE):
                observed_result = await self.browser.get_state(context=context)
                strategy_name = "browser_get_state"

            elif action.capability == CapabilityType.BROWSER_GET_URL:
                observed_result = await self.browser.get_url(context=context)
                strategy_name = "browser_get_url"

            elif action.capability == CapabilityType.BROWSER_GET_TITLE:
                observed_result = await self.browser.get_title(context=context)
                strategy_name = "browser_get_title"

            elif action.capability == CapabilityType.BROWSER_BACK:
                observed_result = await self.browser.back(context=context)
                strategy_name = "browser_back"

            elif action.capability == CapabilityType.BROWSER_FORWARD:
                observed_result = await self.browser.forward(context=context)
                strategy_name = "browser_forward"

            elif action.capability == CapabilityType.BROWSER_RELOAD:
                observed_result = await self.browser.reload(context=context)
                strategy_name = "browser_reload"

            elif action.capability in (CapabilityType.BROWSER_WAIT_FOR_PAGE, CapabilityType.BROWSER_WAIT_FOR):
                state = params.get("state", "visible")
                timeout_s = params.get("timeout_seconds", 5.0)
                observed_result = await self.browser.wait_for_page(state=state, timeout_seconds=timeout_s, context=context)
                strategy_name = "browser_wait_for_page"

            elif action.capability == CapabilityType.BROWSER_DOWNLOAD:
                target_url = params.get("target_url")
                observed_result = await self.web.download(target_url=target_url, context=context)
                strategy_name = "browser_download"

            elif action.capability == CapabilityType.BROWSER_UPLOAD:
                selector = params.get("selector", "")
                fpath = params.get("file_path", "")
                observed_result = await self.web.upload(selector=selector, file_path=fpath, context=context)
                strategy_name = "browser_upload"

            elif action.capability in (CapabilityType.BROWSER_INSPECT_PAGE, CapabilityType.WEB_INSPECT):
                max_el = params.get("max_elements", 150)
                observed_result = await self.web.inspect(max_elements=max_el, context=context)
                strategy_name = "web_inspect"

            elif action.capability in (CapabilityType.BROWSER_FIND_ELEMENT, CapabilityType.WEB_FIND):
                target_elem = params.get("target", action.target)
                role = params.get("role")
                observed_result = await self.web.find(target_elem, role=role, context=context)
                strategy_name = "web_find"

            elif action.capability in (CapabilityType.BROWSER_CLICK_ELEMENT, CapabilityType.WEB_CLICK):
                target_elem = params.get("target", action.target)
                role = params.get("role")
                expected = params.get("expected_change")
                observed_result = await self.web.click(target_elem, role=role, expected_change=expected, context=context)
                strategy_name = "web_click"

            elif action.capability == CapabilityType.WEB_DOUBLE_CLICK:
                target_elem = params.get("target", action.target)
                role = params.get("role")
                observed_result = await self.web.double_click(target_elem, role=role, context=context)
                strategy_name = "web_double_click"

            elif action.capability in (CapabilityType.BROWSER_TYPE_ELEMENT, CapabilityType.WEB_TYPE):
                target_elem = params.get("target", action.target)
                text = params.get("text", "")
                clear_first = params.get("clear_first", True)
                role = params.get("role")
                press_ent = params.get("press_enter", False)
                observed_result = await self.web.type(
                    target_elem,
                    text=text,
                    clear_first=clear_first,
                    role=role,
                    press_enter=press_ent,
                    context=context,
                )
                strategy_name = "web_type"

            elif action.capability == CapabilityType.WEB_CLEAR:
                target_elem = params.get("target", action.target)
                role = params.get("role")
                observed_result = await self.web.clear(target_elem, role=role, context=context)
                strategy_name = "web_clear"

            elif action.capability == CapabilityType.WEB_PRESS:
                key = params.get("key", action.target)
                target_elem = params.get("target")
                observed_result = await self.web.press(key, target=target_elem, context=context)
                strategy_name = "web_press"

            elif action.capability in (CapabilityType.BROWSER_SELECT_ELEMENT, CapabilityType.WEB_SELECT):
                target_elem = params.get("target", action.target)
                value = params.get("value", "")
                role = params.get("role", "combobox")
                observed_result = await self.web.select(target_elem, value=value, role=role, context=context)
                strategy_name = "web_select"

            elif action.capability == CapabilityType.WEB_HOVER:
                target_elem = params.get("target", action.target)
                role = params.get("role")
                observed_result = await self.web.hover(target_elem, role=role, context=context)
                strategy_name = "web_hover"

            elif action.capability in (CapabilityType.BROWSER_SCROLL_PAGE, CapabilityType.WEB_SCROLL):
                dx = params.get("delta_x", 0)
                dy = params.get("delta_y", 400)
                observed_result = await self.web.scroll(delta_x=dx, delta_y=dy, context=context)
                strategy_name = "web_scroll"

            elif action.capability in (CapabilityType.BROWSER_READ_PAGE, CapabilityType.WEB_READ):
                selector = params.get("selector")
                max_len = params.get("max_length", 4000)
                observed_result = await self.web.read(selector=selector, max_length=max_len, context=context)
                strategy_name = "web_read"

            elif action.capability in (CapabilityType.BROWSER_EXTRACT_TEXT, CapabilityType.WEB_EXTRACT_TEXT):
                selector = params.get("selector")
                max_len = params.get("max_length", 4000)
                observed_result = await self.web.extract_text(selector=selector, max_length=max_len, context=context)
                strategy_name = "web_extract_text"

            elif action.capability in (CapabilityType.BROWSER_EXTRACT_LINKS, CapabilityType.WEB_EXTRACT_LINKS):
                scope = params.get("scope_selector")
                observed_result = await self.web.extract_links(scope_selector=scope, context=context)
                strategy_name = "web_extract_links"

            elif action.capability == CapabilityType.WEB_WAIT:
                selector = params.get("selector")
                text = params.get("text")
                state = params.get("state", "visible")
                timeout_s = params.get("timeout_seconds", 5.0)
                observed_result = await self.web.wait(selector=selector, text=text, state=state, timeout_seconds=timeout_s, context=context)
                strategy_name = "web_wait"

            # =================================================================
            # UI Domain
            # =================================================================
            elif action.capability == CapabilityType.UI_INSPECT:
                tree = self.ui.inspect(hwnd=context.bound_hwnd or 0, context=context)
                observed_result = {"success": True, "tree": tree, "count": len(tree)}
                strategy_name = "uia_tree_inspect"

            elif action.capability == CapabilityType.UI_FIND:
                q = params.get("query", action.target)
                elems = self.ui.find(q, hwnd=context.bound_hwnd or 0, context=context)
                observed_result = {"success": bool(elems), "elements": elems, "count": len(elems)}
                strategy_name = "uia_find"

            elif action.capability == CapabilityType.UI_INVOKE:
                observed_result = self.ui.invoke(action.target, hwnd=context.bound_hwnd or 0, context=context)
                strategy_name = "uia_invoke"

            elif action.capability == CapabilityType.UI_SET_VALUE:
                val = params.get("value", "")
                observed_result = self.ui.set_value(action.target, value=val, hwnd=context.bound_hwnd or 0, context=context)
                strategy_name = "uia_set_value"

            elif action.capability == CapabilityType.UI_TOGGLE:
                observed_result = self.ui.toggle(action.target, hwnd=context.bound_hwnd or 0, context=context)
                strategy_name = "uia_toggle"

            elif action.capability == CapabilityType.UI_SELECT:
                observed_result = self.ui.select(action.target, hwnd=context.bound_hwnd or 0, context=context)
                strategy_name = "uia_select"

            elif action.capability == CapabilityType.UI_EXPAND:
                observed_result = self.ui.expand(action.target, hwnd=context.bound_hwnd or 0, context=context)
                strategy_name = "uia_expand"

            elif action.capability == CapabilityType.UI_COLLAPSE:
                observed_result = self.ui.collapse(action.target, hwnd=context.bound_hwnd or 0, context=context)
                strategy_name = "uia_collapse"

            elif action.capability == CapabilityType.UI_FOCUS:
                observed_result = self.ui.focus(action.target, hwnd=context.bound_hwnd or 0, context=context)
                strategy_name = "uia_focus"

            # =================================================================
            # KEYBOARD Domain
            # =================================================================
            elif action.capability == CapabilityType.KEYBOARD_TYPE:
                text_to_type = params.get("text", action.target)
                target_hwnd = params.get("hwnd") or context.bound_hwnd or context.workflow_context.active_hwnd
                target_pid = params.get("pid") or context.bound_pid or context.workflow_context.active_pid
                if not target_hwnd or target_hwnd == 0:
                    lookup_target = str(params.get("target_window") or params.get("app_name") or action.target or "").strip()
                    from app.tools.uia_engine import UIA_ENGINE
                    if lookup_target:
                        wins = UIA_ENGINE.list_windows(visible_only=True)
                        q_kw = lookup_target.lower()
                        for w in wins:
                            w_title = (w.get("title") or "").lower()
                            if q_kw in w_title or (q_kw == "calculator" and "calc" in w_title) or (q_kw == "notepad" and "note" in w_title):
                                target_hwnd = w.get("hwnd")
                                target_pid = w.get("pid")
                                context.bound_hwnd = target_hwnd
                                context.bound_pid = target_pid
                                break
                    if not target_hwnd or target_hwnd == 0:
                        fg = UIA_ENGINE.get_foreground_window()
                        if fg and fg.get("hwnd"):
                            target_hwnd = fg.get("hwnd")
                            target_pid = fg.get("pid")
                            context.bound_hwnd = target_hwnd
                            context.bound_pid = target_pid

                if not target_hwnd or target_hwnd == 0:
                    return ToolResult(
                        call_id=action.id,
                        name=action.capability.value,
                        observed={"error": "TARGET_BINDING_FAILED", "reason": "No target window HWND bound for keyboard typing."},
                        status="failed",
                        summary="TARGET_BINDING_FAILED: No target window bound for keyboard typing.",
                        raw_arguments=action.parameters,
                    )
                observed_result = self.keyboard.type_text(
                    text=text_to_type,
                    hwnd=target_hwnd,
                    pid=target_pid,
                    expected_text=action.expected_state or text_to_type,
                    context=context,
                )
                strategy_name = "target_bound_keyboard_pipeline"

            elif action.capability == CapabilityType.KEYBOARD_PRESS:
                key = params.get("key", action.target)
                observed_result = self.keyboard.press(key, context=context)
                strategy_name = "keyboard_press"

            elif action.capability == CapabilityType.KEYBOARD_HOTKEY:
                keys = params.get("keys", action.target)
                observed_result = self.keyboard.hotkey(keys, context=context)
                strategy_name = "keyboard_hotkey"

            elif action.capability == CapabilityType.KEYBOARD_COPY:
                observed_result = self.keyboard.copy(context=context)
                strategy_name = "keyboard_copy"

            elif action.capability == CapabilityType.KEYBOARD_PASTE:
                observed_result = self.keyboard.paste(context=context)
                strategy_name = "keyboard_paste"

            elif action.capability == CapabilityType.KEYBOARD_CUT:
                observed_result = self.keyboard.cut(context=context)
                strategy_name = "keyboard_cut"

            elif action.capability == CapabilityType.KEYBOARD_UNDO:
                observed_result = self.keyboard.undo(context=context)
                strategy_name = "keyboard_undo"

            elif action.capability == CapabilityType.KEYBOARD_REDO:
                observed_result = self.keyboard.redo(context=context)
                strategy_name = "keyboard_redo"

            # =================================================================
            # MOUSE Domain
            # =================================================================
            elif action.capability == CapabilityType.MOUSE_MOVE:
                observed_result = self.mouse.move(params.get("x", 0), params.get("y", 0), context=context)
                metrics.mouse_used = True
                strategy_name = "mouse_move"

            elif action.capability == CapabilityType.MOUSE_CLICK:
                observed_result = self.mouse.click(
                    x=params.get("x"),
                    y=params.get("y"),
                    button=params.get("button", "left"),
                    clicks=params.get("clicks", 1),
                    context=context,
                )
                metrics.mouse_used = True
                strategy_name = "mouse_click"

            elif action.capability == CapabilityType.MOUSE_DOUBLE_CLICK:
                observed_result = self.mouse.double_click(x=params.get("x"), y=params.get("y"), context=context)
                metrics.mouse_used = True
                strategy_name = "mouse_double_click"

            elif action.capability == CapabilityType.MOUSE_RIGHT_CLICK:
                observed_result = self.mouse.right_click(x=params.get("x"), y=params.get("y"), context=context)
                metrics.mouse_used = True
                strategy_name = "mouse_right_click"

            elif action.capability == CapabilityType.MOUSE_DRAG:
                observed_result = self.mouse.drag(
                    start_x=params.get("start_x", 0),
                    start_y=params.get("start_y", 0),
                    end_x=params.get("end_x", 0),
                    end_y=params.get("end_y", 0),
                    context=context,
                )
                metrics.mouse_used = True
                strategy_name = "mouse_drag"

            elif action.capability == CapabilityType.MOUSE_SCROLL:
                observed_result = self.mouse.scroll(
                    clicks=params.get("clicks", 400),
                    x=params.get("x"),
                    y=params.get("y"),
                    context=context,
                )
                metrics.mouse_used = True
                strategy_name = "mouse_scroll"

            elif action.capability == CapabilityType.MOUSE_POSITION:
                observed_result = self.mouse.position(context=context)
                metrics.mouse_used = True
                strategy_name = "mouse_position"

            # =================================================================
            # SCREEN & VISION Domain
            # =================================================================
            elif action.capability == CapabilityType.SCREEN_CAPTURE:
                reg = params.get("region")
                observed_result = self.screen.capture(region=reg, context=context)
                strategy_name = "screen_capture"

            elif action.capability == CapabilityType.SCREEN_INSPECT:
                reg = params.get("region")
                observed_result = self.screen.inspect(region=reg, context=context)
                strategy_name = "screen_inspect"

            elif action.capability == CapabilityType.VISION_FIND:
                observed_result = self.vision.find(action.target, context=context)
                metrics.vision_used = True
                strategy_name = "vision_find"

            elif action.capability == CapabilityType.VISION_COMPARE:
                observed_result = self.vision.compare(params.get("image_a", ""), params.get("image_b", ""), context=context)
                metrics.vision_used = True
                strategy_name = "vision_compare"

            elif action.capability == CapabilityType.VISION_VERIFY:
                observed_result = self.vision.verify(action.target, context=context)
                metrics.vision_used = True
                strategy_name = "vision_verify"

            elif action.capability == CapabilityType.VISION_INSPECT:
                prompt_text = params.get("prompt", action.target)
                observed_result = self.vision.inspect(prompt=prompt_text, context=context)
                metrics.vision_used = True
                strategy_name = "vision_inspect"

            # =================================================================
            # FILESYSTEM Domain
            # =================================================================
            elif action.capability == CapabilityType.FILESYSTEM_LIST:
                observed_result = self.filesystem.list(path=action.target or ".", context=context)
                strategy_name = "fs_list"

            elif action.capability == CapabilityType.FILESYSTEM_READ:
                observed_result = self.filesystem.read(action.target, context=context)
                strategy_name = "fs_read"

            elif action.capability == CapabilityType.FILESYSTEM_WRITE:
                observed_result = self.filesystem.write(action.target, params.get("content", ""), context=context)
                strategy_name = "fs_write"

            elif action.capability == CapabilityType.FILESYSTEM_CREATE:
                is_d = params.get("is_dir", False)
                cnt = params.get("content", "")
                observed_result = self.filesystem.create(action.target, is_dir=is_d, content=cnt, context=context)
                strategy_name = "fs_create"

            elif action.capability == CapabilityType.FILESYSTEM_MOVE:
                dest = params.get("destination", "")
                observed_result = self.filesystem.move(action.target, dest, context=context)
                strategy_name = "fs_move"

            elif action.capability == CapabilityType.FILESYSTEM_COPY:
                dest = params.get("destination", "")
                observed_result = self.filesystem.copy(action.target, dest, context=context)
                strategy_name = "fs_copy"

            elif action.capability == CapabilityType.FILESYSTEM_RENAME:
                new_n = params.get("new_name", "")
                observed_result = self.filesystem.rename(action.target, new_n, context=context)
                strategy_name = "fs_rename"

            elif action.capability == CapabilityType.FILESYSTEM_DELETE:
                observed_result = self.filesystem.delete(action.target, context=context)
                strategy_name = "fs_delete"

            elif action.capability == CapabilityType.FILESYSTEM_SEARCH:
                pat = params.get("pattern", "*")
                root_p = params.get("root", ".")
                observed_result = self.filesystem.search(pattern=pat, root=root_p, context=context)
                strategy_name = "fs_search"

            elif action.capability == CapabilityType.FILESYSTEM_EXISTS:
                observed_result = self.filesystem.exists(action.target, context=context)
                strategy_name = "fs_exists"

            elif action.capability == CapabilityType.FILESYSTEM_METADATA:
                observed_result = self.filesystem.metadata(action.target, context=context)
                strategy_name = "fs_metadata"

            # =================================================================
            # TERMINAL Domain
            # =================================================================
            elif action.capability == CapabilityType.TERMINAL_EXECUTE:
                observed_result = self.terminal.execute(action.target, cwd=params.get("cwd"), context=context)
                strategy_name = "terminal_execute"

            elif action.capability == CapabilityType.TERMINAL_OUTPUT:
                observed_result = self.terminal.output(context=context)
                strategy_name = "terminal_output"

            elif action.capability == CapabilityType.TERMINAL_EXIT_CODE:
                observed_result = self.terminal.exit_code(context=context)
                strategy_name = "terminal_exit_code"

            elif action.capability == CapabilityType.TERMINAL_PROCESS:
                pid = params.get("pid", 0)
                observed_result = self.terminal.process(pid=pid, context=context)
                strategy_name = "terminal_process"

            elif action.capability == CapabilityType.TERMINAL_STOP:
                pid = params.get("pid", 0)
                observed_result = self.terminal.stop(pid=pid, context=context)
                strategy_name = "terminal_stop"

            # =================================================================
            # CLIPBOARD Domain
            # =================================================================
            elif action.capability == CapabilityType.CLIPBOARD_GET:
                observed_result = self.clipboard.get(context=context)
                strategy_name = "clipboard_get"

            elif action.capability == CapabilityType.CLIPBOARD_SET:
                observed_result = self.clipboard.set(params.get("content", action.target), context=context)
                strategy_name = "clipboard_set"

            elif action.capability == CapabilityType.CLIPBOARD_CLEAR:
                observed_result = self.clipboard.clear(context=context)
                strategy_name = "clipboard_clear"

            elif action.capability == CapabilityType.CALCULATE:
                expr = str(params.get("expression") or action.target or "").strip()
                try:
                    import ast
                    import operator as op

                    # Safe mathematical AST evaluator (no arbitrary code execution)
                    operators = {
                        ast.Add: op.add,
                        ast.Sub: op.sub,
                        ast.Mult: op.mul,
                        ast.Div: op.truediv,
                        ast.FloorDiv: op.floordiv,
                        ast.Mod: op.mod,
                        ast.Pow: op.pow,
                        ast.USub: op.neg,
                        ast.UAdd: op.pos,
                    }

                    def eval_expr(node):
                        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                            return node.value
                        elif isinstance(node, ast.BinOp):
                            return operators[type(node.op)](eval_expr(node.left), eval_expr(node.right))
                        elif isinstance(node, ast.UnaryOp):
                            return operators[type(node.op)](eval_expr(node.operand))
                        else:
                            raise TypeError(f"Unsupported AST node: {type(node)}")

                    # Normalize common math terms in expression string
                    norm_expr = expr.replace("times", "*").replace("multiplied by", "*").replace("multiplied", "*").replace("plus", "+").replace("minus", "-").replace("divided by", "/").replace("divided", "/")
                    norm_expr = re.sub(r"[^0-9\+\-\*\/\(\)\.\s\%\^]", "", norm_expr).replace("^", "**")
                    parsed_ast = ast.parse(norm_expr, mode="eval")
                    calc_val = eval_expr(parsed_ast.body)
                    ans_str = str(int(calc_val)) if isinstance(calc_val, float) and calc_val.is_integer() else str(calc_val)
                    observed_result = {
                        "success": True,
                        "expression": expr,
                        "normalized_expression": norm_expr,
                        "result": calc_val,
                        "result_string": ans_str,
                        "message": f"Calculated {expr} = {ans_str}",
                    }
                except Exception as ex:
                    observed_result = {"success": False, "error": f"Failed to evaluate arithmetic expression '{expr}': {ex}"}
                strategy_name = "math_ast_eval"

            elif action.capability == CapabilityType.GENERAL_ACTION:
                err = params.get("error") or f"Could not execute action on target: {action.target}"
                observed_result = {"success": False, "error": err, "message": err}
                strategy_name = "general_action"

            else:
                observed_result = {"success": False, "error": f"Unhandled capability: {action.capability.value}"}

        except Exception as e:
            logger.exception("[COMPUTER_ENGINE] Error executing action %s: %s", action.id, e)
            observed_result = {"success": False, "error": str(e)}

        metrics.execution_latency_ms = (time.perf_counter() - t_exec_start) * 1000.0
        metrics.total_latency_ms = (time.perf_counter() - t_start) * 1000.0
        metrics.strategy_selected = strategy_name

        is_success = observed_result.get("success", False)
        status = "completed" if is_success else "failed"
        summary = observed_result.get("message") or (f"Completed {action.capability.value} successfully." if is_success else f"Failed {action.capability.value}: {observed_result.get('error')}")

        return ToolResult(
            call_id=action.id,
            name=action.capability.value,
            status=status,
            summary=summary,
            observed=observed_result,
            raw_arguments=action.parameters,
        )

    # -------------------------------------------------------------------------
    # Helper Mappings
    # -------------------------------------------------------------------------

    def _map_capability_to_domain(self, cap: CapabilityType) -> ComputerDomain:
        val = cap.value.lower()
        if val.startswith("app."):
            return ComputerDomain.APP
        elif val.startswith("window."):
            return ComputerDomain.WINDOW
        elif val.startswith("browser."):
            return ComputerDomain.BROWSER
        elif val.startswith("web."):
            return ComputerDomain.WEB
        elif val.startswith("ui."):
            return ComputerDomain.UI
        elif val.startswith("keyboard."):
            return ComputerDomain.KEYBOARD
        elif val.startswith("mouse."):
            return ComputerDomain.MOUSE
        elif val.startswith("screen."):
            return ComputerDomain.SCREEN
        elif val.startswith("vision."):
            return ComputerDomain.VISION
        elif val.startswith("filesystem."):
            return ComputerDomain.FILESYSTEM
        elif val.startswith("terminal."):
            return ComputerDomain.TERMINAL
        elif val.startswith("clipboard."):
            return ComputerDomain.CLIPBOARD
        return ComputerDomain.UI

    def _build_target_spec(self, action: Action, domain: ComputerDomain) -> TargetSpec:
        p = action.parameters or {}
        return TargetSpec(
            semantic_name=p.get("semantic_name") or action.target,
            exact_text=p.get("exact_text"),
            app_identity=p.get("app_name") or action.target,
            pid=p.get("pid"),
            hwnd=p.get("hwnd"),
            browser_name=p.get("browser"),
            tab_title=p.get("target_tab") or p.get("target") or action.target,
            url=p.get("url"),
            automation_id=p.get("automation_id"),
            control_type=p.get("control_type"),
            dom_selector=p.get("selector"),
            raw_query=action.target,
            attributes=p,
        )


COMPUTER_ENGINE = ComputerEngine()
