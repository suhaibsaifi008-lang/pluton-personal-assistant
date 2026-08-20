import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.agent import AgentEngine
from app.database import SessionLocal, migrate
from app.models import Activity, Task, TaskStatus
from app.providers import AIProvider, ProviderEvent, ProviderRequest, ProviderResponse, ToolCall
from app.security import PermissionLevel, requires_confirmation
from app.tool_executor import ToolExecutionResult, ToolExecutor
from app.tools import TOOLS, ToolRegistry
from app.tools import computer as computer_module
from app.tools.computer import (
    _gui_action_workflow,
    _locate_element,
    _mouse_click,
    register_computer_tools,
)


def setup_function():
    migrate()


@pytest.fixture
def sample_image(tmp_path):
    img_file = tmp_path / "test_screen.png"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x03\x00\x08\xfc\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
    img_file.write_bytes(png_bytes)
    return img_file


class FakeScriptedProvider(AIProvider):
    name = "scripted_vision"

    def __init__(self, turns):
        self.turns = list(turns)
        self.recorded_requests: list[ProviderRequest] = []

    @property
    def model(self) -> str:
        return "scripted-vision-model"

    @property
    def supports_vision(self) -> bool:
        return True

    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        self.recorded_requests.append(request)
        if self.turns:
            turn = self.turns.pop(0)
            if isinstance(turn, str):
                return ProviderResponse(response_id="resp_text", text=turn)
            elif isinstance(turn, tuple):
                calls, resp_id = turn
                return ProviderResponse(response_id=resp_id, text="", tool_calls=calls)
        return ProviderResponse(response_id="resp_empty", text="Done.")

    async def stream_respond(self, request: ProviderRequest):
        self.recorded_requests.append(request)
        if not self.turns:
            yield ProviderEvent(kind="text_delta", text="Default completion.")
            yield ProviderEvent(kind="tool_calls", tool_calls=[], response_id="resp_fin")
            return

        turn = self.turns.pop(0)
        if isinstance(turn, str):
            yield ProviderEvent(kind="text_delta", text=turn)
            yield ProviderEvent(kind="tool_calls", tool_calls=[], response_id="resp_final")
        else:
            calls, response_id = turn
            yield ProviderEvent(kind="tool_calls", tool_calls=calls, response_id=response_id)


async def collect_events(async_gen):
    return [(event, data) async for event, data in async_gen]


def create_test_task(prompt: str = "Test prompt"):
    db = SessionLocal()
    task = Task(title="gui_test", request=prompt, status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)
    task_id = task.id
    db.close()
    return task_id


# ---------------------------------------------------------------------------
# 1. Autonomous GUI Action Workflow Tool Unit Tests
# ---------------------------------------------------------------------------

from PIL import Image

