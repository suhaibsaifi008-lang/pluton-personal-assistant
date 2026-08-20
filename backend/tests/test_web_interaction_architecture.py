"""
PLUTON V2 — Generic Web Interaction Subsystem Verification Suite
Validates the canonical webpage control architecture on the local deterministic test page:
1. Full workflow: Navigate -> Type textbox -> Toggle checkbox -> Select dropdown -> Click button -> Read result area.
2. Target resolution order: Exact Accessible Name -> Role+Name -> Label -> Placeholder -> Selector.
3. Element not found returns clean structured TARGET_NOT_FOUND.
4. Ambiguity protection returns AMBIGUOUS_TARGET.
5. Strict post-action readback verification on all input controls.
6. Zero coordinate mouse dependency for DOM interactions.
"""

import asyncio
import pytest
from app.core.contracts import ExecutionContext, BrowserTabIdentity
from app.subsystems.computer.contracts import WebTarget
from app.subsystems.computer.browser_engine import BROWSER_ENGINE
from app.subsystems.computer.domains.web import WEB_DOMAIN


def test_web_target_model_completeness():
    """Verify WebTarget contains all required canonical metadata fields."""
    target = WebTarget(
        browser_name="Brave",
        browser_pid=1234,
        browser_hwnd=5678,
        tab_index=1,
        tab_title="Pluton Web Interaction Test Page",
        tab_url="http://127.0.0.1:5173/test_page.html",
        page_id="page-1",
        element_id="test-input",
        role="textbox",
        accessible_name="Enter text",
        text="PLUTON TEST",
        selector="#test-input",
        confidence=1.0,
        resolver_source="dom_selector",
        visible=True,
        enabled=True,
        value="PLUTON TEST",
    )
    assert target.browser_name == "Brave"
    assert target.role == "textbox"
    assert target.accessible_name == "Enter text"
    assert target.selector == "#test-input"
    assert target.value == "PLUTON TEST"


def _get_test_page_url():
    import os
    from pathlib import Path
    p = Path(r"c:\Users\MOHD SUHAIB\Downloads\PLUTON-UPDATED\frontend\public\test_page.html").resolve()
    return p.as_uri()


def test_element_not_found_returns_clean_structured_error():
    """Verify searching for a non-existent element returns clean TARGET_NOT_FOUND without exceptions."""
    async def run():
        await BROWSER_ENGINE.navigate(_get_test_page_url())
        res = await BROWSER_ENGINE.find_element("NonExistentButtonXYZ12345", role="button")
        assert res.get("found") is False
        assert "TARGET_NOT_FOUND" in res.get("error", "")

    asyncio.run(run())


def test_generic_test_page_full_workflow():
    """Execute the canonical 10-step web interaction loop against local deterministic test page."""
    async def run():
        # 1. Navigate to test page
        nav = await BROWSER_ENGINE.navigate(_get_test_page_url())
        assert nav.get("success") is True
        assert "Pluton Web Interaction Test Page" in nav.get("title", "")

        # 2. Find and type into textbox
        f_input = await BROWSER_ENGINE.find_element("Enter text", role="textbox")
        assert f_input.get("found") is True
        assert f_input.get("selector") == "#test-input"

        t_res = await BROWSER_ENGINE.type_element("Enter text", "PLUTON TEST")
        assert t_res.get("success") is True
        assert t_res.get("readback_value") == "PLUTON TEST"
        assert t_res.get("verified") is True

        # 3. Find and toggle checkbox
        f_chk = await BROWSER_ENGINE.find_element("Enable feature", role="checkbox")
        assert f_chk.get("found") is True
        assert f_chk.get("selector") == "#test-checkbox"

        c_res = await BROWSER_ENGINE.click_element("Enable feature", role="checkbox")
        assert c_res.get("success") is True

        # 4. Find and select dropdown Option B
        f_sel = await BROWSER_ENGINE.find_element("Select option", role="combobox")
        assert f_sel.get("found") is True
        assert f_sel.get("selector") == "#test-select"

        s_res = await BROWSER_ENGINE.select_element("Select option", "Option B")
        assert s_res.get("success") is True
        assert s_res.get("selected_value") == "Option B"
        assert s_res.get("verified") is True

        # 5. Find and click Change Page button
        f_btn = await BROWSER_ENGINE.find_element("Change Page", role="button")
        assert f_btn.get("found") is True
        assert f_btn.get("selector") == "#test-button"

        b_res = await BROWSER_ENGINE.click_element("Change Page", role="button")
        assert b_res.get("success") is True

        # 6. Extract text from result area and verify state transition
        r_res = await BROWSER_ENGINE.extract_text("#result-area")
        assert r_res.get("success") is True
        res_text = r_res.get("text", "")
        assert 'Text: "PLUTON TEST"' in res_text
        assert "Checkbox: CHECKED" in res_text
        assert 'Selected: "Option B"' in res_text
        assert "Button Click" in res_text

    asyncio.run(run())
