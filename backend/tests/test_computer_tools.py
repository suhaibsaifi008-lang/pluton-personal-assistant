import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.database import SessionLocal, migrate
from app.models import Activity, Task
from app.security import PermissionLevel, requires_confirmation
from app.tool_executor import ToolExecutionResult, ToolExecutor
from app.tools import TOOLS, ToolRegistry
from app.tools import computer as computer_module
from app.tools.computer import (
    _get_active_window,
    _get_screen_size,
    _hotkey,
    _key_press,
    _keyboard_type,
    _launch_app,
    _mouse_click,
    _mouse_move,
    _screenshot,
    _scroll,
    register_computer_tools,
)


def setup_function():
    migrate()


# ---------------------------------------------------------------------------
# 1. Registration & Schema Tests
# ---------------------------------------------------------------------------

def test_all_computer_tools_registered_in_default_tools():
    expected_tools = {
        "computer.screenshot": PermissionLevel.LOW,
        "computer.inspect_screen": PermissionLevel.LOW,
        "computer.locate_element": PermissionLevel.LOW,
        "computer.verify_screen_change": PermissionLevel.LOW,
        "computer.gui_action_workflow": PermissionLevel.MEDIUM,
        "computer.get_active_window": PermissionLevel.LOW,
        "computer.mouse_move": PermissionLevel.LOW,
        "computer.scroll": PermissionLevel.LOW,
        "computer.mouse_click": PermissionLevel.MEDIUM,
        "computer.keyboard_type": PermissionLevel.MEDIUM,
        "computer.key_press": PermissionLevel.MEDIUM,
        "computer.hotkey": PermissionLevel.HIGH,
        "computer.launch_app": PermissionLevel.HIGH,
        "computer.close_browser_tab": PermissionLevel.MEDIUM,
    }
    for name, expected_perm in expected_tools.items():
        tool = TOOLS.get(name)
        assert tool is not None, f"Expected {name} to be in TOOLS"
        assert tool.permission == expected_perm, f"Expected {name} to have permission {expected_perm}"
        assert tool.input_schema.get("type") == "object"
        assert callable(tool.execute)


def test_computer_tools_custom_registry():
    custom_reg = ToolRegistry()
    register_computer_tools(custom_reg)
    assert len(custom_reg) == 21
    assert custom_reg.contains("computer.screenshot")
    assert custom_reg.contains("computer.inspect_screen")
    assert custom_reg.contains("computer.locate_element")
    assert custom_reg.contains("computer.gui_action_workflow")
    assert custom_reg.contains("computer.close_browser_tab")
    assert custom_reg.contains("computer.launch_app")
    assert custom_reg.contains("computer.list_windows")
    assert custom_reg.contains("computer.ui_action")






# ---------------------------------------------------------------------------
# 2. Screenshot Tests
# ---------------------------------------------------------------------------

def test_screenshot_success(tmp_path, monkeypatch):
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: tmp_path)

    fake_img = MagicMock()
    fake_img.size = (1920, 1080)
    fake_img.getextrema.return_value = ((0, 255), (0, 255), (0, 255))
    monkeypatch.setattr(computer_module, "_capture_screen_image_with_diag", lambda: (fake_img, {"successful_method": "mock"}))

    result = _screenshot()
    assert result.get("captured") is True
    assert result.get("width") == 1920
    assert result.get("height") == 1080
    assert "timestamp" in result
    assert result.get("path")
    assert fake_img.save.called


def test_screenshot_handles_failure(monkeypatch):
    def failing_screenshot():
        raise RuntimeError("Display device unavailable")

    monkeypatch.setattr(computer_module, "_capture_screen_image_with_diag", failing_screenshot)
    result = _screenshot()
    assert "error" in result
    assert "Display device unavailable" in result["error"]




# ---------------------------------------------------------------------------
# 3. Active Window Tests
# ---------------------------------------------------------------------------

def test_get_active_window_success(monkeypatch):
    fake_win = MagicMock()
    fake_win.title = "Visual Studio Code - PLUTON"
    fake_win.left = 100
    fake_win.top = 50
    fake_win.width = 1200
    fake_win.height = 800
    monkeypatch.setattr(computer_module.pyautogui, "getActiveWindow", lambda: fake_win)

    result = _get_active_window()
    assert result.get("active") is True
    assert result.get("title") == "Visual Studio Code - PLUTON"
    assert result.get("left") == 100
    assert result.get("top") == 50
    assert result.get("width") == 1200
    assert result.get("height") == 800


