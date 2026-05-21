# pacer-ai

> AI study companion for the Gaokao marathon

[简体中文](README.zh-CN.md) · **English**

<p align="center">
  <img src="pic/readme.png" alt="pacer-ai overview" width="720">
</p>

A multi-agent AI companion for Chinese high-school seniors prepping for the **Gaokao** — China's nationwide college-entrance exam (think SAT, except two days, one shot). Three agents — homeroom teacher, subject teacher, and mood companion — share one conversation, backed by persistent per-student memory built up over months.

---

## Features

- **Multi-agent chat** — one conversation, three AI roles. A router (Haiku) picks the right agent per turn; the student perceives one continuous companion.
- **Photo Q&A** — snap a math problem, get OCR + subject routing + step-by-step explanation.
- **Error book** — every mistake is recorded. Click "开始复盘" to re-enter a chat where the subject teacher re-explains, generates a variant, and grades your attempt.
- **Mastery tracking** — per-knowledge-point scores across all 6 Gaokao subjects, with weak-spot highlights and one-click review chats.
- **Plan check-off** — morning plan with checkboxes; real completion rates feed the evening report.
- **Daily companion loop** — 07:00 briefing → anytime Q&A → 18:00 error review → 21:30 daily report → 22:30 goodnight.
- **Mood safety net** — keyword scanner + LLM triage short-circuits to crisis hotlines before the main agent ever sees the text.
- **Long-term memory** — 384-dim vector embeddings (all-MiniLM-L6-v2), cosine de-duplication, automatic fact extraction from conversations.

---

## Quick Start

```bash
# 1. Clone and install
git clone git@github.com:flysheep-ai/pacer-ai.git
cd pacer-ai
pip install -e '.[dev]'

# 2. Set up environment
cp .env.example .env
# Edit .env — fill LLM_API_KEY and PACER_INTERNAL_TOKEN

# 3. Migrate + seed
alembic upgrade head
python scripts/seed_dev_student.py
python scripts/seed_knowledge_points.py

# 4. Start backend (terminal 1)
uvicorn pacer.api.server:create_app --factory --reload --port 8001

# 5. Start scheduler (terminal 2)
python -m pacer.scheduler.runner

# 6. Start frontend (terminal 3)
cd src/pacer/web-next && pnpm install && pnpm dev

# Open http://localhost:5173 — login with id=1, pin=123456
```

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11+ · FastAPI · SQLAlchemy · Alembic |
| Frontend | Vue 3 · Vite · Pinia · TypeScript |
| LLM | Claude Sonnet 4.6 (main) · Claude Haiku 4.5 (router) |
| Embeddings | all-MiniLM-L6-v2 (384-dim, numpy) |
| DB | SQLite (dev) → Postgres (prod) |
| Scheduling | APScheduler (separate process) |
| Auth | bcrypt PIN + DB-backed tokens with TTL |

---

## Architecture

```
POST /message/send
  ├─ red_line scan → escalate? → crisis response (no LLM)
  ├─ create streaming placeholder → 202 ack
  └─ background task (own DB session)
       ├─ RouterLLM (Haiku): intent → agent choice
       ├─ AgentLoop.run_streaming (tools ↔ LLM)
       │    ├─ homeroom: plan, profile, errors, memory
       │    ├─ subject_teacher: skills, vision, variants
       │    └─ mood_companion: log_mood, return_to_homeroom
       ├─ SSE deltas → EventBus → GET /events/stream
       ├─ LLMUsage telemetry
       └─ memory summarizer (every N turns)
```

Tests: `tests/{unit,integration,api,e2e}/` · `pytest` (81 tests) · `pnpm test` (vitest, 66 tests)

---

## Development

```bash
# Backend
pytest                              # all tests
pytest tests/unit/test_memory.py    # single file
alembic revision --autogenerate -m "description"

# Frontend
cd src/pacer/web-next
pnpm dev          # dev server (port 5173)
pnpm build        # production build
pnpm test         # vitest
pnpm typecheck    # vue-tsc --noEmit

# Seed data
python scripts/seed_dev_student.py        # student id=1, pin=123456
python scripts/seed_knowledge_points.py   # ~200 Gaokao knowledge points
```

Full design doc: [`docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md`](docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md)

---

## License

Apache License 2.0
