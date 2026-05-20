# pacer-ai

> AI study companion for the Gaokao marathon

[简体中文](README.zh-CN.md) · **English**

![pacer-ai overview](pic/readme.png)

A multi-agent AI companion for Chinese high-school seniors prepping for the **Gaokao** — China's nationwide college-entrance exam (think SAT, except it runs two days, you take it once, and your score is by far the biggest factor in which university you end up at). Not a replacement runner — a pacer that runs alongside, covering academics, planning, and emotional support throughout the year-long sprint.

## Why

Existing AI study tools fall into two camps:
- **Photo-and-search apps** — handy for one-off questions, but transactional, no continuity
- **Single-subject tutors** — deep but narrow, no whole-person view

Seniors need something that *knows them*: their weak spots, their goals, their stress patterns, their progress. `pacer-ai` is designed around persistent student understanding accumulated across months of daily interaction.

## Core Architecture

**Three collaborating agents**:
- 🎓 **Homeroom Teacher** — Always present. Routes intent, generates daily plans, manages cadence, fills gaps in the student profile through natural conversation.
- 📚 **Subject Teacher** — One agent, six skill libraries. Loads the right subject pack (Math / Chinese-language / English / Physics / Chemistry / Biology) on demand, then hands back to homeroom.
- 💗 **Mood Companion** — Non-judgmental listening for stress moments. Includes a red-line layer that flags self-harm signals.

**Daily companion loop**:
```
07:00 🌅 Morning briefing + today's plan
  ↓
anytime 💬 Q&A (photo or text)
  ↓
18:00 📝 Error review + variant practice
  ↓
21:30 📊 Daily report + mood check-in
```

The homeroom agent stays in the conversation; subject and mood agents are called as workers and return control afterward — so the student feels like they're talking to one coherent companion, not switching between bots.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Web framework | FastAPI (HTTP + SSE streaming) |
| ORM / DB | SQLAlchemy + SQLite (MVP) → Postgres |
| Scheduling | APScheduler (separate process) |
| LLM (configurable) | Claude Sonnet 4.6 (main) + Haiku 4.5 (router) |
| Vision (replaces OCR) | Commercial multimodal LLM API |
| Frontend | Tablet web page (existing hardware) |

## Design Document

The full design is in [`docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md`](docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md) — 12 sections covering architecture, agent roles, data model, scenario flows, error handling, testing strategy, and 24 locked design decisions.

## Roadmap

5-week MVP across 4 stages:

| Stage | Duration | Goal |
|-------|----------|------|
| 1 · Skeleton | ~1 week | Fork base, DB schema, single-agent loop, FastAPI + SSE |
| 2 · 3-Agent Orchestration | ~1.5 weeks | Router LLM, three prompts, Q&A scenario end-to-end |
| 3 · Active Companion + Error Loop | ~1.5 weeks | Scheduler, four daily scenarios, vision input, mastery tracking |
| 4 · Mood Companion + Polish | ~1 week | Mood agent, red-line detection, six subjects, E2E tests |

V1.1+ candidates: weekly reports, parent dashboard, semantic memory retrieval, expanded question bank, offline mode.

## Status

🚧 Design phase complete. Implementation planning in progress.

## License

Apache License 2.0
