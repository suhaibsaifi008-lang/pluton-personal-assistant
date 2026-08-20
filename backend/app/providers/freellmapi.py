"""FreeLLMAPI OpenAI Chat Completions provider implementation with retry and model fallback."""
from __future__ import annotations

import asyncio
import json
import re
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


def strip_think_tags(text: str) -> str:
    """Strip <think>...</think> and <thought>...</thought> blocks from text content.
    Prevents FreeLLMAPI proxy from parsing think tags and inserting unwanted
    reasoning_content properties into outgoing messages.
    """
    if not text or not isinstance(text, str):
        return ""
    # Strip closed <think>...</think> and <thought>...</thought>
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thought>[\s\S]*?</thought>", "", cleaned, flags=re.IGNORECASE)
    # Strip unclosed <think>... or <thought>...
    cleaned = re.sub(r"<think>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thought>[\s\S]*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def sanitize_chat_completions_messages(raw_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strictly sanitize messages to standard OpenAI Chat Completions API format.
    Guarantees that no provider-specific keys (e.g. reasoning_content, channel, refusal, thought)
    or think-tag artifacts leak to FreeLLMAPI or upstream providers like Groq.
    """
    sanitized: list[dict[str, Any]] = []
    for m in raw_messages:
        role = m.get("role", "user")
        content = m.get("content")

        if role == "system":
            sanitized.append({
                "role": "system",
                "content": strip_think_tags(str(content)) if content is not None else "",
            })
        elif role == "user":
            if isinstance(content, list):
                sanitized_parts = []
                for part in content:
                    if isinstance(part, dict):
                        p_type = part.get("type", "text")
                        if p_type == "text":
                            sanitized_parts.append({"type": "text", "text": strip_think_tags(str(part.get("text", "")))})
                        elif p_type == "image_url":
                            img_obj = part.get("image_url", {})
                            url = img_obj.get("url", "") if isinstance(img_obj, dict) else str(img_obj)
                            sanitized_parts.append({"type": "image_url", "image_url": {"url": url}})
                sanitized.append({"role": "user", "content": sanitized_parts})
            else:
                sanitized.append({"role": "user", "content": strip_think_tags(str(content)) if content is not None else ""})
        elif role == "assistant":
            cleaned_text = strip_think_tags(str(content)) if content is not None else ""
            asst_msg: dict[str, Any] = {
                "role": "assistant",
                "content": cleaned_text,
            }
            if m.get("tool_calls"):
                cleaned_calls = []
                for tc in m["tool_calls"]:
                    if isinstance(tc, dict):
                        fn = tc.get("function", {})
                        cleaned_calls.append({
                            "id": str(tc.get("id", "")),
                            "type": "function",
                            "function": {
                                "name": str(fn.get("name", "")),
                                "arguments": str(fn.get("arguments", "{}")),
                            },
                        })
                asst_msg["tool_calls"] = cleaned_calls
            sanitized.append(asst_msg)
        elif role == "tool":
            sanitized.append({
                "role": "tool",
                "content": str(content) if content is not None else "",
                "tool_call_id": str(m.get("tool_call_id", "")),
            })
        else:
            sanitized.append({
                "role": "user",
                "content": strip_think_tags(str(content)) if content is not None else "",
            })
    return sanitized



def strip_forbidden_keys(obj: Any, forbidden: set[str]) -> Any:
    """Recursively strip forbidden provider-specific keys at any nesting level."""
    if isinstance(obj, dict):
        return {k: strip_forbidden_keys(v, forbidden) for k, v in obj.items() if k not in forbidden}
    elif isinstance(obj, list):
        return [strip_forbidden_keys(elem, forbidden) for elem in obj]
    return obj


class FreeLLMAPIProvider(AIProvider):
    name = "freeLLMAPI"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client
        self._selected_model: str = self.settings.freeLLMAPI_model

    @property
    def model(self) -> str:
        return self._selected_model

    @property
    def supports_vision(self) -> bool:
        return bool(self.settings.freeLLMAPI_api_key)

    @model.setter
    def model(self, value: str):
        self._selected_model = value

    def _payload_chat(self, request: ProviderRequest, model: str | None = None, stream: bool = False) -> dict[str, Any]:
        from .base import image_to_data_uri

        instructions = OPENAI_INSTRUCTIONS
        if request.context:
            instructions = f"{instructions}\n\nRelevant saved memories:\n{request.context}"
        raw_messages: list[dict[str, Any]] = []
        if request.messages:
            raw_messages = [{"role": "system", "content": instructions}, *request.messages]
        else:
            raw_messages = [{"role": "system", "content": instructions}]
            for item in request.history:
                raw_messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})
            if request.images:
                content_parts: list[dict[str, Any]] = [{"type": "text", "text": request.message}]
                for img in request.images:
                    content_parts.append({"type": "image_url", "image_url": {"url": image_to_data_uri(img)}})
                raw_messages.append({"role": "user", "content": content_parts})
            else:
                raw_messages.append({"role": "user", "content": request.message})
            if request.tool_outputs:
                synth_calls = []
                for output in request.tool_outputs:
                    synth_calls.append({
                        "id": output.get("call_id", ""),
                        "type": "function",
                        "function": {
                            "name": output.get("name", ""),
                            "arguments": output.get("arguments", "{}"),
                        },
                    })
                raw_messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": synth_calls,
                })
                for output in request.tool_outputs:
                    raw_messages.append({
                        "role": "tool",
                        "tool_call_id": output.get("call_id", ""),
                        "content": output.get("output", ""),
                    })

        messages = sanitize_chat_completions_messages(raw_messages)

        tools: list[dict[str, Any]] = []
        for tool in request.tools:
            if "function" in tool:
                tools.append(tool)
            elif "name" in tool:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    },
                })
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        if stream:
            payload["stream"] = True
        
        forbidden_keys = {"reasoning_content", "reasoning", "channel", "refusal", "thought", "signature"}
        return strip_forbidden_keys(payload, forbidden_keys)


    def _parse_chat_response(self, payload: dict[str, Any]) -> ProviderResponse:
        response_id = payload.get("id", "")
        choices = payload.get("choices", [])
        message = choices[0].get("message", {}) if choices else {}
        text = message.get("content") or ""
        calls: list[ToolCall] = []
        for item in message.get("tool_calls", []) or []:
            fn = item.get("function", {})
            call_id = item.get("id", "")
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, dict):
                args = raw_args
            else:
                try:
                    args = json.loads(raw_args or "{}")
                except json.JSONDecodeError:
                    args = {}
            calls.append(ToolCall(call_id=call_id, name=name, arguments=args))
        usage = {key: value for key, value in (payload.get("usage") or {}).items() if isinstance(value, int)}
        return ProviderResponse(response_id=response_id, text=text, tool_calls=calls, usage=usage)

    async def _get_model_candidates(self, client: httpx.AsyncClient, headers: dict[str, str], is_vision: bool = False) -> list[str]:
        """Collect candidate models starting with the primary model, followed by configured and discovered fallbacks."""
        primary = self.model
        candidates = [primary]

        # 1. Add configured fallback models
        for m in (self.settings.freeLLMAPI_fallback_models or []):
            if m and m not in candidates:
                candidates.append(m)

        # 2. Dynamically discover available models if enabled
        if self.settings.freeLLMAPI_auto_discover_fallbacks:
            try:
                base = self.settings.freeLLMAPI_base_url.rstrip("/")
                resp = await client.get(f"{base}/models", headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    for item in data:
                        m_id = item.get("id")
                        if m_id and item.get("available", False) and m_id not in candidates:
                            candidates.append(m_id)
            except Exception:
                pass

        if is_vision:
            # Prioritize models known to support multimodal vision inputs
            vision_keywords = ("gemini", "vision", "vl", "gpt-4", "glm-4.6v", "claude")
            vision_models = [m for m in candidates if any(k in m.lower() for k in vision_keywords) or m in ("auto", "fusion")]
            non_vision = [m for m in candidates if m not in vision_models]
            candidates = vision_models + non_vision

        return candidates

    async def _post_with_model(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        path: str,
        payload: dict[str, Any],
    ) -> tuple[bool, dict[str, Any] | None]:
        """Execute POST for a specific model with exponential backoff for transient errors.
        Returns (is_rate_limited, json_response).
        """
        max_retries = self.settings.provider_max_retries
        backoff_factor = self.settings.provider_retry_backoff_factor
        max_backoff = self.settings.provider_retry_max_backoff
        base_url = self.settings.freeLLMAPI_base_url.rstrip("/")
        last_error = None
        req_model = payload.get("model", "unknown")

        # Diagnostic log (no sensitive data)
        msg_count = len(payload.get("messages", []))
        tool_count = len(payload.get("tools", []))
        forbidden = [k for k in ("reasoning_content", "reasoning", "channel", "refusal", "thought") if k in json.dumps(payload)]
        print(f"[FreeLLMAPI DIAG] POST {path} | model={req_model} | msgs={msg_count} | tools={tool_count} | forbidden_keys={forbidden}")

        for attempt in range(max_retries + 1):
            try:
                response = await client.post(f"{base_url}{path}", headers=headers, json=payload)
                print(f"[FreeLLMAPI DIAG] Response status={response.status_code} for model={req_model} (attempt {attempt})")
                if response.status_code in (401, 403):
                    raise ProviderAuthenticationError("FreeLLMAPI API key rejected or endpoint unavailable.")
                if response.status_code == 429:
                    # Model rate limited / busy: immediately yield to next candidate in fallback chain
                    return True, None
                if response.status_code in (404, 503):
                    # Catalog route unavailable or temporary overload
                    if attempt < max_retries:
                        await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                        continue
                    return True, None
                if response.status_code >= 500:
                    if attempt < max_retries:
                        await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                        continue
                    raise ProviderError(f"FreeLLMAPI returned HTTP {response.status_code}.")
                if response.status_code >= 400:
                    err_msg = ""
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("error", {}).get("message", "")
                    except Exception:
                        pass
                    if not err_msg:
                        err_msg = response.text[:200]
                    raise ProviderError(f"FreeLLMAPI returned HTTP {response.status_code}: {err_msg}")
                return False, response.json()

            except (ProviderAuthenticationError, ProviderConfigurationError):
                raise
            except httpx.TimeoutException as error:
                last_error = ProviderTimeoutError("FreeLLMAPI took too long to respond.")
                if attempt < max_retries:
                    await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                    continue
                raise last_error from error
            except httpx.RequestError as error:
                last_error = ProviderError("PLUTON could not reach FreeLLMAPI. Check the base URL and network.")
                if attempt < max_retries:
                    await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                    continue
                raise last_error from error

        if last_error:
            raise last_error
        return True, None

    async def respond(self, request: ProviderRequest) -> ProviderResponse:
        if not self.settings.freeLLMAPI_api_key:
            raise ProviderConfigurationError("No AI provider key is configured. Add PLUTON_FREELLMAPI_API_KEY to .env and restart the backend.")

        headers = {"Content-Type": "application/json"}
        if self.settings.freeLLMAPI_api_key:
            headers["Authorization"] = f"Bearer {self.settings.freeLLMAPI_api_key}"

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.settings.freeLLMAPI_timeout_seconds)

        try:
            is_vis = bool(request.images)
            # 1. Try primary model first without extra overhead (or first vision model if vision request)
            if is_vis:
                candidates = await self._get_model_candidates(client, headers, is_vision=True)
                primary_model = candidates[0] if candidates else self.model
            else:
                candidates = None
                primary_model = self.model

            payload = self._payload_chat(request, model=primary_model, stream=False)
            is_rate_limited, json_response = await self._post_with_model(client, headers, "/chat/completions", payload)
            if not is_rate_limited and json_response is not None:
                return self._parse_chat_response(json_response)

            # 2. If rate-limited, lazily discover and try fallback models
            if candidates is None:
                candidates = await self._get_model_candidates(client, headers, is_vision=is_vis)
            for candidate in candidates:
                if candidate == primary_model:
                    continue
                payload = self._payload_chat(request, model=candidate, stream=False)
                is_rate_limited, json_response = await self._post_with_model(client, headers, "/chat/completions", payload)
                if is_rate_limited:
                    continue
                if json_response is not None:
                    return self._parse_chat_response(json_response)

            raise ProviderRateLimitError("The AI provider is temporarily rate-limited. Please try again in a moment.")
        finally:
            if owns_client:
                await client.aclose()

    async def stream_respond(self, request: ProviderRequest) -> AsyncIterator[ProviderEvent]:
        if not self.settings.freeLLMAPI_api_key:
            raise ProviderConfigurationError("No AI provider key is configured. Add PLUTON_FREELLMAPI_API_KEY to .env and restart the backend.")

        headers = {"Content-Type": "application/json"}
        if self.settings.freeLLMAPI_api_key:
            headers["Authorization"] = f"Bearer {self.settings.freeLLMAPI_api_key}"

        owns_client = self._client is None
        stream_timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        client = self._client or httpx.AsyncClient(timeout=stream_timeout)
        max_retries = min(self.settings.provider_max_retries, 1)
        backoff_factor = self.settings.provider_retry_backoff_factor
        max_backoff = self.settings.provider_retry_max_backoff
        base_url = self.settings.freeLLMAPI_base_url.rstrip("/")
        is_vis = bool(request.images)

        try:
            candidates: list[str] | None = None
            candidate_index = 0
            current_model = self.model
            if is_vis:
                candidates = await self._get_model_candidates(client, headers, is_vision=True)
                if candidates:
                    current_model = candidates[0]

            while True:
                payload = self._payload_chat(request, model=current_model, stream=True)
                yielded_any = False
                rate_limited = False

                # Diagnostic log (no sensitive data)
                msg_count = len(payload.get("messages", []))
                tool_count = len(payload.get("tools", []))
                forbidden = [k for k in ("reasoning_content", "reasoning", "channel", "refusal", "thought") if k in json.dumps(payload)]
                print(f"[FreeLLMAPI DIAG STREAM] POST /chat/completions | model={current_model} | msgs={msg_count} | tools={tool_count} | forbidden_keys={forbidden}")

                for attempt in range(max_retries + 1):
                    calls_by_index: dict[int, dict[str, str]] = {}
                    response_id = ""
                    try:
                        async with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as response:
                            print(f"[FreeLLMAPI DIAG STREAM] Response status={response.status_code} for model={current_model} (attempt {attempt})")
                            if response.status_code in (401, 403):
                                raise ProviderAuthenticationError("FreeLLMAPI API key rejected or endpoint unavailable.")
                            if response.status_code in (404, 429, 503):
                                if attempt < max_retries:
                                    await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                                    continue
                                rate_limited = True
                                break
                            if response.status_code >= 500:
                                if attempt < max_retries:
                                    await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                                    continue
                                raise ProviderError(f"FreeLLMAPI returned HTTP {response.status_code}.")
                            if response.status_code >= 400:
                                err_body = await response.aread()
                                err_text = err_body.decode(errors="replace")
                                err_msg = ""
                                try:
                                    err_json = json.loads(err_text)
                                    err_msg = err_json.get("error", {}).get("message", "")
                                except Exception:
                                    pass
                                if not err_msg:
                                    err_msg = err_text[:200]
                                print(f"[FreeLLMAPI DIAG STREAM] 4xx error body: {err_msg[:200]}")
                                raise ProviderError(f"FreeLLMAPI returned HTTP {response.status_code}: {err_msg}")





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
                                if not response_id and event.get("id"):
                                    response_id = event["id"]
                                choices = event.get("choices", [])
                                if not choices:
                                    continue
                                choice = choices[0]
                                delta = choice.get("delta", {})
                                if delta.get("content"):
                                    yielded_any = True
                                    yield ProviderEvent(kind="text_delta", text=delta["content"])
                                for tc in delta.get("tool_calls", []) or []:
                                    idx = tc.get("index", 0)
                                    if idx not in calls_by_index:
                                        calls_by_index[idx] = {"call_id": tc.get("id", "") or f"call_{idx}", "name": "", "args": ""}
                                    if tc.get("id"):
                                        calls_by_index[idx]["call_id"] = tc.get("id", "")
                                    fn = tc.get("function", {})
                                    if fn.get("name"):
                                        calls_by_index[idx]["name"] += fn.get("name", "")
                                    if fn.get("arguments"):
                                        calls_by_index[idx]["args"] += fn.get("arguments", "")
                            if calls_by_index:
                                tool_calls = []
                                for item in calls_by_index.values():
                                    try:
                                        arguments = json.loads(item.get("args") or "{}")
                                    except json.JSONDecodeError:
                                        arguments = {}
                                    tool_calls.append(ToolCall(item["call_id"], item["name"], arguments))
                                yielded_any = True
                                yield ProviderEvent(kind="tool_calls", tool_calls=tool_calls, response_id=response_id)
                        # Successful stream completion
                        return
                    except (ProviderAuthenticationError, ProviderConfigurationError):
                        raise
                    except httpx.TimeoutException as error:
                        if not yielded_any and attempt < max_retries:
                            await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                            continue
                        raise ProviderTimeoutError("FreeLLMAPI took too long to respond.") from error
                    except httpx.RequestError as error:
                        if not yielded_any and attempt < max_retries:
                            await asyncio.sleep(min(max_backoff, backoff_factor * (2 ** attempt)))
                            continue
                        raise ProviderError("PLUTON could not reach FreeLLMAPI. Check the base URL and network.") from error

                if rate_limited and not yielded_any:
                    if candidates is None:
                        candidates = await self._get_model_candidates(client, headers)
                        candidate_index = 0
                    else:
                        candidate_index += 1

                    # Find next candidate that isn't the one we just tried
                    next_model = None
                    while candidate_index < len(candidates):
                        cand = candidates[candidate_index]
                        candidate_index += 1
                        if cand != current_model:
                            next_model = cand
                            break

                    if next_model:
                        current_model = next_model
                        continue
                    else:
                        raise ProviderRateLimitError("The AI provider is temporarily rate-limited. Please try again in a moment.")
                elif rate_limited and yielded_any:
                    raise ProviderRateLimitError("The AI provider is temporarily rate-limited. Please try again in a moment.")

            raise ProviderRateLimitError("The AI provider is temporarily rate-limited. Please try again in a moment.")
        finally:
            if owns_client:
                await client.aclose()
