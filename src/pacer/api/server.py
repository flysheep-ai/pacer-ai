from __future__ import annotations
from fastapi import FastAPI
from pacer.api import deps
from pacer.api.routes.auth import router as auth_router
from pacer.api.routes.message import router as message_router
from pacer.api.routes.events import router as events_router
from pacer.session.events import EventBus
from pacer.llm.client import LLMClient
from pacer.config import get_settings


def create_app(database_url: str | None = None) -> FastAPI:
    deps.init_db(database_url)
    app = FastAPI(title="pacer-ai")
    settings = get_settings()
    app.state.event_bus = EventBus()
    app.state.llm = LLMClient(
        api_key=settings.anthropic_api_key, model=settings.main_model,
    )
    app.include_router(auth_router)
    app.include_router(message_router)
    app.include_router(events_router)
    return app
