# Stage 1 · Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation a single-agent ReAct loop with persistent memory, served via FastAPI + SSE, backed by SQLite. Validation point: a student can chat with a minimal AI through a Web endpoint, and the conversation persists across restarts.

**Architecture:** Greenfield Python package `pacer` using SQLAlchemy + FastAPI + Anthropic SDK. The data layer (memory, session, tools, ReAct loop) is *modeled after* Vibe-Trading's `memory/persistent.py`, `session/`, `agent/loop.py`, `agent/tools.py` — but rewritten with SQLAlchemy backends instead of Markdown/JSONL files.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite, Alembic, Anthropic SDK, pytest, pydantic-settings.

---

## Target File Structure (end of Stage 1)

```
pacer-ai/
├── pyproject.toml                    # NEW
├── alembic.ini                       # NEW
├── .env.example                      # NEW
├── src/pacer/
│   ├── __init__.py                   # NEW
│   ├── config.py                     # NEW — settings via pydantic-settings
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py                 # NEW — Anthropic wrapper (sync + stream)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                 # NEW — 10 SQLAlchemy models
│   │   ├── session.py                # NEW — engine + session factory
│   │   └── migrations/               # NEW — Alembic
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                   # NEW — BaseTool + ToolRegistry
│   │   ├── memory_tools.py           # NEW — search_memory, remember
│   │   └── profile_tools.py          # NEW — get_student_profile, update
│   ├── memory/
│   │   ├── __init__.py
│   │   └── persistent.py             # NEW — DB-backed memory
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py                   # NEW — minimal ReAct (single-agent)
│   │   └── context.py                # NEW — message builder
│   ├── session/
│   │   ├── __init__.py
│   │   ├── service.py                # NEW — session lifecycle
│   │   ├── store.py                  # NEW — sessions/messages CRUD
│   │   └── events.py                 # NEW — SSE event bus
│   └── api/
│       ├── __init__.py
│       ├── server.py                 # NEW — FastAPI app
│       ├── deps.py                   # NEW — DB session, current_student
│       └── routes/
│           ├── auth.py               # NEW — login with student_id + PIN
│           ├── message.py            # NEW — POST /message/send
│           └── events.py             # NEW — GET /events/stream (SSE)
└── tests/
    ├── unit/
    │   ├── test_config.py
    │   ├── test_db_models.py
    │   ├── test_tool_registry.py
    │   ├── test_memory.py
    │   ├── test_loop.py
    │   └── test_session_store.py
    ├── integration/
    │   ├── test_agent_with_tools.py
    │   └── test_message_endpoint.py
    └── e2e/
        └── test_chat_flow.py
```

---

## Task 1: Project Bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/pacer/__init__.py`
- Create: `src/pacer/config.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/unit/test_config.py`

- [ ] **Step 1: Create `pyproject.toml` with src layout**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pacer-ai"
version = "0.0.1"
description = "AI Study Companion — a pacer for the 高考 marathon"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "anthropic>=0.40",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.20",
    "sse-starlette>=2.1",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.7",
    "mypy>=1.13",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
# pacer-ai environment configuration
# Copy to .env and fill values

# Database
DATABASE_URL=sqlite:///./pacer.db

# LLM
ANTHROPIC_API_KEY=sk-ant-...
PACER_MAIN_MODEL=claude-sonnet-4-6
PACER_ROUTER_MODEL=claude-haiku-4-5-20251001

# Server
PACER_HOST=127.0.0.1
PACER_PORT=8000

# Auth (MVP: shared dev PIN; production should hash per-student)
PACER_PIN_LENGTH=6
```

- [ ] **Step 3: Write failing test for config**

Create `tests/unit/test_config.py`:

```python
import os
import pytest
from pacer.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("PACER_MAIN_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("PACER_ROUTER_MODEL", "claude-haiku-4-5-20251001")
    s = Settings()
    assert s.database_url == "sqlite:///./test.db"
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.main_model == "claude-sonnet-4-6"
    assert s.router_model == "claude-haiku-4-5-20251001"


def test_settings_defaults_for_server(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8000
```

- [ ] **Step 4: Run test and watch it fail**

Run: `pytest tests/unit/test_config.py -v`
Expected: ImportError or ModuleNotFoundError.

- [ ] **Step 5: Implement `src/pacer/config.py`**

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    main_model: str = Field("claude-sonnet-4-6", alias="PACER_MAIN_MODEL")
    router_model: str = Field("claude-haiku-4-5-20251001", alias="PACER_ROUTER_MODEL")
    host: str = Field("127.0.0.1", alias="PACER_HOST")
    port: int = Field(8000, alias="PACER_PORT")
    pin_length: int = Field(6, alias="PACER_PIN_LENGTH")


def get_settings() -> Settings:
    return Settings()
```

Create `src/pacer/__init__.py`:

```python
__version__ = "0.0.1"
```

- [ ] **Step 6: Run test and watch it pass**

Run: `pytest tests/unit/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 7: Install package in editable mode and commit**

```bash
pip install -e ".[dev]"
git add pyproject.toml .env.example src/pacer/__init__.py src/pacer/config.py tests/__init__.py tests/unit/__init__.py tests/unit/test_config.py
git commit -m "feat: project bootstrap with pydantic-settings config"
```

---

## Task 2: LLM Client Wrapper

**Files:**
- Create: `src/pacer/llm/__init__.py`
- Create: `src/pacer/llm/client.py`
- Create: `tests/unit/test_llm_client.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_llm_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pacer.llm.client import LLMClient, LLMMessage


@pytest.mark.asyncio
async def test_chat_returns_assistant_text():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="Hello, student!")]
    fake_response.stop_reason = "end_turn"
    fake_response.usage = MagicMock(input_tokens=10, output_tokens=5)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=fake_response)

    with patch("pacer.llm.client.AsyncAnthropic", return_value=mock_client):
        llm = LLMClient(api_key="sk-test", model="claude-sonnet-4-6")
        result = await llm.chat([LLMMessage(role="user", content="Hi")])

    assert result.text == "Hello, student!"
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 10
    assert result.output_tokens == 5


@pytest.mark.asyncio
async def test_chat_passes_system_prompt():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="ok")]
    fake_response.stop_reason = "end_turn"
    fake_response.usage = MagicMock(input_tokens=1, output_tokens=1)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=fake_response)

    with patch("pacer.llm.client.AsyncAnthropic", return_value=mock_client):
        llm = LLMClient(api_key="sk-test", model="claude-sonnet-4-6")
        await llm.chat(
            [LLMMessage(role="user", content="Hi")],
            system="You are a teacher.",
        )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are a teacher."
    assert call_kwargs["model"] == "claude-sonnet-4-6"
