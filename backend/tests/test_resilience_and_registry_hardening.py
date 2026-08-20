import asyncio
import json
import httpx
import pytest
from sqlalchemy import select

from app.agent import AgentEngine
from app.config import Settings
from app.database import SessionLocal, migrate
from app.models import Memory, Task, TaskStatus
from app.providers import (
    FreeLLMAPIProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ToolCall,
)
from app.security import PermissionLevel
from app.tools import (
    TOOLS,
    Tool,
    ToolRegistry,
    _memory_save,
    recall_memories,
    tool_metadata,
)


# ==========================================
# 1. PROVIDER RESILIENCE & RETRY TESTS
# ==========================================

def test_freellmapi_transient_connection_failure_then_success():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Connection refused", request=request)
        return httpx.Response(200, json={
            "id": "resp-1",
            "choices": [{"message": {"content": "Success after retry", "tool_calls": []}}],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=2,
        provider_retry_backoff_factor=0.01,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    response = asyncio.run(provider.respond(ProviderRequest(message="Hello")))
    assert response.text == "Success after retry"
    assert call_count == 2


def test_freellmapi_transient_500_then_success():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json={
            "id": "resp-1",
            "choices": [{"message": {"content": "Recovered from 503", "tool_calls": []}}],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=3,
        provider_retry_backoff_factor=0.01,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    response = asyncio.run(provider.respond(ProviderRequest(message="Hello")))
    assert response.text == "Recovered from 503"
    assert call_count == 3


def test_freellmapi_repeated_failure_exhausts_retries():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=2,
        provider_retry_backoff_factor=0.01,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.respond(ProviderRequest(message="Hello")))
    assert "HTTP 500" in str(exc_info.value)
    assert call_count == 3  # Initial attempt + 2 retries


def test_freellmapi_4xx_not_retried():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, json={"error": {"message": "Bad Request: invalid schema"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=3,
        provider_retry_backoff_factor=0.01,
        freeLLMAPI_auto_discover_fallbacks=False,
        freeLLMAPI_fallback_models=[],
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.respond(ProviderRequest(message="Hello")))
    assert "Bad Request: invalid schema" in str(exc_info.value)
    assert call_count == 1


def test_freellmapi_http429_falls_back_to_next_candidate():
    tried_models = []

    def handler(request: httpx.Request):
        payload = json.loads(request.content)
        model = payload.get("model")
        tried_models.append(model)
        if model == "model-rate-limited":
            return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})
        return httpx.Response(200, json={
            "id": "chatcmpl-fallback-ok",
            "choices": [{"message": {"role": "assistant", "content": "Fallback succeeded"}}],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        freeLLMAPI_model="model-rate-limited",
        freeLLMAPI_fallback_models=["model-available"],
        freeLLMAPI_auto_discover_fallbacks=False,
        provider_max_retries=0,
        provider_retry_backoff_factor=0.01,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    resp = asyncio.run(provider.respond(ProviderRequest(
        message="test request",
        tools=[{"name": "test_tool", "description": "test", "parameters": {}}],
    )))
    assert resp.text == "Fallback succeeded"
    assert tried_models == ["model-rate-limited", "model-available"]


def test_freellmapi_http400_raises_immediately_as_invalid_request():
    tried_models = []

    def handler(request: httpx.Request):
        payload = json.loads(request.content)
        model = payload.get("model")
        tried_models.append(model)
        return httpx.Response(400, json={"error": {"message": "invalid_request: schema invalid"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        freeLLMAPI_model="model-primary",
        freeLLMAPI_fallback_models=["model-fallback"],
        freeLLMAPI_auto_discover_fallbacks=False,
        provider_max_retries=1,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.respond(ProviderRequest(message="test")))
    assert "FreeLLMAPI returned HTTP 400" in str(exc_info.value)
    assert "invalid_request: schema invalid" in str(exc_info.value)
    # HTTP 400 must NOT fall back or be classified as rate-limited
    assert tried_models == ["model-primary"]



def test_freellmapi_tool_serialization_always_wraps_in_function_object():
    provider = FreeLLMAPIProvider(settings=Settings(freeLLMAPI_api_key="test-key"))
    raw_defs = [
        {"type": "function", "name": "computer.screenshot", "description": "take screenshot", "parameters": {"type": "object"}},
        {"type": "function", "function": {"name": "terminal.run", "description": "run shell", "parameters": {"type": "object"}}},
    ]
    payload = provider._payload_chat(ProviderRequest(message="test", tools=raw_defs))
    assert "tools" in payload
    assert len(payload["tools"]) == 2
    # Both tools must have the nested "function" wrapper required by Chat Completions
    for t in payload["tools"]:
        assert t["type"] == "function"
        assert "function" in t
        assert "name" in t["function"]
        assert "description" in t["function"]
        assert "parameters" in t["function"]



def test_freellmapi_auth_error_not_retried():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": "Invalid API key"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="bad-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=3,
        provider_retry_backoff_factor=0.01,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    with pytest.raises(ProviderAuthenticationError):
        asyncio.run(provider.respond(ProviderRequest(message="Hello")))
    assert call_count == 1


def test_freellmapi_streaming_midstream_error_does_not_duplicate():
    call_count = 0

    def handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        # SSE stream that emits half a chunk then disconnects/errors
        lines = [
            'data: {"id":"s1","choices":[{"delta":{"content":"Part 1"}}]}\n\n',
        ]
        return httpx.Response(200, content="".join(lines).encode("utf-8"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        provider_max_retries=3,
        provider_retry_backoff_factor=0.01,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    async def run_stream():
        events = []
        async for ev in provider.stream_respond(ProviderRequest(message="Hello")):
            events.append(ev)
        return events

    events = asyncio.run(run_stream())
    text_deltas = [ev.text for ev in events if ev.kind == "text_delta"]
    # Only "Part 1" was yielded once
    assert text_deltas == ["Part 1"]


# ==========================================
# 2. MEMORY RETRIEVAL TESTS (FTS5 / Ranking)
# ==========================================

def test_memory_fts5_ranking_and_exact_keyword():
    migrate()
    db = SessionLocal()

    # Clean up test table
    db.connection().exec_driver_sql("DELETE FROM memories_fts")
    for m in db.scalars(select(Memory)).all():
        db.delete(m)
    db.commit()

    # Save distinct memories
    _memory_save("User prefers dark mode in the IDE and editor.", category="preference")
    _memory_save("User works as a Python backend engineer on microservices.", category="fact")
    _memory_save("Favorite food is sushi and Italian pasta.", category="preference")

    # Search for "python engineer"
    recalled = recall_memories("python engineer", limit=5)
    assert len(recalled) >= 1
    assert "Python backend engineer" in recalled[0]["content"]

    # Search for "dark mode"
    recalled_dark = recall_memories("dark mode", limit=5)
    assert len(recalled_dark) >= 1
    assert "dark mode" in recalled_dark[0]["content"]

    db.close()


def test_memory_empty_and_irrelevant_queries():
    migrate()
    recalled = recall_memories("", limit=3)
    assert isinstance(recalled, list)

    recalled_nomatch = recall_memories("nonexistentterm12345xyz", limit=3)
    assert isinstance(recalled_nomatch, list)


def test_memory_migration_populates_existing_records():
    db = SessionLocal()
    # Insert direct memory without fts
    m = Memory(content="Legacy memory created before FTS5 table existed.", category="legacy")
    db.add(m)
    db.commit()
    db.refresh(m)

    # Run migrate()
    migrate()

    # Verify query finds legacy memory
    recalled = recall_memories("Legacy memory created before FTS5", limit=5)
    assert any("Legacy memory" in r["content"] for r in recalled)
    db.close()


# ==========================================
# 3. TOOL REGISTRY TESTS
# ==========================================

def test_tool_registry_registration_and_lookup():
    reg = ToolRegistry()
    dummy_tool = Tool(
        name="custom.ping",
        description="Ping pong tool",
        permission=PermissionLevel.LOW,
        input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        execute=lambda: {"pong": True},
    )

    reg.register(dummy_tool)
    assert "custom.ping" in reg
    assert reg.contains("custom.ping")
    assert reg.get("custom.ping") == dummy_tool
    assert reg["custom.ping"] == dummy_tool
    assert len(reg.list()) == 1


def test_tool_registry_unregister():
    reg = ToolRegistry()
    dummy = Tool(
        name="temp.tool",
        description="Temporary",
        permission=PermissionLevel.LOW,
        input_schema={},
        execute=lambda: {},
    )
    reg.register(dummy)
    assert "temp.tool" in reg

    removed = reg.unregister("temp.tool")
    assert removed == dummy
    assert "temp.tool" not in reg
    assert reg.get("temp.tool") is None


def test_tool_registry_duplicate_registration_guard():
    reg = ToolRegistry()
    t1 = Tool(name="tool.a", description="First", permission=PermissionLevel.LOW, input_schema={}, execute=lambda: {})
    t2 = Tool(name="tool.a", description="Second", permission=PermissionLevel.LOW, input_schema={}, execute=lambda: {})

    reg.register(t1)
    with pytest.raises(ValueError) as exc:
        reg.register(t2, overwrite=False)
    assert "already registered" in str(exc.value)

    # Overwrite allowed when explicit
    reg.register(t2, overwrite=True)
    assert reg.get("tool.a").description == "Second"


def test_agent_engine_with_custom_registry():
    custom_reg = ToolRegistry()
    executed_flags = []

    def mock_exec():
        executed_flags.append(True)
        return {"result": "custom tool executed"}

    custom_tool = Tool(
        name="custom.test_action",
        description="Custom action for engine test",
        permission=PermissionLevel.LOW,
        input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        execute=mock_exec,
    )
    custom_reg.register(custom_tool)

    class CustomTurnProvider(FreeLLMAPIProvider):
        async def stream_respond(self, req):
            yield ProviderResponse("resp-1", "Done", tool_calls=[ToolCall("c1", "custom.test_action", {})])

    # AgentEngine accepts custom registry
    engine = AgentEngine(provider=None, registry=custom_reg)
    assert len(engine._definitions()) == 1
    assert engine._definitions()[0]["name"] == "custom.test_action"
    assert engine.registry.get("custom.test_action") == custom_tool


def test_default_tools_registry_backward_compatibility():
    assert isinstance(TOOLS, ToolRegistry)
    assert "filesystem.read" in TOOLS
    assert "terminal.run" in TOOLS
    assert "computer.screenshot" in TOOLS
    assert "computer.inspect_screen" in TOOLS
    assert "computer.locate_element" in TOOLS
    assert "computer.verify_screen_change" in TOOLS
    assert "computer.gui_action_workflow" in TOOLS
    assert "computer.close_browser_tab" in TOOLS
    assert TOOLS["terminal.run"].permission == PermissionLevel.HIGH
    assert len(TOOLS.list()) == 33

    meta = tool_metadata()
    assert len(meta) == 33
    assert any(m["name"] == "terminal.run" and m["permission"] == "high" for m in meta)

    assert any(m["name"] == "computer.screenshot" and m["permission"] == "low" for m in meta)
    assert any(m["name"] == "computer.locate_element" and m["permission"] == "low" for m in meta)
    assert any(m["name"] == "computer.gui_action_workflow" and m["permission"] == "medium" for m in meta)
    assert any(m["name"] == "computer.close_browser_tab" and m["permission"] == "medium" for m in meta)



def test_freellmapi_sanitizes_reasoning_content_from_assistant_messages():
    provider = FreeLLMAPIProvider(settings=Settings(freeLLMAPI_api_key="test-key"))
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi", "reasoning_content": "internal chain of thought", "channel": "analysis", "refusal": None},
    ]
    payload = provider._payload_chat(ProviderRequest(message="next", messages=messages))
    asst_msg = payload["messages"][2]  # index 0 is system, 1 is user, 2 is assistant
    assert asst_msg["role"] == "assistant"
    assert asst_msg["content"] == "hi"
    assert "reasoning_content" not in asst_msg
    assert "channel" not in asst_msg
    assert "refusal" not in asst_msg


def test_freellmapi_sanitizes_tool_calls_with_reasoning_content():
    provider = FreeLLMAPIProvider(settings=Settings(freeLLMAPI_api_key="test-key"))
    messages = [
        {"role": "user", "content": "close Claude tab"},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Locating Claude tab on Brave browser...",
            "channel": "thought",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "computer.locate_element", "arguments": '{"element_description": "Claude tab"}'},
                    "reasoning_content": "extra nested field",
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"found": true}', "reasoning": "bad field"},
    ]
    payload = provider._payload_chat(ProviderRequest(message="close Claude tab", messages=messages))
    
    # Verify assistant message has valid tool_calls but no reasoning_content
    asst_msg = payload["messages"][2]
    assert asst_msg["role"] == "assistant"
    assert len(asst_msg["tool_calls"]) == 1
    assert asst_msg["tool_calls"][0]["function"]["name"] == "computer.locate_element"
    assert "reasoning_content" not in asst_msg
    assert "reasoning_content" not in asst_msg["tool_calls"][0]

    # Verify tool message
    tool_msg = payload["messages"][3]
    assert tool_msg["role"] == "tool"
    assert "reasoning" not in tool_msg


def test_freellmapi_sanitizes_multi_turn_history_with_reasoning_content():
    provider = FreeLLMAPIProvider(settings=Settings(freeLLMAPI_api_key="test-key"))
    # Build 8-turn conversation with contaminated fields in message 8
    history = [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "resp 1", "reasoning_content": "thought 1"},
        {"role": "tool", "tool_call_id": "t1", "content": "tool 1"},
        {"role": "assistant", "content": "resp 2", "reasoning_content": "thought 2"},
        {"role": "tool", "tool_call_id": "t2", "content": "tool 2"},
        {"role": "assistant", "content": "resp 3", "reasoning_content": "thought 3"},
        {"role": "tool", "tool_call_id": "t3", "content": "tool 3"},
        {"role": "assistant", "content": "resp 4", "reasoning_content": "thought 4", "channel": "analysis"},
    ]
    payload = provider._payload_chat(ProviderRequest(message="turn 5", messages=history))
    
    # Must have system + 8 history turns = 9 messages
    assert len(payload["messages"]) == 9
    for idx, msg in enumerate(payload["messages"]):
        assert "reasoning_content" not in msg, f"Found reasoning_content in message {idx}"
        assert "channel" not in msg, f"Found channel in message {idx}"
        assert "refusal" not in msg, f"Found refusal in message {idx}"


def test_freellmapi_fallback_models_receive_sanitized_payload():
    received_payloads = []

    def handler(request: httpx.Request):
        p = json.loads(request.content)
        received_payloads.append(p)
        if p.get("model") == "model-a":
            return httpx.Response(429, json={"error": {"message": "Rate limited"}})
        return httpx.Response(200, json={
            "id": "cmpl-ok",
            "choices": [{"message": {"role": "assistant", "content": "fallback success"}}],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        freeLLMAPI_api_key="test-key",
        freeLLMAPI_base_url="http://test-server/v1",
        freeLLMAPI_model="model-a",
        freeLLMAPI_fallback_models=["model-b"],
        freeLLMAPI_auto_discover_fallbacks=False,
        provider_max_retries=0,
    )
    provider = FreeLLMAPIProvider(settings=settings, client=client)

    contaminated_messages = [
        {"role": "user", "content": "test"},
        {"role": "assistant", "content": "thinking", "reasoning_content": "leaked thought"},
    ]
    resp = asyncio.run(provider.respond(ProviderRequest(message="test", messages=contaminated_messages)))
    assert resp.text == "fallback success"
    assert len(received_payloads) == 2  # Primary model-a and Fallback model-b

    # Both primary and fallback payloads must be strictly sanitized
    for idx, p in enumerate(received_payloads):
        for m_idx, m in enumerate(p["messages"]):
            assert "reasoning_content" not in m, f"Payload {idx} message {m_idx} contained reasoning_content"



def test_freellmapi_payload_recursively_free_of_forbidden_keys():
    provider = FreeLLMAPIProvider(settings=Settings(freeLLMAPI_api_key="test-key"))
    nested_contaminated = [
        {
            "role": "assistant",
            "content": "action",
            "reasoning_content": "top level reasoning",
            "channel": "top channel",
            "refusal": "top refusal",
            "thought": "top thought",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "test",
                        "arguments": "{}",
                        "reasoning_content": "nested in function",
                    },
                    "channel": "nested channel",
                }
            ],
        }
    ]
    payload = provider._payload_chat(ProviderRequest(message="test", messages=nested_contaminated))
    
    # Recursive walk
    forbidden = {"reasoning_content", "reasoning", "channel", "refusal", "thought", "signature"}
    found = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in forbidden:
                    found.append(k)
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    assert found == [], f"Forbidden keys found in payload: {found}"


def test_freellmapi_strips_think_tags_from_messages():
    from app.providers.freellmapi import strip_think_tags
    assert strip_think_tags("<think>some internal thoughts</think>Hello world") == "Hello world"
    assert strip_think_tags("<thought>nested thinking</thought>Clean message") == "Clean message"
    assert strip_think_tags("<think>unclosed thought without end tag") == ""

    provider = FreeLLMAPIProvider(settings=Settings(freeLLMAPI_api_key="test-key"))
    messages = [
        {"role": "user", "content": "close the tab"},
        {
            "role": "assistant",
            "content": "<think>\nThinking about capturing screenshot\n</think>\nI will capture a screenshot.",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "computer.screenshot", "arguments": "{}"}}],
        },
    ]
    payload = provider._payload_chat(ProviderRequest(message="close the tab", messages=messages))
    asst_content = payload["messages"][2]["content"]
    assert "<think>" not in asst_content
    assert "</think>" not in asst_content
    assert asst_content == "I will capture a screenshot."





