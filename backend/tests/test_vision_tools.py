import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.database import SessionLocal, migrate
from app.models import Activity, Task
from app.providers import (
    AIProvider,
    FreeLLMAPIProvider,
    OpenAIProvider,
    ProviderRequest,
    ProviderResponse,
    image_to_data_uri,
)
from app.security import PermissionLevel, requires_confirmation, sanitize_for_storage
from app.tool_executor import ToolExecutionResult, ToolExecutor
from app.tools import TOOLS, ToolRegistry
from app.tools import computer as computer_module
from app.tools.computer import (
    _inspect_screen,
    _locate_element,
    _screenshot,
    _verify_screen_change,
    register_computer_tools,
)


def setup_function():
    migrate()


@pytest.fixture
def sample_image(tmp_path):
    from PIL import Image
    img_file = tmp_path / "test_screenshot.png"
    img = Image.new("RGB", (1920, 1080), color=(40, 40, 45))
    img.save(str(img_file))
    return img_file



class FakeVisionProvider(AIProvider):
    name = "fake_vision"

    def __init__(self, response_text: str = "A desktop screen with a browser window.", vision_supported: bool = True):
        self._response_text = response_text
        self._vision_supported = vision_supported
        self.received_requests: list[ProviderRequest] = []

    @property
    def model(self) -> str:
        return "fake-vision-model"

    @property
    def supports_vision(self) -> bool:
        return self._vision_supported

    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        self.received_requests.append(request)
        return ProviderResponse(response_id="resp_vis_123", text=self._response_text)


# ---------------------------------------------------------------------------
# 1. Image Encoding & Data URI Tests
# ---------------------------------------------------------------------------

def test_image_to_data_uri_encodes_local_file(sample_image):
    uri = image_to_data_uri(str(sample_image))
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > len("data:image/png;base64,")


def test_image_to_data_uri_preserves_existing_data_uri():
    existing = "data:image/jpeg;base64,abc12345"
    assert image_to_data_uri(existing) == existing


def test_image_to_data_uri_preserves_http_url():
    url = "https://example.com/screenshot.png"
    assert image_to_data_uri(url) == url


def test_image_to_data_uri_missing_file_raises_error():
    with pytest.raises(FileNotFoundError):
        image_to_data_uri("nonexistent_path/image.png")


# ---------------------------------------------------------------------------
# 2. Provider Multimodal Payload Formatting Tests
# ---------------------------------------------------------------------------

def test_openai_provider_builds_multimodal_image_payload(sample_image, monkeypatch):
    from app.config import Settings
    s = Settings(openai_api_key="test-key", openai_model="gpt-4.1-mini")
    p = OpenAIProvider(settings=s)

    assert p.supports_vision is True

    req = ProviderRequest(
        message="What is this UI?",
        images=[str(sample_image)],
    )
    payload = p._payload(req)

    user_msg = payload["input"][-1]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][0] == {"type": "text", "text": "What is this UI?"}
    assert user_msg["content"][1]["type"] == "image_url"
    assert user_msg["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_freellmapi_provider_builds_multimodal_image_payload(sample_image, monkeypatch):
    from app.config import Settings
    s = Settings(freeLLMAPI_api_key="test-key", freeLLMAPI_model="auto")
    p = FreeLLMAPIProvider(settings=s)

    assert p.supports_vision is True

    req = ProviderRequest(
        message="Find the submit button.",
        images=[str(sample_image)],
    )
    payload = p._payload_chat(req)

    user_msg = payload["messages"][-1]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert user_msg["content"][0] == {"type": "text", "text": "Find the submit button."}
    assert user_msg["content"][1]["type"] == "image_url"
    assert user_msg["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_freellmapi_prioritizes_vision_models_when_images_present():
    from app.config import Settings
    s = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_model="auto",
        freeLLMAPI_fallback_models=["gemma-4-31b-it", "gemini-2.5-flash", "qwen2.5-vl-72b"],
        freeLLMAPI_auto_discover_fallbacks=False,
    )
    p = FreeLLMAPIProvider(settings=s)

    # Without images
    candidates_text = asyncio.run(p._get_model_candidates(MagicMock(), {}, is_vision=False))
    assert candidates_text == ["auto", "gemma-4-31b-it", "gemini-2.5-flash", "qwen2.5-vl-72b"]

    # With images (vision prioritized)
    candidates_vision = asyncio.run(p._get_model_candidates(MagicMock(), {}, is_vision=True))
    assert candidates_vision[0] in ("auto", "gemini-2.5-flash", "qwen2.5-vl-72b")
    # Non-vision model gemma should be moved after vision models
    assert candidates_vision.index("gemma-4-31b-it") > candidates_vision.index("gemini-2.5-flash")


# ---------------------------------------------------------------------------
# 3. Screen Inspection Tool Tests
# ---------------------------------------------------------------------------

def test_inspect_screen_success(sample_image, monkeypatch):
    fake_provider = FakeVisionProvider("The screen shows an open terminal window and browser.")
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))

    result = _inspect_screen(prompt="What apps are open?", image_path=str(sample_image))

    assert result.get("inspected") is True
    assert "open terminal window" in result.get("description", "")
    assert result.get("image_path") == str(sample_image.resolve())
    assert result.get("width") == 1920
    assert result.get("height") == 1080