```

- [ ] **Step 2: Run test, watch it fail (module missing)**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/llm/client.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal
from anthropic import AsyncAnthropic


@dataclass
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]  # str for text, list for tool_use/tool_result blocks


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str
    input_tokens: int
    output_tokens: int
    raw: Any  # original SDK response, for advanced callers


class LLMClient:
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        resp = await self._client.messages.create(**kwargs)
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=resp.stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw=resp,
        )
```

Create `src/pacer/llm/__init__.py`:

```python
from pacer.llm.client import LLMClient, LLMMessage, LLMResponse

__all__ = ["LLMClient", "LLMMessage", "LLMResponse"]
```

- [ ] **Step 4: Run test, watch it pass**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/llm/ tests/unit/test_llm_client.py
git commit -m "feat: async LLM client wrapper around Anthropic SDK"
```

---

## Task 3: Database Schema + Migrations

**Files:**
- Create: `src/pacer/db/__init__.py`, `src/pacer/db/models.py`, `src/pacer/db/session.py`
- Create: `alembic.ini`, `src/pacer/db/migrations/env.py`, `src/pacer/db/migrations/script.py.mako`
- Create: `tests/unit/test_db_models.py`

- [ ] **Step 1: Write failing model tests**

```python
# tests/unit/test_db_models.py
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import (
    Base, Student, KnowledgePoint, Question, ErrorRecord,
    StudentMastery, Plan, ChatSession, Message, MemoryEntry, MoodLog,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_can_insert_student(db_session):
    s = Student(name="小明", grade=12, school="清华附中", pin_hash="hash123")
    db_session.add(s)
    db_session.commit()
    assert s.id is not None
    assert s.created_at is not None


def test_can_create_knowledge_point_with_prereqs(db_session):
    parent = KnowledgePoint(subject="math", chapter="函数与导数", point_name="导数定义", difficulty=3)
    db_session.add(parent)
    db_session.flush()
    child = KnowledgePoint(
        subject="math", chapter="函数与导数", point_name="切线方程",
        difficulty=4, prereq_ids=[parent.id]
    )
    db_session.add(child)
    db_session.commit()
    assert child.prereq_ids == [parent.id]


def test_can_link_error_record_to_student_and_question(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    q = Question(subject="math", stem="求 f(x)=x^2 在 x=1 的切线方程", answer="y=2x-1", knowledge_point_ids=[])
    db_session.add_all([s, q])
    db_session.flush()
    e = ErrorRecord(
        student_id=s.id, question_id=q.id,
        user_answer="y=2x", error_type="concept",
        knowledge_point_ids=[], mastery_level=0.3, source="photo",
    )
    db_session.add(e)
    db_session.commit()
    assert e.id is not None
    assert e.student.id == s.id
    assert e.question.id == q.id


def test_message_belongs_to_session(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    db_session.add(s)
    db_session.flush()
    chat = ChatSession(student_id=s.id, status="active")
    db_session.add(chat)
    db_session.flush()
    m = Message(session_id=chat.id, role="user", agent=None, content="Hello", metadata_json={})
    db_session.add(m)
    db_session.commit()
    assert m.session.id == chat.id


def test_memory_entry_stores_typed_payload(db_session):
    s = Student(name="小明", grade=12, pin_hash="h")
    db_session.add(s)
    db_session.flush()
    me = MemoryEntry(
        student_id=s.id, type="weakness", key="导数:切线方程",
        content="多次在切线方程问题上选错斜率", importance=0.8,
    )
    db_session.add(me)
    db_session.commit()
    assert me.id is not None
```

- [ ] **Step 2: Run test, watch fail**

Run: `pytest tests/unit/test_db_models.py -v`
Expected: ModuleNotFoundError on `pacer.db.models`.

- [ ] **Step 3: Implement `src/pacer/db/models.py`**

```python
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    grade: Mapped[int] = mapped_column(Integer)  # 12 = 高三
    school: Mapped[Optional[str]] = mapped_column(String(100))
    target_school: Mapped[Optional[str]] = mapped_column(String(100))
    stream: Mapped[Optional[str]] = mapped_column(String(10))  # 文/理
    pin_hash: Mapped[str] = mapped_column(String(128))
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(20))
    chapter: Mapped[str] = mapped_column(String(100))
    point_name: Mapped[str] = mapped_column(String(100))
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    prereq_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    exam_freq: Mapped[Optional[int]] = mapped_column(Integer)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(20))
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[Optional[dict]] = mapped_column(JSON)
    answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    knowledge_point_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    difficulty: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[Optional[str]] = mapped_column(String(100))
    year: Mapped[Optional[int]] = mapped_column(Integer)
    image_url: Mapped[Optional[str]] = mapped_column(String(500))


class ErrorRecord(Base):
    __tablename__ = "error_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    question_id: Mapped[Optional[int]] = mapped_column(ForeignKey("questions.id"))
    user_answer: Mapped[Optional[str]] = mapped_column(Text)
    correct_answer: Mapped[Optional[str]] = mapped_column(Text)
    error_type: Mapped[Optional[str]] = mapped_column(String(50))  # carelessness/concept/method
    knowledge_point_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    mastery_level: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(20))  # photo/text/qa
    explanation_text: Mapped[Optional[str]] = mapped_column(Text)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student = relationship("Student")
    question = relationship("Question")


class StudentMastery(Base):
    __tablename__ = "student_mastery"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    knowledge_point_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"))
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_practice_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    date: Mapped[datetime] = mapped_column(DateTime)
    type: Mapped[str] = mapped_column(String(20))  # daily/weekly
    tasks_json: Mapped[list] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(50), default="homeroom")
    feedback: Mapped[Optional[str]] = mapped_column(Text)


class ChatSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(20))  # user/assistant/system/tool
    agent: Mapped[Optional[str]] = mapped_column(String(30))  # homeroom/subject/mood/null
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session = relationship("ChatSession")


class MemoryEntry(Base):
    __tablename__ = "memory_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    type: Mapped[str] = mapped_column(String(30))  # profile/weakness/habit/goal/event
    key: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MoodLog(Base):
    __tablename__ = "mood_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sessions.id"))
    self_score: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    red_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

Create `src/pacer/db/__init__.py`:

```python
from pacer.db.models import (
    Base, Student, KnowledgePoint, Question, ErrorRecord,
    StudentMastery, Plan, ChatSession, Message, MemoryEntry, MoodLog,
)

__all__ = [
    "Base", "Student", "KnowledgePoint", "Question", "ErrorRecord",
    "StudentMastery", "Plan", "ChatSession", "Message", "MemoryEntry", "MoodLog",
]
```

- [ ] **Step 4: Run test, watch pass**

Run: `pytest tests/unit/test_db_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Implement DB session factory**

Create `src/pacer/db/session.py`:

```python
from contextlib import contextmanager
from collections.abc import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pacer.config import get_settings

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(database_url: str | None = None):
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    _engine = create_engine(url, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 6: Initialize Alembic**

Run:
```bash
alembic init -t async src/pacer/db/migrations
```

Wait — we're using sync SQLAlchemy. Use the sync template:
```bash
alembic init src/pacer/db/migrations
mv alembic.ini ./alembic.ini  # ensure at project root
```

Edit `alembic.ini` — set `sqlalchemy.url` to read from env (we'll override in env.py):

```ini
sqlalchemy.url =
```

Edit `src/pacer/db/migrations/env.py` — replace its body with:

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from pacer.config import get_settings
from pacer.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 7: Generate initial migration**

```bash
cp .env.example .env
alembic revision --autogenerate -m "initial schema (10 tables)"
```

Inspect the generated migration in `src/pacer/db/migrations/versions/` — it should `op.create_table(...)` for all 10 tables. If anything is missing, fix manually.

- [ ] **Step 8: Apply migration and verify**

```bash
alembic upgrade head
sqlite3 pacer.db ".tables"
```

Expected output: All 10 tables present.

- [ ] **Step 9: Commit**

```bash
git add src/pacer/db/ alembic.ini tests/unit/test_db_models.py
git commit -m "feat: SQLAlchemy schema (10 tables) + Alembic migration"
```

---

## Task 4: BaseTool + ToolRegistry

**Files:**
- Create: `src/pacer/tools/__init__.py`, `src/pacer/tools/base.py`
- Create: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tool_registry.py
import pytest
from pacer.tools.base import BaseTool, ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo back the input"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }
    is_readonly = True

    async def execute(self, *, text: str) -> dict:
        return {"echo": text}


class FailingTool(BaseTool):
    name = "fail"
    description = "Always fails"
    parameters = {"type": "object", "properties": {}}
    is_readonly = True

    async def execute(self, **kwargs):
        raise ValueError("intentional")


@pytest.mark.asyncio
async def test_registry_executes_tool():
    reg = ToolRegistry()
    reg.register(EchoTool())
    result = await reg.execute("echo", {"text": "hi"})
    assert result == {"status": "ok", "result": {"echo": "hi"}}


@pytest.mark.asyncio
async def test_registry_wraps_errors():
    reg = ToolRegistry()
    reg.register(FailingTool())
    result = await reg.execute("fail", {})
    assert result["status"] == "error"
    assert "intentional" in result["error"]


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    reg = ToolRegistry()
    result = await reg.execute("ghost", {})
    assert result["status"] == "error"
    assert "unknown" in result["error"].lower()


def test_to_anthropic_schemas():
    reg = ToolRegistry()
    reg.register(EchoTool())
    schemas = reg.to_anthropic_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "echo"
    assert schemas[0]["description"] == "Echo back the input"
    assert schemas[0]["input_schema"]["required"] == ["text"]
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/unit/test_tool_registry.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/tools/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    is_readonly: bool = True
    repeatable: bool = True

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        ...

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def to_anthropic_schemas(self) -> list[dict[str, Any]]:
        return [t.to_anthropic_schema() for t in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"status": "error", "error": f"unknown tool: {name}"}
        try:
            result = await tool.execute(**params)
            return {"status": "ok", "result": result}
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
```

Create `src/pacer/tools/__init__.py`:

```python
from pacer.tools.base import BaseTool, ToolRegistry

__all__ = ["BaseTool", "ToolRegistry"]
```

- [ ] **Step 4: Run, watch pass**

Run: `pytest tests/unit/test_tool_registry.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/tools/ tests/unit/test_tool_registry.py
git commit -m "feat: BaseTool + ToolRegistry with Anthropic schema export"
```

---

## Task 5: Persistent Memory (DB-backed)

**Files:**
- Create: `src/pacer/memory/__init__.py`, `src/pacer/memory/persistent.py`
- Create: `tests/unit/test_memory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_memory.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.memory.persistent import PersistentMemory


@pytest.fixture
def session_with_student():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = Session(engine)
    student = Student(name="小明", grade=12, pin_hash="h")
    s.add(student)
    s.commit()
    yield s, student.id
    s.close()


def test_add_and_retrieve_memory(session_with_student):
    s, student_id = session_with_student
    mem = PersistentMemory(s, student_id)
    entry = mem.add(type="weakness", key="导数:切线方程", content="多次错")
    assert entry.id is not None
    fetched = mem.find_relevant("切线", max_results=5)
    assert len(fetched) == 1
    assert fetched[0].key == "导数:切线方程"


def test_find_relevant_ranks_by_keyword_overlap(session_with_student):
    s, student_id = session_with_student
    mem = PersistentMemory(s, student_id)
    mem.add(type="goal", key="目标院校", content="清华大学计算机系")
    mem.add(type="habit", key="作息", content="晚 22:30 入睡早 06:30 起")
    mem.add(type="weakness", key="导数:切线方程", content="切线方程斜率多次出错")
    results = mem.find_relevant("切线方程", max_results=2)
    assert results[0].content.startswith("切线方程")


def test_isolated_per_student(session_with_student):
    s, student_id = session_with_student
    other = Student(name="小红", grade=12, pin_hash="h")
    s.add(other); s.commit()
    mem_a = PersistentMemory(s, student_id)
    mem_b = PersistentMemory(s, other.id)
    mem_a.add(type="goal", key="g", content="A's goal")
    mem_b.add(type="goal", key="g", content="B's goal")
    a_results = mem_a.find_relevant("goal", max_results=10)
    b_results = mem_b.find_relevant("goal", max_results=10)
    assert len(a_results) == 1 and a_results[0].content == "A's goal"
    assert len(b_results) == 1 and b_results[0].content == "B's goal"
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/unit/test_memory.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/memory/persistent.py`**

```python
from __future__ import annotations
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pacer.db.models import MemoryEntry


_CJK_RE = re.compile(r"[一-鿿]")
_ASCII_RE = re.compile(r"[A-Za-z]{3,}")


def _tokenize(text: str) -> list[str]:
    tokens = _ASCII_RE.findall(text.lower())
    tokens += _CJK_RE.findall(text)  # one CJK char = one token
    return tokens


class PersistentMemory:
    """DB-backed long-term memory scoped to a single student."""

    def __init__(self, session: Session, student_id: int):
        self._session = session
        self._student_id = student_id

    def add(self, *, type: str, key: str, content: str, importance: float = 0.5) -> MemoryEntry:
        entry = MemoryEntry(
            student_id=self._student_id,
            type=type, key=key, content=content, importance=importance,
        )
        self._session.add(entry)
        self._session.commit()
        self._session.refresh(entry)
        return entry

    def find_relevant(self, query: str, *, max_results: int = 3) -> list[MemoryEntry]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        # Naive LIKE-based search; rank by token overlap count.
        conds = [MemoryEntry.content.ilike(f"%{t}%") for t in tokens] + \
                [MemoryEntry.key.ilike(f"%{t}%") for t in tokens]
        rows = (
            self._session.query(MemoryEntry)
            .filter(MemoryEntry.student_id == self._student_id, or_(*conds))
            .all()
        )

        def score(entry: MemoryEntry) -> float:
            blob = (entry.content + " " + entry.key).lower()
            tok_hits = sum(1 for t in tokens if t.lower() in blob)
            return tok_hits + entry.importance

        rows.sort(key=score, reverse=True)
        return rows[:max_results]
```

Create `src/pacer/memory/__init__.py`:

```python
from pacer.memory.persistent import PersistentMemory

__all__ = ["PersistentMemory"]
```

- [ ] **Step 4: Run, watch pass**

Run: `pytest tests/unit/test_memory.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/memory/ tests/unit/test_memory.py
git commit -m "feat: DB-backed persistent memory with student isolation"
```

---

## Task 6: Memory & Profile Tools

**Files:**
- Create: `src/pacer/tools/memory_tools.py`, `src/pacer/tools/profile_tools.py`
- Create: `tests/unit/test_memory_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_memory_tools.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.tools.memory_tools import SearchMemoryTool, RememberTool
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool


@pytest.fixture
def db_and_student():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    s = Student(name="小明", grade=12, pin_hash="h", profile_json={"target_score": 600})
    sess.add(s); sess.commit()
    yield sess, s.id
    sess.close()


@pytest.mark.asyncio
async def test_remember_and_search_round_trip(db_and_student):
    sess, sid = db_and_student
    remember = RememberTool(session_factory=lambda: sess, student_id=sid)
    search = SearchMemoryTool(session_factory=lambda: sess, student_id=sid)
    await remember.execute(type="goal", key="target", content="清华计算机", importance=0.9)
    res = await search.execute(query="清华")
    assert len(res["entries"]) == 1
    assert res["entries"][0]["content"] == "清华计算机"


@pytest.mark.asyncio
async def test_get_and_update_profile(db_and_student):
    sess, sid = db_and_student
    getter = GetStudentProfileTool(session_factory=lambda: sess, student_id=sid)
    updater = UpdateStudentProfileTool(session_factory=lambda: sess, student_id=sid)
    profile = await getter.execute()
    assert profile["name"] == "小明"
    assert profile["profile_json"]["target_score"] == 600
    await updater.execute(updates={"target_school": "清华大学", "profile_json.bedtime": "22:30"})
    refreshed = await getter.execute()
    assert refreshed["target_school"] == "清华大学"
    assert refreshed["profile_json"]["bedtime"] == "22:30"
    assert refreshed["profile_json"]["target_score"] == 600  # preserved
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/unit/test_memory_tools.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/tools/memory_tools.py`**

```python
from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.tools.base import BaseTool
from pacer.memory.persistent import PersistentMemory


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "Search the student's long-term memory for entries matching a query."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "keywords to match"},
            "max_results": {"type": "integer", "default": 3},
        },
        "required": ["query"],
    }
    is_readonly = True

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, query: str, max_results: int = 3) -> dict:
        sess = self._session_factory()
        mem = PersistentMemory(sess, self._student_id)
        entries = mem.find_relevant(query, max_results=max_results)
        return {"entries": [
            {"type": e.type, "key": e.key, "content": e.content, "importance": e.importance}
            for e in entries
        ]}