def test_get_active_window_none(monkeypatch):
    monkeypatch.setattr(computer_module.pyautogui, "getActiveWindow", lambda: None)
    monkeypatch.setattr(computer_module, "_attach_interactive_desktop", lambda: False)
    if hasattr(computer_module, "ctypes"):
        monkeypatch.setattr(computer_module.ctypes.windll.user32, "GetForegroundWindow", lambda: 0)
    result = _get_active_window()
    assert result.get("active") is False
    assert result.get("title") == ""


def test_get_active_window_handles_failure(monkeypatch):
    def failing_active_window():
        raise OSError("Window query failed")

    monkeypatch.setattr(computer_module.pyautogui, "getActiveWindow", failing_active_window)
    monkeypatch.setattr(computer_module, "_attach_interactive_desktop", lambda: False)
    if hasattr(computer_module, "ctypes"):
        monkeypatch.setattr(computer_module.ctypes.windll.user32, "GetForegroundWindow", lambda: 0)
    result = _get_active_window()
    assert result.get("active") is False or "error" in result


# ---------------------------------------------------------------------------
# 4. Mouse Move Tests
# ---------------------------------------------------------------------------

def test_mouse_move_success(monkeypatch):
    moved = []
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "moveTo", lambda x, y: moved.append((x, y)))

    result = _mouse_move(500, 300)
    assert result.get("moved") is True
    assert result.get("x") == 500
    assert result.get("y") == 300
    assert moved == [(500, 300)]


def test_mouse_move_out_of_bounds(monkeypatch):
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))

    assert "error" in _mouse_move(-10, 500)
    assert "error" in _mouse_move(500, -1)
    assert "error" in _mouse_move(2000, 500)
    assert "error" in _mouse_move(500, 1200)


def test_mouse_move_handles_failure(monkeypatch):
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module, "_native_mouse_move", lambda *a, **k: False)
    monkeypatch.setattr(
        computer_module.pyautogui,
        "moveTo",
        MagicMock(side_effect=RuntimeError("pyautogui failsafe triggered")),
    )
    result = _mouse_move(100, 100)
    assert "error" in result
    assert "Failed to move mouse" in result["error"] or "failsafe" in result["error"]



# ---------------------------------------------------------------------------
# 5. Mouse Click Tests
# ---------------------------------------------------------------------------

def test_mouse_click_success(monkeypatch):
    clicked = []
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(
        computer_module.pyautogui,
        "click",
        lambda x, y, button, clicks: clicked.append((x, y, button, clicks)),
    )

    result = _mouse_click(400, 250, button="left", clicks=1)
    assert result.get("clicked") is True
    assert result.get("x") == 400
    assert result.get("y") == 250
    assert result.get("button") == "left"
    assert clicked == [(400, 250, "left", 1)]


def test_mouse_click_double_click(monkeypatch):
    clicked = []
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(
        computer_module.pyautogui,
        "click",
        lambda x, y, button, clicks: clicked.append((x, y, button, clicks)),
    )

    result = _mouse_click(100, 100, button="right", clicks=2)
    assert result.get("clicked") is True
    assert result.get("button") == "right"
    assert result.get("clicks") == 2
    assert clicked == [(100, 100, "right", 2)]


def test_mouse_click_invalid_inputs(monkeypatch):
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))

    assert "error" in _mouse_click(-1, 100)
    assert "error" in _mouse_click(100, 100, button="invalid")
    assert "error" in _mouse_click(100, 100, clicks=5)


# ---------------------------------------------------------------------------
# 6. Scroll Tests
# ---------------------------------------------------------------------------

def test_scroll_success(monkeypatch):
    scrolled = []
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "scroll", lambda clicks, **kw: scrolled.append((clicks, kw)))

    result = _scroll(-5)
    assert result.get("scrolled") is True
    assert result.get("clicks") == -5

    result2 = _scroll(3, x=200, y=300)
    assert result2.get("scrolled") is True
    assert result2.get("clicks") == 3
    assert len(scrolled) == 2


def test_scroll_out_of_bounds(monkeypatch):
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    assert "error" in _scroll(5, x=-10, y=100)
    assert "error" in _scroll(5, x=100, y=2000)


