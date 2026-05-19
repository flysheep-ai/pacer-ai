import pytest
from pacer.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-test")
    monkeypatch.setenv("PACER_INTERNAL_TOKEN", "test-token-123")
    monkeypatch.setenv("PACER_MAIN_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("PACER_ROUTER_MODEL", "claude-haiku-4-5-20251001")
    s = Settings()
    assert s.database_url == "sqlite:///./test.db"
    assert s.llm_api_key == "sk-ant-test"
    assert s.main_model == "claude-sonnet-4-6"
    assert s.router_model == "claude-haiku-4-5-20251001"


def test_settings_defaults_for_server(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-test")
    monkeypatch.setenv("PACER_INTERNAL_TOKEN", "test-token-123")
    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8000
