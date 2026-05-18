# Stage 3 · Active Companion + Error Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add proactive scheduling, vision-based question input, error-record lifecycle, and mastery tracking. By end of this stage, the system runs 4 daily scenarios on schedule (07:00 morning briefing, 18:00 error review, 21:30 daily report, 22:30 goodnight), accepts photo questions, and updates `student_mastery` based on errors.

**Architecture:** APScheduler runs in a separate process. Scheduled jobs POST to an internal `/internal/system-event` endpoint (token-protected, localhost-only). When the student is offline, events queue per-student and replay on next login. Vision is a Tool wrapping multimodal LLM calls. Error records flow through `save_error_record` and trigger `update_student_mastery`.

**Tech Stack:** Stage 1 + 2 foundations + APScheduler + Anthropic multimodal API (images via base64 or URL).

---

## Target Files (NEW in Stage 3)

```
src/pacer/
├── scheduler/
│   ├── __init__.py
│   ├── jobs.py                    # job definitions (morning/review/report/goodnight)
│   ├── runner.py                  # APScheduler process entry
│   └── client.py                  # HTTP client → /internal/system-event
├── api/routes/
│   ├── internal.py                # POST /internal/system-event (localhost only)
│   └── upload.py                  # POST /upload/image
├── companion/
│   ├── __init__.py
│   ├── briefing.py                # generate_morning_plan
│   ├── error_review.py            # run_error_review
│   ├── daily_report.py            # generate_daily_report
│   └── backlog.py                 # offline event queue
├── tools/
│   ├── vision_tool.py             # vision_understand_image
│   ├── error_tools.py             # save_error_record, get_recent_errors, generate_variant
│   ├── mastery_tools.py           # update_student_mastery, get_student_weakness
│   └── plan_tools.py              # get_today_plan, update_plan
```

Modified:
- `src/pacer/llm/client.py` → add `chat_with_images()` method
- `src/pacer/agents/subject_teacher.py` → register vision + error + mastery tools
- `src/pacer/agents/homeroom.py` → register plan + error tools
- `src/pacer/api/server.py` → register internal + upload routes

---

## Task 1: Vision-Enabled LLM Client + Tool

**Files:**
- Modify: `src/pacer/llm/client.py` (add image support)
- Create: `src/pacer/tools/vision_tool.py`
- Create: `tests/unit/test_vision_tool.py`

- [ ] **Step 1: Extend `LLMClient` with multimodal capability**

Add method:

```python
async def chat_with_images(
    self,
    *, system: str, user_text: str, image_base64_list: list[str],
    model: str | None = None,
) -> LLMResponse:
    content_blocks: list[dict] = []
    for img in image_base64_list:
        content_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": img},
        })
    content_blocks.append({"type": "text", "text": user_text})
    resp = await self._client.messages.create(
        model=model or self.model, max_tokens=self.max_tokens,
        system=system,
        messages=[{"role": "user", "content": content_blocks}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return LLMResponse(text=text, tool_calls=[], stop_reason=resp.stop_reason,
                       input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens, raw=resp)
```

- [ ] **Step 2: Write failing test for VisionUnderstandImageTool**

```python
# tests/unit/test_vision_tool.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pacer.llm.client import LLMResponse
from pacer.tools.vision_tool import VisionUnderstandImageTool


@pytest.mark.asyncio
async def test_vision_tool_extracts_question_and_subject():
    llm = MagicMock()
    llm.chat_with_images = AsyncMock(return_value=LLMResponse(
        text=(
            '{"subject":"math","stem":"求 f(x)=x^2 在 x=1 处的切线方程","figure_description":"无图"}'
        ),
        tool_calls=[], stop_reason="end_turn",
        input_tokens=50, output_tokens=30, raw=None,
    ))
    tool = VisionUnderstandImageTool(llm=llm, model="claude-sonnet-4-6")
    result = await tool.execute(image_base64="<b64>", hint=None)
    assert result["subject"] == "math"
    assert "切线" in result["stem"]
```

- [ ] **Step 3: Implement `src/pacer/tools/vision_tool.py`**

