from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    llm_provider: str = Field("anthropic", alias="LLM_PROVIDER")  # anthropic | openai-compat
    llm_api_key: str = Field(..., alias="LLM_API_KEY")
    llm_base_url: str = Field("", alias="LLM_BASE_URL")  # only for openai-compat
    main_model: str = Field("claude-sonnet-4-6", alias="PACER_MAIN_MODEL")
    router_model: str = Field("claude-haiku-4-5-20251001", alias="PACER_ROUTER_MODEL")
    internal_token: str = Field(..., alias="PACER_INTERNAL_TOKEN")
    host: str = Field("127.0.0.1", alias="PACER_HOST")
    port: int = Field(8000, alias="PACER_PORT")
    pin_length: int = Field(6, alias="PACER_PIN_LENGTH")
    cors_origins: str = Field("", alias="PACER_CORS_ORIGINS")
    token_ttl_seconds: int = Field(60 * 60 * 24 * 7, alias="PACER_TOKEN_TTL_SECONDS")
    upload_max_bytes: int = Field(10 * 1024 * 1024, alias="PACER_UPLOAD_MAX_BYTES")
    login_max_attempts: int = Field(5, alias="PACER_LOGIN_MAX_ATTEMPTS")
    login_lockout_seconds: int = Field(300, alias="PACER_LOGIN_LOCKOUT_SECONDS")
    memory_summarize_interval: int = Field(3, alias="PACER_MEMORY_SUMMARIZE_INTERVAL")
    handoff_enabled: bool = Field(False, alias="PACER_HANDOFF_ENABLED")


def get_settings() -> Settings:
    return Settings()
