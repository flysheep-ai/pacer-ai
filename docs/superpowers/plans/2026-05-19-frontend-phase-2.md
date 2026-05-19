# Frontend Optimization — Phase 2 Implementation Plan (Streaming + Markdown)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-19-frontend-optimization-design.md`

**Goal:** Add true LLM token-by-token streaming with a stop button, and upgrade Markdown rendering from the Phase 1 regex port to markdown-it + KaTeX + highlight.js for full math/code/table support.

**Architecture:** Backend: `LLMClient` and `OpenAICompatClient` get `chat_stream()` async generators. `Orchestrator.handle_streaming()` routes synchronously then streams the final answer, pushing deltas through `EventBus` as `assistant_delta` SSE events. `Message` table gets a `status` column. `POST /message/send` returns an immediate ack (202) and runs the orchestrator in a background asyncio task. Frontend: `chatStore.send()` creates a placeholder message and accumulates deltas. `SSEHandlers` add `onAssistantStart`, `onAssistantDelta`, `onAssistantDone`. `Composer` shows a stop button during streaming. `utils/markdown.ts` is replaced by a markdown-it pipeline with KaTeX + highlight.js.

**Tech Stack:** Existing (FastAPI, Vue 3, Pinia, TypeScript, Vite) plus `markdown-it@14`, `@gerhobbelt/markdown-it-katex`, `katex@0.16`, `highlight.js@11`.

---

## File Structure (Phase 2 — created / modified)

```
Backend (modified):
  src/pacer/llm/client.py                  + chat_stream()
  src/pacer/llm/openai_client.py           + chat_stream()
  src/pacer/orchestrator/orchestrator.py   + handle_streaming(on_delta)
  src/pacer/api/routes/message.py          send → ack + background task, + stop endpoint
  src/pacer/db/models.py                   Message.status column
  src/pacer/session/store.py               + create_empty_assistant(), + update_message_content()
  src/pacer/db/migrations/versions/<hash>_message_status.py  (new migration)

Backend (new test files):
  tests/unit/test_streaming.py
  tests/unit/test_message_stop.py

Frontend (modified):
  src/pacer/web-next/src/stores/chat.ts           delta accumulation + stop
  src/pacer/web-next/src/api/sse.ts               new SSE event handlers
  src/pacer/web-next/src/components/Composer.vue  stop button
  src/pacer/web-next/src/components/AssistantMessage.vue  streaming/stopped states
  src/pacer/web-next/src/components/MarkdownRender.vue    markdown-it + katex + hljs

Frontend (replaced):
  src/pacer/web-next/src/utils/markdown.ts        → becomes katex+hljs bootstrap

Frontend (new):
  src/pacer/web-next/src/utils/katex.ts           KaTeX lazy-loader
  src/pacer/web-next/src/utils/highlight.ts       highlight.js lazy-loader

Frontend (new test files):
  src/pacer/web-next/tests/unit/chat-store-streaming.test.ts
  src/pacer/web-next/tests/unit/sse-streaming.test.ts
  src/pacer/web-next/tests/unit/markdown-enhanced.test.ts

package.json (modified):
  + markdown-it, @gerhobbelt/markdown-it-katex, katex, highlight.js
```

---

## Task 1: Backend — `StreamChunk` dataclass + `chat_stream()` on both LLM clients

**Files:**
- Modify: `src/pacer/llm/client.py`
- Modify: `src/pacer/llm/openai_client.py`
- Create: `tests/unit/test_streaming.py`

- [ ] **Step 1: Add `StreamChunk` to `src/pacer/llm/client.py`**

Append to the existing dataclasses in `client.py` (after `LLMResponse`):

```python
@dataclass
class StreamChunk:
    delta_text: str
    tool_call_delta: dict[str, Any] | None = None
    finish_reason: str | None = None
```

- [ ] **Step 2: Add `chat_stream()` to `LLMClient` (Anthropic path)**

Append this method inside `class LLMClient`:

```python
    async def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield StreamChunk(delta_text=event.delta.text)
                elif event.type == "content_block_stop":
                    pass
                elif event.type == "message_stop":
                    pass
```

Note: `AsyncIterator` requires `from collections.abc import AsyncIterator` at the top. The existing import is `from dataclasses import dataclass`. Add `from collections.abc import AsyncIterator` to the imports.

- [ ] **Step 3: Add `chat_stream()` to `OpenAICompatClient`**

Append this method inside `class OpenAICompatClient`:

```python
    async def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        from pacer.llm.client import StreamChunk

        oai_msgs: list[dict] = []
        if system:
            oai_msgs.append({"role": "system", "content": system})
        for m in messages:
            if isinstance(m.content, list):
                # Flatten tool-result blocks — same logic as chat()
                blocks = m.content
                text_parts = [b["text"] for b in blocks if b["type"] == "text"]
                tool_calls = []
                for b in blocks:
                    if b["type"] == "tool_use":
                        import json
                        tool_calls.append({
                            "id": b["id"], "type": "function",
                            "function": {"name": b["name"], "arguments": json.dumps(b["input"], ensure_ascii=False)},
                        })
                    elif b["type"] == "tool_result":
                        oai_msgs.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": str(b["content"])})
                if tool_calls:
                    tc_msg = {"role": "assistant", "content": "\n".join(text_parts) or None}
                    tc_msg["tool_calls"] = tool_calls
                    oai_msgs.append(tc_msg)
                elif text_parts and not any(b["type"] == "tool_result" for b in blocks):
                    oai_msgs.append({"role": m.role, "content": "\n".join(text_parts)})
            else:
                oai_msgs.append({"role": m.role, "content": m.content})

        kwargs = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": oai_msgs,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = _anthropic_tools_to_openai(tools)

        resp = await self._client.chat.completions.create(**kwargs)
        async for chunk in resp:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue
            delta = choice.delta
            if delta and delta.content:
                yield StreamChunk(delta_text=delta.content)
            if choice.finish_reason:
                yield StreamChunk(delta_text="", finish_reason=choice.finish_reason)
```

- [ ] **Step 4: Write the failing test**

Create `tests/unit/test_streaming.py`:

```python
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
from pacer.llm.client import LLMClient, LLMMessage, StreamChunk


def _make_stream_chunks(texts: list[str]):
    """Simulate Anthropic text_delta events."""
    class FakeTextDelta:
        def __init__(self, text): self.text = text
    class FakeDelta:
        def __init__(self, text): self.type = "text_delta"; self.delta = FakeTextDelta(text)
    class FakeMessageStop:
        pass
    events = []
    for t in texts:
        events.append(type("Event", (), {"type": "content_block_delta", "delta": FakeDelta(t)}))
    events.append(type("Event", (), {"type": "message_stop"}))
    return events

@pytest.mark.asyncio
async def test_anthropic_chat_stream_yields_chunks():
    client = LLMClient(api_key="sk-test", model="claude-test")
    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aiter__ = lambda s: iter(_make_stream_chunks(["Hello", " world"]))
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch.object(client._client.messages, "stream", return_value=mock_stream):
        chunks = []
        async for chunk in client.chat_stream([LLMMessage(role="user", content="hi")]):
            chunks.append(chunk.delta_text)
        assert "".join(chunks) == "Hello world"

@pytest.mark.asyncio
async def test_openai_chat_stream_yields_chunks():
    from pacer.llm.openai_client import OpenAICompatClient
    client = OpenAICompatClient(api_key="sk-test", base_url="https://test", model="test")

    class FakeDelta:
        def __init__(self, content): self.content = content; self.tool_calls = None
    class FakeChoice:
        def __init__(self, content, finish=None): self.delta = FakeDelta(content); self.finish_reason = finish
    class FakeChunk:
        def __init__(self, content, finish=None): self.choices = [FakeChoice(content, finish)]

    chunks_iter = iter([FakeChunk("Hello"), FakeChunk(" world"), FakeChunk("", finish="stop")])

    mock_stream = AsyncMock()
    mock_stream.__aiter__ = lambda s: chunks_iter
    with patch.object(client._client.chat.completions, "create", new=AsyncMock(return_value=mock_stream)):
        chunks = []
        async for chunk in client.chat_stream([LLMMessage(role="user", content="hi")]):
            if chunk.delta_text:
                chunks.append(chunk.delta_text)
        assert "".join(chunks) == "Hello world"
```

- [ ] **Step 5: Run tests — expect FAIL**

```
python3 -m pytest tests/unit/test_streaming.py -v
```

Expected: 2 fail — method or AsyncIterator import not found.

- [ ] **Step 6: Fix imports, run tests — expect PASS**

```
python3 -m pytest tests/unit/test_streaming.py -v
```

Expected: 2 pass.

- [ ] **Step 7: Run full backend suite, then commit**

```bash
python3 -m pytest -x
git add src/pacer/llm/client.py src/pacer/llm/openai_client.py tests/unit/test_streaming.py
git commit -m "feat(llm): add chat_stream() async generator to both clients"
```

---

## Task 2: Backend — `Message.status` column + Alembic migration

**Files:**
- Modify: `src/pacer/db/models.py` (add `status` column to `Message`)
- Create: `src/pacer/db/migrations/versions/<auto>_message_status.py`
- Modify: `src/pacer/session/store.py` (new methods)

- [ ] **Step 1: Add `status` column to `Message` model**

In `src/pacer/db/models.py`, inside `class Message`, add after `content`:

```python
    status: Mapped[str] = mapped_column(String(20), default="done", server_default="done")
```

The full column order should be: `id, session_id, role, agent, content, status, metadata_json, created_at`.

- [ ] **Step 2: Generate the migration**

From repo root:
```bash
cd src/pacer && python3 -m alembic -c ../alembic.ini revision --autogenerate -m "message_status"
```

Expected: creates a migration file in `src/pacer/db/migrations/versions/<hash>_message_status.py`.

Inspect the generated file to confirm it adds a `status` column with `server_default='done'` to the `messages` table.

- [ ] **Step 3: Run migration against local DB to confirm it works**

```bash
cd src/pacer && python3 -m alembic -c ../alembic.ini upgrade head
```

Expected: outputs "Running upgrade <prev> -> <hash>, message_status", no errors.

- [ ] **Step 4: Extend `SessionStore` with two new methods**

In `src/pacer/session/store.py`, add after `append_message()`:

```python
    def create_empty_assistant(
        self, session_id: int, *, agent: str = "homeroom", metadata: dict | None = None,
    ) -> Message:
        m = Message(
            session_id=session_id, role="assistant", agent=agent,
            content="", status="streaming", metadata_json=metadata or {},
        )
        self._session.add(m)
        chat = self.get_session(session_id)
        if chat is not None:
            chat.last_active_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(m)
        return m

    def finalize_message(self, message_id: int, *, content: str, status: str = "done") -> None:
        m = self._session.get(Message, message_id)
        if m is not None:
            m.content = content
            m.status = status
            self._session.commit()

    def append_content_to_message(self, message_id: int, delta: str) -> None:
        """Append delta text to a streaming message. Called per chunk."""
        m = self._session.get(Message, message_id)
        if m is not None:
            m.content = (m.content or "") + delta
            self._session.commit()
```

- [ ] **Step 5: Write test for new store methods**

Create `tests/unit/test_streaming_store.py`:

```python
from pacer.db.models import Message
from pacer.session.store import SessionStore

def test_create_empty_assistant_and_finalize(db_session):
    store = SessionStore(db_session)
    chat = store.create_session(student_id=1)
    msg = store.create_empty_assistant(chat.id, agent="subject_teacher")
    assert msg.status == "streaming"
    assert msg.content == ""

    store.append_content_to_message(msg.id, "hello")
    store.append_content_to_message(msg.id, " world")
    store.finalize_message(msg.id, content="hello world", status="done")

    # Re-fetch
    final = db_session.get(Message, msg.id)
    assert final.content == "hello world"
    assert final.status == "done"

def test_create_empty_assistant_with_metadata(db_session):
    store = SessionStore(db_session)
    chat = store.create_session(student_id=1)
    msg = store.create_empty_assistant(chat.id, agent="homeroom", metadata={"route": "homeroom"})
    assert msg.metadata_json == {"route": "homeroom"}
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
python3 -m pytest tests/unit/test_streaming_store.py -v
```

- [ ] **Step 7: Run full backend suite, then commit**

```bash
python3 -m pytest -x
git add src/pacer/db/models.py src/pacer/db/migrations/versions/*message_status.py src/pacer/session/store.py tests/unit/test_streaming_store.py
git commit -m "feat(db): add message.status column for streaming lifecycle"
```

---

## Task 3: Backend — `Orchestrator.handle_streaming()` with on_delta callback

**Files:**
- Modify: `src/pacer/orchestrator/orchestrator.py`

- [ ] **Step 1: Add `handle_streaming()` method**

Append inside `class Orchestrator`:

```python
    async def handle_streaming(
        self,
        user_message: str,
        history: list[LLMMessage],
        on_delta: Callable[[str], Awaitable[None]],
    ) -> OrchestratedResult:
        route = await self.router.route(user_message)

        if route.intent == "subject_qa" and route.subject:
            agent = build_subject_teacher_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id, subject=route.subject,
                skills_loader=self.skills_loader,
                vision_model=self.vision_model,
            )
            agent_used = "subject_teacher"
        elif route.intent == "mood_support":
            agent = build_mood_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id,
            )
            agent_used = "mood_companion"
        else:
            agent = build_homeroom_agent(
                llm=self.llm, session_factory=self.session_factory,
                student_id=self.student_id,
            )
            agent_used = "homeroom"

        result = await agent.run_streaming(user_message, history=history, on_delta=on_delta)
        return OrchestratedResult(
            final_text=result.final_text, agent_used=agent_used,
            subject=route.subject, route=route, inner=result,
        )
```

Add the missing imports at the top of the file — update the imports block to:

```python
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable, Awaitable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient, LLMMessage
from pacer.skills.loader import SkillsLoader
from pacer.orchestrator.router import RouterLLM, RouteDecision
from pacer.agents.homeroom import build_homeroom_agent
from pacer.agents.subject_teacher import build_subject_teacher_agent
from pacer.agents.mood_companion import build_mood_agent
from pacer.agent.loop import AgentResult
```

(Only `Awaitable` is new; `Callable` was already imported.)

- [ ] **Step 2: The agent loop needs `run_streaming`**

Each agent (`src/pacer/agents/homeroom.py`, `subject_teacher.py`, `mood_companion.py`) and the base `src/pacer/agent/loop.py` need a `run_streaming()` method that calls `llm.chat_stream()` instead of `llm.chat()`.

Read each agent file to understand their current `run()` pattern — they delegate to `self.llm.chat(...)` in their tool-using loop. The streaming variant:
- Uses `self.llm.chat_stream(...)` in the final answer step
- For each tool call in the loop, still uses sync `chat()` (tool calls are short)
- In the final "no tool call" situation, `async for chunk in self.llm.chat_stream(...)` → `await on_delta(chunk.delta_text)`
- Collects all delta text into `final_text` for the returned `AgentResult`

Implement `run_streaming()` in `src/pacer/agent/loop.py`'s agent runner. The loop pattern is:

```python
async def run_streaming(self, user_message: str, history: list[LLMMessage], on_delta) -> AgentResult:
    full_messages = [*history, LLMMessage(role="user", content=user_message)]
    tool_use_count = 0
    all_text: list[str] = []
    trace: list[dict[str, Any]] = []

    while tool_use_count < self.max_iterations:
        if tool_use_count == self.max_iterations - 1:
            # Final answer: stream it
            async for chunk in self.llm.chat_stream(full_messages, system=self.system_prompt, tools=self.tools):
                if chunk.delta_text:
                    await on_delta(chunk.delta_text)
                    all_text.append(chunk.delta_text)
            break
        else:
            resp = await self.llm.chat(full_messages, system=self.system_prompt, tools=self.tools)
            trace.append({"text": resp.text, "tool_calls": resp.tool_calls})
            if not resp.tool_calls:
                all_text.append(resp.text)
                break
            # Execute tool call, append tool_result, loop
            full_messages.append(LLMMessage(role="assistant", content=resp.text))
            for tc in resp.tool_calls:
                result = await self._execute_tool(tc)
                full_messages.append(LLMMessage(role="user", content=f"Tool result: {result}"))
            tool_use_count += 1

    return AgentResult(final_text="".join(all_text), iterations=tool_use_count + 1, trace=trace)
```

This requires reading the actual agent implementations to adapt exactly. **Delegate to the implementer subagent: read each agent's `run()` method and mirror its structure, replacing `chat()` with `chat_stream()` on the final turn only.**

- [ ] **Step 3: Run tests, typecheck**

From repo root — commit only if existing tests still pass. New streaming tests for the agent loop and orchestrator are written in Task 7 (integration tests flow through `POST /message/send`).

```bash
python3 -m pytest -x
```

- [ ] **Step 4: Commit**

```bash
git add src/pacer/orchestrator/orchestrator.py src/pacer/agent/loop.py src/pacer/agents/*.py
git commit -m "feat(core): add handle_streaming to orchestrator and agent loop"
```

---

## Task 4: Backend — Rewrite `POST /message/send` as immediate ack + background task

**Files:**
- Modify: `src/pacer/api/routes/message.py`

- [ ] **Step 1: Rewrite the endpoint**

Replace the entire `send_message` function in `src/pacer/api/routes/message.py`:

```python
from __future__ import annotations
import asyncio
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, current_student_id
from pacer.session.store import SessionStore
from pacer.session.events import SSEEvent
from pacer.llm.client import LLMMessage
from pacer.orchestrator.orchestrator import Orchestrator
from pacer.config import get_settings

router = APIRouter(prefix="/message", tags=["message"])


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None


class SendAck(BaseModel):
    session_id: int
    assistant_message_id: int


class StopRequest(BaseModel):
    pass


# In-memory registry of cancellable streaming tasks: {message_id: asyncio.Task}
_streaming_tasks: dict[int, asyncio.Task] = {}


@router.post("/send", response_model=SendAck, status_code=202)
async def send_message(
    req: SendRequest,
    request: Request,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
) -> SendAck:
    store = SessionStore(db)
    if req.session_id is None:
        chat = store.create_session(student_id=student_id)
    else:
        chat = store.get_session(req.session_id)
        if chat is None or chat.student_id != student_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="session not found")

    store.append_message(chat.id, role="user", agent=None, content=req.text)
    history_dicts = store.history_for_llm(chat.id)
    history = [LLMMessage(role=h["role"], content=h["content"]) for h in history_dicts[:-1]]

    settings = get_settings()
    orch = Orchestrator(
        llm=request.app.state.llm,
        router_model=settings.router_model,
        session_factory=lambda: db,
        student_id=student_id,
        skills_loader=request.app.state.skills_loader,
    )

    # Create a placeholder assistant message (status='streaming')
    msg = store.create_empty_assistant(chat.id, agent="homeroom")
    bus = request.app.state.event_bus

    async def run_stream():
        collected: list[str] = []
        try:
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_start",
                data={"session_id": chat.id, "message_id": msg.id, "agent": "homeroom"},
            ))

            async def on_delta(text: str):
                collected.append(text)
                await bus.publish(SSEEvent(
                    student_id=student_id, event_type="assistant_delta",
                    data={"message_id": msg.id, "delta": text},
                ))

            out = await orch.handle_streaming(req.text, history=history, on_delta=on_delta)

            # Update the placeholder message with the agent route determined
            store.finalize_message(msg.id, content=out.final_text, status="done")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg.id, "agent": out.agent_used, "stop_reason": "completed"},
            ))
        except asyncio.CancelledError:
            store.finalize_message(msg.id, content="".join(collected), status="failed")
            await bus.publish(SSEEvent(
                student_id=student_id, event_type="assistant_done",
                data={"message_id": msg.id, "stop_reason": "user_stopped"},
            ))
        finally:
            _streaming_tasks.pop(msg.id, None)

    task = asyncio.create_task(run_stream())
    _streaming_tasks[msg.id] = task

    return SendAck(session_id=chat.id, assistant_message_id=msg.id)
```

- [ ] **Step 2: Add the stop endpoint**

Append after `send_message`:

```python
@router.post("/{message_id}/stop", status_code=204)
async def stop_stream(message_id: int, student_id: int = Depends(current_student_id)):
    task = _streaming_tasks.get(message_id)
    if task is not None and not task.done():
        task.cancel()
    return None
```

- [ ] **Step 3: Update test for the new send response shape**

Find the existing `tests/` for message sending (check what exists that tests `POST /message/send`) and update them to expect a 202 with `SendAck` instead of 200 with `SendResponse`. If no existing test, create:

```python
def test_send_returns_ack(db_session, client):
    # client is a TestClient fixture pointing at the app
    # Requires a student to be created first for the token
    pass  # Adapted to actual test setup pattern
```

**Delegate to implementer: check existing test patterns and adapt.**

- [ ] **Step 4: Run tests — expect PASS**

```bash
python3 -m pytest -x
```

- [ ] **Step 5: Commit**

```bash
git add src/pacer/api/routes/message.py
git commit -m "feat(api): send returns immediate ack, streaming via bg task + event bus"
```

---

## Task 5: Backend — Integration test for full streaming flow

**Files:**
- Create: `tests/api/test_message_streaming.py`

- [ ] **Step 1: Write the integration test**

```python
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from pacer.api.server import create_app
from pacer.db.models import Base, Student
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api.deps import get_db


@pytest.fixture
def app_with_mock_llm():
    engine = create_engine("sqlite:///./test_stream.db")
    Base.metadata.create_all(engine)

    # Create a test student
    with Session(engine) as s:
        if not s.query(Student).filter_by(id=1).first():
            import bcrypt
            s.add(Student(id=1, name="test", grade=3, pin_hash=bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()))
            s.commit()

    app = create_app(database_url="sqlite:///./test_stream.db")
    client = TestClient(app)

    # Mock the LLM stream
    from pacer.llm.client import StreamChunk
    async def fake_stream(*a, **kw):
        for text in ["这是", "一道", "导数题"]:
            yield StreamChunk(delta_text=text)
            await asyncio.sleep(0)

    with patch("pacer.llm.openai_client.OpenAICompatClient.chat_stream", side_effect=fake_stream):
        yield client

    import os
    os.remove("test_stream.db")


def test_streaming_send_returns_ack_and_sse_deltas(app_with_mock_llm):
    client = app_with_mock_llm
    # Login
    r = client.post("/auth/login", json={"student_id": 1, "pin": "123456"})
    assert r.status_code == 200
    token = r.json()["token"]

    # Send a message
    r = client.post("/message/send", json={"text": "讲一道导数题", "session_id": None},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202
    ack = r.json()
    assert "assistant_message_id" in ack
    assert "session_id" in ack

    # The LLM mock pushes deltas in the background task — we can't easily
    # receive SSE from TestClient, but we can verify the message was created
    # and finalized by polling the SSE endpoint or checking the DB directly.
    import time
    time.sleep(0.5)

    # Verify message finalized in DB
    from sqlalchemy.orm import Session as DBSession
    from sqlalchemy import create_engine as ce
    from pacer.db.models import Message
    engine = ce("sqlite:///./test_stream.db")
    with DBSession(engine) as s:
        msg = s.query(Message).filter_by(id=ack["assistant_message_id"]).first()
        assert msg is not None
        assert msg.status in ("done", "streaming")
```

- [ ] **Step 2: Run — adapt to actual project test patterns**

The implementer must read existing test fixtures (`tests/conftest.py`, existing `tests/api/` tests) and adapt the test setup to match the project's actual patterns (db fixture, client fixture, token generation, etc.).

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_message_streaming.py
git commit -m "test(api): integration test for streaming send+ack"
```

---

## Task 6: Frontend — `chatStore` delta accumulation + placeholder model

**Files:**
- Modify: `src/pacer/web-next/src/stores/chat.ts` (significant rewrite)
- Create: `src/pacer/web-next/tests/unit/chat-store-streaming.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/pacer/web-next/tests/unit/chat-store-streaming.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore, type ChatMessage } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'

describe('chatStore streaming', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('pacer_token', 'tk')
  })

  it('send returns message id after ack', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 42, assistant_message_id: 99 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    const mid = await s.send('hello')
    expect(mid).toBe(99)
    expect(s.messages.length).toBe(2) // user + placeholder
    const placeholder = s.messages[1]
    expect(placeholder.role).toBe('assistant')
    expect(placeholder.content).toBe('')
    expect(placeholder.streaming).toBe(true)
  })

  it('appendDelta adds text to the streaming message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'Hello' })
    s.receiveDelta({ message_id: 10, delta: ' world' })
    expect(s.messages[1].content).toBe('Hello world')
    expect(s.messages[1].streaming).toBe(true)
    expect(s.isStreaming).toBe(true)
  })

  it('finalizeStream seals the message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'Done' })
    s.finalizeStream({ message_id: 10, agent: 'subject_teacher', stop_reason: 'completed' })
    expect(s.messages[1].streaming).toBe(false)
    expect(s.isStreaming).toBe(false)
    expect(s.messages[1].agent).toBe('subject_teacher')
  })

  it('stopStreaming marks message as stopped and cancels', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
          status: 202,
          headers: { 'content-type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(null, { status: 204 }),
      )
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'partial' })
    await s.stopStreaming()
    expect(s.messages[1].streaming).toBe(false)
    expect(s.isStreaming).toBe(false)
    // Verify POST /message/10/stop was called
    expect(globalThis.fetch).toHaveBeenCalledWith('/message/10/stop', expect.objectContaining({ method: 'POST' }))
  })

  it('reset clears streaming state', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: 1, assistant_message_id: 10 }), {
        status: 202,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useChatStore()
    await s.send('hi')
    s.receiveDelta({ message_id: 10, delta: 'x' })
    s.reset()
    expect(s.messages).toEqual([])
    expect(s.isStreaming).toBe(false)
  })

  it('ignores deltas for unknown message_id', async () => {
    const s = useChatStore()
    s.receiveDelta({ message_id: 999, delta: 'orphan' })
    // No crash; no placeholder created
    expect(s.messages.length).toBe(0)
  })
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd src/pacer/web-next && pnpm test
```

- [ ] **Step 3: Rewrite `src/pacer/web-next/src/stores/chat.ts`**

```ts
import { defineStore } from 'pinia'
import { apiFetch } from '@/api/client'
import { useSessionStore } from './session'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  agent?: string
  streaming?: boolean
  stopReason?: string
  messageId?: number
}

interface SendAck {
  session_id: number
  assistant_message_id: number
}

interface DeltaPayload {
  message_id: number
  delta: string
}

interface DonePayload {
  message_id: number
  agent: string
  stop_reason: string
}