class RememberTool(BaseTool):
    name = "remember"
    description = "Persist a fact about the student to long-term memory."
    parameters = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["profile", "weakness", "habit", "goal", "event"]},
            "key": {"type": "string"},
            "content": {"type": "string"},
            "importance": {"type": "number", "default": 0.5},
        },
        "required": ["type", "key", "content"],
    }
    is_readonly = False

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, type: str, key: str, content: str, importance: float = 0.5) -> dict:
        sess = self._session_factory()
        mem = PersistentMemory(sess, self._student_id)
        entry = mem.add(type=type, key=key, content=content, importance=importance)
        return {"saved_id": entry.id}
```

- [ ] **Step 4: Implement `src/pacer/tools/profile_tools.py`**

```python
from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.tools.base import BaseTool
from pacer.db.models import Student


def _set_dotted(d: dict, dotted_key: str, value):
    parts = dotted_key.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = value


class GetStudentProfileTool(BaseTool):
    name = "get_student_profile"
    description = "Fetch the student's profile (name, grade, school, target_school, stream, profile_json)."
    parameters = {"type": "object", "properties": {}}
    is_readonly = True

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self) -> dict:
        sess = self._session_factory()
        s = sess.get(Student, self._student_id)
        if s is None:
            return {}
        return {
            "id": s.id, "name": s.name, "grade": s.grade,
            "school": s.school, "target_school": s.target_school,
            "stream": s.stream, "profile_json": dict(s.profile_json or {}),
        }


class UpdateStudentProfileTool(BaseTool):
    name = "update_student_profile"
    description = (
        "Update student profile fields. Keys without dots write to top-level fields; "
        "keys with dots write into profile_json (e.g. 'profile_json.bedtime')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "updates": {
                "type": "object",
                "description": "field-name -> value mapping",
            },
        },
        "required": ["updates"],
    }
    is_readonly = False

    _TOP_LEVEL = {"name", "grade", "school", "target_school", "stream"}

    def __init__(self, session_factory: Callable[[], Session], student_id: int):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, updates: dict) -> dict:
        sess = self._session_factory()
        s = sess.get(Student, self._student_id)
        if s is None:
            return {"status": "not_found"}
        pj = dict(s.profile_json or {})
        for k, v in updates.items():
            if k in self._TOP_LEVEL:
                setattr(s, k, v)
            elif k.startswith("profile_json."):
                _set_dotted(pj, k[len("profile_json."):], v)
            else:
                _set_dotted(pj, k, v)
        s.profile_json = pj
        sess.commit()
        return {"updated_fields": list(updates.keys())}
