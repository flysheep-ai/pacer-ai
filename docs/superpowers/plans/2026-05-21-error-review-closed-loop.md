# Error-Review Closed Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clicking an item in the error book opens a chat in which the subject teacher walks the student through *that specific error* end-to-end (explain → variant → grade → mastery update).

**Architecture:** A new `POST /errors/{error_id}/start-review` endpoint creates a fresh `ChatSession`, seeds a structured user message tagged `[复盘错题 #N] …`, and spawns the same background streaming task that `/message/send` uses. The subject-teacher system prompt gains a "review protocol" block that recognises the tag and runs `generate_variant` → `mark_error_reviewed` → `update_student_mastery`. The frontend gains an "开始复盘" button per error card that POSTs and routes to `/chat/{session_id}`.

**Tech Stack:** FastAPI · SQLAlchemy · Vue 3 · vue-router · pytest

**Spec:** `docs/superpowers/specs/2026-05-21-feature-roadmap-design.md` § Iteration 1 / subproject #2

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/pacer/api/streaming.py` | create | `start_assistant_stream(...)` extracted from `message.py` so other endpoints can reuse it |
| `src/pacer/api/routes/message.py` | modify | use the new `start_assistant_stream` instead of inline `run_stream` |
| `src/pacer/api/routes/resources.py` | modify | new `POST /errors/{error_id}/start-review` endpoint |
| `src/pacer/agents/subject_teacher.py` | modify | system prompt grows an `[复盘错题]` protocol section |
| `src/pacer/web-next/src/views/ErrorsView.vue` | modify | "开始复盘" button per card; POST → router push |
| `tests/api/test_start_review.py` | create | endpoint contract + auth boundaries |
| `tests/e2e/test_error_review_flow.py` | create | full loop: start-review → tool calls → mastery update |

`message.py` already does the right things (red-line scan, image handling, history rebuild, LLMUsage telemetry, throttled summarizer) — Task 1 is a *refactor only*, behaviour-preserving. Test suite must stay green after Task 1 with zero new tests.

---

## Tasks

### Task 1: Extract streaming runner into a reusable helper

**Files:**
- Create: `src/pacer/api/streaming.py`
- Modify: `src/pacer/api/routes/message.py`

- [ ] **Step 1: Confirm existing tests pass before touching anything**

```bash
python -m pytest -q
```

Expected: all green (baseline).

- [ ] **Step 2: Create `src/pacer/api/streaming.py`**

```python
"""Shared background-streaming runner.

Used by `POST /message/send` and any other endpoint that needs to push an
assistant reply through the orchestrator and into the SSE event bus
(e.g. `POST /errors/{id}/start-review`).
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from pacer.api import deps
from pacer.config import get_settings
from pacer.llm.client import LLMMessage
from pacer.orchestrator.orchestrator import Orchestrator
from pacer.session.events import SSEEvent
from pacer.session.store import SessionStore

log = logging.getLogger("pacer.streaming")

# Single-process registry of cancellable streaming tasks.
# Shared with `/message/{message_id}/stop`. Multi-worker deploys would need
# this moved to a DB flag the loop polls per tick.
_streaming_tasks: dict[int, asyncio.Task] = {}


def get_streaming_tasks() -> dict[int, asyncio.Task]:
    """Accessor so callers (notably the stop endpoint) share one dict."""
    return _streaming_tasks


def start_assistant_stream(
    *,
    app_state: Any,
    student_id: int,
    session_id: int,
    assistant_message_id: int,
    user_message_for_llm: str | list[dict[str, Any]],
    user_text_for_memory: str,
    history: list[LLMMessage],
) -> asyncio.Task:
    """Spawn the streaming background task.

    Caller MUST have already:
    - persisted the user message into the session
    - created an empty placeholder assistant message (`status='streaming'`)
    - built `history` (excluding the trailing user message)
    """
    settings = get_settings()
    bus = app_state.event_bus

    async def run() -> None:
        collected: list[str] = []
        db_session = deps._SessionLocal()
        local_store = SessionStore(db_session)
        bg_factory = lambda: db_session
        orch = Orchestrator(
            llm=app_state.llm,
            router_model=settings.router_model,
            session_factory=bg_factory,
            student_id=student_id,
            skills_loader=app_state.skills_loader,
        )
        try:
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_start",
                data={
                    "session_id": session_id,
                    "message_id": assistant_message_id,
                    "agent": "homeroom",
                },
            ))

            async def on_delta(text: str) -> None:
                if not text:
                    return
                collected.append(text)
                local_store.append_content_to_message(assistant_message_id, text)
                await bus.publish(SSEEvent(
                    student_id=student_id, event_type="assistant_delta",
                    data={"message_id": assistant_message_id, "delta": text},
                ))

            out = await orch.handle_streaming(
                user_message_for_llm, history=history, on_delta=on_delta,
            )
            local_store.finalize_message(
                assistant_message_id, content=out.final_text, status="done",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": assistant_message_id,
                    "agent": out.agent_used,
                    "stop_reason": "completed",
                },
            ))

            try:
                from pacer.db.models import LLMUsage
                db_session.add(LLMUsage(
                    student_id=student_id, session_id=session_id,
                    agent=out.agent_used, model=app_state.llm.model,
                    input_tokens=out.inner.total_input_tokens,
                    output_tokens=out.inner.total_output_tokens,
                    iterations=out.inner.iterations,
                ))
                db_session.commit()
            except Exception:
                log.exception("failed to write LLMUsage")

            try:
                if _should_summarize(local_store, session_id, settings.memory_summarize_interval):
                    from pacer.memory.summarizer import extract_and_store
                    n = await extract_and_store(
                        app_state.llm, student_id, user_text_for_memory, out.final_text,
                        lambda: deps._SessionLocal(),
                        model=settings.router_model,
                    )
                    if n > 0:
                        log.info("stored %d new memories student=%s", n, student_id)
            except Exception:
                log.exception("memory summarizer failed")
        except asyncio.CancelledError:
            local_store.finalize_message(
                assistant_message_id, content="".join(collected), status="failed",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": assistant_message_id, "agent": "homeroom",
                    "stop_reason": "user_stopped",
                },
            ))
        except Exception:
            log.exception("streaming failed message_id=%s", assistant_message_id)
            local_store.finalize_message(
                assistant_message_id, content="".join(collected), status="failed",
            )
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={
                    "message_id": assistant_message_id, "agent": "homeroom",
                    "stop_reason": "error",
                },
            ))
        finally:
            db_session.close()
            _streaming_tasks.pop(assistant_message_id, None)

    task = asyncio.create_task(run())
    _streaming_tasks[assistant_message_id] = task
    return task


def _should_summarize(store: SessionStore, session_id: int, interval: int) -> bool:
    if interval <= 1:
        return True
    msgs = store.list_messages(session_id)
    assistant_count = sum(1 for m in msgs if m.role == "assistant" and m.status == "done")
    return assistant_count > 0 and assistant_count % interval == 0
```

- [ ] **Step 3: Replace `src/pacer/api/routes/message.py` entirely**

```python
from __future__ import annotations
import json
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pacer.api import deps
from pacer.api.streaming import get_streaming_tasks, start_assistant_stream
from pacer.companion.red_line import (
    ESCALATION_RESPONSE, scan_keywords, should_escalate,
)
from pacer.llm.client import LLMMessage
from pacer.session.store import SessionStore

router = APIRouter(prefix="/message", tags=["message"])
log = logging.getLogger("pacer.message")
_streaming_tasks = get_streaming_tasks()


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None
    image_base64: str | None = None


class SendAck(BaseModel):
    session_id: int
    assistant_message_id: int


@router.post("/send", response_model=SendAck, status_code=202)
async def send_message(
    req: SendRequest,
    request: Request,
    db: Session = Depends(deps.get_db),
    student_id: int = Depends(deps.current_student_id),
) -> SendAck:
    store = SessionStore(db)
    if req.session_id is None:
        chat = store.create_session(student_id=student_id)
    else:
        chat = store.get_session(req.session_id)
        if chat is None or chat.student_id != student_id:
            raise HTTPException(status_code=404, detail="session not found")

    red_hits = scan_keywords(req.text)
    if red_hits and should_escalate(red_hits):
        log.warning(
            "red-line escalation student=%s hits=%s",
            student_id, [h["category"] for h in red_hits],
        )
        store.append_message(chat.id, role="user", agent=None, content=req.text)
        ack_msg = store.append_message(
            chat.id, role="assistant", agent="mood_companion",
            content=ESCALATION_RESPONSE,
            metadata={"red_line": True, "categories": [h["category"] for h in red_hits]},
        )
        try:
            from pacer.db.models import MoodLog
            db.add(MoodLog(
                student_id=student_id, session_id=chat.id, self_score=1,
                topics=[h["category"] for h in red_hits],
                summary="red-line auto-detected", red_flag=True,
            ))
            db.commit()
        except Exception:
            log.exception("failed to write red-line MoodLog")
        return SendAck(session_id=chat.id, assistant_message_id=ack_msg.id)

    if req.image_base64:
        user_content_for_db = json.dumps(
            {"text": req.text, "image_base64": req.image_base64}, ensure_ascii=False,
        )
        user_content_for_llm: str | list[dict[str, Any]] = [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg", "data": req.image_base64,
            }},
            {"type": "text", "text": req.text},
        ]
    else:
        user_content_for_db = req.text
        user_content_for_llm = req.text

    store.append_message(chat.id, role="user", agent=None, content=user_content_for_db)
    history_dicts = store.history_for_llm(chat.id)
    history = [LLMMessage(role=h["role"], content=h["content"]) for h in history_dicts[:-1]]

    msg = store.create_empty_assistant(chat.id, agent="homeroom")

    start_assistant_stream(
        app_state=request.app.state,
        student_id=student_id,
        session_id=chat.id,
        assistant_message_id=msg.id,
        user_message_for_llm=user_content_for_llm,
        user_text_for_memory=req.text,
        history=history,
    )

    return SendAck(session_id=chat.id, assistant_message_id=msg.id)


@router.post("/{message_id}/stop", status_code=204)
async def stop_stream(
    message_id: int,
    student_id: int = Depends(deps.current_student_id),
):
    task = _streaming_tasks.get(message_id)
    if task is not None and not task.done():
        task.cancel()
    return None
```

- [ ] **Step 4: Verify zero behaviour change — full test suite passes**

```bash
python -m pytest -q
```

Expected: same green count as Step 1 (no new tests, no breaks). If `tests/api/test_message_streaming.py` imports `_streaming_tasks` from the old location, fix it by updating the import to `from pacer.api.streaming import get_streaming_tasks`.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/api/streaming.py src/pacer/api/routes/message.py tests/api/test_message_streaming.py
git commit -m "refactor(api): extract start_assistant_stream so endpoints can share it"
```

(Drop `tests/api/test_message_streaming.py` from the `git add` if no import fix was needed.)

---

### Task 2: Teach the subject teacher the review protocol

**Files:**
- Modify: `src/pacer/agents/subject_teacher.py`

Pure prompt edit — no new tests required at this layer; Task 5 covers the behaviour end-to-end with a mocked LLM script.

- [ ] **Step 1: Replace `SUBJECT_SYSTEM_TMPL` in `src/pacer/agents/subject_teacher.py`**

```python
SUBJECT_SYSTEM_TMPL = """你是一位{subject}学科老师，专业、严谨、爱启发。不寒暄、不闲聊，专注讲解。