# ---------------------------------------------------------------------------
# 7. Keyboard Type Tests
# ---------------------------------------------------------------------------

def test_keyboard_type_success(monkeypatch):
    typed = []
    monkeypatch.setattr(computer_module.pyautogui, "write", lambda text, interval: typed.append((text, interval)))

    result = _keyboard_type("Hello PLUTON", interval=0.01)
    assert result.get("typed") is True
    assert result.get("typed_length") == len("Hello PLUTON")
    assert typed == [("Hello PLUTON", 0.01)]


def test_keyboard_type_invalid(monkeypatch):
    assert "error" in _keyboard_type("")
    assert "error" in _keyboard_type("hello", interval=-0.5)
    assert "error" in _keyboard_type("hello", interval=5.0)


# ---------------------------------------------------------------------------
# 8. Key Press Tests
# ---------------------------------------------------------------------------

def test_key_press_success(monkeypatch):
    pressed = []
    monkeypatch.setattr(computer_module.pyautogui, "press", lambda key: pressed.append(key))

    result = _key_press("enter")
    assert result.get("pressed") is True
    assert result.get("key") == "enter"
    assert pressed == ["enter"]


def test_key_press_empty():
    assert "error" in _key_press("")
    assert "error" in _key_press("   ")


def test_key_press_denies_disruptive_power_keys():
    for k in ["power", "sleep", "wakeup"]:
        res = _key_press(k)
        assert res.get("denied") is True
        assert "disruptive" in res.get("reason", "")


# ---------------------------------------------------------------------------
# 9. Hotkey / Shortcut Tests
# ---------------------------------------------------------------------------

def test_hotkey_success(monkeypatch):
    hotkeyed = []
    monkeypatch.setattr(computer_module.pyautogui, "hotkey", lambda *keys: hotkeyed.append(keys))

    result = _hotkey(["ctrl", "s"])
    assert result.get("pressed") is True
    assert result.get("keys") == ["ctrl", "s"]
    assert hotkeyed == [("ctrl", "s")]


def test_hotkey_blocks_dangerous_combinations():
    dangerous = [
        ["ctrl", "alt", "delete"],
        ["ctrl", "alt", "del"],
        ["alt", "f4"],
        ["win", "l"],
        ["ctrl", "shift", "escape"],
        ["ctrl", "shift", "delete"],
        ["win", "x"],
    ]
    for combo in dangerous:
        res = _hotkey(combo)
        assert res.get("denied") is True, f"Expected {combo} to be denied"
        assert "dangerous" in res.get("reason", "").lower() or "blocked" in res.get("reason", "").lower()


def test_hotkey_empty():
    assert "error" in _hotkey([])
    assert "error" in _hotkey(["", "  "])


# ---------------------------------------------------------------------------
# 10. Launch App Tests
# ---------------------------------------------------------------------------

def test_launch_app_success(monkeypatch):
    fake_proc = MagicMock()
    fake_proc.pid = 98765
    launched_cmd = []
    monkeypatch.setattr(computer_module.subprocess, "Popen", lambda cmd, **kw: launched_cmd.append(cmd) or fake_proc)

    result = _launch_app("notepad.exe", args=["test.txt"])
    assert result.get("launched") is True
    assert result.get("target") == "notepad.exe"
    assert result.get("pid") == 98765
    assert launched_cmd == [["notepad.exe", "test.txt"]]


def test_launch_app_denies_shell_bypass():
    denied_targets = ["powershell.exe", "powershell", "pwsh.exe", "pwsh", "cmd.exe", "cmd", "bash", "wscript", "cscript"]
    for target in denied_targets:
        res = _launch_app(target)
        assert res.get("denied") is True, f"Expected {target} to be denied"
        assert "blocks shell" in res.get("reason", "").lower()


def test_launch_app_empty():
    assert "error" in _launch_app("")


def test_launch_app_file_not_found(monkeypatch):
    def missing_app(*args, **kw):
        raise FileNotFoundError("App not found")

    monkeypatch.setattr(computer_module.subprocess, "Popen", missing_app)
    result = _launch_app("nonexistent_binary.exe")
    assert "error" in result
    assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# 11. ToolExecutor Integration Tests
# ---------------------------------------------------------------------------