```

- [ ] **Step 5: Run, watch pass**

Run: `pytest tests/unit/test_memory_tools.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pacer/tools/memory_tools.py src/pacer/tools/profile_tools.py tests/unit/test_memory_tools.py
git commit -m "feat: memory and student profile tools"
```

---

## Task 7: Minimal ReAct Loop

**Files:**
- Create: `src/pacer/agent/__init__.py`, `src/pacer/agent/loop.py`, `src/pacer/agent/context.py`
- Create: `tests/unit/test_loop.py`, `tests/integration/test_agent_with_tools.py`

- [ ] **Step 1: Write failing test for AgentLoop (unit, with mocked LLM)**

```python
# tests/unit/test_loop.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pacer.agent.loop import AgentLoop, AgentResult
from pacer.tools.base import ToolRegistry, BaseTool


class _StubTool(BaseTool):
    name = "stub"
    description = "stub"
    parameters = {"type": "object", "properties": {}}
    is_readonly = True

    async def execute(self, **kwargs):
        return {"ok": True}


def _llm_response(text="", tool_calls=None, stop_reason="end_turn"):
    from pacer.llm.client import LLMResponse
    return LLMResponse(
        text=text, tool_calls=tool_calls or [],
        stop_reason=stop_reason, input_tokens=10, output_tokens=5, raw=None,
    )


@pytest.mark.asyncio
async def test_loop_returns_text_when_no_tool_calls():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=_llm_response(text="Hello!"))
    reg = ToolRegistry()
    loop = AgentLoop(llm=llm, tools=reg, system_prompt="You are a teacher.")
    result = await loop.run("Hi", history=[])
    assert isinstance(result, AgentResult)
    assert result.final_text == "Hello!"
    assert result.iterations == 1


@pytest.mark.asyncio
async def test_loop_executes_tool_then_returns():
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=[
        _llm_response(tool_calls=[{"id": "t1", "name": "stub", "input": {}}], stop_reason="tool_use"),
        _llm_response(text="done", stop_reason="end_turn"),
    ])
    reg = ToolRegistry(); reg.register(_StubTool())
    loop = AgentLoop(llm=llm, tools=reg, system_prompt="sys")
    result = await loop.run("call stub", history=[])
    assert result.final_text == "done"
    assert result.iterations == 2
    assert any(step["tool"] == "stub" for step in result.trace)


@pytest.mark.asyncio
async def test_loop_terminates_at_max_iterations():
    llm = MagicMock()
    # Always returns a tool call → would loop forever
    llm.chat = AsyncMock(return_value=_llm_response(
        tool_calls=[{"id": "t", "name": "stub", "input": {}}], stop_reason="tool_use",
    ))
    reg = ToolRegistry(); reg.register(_StubTool())
    loop = AgentLoop(llm=llm, tools=reg, system_prompt="sys", max_iterations=3)
    result = await loop.run("loop", history=[])
    assert result.iterations == 3
    assert result.stopped_reason == "max_iterations"
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/unit/test_loop.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/pacer/agent/context.py`**

```python
from __future__ import annotations
from pacer.llm.client import LLMMessage


def build_messages(
    user_message: str,
    history: list[LLMMessage],
    recalled_memory_block: str | None = None,
) -> list[LLMMessage]:
    msgs = list(history)
    user_text = user_message
    if recalled_memory_block:
        user_text = f"<recalled-memories>\n{recalled_memory_block}\n</recalled-memories>\n\n{user_message}"
    msgs.append(LLMMessage(role="user", content=user_text))
    return msgs
```

- [ ] **Step 4: Implement `src/pacer/agent/loop.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from pacer.llm.client import LLMClient, LLMMessage
from pacer.tools.base import ToolRegistry
from pacer.agent.context import build_messages


@dataclass
class AgentResult:
    final_text: str
    iterations: int
    trace: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str = "end_turn"
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        system_prompt: str,
        max_iterations: int = 8,
    ):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

    async def run(
        self,
        user_message: str,
        history: list[LLMMessage],
        recalled_memory_block: str | None = None,
    ) -> AgentResult:
        messages = build_messages(user_message, history, recalled_memory_block)
        trace: list[dict[str, Any]] = []
        total_in = total_out = 0
        for i in range(1, self.max_iterations + 1):
            resp = await self.llm.chat(
                messages,
                system=self.system_prompt,
                tools=self.tools.to_anthropic_schemas() or None,
            )
            total_in += resp.input_tokens
            total_out += resp.output_tokens
            if not resp.tool_calls:
                return AgentResult(
                    final_text=resp.text, iterations=i, trace=trace,
                    stopped_reason=resp.stop_reason,
                    total_input_tokens=total_in, total_output_tokens=total_out,
                )
            # Reflect tool_use blocks back to the model + execute + append tool_result
            assistant_content: list[dict[str, Any]] = []
            if resp.text:
                assistant_content.append({"type": "text", "text": resp.text})
            for tc in resp.tool_calls:
                assistant_content.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]})
            messages.append(LLMMessage(role="assistant", content=assistant_content))

            tool_results: list[dict[str, Any]] = []
            for tc in resp.tool_calls:
                exec_result = await self.tools.execute(tc["name"], tc["input"])
                trace.append({"tool": tc["name"], "input": tc["input"], "result": exec_result})
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tc["id"],
                    "content": str(exec_result),
                })
            messages.append(LLMMessage(role="user", content=tool_results))

        return AgentResult(
            final_text="", iterations=self.max_iterations, trace=trace,
            stopped_reason="max_iterations",
            total_input_tokens=total_in, total_output_tokens=total_out,
        )
```

Create `src/pacer/agent/__init__.py`:

```python
from pacer.agent.loop import AgentLoop, AgentResult

__all__ = ["AgentLoop", "AgentResult"]
```

- [ ] **Step 5: Run, watch pass**

Run: `pytest tests/unit/test_loop.py -v`
Expected: 3 passed.

- [ ] **Step 6: Write integration test exercising real registry**

```python
# tests/integration/__init__.py  -- empty file
# tests/integration/test_agent_with_tools.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import RememberTool, SearchMemoryTool
from pacer.agent.loop import AgentLoop
from pacer.llm.client import LLMResponse