常规答疑流程：
1. 先调 list_skills(subject="{subject}") 看可用的知识点资料
2. 调 load_skill(name=...) 加载相关知识点的完整内容
3. 给学生分步讲解，关键提示要点。如果学生提供了图片，用 vision_understand_image 先看题
4. 如果学生答错了，用 save_error_record 记录
5. 讲解后问"要不要做变式题？"→ 用 generate_variant 出题 → 用 mark_error_reviewed 反馈
6. 讲完后调 return_to_homeroom 把对话交回班主任

【错题复盘协议】
当用户首条消息以 `[复盘错题 #<error_id>]` 开头时，按以下顺序工作：
1. 解析出 error_id、题目、用户答案、正确答案
2. 用 1-2 段把"错在哪 / 正确做法的关键步骤"讲清楚
3. 调 generate_variant(original_stem=...) 出一道变式题，邀请学生作答
4. 收到学生答复后，判断对错：
   - 调 mark_error_reviewed(error_record_id=<error_id>, correct=<bool>)
   - 若该错题关联了 knowledge_point_id，再调 update_student_mastery
5. 简短总结、鼓励，然后 return_to_homeroom

学生当前的薄弱点你可以用 get_student_weakness 和 search_memory(query="...") 查询。"""
```

- [ ] **Step 2: Confirm tests still pass (no behavioural test asserts on this prompt)**

```bash
python -m pytest -q
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add src/pacer/agents/subject_teacher.py
git commit -m "feat(subject): teach an error-review protocol triggered by [复盘错题 …]"
```

---

### Task 3: POST /errors/{error_id}/start-review endpoint

**Files:**
- Modify: `src/pacer/api/routes/resources.py`
- Test: `tests/api/test_start_review.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_start_review.py`:

```python
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.api.streaming import get_streaming_tasks
from pacer.db.models import Base, ErrorRecord, Message, Question, Student
from pacer.llm.client import LLMResponse


def _llm(text="ok"):
    return LLMResponse(
        text=text, tool_calls=[], stop_reason="end_turn",
        input_tokens=5, output_tokens=5, raw=None,
    )


@pytest.mark.asyncio
async def test_start_review_creates_session_with_seed_message(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Question(id=11, subject="math", stem="求 f(x)=x^2 的导数", answer="2x"))
        s.add(ErrorRecord(
            id=21, student_id=1, question_id=11,
            user_answer="x", correct_answer="2x", error_type="concept",
            source="text", explanation_text="",
        ))
        s.commit()
    app = create_app(database_url=url)

    async def _mock_chat(*args, **kwargs):
        return _llm('{"intent":"subject_qa","subject":"math","confidence":0.9}')

    with patch("pacer.llm.client.LLMClient.chat", new=AsyncMock(side_effect=_mock_chat)):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t",
        ) as ac:
            tok = (await ac.post(
                "/auth/login", json={"student_id": 1, "pin": "123456"},
            )).json()["token"]
            r = await ac.post(
                "/errors/21/start-review",
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r.status_code == 202
            body = r.json()
            session_id = body["session_id"]
            msg_id = body["assistant_message_id"]
            task = get_streaming_tasks().get(msg_id)
            if task is not None:
                await task

    with Session(engine) as s:
        msgs = (
            s.query(Message)
            .filter_by(session_id=session_id)
            .order_by(Message.id)
            .all()
        )
        assert len(msgs) >= 2
        seed = msgs[0]
        assert seed.role == "user"
        assert "[复盘错题 #21]" in seed.content
        assert "求 f(x)=x^2 的导数" in seed.content
        assert "我的答案: x" in seed.content
        assert "正确答案: 2x" in seed.content
        assert msgs[1].role == "assistant"


@pytest.mark.asyncio
async def test_start_review_404_for_other_students_error(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Student(id=2, name="B", grade=12, pin_hash=deps.hash_pin("000000")))
        s.add(Question(id=11, subject="math", stem="?", answer="."))
        s.add(ErrorRecord(
            id=22, student_id=2, question_id=11,
            user_answer="", correct_answer="", error_type="concept",
            source="text",
        ))
        s.commit()
    app = create_app(database_url=url)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
    ) as ac:
        tok = (await ac.post(
            "/auth/login", json={"student_id": 1, "pin": "123456"},
        )).json()["token"]
        r = await ac.post(
            "/errors/22/start-review",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_start_review_requires_auth(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    app = create_app(database_url=url)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
    ) as ac:
        r = await ac.post("/errors/1/start-review")
        assert r.status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/api/test_start_review.py -v
```

Expected: FAIL with 404/405 (endpoint not registered).

- [ ] **Step 3: Add the endpoint to `src/pacer/api/routes/resources.py`**

Add these imports near the top of the file:

```python
from fastapi import Request
from pacer.api.streaming import start_assistant_stream
from pacer.session.store import SessionStore
```

Append the handler at the bottom of the module:

```python
@router.post("/errors/{error_id}/start-review", status_code=202)
def start_error_review(
    error_id: int,
    request: Request,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    e = db.query(ErrorRecord).filter_by(id=error_id, student_id=student_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="error not found")
    stem = e.question.stem if e.question else "(题干缺失)"
    seed_text = (
        f"[复盘错题 #{e.id}] "
        f"题目: {stem}\n"
        f"我的答案: {e.user_answer or '(空)'}\n"
        f"正确答案: {e.correct_answer or '(未给)'}"
    )

    store = SessionStore(db)
    chat = store.create_session(student_id=student_id)
    store.append_message(
        chat.id, role="user", agent=None, content=seed_text,
        metadata={"error_review_id": e.id},
    )
    assistant_msg = store.create_empty_assistant(chat.id, agent="subject_teacher")

    start_assistant_stream(
        app_state=request.app.state,
        student_id=student_id,
        session_id=chat.id,
        assistant_message_id=assistant_msg.id,
        user_message_for_llm=seed_text,
        user_text_for_memory=seed_text,
        history=[],
    )
    return {"session_id": chat.id, "assistant_message_id": assistant_msg.id}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/api/test_start_review.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/api/routes/resources.py tests/api/test_start_review.py
git commit -m "feat(errors): POST /errors/{id}/start-review seeds a review session"
```

---

### Task 4: Frontend "开始复盘" button + route push

**Files:**
- Modify: `src/pacer/web-next/src/views/ErrorsView.vue`

- [ ] **Step 1: Replace `src/pacer/web-next/src/views/ErrorsView.vue` entirely**

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

type ErrorRow = {
  id: number
  error_type: string
  source: string
  user_answer: string | null
  correct_answer: string | null
  explanation_text: string | null
}

const errors = ref<ErrorRow[]>([])
const loading = ref(true)
const reviewing = ref<number | null>(null)
const router = useRouter()

onMounted(async () => {
  try { const r = await apiFetch<{ items: ErrorRow[] }>('/errors'); errors.value = r.items || [] }
  catch { /* keep empty */ }
  finally { loading.value = false }
})

async function startReview(e: ErrorRow): Promise<void> {
  if (reviewing.value !== null) return
  reviewing.value = e.id
  try {
    const r = await apiFetch<{ session_id: number }>(
      `/errors/${e.id}/start-review`,
      { method: 'POST' },
    )
    router.push(`/chat/${r.session_id}`)
  } catch {
    reviewing.value = null
  }
}
</script>

<template>
  <AppShell>
    <div class="page">
      <h1>错题本</h1>
      <p v-if="loading" class="hint">翻阅中…</p>
      <p v-else-if="errors.length === 0" class="empty">暂未记下错题</p>
      <div v-for="e in errors" :key="e.id" class="card">
        <div class="meta">{{ e.error_type }} · {{ e.source }}</div>
        <div class="answer">你的答案: {{ e.user_answer || '——' }}</div>
        <div class="answer">正确答案: {{ e.correct_answer || '——' }}</div>
        <div v-if="e.explanation_text" class="explain">{{ e.explanation_text }}</div>
        <div class="actions">
          <button
            class="review-btn"
            :disabled="reviewing === e.id"
            @click="startReview(e)"
          >
            {{ reviewing === e.id ? '正在准备…' : '开始复盘' }}
          </button>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.page { max-width:720px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:24px; margin-bottom:var(--space-6); }
.hint,.empty { color:var(--ink-500); font-family:var(--font-serif); font-size:15px; text-align:center; padding:var(--space-12) 0; }
.card { background:var(--paper-1); border:1px solid var(--ink-300); border-radius:var(--radius-md); padding:var(--space-4); margin-bottom:var(--space-3); }
.meta { font-size:11px; color:var(--ink-500); margin-bottom:var(--space-2); }
.answer { font-size:14px; color:var(--ink-700); margin-bottom:4px; }
.explain { font-size:13px; color:var(--ink-900); margin-top:var(--space-2); border-top:1px solid var(--ink-300); padding-top:var(--space-2); }
.actions { margin-top:var(--space-3); display:flex; justify-content:flex-end; }
.review-btn { font-size:13px; padding:6px 12px; border:1px solid var(--ink-700); background:var(--paper-0); color:var(--ink-900); border-radius:var(--radius-sm); cursor:pointer; }
.review-btn:hover:not(:disabled) { background:var(--ink-900); color:var(--paper-0); }
.review-btn:disabled { opacity:0.5; cursor:wait; }
</style>
```

- [ ] **Step 2: Run frontend type-check**

```bash
cd src/pacer/web-next && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 3: Run frontend tests (no new ones; verify no regression)**

```bash
cd src/pacer/web-next && pnpm test
```

Expected: existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add src/pacer/web-next/src/views/ErrorsView.vue
git commit -m "feat(errors-ui): 开始复盘 button → POST /errors/{id}/start-review → /chat/:sid"
```

---

### Task 5: E2E test — full review loop with mastery update

**Files:**
- Create: `tests/e2e/test_error_review_flow.py`

- [ ] **Step 1: Write the e2e test**

```python
"""E2E: starting an error review drives the subject teacher through
mark_error_reviewed → mastery update.

