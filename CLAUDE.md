# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: pacer-ai

Multi-agent AI study companion for Chinese 高三 (Gaokao prep) students. Three collaborating agents (homeroom teacher / subject teacher / mood companion) share a single conversation; the user perceives one continuous companion, not a bot switcher. Full design: `docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md`.

## Common commands

Backend (run from repo root):
- Install dev deps: `pip install -e '.[dev]'`
- Run API server: `uvicorn pacer.api.server:create_app --factory --reload`
- Run scheduler (separate process): `python -m pacer.scheduler.runner`
- Seed a dev student (id=1, pin=123456): `python scripts/seed_dev_student.py`
- DB migration: `alembic upgrade head` (config in `alembic.ini`, migrations live at `src/pacer/db/migrations/versions/`)
- New migration: `alembic revision --autogenerate -m "<msg>"`
- All tests: `pytest`
- One test: `pytest tests/unit/test_memory.py::test_add_and_retrieve_memory`
- Test layout: `tests/{unit,integration,api,e2e}/`; pytest config in `pyproject.toml` sets `pythonpath=["src"]` and `asyncio_mode=auto`.

Frontend (`src/pacer/web-next/`, uses pnpm):
- Dev server: `pnpm dev` (Vite, default port 5173)
- Production build: `pnpm build` (runs `vue-tsc --noEmit` then Vite)
- Tests: `pnpm test` (vitest)
- The FastAPI app serves `web-next/dist/` as SPA when present; build the frontend before testing the full HTTP flow against a single port.

Environment: copy `.env.example` to `.env`. `LLM_PROVIDER=anthropic` (default) or `openai-compat` (with `LLM_BASE_URL`). All `PACER_*` knobs have defaults — see `src/pacer/config.py` for the authoritative list.

## Architecture

### Request flow
`POST /message/send` (`api/routes/message.py`) is the main entry. It:
1. Runs `red_line.scan_keywords` on the user text; if `should_escalate` fires, the request short-circuits with the crisis-resources response and a `MoodLog` is written. The LLM is never called.
2. Otherwise creates a placeholder assistant `Message` (status="streaming") and launches an `asyncio` background task; the HTTP response returns 202 immediately with the message id.
3. The background task creates **its own DB session** (not the request session, which closes when the 202 returns), then calls `Orchestrator.handle_streaming`. Each text delta is persisted via `SessionStore.append_content_to_message` and published to the per-student `EventBus`. Clients listen on `GET /events/stream` (SSE).
4. After streaming, `LLMUsage` is written for token accounting and the memory summarizer is invoked — but only every `PACER_MEMORY_SUMMARIZE_INTERVAL` (default 3) assistant turns. Cancellation: `POST /message/{id}/stop` cancels the in-memory `_streaming_tasks[id]`.

### Orchestrator / agents
`orchestrator/orchestrator.py` is **router-based, not delegation-based**. For each turn:
1. `RouterLLM` (Haiku) classifies intent: `subject_qa | mood_support | planning | chitchat`. A keyword post-filter in `router.py` upgrades obvious subject mentions.
2. One of three agents is built fresh: `build_homeroom_agent` / `build_subject_teacher_agent` / `build_mood_agent`. There is no hand-back chain — the chosen agent owns the whole turn.
3. `_recall_memories` pre-fetches the top-5 relevant memory entries by cosine similarity and prepends them as a `<recalled-memories>` block. Homeroom intentionally does NOT carry `search_memory` because this pre-fetch is the single source; subject/mood keep the tool for proactive lookups during their tasks.

`agent/loop.py::AgentLoop` runs the tool-use loop. Critically, `run_streaming` calls the **non-streaming** LLM API on every iteration and chunk-emits the final text-only response — the streaming API can't surface `tool_use` blocks yet, so streaming the final turn directly would silently drop tool calls. Don't "fix" this back to `chat_stream` without first teaching the LLM clients to yield `tool_use` events.

### Tools
All tools inherit `BaseTool`; the common (`session_factory`, `student_id`) pair is provided via `StudentScopedTool`. Each agent's `build_*_agent` function registers its tool set. `ToolRegistry.execute` wraps every call in a try/except so a buggy tool returns `{"status":"error", "error":...}` rather than killing the loop.

### Memory
`memory/persistent.py::PersistentMemory` stores facts about a student in `memory_entries`. Embeddings are 384-dim float32 from `all-MiniLM-L6-v2` (sentence-transformers), persisted as **packed bytes in `embedding_blob`** with `embedding_dim`; the legacy `embedding_json` column is kept for the alembic backfill in revision `c1a8e2b73d10`. Retrieval (`find_relevant`) caps the candidate set at 500 rows ordered by importance/recency, then does a single numpy matrix-vector product for cosine scoring. `add_if_novel` skips writes whose cosine ≥ 0.92 to any existing entry, preventing paraphrase duplicates ("目标大学" vs "目标院校"). Memory ingestion runs through `memory/summarizer.py::extract_and_store`, which routes through the router model (Haiku) to keep extraction cheap.

### Scheduler
`scheduler/runner.py` is a **separate process** (`BlockingScheduler`, `Asia/Shanghai`). It fires four daily cron jobs (`morning_briefing`, `error_review`, `daily_report`, `goodnight`) which POST to `/internal/system-event` on the API. The internal endpoint requires `X-Internal-Token` and a loopback client address. If `PACER_HOST=0.0.0.0`, `scheduler/client.py` substitutes `127.0.0.1` for the outbound call.

If a student is currently SSE-subscribed, `companion/backlog.py::enqueue_or_publish` publishes directly; otherwise it writes to `pending_events` for the next connection to flush.

### Sessions & multimodal
`session/store.py::SessionStore.history_for_llm` rebuilds chat history for the LLM. Image messages are stored as JSON (`{"text":..., "image_base64":...}`); `_decode_message_content` re-expands them into Anthropic-format content blocks so subsequent turns retain the attached image. Single-string text rows pass through unchanged. `_derive_title` does the inverse for the sessions list UI so image-first chats don't show JSON garbage as titles.

### Auth
`api/deps.py` holds the DB-backed token store. `verify_pin` accepts both bcrypt (`$2*`) and legacy unsalted sha256 hashes; on a successful legacy login the route silently re-hashes to bcrypt. `current_student_id` resolves tokens via the `auth_tokens` table (with TTL); `optional_student_id` additionally accepts `?token=` for SSE since EventSource can't set headers. `_utc_naive_now()` is used everywhere because SQLAlchemy stores `DateTime` columns as naive UTC — mixing aware/naive raises `TypeError` in comparisons.

### LLM backends
`llm/client.py::LLMClient` (Anthropic) and `llm/openai_client.py::OpenAICompatClient` are interchangeable; `LLMClientProtocol` defines the contract. `OpenAICompatClient._build_messages` translates Anthropic-format content blocks (image / tool_use / tool_result) into OpenAI chat shapes. When adding new content block types, both clients must be updated.

## Project conventions

- Database: SQLite for MVP (`pacer.db` at repo root, gitignored), Postgres-ready via `DATABASE_URL`.
- Commit message style: `type(scope): short imperative subject`, body explains *why*. Types in use: `feat`, `fix`, `refactor`, `chore`, `db`. No `Co-Authored-By` lines in commits or PRs.
- New tools live in `src/pacer/tools/*.py` and must be registered in the relevant `build_*_agent` to be visible to the LLM — `ToolRegistry` itself doesn't auto-discover.
- New routes register in `src/pacer/api/server.py::create_app` *before* the SPA fallback mount, otherwise `/{full_path:path}` shadows them.
