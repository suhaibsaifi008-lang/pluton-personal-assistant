import asyncio
import json
import httpx
import pytest

from app.config import Settings
from app.providers import (
    FreeLLMAPIProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
)


def test_fallback_when_first_model_rate_limited():
    attempted_models = []

    def handler(request: httpx.Request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "fallback-1", "available": True}, {"id": "fallback-2", "available": True}]})
        
        body = json.loads(request.content.decode("utf-8"))
        model = body.get("model")
        attempted_models.append(model)
        if model == "auto":
            return httpx.Response(429, json={"error": "Rate limit on auto"})
        elif model == "fallback-1":
            return httpx.Response(200, json={
                "id": "resp-fb",
                "choices": [{"message": {"content": f"Success with {model}", "tool_calls": []}}],
            })
        return httpx.Response(404, json={"error": "Not found"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=1,
        provider_retry_backoff_factor=0.01,
        freeLLMAPI_model="auto",
        freeLLMAPI_fallback_models=["fallback-1"],
        freeLLMAPI_auto_discover_fallbacks=True,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    resp = asyncio.run(provider.respond(ProviderRequest(message="test")))
    assert resp.text == "Success with fallback-1"
    assert "auto" in attempted_models
    assert "fallback-1" in attempted_models
    # "auto" was tried first
    assert attempted_models[0] == "auto"


def test_all_fallback_models_exhausted_raises_clean_rate_limit_error():
    attempted_models = []

    def handler(request: httpx.Request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        body = json.loads(request.content.decode("utf-8"))
        attempted_models.append(body.get("model"))
        return httpx.Response(429, json={"error": "Rate limit"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=0,
        provider_retry_backoff_factor=0.01,
        freeLLMAPI_model="auto",
        freeLLMAPI_fallback_models=["fallback-1", "fallback-2"],
        freeLLMAPI_auto_discover_fallbacks=False,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    with pytest.raises(ProviderRateLimitError) as exc_info:
        asyncio.run(provider.respond(ProviderRequest(message="test")))

    assert "The AI provider is temporarily rate-limited. Please try again in a moment." in str(exc_info.value)
    assert attempted_models == ["auto", "fallback-1", "fallback-2"]


def test_401_and_400_do_not_trigger_fallback():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": "Invalid API key"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="bad-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=1,
        provider_retry_backoff_factor=0.01,
        freeLLMAPI_fallback_models=["fallback-1"],
        freeLLMAPI_auto_discover_fallbacks=False,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(provider.respond(ProviderRequest(message="test")))
    assert call_count == 1


def test_streaming_fallback_before_first_token():
    attempted_models = []

    def handler(request: httpx.Request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        body = json.loads(request.content.decode("utf-8"))
        model = body.get("model")
        attempted_models.append(model)
        if model == "auto":
            return httpx.Response(429, json={"error": "Rate limited"})
        lines = [
            'data: {"id":"s1","choices":[{"delta":{"content":"Streamed with fallback"}}]}\n\n',
            'data: [DONE]\n\n',
        ]
        return httpx.Response(200, content="".join(lines).encode("utf-8"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=0,
        provider_retry_backoff_factor=0.01,
        freeLLMAPI_model="auto",
        freeLLMAPI_fallback_models=["fallback-stream"],
        freeLLMAPI_auto_discover_fallbacks=False,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    async def run_stream():
        events = []
        async for ev in provider.stream_respond(ProviderRequest(message="test")):
            events.append(ev)
        return events

    events = asyncio.run(run_stream())
    text_deltas = [ev.text for ev in events if ev.kind == "text_delta"]
    assert text_deltas == ["Streamed with fallback"]
    assert attempted_models == ["auto", "fallback-stream"]


def test_streaming_failure_after_token_yield_does_not_restart_with_fallback():
    attempted_models = []

    def handler(request: httpx.Request):
        body = json.loads(request.content.decode("utf-8"))
        model = body.get("model")
        attempted_models.append(model)
        # Emits one token then closes connection prematurely
        lines = [
            'data: {"id":"s1","choices":[{"delta":{"content":"Chunk 1"}}]}\n\n',
        ]
        return httpx.Response(200, content="".join(lines).encode("utf-8"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=1,
        provider_retry_backoff_factor=0.01,
        freeLLMAPI_model="auto",
        freeLLMAPI_fallback_models=["fallback-should-not-run"],
        freeLLMAPI_auto_discover_fallbacks=False,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    async def run_stream():
        events = []
        async for ev in provider.stream_respond(ProviderRequest(message="test")):
            events.append(ev)
        return events

    events = asyncio.run(run_stream())
    # Emitted Chunk 1 once and did NOT restart with fallback-should-not-run
    assert [ev.text for ev in events if ev.kind == "text_delta"] == ["Chunk 1"]
    assert attempted_models == ["auto"]


def test_fallback_when_model_returns_404_or_503():
    attempted_models = []

    def handler(request: httpx.Request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        body = json.loads(request.content.decode("utf-8"))
        model = body.get("model")
        attempted_models.append(model)
        if model == "auto":
            # FreeLLMAPI router returns 404 because upstream model is removed or catalog stale
            return httpx.Response(404, json={"error": {"message": "Model not found upstream"}})
        elif model == "fallback-1":
            # Overloaded upstream model
            return httpx.Response(503, json={"error": {"message": "Model overloaded"}})
        elif model == "fallback-2":
            return httpx.Response(200, json={
                "id": "resp-fb2",
                "choices": [{"message": {"content": "Success after 404 and 503", "tool_calls": []}}],
            })
        return httpx.Response(404, json={"error": "Not found"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=0,
        provider_retry_backoff_factor=0.01,
        freeLLMAPI_model="auto",
        freeLLMAPI_fallback_models=["fallback-1", "fallback-2"],
        freeLLMAPI_auto_discover_fallbacks=False,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    resp = asyncio.run(provider.respond(ProviderRequest(message="test")))
    assert resp.text == "Success after 404 and 503"
    assert attempted_models == ["auto", "fallback-1", "fallback-2"]