@pytest.mark.asyncio
async def test_agent_remembers_via_tool():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    s = Student(name="X", grade=12, pin_hash="h")
    sess.add(s); sess.commit()

    reg = ToolRegistry()
    reg.register(RememberTool(lambda: sess, s.id))
    reg.register(SearchMemoryTool(lambda: sess, s.id))

    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=[
        LLMResponse(
            text="", tool_calls=[{
                "id": "t1", "name": "remember",
                "input": {"type": "goal", "key": "target", "content": "清华"},
            }],
            stop_reason="tool_use", input_tokens=10, output_tokens=5, raw=None,
        ),
        LLMResponse(
            text="Saved!", tool_calls=[], stop_reason="end_turn",
            input_tokens=8, output_tokens=4, raw=None,
        ),
    ])

    loop = AgentLoop(llm=llm, tools=reg, system_prompt="sys")
    result = await loop.run("Remember I want Tsinghua", history=[])
    assert result.final_text == "Saved!"
    # Verify side-effect actually happened
    from pacer.db.models import MemoryEntry
    entries = sess.query(MemoryEntry).filter_by(student_id=s.id).all()
    assert len(entries) == 1
    assert entries[0].content == "清华"
```

- [ ] **Step 7: Run integration test**

Run: `pytest tests/integration/test_agent_with_tools.py -v`
Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add src/pacer/agent/ tests/unit/test_loop.py tests/integration/__init__.py tests/integration/test_agent_with_tools.py
git commit -m "feat: minimal ReAct loop with tool calling"
```

---

## Task 8: Session + Message Persistence

**Files:**
- Create: `src/pacer/session/__init__.py`, `src/pacer/session/store.py`
- Create: `tests/unit/test_session_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_session_store.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.session.store import SessionStore


@pytest.fixture
def store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    s = Student(name="X", grade=12, pin_hash="h")
    sess.add(s); sess.commit()
    yield SessionStore(sess), s.id
    sess.close()


def test_create_session_and_append_messages(store):
    s, sid = store
    chat = s.create_session(student_id=sid)
    s.append_message(chat.id, role="user", agent=None, content="Hi")
    s.append_message(chat.id, role="assistant", agent="homeroom", content="Hello!")
    msgs = s.list_messages(chat.id)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].agent == "homeroom"


def test_history_for_llm_returns_oai_format(store):
    s, sid = store
    chat = s.create_session(student_id=sid)
    s.append_message(chat.id, role="user", agent=None, content="A")
    s.append_message(chat.id, role="assistant", agent="homeroom", content="B")
    history = s.history_for_llm(chat.id)
    assert history == [
        {"role": "user", "content": "A"},
        {"role": "assistant", "content": "B"},
    ]
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/unit/test_session_store.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/session/store.py`**

```python
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from pacer.db.models import ChatSession, Message


class SessionStore:
    def __init__(self, session: Session):
        self._session = session

    def create_session(self, *, student_id: int) -> ChatSession:
        chat = ChatSession(student_id=student_id, status="active", last_active_at=datetime.utcnow())
        self._session.add(chat); self._session.commit(); self._session.refresh(chat)
        return chat

    def get_session(self, session_id: int) -> ChatSession | None:
        return self._session.get(ChatSession, session_id)

    def append_message(
        self, session_id: int, *, role: str, agent: str | None,
        content: str, metadata: dict | None = None,
    ) -> Message:
        m = Message(
            session_id=session_id, role=role, agent=agent,
            content=content, metadata_json=metadata or {},
        )
        self._session.add(m)
        chat = self.get_session(session_id)
        if chat is not None:
            chat.last_active_at = datetime.utcnow()
        self._session.commit(); self._session.refresh(m)
        return m

    def list_messages(self, session_id: int) -> list[Message]:
        return (
            self._session.query(Message)
            .filter_by(session_id=session_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )

    def history_for_llm(self, session_id: int) -> list[dict]:
        return [
            {"role": m.role, "content": m.content}
            for m in self.list_messages(session_id)
            if m.role in ("user", "assistant")
        ]
```

Create `src/pacer/session/__init__.py`:

```python
from pacer.session.store import SessionStore

__all__ = ["SessionStore"]
```

- [ ] **Step 4: Run, watch pass**

Run: `pytest tests/unit/test_session_store.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/session/ tests/unit/test_session_store.py
git commit -m "feat: SessionStore for chat persistence"
```

---

## Task 9: SSE Event Bus

**Files:**
- Create: `src/pacer/session/events.py`
- Create: `tests/unit/test_events.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_events.py
import asyncio
import pytest
from pacer.session.events import EventBus, SSEEvent


@pytest.mark.asyncio
async def test_subscribe_receives_published_event():
    bus = EventBus()
    sub = bus.subscribe(student_id=1)
    await bus.publish(SSEEvent(student_id=1, event_type="message", data={"text": "hi"}))
    evt = await asyncio.wait_for(sub.get(), timeout=1.0)
    assert evt.event_type == "message"
    assert evt.data == {"text": "hi"}


@pytest.mark.asyncio
async def test_subscribers_are_isolated_by_student():
    bus = EventBus()
    sub_a = bus.subscribe(student_id=1)
    sub_b = bus.subscribe(student_id=2)
    await bus.publish(SSEEvent(student_id=1, event_type="msg", data={}))
    await bus.publish(SSEEvent(student_id=2, event_type="other", data={}))
    a_evt = await asyncio.wait_for(sub_a.get(), timeout=1.0)
    b_evt = await asyncio.wait_for(sub_b.get(), timeout=1.0)
    assert a_evt.event_type == "msg"
    assert b_evt.event_type == "other"


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    sub = bus.subscribe(student_id=1)
    bus.unsubscribe(student_id=1, queue=sub)
    await bus.publish(SSEEvent(student_id=1, event_type="x", data={}))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub.get(), timeout=0.1)
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/unit/test_events.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/session/events.py`**