```python
from __future__ import annotations
import json
from pacer.tools.base import BaseTool
from pacer.llm.client import LLMClient


_SYSTEM = """You are an OCR + understanding assistant for Chinese high-school exam questions.
Extract the question stem, identify the subject, and describe any figures.
Output STRICT JSON only:
{"subject":"math|chinese|english|physics|chemistry|biology","stem":"<text>","figure_description":"<short>"}
"""


class VisionUnderstandImageTool(BaseTool):
    name = "vision_understand_image"
    description = "OCR and understand a photographed exam question. Returns subject + stem text."
    parameters = {
        "type": "object",
        "properties": {
            "image_base64": {"type": "string", "description": "base64-encoded JPEG"},
            "hint": {"type": "string", "description": "optional subject hint"},
        },
        "required": ["image_base64"],
    }
    is_readonly = True

    def __init__(self, llm: LLMClient, model: str):
        self.llm = llm
        self.model = model

    async def execute(self, *, image_base64: str, hint: str | None = None) -> dict:
        user_text = "请按 system 指令提取这道题目。" + (f"提示：可能是{hint}。" if hint else "")
        resp = await self.llm.chat_with_images(
            system=_SYSTEM, user_text=user_text,
            image_base64_list=[image_base64], model=self.model,
        )
        try:
            return json.loads(resp.text.strip())
        except json.JSONDecodeError:
            return {"subject": hint or "unknown", "stem": resp.text, "figure_description": ""}
```

- [ ] **Step 4: Test + commit**

Run: `pytest tests/unit/test_vision_tool.py -v` → 1 passed
```bash
git add src/pacer/llm/client.py src/pacer/tools/vision_tool.py tests/unit/test_vision_tool.py
git commit -m "feat: vision_understand_image tool (multimodal LLM-backed OCR)"
```

---

## Task 2: Error + Mastery + Plan Tools

**Files:**
- Create: `src/pacer/tools/error_tools.py`, `src/pacer/tools/mastery_tools.py`, `src/pacer/tools/plan_tools.py`
- Create: `tests/unit/test_error_tools.py`, `tests/unit/test_mastery_tools.py`, `tests/unit/test_plan_tools.py`

- [ ] **Step 1: Write failing tests**

Each test follows the pattern from Task 6 in Stage 1 (sqlite in-memory + Student fixture). Each tool has 2-3 tests verifying CRUD behavior. Sample for `error_tools`:

```python
@pytest.mark.asyncio
async def test_save_and_recent(db_and_student):
    sess, sid = db_and_student
    saver = SaveErrorRecordTool(lambda: sess, sid)
    recent = GetRecentErrorsTool(lambda: sess, sid)
    await saver.execute(
        question_id=None, user_answer="y=2x", correct_answer="y=2x-1",
        error_type="concept", knowledge_point_ids=[],
        source="photo", explanation_text="斜率正确但截距错",
        stem_text="求 f(x)=x^2 在 x=1 切线",
    )
    result = await recent.execute(limit=10)
    assert len(result["errors"]) == 1
    assert result["errors"][0]["error_type"] == "concept"
```

- [ ] **Step 2: Implement tools (each file ~100 lines, all share the same `session_factory + student_id` pattern as memory_tools)**

Key tool list and signatures:

`error_tools.py`:
- `SaveErrorRecordTool`: writes a row in `error_records`, optionally creates an ad-hoc question. `name="save_error_record"`.
- `GetRecentErrorsTool`: `name="get_recent_errors"`, params `{limit:int, subject?:str, since_days?:int}`.
- `GenerateVariantTool`: `name="generate_variant"`, MVP can call LLM with prompt "Generate a variant of this question for practice." Returns `{stem, expected_answer}`.
- `MarkErrorReviewedTool`: `name="mark_error_reviewed"`, params `{error_record_id, correct:bool}` — bumps `review_count`, sets `last_reviewed_at`, adjusts `mastery_level`.

`mastery_tools.py`:
- `UpdateStudentMasteryTool`: `name="update_student_mastery"`, params `{knowledge_point_id, correct:bool}`. Increments correct/wrong, recomputes `mastery_score = correct / (correct + wrong)`.
- `GetStudentWeaknessTool`: `name="get_student_weakness"`, params `{subject?, top_n:int}`. Returns sorted ascending by mastery_score.