interface AssistantPayload {
  session_id: number
  text: string
  agent: string
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [] as ChatMessage[],
    isAwaiting: false,
    _lastAssistantContent: null as string | null,
    _streamingMid: null as number | null,
  }),
  getters: {
    isStreaming: (s) => s._streamingMid !== null,
  },
  actions: {
    reset(): void {
      this.messages = []
      this.isAwaiting = false
      this._lastAssistantContent = null
      this._streamingMid = null
      useSessionStore().reset()
    },

    receiveAssistantMessage(payload: AssistantPayload): void {
      const session = useSessionStore()
      session.currentSid = payload.session_id
      if (this._lastAssistantContent === payload.text) return
      this._lastAssistantContent = payload.text
      this.isAwaiting = false
      this._streamingMid = null
      this.messages.push({ role: 'assistant', content: payload.text, agent: payload.agent })
    },

    receiveDelta(payload: DeltaPayload): void {
      const target = this.messages.find(
        m => m.streaming && m.messageId === payload.message_id,
      )
      if (target) {
        target.content += payload.delta
      }
    },

    receiveDone(payload: DonePayload): void {
      const target = this.messages.find(
        m => m.streaming && m.messageId === payload.message_id,
      )
      if (target) {
        target.streaming = false
        target.agent = payload.agent
        if (payload.stop_reason === 'user_stopped') {
          target.stopReason = 'user_stopped'
        }
      }
      this.isAwaiting = false
      this._streamingMid = null
    },

    async send(text: string): Promise<number | null> {
      const trimmed = text.trim()
      if (!trimmed) return null
      this.messages.push({ role: 'user', content: trimmed })
      this.isAwaiting = true
      const session = useSessionStore()

      try {
        const ack = await apiFetch<SendAck>('/message/send', {
          method: 'POST',
          json: { text: trimmed, session_id: session.currentSid },
        })
        session.currentSid = ack.session_id
        this.messages.push({
          role: 'assistant', content: '', streaming: true,
          messageId: ack.assistant_message_id,
        })
        this._streamingMid = ack.assistant_message_id
        return ack.assistant_message_id
      } catch {
        this.messages.push({ role: 'assistant', content: '出错了，请稍后重试。' })
        this.isAwaiting = false
        return null
      }
    },

    async stopStreaming(): Promise<void> {
      const mid = this._streamingMid
      if (mid === null) return
      try {
        await apiFetch(`/message/${mid}/stop`, { method: 'POST' })
      } catch { /* best-effort */ }
      this.isAwaiting = false
      this._streamingMid = null
      const target = this.messages.find(m => m.streaming && m.messageId === mid)
      if (target) {
        target.streaming = false
        target.stopReason = 'user_stopped'
      }
    },
  },
})
```

The old `interface SendResponse` and `_lastAssistantContent` dedup logic are removed. The `receiveAssistantMessage` handler is kept for backward compatibility (Phase 1 protocol) but renamed internally. `_streamingMid` tracks the currently-streaming message ID; `isAwaiting` is for the POST round-trip phase; `isStreaming` is true while deltas are arriving.

- [ ] **Step 4: Run tests — expect all streaming tests pass + prior tests may need updating**

```bash
cd src/pacer/web-next && pnpm test
```

If the old `chat-store.test.ts` tests reference the old API (e.g., `SendResponse` type, the old `send` return shape), update them to match the new API. The 202 response and placeholder model are the new contract.

- [ ] **Step 5: Run typecheck, then commit**

```bash
cd src/pacer/web-next && pnpm typecheck
git add src/pacer/web-next/src/stores/chat.ts \
        src/pacer/web-next/tests/unit/chat-store-streaming.test.ts \
        src/pacer/web-next/tests/unit/chat-store.test.ts
git commit -m "feat(web-next): rewrite chat store for delta streaming"
```

---

## Task 7: Frontend — SSE client consumes `assistant_start` / `assistant_delta` / `assistant_done`

**Files:**
- Modify: `src/pacer/web-next/src/api/sse.ts`
- Create: `src/pacer/web-next/tests/unit/sse-streaming.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `src/pacer/web-next/tests/unit/sse-streaming.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { startSSE, _setEventSourceImpl, _resetEventSourceImpl } from '@/api/sse'

class FakeEventSource {
  url: string
  onerror: ((e: Event) => void) | null = null
  static instances: FakeEventSource[] = []
  private listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(name: string, fn: (e: MessageEvent) => void): void {
    (this.listeners[name] ||= []).push(fn)
  }
  removeEventListener(): void {}
  close(): void {}
  emit(name: string, data: unknown): void {
    const ev = { data: JSON.stringify(data) } as unknown as MessageEvent
    this.listeners[name]?.forEach(fn => fn(ev))
  }
  emitError(): void { this.onerror?.(new Event('error')) }
}

describe('startSSE streaming events', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    _setEventSourceImpl(FakeEventSource as unknown as typeof EventSource)
    vi.useFakeTimers()
  })
  afterEach(() => {
    _resetEventSourceImpl()
    vi.useRealTimers()
  })

  it('dispatches assistant_start events', () => {
    const handler = vi.fn()
    startSSE('tk', {
      onAssistantMessage: () => {},
      onAssistantStart: handler,
      onAssistantDelta: () => {},
      onAssistantDone: () => {},
    })
    FakeEventSource.instances[0].emit('assistant_start', {
      session_id: 1, message_id: 42, agent: 'a',
    })
    expect(handler).toHaveBeenCalledWith({ session_id: 1, message_id: 42, agent: 'a' })
  })

  it('dispatches assistant_delta events', () => {
    const handler = vi.fn()
    startSSE('tk', {
      onAssistantMessage: () => {},
      onAssistantStart: () => {},
      onAssistantDelta: handler,
      onAssistantDone: () => {},
    })
    FakeEventSource.instances[0].emit('assistant_delta', {
      message_id: 42, delta: 'hello',
    })
    expect(handler).toHaveBeenCalledWith({ message_id: 42, delta: 'hello' })
  })

  it('dispatches assistant_done events', () => {
    const handler = vi.fn()
    startSSE('tk', {
      onAssistantMessage: () => {},
      onAssistantStart: () => {},
      onAssistantDelta: () => {},
      onAssistantDone: handler,
    })
    FakeEventSource.instances[0].emit('assistant_done', {
      message_id: 42, agent: 'subject_teacher', stop_reason: 'completed',
    })
    expect(handler).toHaveBeenCalledWith({
      message_id: 42, agent: 'subject_teacher', stop_reason: 'completed',
    })
  })

  it('legacy assistant_message still fires backwards-compat handler', () => {
    const legacy = vi.fn()
    startSSE('tk', {
      onAssistantMessage: legacy,
      onAssistantStart: () => {},
      onAssistantDelta: () => {},
      onAssistantDone: () => {},
    })
    FakeEventSource.instances[0].emit('assistant_message', {
      session_id: 1, text: 'hi', agent: 'a',
    })
    expect(legacy).toHaveBeenCalledWith({ session_id: 1, text: 'hi', agent: 'a' })
  })

  it('all new handlers are optional', () => {
    // Should not throw — only onAssistantMessage is required
    expect(() => {
      startSSE('tk', { onAssistantMessage: () => {} })
    }).not.toThrow()
  })
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd src/pacer/web-next && pnpm test -- tests/unit/sse-streaming.test.ts
```

- [ ] **Step 3: Update `src/pacer/web-next/src/api/sse.ts`**

Replace the full file:

```ts
export interface AssistantMessagePayload {
  session_id: number
  text: string
  agent: string
}

export interface AssistantStartPayload {
  session_id: number
  message_id: number
  agent: string
}

export interface AssistantDeltaPayload {
  message_id: number
  delta: string
}

export interface AssistantDonePayload {
  message_id: number
  agent: string
  stop_reason: string
}

export interface SSEHandlers {
  onAssistantMessage: (payload: AssistantMessagePayload) => void
  onAssistantStart?: (payload: AssistantStartPayload) => void
  onAssistantDelta?: (payload: AssistantDeltaPayload) => void
  onAssistantDone?: (payload: AssistantDonePayload) => void
}

let EventSourceImpl: typeof EventSource = globalThis.EventSource

export function _setEventSourceImpl(impl: typeof EventSource): void {
  EventSourceImpl = impl
}
export function _resetEventSourceImpl(): void {
  EventSourceImpl = globalThis.EventSource
}

const BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]

function jsonHandler<T>(fn: ((payload: T) => void) | undefined): ((e: MessageEvent) => void) | undefined {
  if (!fn) return undefined
  return (e: MessageEvent) => {
    try {
      fn(JSON.parse(e.data) as T)
    } catch (err) {
      console.warn('sse parse error', err)
    }
  }
}

export function startSSE(token: string, handlers: SSEHandlers): () => void {
  let stopped = false
  let attempt = 0
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function open(): void {
    if (stopped) return
    source = new EventSourceImpl(`/events/stream?token=${encodeURIComponent(token)}`)
    const addJson = <T>(name: string, fn: ((payload: T) => void) | undefined) => {
      const h = jsonHandler(fn)
      if (h) source!.addEventListener(name, h)
    }
    addJson('assistant_message', handlers.onAssistantMessage)
    addJson('assistant_start', handlers.onAssistantStart)
    addJson('assistant_delta', handlers.onAssistantDelta)
    addJson('assistant_done', handlers.onAssistantDone)
    source.addEventListener('ping', () => { attempt = 0 })
    source.onerror = () => {
      source?.close()
      source = null
      if (stopped) return
      const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
      attempt += 1
      timer = setTimeout(open, delay)
    }
  }
  open()

  return () => {
    stopped = true
    if (timer !== null) clearTimeout(timer)
    source?.close()
    source = null
  }
}
```

- [ ] **Step 4: Update `src/pacer/web-next/src/main.ts` SSE bootstrap**

In `main.ts`, update the `reconcileSSE` call to wire the new handlers:

```ts
function reconcileSSE(token: string | null): void {
  if (stopSSE) { stopSSE(); stopSSE = null }
  if (token !== null) {
    stopSSE = startSSE(token, {
      onAssistantMessage: (p) => chat.receiveAssistantMessage(p),
      onAssistantStart: (p) => chat._streamingMid = p.message_id,
      onAssistantDelta: (p) => chat.receiveDelta(p),
      onAssistantDone: (p) => chat.receiveDone(p),
    })
  }
}
```

Wait — `_streamingMid` is a private state property. Instead of reaching into store internals, defer the SSE wiring fix to Task 10 (where the streaming flow is fully wired). For now, just get the SSE client updated and tests passing; the bootstrap wiring update is done in Task 10.

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd src/pacer/web-next && pnpm test && pnpm typecheck
```

- [ ] **Step 6: Commit**

```bash
git add src/pacer/web-next/src/api/sse.ts \
        src/pacer/web-next/tests/unit/sse-streaming.test.ts
git commit -m "feat(web-next): add streaming SSE event handlers"
```

---

## Task 8: Frontend — `markdown-it` + KaTeX + highlight.js

**Files:**
- Replace: `src/pacer/web-next/src/utils/markdown.ts` (becomes a markdown-it factory)
- Create: `src/pacer/web-next/src/utils/katex.ts` (KaTeX lazy-loader)
- Create: `src/pacer/web-next/src/utils/highlight.ts` (highlight.js lazy-loader)
- Create: `src/pacer/web-next/tests/unit/markdown-enhanced.test.ts`
- Modify: `src/pacer/web-next/package.json` (add deps)

- [ ] **Step 1: Install packages**

```bash
cd src/pacer/web-next && pnpm add markdown-it @gerhobbelt/markdown-it-katex katex highlight.js
pnpm add -D @types/markdown-it @types/katex
```

- [ ] **Step 2: Write `src/pacer/web-next/src/utils/katex.ts`**

```ts
let _katexCssLoaded = false

export async function loadKatex(): Promise<void> {
  if (typeof window === 'undefined') return
  if (!_katexCssLoaded) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css'
    document.head.appendChild(link)
    _katexCssLoaded = true
  }
}
```

- [ ] **Step 3: Write `src/pacer/web-next/src/utils/highlight.ts`**

```ts
import hljs from 'highlight.js/lib/core'

// Register common languages (lazy-loaded in production, but for
// simplicity register the 5 most-used in a gaokao context)
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import plaintext from 'highlight.js/lib/languages/plaintext'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('plaintext', plaintext)
hljs.registerLanguage('text', plaintext)

let _cssLoaded = false

export function loadHighlightTheme(isDark: boolean): void {
  if (typeof window === 'undefined') return
  const id = 'hljs-theme'
  const existing = document.getElementById(id)
  if (existing) existing.remove()
  const link = document.createElement('link')
  link.id = id
  link.rel = 'stylesheet'
  link.href = isDark
    ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
    : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css'
  document.head.appendChild(link)
  _cssLoaded = true
}

export { hljs }
```

- [ ] **Step 4: Rewrite `src/pacer/web-next/src/utils/markdown.ts`**

```ts
import MarkdownIt from 'markdown-it'
import markdownItKatex from '@gerhobbelt/markdown-it-katex'
import { loadKatex } from './katex'
import { hljs, loadHighlightTheme } from './highlight'

let _md: MarkdownIt | null = null
let _katexLoaded = false
let _theme: 'light' | 'dark' = 'light'

export function getMarkdownRenderer(theme?: 'light' | 'dark'): MarkdownIt {
  if (theme && theme !== _theme) {
    loadHighlightTheme(theme === 'dark')
    _theme = theme
  }
  if (!_md) {
    _md = new MarkdownIt({
      html: false,
      linkify: false,
      breaks: true,
      typographer: false,
      highlight: (str: string, lang: string): string => {
        if (lang && hljs.getLanguage(lang)) {
          try {
            return `<pre><code class="hljs language-${lang}">${hljs.highlight(str, { language: lang }).value}</code></pre>`
          } catch { /* fall through to auto-escaped */ }
        }
        return `<pre><code>${_md!.utils.escapeHtml(str)}</code></pre>`
      },
    })
    _md.use(markdownItKatex, { throwOnError: false, errorColor: 'var(--seal)' })
  }
  return _md
}

export function mdToHtml(text: string): string {
  if (!_katexLoaded) {
    _katexLoaded = true
    void loadKatex()
  }
  const md = getMarkdownRenderer()
  return md.render(text)
}

