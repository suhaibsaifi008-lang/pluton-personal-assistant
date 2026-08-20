import asyncio

import httpx
import pytest

from app.config import Settings
from app.providers import (
    OpenAIProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRequest,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_openai_provider_parses_text_and_function_call():
    def handler(request: httpx.Request):
        assert request.url.path == "/v1/responses"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"id": "resp_1", "output_text": "Done", "output": [{"type": "function_call", "call_id": "call_1", "name": "filesystem.read", "arguments": '{"path":"README.md"}'}]})
    settings = Settings(_env_file=None, openai_api_key="test-key", openai_base_url="https://provider.test/v1")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = run(OpenAIProvider(settings, client).respond(ProviderRequest("Read the README.")))
    assert response.text == "Done"
    assert response.tool_calls[0].arguments == {"path": "README.md"}
    run(client.aclose())


def test_openai_provider_injects_context_and_history():
    sent = {}

    def handler(request: httpx.Request):
        sent["request"] = request.read().decode()
        return httpx.Response(200, json={"id": "resp_1", "output_text": "Ok", "output": []})

    settings = Settings(_env_file=None, openai_api_key="test-key", openai_base_url="https://provider.test/v1")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = ProviderRequest(
        message="What do I prefer?",
        context="- [preference] I like dark mode",
        history=[{"role": "user", "content": "earlier message"}, {"role": "assistant", "content": "earlier reply"}],
    )
    run(OpenAIProvider(settings, client).respond(request))
    import json
    payload = json.loads(sent["request"])
    assert "dark mode" in payload["instructions"]
    assert payload["input"][0]["role"] == "user"
    assert payload["input"][-1]["content"] == "What do I prefer?"
    run(client.aclose())


def test_openai_provider_reports_missing_and_rejected_keys():
    settings = Settings(_env_file=None, openai_api_key=None)
    with pytest.raises(ProviderConfigurationError):
        run(OpenAIProvider(settings).respond(ProviderRequest("Hello")))
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    with pytest.raises(ProviderAuthenticationError):
        run(OpenAIProvider(Settings(_env_file=None, openai_api_key="bad"), client).respond(ProviderRequest("Hello")))
    run(client.aclose())


def test_openai_provider_reports_rate_limit():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429)))
    with pytest.raises(ProviderRateLimitError):
        run(OpenAIProvider(Settings(_env_file=None, openai_api_key="test"), client).respond(ProviderRequest("Hello")))
    run(client.aclose())


def _sse_response(*events):
    lines = []
    for event_type, payload in events:
        lines.append(f"event: {event_type}")
        lines.append(f"data: {payload}")
        lines.append("")
    lines.append("data: [DONE]")
    return httpx.Response(200, text="\n".join(lines))


def test_openai_provider_streams_text_and_tool_calls():
    response = _sse_response(
        ("response.output_text.delta", '{"type":"response.output_text.delta","delta":"Hi"}'),
        ("response.output_item.added", '{"type":"response.output_item.added","item":{"type":"function_call","call_id":"call_1","name":"filesystem.read"}}'),
        ("response.function_call_arguments.done", '{"type":"response.function_call_arguments.done","call_id":"call_1","arguments":"{\\"path\\":\\"README.md\\"}"}'),
        ("response.completed", '{"type":"response.completed","response":{"id":"resp_s"}}'),
    )
    settings = Settings(_env_file=None, openai_api_key="test-key", openai_base_url="https://provider.test/v1")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response))
    events = []

    async def go():
        async for event in OpenAIProvider(settings, client).stream_respond(ProviderRequest("Read the README.")):
            events.append(event)

    asyncio.run(go())
    text = "".join(e.text for e in events if e.kind == "text_delta")
    assert text == "Hi"
    calls = [e for e in events if e.kind == "tool_calls"][0]
    assert calls.response_id == "resp_s"
    assert calls.tool_calls[0].arguments == {"path": "README.md"}
    asyncio.run(client.aclose())


def test_openai_provider_stream_reports_rejected_key():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401)))

    async def go():
        async for _ in OpenAIProvider(Settings(_env_file=None, openai_api_key="bad"), client).stream_respond(ProviderRequest("Hello")):
            pass

    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(go())
    asyncio.run(client.aclose())