`plan_tools.py`:
- `GetTodayPlanTool`: `name="get_today_plan"`, returns latest `plans` row for today.
- `UpdatePlanTool`: `name="update_plan"`, params `{plan_id, tasks_json: list, feedback?: str}`.
- `CreatePlanTool`: `name="create_plan"`, params `{date, type: "daily"|"weekly", tasks_json}`.

Each tool file follows the same skeleton:

```python
from __future__ import annotations
from datetime import datetime, timedelta
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.tools.base import BaseTool
from pacer.db.models import ErrorRecord, StudentMastery, Plan, Question


class SaveErrorRecordTool(BaseTool):
    name = "save_error_record"
    description = "Persist an error record for the student. May create an ad-hoc question entry if question_id is None."
    parameters = {
        "type": "object",
        "properties": {
            "question_id": {"type": ["integer", "null"]},
            "stem_text": {"type": "string"},
            "user_answer": {"type": "string"},
            "correct_answer": {"type": "string"},
            "error_type": {"type": "string", "enum": ["carelessness", "concept", "method", "other"]},
            "knowledge_point_ids": {"type": "array", "items": {"type": "integer"}},
            "source": {"type": "string", "enum": ["photo", "text", "qa"]},
            "explanation_text": {"type": "string"},
            "subject": {"type": "string"},
        },
        "required": ["stem_text", "user_answer", "correct_answer", "error_type", "source"],
    }
    is_readonly = False
    # __init__ + execute as in Stage 1's pattern
```

(Full implementations follow the same idiom; ~30 lines each.)

- [ ] **Step 3: Tests pass + commit**

```bash
pytest tests/unit/test_error_tools.py tests/unit/test_mastery_tools.py tests/unit/test_plan_tools.py -v
git add src/pacer/tools/error_tools.py src/pacer/tools/mastery_tools.py src/pacer/tools/plan_tools.py tests/unit/test_error_tools.py tests/unit/test_mastery_tools.py tests/unit/test_plan_tools.py
git commit -m "feat: error / mastery / plan tools"
```

---

## Task 3: Register New Tools on Agents

**Files:**
- Modify: `src/pacer/agents/homeroom.py`, `src/pacer/agents/subject_teacher.py`
- Modify: `tests/unit/test_agent_factories.py` (extend assertions)

- [ ] **Step 1: Add to homeroom registry**

In `build_homeroom_agent`, register: `GetTodayPlanTool`, `UpdatePlanTool`, `CreatePlanTool`, `GetRecentErrorsTool`, `GetStudentWeaknessTool`.

- [ ] **Step 2: Add to subject_teacher registry**

In `build_subject_teacher_agent`, register: `VisionUnderstandImageTool` (pass LLM + model), `SaveErrorRecordTool`, `GenerateVariantTool`, `MarkErrorReviewedTool`, `UpdateStudentMasteryTool`, `GetStudentWeaknessTool`.

- [ ] **Step 3: Update factory tests**

```python
def test_subject_teacher_has_vision_and_error_tools(common):
    sess, loader = common
    loop = build_subject_teacher_agent(
        llm=_llm(), session_factory=lambda: sess, student_id=1,
        subject="math", skills_loader=loader, vision_model="claude-sonnet-4-6",
    )
    names = set(loop.tools.names())
    for t in ["vision_understand_image", "save_error_record", "generate_variant",
              "mark_error_reviewed", "update_student_mastery"]:
        assert t in names
```

(Note: subject_teacher factory now needs `vision_model` param.)

- [ ] **Step 4: Run tests + commit**

```bash
pytest -v
git commit -am "feat: register error/mastery/plan/vision tools on agents"
```

---

## Task 4: Internal System-Event Endpoint

**Files:**
- Create: `src/pacer/api/routes/internal.py`
- Modify: `src/pacer/api/server.py`
- Modify: `src/pacer/config.py` (add `internal_token` setting)
- Create: `tests/integration/test_internal_event.py`

The internal endpoint accepts `{type, student_id, payload?}`, runs the corresponding companion handler, and pushes resulting messages via SSE.

- [ ] **Step 1: Add `internal_token` to settings**

```python
# config.py
internal_token: str = Field(..., alias="PACER_INTERNAL_TOKEN")
```

Append to `.env.example`:
```
PACER_INTERNAL_TOKEN=  # generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- [ ] **Step 2: Implement `src/pacer/api/routes/internal.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException, Request, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db
from pacer.config import get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


