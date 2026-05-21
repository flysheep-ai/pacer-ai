# Feature Roadmap — pacer-ai v1.x

**Status**: design / pending implementation
**Date**: 2026-05-21

Eight follow-up subprojects identified during the post-launch feature audit, organized into three iterations. Each subproject ships independently; this document scopes them so that implementation work doesn't drift across boundaries.

---

## Overview

| # | Subproject | Priority | Estimate | Depends on |
|---|---|---|---|---|
| 1 | Plan task check-off + progress | P0 | ~0.5d | — |
| 2 | Error-review closed loop | P0 | ~1.5d | — |
| 3 | Knowledge-point seed data | P1 | ~1d engineering + ~2d data | — |
| 4 | Mastery visualization | P1 | ~1d | #3 (recommended) |
| 5 | E2E tests for critical paths | P1 | ~1d | tracks #1, #2, #6 |
| 6 | Multi-agent hand-back orchestration | P2 | ~2d | — (invasive) |
| 7 | Weekly report | P2 | ~1d | #1, #4 |
| 8 | Productionization (Docker + Postgres + multi-worker) | P3 | ~2d | — |

### Dependency sketch

```
plan check-off ─┐
                 ├─► weekly report
mastery viz ────┘    ▲
                     │
error-review ────────┘

KP seed ────► mastery viz (best with this in place)

hand-back ──── standalone (invasive refactor)
e2e ─────────  threads through #1, #2, #6
docker ──────  standalone (pre-production)
```

### Suggested cadence

- **Iteration 1 (fast, visible wins)**: #1 + #2 + half of #5 (the e2e tests written alongside).
- **Iteration 2 (data depth)**: #3 + #4.
- **Iteration 3 (architecture + tail)**: #6 + #7 + #8. These three don't block each other and can be parallelized.

---

## Locked design decisions

**D1 — Error-review entry point**: error-list "开始复盘" button opens the existing `/chat/{session_id}` view with a pre-seeded user message (`[复盘错题 #N] …`). The subject teacher recognises the prefix and runs the explain-variant-grade loop. Trade-off accepted: review messages mix into normal conversation history; the upside is zero new chat-component cost.

**D2 — Plan task-checkoff interface**: every task gets a stable `id` (uuid4). The endpoint is `PATCH /plans/{plan_id}/tasks/{task_id}` body `{"done": bool}`. Trade-off accepted: a one-shot migration script will need to back-fill ids on existing `tasks_json` rows.

**D3 — Knowledge-point data source**: hybrid LLM-draft + manual reconciliation against public 高考考试说明 / 教学大纲. ~1 day engineering for the loader + ~2 days data work (can be done async).

---

## Iteration 1 — fast wins

### 1. Plan task check-off + progress

**Goal**: each `tasks_json` task is checkbox-toggleable in the frontend; homeroom briefing and daily report read real completion rates.

**Changes**
- Schema: each task in `tasks_json` gains `id: str (uuid4)` and `done: bool` fields. One-shot script `scripts/backfill_task_ids.py` populates ids on existing rows.
- Backend
  - `tools/plan_tools.py::CreatePlanTool` mints uuid for each new task at write time.
  - New endpoint `PATCH /plans/{plan_id}/tasks/{task_id}` with body `{"done": bool}`. Owner check by student_id. Writes the full `tasks_json` back atomically.
- Frontend
  - `views/PlanView.vue`: render a checkbox per task, plus an X/Y progress bar at the plan-card header. Optimistic local update, rollback on API error.
- `companion/briefing.py::_summarize` and `companion/daily_report.py::_completion_str` already read `t.get("done")` — no change needed.

**Out of scope**: drag-to-reorder, add/remove/edit tasks (this subproject is *check-off only*), plan version history.

**Acceptance**
- Toggling a checkbox survives page reload.
- `GET /plans` returns each task with `id` and `done`.
- Morning briefing's "yesterday's completion" line shows real X/Y, not "未制定".

---

### 2. Error-review closed loop

**Goal**: clicking a row in the error book opens a chat in which the subject teacher walks the student through *that specific error*: explain → offer a variant → grade the attempt → update mastery.

