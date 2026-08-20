"""
PLUTON V2 — Playwright Browser Engine Integration Tests
Tests DOM lookup, clicks, fills, page content readback, navigation, and state retrieval.
"""

import pytest
from app.core.contracts import ExecutionContext
from app.kernel.control_kernel import KERNEL
from app.subsystems.computer.browser_engine import BrowserEngine


@pytest.fixture(autouse=True)
def auth_task():
    task_id = "test-pw-task"
    ctx = ExecutionContext(task_id=task_id)
    KERNEL.authorize_task(task_id, context=ctx)
    yield ctx
    KERNEL.revoke_task(task_id)


@pytest.mark.anyio
async def test_playwright_engine_headless_workflow():
    engine = BrowserEngine()
    try:
        # 1. Ensure headless Playwright page
        page = await engine._ensure_playwright(headless=True)
        assert page is not None

        # 2. Set HTML content directly to test DOM interactions deterministically
        test_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Pluton Playwright Test</title></head>
        <body>
            <h1>Pluton Web Interface</h1>
            <input id="test-input" type="text" value="" />
            <button id="test-btn" onclick="document.getElementById('status').innerText = 'Clicked!'">Submit</button>
            <div id="status">Ready</div>
        </body>
        </html>
        """
        await page.set_content(test_html)

        # 3. Read page state
        state = await engine.get_state()
        assert state["active"] is True
        assert state["title"] == "Pluton Playwright Test"

        # 4. Type into input
        type_res = await engine.type_text("#test-input", "Hello from Pluton Playwright")
        assert type_res["success"] is True
        input_val = await page.input_value("#test-input")
        assert input_val == "Hello from Pluton Playwright"

        # 5. Click button
        click_res = await engine.click("#test-btn")
        assert click_res["success"] is True
        status_text = await page.inner_text("#status")
        assert status_text == "Clicked!"

        # 6. Read page text content
        read_res = await engine.read_page()
        assert read_res["success"] is True
        assert "Pluton Web Interface" in read_res["content"]

    finally:
        await engine.close()