def test_inspect_screen_auto_captures_when_no_image_path(monkeypatch):
    fake_provider = FakeVisionProvider("Active desktop overview.")
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(
        computer_module,
        "_screenshot",
        lambda: {"path": "data/screenshots/auto_shot.png", "width": 1920, "height": 1080, "captured": True},
    )

    result = _inspect_screen(prompt="Describe screen")
    assert result.get("inspected") is True
    assert result.get("description") == "Active desktop overview."
    assert result.get("image_path") == "data/screenshots/auto_shot.png"


def test_inspect_screen_returns_error_when_provider_unsupported(sample_image, monkeypatch):
    unsupported_provider = FakeVisionProvider(vision_supported=False)
    monkeypatch.setattr(computer_module, "create_provider", lambda: unsupported_provider)

    result = _inspect_screen(image_path=str(sample_image))
    assert "error" in result
    assert "does not support vision" in result["error"]


def test_inspect_screen_missing_image_file():
    result = _inspect_screen(image_path="nonexistent_folder/missing.png")
    assert "error" in result
    assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# 4. Element Grounding & Coordinate Location Tests
# ---------------------------------------------------------------------------

def test_locate_element_by_normalized_point(sample_image, monkeypatch):
    # Normalized point [500, 250] on 1920x1080 screen -> pixel (960, 270)
    json_resp = json.dumps({
        "found": True,
        "point": [500, 250],
        "label": "Settings Icon",
        "confidence": 0.95,
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))

    result = _locate_element("Settings icon", image_path=str(sample_image))

    assert result.get("found") is True
    assert result.get("x") == 960
    assert result.get("y") == 270
    assert result.get("label") == "Settings Icon"
    assert result.get("confidence") == 0.95


def test_locate_element_by_bounding_box(sample_image, monkeypatch):
    # Normalized bbox [100, 200, 300, 400] -> center y = (100+300)/2 = 200, center x = (200+400)/2 = 300
    # On 1000x1000 screen -> pixel (300, 200)
    json_resp = json.dumps({
        "found": True,
        "bbox": [100, 200, 300, 400],
        "label": "Send Button",
        "confidence": 0.99,
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))

    result = _locate_element("Send button", image_path=str(sample_image))

    assert result.get("found") is True
    # sample_image size is 1920x1080 -> 300/1000 * 1920 = 576, 200/1000 * 1080 = 216
    assert result.get("x") == 576
    assert result.get("y") == 216
    assert result.get("label") == "Send Button"