def test_gui_action_workflow_successful_click(sample_image, monkeypatch):
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))


    clicked_coords = []
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda x, y, button, clicks: clicked_coords.append((x, y, button, clicks)))

    # Locate response (pixel: 480, 270) + Verification response
    locate_json = json.dumps({"found": True, "point": [250, 250], "label": "Save Button", "confidence": 0.95})
    verify_json = json.dumps({"verified": True, "explanation": "File saved banner appeared."})

    fake_provider = FakeScriptedProvider([locate_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _gui_action_workflow(
        target_element="Save Button",
        action="click",
        expected_change="File saved banner appears",
    )

    assert result.get("success") is True
    assert result.get("x") == 480
    assert result.get("y") == 270
    assert clicked_coords == [(480, 270, "left", 1)]
    assert result.get("verification", {}).get("verified") is True


def test_gui_action_workflow_type_action(sample_image, monkeypatch):
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))

    clicked = []
    typed = []
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda x, y, button, clicks: clicked.append((x, y)))
    monkeypatch.setattr(computer_module.pyautogui, "write", lambda text, interval: typed.append((text, interval)))

    locate_json = json.dumps({"found": True, "point": [500, 300], "label": "Search Input"})
    fake_provider = FakeScriptedProvider([locate_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _gui_action_workflow(
        target_element="Search Input",
        action="type",
        text_to_type="PLUTON AI",
    )

    assert result.get("success") is True
    # 500/1000 * 1920 = 960, 300/1000 * 1080 = 324
    assert clicked == [(960, 324)]
    assert typed == [("PLUTON AI", 0.0)]


def test_gui_action_workflow_retry_on_initial_failure(sample_image, monkeypatch):
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda *a, **k: None)

    # Attempt 1: not found -> Attempt 2: found
    not_found_json = json.dumps({"found": False, "reason": "Element obscured."})
    found_json = json.dumps({"found": True, "point": [200, 400], "label": "Submit Button"})

    fake_provider = FakeScriptedProvider([not_found_json, found_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _gui_action_workflow(
        target_element="Submit Button",
        action="click",
        retries=1,
    )

    assert result.get("success") is True
    # 200/1000 * 1920 = 384, 400/1000 * 1080 = 432
    assert result.get("x") == 384
    assert result.get("y") == 432



def test_gui_action_workflow_locate_exhausts_retries_returns_failure(sample_image, monkeypatch):
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1000, 1000)))

    not_found_json = json.dumps({"found": False, "reason": "Element not visible anywhere on screen."})
    fake_provider = FakeScriptedProvider([not_found_json, not_found_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)


    result = _gui_action_workflow(
        target_element="Missing Button",
        retries=1,
    )

    assert result.get("success") is False
    assert result.get("failed_step") == "locate"
    assert "not visible" in result.get("reason", "")


def test_gui_action_workflow_invalid_arguments():
    assert "error" in _gui_action_workflow("")
    assert "error" in _gui_action_workflow("Button", action="invalid_action")
    assert "error" in _gui_action_workflow("Input", action="type", text_to_type="")


# ---------------------------------------------------------------------------
# 2. Agent Multi-Step GUI Planner & Verification Loop Tests
# ---------------------------------------------------------------------------

def test_agent_executes_multi_step_gui_locate_click_verify_flow(sample_image, monkeypatch):
    """Test full planner loop:
    Turn 1: Agent calls locate_element
    Turn 2: Agent calls mouse_click at coordinates
    Turn 3: Agent calls verify_screen_change
    Turn 4: Agent completes task with summary
    """
    task_id = create_test_task("Click the Settings button and verify it opened.")

    locate_call = ToolCall(call_id="c_loc", name="computer.locate_element", arguments={"element_description": "Settings button", "image_path": str(sample_image)})
    click_call = ToolCall(call_id="c_clk", name="computer.mouse_click", arguments={"x": 500, "y": 300, "button": "left", "clicks": 1})
    verify_call = ToolCall(call_id="c_ver", name="computer.verify_screen_change", arguments={"expected_change": "Settings panel opened", "before_image_path": str(sample_image), "after_image_path": str(sample_image)})

    fake_agent_provider = FakeScriptedProvider([
        ([locate_call], "resp_1"),
        ([click_call], "resp_2"),
        ([verify_call], "resp_3"),
        "Successfully opened Settings and verified the panel is open.",
    ])

    # Mock tool underlying vision calls
    locate_json = json.dumps({"found": True, "point": [500, 300], "label": "Settings button"})
    verify_json = json.dumps({"verified": True, "explanation": "Settings panel visible."})
    fake_vision_provider = FakeScriptedProvider([locate_json, verify_json])

    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda *a, **k: None)

    engine = AgentEngine(provider=fake_agent_provider)
    events = asyncio.run(collect_events(engine.run(task_id)))

    # Verify all tool activities recorded in order
    activity_names = [data["name"] for ev, data in events if ev == "activity" and data.get("status") == "completed"]
    assert "computer.locate_element" in activity_names
    assert "computer.mouse_click" in activity_names
    assert "computer.verify_screen_change" in activity_names

    # Verify done event
    done_event = [data for ev, data in events if ev == "done"][0]
    assert done_event["status"] == "COMPLETED"
    assert "Successfully opened Settings" in done_event["message"]