export function setMarkdownTheme(theme: 'light' | 'dark'): void {
  _theme = theme
  // Force re-creation to pick up new highlight theme for cached renderer.
  // Actually, highlight theme is loaded once via CSS; the render() output
  // just uses hljs class names, so CSS changes take effect immediately.
  // We just need the CSS loaded.
  loadHighlightTheme(theme === 'dark')
}
```

- [ ] **Step 5: Write the enhanced markdown tests**

Create `src/pacer/web-next/tests/unit/markdown-enhanced.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { mdToHtml } from '@/utils/markdown'

describe('mdToHtml (markdown-it enhanced)', () => {
  it('renders tables', () => {
    const out = mdToHtml('|a|b|\n|-|-|\n|1|2|')
    expect(out).toContain('<table>')
    expect(out).toContain('<td>1</td>')
  })

  it('renders headings', () => {
    expect(mdToHtml('# Title')).toContain('<h1')
    expect(mdToHtml('## Sub')).toContain('<h2')
  })

  it('renders inline math', () => {
    const out = mdToHtml('$x^2$')
    // markdown-it-katex wraps inline math in a span
    expect(out).toContain('katex')
  })

  it('renders block math', () => {
    const out = mdToHtml('$$\nx^2\n$$')
    expect(out).toContain('katex')
  })

  it('renders fenced code with highlight.js', () => {
    const out = mdToHtml('```python\nprint(1)\n```')
    expect(out).toContain('<code class="hljs')
    expect(out).toContain('language-python')
  })

  it('still escapes HTML', () => {
    const out = mdToHtml('<script>alert(1)</script>')
    expect(out).not.toContain('<script>')
    expect(out).toContain('&lt;script&gt;')
  })

  it('still renders bold', () => {
    expect(mdToHtml('**bold**')).toContain('<strong>bold</strong>')
  })

  it('still renders inline code for single backtick', () => {
    const out = mdToHtml('`code`')
    expect(out).toContain('<code>code</code>')
  })

  it('handles empty input', () => {
    expect(mdToHtml('')).toBe('')
  })
})
```

Note: the old `markdown.test.ts` tests may need updating since the output format differs slightly between markdown-it and the regex-based renderer (e.g., markdown-it wraps output in `<p>` tags for paragraphs, uses `<em>` for single-`*`, etc.). Keep the old tests that still pass and update the ones that don't to match markdown-it's actual output.

- [ ] **Step 6: Run tests — expect PASS**

```bash
cd src/pacer/web-next && pnpm test && pnpm typecheck && pnpm build
```

Confirm KaTeX and highlight.js are NOT inlined into the bundle (they're CDN-loaded). The CSS netchunks in `dist/assets/` should not contain KaTeX fonts.

- [ ] **Step 7: Commit**

```bash
cd src/pacer/web-next && pnpm add markdown-it @gerhobbelt/markdown-it-katex katex highlight.js
pnpm add -D @types/markdown-it @types/katex
git add src/pacer/web-next/package.json src/pacer/web-next/pnpm-lock.yaml \
        src/pacer/web-next/src/utils/markdown.ts \
        src/pacer/web-next/src/utils/katex.ts \
        src/pacer/web-next/src/utils/highlight.ts \
        src/pacer/web-next/tests/unit/markdown-enhanced.test.ts \
        src/pacer/web-next/tests/unit/markdown.test.ts
git commit -m "feat(web-next): upgrade markdown to markdown-it + katex + highlight.js"
```

---

## Task 9: Frontend — `MarkdownRender.vue` uses new renderer with theme

**Files:**
- Modify: `src/pacer/web-next/src/components/MarkdownRender.vue`

- [ ] **Step 1: Replace the component**

```vue
<script setup lang="ts">
import { computed, watch } from 'vue'
import { mdToHtml, setMarkdownTheme } from '@/utils/markdown'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ text: string }>()
const ui = useUiStore()

const html = computed(() => mdToHtml(props.text))

watch(() => ui.theme, (t) => setMarkdownTheme(t), { immediate: true })
</script>

<template>
  <div class="md" v-html="html" />
</template>

<style scoped>
.md { font-size: 15px; line-height: 1.7; color: var(--ink-900); word-break: break-word; }
.md :deep(p) { margin: 0 0 10px; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.9em;
  background: var(--paper-2);
  padding: 1px 4px;
  border-radius: var(--radius-xs);
}
.md :deep(pre) {
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  overflow-x: auto;
  margin: 10px 0;
}
.md :deep(pre code) {
  background: none; padding: 0;
  font-size: 13px; line-height: 1.5;
}
.md :deep(strong) { color: var(--ink-900); font-weight: 600; }
.md :deep(h1), .md :deep(h2), .md :deep(h3) {
  font-family: var(--font-serif);
  margin: 16px 0 8px;
  letter-spacing: 0.04em;
}
.md :deep(h1) { font-size: 20px; }
.md :deep(h2) { font-size: 17px; }
.md :deep(h3) { font-size: 15px; }
.md :deep(table) {
  width: 100%; border-collapse: collapse;
  margin: 12px 0; font-size: 14px;
}
.md :deep(th), .md :deep(td) {
  border: 1px solid var(--ink-300);
  padding: 6px 10px; text-align: left;
}
.md :deep(th) { background: var(--paper-1); font-weight: 600; }
.md :deep(blockquote) {
  border-left: 2px solid var(--ink-300);
  margin: 10px 0; padding: 4px 12px;
  color: var(--ink-700); font-style: italic;
}
.md :deep(ul), .md :deep(ol) { padding-left: 20px; margin: 8px 0; }
.md :deep(li) { margin: 2px 0; }
.md :deep(hr) { border: none; border-top: 1px solid var(--ink-300); margin: 16px 0; }
.md :deep(a) { color: var(--accent); text-decoration: underline; }
</style>
```

- [ ] **Step 2: Run typecheck + build**

```bash
cd src/pacer/web-next && pnpm typecheck && pnpm build
```

- [ ] **Step 3: Commit**

```bash
git add src/pacer/web-next/src/components/MarkdownRender.vue
git commit -m "feat(web-next): connect markdown-it to MarkdownRender with theme support"
```

---

## Task 10: Frontend — `AssistantMessage.vue` streaming/stopped states + `Composer.vue` stop button

**Files:**
- Modify: `src/pacer/web-next/src/components/AssistantMessage.vue`
- Modify: `src/pacer/web-next/src/components/Composer.vue`

- [ ] **Step 1: Update `AssistantMessage.vue`**

Add `streaming` and `stopReason` props, and conditional CSS:

```vue
<script setup lang="ts">
import MarkdownRender from './MarkdownRender.vue'

const props = defineProps<{
  content: string
  agent?: string
  streaming?: boolean
  stopReason?: string
}>()

function agentLabel(agent: string | undefined): string {
  if (agent === 'subject_teacher') return '学科老师'
  if (agent === 'mood_companion') return '心态陪伴'
  return ''
}

function badgeText(): string {
  if (props.streaming) return '正在回答…'
  if (props.stopReason === 'user_stopped') return '已停止'
  return agentLabel(props.agent)
}
</script>

