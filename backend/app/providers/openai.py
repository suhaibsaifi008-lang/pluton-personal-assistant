"""OpenAI Responses API provider implementation."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from ..config import Settings, get_settings
from .base import (
    AIProvider,
    OPENAI_INSTRUCTIONS,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderEvent,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ToolCall,
)


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def model(self) -> str:
        return self.settings.openai_model

    @property
    def supports_vision(self) -> bool:
        return True

    def _payload(self, request: ProviderRequest, stream: bool = False) -> dict[str, Any]:
        from .base import image_to_data_uri

        instructions = OPENAI_INSTRUCTIONS
        if request.context:
            instructions = f"{instructions}\n\nRelevant saved memories:\n{request.context}"
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "tools": request.tools,
        }
        if stream:
            payload["stream"] = True
        if request.previous_response_id:
            payload["previous_response_id"] = request.previous_response_id
            payload["input"] = request.tool_outputs
        else:
            if request.images:
                content_parts: list[dict[str, Any]] = [{"type": "text", "text": request.message}]
                for img in request.images:
                    content_parts.append({"type": "image_url", "image_url": {"url": image_to_data_uri(img)}})
                user_msg = {"role": "user", "content": content_parts}
            else:
                user_msg = {"role": "user", "content": request.message}
            payload["input"] = [*request.history, user_msg]
        return payload


    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        if not self.settings.openai_api_key:
            raise ProviderConfigurationError("No AI provider key is configured. Add PLUTON_OPENAI_API_KEY to .env and restart the backend.")
        return self._parse_response(await self._post("/responses", self._payload(request)))

    async def stream_respond(self, request: ProviderRequest) -> AsyncIterator[ProviderEvent]:
        if not self.settings.openai_api_key:
            raise ProviderConfigurationError("No AI provider key is configured. Add PLUTON_OPENAI_API_KEY to .env and restart the backend.")
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.settings.provider_timeout_seconds)
        calls: dict[str, dict[str, str]] = {}
        try:
            async with client.stream("POST", f"{self.settings.openai_base_url.rstrip('/')}/responses", headers=headers, json=self._payload(request, stream=True)) as response:
                if response.status_code in (401, 403):
                    raise ProviderAuthenticationError("The configured AI provider key was rejected. Check PLUTON_OPENAI_API_KEY.")
                if response.status_code == 429:
                    raise ProviderRateLimitError("The AI provider rate limit was reached. Please wait and try again.")
                if response.status_code >= 400:
                    raise ProviderError("The AI provider could not process this request. Please try again later.")
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type")
                    if event_type == "response.output_text.delta":
                        yield ProviderEvent(kind="text_delta", text=event.get("delta", ""))
                    elif event_type == "response.output_item.added":
                        item = event.get("item", {})
                        if item.get("type") == "function_call":
                            call_id = item.get("call_id", "")
                            calls[call_id] = {"call_id": call_id, "name": item.get("name", ""), "args": ""}
                    elif event_type == "response.function_call_arguments.delta":
                        call_id = event.get("call_id", "")
                        if call_id in calls:
                            calls[call_id]["args"] += event.get("delta", "")
                    elif event_type == "response.function_call_arguments.done":
                        call_id = event.get("call_id", "")
                        if call_id in calls:
                            calls[call_id]["args"] = event.get("arguments", "")
                    elif event_type == "response.completed":
                        response_id = (event.get("response") or {}).get("id", "")
                        tool_calls = []
                        for item in calls.values():
                            try:
                                arguments = json.loads(item.get("args") or "{}")
                            except json.JSONDecodeError:
                                arguments = {}
                            tool_calls.append(ToolCall(item["call_id"], item["name"], arguments))
                        yield ProviderEvent(kind="tool_calls", tool_calls=tool_calls, response_id=response_id)
                    elif event_type == "response.failed":
                        raise ProviderError("The AI provider could not complete the response. Please try again later.")
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError("The AI provider took too long to respond. Please try again.") from error
        except httpx.RequestError as error:
            raise ProviderError("PLUTON could not reach the configured AI provider. Check your connection and provider settings.") from error
        finally:
            if owns_client:
                await client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.settings.provider_timeout_seconds)
        try:
            response = await client.post(f"{self.settings.openai_base_url.rstrip('/')}{path}", headers=headers, json=payload)
            if response.status_code in (401, 403):
                raise ProviderAuthenticationError("The configured AI provider key was rejected. Check PLUTON_OPENAI_API_KEY.")
            if response.status_code == 429:
                raise ProviderRateLimitError("The AI provider rate limit was reached. Please wait and try again.")
            if response.status_code >= 400:
                raise ProviderError("The AI provider could not process this request. Please try again later.")
            return response.json()
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError("The AI provider took too long to respond. Please try again.") from error
        except httpx.RequestError as error:
            raise ProviderError("PLUTON could not reach the configured AI provider. Check your connection and provider settings.") from error
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _parse_response(payload: dict[str, Any]) -> ProviderResponse:
        calls = []
        for item in payload.get("output", []):
            if item.get("type") == "function_call":
                try:
                    arguments = json.loads(item.get("arguments", "{}"))
                except json.JSONDecodeError:
                    arguments = {}
                calls.append(ToolCall(item["call_id"], item["name"], arguments))
        usage = {key: value for key, value in (payload.get("usage") or {}).items() if isinstance(value, int)}
        return ProviderResponse(payload.get("id", ""), payload.get("output_text", ""), calls, usage)
