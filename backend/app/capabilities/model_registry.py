"""
PLUTON V2 Canonical Model-Facing Capability Registry.

Exposes strictly canonical capability tools to the LLM.
All capability tools delegate directly into COMPUTER_ENGINE,
enforcing security policies, kernel token checks, and execution tiers.
Legacy computer tools are excluded from model-facing discovery.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable
from ..security import PermissionLevel
from ..tools.base import Tool, _STRING_PROP, _schema
from ..tools.registry import ToolRegistry
from ..core.contracts import ExecutionContext
from ..kernel.control_kernel import KERNEL


def _engine():
    """Lazily obtain COMPUTER_ENGINE instance without module-load circular imports."""
    from ..subsystems.computer.engine import COMPUTER_ENGINE
    return COMPUTER_ENGINE


def _get_current_context() -> ExecutionContext:
    """Get active authorized task context or create ephemeral context."""
    active_token = getattr(KERNEL, "_active_token", None)
    active_id = active_token.task_id if (active_token and active_token.is_valid) else "ephemeral-tool-task"
    return ExecutionContext(task_id=active_id)




# -----------------------------------------------------------------------------
# Canonical Capability Handlers (Delegating to COMPUTER_ENGINE)
# -----------------------------------------------------------------------------

# --- APP DOMAIN ---
def _cap_app_launch(target: str, args: list[str] | None = None) -> dict[str, Any]:
    """Launch an application executable."""
    ctx = _get_current_context()
    return _engine().app.launch(target=target, args=args, context=ctx)

def _cap_app_close(target: str) -> dict[str, Any]:
    """Close an application executable."""
    ctx = _get_current_context()
    return _engine().app.close(target=target, context=ctx)


# --- WINDOW DOMAIN ---
def _cap_window_list(visible_only: bool = True) -> dict[str, Any]:
    """List all open desktop windows."""
    ctx = _get_current_context()
    return {"windows": _engine().window.list_windows(visible_only=visible_only, context=ctx)}


def _cap_window_focus(target: str) -> dict[str, Any]:
    """Bring a window to the foreground and focus it."""
    ctx = _get_current_context()
    return _engine().window.focus(target=target, context=ctx)

def _cap_window_minimize(target: str) -> dict[str, Any]:
    """Minimize a window."""
    ctx = _get_current_context()
    return _engine().window.minimize(target=target, context=ctx)

def _cap_window_maximize(target: str) -> dict[str, Any]:
    """Maximize a window."""
    ctx = _get_current_context()
    return _engine().window.maximize(target=target, context=ctx)

def _cap_window_restore(target: str) -> dict[str, Any]:
    """Restore a minimized or maximized window."""
    ctx = _get_current_context()
    return _engine().window.restore(target=target, context=ctx)

def _cap_window_close(target: str) -> dict[str, Any]:
    """Close a window."""
    ctx = _get_current_context()
    return _engine().window.close(target=target, context=ctx)


# --- BROWSER DOMAIN ---
def _cap_browser_list_tabs(browser: str = "Brave") -> dict[str, Any]:
    """List all open tabs in a browser."""
    ctx = _get_current_context()
    return {"tabs": _engine().browser.list_tabs(browser=browser, context=ctx)}

def _cap_browser_open_tab(url: str = "about:blank", browser: str = "Brave") -> dict[str, Any]:
    """Open a new tab in the browser."""
    ctx = _get_current_context()
    return _engine().browser.open_tab(url=url, browser=browser, context=ctx)

def _cap_browser_navigate(url: str, target_tab: str = "", browser: str = "Brave") -> dict[str, Any]:
    """Navigate to a URL in a browser tab."""
    ctx = _get_current_context()
    return _engine().browser.navigate(url=url, browser=browser, context=ctx)

def _cap_browser_switch_tab(target_tab: str, browser: str = "Brave") -> dict[str, Any]:
    """Switch to an open tab in the browser."""
    ctx = _get_current_context()
    return _engine().browser.switch_tab(target_tab=target_tab, browser=browser, context=ctx)

def _cap_browser_close_tab(target_tab: str, browser: str = "Brave") -> dict[str, Any]:
    """Close a tab in the browser."""
    ctx = _get_current_context()
    return _engine().browser.close_tab(target_tab=target_tab, browser=browser, context=ctx)

async def _cap_browser_get_state(browser: str = "Brave") -> dict[str, Any]:
    """Get active tab URL, title, and state."""
    ctx = _get_current_context()
    return await _engine().browser.get_state(context=ctx)

async def _cap_browser_read_page(browser: str = "Brave") -> dict[str, Any]:
    """Read DOM text content of the active page."""
    ctx = _get_current_context()
    return await _engine().web.inspect(context=ctx)

async def _cap_browser_click(selector: str, browser: str = "Brave") -> dict[str, Any]:
    """Click an element on the active page via CSS/XPath selector."""
    ctx = _get_current_context()
    return await _engine().web.click(target=selector, context=ctx)

async def _cap_browser_type(selector: str, text: str, browser: str = "Brave", press_enter: bool = True) -> dict[str, Any]:
    """Type text into an input field on the active page and optionally press Enter to submit."""
    ctx = _get_current_context()
    return await _engine().web.type(target=selector, text=text, press_enter=press_enter, context=ctx)

async def _cap_browser_scroll(direction: str = "down", amount: int = 300, browser: str = "Brave") -> dict[str, Any]:
    """Scroll the active browser page."""
    ctx = _get_current_context()
    return await _engine().web.scroll(direction=direction, amount=amount, context=ctx)

async def _cap_browser_search(query: str, engine: str = "", browser: str = "Brave") -> dict[str, Any]:
    """Search the web or active site (Google/YouTube) directly with query."""
    ctx = _get_current_context()
    return await _engine().browser.search(query=query, engine=engine, browser_name=browser, context=ctx)

async def _cap_browser_inspect_page(browser: str = "Brave") -> dict[str, Any]:
    """Inspect the current browser page DOM — returns URL, title, and interactive elements with CSS selectors."""
    from ..subsystems.computer.browser_engine import BROWSER_ENGINE

    result = await BROWSER_ENGINE.inspect_page(max_elements=100)
    if result.get("success"):
        return result

    return {
        "success": False,
        "error": result.get("error", f"Authoritative browser session for '{browser}' has no inspectable DOM page."),
    }


# --- UI AUTOMATION DOMAIN ---
def _cap_ui_inspect(window_query: str = "", max_depth: int = 4) -> dict[str, Any]:
    """Inspect structured controls and elements of an application window."""
    ctx = _get_current_context()
    return _engine().ui.inspect(window_query=window_query, max_depth=max_depth, context=ctx)

def _cap_ui_find(query: str, window_query: str = "") -> dict[str, Any]:
    """Find specific UI elements by name, type, or automation ID."""
    ctx = _get_current_context()
    return _engine().ui.find(query=query, window_query=window_query, context=ctx)

def _cap_ui_invoke(target_element: str, window_query: str = "") -> dict[str, Any]:
    """Invoke a button or clickable UI element."""
    ctx = _get_current_context()
    return _engine().ui.invoke(target_element=target_element, window_query=window_query, context=ctx)

def _cap_ui_set_value(target_element: str, value: str, window_query: str = "") -> dict[str, Any]:
    """Set text value of an input or edit UI element."""
    ctx = _get_current_context()
    return _engine().ui.set_value(target_element=target_element, value=value, window_query=window_query, context=ctx)

def _cap_ui_toggle(target_element: str, window_query: str = "") -> dict[str, Any]:
    """Toggle a checkbox or switch UI element."""
    ctx = _get_current_context()
    return _engine().ui.toggle(target_element=target_element, window_query=window_query, context=ctx)

def _cap_ui_select(target_element: str, window_query: str = "") -> dict[str, Any]:
    """Select a tab item, radio button, or list item."""
    ctx = _get_current_context()
    return _engine().ui.select(target_element=target_element, window_query=window_query, context=ctx)


# --- KEYBOARD DOMAIN ---
def _cap_keyboard_type(text: str, target_window: str = "") -> dict[str, Any]:
    """Type text into the active or target window."""
    ctx = _get_current_context()
    return _engine().keyboard.type(text=text, target_window=target_window, context=ctx)

def _cap_keyboard_press(key: str, target_window: str = "") -> dict[str, Any]:
    """Press a single key (e.g. Enter, Tab, Escape)."""
    ctx = _get_current_context()
    return _engine().keyboard.press(key=key, target_window=target_window, context=ctx)

def _cap_keyboard_hotkey(keys: list[str], target_window: str = "") -> dict[str, Any]:
    """Press a key combination (e.g. ['ctrl', 'a'], ['ctrl', 'c'])."""
    ctx = _get_current_context()
    return _engine().keyboard.hotkey(keys=keys, target_window=target_window, context=ctx)

def _cap_keyboard_copy() -> dict[str, Any]:
    """Execute Ctrl+C copy."""
    ctx = _get_current_context()
    return _engine().keyboard.copy(context=ctx)

def _cap_keyboard_paste() -> dict[str, Any]:
    """Execute Ctrl+V paste."""
    ctx = _get_current_context()
    return _engine().keyboard.paste(context=ctx)


# --- MOUSE DOMAIN ---
def _cap_mouse_move(x: int, y: int) -> dict[str, Any]:
    """Move mouse cursor to (x, y) coordinates."""
    ctx = _get_current_context()
    return _engine().mouse.move(x=x, y=y, context=ctx)

def _cap_mouse_click(x: int | None = None, y: int | None = None, button: str = "left") -> dict[str, Any]:
    """Click mouse button at current position or (x, y) coordinates."""
    ctx = _get_current_context()
    return _engine().mouse.click(x=x, y=y, button=button, context=ctx)

def _cap_mouse_double_click(x: int | None = None, y: int | None = None) -> dict[str, Any]:
    """Double-click mouse button."""
    ctx = _get_current_context()
    return _engine().mouse.double_click(x=x, y=y, context=ctx)

def _cap_mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int) -> dict[str, Any]:
    """Drag mouse from start to end coordinates."""
    ctx = _get_current_context()
    return _engine().mouse.drag(start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y, context=ctx)

def _cap_mouse_scroll(clicks: int = -3, x: int | None = None, y: int | None = None) -> dict[str, Any]:
    """Scroll mouse wheel vertically."""
    ctx = _get_current_context()
    return _engine().mouse.scroll(clicks=clicks, x=x, y=y, context=ctx)


# --- SCREEN & VISION DOMAIN ---
def _cap_screen_capture() -> dict[str, Any]:
    """Capture a screenshot of the desktop."""
    ctx = _get_current_context()
    return _engine().screen.capture(context=ctx)

def _cap_vision_inspect(prompt: str, image_path: str = "") -> dict[str, Any]:
    """Inspect and analyze visible UI via vision AI."""
    ctx = _get_current_context()
    return _engine().vision.inspect(prompt=prompt, image_path=image_path, context=ctx)


# --- FILESYSTEM DOMAIN ---
def _cap_filesystem_read(path: str) -> dict[str, Any]:
    """Read file content within approved workspace."""
    ctx = _get_current_context()
    return _engine().filesystem.read(path=path, context=ctx)

def _cap_filesystem_write(path: str, content: str) -> dict[str, Any]:
    """Write file content within approved workspace."""
    ctx = _get_current_context()
    return _engine().filesystem.write(path=path, content=content, context=ctx)

def _cap_filesystem_move(source_path: str, destination_path: str) -> dict[str, Any]:
    """Move or rename file within approved workspace."""
    ctx = _get_current_context()
    return _engine().filesystem.move(source_path=source_path, destination_path=destination_path, context=ctx)

def _cap_filesystem_delete(path: str) -> dict[str, Any]:
    """Delete a file within approved workspace."""
    ctx = _get_current_context()
    return _engine().filesystem.delete(path=path, context=ctx)


# --- TERMINAL DOMAIN ---
def _cap_terminal_execute(command: str, cwd: str = "") -> dict[str, Any]:
    """Execute a shell command under strict security policy."""
    ctx = _get_current_context()
    return _engine().terminal.execute(command=command, cwd=cwd, context=ctx)


# -----------------------------------------------------------------------------
# Canonical Model Tool Registry Constructor
# -----------------------------------------------------------------------------

def create_canonical_model_registry() -> ToolRegistry:
    """Create the canonical model-facing tool registry. Excludes legacy bypass tools."""
    from ..tools.web import _web_search, _web_fetch, register_web_tools
    from ..tools.memory import _memory_save, _memory_recall, register_memory_tools
    from ..tools.system import _system_info, _clock, register_system_tools

    reg = ToolRegistry()

    # 1. APP DOMAIN
    reg.register(Tool("app.launch", "Launch an application executable on desktop.", PermissionLevel.HIGH, _schema({"target": {"type": "string", "description": "Executable name or path (e.g. 'notepad.exe', 'calc.exe')"}, "args": {"type": "array", "description": "Optional arguments", "items": {"type": "string"}}}, ["target"]), _cap_app_launch))
    reg.register(Tool("app.close", "Close an application process.", PermissionLevel.HIGH, _schema({"target": {"type": "string", "description": "Process name or executable to terminate"}}, ["target"]), _cap_app_close))

    # 2. WINDOW DOMAIN
    reg.register(Tool("window.list", "List open top-level application windows.", PermissionLevel.LOW, _schema({"visible_only": {"type": "boolean", "description": "Filter visible only (default True)"}}, []), _cap_window_list))
    reg.register(Tool("window.focus", "Bring an application window to foreground.", PermissionLevel.LOW, _schema({"target": {"type": "string", "description": "Window title keyword or application name"}}, ["target"]), _cap_window_focus))
    reg.register(Tool("window.minimize", "Minimize a window.", PermissionLevel.LOW, _schema({"target": {"type": "string", "description": "Window title keyword"}}, ["target"]), _cap_window_minimize))
    reg.register(Tool("window.maximize", "Maximize a window.", PermissionLevel.LOW, _schema({"target": {"type": "string", "description": "Window title keyword"}}, ["target"]), _cap_window_maximize))
    reg.register(Tool("window.restore", "Restore a window.", PermissionLevel.LOW, _schema({"target": {"type": "string", "description": "Window title keyword"}}, ["target"]), _cap_window_restore))
    reg.register(Tool("window.close", "Close a window by title.", PermissionLevel.HIGH, _schema({"target": {"type": "string", "description": "Window title keyword"}}, ["target"]), _cap_window_close))

    # 3. BROWSER DOMAIN
    reg.register(Tool("browser.list_tabs", "List open tabs in Brave, Chrome, or Edge.", PermissionLevel.LOW, _schema({"browser": {"type": "string", "description": "Browser name: 'Brave', 'Chrome', or 'Edge'"}}, []), _cap_browser_list_tabs))
    reg.register(Tool("browser.open_tab", "Open a new browser tab with optional URL.", PermissionLevel.LOW, _schema({"url": {"type": "string", "description": "URL to open"}, "browser": {"type": "string", "description": "Browser name"}}, []), _cap_browser_open_tab))
    reg.register(Tool("browser.navigate", "Navigate a browser tab to a URL.", PermissionLevel.LOW, _schema({"url": {"type": "string", "description": "Destination URL (http/https)"}, "target_tab": {"type": "string", "description": "Optional title keyword of tab"}, "browser": {"type": "string", "description": "Browser name"}}, ["url"]), _cap_browser_navigate))
    reg.register(Tool("browser.search", "Search the web or YouTube directly for a query. Opens search results in active browser instantly.", PermissionLevel.LOW, _schema({"query": {"type": "string", "description": "Search query text (e.g. 'Minecraft', 'PLUTON AI')"}, "engine": {"type": "string", "description": "Optional search engine ('google', 'youtube')"}, "browser": {"type": "string", "description": "Browser name"}}, ["query"]), _cap_browser_search))
    reg.register(Tool("browser.switch_tab", "Switch active tab in browser by title keyword.", PermissionLevel.LOW, _schema({"target_tab": {"type": "string", "description": "Title keyword of tab to switch to"}, "browser": {"type": "string", "description": "Browser name"}}, ["target_tab"]), _cap_browser_switch_tab))
    reg.register(Tool("browser.close_tab", "Close a browser tab by title keyword.", PermissionLevel.LOW, _schema({"target_tab": {"type": "string", "description": "Title keyword of tab to close"}, "browser": {"type": "string", "description": "Browser name"}}, ["target_tab"]), _cap_browser_close_tab))
    reg.register(Tool("browser.get_state", "Get current browser URL and title.", PermissionLevel.LOW, _schema({"browser": {"type": "string", "description": "Browser name"}}, []), _cap_browser_get_state))
    reg.register(Tool("browser.read_page", "Read page text and DOM content.", PermissionLevel.LOW, _schema({"browser": {"type": "string", "description": "Browser name"}}, []), _cap_browser_read_page))
    reg.register(Tool("browser.click", "Click a web element by CSS selector.", PermissionLevel.LOW, _schema({"selector": {"type": "string", "description": "CSS selector to click"}, "browser": {"type": "string", "description": "Browser name"}}, ["selector"]), _cap_browser_click))
    reg.register(Tool("browser.type", "Type text into a web element and optionally press Enter to submit search.", PermissionLevel.LOW, _schema({"selector": {"type": "string", "description": "CSS selector of input"}, "text": {"type": "string", "description": "Text to enter"}, "press_enter": {"type": "boolean", "description": "Whether to press Enter after typing (default true)"}, "browser": {"type": "string", "description": "Browser name"}}, ["selector", "text"]), _cap_browser_type))
    reg.register(Tool("browser.scroll", "Scroll the webpage.", PermissionLevel.LOW, _schema({"direction": {"type": "string", "description": "'up' or 'down'"}, "amount": {"type": "integer", "description": "Pixel scroll amount"}, "browser": {"type": "string", "description": "Browser name"}}, []), _cap_browser_scroll))
    reg.register(Tool("browser.inspect_page", "Inspect the current browser page: returns URL, title, and interactive DOM elements (inputs, buttons, links, textareas, selects) with CSS selectors. Use this after navigating to understand page structure before interacting with elements.", PermissionLevel.LOW, _schema({"browser": {"type": "string", "description": "Browser name: 'Brave', 'Chrome', or 'Edge'"}}, []), _cap_browser_inspect_page))

    # 4. UI AUTOMATION DOMAIN
    reg.register(Tool("ui.inspect", "Inspect structured UI controls of a window.", PermissionLevel.LOW, _schema({"window_query": {"type": "string", "description": "Window title keyword"}, "max_depth": {"type": "integer", "description": "Max inspection depth"}}, []), _cap_ui_inspect))
    reg.register(Tool("ui.find", "Find specific UI element in window.", PermissionLevel.LOW, _schema({"query": {"type": "string", "description": "Element name or label"}, "window_query": {"type": "string", "description": "Window title keyword"}}, ["query"]), _cap_ui_find))
    reg.register(Tool("ui.invoke", "Invoke/click a UI button or control.", PermissionLevel.MEDIUM, _schema({"target_element": {"type": "string", "description": "Name or label of button"}, "window_query": {"type": "string", "description": "Window title keyword"}}, ["target_element"]), _cap_ui_invoke))
    reg.register(Tool("ui.set_value", "Set text in a UI edit field.", PermissionLevel.MEDIUM, _schema({"target_element": {"type": "string", "description": "Name or label of text field"}, "value": {"type": "string", "description": "Text to set"}, "window_query": {"type": "string", "description": "Window title keyword"}}, ["target_element", "value"]), _cap_ui_set_value))
    reg.register(Tool("ui.toggle", "Toggle a UI checkbox or switch.", PermissionLevel.MEDIUM, _schema({"target_element": {"type": "string", "description": "Name of checkbox"}, "window_query": {"type": "string", "description": "Window title keyword"}}, ["target_element"]), _cap_ui_toggle))
    reg.register(Tool("ui.select", "Select a UI tab or item.", PermissionLevel.MEDIUM, _schema({"target_element": {"type": "string", "description": "Name of tab or item"}, "window_query": {"type": "string", "description": "Window title keyword"}}, ["target_element"]), _cap_ui_select))

    # 5. KEYBOARD DOMAIN
    reg.register(Tool("keyboard.type", "Type text into active or target window.", PermissionLevel.LOW, _schema({"text": {"type": "string", "description": "Text string to type"}, "target_window": {"type": "string", "description": "Optional window title keyword"}}, ["text"]), _cap_keyboard_type))
    reg.register(Tool("keyboard.press", "Press a single key (Enter, Tab, Escape).", PermissionLevel.LOW, _schema({"key": {"type": "string", "description": "Key name"}, "target_window": {"type": "string", "description": "Optional window title keyword"}}, ["key"]), _cap_keyboard_press))
    reg.register(Tool("keyboard.hotkey", "Press key combination (e.g. ['ctrl', 'a']).", PermissionLevel.LOW, _schema({"keys": {"type": "array", "description": "List of key names", "items": {"type": "string"}}, "target_window": {"type": "string", "description": "Optional window title keyword"}}, ["keys"]), _cap_keyboard_hotkey))
    reg.register(Tool("keyboard.copy", "Trigger copy (Ctrl+C).", PermissionLevel.LOW, _schema({}, []), _cap_keyboard_copy))
    reg.register(Tool("keyboard.paste", "Trigger paste (Ctrl+V).", PermissionLevel.LOW, _schema({}, []), _cap_keyboard_paste))

    # 6. MOUSE DOMAIN
    reg.register(Tool("mouse.move", "Move mouse cursor to (x, y) coordinates.", PermissionLevel.LOW, _schema({"x": {"type": "integer", "description": "X pixel coordinate"}, "y": {"type": "integer", "description": "Y pixel coordinate"}}, ["x", "y"]), _cap_mouse_move))
    reg.register(Tool("mouse.click", "Click mouse at (x, y) coordinates.", PermissionLevel.LOW, _schema({"x": {"type": "integer", "description": "Optional X coordinate"}, "y": {"type": "integer", "description": "Optional Y coordinate"}, "button": {"type": "string", "description": "'left', 'right', or 'middle'"}}, []), _cap_mouse_click))
    reg.register(Tool("mouse.double_click", "Double-click mouse.", PermissionLevel.LOW, _schema({"x": {"type": "integer", "description": "Optional X coordinate"}, "y": {"type": "integer", "description": "Optional Y coordinate"}}, []), _cap_mouse_double_click))
    reg.register(Tool("mouse.drag", "Drag mouse from start to end coordinates.", PermissionLevel.LOW, _schema({"start_x": {"type": "integer"}, "start_y": {"type": "integer"}, "end_x": {"type": "integer"}, "end_y": {"type": "integer"}}, ["start_x", "start_y", "end_x", "end_y"]), _cap_mouse_drag))
    reg.register(Tool("mouse.scroll", "Scroll mouse wheel.", PermissionLevel.LOW, _schema({"clicks": {"type": "integer", "description": "Scroll ticks (negative=down, positive=up)"}, "x": {"type": "integer"}, "y": {"type": "integer"}}, []), _cap_mouse_scroll))

    # 7. SCREEN & VISION DOMAIN
    reg.register(Tool("screen.capture", "Capture screenshot of desktop.", PermissionLevel.LOW, _schema({}, []), _cap_screen_capture))
    reg.register(Tool("vision.inspect", "Visually inspect screen with AI.", PermissionLevel.LOW, _schema({"prompt": {"type": "string", "description": "Inspection query"}, "image_path": {"type": "string", "description": "Optional screenshot path"}}, ["prompt"]), _cap_vision_inspect))

    # 8. FILESYSTEM DOMAIN
    reg.register(Tool("filesystem.read", "Read file content in workspace.", PermissionLevel.LOW, _schema({"path": {"type": "string", "description": "File path"}}, ["path"]), _cap_filesystem_read))
    reg.register(Tool("filesystem.write", "Write content to file in workspace.", PermissionLevel.LOW, _schema({"path": {"type": "string", "description": "File path"}, "content": {"type": "string", "description": "Text content"}}, ["path", "content"]), _cap_filesystem_write))
    reg.register(Tool("filesystem.move", "Move/rename file in workspace.", PermissionLevel.LOW, _schema({"source_path": {"type": "string"}, "destination_path": {"type": "string"}}, ["source_path", "destination_path"]), _cap_filesystem_move))
    reg.register(Tool("filesystem.delete", "Delete file in workspace.", PermissionLevel.MEDIUM, _schema({"path": {"type": "string", "description": "File path to delete"}}, ["path"]), _cap_filesystem_delete))

    # 9. TERMINAL DOMAIN
    reg.register(Tool("terminal.execute", "Execute shell command under safety policy.", PermissionLevel.HIGH, _schema({"command": {"type": "string", "description": "Command string to run"}, "cwd": {"type": "string", "description": "Optional working directory"}}, ["command"]), _cap_terminal_execute))

    # 10. WEB, MEMORY & SYSTEM TOOLS
    register_web_tools(reg)
    register_memory_tools(reg)
    register_system_tools(reg)

    return reg


CANONICAL_MODEL_REGISTRY: ToolRegistry = create_canonical_model_registry()