def test_toolexecutor_runs_computer_screenshot(tmp_path, monkeypatch):
    db = SessionLocal()
    task = Task(title="test", request="take screenshot", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: tmp_path)
    fake_img = MagicMock()
    fake_img.size = (1920, 1080)
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: fake_img)

    reg = ToolRegistry()
    register_computer_tools(reg)
    executor = ToolExecutor(reg)

    res, (ev_name, ev_data) = asyncio.run(
        executor.execute_call(db, task.id, "computer.screenshot", "call_ss", {}, approved=True)
    )

    assert isinstance(res, ToolExecutionResult)
    assert res.status == "completed"
    assert res.observed.get("captured") is True
    assert ev_name == "activity"
    assert ev_data["status"] == "completed"

    activities = db.scalars(select(Activity).where(Activity.task_id == task.id)).all()
    assert len(activities) == 1
    assert activities[0].name == "computer.screenshot"
    assert activities[0].status == "completed"

    db.close()


def test_toolexecutor_denies_high_risk_launch_app_when_unapproved():
    db = SessionLocal()
    task = Task(title="test", request="launch app", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    reg = ToolRegistry()
    register_computer_tools(reg)
    executor = ToolExecutor(reg)

    res, (ev_name, ev_data) = asyncio.run(
        executor.execute_call(
            db, task.id, "computer.launch_app", "call_launch", {"target": "calc.exe"}, approved=False
        )
    )

    assert res.status == "denied"
    assert res.observed.get("denied") is True
    assert ev_data["status"] == "denied"
    assert "Denied by user" in res.summary

    activities = db.scalars(select(Activity).where(Activity.task_id == task.id)).all()
    assert len(activities) == 1
    assert activities[0].name == "computer.launch_app"
    assert activities[0].status == "denied"

    db.close()


def test_toolexecutor_validates_computer_tool_arguments():
    db = SessionLocal()
    task = Task(title="test", request="test req", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    reg = ToolRegistry()
    register_computer_tools(reg)
    executor = ToolExecutor(reg)

    # Missing required argument 'x' in mouse_move
    res, _ = asyncio.run(
        executor.execute_call(db, task.id, "computer.mouse_move", "call_inv", {"y": 100}, approved=True)
    )
    assert res.status == "failed"
    assert "Missing required argument: 'x'" in res.observed.get("error", "")

    # Wrong type in mouse_move
    res2, _ = asyncio.run(
        executor.execute_call(db, task.id, "computer.mouse_move", "call_inv2", {"x": "not_an_int", "y": 100}, approved=True)
    )
    assert res2.status == "failed"
    assert "must be of type integer" in res2.observed.get("error", "")

    db.close()



# ---------------------------------------------------------------------------
# 12. Security & Confirmation Tests
# ---------------------------------------------------------------------------

def test_high_risk_computer_tools_require_confirmation():
    assert requires_confirmation(TOOLS["computer.hotkey"].permission)
    assert requires_confirmation(TOOLS["computer.launch_app"].permission)
    assert not requires_confirmation(TOOLS["computer.screenshot"].permission)
    assert not requires_confirmation(TOOLS["computer.get_active_window"].permission)
    assert not requires_confirmation(TOOLS["computer.mouse_move"].permission)
    assert not requires_confirmation(TOOLS["computer.scroll"].permission)
    assert not requires_confirmation(TOOLS["computer.mouse_click"].permission)
    assert not requires_confirmation(TOOLS["computer.keyboard_type"].permission)
    assert not requires_confirmation(TOOLS["computer.key_press"].permission)


def test_screenshot_fallback_when_pyautogui_fails(monkeypatch, tmp_path):
    from PIL import Image
    import pyautogui
    from app.tools.computer import _screenshot, _capture_screen_image

    # Simulate PyAutoGUI and ImageGrab raising OSError
    def fail_screenshot(*args, **kwargs):
        raise OSError("screen grab failed")

    monkeypatch.setattr(pyautogui, "screenshot", fail_screenshot)
    monkeypatch.setattr("PIL.ImageGrab.grab", fail_screenshot)

    img = _capture_screen_image()
    assert isinstance(img, Image.Image)
    assert img.size[0] > 0
    assert img.size[1] > 0

    res = _screenshot()
    assert res.get("captured") is True
    assert "path" in res
    assert Path(res["path"]).is_file()
    assert Path(res["path"]).stat().st_size > 0

    # Ensure the saved file can be cleanly opened by PIL
    opened = Image.open(res["path"])
    assert opened.size == (res["width"], res["height"])

