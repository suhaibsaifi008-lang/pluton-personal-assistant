"""
LIVE CUTOVER FAILURE INVESTIGATION SCRIPT
Submits "OPEN GMAIL TAB IN MY BROWSER" to /api/chat stream and captures raw SSE events & exceptions.
"""

import asyncio
import json
import httpx


async def test_live_chat_stream():
    url = "http://127.0.0.1:8000/api/chat"
    payload = {
        "message": "OPEN GMAIL TAB IN MY BROWSER",
        "stream": True,
    }

    print(f"[TEST] Sending POST {url} with payload: {payload}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream("POST", url, json=payload) as response:
                print(f"[TEST] Response status: {response.status_code}")
                print(f"[TEST] Response headers: {response.headers}")
                
                async for line in response.aiter_lines():
                    print(f"[SSE LINE] {line}")
        except Exception as e:
            print(f"[TEST EXCEPTION] {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test_live_chat_stream())