```python
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any
import time


@dataclass
class SSEEvent:
    student_id: int
    event_type: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class EventBus:
    def __init__(self, queue_maxsize: int = 100):
        self._subscribers: dict[int, list[asyncio.Queue[SSEEvent]]] = defaultdict(list)
        self._queue_maxsize = queue_maxsize

    def subscribe(self, student_id: int) -> asyncio.Queue[SSEEvent]:
        q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._subscribers[student_id].append(q)
        return q

    def unsubscribe(self, student_id: int, queue: asyncio.Queue[SSEEvent]) -> None:
        if queue in self._subscribers.get(student_id, []):
            self._subscribers[student_id].remove(queue)

    async def publish(self, event: SSEEvent) -> None:
        for q in list(self._subscribers.get(event.student_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest, append new (best-effort)
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                q.put_nowait(event)
```

- [ ] **Step 4: Run, watch pass**

Run: `pytest tests/unit/test_events.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/session/events.py tests/unit/test_events.py
git commit -m "feat: in-process SSE event bus"
```

---

## Task 10: FastAPI App + Auth

**Files:**
- Create: `src/pacer/api/__init__.py`, `src/pacer/api/server.py`, `src/pacer/api/deps.py`
- Create: `src/pacer/api/routes/__init__.py`, `src/pacer/api/routes/auth.py`
- Create: `tests/unit/test_auth_route.py`

- [ ] **Step 1: Write failing test (uses fastapi TestClient)**

```python
# tests/unit/test_auth_route.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.db.models import Base, Student
from pacer.api.server import create_app
from pacer.api.deps import hash_pin


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sess = SessionLocal()
    sess.add(Student(id=1, name="Alice", grade=12, pin_hash=hash_pin("123456")))
    sess.commit(); sess.close()

    app = create_app(database_url=url)
    return TestClient(app)


def test_login_returns_session_token(client):
    resp = client.post("/auth/login", json={"student_id": 1, "pin": "123456"})
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body and len(body["token"]) > 20


def test_login_wrong_pin_rejected(client):
    resp = client.post("/auth/login", json={"student_id": 1, "pin": "999999"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/unit/test_auth_route.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/api/deps.py`**

```python
from __future__ import annotations
import hashlib
import secrets
from collections.abc import Iterator
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from pacer.config import get_settings


_engine = None
_SessionLocal: sessionmaker[Session] | None = None
_tokens: dict[str, int] = {}  # token -> student_id (in-memory MVP)


def init_db(database_url: str | None = None) -> None:
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    _engine = create_engine(url, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    assert _SessionLocal is not None, "init_db() must be called before requests"
    sess = _SessionLocal()
    try:
        yield sess
    finally:
        sess.close()


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def issue_token(student_id: int) -> str:
    tok = secrets.token_urlsafe(32)
    _tokens[tok] = student_id
    return tok


def current_student_id(authorization: str | None = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    tok = authorization[len("Bearer "):]
    sid = _tokens.get(tok)
    if sid is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return sid
```

- [ ] **Step 4: Implement `src/pacer/api/routes/auth.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, hash_pin, issue_token
from pacer.db.models import Student

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    student_id: int
    pin: str


class LoginResponse(BaseModel):
    token: str
    student_id: int


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    s = db.get(Student, req.student_id)
    if s is None or s.pin_hash != hash_pin(req.pin):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = issue_token(s.id)
    return LoginResponse(token=token, student_id=s.id)
```

- [ ] **Step 5: Implement `src/pacer/api/server.py`**

```python
from __future__ import annotations
from fastapi import FastAPI
from pacer.api import deps
from pacer.api.routes.auth import router as auth_router


def create_app(database_url: str | None = None) -> FastAPI:
    deps.init_db(database_url)
    app = FastAPI(title="pacer-ai")
    app.include_router(auth_router)
    return app
```

Create `src/pacer/api/__init__.py` (empty) and `src/pacer/api/routes/__init__.py` (empty).

- [ ] **Step 6: Run, watch pass**

Run: `pytest tests/unit/test_auth_route.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/pacer/api/ tests/unit/test_auth_route.py
git commit -m "feat: FastAPI app skeleton with /auth/login (student_id + PIN)"
```

---

## Task 11: Message + Events Endpoints

**Files:**
- Create: `src/pacer/api/routes/message.py`, `src/pacer/api/routes/events.py`
- Modify: `src/pacer/api/server.py` (register new routers, instantiate EventBus + LLMClient as app state)
- Create: `tests/integration/test_message_endpoint.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/test_message_endpoint.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.db.models import Base, Student
from pacer.api.server import create_app
from pacer.api.deps import hash_pin
from pacer.llm.client import LLMResponse


@pytest.fixture
def client_and_token(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sess = SessionLocal()
    sess.add(Student(id=1, name="Alice", grade=12, pin_hash=hash_pin("123456")))
    sess.commit(); sess.close()
    app = create_app(database_url=url)
    client = TestClient(app)
    token = client.post("/auth/login", json={"student_id": 1, "pin": "123456"}).json()["token"]
    return client, token


def test_send_message_persists_and_returns_reply(client_and_token):
    client, token = client_and_token
    fake_resp = LLMResponse(
        text="Hi Alice!", tool_calls=[], stop_reason="end_turn",
        input_tokens=10, output_tokens=4, raw=None,
    )
    with patch("pacer.api.routes.message.LLMClient.chat", new=AsyncMock(return_value=fake_resp)):
        resp = client.post(
            "/message/send", json={"text": "Hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Hi Alice!"
    assert "session_id" in body
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/integration/test_message_endpoint.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/pacer/api/routes/message.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, current_student_id
from pacer.session.store import SessionStore
from pacer.session.events import SSEEvent
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import RememberTool, SearchMemoryTool
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool
from pacer.agent.loop import AgentLoop
from pacer.llm.client import LLMClient, LLMMessage

router = APIRouter(prefix="/message", tags=["message"])

_SYSTEM_PROMPT_MVP = (
    "You are a warm, attentive AI study companion for a Chinese high-school senior. "
    "Speak in simplified Chinese unless the student writes in English. "
    "Use the tools to remember persistent facts and recall context. Be concise."
)


class SendRequest(BaseModel):
    text: str
    session_id: int | None = None


class SendResponse(BaseModel):
    text: str
    session_id: int


@router.post("/send", response_model=SendResponse)
async def send_message(
    req: SendRequest,
    request: Request,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
) -> SendResponse:
    store = SessionStore(db)
    if req.session_id is None:
        chat = store.create_session(student_id=student_id)
    else:
        chat = store.get_session(req.session_id)
        assert chat is not None and chat.student_id == student_id

    store.append_message(chat.id, role="user", agent=None, content=req.text)
    history_dicts = store.history_for_llm(chat.id)
    history = [LLMMessage(role=h["role"], content=h["content"]) for h in history_dicts[:-1]]

    reg = ToolRegistry()
    reg.register(RememberTool(lambda: db, student_id))
    reg.register(SearchMemoryTool(lambda: db, student_id))
    reg.register(GetStudentProfileTool(lambda: db, student_id))
    reg.register(UpdateStudentProfileTool(lambda: db, student_id))

    llm: LLMClient = request.app.state.llm
    loop = AgentLoop(llm=llm, tools=reg, system_prompt=_SYSTEM_PROMPT_MVP)
    result = await loop.run(req.text, history=history)

    store.append_message(
        chat.id, role="assistant", agent="homeroom", content=result.final_text,
        metadata={"iterations": result.iterations, "trace": result.trace},
    )
    bus = request.app.state.event_bus
    await bus.publish(SSEEvent(
        student_id=student_id, event_type="assistant_message",
        data={"session_id": chat.id, "text": result.final_text},
    ))
    return SendResponse(text=result.final_text, session_id=chat.id)
```