We script the LLM with three responses:
  1. router: subject_qa / math
  2. subject teacher: tool_use mark_error_reviewed(correct=True)
  3. subject teacher: final text reply

The agent loop is non-streaming throughout (because the streaming runner
uses chat() per iteration and only chunk-emits the final text), so a flat
list of LLMResponse objects is enough.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.api.streaming import get_streaming_tasks
from pacer.db.models import Base, ErrorRecord, Question, Student
from pacer.llm.client import LLMResponse


def _resp(text: str = "", tool_calls=None, stop: str = "end_turn") -> LLMResponse:
    return LLMResponse(
        text=text, tool_calls=tool_calls or [], stop_reason=stop,
        input_tokens=5, output_tokens=5, raw=None,
    )


@pytest.mark.asyncio
async def test_start_review_runs_full_loop_and_updates_mastery(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Question(id=11, subject="math", stem="求 f(x)=x^2 的导数", answer="2x"))
        s.add(ErrorRecord(
            id=21, student_id=1, question_id=11,
            user_answer="x", correct_answer="2x", error_type="concept",
            source="text", mastery_level=0.5, review_count=0,
        ))
        s.commit()
    app = create_app(database_url=url)

    call_index = 0

    async def _mock_chat(*args, **kwargs):
        nonlocal call_index
        call_index += 1
        if call_index == 1:
            # Router classifies as subject_qa / math
            return _resp(text='{"intent":"subject_qa","subject":"math","confidence":0.95}')
        if call_index == 2:
            # Subject teacher's first turn: call mark_error_reviewed correct=True
            return _resp(
                tool_calls=[{
                    "id": "tc1",
                    "name": "mark_error_reviewed",
                    "input": {"error_record_id": 21, "correct": True},
                }],
                stop="tool_use",
            )
        # Subject teacher's wrap-up reply
        return _resp(text="不错，看来你掌握了。我们今天就到这里。")

    with patch("pacer.llm.client.LLMClient.chat", new=AsyncMock(side_effect=_mock_chat)):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t",
        ) as ac:
            tok = (await ac.post(
                "/auth/login", json={"student_id": 1, "pin": "123456"},
            )).json()["token"]
            r = await ac.post(
                "/errors/21/start-review",
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r.status_code == 202
            msg_id = r.json()["assistant_message_id"]
            task = get_streaming_tasks().get(msg_id)
            if task is not None:
                await task

    with Session(engine) as s:
        e = s.get(ErrorRecord, 21)
        assert e.review_count == 1
        # mark_error_reviewed correct=True bumps mastery_level by 0.15
        assert e.mastery_level == pytest.approx(0.65, abs=0.001)
        assert e.last_reviewed_at is not None
```

- [ ] **Step 2: Run the e2e test**

```bash
python -m pytest tests/e2e/test_error_review_flow.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_error_review_flow.py
git commit -m "test(e2e): error-review start → mark_reviewed → mastery update"
```

---

### Task 6: Full regression + build

- [ ] **Step 1: Run the full Python suite**

```bash
python -m pytest -q
```

Expected: all green (existing 57 + Task 3 (3 new) + Task 5 (1 new)).

- [ ] **Step 2: Frontend type-check + build**

```bash
cd src/pacer/web-next && pnpm typecheck && pnpm build
```

Expected: both succeed.

- [ ] **Step 3: Manual smoke**

Backend:
```bash
uvicorn pacer.api.server:create_app --factory --reload --port 8001
```

Frontend:
```bash
cd src/pacer/web-next && pnpm dev
```

Steps:
1. Log in as the dev student.
2. Send a chat asking the homeroom to record an error (or seed one via SQL).
3. Visit `/errors`. The card now shows a "开始复盘" button.
4. Click it. Browser navigates to `/chat/<new_sid>`. The conversation shows the `[复盘错题 #N] …` seed message; the assistant's reply streams in.

- [ ] **Step 4: No commit if all green — work complete.**

---

## Definition of Done

- All Python tests pass (including the new endpoint test and the e2e mastery test).
- `pnpm typecheck` and `pnpm build` succeed.
- Clicking "开始复盘" on an error card routes to a new chat session whose first user message is the structured `[复盘错题 #N]` seed.
- A scripted-LLM run where the subject teacher calls `mark_error_reviewed(correct=True)` increments `review_count` and shifts `mastery_level` upward by 0.15.
- `start_assistant_stream` is shared between `/message/send` and `/errors/{id}/start-review`, with no duplicated streaming code.
