from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pacer.api import deps
from pacer.api.routes.auth import router as auth_router
from pacer.api.routes.message import router as message_router
from pacer.api.routes.events import router as events_router
from pacer.api.routes.internal import router as internal_router
from pacer.api.routes.upload import router as upload_router
from pacer.api.routes.profile import router as profile_router
from pacer.api.routes.sessions import router as sessions_router
from pacer.api.routes.resources import router as resources_router
from pacer.session.events import EventBus
from pacer.skills.loader import SkillsLoader
from pacer.config import get_settings

LEGACY_WEB_DIR = Path(__file__).parent.parent / "web"
NEXT_DIST_DIR = Path(__file__).parent.parent / "web-next" / "dist"


def _create_llm_client(settings):
    if settings.llm_provider == "openai-compat":
        from pacer.llm.openai_client import OpenAICompatClient
        return OpenAICompatClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.main_model,
        )
    else:
        from pacer.llm.client import LLMClient
        return LLMClient(api_key=settings.llm_api_key, model=settings.main_model)


def create_app(database_url: str | None = None) -> FastAPI:
    deps.init_db(database_url)
    app = FastAPI(title="pacer-ai")
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.event_bus = EventBus()
    app.state.llm = _create_llm_client(settings)
    skills_root = Path(__file__).parent.parent / "skills" / "content"
    app.state.skills_loader = SkillsLoader(root=skills_root)

    app.include_router(auth_router)
    app.include_router(message_router)
    app.include_router(events_router)
    app.include_router(internal_router)
    app.include_router(upload_router)
    app.include_router(profile_router)
    app.include_router(sessions_router)
    app.include_router(resources_router)

    # Static mounting MUST come after all include_router() calls — the SPA fallback
    # (/{full_path:path}) would otherwise shadow any later-registered API route.
    if NEXT_DIST_DIR.exists():
        _mount_spa(app, NEXT_DIST_DIR)
    elif LEGACY_WEB_DIR.exists():
        _mount_legacy(app, LEGACY_WEB_DIR)

    return app


def _mount_legacy(app: FastAPI, web_dir: Path) -> None:
    static_dir = web_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def legacy_index():
        return FileResponse(str(web_dir / "index.html"))


def _mount_spa(app: FastAPI, dist_dir: Path) -> None:
    index_path = dist_dir / "index.html"
    if not index_path.exists():
        raise RuntimeError("web-next/dist/index.html missing — run `pnpm build`")

    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def spa_index():
        return FileResponse(str(index_path))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        return FileResponse(str(index_path))