- [ ] **Step 4: Implement `src/pacer/api/routes/events.py`**

```python
from __future__ import annotations
import asyncio
import json
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from pacer.api.deps import current_student_id

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream_events(request: Request, student_id: int = Depends(current_student_id)):
    bus = request.app.state.event_bus
    queue = bus.subscribe(student_id)

    async def event_gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": evt.event_type,
                        "data": json.dumps(evt.data, ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            bus.unsubscribe(student_id, queue)

    return EventSourceResponse(event_gen())
```

- [ ] **Step 5: Update `src/pacer/api/server.py`**

```python
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
    app.state.llm = LLMClient(api_key=settings.anthropic_api_key, model=settings.main_model)
    app.include_router(auth_router)
    app.include_router(message_router)
    app.include_router(events_router)
    return app
```

- [ ] **Step 6: Run integration test**

Run: `pytest tests/integration/test_message_endpoint.py -v`
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add src/pacer/api/routes/message.py src/pacer/api/routes/events.py src/pacer/api/server.py tests/integration/test_message_endpoint.py
git commit -m "feat: /message/send + /events/stream wired to ReAct loop"
```

---

## Task 12: E2E Smoke Test

**Files:**
- Create: `tests/e2e/__init__.py`, `tests/e2e/test_chat_flow.py`
- Create: `scripts/seed_dev_student.py`

- [ ] **Step 1: Write E2E test (mocked LLM, real DB on tmpfile)**

```python
# tests/e2e/test_chat_flow.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pacer.db.models import Base, Student
from pacer.api.server import create_app
from pacer.api.deps import hash_pin
from pacer.llm.client import LLMResponse


@pytest.fixture
def client_token(tmp_path):
    db = tmp_path / "e2e.db"
    url = f"sqlite:///{db}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = SessionLocal()
    s.add(Student(id=42, name="ZeroDay", grade=12, pin_hash=hash_pin("000000")))
    s.commit(); s.close()
    app = create_app(database_url=url)
    client = TestClient(app)
    tok = client.post("/auth/login", json={"student_id": 42, "pin": "000000"}).json()["token"]
    return client, tok


def test_two_turn_conversation_persists(client_token):
    client, token = client_token
    replies = [
        LLMResponse(text="你好，ZeroDay！", tool_calls=[], stop_reason="end_turn",
                    input_tokens=10, output_tokens=5, raw=None),
        LLMResponse(text="你之前说过你想冲清华。", tool_calls=[], stop_reason="end_turn",
                    input_tokens=15, output_tokens=8, raw=None),
    ]
    with patch("pacer.api.routes.message.LLMClient.chat",
               new=AsyncMock(side_effect=replies)):
        r1 = client.post("/message/send", json={"text": "你好"},
                         headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 200
        sid = r1.json()["session_id"]
        r2 = client.post(
            "/message/send",
            json={"text": "我的目标是什么？", "session_id": sid},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
        assert r2.json()["session_id"] == sid
```

- [ ] **Step 2: Run E2E**

Run: `pytest tests/e2e/test_chat_flow.py -v`
Expected: 1 passed.

- [ ] **Step 3: Write a dev seed script**

Create `scripts/seed_dev_student.py`:

```python
"""Seed a dev student for local manual testing.

Usage: python scripts/seed_dev_student.py
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.config import get_settings
from pacer.db.models import Base, Student
from pacer.api.deps import hash_pin


def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        existing = s.query(Student).filter_by(id=1).first()
        if existing is None:
            s.add(Student(id=1, name="开发学生", grade=12, pin_hash=hash_pin("123456")))
            s.commit()
            print("seeded student id=1, pin=123456")
        else:
            print("student id=1 already exists; nothing to do")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: All previous tests pass + 1 e2e test pass.

- [ ] **Step 5: Manual smoke test (optional)**

```bash
# In one terminal:
cp .env.example .env  # set ANTHROPIC_API_KEY
alembic upgrade head
python scripts/seed_dev_student.py
uvicorn pacer.api.server:create_app --factory --reload

# In another terminal:
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"student_id": 1, "pin": "123456"}'
# Copy the token, then:
TOKEN="..."
curl -X POST http://localhost:8000/message/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"text": "你好"}'
```

Expected: a coherent Chinese reply from Claude Sonnet via the loop.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/ scripts/
git commit -m "test: e2e two-turn conversation + dev seed script"
```

---

## Task 13: Stage 1 Wrap-up

- [ ] **Step 1: Run the entire test suite with coverage**

Run: `pytest --cov=src/pacer --cov-report=term-missing`
Expected: All tests pass, coverage >= 80%.

- [ ] **Step 2: Smoke-check lint**

Run: `ruff check src/ tests/` and `mypy src/pacer`
Expected: No errors (or only intentional ones documented in a comment).

- [ ] **Step 3: Tag Stage 1 milestone**

```bash
git tag -a stage-1-skeleton -m "Stage 1 complete: single-agent ReAct + DB + FastAPI + SSE"
git push origin main --tags
```

---

## Validation Criteria (Stage 1 done when)

- [ ] All unit, integration, e2e tests pass (`pytest -v`)
- [ ] Manual smoke: login → POST /message/send → receive a coherent LLM reply
- [ ] SSE stream emits `assistant_message` events on the same student's `/events/stream`
- [ ] Database has student, session, messages persisted across server restart
- [ ] `git tag stage-1-skeleton` exists and is pushed
- [ ] No `# TODO` / placeholder code remains in implementations