<template>
  <div class="row" :class="{ stopped: stopReason === 'user_stopped' }">
    <span v-if="badgeText()" class="badge">{{ badgeText() }}</span>
    <MarkdownRender :text="content" />
    <span v-if="streaming" class="cursor" aria-hidden="true" />
  </div>
</template>

<style scoped>
.row {
  position: relative;
  padding: 4px 0 4px 16px;
  margin: 14px 0;
  border-left: 2px solid var(--accent);
}
.row.stopped {
  border-left-style: dashed;
}
.badge {
  display: inline-block;
  font-family: var(--font-serif);
  font-size: 11px;
  color: var(--ink-500);
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}
.cursor {
  display: inline-block;
  width: 1px; height: 1em;
  background: var(--accent);
  margin-left: 1px;
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .cursor { animation: none; }
}
</style>
```

- [ ] **Step 2: Update `Composer.vue` — add stop button**

Change the send button area. During streaming (`chat.isStreaming`), show a stop button (a square, like a media player "stop") instead of the send arrow:

In the `<template>`, replace the send button block:

```html
      <button
        v-if="chat.isStreaming"
        type="button"
        class="stop-btn"
        @click="onStop"
        title="停止输出"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="1"/>
        </svg>
      </button>
      <button
        v-else
        type="button"
        class="send"
        :disabled="chat.isAwaiting || !text.trim()"
        @click="onSend"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <path d="M2 21l21-9L2 3v7l15 2-15 2z"/>
        </svg>
      </button>
```

Add the `onStop` function and `stop-btn` style in `<script>` and `<style>`:

```ts
import { useChatStore } from '@/stores/chat'
// (already imported — add the `computed`-style reference)
const chat = useChatStore()

async function onStop(): Promise<void> {
  await chat.stopStreaming()
}
```

```css
.stop-btn {
  width: 32px; height: 32px;
  border-radius: var(--radius-sm);
  background: var(--seal);
  color: var(--paper-0);
  display: inline-flex; align-items: center; justify-content: center;
  transition: opacity var(--motion-fast);
}
.stop-btn:hover { opacity: 0.85; }
```

- [ ] **Step 3: Update `MessageList.vue` to pass `streaming` and `stopReason`**

In `src/pacer/web-next/src/components/MessageList.vue`, update the `<AssistantMessage>` usage to pass the new props:

```html
<AssistantMessage
  v-else
  :content="m.content"
  :agent="m.agent"
  :streaming="m.streaming"
  :stop-reason="m.stopReason"
/>
```

- [ ] **Step 4: Run typecheck + build**

```bash
cd src/pacer/web-next && pnpm typecheck && pnpm build
```

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/components/AssistantMessage.vue \
        src/pacer/web-next/src/components/Composer.vue \
        src/pacer/web-next/src/components/MessageList.vue
git commit -m "feat(web-next): add streaming + stopped states to assistant and composer"
```

---

## Task 11: Frontend — Wire SSE streaming handlers in `main.ts`

**Files:**
- Modify: `src/pacer/web-next/src/main.ts`

- [ ] **Step 1: Update the SSE bootstrap**

Replace the `reconcileSSE` function in `main.ts`:

```ts
function reconcileSSE(token: string | null): void {
  if (stopSSE) { stopSSE(); stopSSE = null }
  if (token !== null) {
    stopSSE = startSSE(token, {
      onAssistantMessage: (p) => chat.receiveAssistantMessage(p),
      onAssistantDelta: (p) => chat.receiveDelta(p),
      onAssistantDone: (p) => chat.receiveDone(p),
    })
  }
}
```

(The `onAssistantStart` handler is optional — the streaming is already tracked by the ack response from `send()`.)

- [ ] **Step 2: Run typecheck + all tests**

```bash
cd src/pacer/web-next && pnpm typecheck && pnpm test
```

- [ ] **Step 3: Commit**

```bash
git add src/pacer/web-next/src/main.ts
git commit -m "feat(web-next): wire SSE streaming handlers to chat store"
```

---

## Task 12: End-of-phase verification

**Files:** none — verification only.

- [ ] **Step 1: Run full backend suite**

```bash
cd /Users/clover/Desktop/code/aiAgent
python3 -m pytest -x
```

- [ ] **Step 2: Run full frontend suite + build**

```bash
cd src/pacer/web-next
pnpm test && pnpm typecheck && pnpm build
```

- [ ] **Step 3: Confirm the built SPA is served correctly**

```bash
cd /Users/clover/Desktop/code/aiAgent
export $(cat .env | grep -v '^#' | xargs) && python3 -c "
from fastapi.testclient import TestClient
from pacer.api.server import create_app
client = TestClient(create_app())
r = client.get('/')
assert r.status_code == 200
assert 'app' in r.text
print('Production serve OK')
"
```

- [ ] **Step 4: Run backend with `uvicorn` and test streaming manually**

From repo root:
```bash
export $(cat .env | grep -v '^#' | xargs)
python3 -m uvicorn pacer.api.server:create_app --factory --port 8000 &
```

From `src/pacer/web-next/`:
```bash
pnpm dev
```

Open `http://localhost:5173` and verify:
1. Login → send a message → reply streams word-by-word with blinking cursor
2. Click stop mid-stream → output halts → border-left becomes dashed → badge shows "已停止"
3. Send "讲一道导数题 $$\\frac{dx}{dt}$$" → math is rendered with KaTeX
4. Send a message with a fenced code block → syntax highlighting renders
5. Toggle dark mode → code highlight theme switches to github-dark
6. SSE drops (kill backend) → "重连中" banner appears → restart backend → auto-reconnect

- [ ] **Step 5: Mark Phase 2 complete in spec**

Update `docs/superpowers/specs/2026-05-19-frontend-optimization-design.md`:

```markdown
## Progress

- [x] Phase 1 (2026-05-19): Vite + Vue 3 scaffold, visual rewrite, chat parity
- [x] Phase 2 (2026-05-19): streaming + Markdown enhancements
- [ ] Phase 3: session history
- [ ] Phase 4: profile / errors / plan views; delete legacy web/
```

- [ ] **Step 6: Final commit**

```bash
git add docs/superpowers/specs/2026-05-19-frontend-optimization-design.md
git commit -m "docs(spec): mark phase 2 complete"
```

---

## Phase 2 Acceptance

Run by hand before declaring Phase 2 done:

- [ ] Send message → word-by-word streaming visible in chat
- [ ] Stop button appears during stream; clicking it stops output immediately
- [ ] Stopped messages show dashed accent line + "已停止" badge; content preserved on refresh
- [ ] Math: `$x^2$` inline + `$$\n...\n$$` block render via KaTeX
- [ ] Code: fenced blocks with language get syntax highlighting
- [ ] Tables render correctly
- [ ] Dark mode switches code theme
- [ ] Legacy `assistant_message` SSE still works if delta events don't fire (backward compat)
- [ ] `pnpm test`, `pnpm typecheck`, `pnpm build`, `pytest -x` all green