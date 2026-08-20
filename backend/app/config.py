from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            ".env",
            "../.env",
            str(Path(__file__).resolve().parent.parent.parent / ".env"),
            str(Path(__file__).resolve().parent.parent / ".env"),
        ),
        env_prefix="PLUTON_",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/pluton.db"
    allowed_workspace: Path = Path(".")
    ai_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    provider_timeout_seconds: float = 45.0
    log_level: str = "INFO"
    max_agent_steps: int = 20
    terminal_timeout_seconds: float = 20.0

    web_timeout_seconds: float = 15.0
    max_tool_output_chars: int = 8000
    memory_context_limit: int = 5
    max_history_turns: int = 10
    max_history_tokens: int = 4000
    max_consecutive_identical_tool_calls: int = 3
    provider_max_retries: int = 3
    provider_retry_backoff_factor: float = 0.5
    provider_retry_max_backoff: float = 2.0
    freeLLMAPI_base_url: str = "http://localhost:8080"
    freeLLMAPI_api_key: str | None = None
    freeLLMAPI_timeout_seconds: float = 60.0
    freeLLMAPI_model: str = "auto"
    freeLLMAPI_fallback_models: list[str] = [
        "llama-3.1-70b",
        "codestral-latest",
        "qwen3.6-27b",
        "compound",
        "gemma-4-31b-it",
    ]
    freeLLMAPI_auto_discover_fallbacks: bool = True



@lru_cache
def get_settings() -> Settings:
    return Settings()