class SystemEventReq(BaseModel):
    type: str  # morning_briefing | error_review | daily_report | goodnight
    student_id: int
    payload: dict | None = None


def _verify_internal_token(
    x_internal_token: str | None = Header(None, alias="X-Internal-Token"),
    request: Request = None,
):
    settings = get_settings()
    if not x_internal_token or x_internal_token != settings.internal_token:
        raise HTTPException(status_code=403, detail="forbidden")
    # Localhost-only enforcement
    if request is not None:
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=403, detail="not local")


@router.post("/system-event", dependencies=[Depends(_verify_internal_token)])
async def handle_system_event(
    req: SystemEventReq, request: Request, db: Session = Depends(get_db),
):
    from pacer.companion.briefing import generate_morning_plan
    from pacer.companion.error_review import run_error_review
    from pacer.companion.daily_report import generate_daily_report
    from pacer.companion.backlog import enqueue_or_publish

    student_id = req.student_id
    if req.type == "morning_briefing":
        text = await generate_morning_plan(db, request.app.state, student_id)
        await enqueue_or_publish(request.app.state, student_id, "morning_briefing", text)
    elif req.type == "error_review":
        text = await run_error_review(db, request.app.state, student_id)
        await enqueue_or_publish(request.app.state, student_id, "error_review", text)
    elif req.type == "daily_report":
        text = await generate_daily_report(db, request.app.state, student_id)
        await enqueue_or_publish(request.app.state, student_id, "daily_report", text)
    elif req.type == "goodnight":
        await enqueue_or_publish(request.app.state, student_id, "goodnight", "晚安，好好休息～")
    else:
        raise HTTPException(status_code=400, detail=f"unknown event type {req.type!r}")
    return {"status": "ok"}
