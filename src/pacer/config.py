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


def get_settings() -> Settings:
    return Settings()