def test_agent_recovers_when_locate_fails_and_adapts(sample_image, monkeypatch):
    """Test planner resilience:
    Turn 1: Agent calls locate_element with specific text -> not found
    Turn 2: Agent calls inspect_screen to analyze UI layout
    Turn 3: Agent calls locate_element with broader description -> found!
    Turn 4: Agent clicks and completes
    """
    task_id = create_test_task("Find the Submit button and click it.")

    call_loc_fail = ToolCall(call_id="c_f", name="computer.locate_element", arguments={"element_description": "Small Submit Button", "image_path": str(sample_image)})
    call_inspect = ToolCall(call_id="c_insp", name="computer.inspect_screen", arguments={"prompt": "Where is the main action button?", "image_path": str(sample_image)})
    call_loc_success = ToolCall(call_id="c_s", name="computer.locate_element", arguments={"element_description": "Primary Blue Action Button", "image_path": str(sample_image)})
    call_click = ToolCall(call_id="c_clk", name="computer.mouse_click", arguments={"x": 800, "y": 900})

    fake_agent_provider = FakeScriptedProvider([
        ([call_loc_fail], "resp_1"),
        ([call_inspect], "resp_2"),
        ([call_loc_success], "resp_3"),
        ([call_click], "resp_4"),
        "Located the button as 'Primary Blue Action Button' and clicked it.",
    ])

    not_found_json = json.dumps({"found": False, "reason": "No text matching 'Small Submit Button'."})
    inspect_text = "The page has a 'Primary Blue Action Button' at bottom right."
    found_json = json.dumps({"found": True, "point": [800, 900], "label": "Primary Blue Action Button"})

    fake_vision_provider = FakeScriptedProvider([not_found_json, inspect_text, found_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda *a, **k: None)

    engine = AgentEngine(provider=fake_agent_provider)
    events = asyncio.run(collect_events(engine.run(task_id)))

    done_event = [data for ev, data in events if ev == "done"][0]
    assert done_event["status"] == "COMPLETED"
    assert "Located the button" in done_event["message"]


def test_agent_pauses_for_confirmation_on_high_risk_in_gui_chain(sample_image, monkeypatch):
    """Test that vision tools identifying elements does NOT bypass high-risk confirmation."""
    task_id = create_test_task("Find the close button and send Alt+F4 / launch an external app.")

    loc_call = ToolCall(call_id="c_loc", name="computer.locate_element", arguments={"element_description": "App window", "image_path": str(sample_image)})
    launch_call = ToolCall(call_id="c_launch", name="computer.launch_app", arguments={"target": "notepad.exe"})

    fake_agent_provider = FakeScriptedProvider([
        ([loc_call], "resp_1"),
        ([launch_call], "resp_2"),
        "App launched after approval.",
    ])

    locate_json = json.dumps({"found": True, "point": [100, 100], "label": "App window"})
    fake_vision_provider = FakeScriptedProvider([locate_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))

    engine = AgentEngine(provider=fake_agent_provider)
    events = asyncio.run(collect_events(engine.run(task_id)))

    # Locate executed safely
    loc_activities = [d for ev, d in events if ev == "activity" and d.get("name") == "computer.locate_element"]
    assert len(loc_activities) == 1

    # High-risk launch_app triggered confirmation and paused
    confirmation = [d for ev, d in events if ev == "confirmation"][0]
    assert confirmation["confirmations"][0]["name"] == "computer.launch_app"
    assert confirmation["confirmations"][0]["permission"] == "high"

    db = SessionLocal()
    paused_task = db.get(Task, task_id)
    assert paused_task.status == TaskStatus.CONFIRMING.value
    db.close()


def test_agent_handles_browser_tab_close_gui_request(sample_image, monkeypatch):
    """Test reproduction of: 'close the Claude tab on my Brave browser'
    Verifies agent invokes visual element location and click instead of text refusal.
    """
    task_id = create_test_task("close the Claude tab on my Brave browser")

    locate_call = ToolCall(
        call_id="call_tab_loc",
        name="computer.locate_element",
        arguments={"element_description": "Claude tab close button on Brave browser", "image_path": str(sample_image)},
    )
    click_call = ToolCall(
        call_id="call_tab_click",
        name="computer.mouse_click",
        arguments={"x": 350, "y": 42, "button": "left", "clicks": 1},
    )
    verify_call = ToolCall(
        call_id="call_tab_verify",
        name="computer.verify_screen_change",
        arguments={
            "expected_change": "Claude tab is closed in Brave browser",
            "before_image_path": str(sample_image),
            "after_image_path": str(sample_image),
        },
    )

    fake_agent = FakeScriptedProvider([
        ([locate_call], "resp_1"),
        ([click_call], "resp_2"),
        ([verify_call], "resp_3"),
        "I have located and closed the Claude tab on your Brave browser.",
    ])

    locate_json = json.dumps({"found": True, "point": [350, 42], "label": "Claude tab close button"})
    verify_json = json.dumps({"verified": True, "explanation": "Claude tab is no longer visible on tab bar."})
    fake_vision = FakeScriptedProvider([locate_json, verify_json])

    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    clicked_points = []
    curr_pos = [0, 0]
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": curr_pos.__setitem__(0, x) or curr_pos.__setitem__(1, y))
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (curr_pos[0], curr_pos[1]))
    monkeypatch.setattr(computer_module, "_mouse_click", lambda x, y, button="left", clicks=1, source="": clicked_points.append((x, y)) or {"status": "success", "x": x, "y": y})

    engine = AgentEngine(provider=fake_agent)
    events = asyncio.run(collect_events(engine.run(task_id)))

    # Verify tool activities executed in sequence
    acts = [d["name"] for ev, d in events if ev == "activity" and d.get("status") == "completed"]
    assert any(name in acts for name in ("browser.close_tab", "computer.close_browser_tab", "computer.locate_element"))

    done_event = [d for ev, d in events if ev == "done"][0]
    assert done_event["status"] == "COMPLETED"
    assert "Claude" in done_event["message"] or "closed" in done_event["message"]