def test_locate_element_uses_exact_bbox_center_for_small_close_button(tmp_path, monkeypatch):
    """Ensure small browser-tab close button targets the exact geometric center of bbox rather than an edge."""
    from PIL import Image
    img_file = tmp_path / "browser_tab.png"
    img = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
    img.save(str(img_file))

    # Bounding box of tab close icon X: [ymin=35, xmin=320, ymax=55, xmax=340]
    # Center X = (320 + 340) / 2 = 330 -> pixel 330/1000 * 1920 = 633.6 -> 634
    # Center Y = (35 + 55) / 2 = 45 -> pixel 45/1000 * 1080 = 48.6 -> 49
    json_resp = json.dumps({
        "found": True,
        "bbox": [35, 320, 55, 340],
        "point": [322, 36], # Point might be slightly offset / top-left anchor
        "label": "Claude tab close button",
        "confidence": 0.98,
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _locate_element("Claude tab close button", image_path=str(img_file))

    assert result.get("found") is True
    # Asserts that bbox center is prioritized over approximate point
    assert result.get("x") == 634
    assert result.get("y") == 49
    assert result.get("bbox") == [35, 320, 55, 340]
    assert result.get("confidence") == 0.98


def test_coordinate_mapping_consistency_across_custom_resolutions(tmp_path, monkeypatch):
    """Test element coordinate mapping consistency on 2560x1440 (2K) and 1280x720 (720p)."""
    from PIL import Image

    # 2K Resolution
    img_2k = tmp_path / "screen_2k.png"
    Image.new("RGB", (2560, 1440)).save(str(img_2k))

    json_resp = json.dumps({"found": True, "bbox": [100, 200, 200, 400]})
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    res_2k = _locate_element("Target on 2K", image_path=str(img_2k))
def test_locate_element_disambiguates_xmin_ymin_order_with_point(tmp_path, monkeypatch):
    """Ensure models returning [xmin, ymin, xmax, ymax] are correctly disambiguated."""
    from PIL import Image
    img_file = tmp_path / "browser_tab_order.png"
    Image.new("RGB", (1920, 1080), color=(30, 30, 30)).save(str(img_file))

    # Model returns [xmin=320, ymin=35, xmax=340, ymax=55] and point=[330, 45]
    json_resp = json.dumps({
        "found": True,
        "bbox": [320, 35, 340, 55],
        "point": [330, 45],
        "label": "Claude tab close button",
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _locate_element("Claude tab close button", image_path=str(img_file))
    assert result.get("found") is True
    assert result.get("x") == 634
    assert result.get("y") == 49


def test_locate_element_with_dictionary_bbox(tmp_path, monkeypatch):
    """Ensure dictionary bbox with named keys (ymin, xmin, ymax, xmax) is supported directly."""
    from PIL import Image
    img_file = tmp_path / "dict_bbox.png"
    Image.new("RGB", (1920, 1080), color=(30, 30, 30)).save(str(img_file))

    json_resp = json.dumps({
        "found": True,
        "bbox": {"ymin": 35, "xmin": 320, "ymax": 55, "xmax": 340},
        "label": "Tab Close Button",
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _locate_element("Tab Close Button", image_path=str(img_file))
    assert result.get("found") is True
    assert result.get("x") == 634
    assert result.get("y") == 49


def test_mouse_move_physical_cursor_tracking(monkeypatch):
    """Ensure _mouse_move records physical cursor coordinates and confirms target match."""
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(computer_module.pyautogui, "moveTo", lambda x, y: None)
    monkeypatch.setattr(computer_module, "_get_physical_cursor_pos", lambda: (634, 49))

    res = computer_module._mouse_move(634, 49)
    assert res.get("x") == 634
    assert res.get("y") == 49
    assert res.get("physical_x") == 634
    assert res.get("physical_y") == 49
    assert res.get("matched_target") is True




def test_locate_element_rejects_out_of_bounds_coordinates(sample_image, monkeypatch):
    # Normalized 1500 -> out of bounds > 1000
    json_resp = json.dumps({
        "found": True,
        "point": [1500, 500],
        "label": "Offscreen element",
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))

    result = _locate_element("Offscreen element", image_path=str(sample_image))
    assert result.get("found") is False
    assert "out-of-bounds" in result.get("reason", "").lower()


def test_locate_element_not_found(sample_image, monkeypatch):
    json_resp = json.dumps({
        "found": False,
        "reason": "Search bar is hidden behind modal.",
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))

    result = _locate_element("Search bar", image_path=str(sample_image))
    assert result.get("found") is False
    assert "hidden behind modal" in result.get("reason", "")


def test_locate_element_malformed_model_output(sample_image, monkeypatch):
    fake_provider = FakeVisionProvider("I cannot see any buttons.")
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1920, 1080))

    result = _locate_element("Button", image_path=str(sample_image))
    assert result.get("found") is False
    assert "valid JSON" in result.get("reason", "")


# ---------------------------------------------------------------------------
# 5. Screen Change Verification Loop Tests
# ---------------------------------------------------------------------------

def test_verify_screen_change_success(sample_image, monkeypatch):
    json_resp = json.dumps({
        "verified": True,
        "explanation": "The modal window is now closed and desktop is visible.",
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _verify_screen_change(
        expected_change="Modal window closes",
        before_image_path=str(sample_image),
        after_image_path=str(sample_image),
    )

    assert result.get("verified") is True
    assert "modal window is now closed" in result.get("explanation", "").lower()


def test_verify_screen_change_unverified(sample_image, monkeypatch):
    json_resp = json.dumps({
        "verified": False,
        "explanation": "No visual difference observed; dropdown did not appear.",
    })
    fake_provider = FakeVisionProvider(json_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    result = _verify_screen_change(
        expected_change="Dropdown opens",
        before_image_path=str(sample_image),
        after_image_path=str(sample_image),
    )

    assert result.get("verified") is False
    assert "did not appear" in result.get("explanation", "")


# ---------------------------------------------------------------------------
# 6. End-to-End Action & Verification Loop Simulation
# ---------------------------------------------------------------------------

def test_full_vision_locate_click_verify_loop(sample_image, monkeypatch):
    """Simulates:
    1. Screenshot
    2. locate_element -> gets (x, y)
    3. mouse_click(x, y) -> executes click
    4. verify_screen_change -> confirms UI updated
    """
    # 1. Mock locate_element
    locate_resp = json.dumps({"found": True, "point": [250, 500], "label": "Save Button", "confidence": 0.98})
    fake_provider = FakeVisionProvider(locate_resp)
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)
    monkeypatch.setattr(computer_module, "_get_screen_size", lambda: (1000, 1000))

    loc_res = _locate_element("Save Button", image_path=str(sample_image))
    assert loc_res["found"] is True
    click_x, click_y = loc_res["x"], loc_res["y"]
    # 250/1000 * 1920 = 480, 500/1000 * 1080 = 540
    assert (click_x, click_y) == (480, 540)

    # 2. Mock mouse click
    clicked = []
    monkeypatch.setattr(computer_module.pyautogui, "click", lambda x, y, button, clicks: clicked.append((x, y)))
    click_res = computer_module._mouse_click(click_x, click_y)
    assert click_res["clicked"] is True
    assert clicked == [(480, 540)]


    # 3. Mock verify change
    verify_resp = json.dumps({"verified": True, "explanation": "File saved indicator appeared."})
    fake_provider._response_text = verify_resp

    ver_res = _verify_screen_change(
        expected_change="File saved indicator appears",
        before_image_path=str(sample_image),
        after_image_path=str(sample_image),
    )
    assert ver_res["verified"] is True


# ---------------------------------------------------------------------------
# 7. ToolExecutor & Audit Redaction Tests
# ---------------------------------------------------------------------------

def test_toolexecutor_runs_inspect_screen(sample_image, monkeypatch):
    db = SessionLocal()
    task = Task(title="test", request="inspect screen", status="RUNNING")
    db.add(task)
    db.commit()
    db.refresh(task)

    fake_provider = FakeVisionProvider("Visual summary of screen.")
    monkeypatch.setattr(computer_module, "create_provider", lambda: fake_provider)

    reg = ToolRegistry()
    register_computer_tools(reg)
    executor = ToolExecutor(reg)

    res, (ev_name, ev_data) = asyncio.run(
        executor.execute_call(
            db, task.id, "computer.inspect_screen", "call_insp", {"prompt": "describe", "image_path": str(sample_image)}, approved=True
        )
    )

    assert isinstance(res, ToolExecutionResult)
    assert res.status == "completed"
    assert res.observed["inspected"] is True
    assert res.observed["description"] == "Visual summary of screen."

    # Verify Activity recorded in DB
    activities = db.scalars(select(Activity).where(Activity.task_id == task.id)).all()
    assert len(activities) == 1
    assert activities[0].name == "computer.inspect_screen"
    assert activities[0].status == "completed"

    db.close()


def test_sanitize_for_storage_redacts_base64_image_data():
    raw_payload = {
        "text": "User question",
        "image_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
        "normal_path": "data/screenshots/test.png",
    }
    sanitized = sanitize_for_storage(raw_payload)

    assert sanitized["text"] == "User question"
    assert sanitized["image_data"] == "[IMAGE_DATA]"
    assert sanitized["normal_path"] == "data/screenshots/test.png"


# ---------------------------------------------------------------------------
# 8. Security & Confirmation Boundaries Tests
# ---------------------------------------------------------------------------

def test_vision_tools_are_low_permission():
    assert not requires_confirmation(TOOLS["computer.inspect_screen"].permission)
    assert not requires_confirmation(TOOLS["computer.locate_element"].permission)
    assert not requires_confirmation(TOOLS["computer.verify_screen_change"].permission)
    assert TOOLS["computer.inspect_screen"].permission == PermissionLevel.LOW
    assert TOOLS["computer.locate_element"].permission == PermissionLevel.LOW
    assert TOOLS["computer.verify_screen_change"].permission == PermissionLevel.LOW


def test_action_tools_maintain_strict_permission_levels():
    assert TOOLS["computer.mouse_click"].permission == PermissionLevel.MEDIUM
    assert TOOLS["computer.keyboard_type"].permission == PermissionLevel.MEDIUM
    assert TOOLS["computer.key_press"].permission == PermissionLevel.MEDIUM
    assert TOOLS["computer.hotkey"].permission == PermissionLevel.HIGH
    assert TOOLS["computer.launch_app"].permission == PermissionLevel.HIGH
    assert requires_confirmation(TOOLS["computer.hotkey"].permission)
    assert requires_confirmation(TOOLS["computer.launch_app"].permission)
