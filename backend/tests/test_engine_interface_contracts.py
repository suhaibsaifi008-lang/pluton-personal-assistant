"""
PLUTON V2 — Canonical Engine Interface Contract Tests
Validates that every canonical engine and domain handler satisfies its Protocol contract,
has zero missing methods, exposes compatible callable signatures, and fails fast on non-conforming engines.
"""

import inspect
import pytest
from app.subsystems.computer.interfaces import (
    CanonicalInterfaceError,
    IAppDomain,
    IBrowserDomain,
    IClipboardDomain,
    IFilesystemDomain,
    IKeyboardDomain,
    IMouseDomain,
    IScreenDomain,
    ITerminalDomain,
    IUIADomain,
    IUIAEngine,
    IVisionDomain,
    IWebDomain,
    IWindowDomain,
)
from app.subsystems.computer.conformance import CONFORMANCE_VERIFIER
from app.tools.uia_engine import UIA_ENGINE, UIAutomationEngine
from app.subsystems.computer.browser_engine import BROWSER_ENGINE, BrowserEngine
from app.subsystems.computer.domains.app import APP_DOMAIN, AppDomainHandler
from app.subsystems.computer.domains.window import WINDOW_DOMAIN, WindowDomainHandler
from app.subsystems.computer.domains.ui import UI_DOMAIN, UIDomainHandler
from app.subsystems.computer.domains.browser import BROWSER_DOMAIN, BrowserDomainHandler
from app.subsystems.computer.domains.web import WEB_DOMAIN, WebDomainHandler
from app.subsystems.computer.domains.keyboard import KEYBOARD_DOMAIN, KeyboardDomainHandler
from app.subsystems.computer.domains.mouse import MOUSE_DOMAIN, MouseDomainHandler
from app.subsystems.computer.domains.screen import SCREEN_DOMAIN, ScreenDomainHandler
from app.subsystems.computer.domains.vision import VISION_DOMAIN, VisionDomainHandler
from app.subsystems.computer.domains.filesystem import FILESYSTEM_DOMAIN, FilesystemDomainHandler
from app.subsystems.computer.domains.terminal import TERMINAL_DOMAIN, TerminalDomainHandler
from app.subsystems.computer.domains.clipboard import CLIPBOARD_DOMAIN, ClipboardDomainHandler


def test_conformance_verifier_audits_all_13_engines_cleanly():
    """Verify that all 13 canonical engines pass full interface audit."""
    report = CONFORMANCE_VERIFIER.audit_all()
    assert report["status"] == "CONFORMANT"
    assert report["total_engines"] == 13

    for eng_name, data in report["engines"].items():
        assert data["conforms"] is True
        assert len(data["missing_methods"]) == 0
        assert len(data["required_methods"]) > 0


@pytest.mark.parametrize("instance,protocol_cls,name", [
    (UIA_ENGINE, IUIAEngine, "UIAEngine"),
    (WINDOW_DOMAIN, IWindowDomain, "WindowDomain"),
    (UI_DOMAIN, IUIADomain, "UIDomain"),
    (BROWSER_DOMAIN, IBrowserDomain, "BrowserDomain"),
    (WEB_DOMAIN, IWebDomain, "WebDomain"),
    (KEYBOARD_DOMAIN, IKeyboardDomain, "KeyboardDomain"),
    (MOUSE_DOMAIN, IMouseDomain, "MouseDomain"),
    (SCREEN_DOMAIN, IScreenDomain, "ScreenDomain"),
    (VISION_DOMAIN, IVisionDomain, "VisionDomain"),
    (FILESYSTEM_DOMAIN, IFilesystemDomain, "FilesystemDomain"),
    (TERMINAL_DOMAIN, ITerminalDomain, "TerminalDomain"),
    (CLIPBOARD_DOMAIN, IClipboardDomain, "ClipboardDomain"),
    (APP_DOMAIN, IAppDomain, "AppDomain"),
])
def test_each_engine_conforms_to_protocol(instance, protocol_cls, name):
    """Verify that each individual canonical engine conforms to its Protocol."""
    result = CONFORMANCE_VERIFIER.verify_instance(instance, protocol_cls, name)
    assert result["conforms"] is True
    assert result["missing_methods"] == []


def test_conformance_verifier_fails_fast_on_missing_method():
    """Verify that an incomplete dummy engine raises CanonicalInterfaceError with structured details."""
    class IncompleteWindowEngine:
        def list_windows(self): return []
        # Missing find_window, get_foreground_window, focus_window, close_window, window_state

    with pytest.raises(CanonicalInterfaceError) as exc_info:
        CONFORMANCE_VERIFIER.verify_instance(IncompleteWindowEngine(), IWindowDomain, "IncompleteEngine")

    err_str = str(exc_info.value)
    assert "CANONICAL_INTERFACE_ERROR" in err_str
    assert "missing required methods" in err_str
    assert "get_foreground_window" in err_str


def test_uia_engine_foreground_window_contract():
    """Verify UIAEngine.get_foreground_window returns canonical structure."""
    fg = UIA_ENGINE.get_foreground_window()
    assert isinstance(fg, dict)
    required_keys = {"active", "hwnd", "pid", "title", "process", "class_name", "visibility"}
    assert required_keys.issubset(fg.keys())


def test_mouse_domain_drag_contract():
    """Verify MouseDomainHandler.drag interface contract with coordinate and semantic params."""
    assert hasattr(MOUSE_DOMAIN, "drag")
    sig = inspect.signature(MOUSE_DOMAIN.drag)
    params = set(sig.parameters.keys())
    assert {"start_x", "start_y", "end_x", "end_y", "source_target", "destination_target"}.issubset(params)
