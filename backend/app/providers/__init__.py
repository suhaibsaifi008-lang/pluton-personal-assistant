"""Provider-neutral model interfaces, implementations, and factory for PLUTON."""
from __future__ import annotations

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
    ProviderVisionUnsupportedError,
    ToolCall,
    image_to_data_uri,
)
from .freellmapi import FreeLLMAPIProvider
from .openai import OpenAIProvider


def create_provider(settings: Settings | None = None) -> AIProvider:
    settings = settings or get_settings()
    if settings.ai_provider.lower() == "openai":
        return OpenAIProvider(settings)
    if settings.ai_provider.lower() == "freellmapi":
        return FreeLLMAPIProvider(settings)
    raise ProviderConfigurationError(f"Unsupported provider '{settings.ai_provider}'. Configure PLUTON_AI_PROVIDER=openai or freeLLMAPI.")


__all__ = [
    "AIProvider",
    "OpenAIProvider",
    "FreeLLMAPIProvider",
    "ProviderError",
    "ProviderConfigurationError",
    "ProviderAuthenticationError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderVisionUnsupportedError",
    "ToolCall",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderEvent",
    "OPENAI_INSTRUCTIONS",
    "image_to_data_uri",
    "create_provider",
]