def test_agent_gui_workflow_with_autonomous_tool(sample_image, monkeypatch):
    """Test agent using computer.gui_action_workflow tool to execute complete loop in one turn."""
    task_id = create_test_task("Click the Mute button on the video player")

    workflow_call = ToolCall(
        call_id="call_wf",
        name="computer.gui_action_workflow",
        arguments={
            "target_element": "Mute button",
            "action": "click",
            "expected_change": "Volume muted icon appears",
        },
    )

    fake_agent = FakeScriptedProvider([
        ([workflow_call], "resp_wf"),
        "Muted the video player as requested.",
    ])

    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1000, 1000)))
    clicked = []
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda x, y, button, clicks: clicked.append((x, y)))

    locate_json = json.dumps({"found": True, "point": [100, 900], "label": "Mute button"})
    verify_json = json.dumps({"verified": True, "explanation": "Mute icon visible."})
    fake_vision = FakeScriptedProvider([locate_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    engine = AgentEngine(provider=fake_agent)
    events = asyncio.run(collect_events(engine.run(task_id)))

    wf_act = [d for ev, d in events if ev == "activity" and d.get("name") == "computer.gui_action_workflow"]
    assert len(wf_act) == 1
    assert wf_act[0]["status"] == "completed"

    done_event = [d for ev, d in events if ev == "done"][0]
    assert done_event["status"] == "COMPLETED"
    assert "Mute button" in done_event["message"] or "Muted" in done_event["message"]



def test_targeted_browser_tab_gui_planning_rejects_ctrl_w(sample_image, monkeypatch):
    """Test ensuring targeted tab request selects visual locate/click rather than blind Ctrl+W hotkey."""
    from app.providers.base import OPENAI_INSTRUCTIONS
    assert "['ctrl', 'w']" in OPENAI_INSTRUCTIONS or "Ctrl+W" in OPENAI_INSTRUCTIONS or "ctrl" in OPENAI_INSTRUCTIONS
    assert "close_browser_tab" in OPENAI_INSTRUCTIONS or "locate" in OPENAI_INSTRUCTIONS.lower()

    task_id = create_test_task("close the Claude tab on my Brave browser")

    curr_pos = [0, 0]
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": curr_pos.__setitem__(0, x) or curr_pos.__setitem__(1, y))
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (curr_pos[0], curr_pos[1]))
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda *a, **k: None)

    locate_json = json.dumps({"found": True, "point": [300, 40], "label": "Claude tab close button"})
    verify_json = json.dumps({"verified": True, "explanation": "Claude tab closed."})
    fake_vision = FakeScriptedProvider([locate_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    fake_agent = FakeScriptedProvider(["Claude tab closed directly."])
    engine = AgentEngine(provider=fake_agent)
    events = asyncio.run(collect_events(engine.run(task_id)))
    print("TEST_TARGETED_EVENTS:", events)

    # Verify no computer.hotkey tool call was executed
    hotkey_acts = [d for ev, d in events if ev == "activity" and d.get("name") == "computer.hotkey"]
    assert len(hotkey_acts) == 0

    # Verify deterministic close_browser_tab executed
    acts = [d["name"] for ev, d in events if ev == "activity" and d.get("status") == "completed"]
    assert any(name in acts for name in ("browser.close_tab", "computer.close_browser_tab", "computer.locate_element"))


def test_targeted_browser_tab_gui_planning_for_already_open_brave_window(sample_image, monkeypatch):
    """Regression test: For an already-open Brave window, the agent visually grounds and closes the Claude tab
    without launching a duplicate Brave instance or using generic keyboard shortcuts.
    """
    task_id = create_test_task("close the Claude tab on my Brave browser")

    fake_agent = FakeScriptedProvider(["The Claude tab on your Brave browser has been successfully closed."])

    curr_pos = [0, 0]
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": curr_pos.__setitem__(0, x) or curr_pos.__setitem__(1, y))
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (curr_pos[0], curr_pos[1]))
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda *a, **k: None)
    monkeypatch.setattr(computer_module, "_get_active_window", lambda: {"active": True, "title": "Brave - Claude", "width": 1920, "height": 1080})

    locate_json = json.dumps({"found": True, "tab_x1": 20, "tab_x2": 320, "label": "Claude tab close button"})
    verify_json = json.dumps({"verified": True, "confidence": 0.95, "description": "The Claude tab is gone"})
    fake_vision = FakeScriptedProvider([locate_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    engine = AgentEngine(provider=fake_agent)
    events = asyncio.run(collect_events(engine.run(task_id)))

    # Assert launch_app and destructive hotkeys are NEVER called
    launch_acts = [d for ev, d in events if ev == "activity" and d.get("name") == "computer.launch_app"]
    hotkey_acts = [d for ev, d in events if ev == "activity" and d.get("name") == "computer.hotkey"]
    assert len(launch_acts) == 0, "computer.launch_app must not be called when Brave is already open"
    assert len(hotkey_acts) == 0, "computer.hotkey must not be called for targeted tab closure"

    # Assert close_browser_tab executed directly
    completed_tools = [d["name"] for ev, d in events if ev == "activity" and d.get("status") == "completed"]
    assert any(name in completed_tools for name in ("browser.close_tab", "computer.close_browser_tab"))


    done_event = [d for ev, d in events if ev == "done"][0]
    assert done_event["status"] == "COMPLETED"



# ---------------------------------------------------------------------------
# 6. Deterministic Close Browser Tab Fast-Path Tests
# ---------------------------------------------------------------------------

def test_close_browser_tab_success_cycle(sample_image, monkeypatch):
    """Test the complete deterministic tab close cycle with timing and cursor validation."""
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))

    clicked_coords = []
    curr_pos = [0, 0]
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": curr_pos.__setitem__(0, x) or curr_pos.__setitem__(1, y))
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (curr_pos[0], curr_pos[1]))
    monkeypatch.setattr(computer_module, "_mouse_click", lambda x, y, button, clicks, source="": clicked_coords.append((x, y, button, clicks)) or {"status": "success", "x": x, "y": y})

    # Grounding JSON with tab horizontal bounds
    locate_json = json.dumps({
        "found": True,
        "tab_x1": 20,
        "tab_x2": 320,
        "matched_title": "Claude",
        "confidence": 0.98,
    })
    verify_json = json.dumps({"verified": True, "explanation": "The Claude tab is closed."})

    fake_vision = FakeScriptedProvider([locate_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    res = computer_module._close_browser_tab(tab_name="Claude", browser_name="Brave")

    assert res.get("success") is True
    assert res.get("tab_name") == "Claude"
    target_x, target_y = res.get("target_coordinates")
    assert 280 <= target_x <= 320, f"Target x={target_x} should be at right edge of tab 20..320"
    assert target_y < computer_module.TAB_BAR_HEIGHT, f"Target y={target_y} should be in tab strip"
    assert res.get("cursor_verified") is True
    assert clicked_coords == [(target_x, target_y, "left", 1)]
    assert "timings_ms" in res
    assert "screenshot_ms" in res["timings_ms"]
    assert "vision_grounding_ms" in res["timings_ms"]
    assert "mouse_move_ms" in res["timings_ms"]
    assert "click_ms" in res["timings_ms"]
    assert "verification_ms" in res["timings_ms"]
    assert "total_ms" in res["timings_ms"]



def test_close_browser_tab_rejects_out_of_tab_strip_coordinates(sample_image, monkeypatch):
    """Sanity check: Reject target coordinates that fall in the webpage body (y > TAB_BAR_HEIGHT)."""
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))

    clicked = []
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda *a, **k: clicked.append(True))

    # Invalid tab with tab_x2 <= tab_x1
    locate_json = json.dumps({
        "found": True,
        "tab_x1": 500,
        "tab_x2": 502,
        "label": "Accidental element",
    })
    fake_vision = FakeScriptedProvider([locate_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    res = computer_module._close_browser_tab(tab_name="Claude", browser_name="Brave")

    assert res.get("success") is False
    assert res.get("failed_step") == "invalid_tab_width"
    assert len(clicked) == 0, "Mouse click must NOT execute when target is invalid"


def test_close_browser_tab_rejects_window_control_button(sample_image, monkeypatch):
    """Sanity check: Reject target coordinates that match main browser window top-right close button."""
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))

    clicked = []
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda *a, **k: clicked.append(True))

    # Top-right window close button region (x > 0.95 * 1920 = 1824)
    locate_json = json.dumps({
        "found": True,
        "tab_x1": 1850,
        "tab_x2": 1910,
        "label": "Window close button",
    })
    fake_vision = FakeScriptedProvider([locate_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    res = computer_module._close_browser_tab(tab_name="Claude", browser_name="Brave")

    assert res.get("success") is False
    assert res.get("failed_step") == "safety_check_window_controls"
    assert len(clicked) == 0, "Mouse click must NOT execute on main window close button"


def test_close_browser_tab_aborts_on_physical_cursor_mismatch(sample_image, monkeypatch):
    """Safety check: Abort click if physical cursor position does not match commanded target."""
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))

    clicked = []
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": None)
    monkeypatch.setattr(computer_module, "_mouse_click", lambda *a, **k: clicked.append(True))
    # Return cursor position elsewhere
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (999, 999))

    locate_json = json.dumps({
        "found": True,
        "tab_x1": 20,
        "tab_x2": 320,
        "matched_title": "Claude",
    })
    fake_vision = FakeScriptedProvider([locate_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    res = computer_module._close_browser_tab(tab_name="Claude", browser_name="Brave")

    assert res.get("success") is False
    assert res.get("failed_step") == "physical_cursor_verification"
    assert len(clicked) == 0, "Mouse click must NOT execute if cursor did not land on target"


def test_agent_engine_terminates_immediately_after_close_browser_tab(sample_image, monkeypatch):
    """Ensure AgentEngine concludes task immediately after close_browser_tab completes without re-planning."""
    task_id = create_test_task("close the Claude tab in my Brave browser")

    fake_agent = FakeScriptedProvider([
        "Unreachable follow-up turn",
    ])

    curr_pos = [0, 0]
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": curr_pos.__setitem__(0, x) or curr_pos.__setitem__(1, y))
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (curr_pos[0], curr_pos[1]))
    monkeypatch.setattr(computer_module, "_mouse_click", lambda *a, **k: None)

    locate_json = json.dumps({"found": True, "tab_x1": 20, "tab_x2": 320, "matched_title": "Claude"})
    verify_json = json.dumps({"verified": True, "explanation": "The Claude tab is closed."})
    fake_vision = FakeScriptedProvider([locate_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    engine = AgentEngine(provider=fake_agent)
    events = asyncio.run(collect_events(engine.run(task_id)))


    # Confirm only ONE tool call was executed and task completed immediately
    tool_acts = [d["name"] for ev, d in events if ev == "activity" and d.get("name") in ("browser.close_tab", "computer.close_browser_tab")]
    assert len(tool_acts) == 1
    done_event = [d for ev, d in events if ev == "done"][0]
    assert done_event["status"] == "COMPLETED"
    assert "Claude" in done_event["message"]



def test_close_browser_tab_exact_and_truncated_title_matching(sample_image, monkeypatch):
    """Test that close_browser_tab successfully matches full and truncated titles containing 'Claude'."""
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))
    clicked = []
    curr_pos = [0, 0]
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": curr_pos.__setitem__(0, x) or curr_pos.__setitem__(1, y))
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (curr_pos[0], curr_pos[1]))
    monkeypatch.setattr(computer_module, "_mouse_click", lambda x, y, button="left", clicks=1, source="": clicked.append((x, y)) or {"status": "success", "x": x, "y": y})


    # Mock vision response for truncated title "Building a Jarvis-like AI for PC - Claude..."
    grounding_json = json.dumps({
        "found": True,
        "matched_title": "Building a Jarvis-like AI for PC - Claude",
        "tab_bbox": [0, 0, 45, 220],
        "close_x_bbox": [10, 190, 35, 215],
        "close_x_center_point": [202, 22],
        "confidence": 0.98,
    })
    verify_json = json.dumps({"verified": True, "explanation": "Claude tab closed."})
    fake_vision = FakeScriptedProvider([grounding_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    res = computer_module._close_browser_tab(tab_name="Claude", browser_name="Brave")
    assert res["success"] is True
    assert res["verification"]["verified"] is True
    assert clicked, "Mouse click must occur"
    # Target x should be near the right edge of the tab (tab spans 0..220 -> norm_x ~ 202 -> px ~ 388)
    click_x, click_y = clicked[0]
    assert 180 <= click_x <= 220, f"Expected click near right edge close button, got x={click_x}"
    assert click_y <= 60, f"Expected click in tab strip, got y={click_y}"



def test_close_browser_tab_rejects_unrelated_content_match(sample_image, monkeypatch):
    """Test that when Claude is not present on tab bar, it returns failure without clicking."""
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))
    clicked = []
    monkeypatch.setattr(computer_module, "_mouse_click", lambda x, y, button="left", clicks=1, source="": clicked.append((x, y)) or {"status": "success", "x": x, "y": y})

    # Model reports Claude tab not found on tab strip
    not_found_json = json.dumps({
        "found": False,
        "reason": "Tab 'Claude' not found among visible tabs (open: YouTube, GitHub, Settings)",
    })
    fake_vision = FakeScriptedProvider([not_found_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    res = computer_module._close_browser_tab(tab_name="Claude", browser_name="Brave")
    assert res["success"] is False
    assert "not found" in res.get("reason", "").lower()
    assert len(clicked) == 0, "No click should occur when tab is not found"


def test_close_browser_tab_geometric_safety_rejects_navigation_area(sample_image, monkeypatch):
    """Test that coordinates corresponding to browser navigation buttons (Back/Forward at y >= 70)
    or tab left-edge/center are strictly rejected by code safety checks without clicking.
    """
    monkeypatch.setattr(computer_module, "_screenshots_dir", lambda: sample_image.parent)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "screenshot", lambda: Image.new("RGB", (1920, 1080)))
    clicked = []
    curr_pos = [0, 0]
    monkeypatch.setattr(computer_module, "_mouse_move", lambda x, y, source="": curr_pos.__setitem__(0, x) or curr_pos.__setitem__(1, y))
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (curr_pos[0], curr_pos[1]))
    monkeypatch.setattr(computer_module, "_mouse_click", lambda x, y, button="left", clicks=1, source="": clicked.append((x, y)) or {"status": "success", "x": x, "y": y})

    # Test 1: Real tab structure [tab_x1: 20, tab_x2: 320]
    # Code calculates x_target = 296, y_target = 27
    grounding_json = json.dumps({
        "found": True,
        "matched_title": "Building a Jarvis-like AI for PC - Claude",
        "tab_x1": 20,
        "tab_x2": 320,
        "confidence": 0.98,
    })
    verify_json = json.dumps({"verified": True, "explanation": "Claude tab closed."})
    fake_vision = FakeScriptedProvider([grounding_json, verify_json])
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_vision)

    res = computer_module._close_browser_tab(tab_name="Claude", browser_name="Brave")
    assert res["success"] is True
    target_x, target_y = res["target_coordinates"]
    # Verify target is strictly within tab strip height (<= 55) and NOT in navigation area (>= 70)
    assert target_y < computer_module.TAB_BAR_HEIGHT, f"Target y={target_y} must be in tab strip"
    assert target_y < 70, f"Target y={target_y} must not be in navigation bar"
    # Verify target is at the far right edge of the Claude tab (20..320 -> x >= 230)
    assert target_x >= (20 + 0.70 * (320 - 20)), f"Target x={target_x} must be at right edge"
    assert clicked == [(target_x, target_y)], "Exactly one click must occur at target"