**Changes**
- Backend
  - New endpoint `POST /errors/{error_id}/start-review` → creates (or reuses an "active" review) `ChatSession`, appends a seed user message of the form `[复盘错题 #{id}] 题目: ... 我的答案: ... 正确答案: ...`, returns `{session_id, message_id}` for the frontend to navigate to.
  - Subject teacher's `SUBJECT_SYSTEM_TMPL` gains a paragraph: when the first user turn starts with `[复盘错题 …]`, run the review protocol (explain → call `generate_variant` → wait for student answer → call `mark_error_reviewed` with correctness → call `update_student_mastery` if KP linked).
- Frontend
  - `views/ErrorsView.vue`: each card gets a "开始复盘" button bottom-right. Click → POST → route to `/chat/{session_id}`.
  - `ChatView` already loads session history on mount. The `start-review` endpoint kicks off the orchestrator server-side and returns once the assistant's placeholder message is queued, so the first reply streams in via the normal SSE channel — the frontend doesn't issue an extra `/message/send`.

**Out of scope**
- Batch review (one error at a time).
- Embedded mini-chat inside the error card (we chose D1=A).
- A custom scheduler UI for the 18:00 push (existing push fires and clicking the notification routes to the same flow).

**Acceptance**
- Click an error → land in chat → subject teacher's first message explains it → asks to attempt a variant → on student answer, `ErrorRecord.review_count` increments, `mastery_level` adjusts up/down by 0.15 / -0.10.
- E2E test `test_error_review_flow.py` walks the full cycle.

---

## Iteration 2 — data depth

### 3. Knowledge-point seed data

**Goal**: populate `knowledge_points` with ~300 points across 6 subjects, each with prereqs and exam_freq. This unlocks mastery aggregation by topic, error categorization, and "your weakness in X depends on prerequisite Y" recommendations.

**Changes**
- Data
  - `data/knowledge_points.yaml`: human-readable, git-friendly. Structure:
    ```yaml
    math:
      - name: 集合的基本概念
        chapter: 集合与函数
        difficulty: 2
        prereqs: []
        exam_freq: 3
      - name: 函数的定义域
        chapter: 集合与函数
        difficulty: 2
        prereqs: [集合的基本概念]
        exam_freq: 5
    chinese: …
    ```
  - 50–80 points per subject. Drafted with Claude in batches, reconciled against 教学大纲 / 高考考试说明.
- Loader
  - `scripts/seed_knowledge_points.py`: reads yaml, resolves `prereqs` (name strings) → `prereq_ids` (integers from the same upsert pass). Stable id derivation by `hash(subject + name)` so re-running doesn't churn ids.
- Integration
  - `tools/error_tools.py::SaveErrorRecordTool`: after saving, fire an async LLM call (router model) to classify the error stem into 1–2 KP ids and update the record. Best-effort; failures don't block save.

**Out of scope**
- KP graph visualization page.
- Textbook-style lecture content (`skills/content/*.md` is a separate area).
- Reverse index "questions by KP" (the auto-classification we add is enough for the mastery use case).

**Acceptance**
- `knowledge_points` table holds ≥ 300 rows after seeding.
- ≥ 60% of KPs have non-empty `prereq_ids`.
- For new errors written through the agent, ≥ 70% get at least one auto-classified KP within 5 seconds.

---

### 4. Mastery visualization

**Goal**: turn `/mastery` into a real page so the student can see "where am I weak".

**Changes**
- Frontend
  - New `views/MasteryView.vue`:
    - Top section: 6 subject cards with an average mastery score each.
    - Click a subject → expand to a sortable list of KPs with progress bars.
    - "Top 5 weak points" highlight (lowest `mastery_score` with at least 3 attempts).
  - Route `/mastery`; add `Sidebar` entry between 计划 and 错题.
  - Optional: small SVG radar (one point per subject) at the top.
- Backend: `/mastery` already returns subject-grouped data; no change.
- Plays best after #3 (otherwise KP names show as `知识点 #123`).

**Out of scope**
- Historical progression curves (that lives in the weekly report).
- "Recommended exercises for weak points" (separate, larger subproject).

**Acceptance**
- An account with prior errors sees at least one subject's data rendered.
- Clicking a weak KP opens a new chat seeded with "我想再复习一下 {KP name}".