```

- [ ] **Step 3: Register router**

In `server.py`:
```python
from pacer.api.routes.internal import router as internal_router
app.include_router(internal_router)
```

- [ ] **Step 4: Implement the 3 companion handlers (briefing/error_review/daily_report)**

Each `companion/*.py` module is a function that:
1. Gathers data from DB (yesterday's plan, today's errors, mastery deltas, etc.)
2. Constructs a prompt and runs the homeroom agent (or subject_teacher for error_review)
3. Returns the final text

Example `src/pacer/companion/briefing.py`:

```python
from __future__ import annotations
from datetime import date, timedelta
from sqlalchemy.orm import Session
from pacer.agents.homeroom import build_homeroom_agent
from pacer.db.models import Plan, ErrorRecord, StudentMastery


_PROMPT_TMPL = """[SYSTEM TASK · morning briefing] 现在是早上 07:00。
学生数据：
- 距离高考：{days_left} 天
- 昨日计划完成情况：{yesterday_status}
- 待复习错题数：{review_count}

请：
1. 用一句温暖的早安开头
2. 用 create_plan 生成今日 3-5 个任务（明确学科 + 时间块）
3. 输出简洁的今日重点摘要
"""


async def generate_morning_plan(db: Session, state, student_id: int) -> str:
    today = date.today()
    yesterday = today - timedelta(days=1)
    yesterday_plan = (
        db.query(Plan)
        .filter_by(student_id=student_id, type="daily")
        .filter(Plan.date >= yesterday)
        .order_by(Plan.id.desc())
        .first()
    )
    yesterday_status = "无" if yesterday_plan is None else _summarize_completion(yesterday_plan.tasks_json)
    review_count = db.query(ErrorRecord).filter(
        ErrorRecord.student_id == student_id,
        ErrorRecord.mastery_level < 0.7,
    ).count()
    days_left = max(0, (date(today.year, 6, 7) - today).days)  # 高考一般 6/7

    prompt = _PROMPT_TMPL.format(
        days_left=days_left, yesterday_status=yesterday_status, review_count=review_count,
    )
    agent = build_homeroom_agent(llm=state.llm, session_factory=lambda: db, student_id=student_id)
    result = await agent.run(prompt, history=[])
    return result.final_text


def _summarize_completion(tasks: list[dict]) -> str:
    if not tasks: return "未制定"
    done = sum(1 for t in tasks if t.get("done"))
    return f"{done}/{len(tasks)} 完成"
```

Analogous for `error_review.py` (loads today's errors, dispatches to subject_teacher per subject group) and `daily_report.py` (aggregates today's data, uses homeroom).

- [ ] **Step 5: Test internal endpoint**

```python
# tests/integration/test_internal_event.py
def test_internal_endpoint_requires_token(client_and_token):
    client, _ = client_and_token
    resp = client.post("/internal/system-event",
                       json={"type": "morning_briefing", "student_id": 1})
    assert resp.status_code == 403


def test_internal_endpoint_with_token_runs_briefing(client_and_token, monkeypatch):
    client, _ = client_and_token
    monkeypatch.setenv("PACER_INTERNAL_TOKEN", "secret123")
    # Patch the companion handler to avoid LLM calls in test
    with patch("pacer.api.routes.internal.generate_morning_plan", new=AsyncMock(return_value="早安！")):
        resp = client.post(
            "/internal/system-event",
            json={"type": "morning_briefing", "student_id": 1},
            headers={"X-Internal-Token": "secret123"},
        )
    assert resp.status_code == 200
```

- [ ] **Step 6: Commit**

```bash
git add src/pacer/api/routes/internal.py src/pacer/companion/ src/pacer/config.py .env.example tests/integration/test_internal_event.py
git commit -m "feat: /internal/system-event endpoint + companion handlers (briefing/error_review/daily_report)"
```

---

## Task 5: Offline Event Backlog

**Files:**
- Create: `src/pacer/companion/backlog.py`
- Modify: DB — add `pending_events` table via Alembic migration
- Create: `tests/integration/test_backlog.py`

When a system event fires but the student has no active SSE subscriber, the event is queued in `pending_events`. On `POST /auth/login` (or first SSE subscription), pending events are flushed to the new subscriber and deleted.

- [ ] **Step 1: Add model**

```python
# Append to db/models.py
class PendingEvent(Base):
    __tablename__ = "pending_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    event_type: Mapped[str] = mapped_column(String(50))
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

Generate migration:
```bash
alembic revision --autogenerate -m "add pending_events"
alembic upgrade head
```

- [ ] **Step 2: Implement `src/pacer/companion/backlog.py`**

```python
from __future__ import annotations
from sqlalchemy.orm import Session
from pacer.db.models import PendingEvent
from pacer.session.events import SSEEvent


async def enqueue_or_publish(state, student_id: int, event_type: str, text: str):
    bus = state.event_bus
    data = {"text": text, "event_type": event_type}
    if bus.has_subscriber(student_id):
        await bus.publish(SSEEvent(student_id=student_id, event_type=event_type, data=data))
    else:
        # Persist to DB for later flush
        # ... (DB write via state.db_session_factory)
        pass


def flush_backlog(db: Session, bus, student_id: int):
    rows = db.query(PendingEvent).filter_by(student_id=student_id).order_by(PendingEvent.created_at).all()
    for row in rows:
        # Publish synchronously (or schedule)
        ...
    for row in rows:
        db.delete(row)
    db.commit()
```

Add `EventBus.has_subscriber(student_id)` method:
```python
def has_subscriber(self, student_id: int) -> bool:
    return len(self._subscribers.get(student_id, [])) > 0
```

Hook `flush_backlog` into login response and SSE stream connection.

- [ ] **Step 3: Test backlog flow**

Verify: (1) event with no subscriber persists, (2) login triggers flush, (3) events arrive in chronological order.

- [ ] **Step 4: Commit**

```bash
git add src/pacer/companion/backlog.py src/pacer/db/migrations/versions/*.py src/pacer/db/models.py src/pacer/session/events.py
git commit -m "feat: offline event backlog (pending_events table)"
```

---

## Task 6: APScheduler Process

**Files:**
- Create: `src/pacer/scheduler/__init__.py`, `src/pacer/scheduler/jobs.py`, `src/pacer/scheduler/runner.py`, `src/pacer/scheduler/client.py`
- Create: `tests/integration/test_scheduler_jobs.py`

The scheduler is a separate Python process. It reads student IDs from DB, computes each student's local schedule (assumed Asia/Shanghai for MVP), and posts events to `http://127.0.0.1:8000/internal/system-event`.

- [ ] **Step 1: Add `apscheduler` to `pyproject.toml`**

```toml
"apscheduler>=3.10",
"httpx>=0.27",
```

Reinstall:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Implement `src/pacer/scheduler/client.py`**

```python
import httpx
from pacer.config import get_settings


def post_system_event(event_type: str, student_id: int, payload: dict | None = None):
    settings = get_settings()
    url = f"http://{settings.host}:{settings.port}/internal/system-event"
    httpx.post(
        url, json={"type": event_type, "student_id": student_id, "payload": payload or {}},
        headers={"X-Internal-Token": settings.internal_token}, timeout=30.0,
    )
```

- [ ] **Step 3: Implement `src/pacer/scheduler/jobs.py`**

```python
from __future__ import annotations
from sqlalchemy.orm import Session
from pacer.db.models import Student
from pacer.scheduler.client import post_system_event


def list_active_students(db: Session) -> list[int]:
    rows = db.query(Student).all()
    return [s.id for s in rows]


def fire_for_each_student(event_type: str, db: Session):
    for sid in list_active_students(db):
        try:
            post_system_event(event_type, sid)
        except Exception:
            pass


def morning_job(db: Session):  fire_for_each_student("morning_briefing", db)
def error_review_job(db: Session):  fire_for_each_student("error_review", db)
def daily_report_job(db: Session):  fire_for_each_student("daily_report", db)
def goodnight_job(db: Session):  fire_for_each_student("goodnight", db)
```

- [ ] **Step 4: Implement `src/pacer/scheduler/runner.py`**

```python
"""Entry: python -m pacer.scheduler.runner"""
from __future__ import annotations
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.config import get_settings
from pacer.scheduler.jobs import (
    morning_job, error_review_job, daily_report_job, goodnight_job,
)


def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sched = BlockingScheduler(timezone="Asia/Shanghai")

    def _wrap(fn):
        def _runner():
            sess = SessionLocal()
            try:
                fn(sess)
            finally:
                sess.close()
        return _runner

    sched.add_job(_wrap(morning_job),       CronTrigger(hour=7,  minute=0))
    sched.add_job(_wrap(error_review_job),  CronTrigger(hour=18, minute=0))
    sched.add_job(_wrap(daily_report_job),  CronTrigger(hour=21, minute=30))
    sched.add_job(_wrap(goodnight_job),     CronTrigger(hour=22, minute=30))
    print("[scheduler] starting with 4 jobs (Asia/Shanghai)…")
    sched.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Write test using `apscheduler`'s scheduling-bypass API**

```python
# tests/integration/test_scheduler_jobs.py
from unittest.mock import patch
from pacer.scheduler.jobs import morning_job, fire_for_each_student


def test_morning_job_posts_for_each_student(db_with_two_students):
    db, _ = db_with_two_students
    with patch("pacer.scheduler.jobs.post_system_event") as mock_post:
        morning_job(db)
    assert mock_post.call_count == 2
    args = [c.args[0] for c in mock_post.call_args_list]
    assert all(a == "morning_briefing" for a in args)
```

- [ ] **Step 6: Manual smoke**

In separate terminals:
```bash
# Terminal 1: API
uvicorn pacer.api.server:create_app --factory --reload

# Terminal 2: scheduler
python -m pacer.scheduler.runner
```

Manually trigger by waiting (or temporarily change cron to `minute='*/1'` for fast iteration).

- [ ] **Step 7: Commit + tag**

```bash
git add src/pacer/scheduler/ tests/integration/test_scheduler_jobs.py pyproject.toml
git commit -m "feat: APScheduler process with 4 daily jobs (07/18/21:30/22:30)"
git tag -a stage-3-active-companion -m "Stage 3 complete: scheduler + vision + error loop"
git push origin main --tags
```

---

## Validation Criteria (Stage 3 done when)

- [ ] `pytest -v` all green
- [ ] Scheduler can be started with `python -m pacer.scheduler.runner` and shows 4 jobs
- [ ] Manually POST to `/internal/system-event` with each of 4 types → SSE event reaches subscriber
- [ ] Upload an image → `vision_understand_image` returns subject + stem
- [ ] After a manual error round (save_error_record → mark_error_reviewed), `student_mastery` row exists with non-zero values
- [ ] Offline test: fire `morning_briefing` for student with no SSE subscriber → row in `pending_events` → login → events flush
- [ ] `git tag stage-3-active-companion` pushed