---

### 5. E2E coverage for critical paths

**Goal**: lock in regression coverage for the paths users touch most and the safety paths. Tests are added alongside the features they cover (rather than as a separate work block).

**Changes**
- Shared fixture: `tests/conftest.py` gets an `llm_mock_factory(sequence)` helper returning a context manager that patches both `LLMClient.chat` and `LLMClient.chat_stream` with a scripted sequence of `LLMResponse`s.
- New tests
  - `tests/e2e/test_red_line.py`: send `"我想自杀"` → assert 202 ack with no LLM call → assert canned escalation text in stored message → assert `MoodLog(red_flag=True)` exists.
  - `tests/e2e/test_image_history.py`: turn 1 sends image+text → turn 2 says "刚才那张图" → inspect the messages forwarded to the LLM mock and assert turn 2's history contains an `image` block.
  - `tests/e2e/test_error_review_flow.py` (added with #2): full review cycle.
  - `tests/e2e/test_login_lockout.py`: 5 wrong PINs → 6th returns 429 → wait past lockout (use monkeypatched clock) → next attempt allowed.

**Out of scope**
- Frontend UI e2e via Playwright (vitest covers component logic; no headless-browser layer in this roadmap).

**Acceptance**
- `pytest` runs all green, ≤ 30s wall-clock.

---

## Iteration 3 — architecture & tail

### 6. Multi-agent hand-back orchestration

**Goal**: deliver what the README promises — homeroom → subject teacher → homeroom (or homeroom → mood → homeroom) within a single turn. Today the router picks one agent per turn and that agent owns the whole reply.

**Changes**
- Re-introduce `DelegateToSubjectTeacherTool` / `DelegateToMoodCompanionTool` (reverting the relevant part of commit `f111909`). They become real signals, not metadata.
- `agent/loop.py::AgentLoop`
  - New optional ctor param `on_handoff: Callable[[str, dict], Awaitable[bool]] | None`. The loop calls it when it sees a delegate-style tool call; if the callback returns `True` the loop stops cleanly (returns current text + handoff trace).
- `orchestrator/orchestrator.py::Orchestrator.handle_streaming`
  - Rewrite around a segment iterator: run main agent until handoff → tear down, build child agent, run it until `return_to_homeroom` → tear down, resume main agent for the wrap-up segment. Each segment streams via the existing `on_delta`.
  - Emit a new SSE event type `agent_handoff` with `{from, to, reason}` so the UI can show a badge ("由数学老师讲解中…").
- Frontend: `MessageList`/`AssistantMessage` already display `agent` from each message; add a chip when `agent` changes mid-turn (we'll need to persist segment boundaries — likely as additional `metadata_json` keys on the assistant message rather than splitting into multiple `Message` rows).
- Feature flag: `PACER_HANDOFF_ENABLED` (default `false`). When false, behavior is exactly today's router-only path. Flip to true to enable handoffs.

**Out of scope**
- Three-way conversations (homeroom + subject + mood simultaneously).
- Lateral handoff (subject → mood directly).
- Agent personality voice differences beyond the existing system prompts.

**Risks**
- Most invasive change in the roadmap. Touches the streaming control flow that every conversation goes through.
- Mitigation: feature flag (default off), explicit e2e coverage for both flag states.

**Acceptance**
- With `PACER_HANDOFF_ENABLED=true`: a student asking "讲讲二次函数" produces a trace containing `delegate_to_subject_teacher` → subject agent activity → `return_to_homeroom` → homeroom wrap-up. SSE stream contains an `agent_handoff` event.
- With flag off: behavior byte-identical to current main.

---

### 7. Weekly report

**Goal**: every Sunday 21:00 the student receives a weekly summary: plan completion rate, error distribution (by subject and by KP), mood trend, KPs that moved (improved or regressed).

**Changes**
- Backend
  - `companion/weekly_report.py`: aggregate the last 7 days of `Plan` / `ErrorRecord` / `MoodLog` / `StudentMastery`. Compute the deltas, feed a compact structured prompt to the main model for a warm summary.
  - `scheduler/runner.py`: add cron `day_of_week=sun, hour=21`.
  - `routes/internal.py`: extend the `type` enum with `weekly_report`; dispatch to `weekly_report.generate(...)`.
- Frontend
  - SSE event-type renderer for `weekly_report` posts: render as a card (not a chat bubble), with sections "本周计划 / 本周错题 / 状态 / 进步". Card stays in the chat as a normal `Message` row tagged with `agent="homeroom"` and metadata.
- Depends on #1 (so completion rate is meaningful) and #4 (so KP movement has names).

**Out of scope**
- Monthly report (V1.2 candidate).
- Standalone "weekly reports history" page (the SSE-driven card lives inside chat history; can be lifted to a dedicated page later if needed).

**Acceptance**
- With seeded 7-day data, manually triggering the job produces a card with all four sections populated.
- Card renders distinctly from regular assistant messages in the UI.

---

### 8. Production-ready: Docker + Postgres + multi-worker

**Goal**: `docker compose up` boots the full stack (api + scheduler + db); the streaming-cancellation mechanism works across uvicorn workers; Postgres is the production DB.

**Changes**
- Dockerfiles
  - `Dockerfile.backend`: `python:3.13-slim` base, install deps via `uv pip install -e .`, run `uvicorn pacer.api.server:create_app --factory --host 0.0.0.0 --port 8000`.
  - `Dockerfile.scheduler`: reuse backend image, override CMD to `python -m pacer.scheduler.runner`.
  - `Dockerfile.frontend`: Node 20 builder stage → static files copied into the backend image's `web-next/dist` (single-container serving) or to an nginx image.
- `docker-compose.yml`: `backend`, `scheduler`, `postgres` services with named volumes; `.env` mounted.
- `_streaming_tasks` migration: replace the in-memory dict with a `streaming_cancellation` table (row per active stream with `cancel_requested: bool`). Stream loop polls every N deltas (default 10) and exits cooperatively on `True`. POST `/message/{id}/stop` flips the bit.
- Postgres compat
  - Verify `embedding_blob` (BYTEA) and `JSON` columns behave the same — they do under SQLAlchemy, but worth one CI run.
  - `tests/integration/test_postgres.py` (skipped unless `PACER_TEST_PG_URL` is set).
- README quickstart additions.

**Out of scope**
- Kubernetes helm chart / nomad / ECS templates.
- Automated DB backups & restores.
- Reverse proxy + TLS termination configuration (user-supplied).

**Acceptance**
- Fresh checkout → `docker compose up --build` → `scripts/seed_dev_student.py` runs in the backend container → login → send a message → SSE delta visible.
- With `--workers 2` (multi-worker), starting a long-running stream and hitting stop on the same `message_id` from a different worker still cancels the stream.

---

## Considered but deferred

These came up during the audit but are out of this roadmap. Listing them so they aren't lost.

- **Parent dashboard** (V1.2): separate auth surface + family-share data model. Don't start until single-student flow is stable.
- **PWA / desktop push notifications**: requires service worker + push subscriptions in DB + VAPID keys. Worth doing once the daily-companion loop has more push-worthy events (weekly report adds one).
- **Data export to PDF/CSV**: useful for parents and end-of-year archival. Standalone utility once parent dashboard exists.
- **Prompt versioning + offline eval set**: needed before any large prompt rewrite, but no urgent driver right now. Quality regressions caught manually for now.
- **Monthly report**: depends on weekly report stabilizing.
- **Streaming `tool_use` parsing** (the "future phase" comment in `agent/loop.py`): would let the genuine typewriter UX come back. Requires Anthropic SDK exposing stream tool-use events cleanly, and a parallel OpenAI-compat implementation. Not on critical path.

---

## How to use this roadmap

Each subproject above is the *intent*, not the implementation plan. When picking one up:

1. Re-open this doc, copy the relevant subsection into a fresh design doc at `docs/superpowers/specs/YYYY-MM-DD-<subproject-slug>-design.md`.
2. Run the brainstorming skill again on that fresh doc — refine architecture and any open questions specific to that subproject.
3. Invoke writing-plans for the implementation plan.
4. Implement, with the e2e coverage from #5 folded in.

This indirection keeps each spec tight enough to be useful as an implementation reference, while the roadmap stays a stable index.
