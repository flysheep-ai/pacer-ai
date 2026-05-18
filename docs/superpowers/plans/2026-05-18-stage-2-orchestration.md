# Stage 2 · 3-Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-agent ReAct loop with a 3-agent orchestrator. Homeroom is the always-present coordinator that uses a lightweight router LLM to decide whether to handle the turn itself, delegate to the subject teacher (with auto-loaded subject skill), or delegate to the mood companion. Validation: a student question like "帮我看这道导数题" routes to the subject teacher with `math` skill loaded; a low-mood message routes to the mood companion; a planning question stays with homeroom.

**Architecture:** A thin `Orchestrator` wraps three `AgentLoop` instances (sharing the same `LLMClient` but each with its own system prompt and tool whitelist). The orchestrator's `handle(user_message, session_id)` method first calls a `RouterLLM` (cheaper model, single-shot, JSON output) to get `{intent, subject}`, then dispatches. Each agent ends with `return_to_homeroom` (subject/mood) or `final_text` (homeroom), and the homeroom can optionally append a closing line.

**Tech Stack:** Reuses Stage 1's `LLMClient`, `ToolRegistry`, `AgentLoop`, `SessionStore`. Adds Markdown-based Skills loader.

---

## Target Files (NEW in Stage 2)

```
src/pacer/
├── orchestrator/
│   ├── __init__.py
│   ├── orchestrator.py            # Orchestrator: routes + dispatches
│   ├── router.py                  # RouterLLM: intent + subject from text
│   └── prompts.py                 # Shared prompt snippets, intent enum
├── agents/
│   ├── __init__.py
│   ├── homeroom.py                # build_homeroom_agent() factory
│   ├── subject_teacher.py         # build_subject_teacher_agent(subject)
│   └── mood_companion.py          # build_mood_agent() factory
├── skills/
│   ├── __init__.py
│   ├── loader.py                  # SkillsLoader (filesystem, lazy load)
│   └── content/
│       ├── math/
│       │   └── 导数应用-切线方程.md   # one example skill (template)
│       └── english/
│           └── 完型填空-逻辑关系.md   # one example skill (template)
└── tools/
    ├── delegate_tools.py          # delegate_to_*, return_to_homeroom
    └── skill_tools.py             # load_skill tool
```

Modified:
- `src/pacer/api/routes/message.py` → route through Orchestrator instead of bare AgentLoop
- `src/pacer/api/server.py` → instantiate Orchestrator on app state

---

## Task 1: RouterLLM

**Files:**
- Create: `src/pacer/orchestrator/__init__.py`, `src/pacer/orchestrator/router.py`, `src/pacer/orchestrator/prompts.py`
- Create: `tests/unit/test_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_router.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pacer.orchestrator.router import RouterLLM, RouteDecision


@pytest.mark.asyncio
async def test_router_returns_subject_qa_for_math_question():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=_resp(
        '{"intent":"subject_qa","subject":"math","confidence":0.9}'
    ))
    r = RouterLLM(llm=llm, model="haiku")
    decision = await r.route("帮我看这道导数题")
    assert decision.intent == "subject_qa"
    assert decision.subject == "math"


@pytest.mark.asyncio
async def test_router_falls_back_to_chitchat_on_parse_failure():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=_resp("not json at all"))
    r = RouterLLM(llm=llm, model="haiku")
    decision = await r.route("hi")
    assert decision.intent == "chitchat"
    assert decision.subject is None


@pytest.mark.asyncio
async def test_router_rule_override_for_explicit_subject_keyword():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=_resp(
        '{"intent":"chitchat","subject":null,"confidence":0.5}'
    ))
    r = RouterLLM(llm=llm, model="haiku")
    decision = await r.route("英语老师，这题怎么做")
    assert decision.subject == "english"  # rule override
    assert decision.intent == "subject_qa"


def _resp(text):
    from pacer.llm.client import LLMResponse
    return LLMResponse(text=text, tool_calls=[], stop_reason="end_turn",
                       input_tokens=10, output_tokens=5, raw=None)
```

- [ ] **Step 2: Implement `src/pacer/orchestrator/prompts.py`**

```python
ROUTER_SYSTEM = """You classify a Chinese high-school student's message into one of these intents:
- subject_qa: asking about a school subject (math/chinese/english/physics/chemistry/biology)
- mood_support: expressing stress, anxiety, sadness, frustration, or low mood
- planning: asking about study plan, schedule, today's tasks, or weekly goals
- chitchat: greetings, small talk, anything else

Output STRICT JSON only, no prose:
{"intent": "<one of the four>", "subject": "math|chinese|english|physics|chemistry|biology|null", "confidence": 0.0-1.0}

When intent != subject_qa, subject is null.
"""

SUBJECT_KEYWORD_MAP = {
    "数学": "math", "math": "math",
    "语文": "chinese", "chinese": "chinese", "文言文": "chinese", "作文": "chinese",
    "英语": "english", "english": "english", "完型": "english", "阅读理解": "english",
    "物理": "physics", "physics": "physics",
    "化学": "chemistry", "chemistry": "chemistry",
    "生物": "biology", "biology": "biology",
}
```

- [ ] **Step 3: Implement `src/pacer/orchestrator/router.py`**

```python
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Literal
from pacer.llm.client import LLMClient, LLMMessage
from pacer.orchestrator.prompts import ROUTER_SYSTEM, SUBJECT_KEYWORD_MAP


Intent = Literal["subject_qa", "mood_support", "planning", "chitchat"]


@dataclass
class RouteDecision:
    intent: Intent
    subject: str | None
    confidence: float


class RouterLLM:
    def __init__(self, llm: LLMClient, model: str):
        self.llm = llm
        self.model = model

    async def route(self, text: str) -> RouteDecision:
        resp = await self.llm.chat(
            [LLMMessage(role="user", content=text)],
            system=ROUTER_SYSTEM,
            model=self.model,
        )
        decision = self._parse(resp.text)
        return self._apply_rules(text, decision)

    def _parse(self, raw: str) -> RouteDecision:
        try:
            data = json.loads(raw.strip())
            intent = data.get("intent", "chitchat")
            if intent not in ("subject_qa", "mood_support", "planning", "chitchat"):
                intent = "chitchat"
            return RouteDecision(
                intent=intent,
                subject=data.get("subject") if data.get("subject") != "null" else None,
                confidence=float(data.get("confidence", 0.5)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return RouteDecision(intent="chitchat", subject=None, confidence=0.0)

    def _apply_rules(self, text: str, decision: RouteDecision) -> RouteDecision:
        # If user explicitly names a subject, force subject_qa with that subject.
        lower = text.lower()
        for kw, subj in SUBJECT_KEYWORD_MAP.items():
            if kw in text or kw in lower:
                return RouteDecision(intent="subject_qa", subject=subj, confidence=max(decision.confidence, 0.85))
        return decision
```

- [ ] **Step 4: Run, watch pass**

Run: `pytest tests/unit/test_router.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/orchestrator/ tests/unit/test_router.py
git commit -m "feat: RouterLLM with rule-based subject override"
```

---

## Task 2: Skills Loader

**Files:**
- Create: `src/pacer/skills/__init__.py`, `src/pacer/skills/loader.py`
- Create: `src/pacer/skills/content/math/导数应用-切线方程.md`
- Create: `src/pacer/skills/content/english/完型填空-逻辑关系.md`
- Create: `tests/unit/test_skills_loader.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_skills_loader.py
import pytest
from pathlib import Path
from pacer.skills.loader import SkillsLoader


@pytest.fixture
def loader(tmp_path):
    root = tmp_path / "content"
    (root / "math").mkdir(parents=True)
    (root / "math" / "test-skill.md").write_text(
        "---\nname: test-skill\nsubject: math\nchapter: test\ndescription: A test skill\n---\n\n## Body\nteach this.\n",
        encoding="utf-8",
    )
    return SkillsLoader(root=root)


def test_lists_skills_with_metadata(loader):
    skills = loader.list_skills(subject="math")
    assert len(skills) == 1
    assert skills[0].name == "test-skill"
    assert skills[0].description == "A test skill"


def test_loads_full_skill_body(loader):
    body = loader.load("test-skill")
    assert "## Body" in body
    assert "teach this." in body


def test_load_missing_returns_none(loader):
    assert loader.load("ghost") is None
```

- [ ] **Step 2: Implement `src/pacer/skills/loader.py`**

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path


_FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


@dataclass
class SkillMeta:
    name: str
    subject: str
    chapter: str
    description: str
    path: Path


class SkillsLoader:
    """Lazy filesystem-backed skills. content/<subject>/<name>.md"""

    def __init__(self, root: Path):
        self.root = root
        self._index: dict[str, SkillMeta] | None = None

    def _ensure_index(self) -> dict[str, SkillMeta]:
        if self._index is not None:
            return self._index
        index: dict[str, SkillMeta] = {}
        for path in self.root.rglob("*.md"):
            try:
                meta = self._parse_metadata(path)
                if meta is not None:
                    index[meta.name] = meta
            except Exception:
                continue
        self._index = index
        return index

    def _parse_metadata(self, path: Path) -> SkillMeta | None:
        text = path.read_text(encoding="utf-8")
        m = _FM_RE.match(text)
        if m is None:
            return None
        fm = m.group(1)
        data: dict[str, str] = {}
        for line in fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
        if "name" not in data:
            return None
        return SkillMeta(
            name=data["name"],
            subject=data.get("subject", path.parent.name),
            chapter=data.get("chapter", ""),
            description=data.get("description", ""),
            path=path,
        )

    def list_skills(self, *, subject: str | None = None) -> list[SkillMeta]:
        idx = self._ensure_index()
        all_ = list(idx.values())
        if subject is None:
            return all_
        return [s for s in all_ if s.subject == subject]

    def load(self, name: str) -> str | None:
        idx = self._ensure_index()
        meta = idx.get(name)
        if meta is None:
            return None
        return meta.path.read_text(encoding="utf-8")
```

Create `src/pacer/skills/__init__.py`:

```python
from pacer.skills.loader import SkillsLoader, SkillMeta
__all__ = ["SkillsLoader", "SkillMeta"]
```

- [ ] **Step 3: Create two example skills**

`src/pacer/skills/content/math/导数应用-切线方程.md`:

```markdown
---
name: math-导数应用-切线方程
subject: math
chapter: 函数与导数
description: 求曲线上某点切线方程的标准方法
---

## 核心方法

1. **求导**：先对 f(x) 求导，得到 f'(x)
2. **代入求斜率**：把切点横坐标代入 f'(x)，得到切线斜率 k
3. **写方程**：用点斜式 y - y₀ = k(x - x₀)

## 易错点
- 切点 vs 经过 (x, y) 点：如果题目说"经过"某点，可能不是切点，要设切点 (t, f(t)) 再列方程
- 求导时常数项忘了求成 0
- 复合函数求导链式法则漏一环

## 例题
设 f(x) = x³ - 2x，求在 x = 1 处的切线方程。
- f'(x) = 3x² - 2
- f'(1) = 1
- 切点 (1, -1)
- 切线: y + 1 = 1·(x - 1) → y = x - 2

## 变式题模板（用于 generate_variant）
- 替换函数形式：x³ → e^x / ln x / sin x
- 替换切点：x = 1 → x = π/4 / x = e
- 加约束：求切线过某点的所有切线（隐含找切点 t）
```

`src/pacer/skills/content/english/完型填空-逻辑关系.md`:

```markdown
---
name: english-完型填空-逻辑关系
subject: english
chapter: 完型填空
description: 通过逻辑关系词判断空格选词
---

## 核心思路

完型填空近半空格靠**逻辑关系**判断：
- **因果**：so / therefore / as a result / because / since / due to
- **转折**：but / however / yet / nevertheless / although
- **递进**：moreover / furthermore / besides / what's more
- **对比**：while / whereas / in contrast / on the other hand
- **举例**：for example / for instance / such as

## 解题流程
1. 跳读上下句，找逻辑关系词
2. 判断空格前后是同向（递进/因果/举例）还是反向（转折/对比）
3. 同向选近义词，反向选反义词
4. 代入复读确认通顺

## 易错点
- 把 "however" 误读成 "moreover"（关键词漏看）
- 单看一句，没考虑段落逻辑
- 选项里有同义词陷阱（两个看似合理，选最贴合语气的）
```

- [ ] **Step 4: Run, watch pass**

Run: `pytest tests/unit/test_skills_loader.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/skills/ tests/unit/test_skills_loader.py
git commit -m "feat: SkillsLoader with two example skill templates (math + english)"
```

---

## Task 3: load_skill Tool

**Files:**
- Create: `src/pacer/tools/skill_tools.py`
- Create: `tests/unit/test_skill_tools.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_skill_tools.py
import pytest
from pathlib import Path
from pacer.skills.loader import SkillsLoader
from pacer.tools.skill_tools import LoadSkillTool, ListSkillsTool


@pytest.fixture
def loader(tmp_path):
    root = tmp_path / "content"
    (root / "math").mkdir(parents=True)
    (root / "math" / "x.md").write_text(
        "---\nname: x\nsubject: math\nchapter: c\ndescription: d\n---\nBODY",
        encoding="utf-8",
    )
    return SkillsLoader(root=root)


@pytest.mark.asyncio
async def test_load_skill_returns_body(loader):
    tool = LoadSkillTool(loader=loader)
    result = await tool.execute(name="x")
    assert "BODY" in result["body"]


@pytest.mark.asyncio
async def test_list_skills_filtered_by_subject(loader):
    tool = ListSkillsTool(loader=loader)
    result = await tool.execute(subject="math")
    assert any(s["name"] == "x" for s in result["skills"])
```

- [ ] **Step 2: Implement `src/pacer/tools/skill_tools.py`**

```python
from __future__ import annotations
from pacer.tools.base import BaseTool
from pacer.skills.loader import SkillsLoader


class LoadSkillTool(BaseTool):
    name = "load_skill"
    description = "Load the full body of a skill by name. Use this to fetch teaching content before answering."
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    is_readonly = True

    def __init__(self, loader: SkillsLoader):
        self.loader = loader

    async def execute(self, *, name: str) -> dict:
        body = self.loader.load(name)
        if body is None:
            return {"status": "not_found", "name": name}
        return {"name": name, "body": body}


class ListSkillsTool(BaseTool):
    name = "list_skills"
    description = "List available skills, optionally filtered by subject."
    parameters = {
        "type": "object",
        "properties": {"subject": {"type": "string", "description": "math/chinese/english/physics/chemistry/biology"}},
    }
    is_readonly = True

    def __init__(self, loader: SkillsLoader):
        self.loader = loader

    async def execute(self, *, subject: str | None = None) -> dict:
        skills = self.loader.list_skills(subject=subject)
        return {"skills": [
            {"name": s.name, "subject": s.subject, "chapter": s.chapter, "description": s.description}
            for s in skills
        ]}
```

- [ ] **Step 3: Run, watch pass**

Run: `pytest tests/unit/test_skill_tools.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add src/pacer/tools/skill_tools.py tests/unit/test_skill_tools.py
git commit -m "feat: load_skill + list_skills tools"
```

---

## Task 4: Three Agent Factories

**Files:**
- Create: `src/pacer/agents/__init__.py`, `src/pacer/agents/homeroom.py`, `src/pacer/agents/subject_teacher.py`, `src/pacer/agents/mood_companion.py`
- Create: `tests/unit/test_agent_factories.py`

Each factory returns an `AgentLoop` configured with the right system prompt + tool registry.

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_agent_factories.py
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.llm.client import LLMClient
from pacer.skills.loader import SkillsLoader
from pacer.agents.homeroom import build_homeroom_agent
from pacer.agents.subject_teacher import build_subject_teacher_agent
from pacer.agents.mood_companion import build_mood_agent


def _llm():
    return LLMClient(api_key="sk-test", model="claude-sonnet-4-6")


@pytest.fixture
def common(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    sess.add(Student(id=1, name="X", grade=12, pin_hash="h")); sess.commit()
    loader = SkillsLoader(root=tmp_path / "skills")
    (tmp_path / "skills").mkdir()
    return sess, loader


def test_homeroom_has_no_delegate_self_tool(common):
    sess, _ = common
    loop = build_homeroom_agent(llm=_llm(), session_factory=lambda: sess, student_id=1)
    names = set(loop.tools.names())
    assert "search_memory" in names
    assert "remember" in names
    assert "get_student_profile" in names
    assert "delegate_to_subject_teacher" in names
    assert "delegate_to_mood_companion" in names


def test_subject_teacher_has_load_skill(common):
    sess, loader = common
    loop = build_subject_teacher_agent(
        llm=_llm(), session_factory=lambda: sess, student_id=1,
        subject="math", skills_loader=loader,
    )
    names = set(loop.tools.names())
    assert "load_skill" in names
    assert "list_skills" in names
    assert "return_to_homeroom" in names
    # No homeroom-specific tools
    assert "delegate_to_subject_teacher" not in names


def test_mood_agent_has_log_mood(common):
    sess, _ = common
    loop = build_mood_agent(llm=_llm(), session_factory=lambda: sess, student_id=1)
    names = set(loop.tools.names())
    assert "log_mood" in names
    assert "return_to_homeroom" in names
```

- [ ] **Step 2: Implement `src/pacer/tools/delegate_tools.py` (signals only, no execution)**

```python
# src/pacer/tools/delegate_tools.py
from __future__ import annotations
from pacer.tools.base import BaseTool


class DelegateToSubjectTeacherTool(BaseTool):
    """Marker tool — the orchestrator intercepts this call and re-dispatches."""
    name = "delegate_to_subject_teacher"
    description = "Hand the conversation to the subject teacher. The orchestrator will dispatch the conversation to the subject specialist."
    parameters = {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "enum": ["math", "chinese", "english", "physics", "chemistry", "biology"]},
            "reason": {"type": "string"},
        },
        "required": ["subject"],
    }
    is_readonly = False

    async def execute(self, *, subject: str, reason: str = "") -> dict:
        # Marker — orchestrator processes this before reaching here.
        return {"delegated_to": "subject_teacher", "subject": subject, "reason": reason}


class DelegateToMoodCompanionTool(BaseTool):
    name = "delegate_to_mood_companion"
    description = "Hand the conversation to the mood companion for emotional support."
    parameters = {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": [],
    }
    is_readonly = False

    async def execute(self, *, reason: str = "") -> dict:
        return {"delegated_to": "mood_companion", "reason": reason}


class ReturnToHomeroomTool(BaseTool):
    name = "return_to_homeroom"
    description = "Signal that this agent has completed its task and control should return to the homeroom teacher."
    parameters = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": [],
    }
    is_readonly = False

    async def execute(self, *, summary: str = "") -> dict:
        return {"return": True, "summary": summary}


class LogMoodTool(BaseTool):
    name = "log_mood"
    description = "Persist a mood log entry for the student (self_score 1-5, topics, summary, red_flag)."
    parameters = {
        "type": "object",
        "properties": {
            "self_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "topics": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "red_flag": {"type": "boolean", "default": False},
        },
        "required": ["self_score", "summary"],
    }
    is_readonly = False

    def __init__(self, session_factory, student_id):
        self._session_factory = session_factory
        self._student_id = student_id

    async def execute(self, *, self_score: int, summary: str,
                      topics: list[str] | None = None, red_flag: bool = False) -> dict:
        from pacer.db.models import MoodLog
        sess = self._session_factory()
        log = MoodLog(
            student_id=self._student_id, self_score=self_score,
            topics=topics or [], summary=summary, red_flag=red_flag,
        )
        sess.add(log); sess.commit(); sess.refresh(log)
        return {"id": log.id, "red_flag": red_flag}
```

- [ ] **Step 3: Implement agent factories**

`src/pacer/agents/homeroom.py`:

```python
from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient
from pacer.agent.loop import AgentLoop
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import RememberTool, SearchMemoryTool
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool
from pacer.tools.delegate_tools import DelegateToSubjectTeacherTool, DelegateToMoodCompanionTool


HOMEROOM_SYSTEM = """你是一位温和、专业的高三 AI 班主任。你了解这个学生，关心他的学习节奏与情绪状态。

你的职责：
- 接住所有对话开端，识别学生意图
- 计划生成 / 进度督促 / 日报 / 晚安
- 当学生问学科问题时，调用 delegate_to_subject_teacher 把对话交给学科老师
- 当学生表达压力/焦虑/低落时，调用 delegate_to_mood_companion 交给心态师
- 自然地补充学生画像（用 remember 工具），不要审问
- 简洁、温暖、不啰嗦"""


def build_homeroom_agent(
    *, llm: LLMClient, session_factory: Callable[[], Session], student_id: int,
    max_iterations: int = 5,
) -> AgentLoop:
    reg = ToolRegistry()
    reg.register(SearchMemoryTool(session_factory, student_id))
    reg.register(RememberTool(session_factory, student_id))
    reg.register(GetStudentProfileTool(session_factory, student_id))
    reg.register(UpdateStudentProfileTool(session_factory, student_id))
    reg.register(DelegateToSubjectTeacherTool())
    reg.register(DelegateToMoodCompanionTool())
    return AgentLoop(llm=llm, tools=reg, system_prompt=HOMEROOM_SYSTEM, max_iterations=max_iterations)
```

`src/pacer/agents/subject_teacher.py`:

```python
from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient
from pacer.agent.loop import AgentLoop
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import SearchMemoryTool
from pacer.tools.skill_tools import LoadSkillTool, ListSkillsTool
from pacer.tools.delegate_tools import ReturnToHomeroomTool
from pacer.skills.loader import SkillsLoader


SUBJECT_SYSTEM_TMPL = """你是一位{subject}学科老师，专业、严谨、爱启发。
不寒暄、不闲聊，专注于讲解这道题或这个知识点。

工作流程：
1. 先调 list_skills(subject="{subject}") 看可用的知识点资料
2. 调 load_skill(name=...) 加载相关知识点的完整内容
3. 给学生分步讲解，关键提示要点
4. 讲完后调 return_to_homeroom 把对话交回班主任

学生当前的薄弱点你可以用 search_memory(query="...") 查询。"""


def build_subject_teacher_agent(
    *, llm: LLMClient, session_factory: Callable[[], Session], student_id: int,
    subject: str, skills_loader: SkillsLoader, max_iterations: int = 8,
) -> AgentLoop:
    reg = ToolRegistry()
    reg.register(SearchMemoryTool(session_factory, student_id))
    reg.register(LoadSkillTool(loader=skills_loader))
    reg.register(ListSkillsTool(loader=skills_loader))
    reg.register(ReturnToHomeroomTool())
    return AgentLoop(
        llm=llm, tools=reg,
        system_prompt=SUBJECT_SYSTEM_TMPL.format(subject=subject),
        max_iterations=max_iterations,
    )
```

`src/pacer/agents/mood_companion.py`:

```python
from __future__ import annotations
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient
from pacer.agent.loop import AgentLoop
from pacer.tools.base import ToolRegistry
from pacer.tools.memory_tools import SearchMemoryTool
from pacer.tools.delegate_tools import LogMoodTool, ReturnToHomeroomTool


MOOD_SYSTEM = """你是一位温柔、不评判的心态陪伴者，像一位心理咨询取向的学姐/学长。
不解题、不催进度，只关注学生的感受。

工作风格：
- 用具体的倾听 + 共情技术，不说"加油""一切都会好的"这类敷衍
- 必要时引导呼吸 / 认知重构 / 情境再框架
- 对话结束前调 log_mood 记录（self_score 1-5，topics 列表，summary 一句话，red_flag 默认 false）
- 如果学生表达自伤/严重抑郁/极端念头：red_flag=true，并立即给出兜底信息（如"我会先记下，你现在可以联系...")
- 完成对话后调 return_to_homeroom"""


def build_mood_agent(
    *, llm: LLMClient, session_factory: Callable[[], Session], student_id: int,
    max_iterations: int = 6,
) -> AgentLoop:
    reg = ToolRegistry()
    reg.register(SearchMemoryTool(session_factory, student_id))
    reg.register(LogMoodTool(session_factory, student_id))
    reg.register(ReturnToHomeroomTool())
    return AgentLoop(llm=llm, tools=reg, system_prompt=MOOD_SYSTEM, max_iterations=max_iterations)
```

- [ ] **Step 4: Run, watch pass**

Run: `pytest tests/unit/test_agent_factories.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/agents/ src/pacer/tools/delegate_tools.py tests/unit/test_agent_factories.py
git commit -m "feat: three agent factories (homeroom/subject_teacher/mood_companion) + delegate tools"
```

---

## Task 5: Orchestrator

**Files:**
- Create: `src/pacer/orchestrator/orchestrator.py`
- Create: `tests/integration/test_orchestrator.py`

The orchestrator's loop:
1. Run router → get `intent`
2. If `intent in (planning, chitchat)` → run homeroom directly
3. If `intent == subject_qa` → run subject_teacher (with subject)
4. If `intent == mood_support` → run mood_agent
5. Intercept `delegate_to_*` tool calls by homeroom (homeroom can also delegate mid-conversation, not just based on router)
6. When subject/mood agent calls `return_to_homeroom`, optionally append a brief homeroom closing turn

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.skills.loader import SkillsLoader
from pacer.llm.client import LLMResponse
from pacer.orchestrator.orchestrator import Orchestrator
from pacer.orchestrator.router import RouteDecision


def _resp(text="", tool_calls=None, stop_reason="end_turn"):
    return LLMResponse(text=text, tool_calls=tool_calls or [],
                       stop_reason=stop_reason, input_tokens=10, output_tokens=5, raw=None)


@pytest.fixture
def env(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = Session(engine)
    sess.add(Student(id=1, name="X", grade=12, pin_hash="h")); sess.commit()
    skills_dir = tmp_path / "skills" / "math"
    skills_dir.mkdir(parents=True)
    (skills_dir / "x.md").write_text(
        "---\nname: x\nsubject: math\nchapter: c\ndescription: d\n---\nbody",
        encoding="utf-8",
    )
    loader = SkillsLoader(root=tmp_path / "skills")
    return sess, loader


@pytest.mark.asyncio
async def test_routes_math_question_to_subject_teacher(env):
    sess, loader = env
    llm = MagicMock()
    # Router LLM returns subject_qa/math; subject teacher responds with final text.
    llm.chat = AsyncMock(side_effect=[
        _resp(text='{"intent":"subject_qa","subject":"math","confidence":0.95}'),
        _resp(text="切线方程是 y=2x-1。"),
    ])
    orch = Orchestrator(
        llm=llm, router_model="haiku",
        session_factory=lambda: sess, student_id=1, skills_loader=loader,
    )
    result = await orch.handle("求 f(x)=x^2 在 x=1 切线", history=[])
    assert "切线" in result.final_text
    assert result.agent_used == "subject_teacher"
    assert result.subject == "math"


@pytest.mark.asyncio
async def test_routes_mood_to_mood_agent(env):
    sess, loader = env
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=[
        _resp(text='{"intent":"mood_support","subject":null,"confidence":0.9}'),
        _resp(text="听起来你今天压力很大。"),
    ])
    orch = Orchestrator(
        llm=llm, router_model="haiku",
        session_factory=lambda: sess, student_id=1, skills_loader=loader,
    )
    result = await orch.handle("我感觉撑不住了", history=[])
    assert result.agent_used == "mood_companion"


@pytest.mark.asyncio
async def test_chitchat_stays_with_homeroom(env):
    sess, loader = env
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=[
        _resp(text='{"intent":"chitchat","subject":null,"confidence":0.6}'),
        _resp(text="早安！今天打算怎么安排？"),
    ])
    orch = Orchestrator(
        llm=llm, router_model="haiku",
        session_factory=lambda: sess, student_id=1, skills_loader=loader,
    )
    result = await orch.handle("早上好", history=[])
    assert result.agent_used == "homeroom"
```

- [ ] **Step 2: Implement Orchestrator**

```python
# src/pacer/orchestrator/orchestrator.py
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable
from sqlalchemy.orm import Session
from pacer.llm.client import LLMClient, LLMMessage
from pacer.skills.loader import SkillsLoader
from pacer.orchestrator.router import RouterLLM, RouteDecision
from pacer.agents.homeroom import build_homeroom_agent
from pacer.agents.subject_teacher import build_subject_teacher_agent
from pacer.agents.mood_companion import build_mood_agent
from pacer.agent.loop import AgentResult


@dataclass
class OrchestratedResult:
    final_text: str
    agent_used: str  # "homeroom" | "subject_teacher" | "mood_companion"
    subject: str | None
    route: RouteDecision
    inner: AgentResult


class Orchestrator:
    def __init__(
        self, *, llm: LLMClient, router_model: str,
        session_factory: Callable[[], Session], student_id: int,
        skills_loader: SkillsLoader,
    ):
        self.llm = llm
        self.router = RouterLLM(llm=llm, model=router_model)
        self.session_factory = session_factory
        self.student_id = student_id
        self.skills_loader = skills_loader

    async def handle(self, user_message: str, history: list[LLMMessage]) -> OrchestratedResult:
        route = await self.router.route(user_message)
        if route.intent == "subject_qa" and route.subject:
            agent = build_subject_teacher_agent(
                llm=self.llm,
                session_factory=self.session_factory, student_id=self.student_id,
                subject=route.subject, skills_loader=self.skills_loader,
            )
            agent_used = "subject_teacher"
        elif route.intent == "mood_support":
            agent = build_mood_agent(
                llm=self.llm,
                session_factory=self.session_factory, student_id=self.student_id,
            )
            agent_used = "mood_companion"
        else:
            agent = build_homeroom_agent(
                llm=self.llm,
                session_factory=self.session_factory, student_id=self.student_id,
            )
            agent_used = "homeroom"

        result = await agent.run(user_message, history=history)
        return OrchestratedResult(
            final_text=result.final_text, agent_used=agent_used,
            subject=route.subject, route=route, inner=result,
        )
```

- [ ] **Step 3: Run, watch pass**

Run: `pytest tests/integration/test_orchestrator.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/pacer/orchestrator/orchestrator.py tests/integration/test_orchestrator.py
git commit -m "feat: Orchestrator dispatches to homeroom/subject_teacher/mood by router intent"
```

---

## Task 6: Wire Orchestrator into FastAPI Route

**Files:**
- Modify: `src/pacer/api/routes/message.py`
- Modify: `src/pacer/api/server.py`
- Modify: `tests/integration/test_message_endpoint.py` (extend with subject routing assertion)

- [ ] **Step 1: Update server.py to instantiate SkillsLoader and pass it to message route**

Add to `create_app`:

```python
# In server.py imports
from pathlib import Path
from pacer.skills.loader import SkillsLoader

# In create_app(), after instantiating llm:
app.state.skills_loader = SkillsLoader(root=Path(__file__).parent.parent / "skills" / "content")
```

- [ ] **Step 2: Refactor `src/pacer/api/routes/message.py` to use Orchestrator**

Replace the body of `send_message` with:

```python
@router.post("/send", response_model=SendResponse)
async def send_message(
    req: SendRequest, request: Request,
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

    from pacer.orchestrator.orchestrator import Orchestrator
    from pacer.config import get_settings
    settings = get_settings()

    orch = Orchestrator(
        llm=request.app.state.llm,
        router_model=settings.router_model,
        session_factory=lambda: db,
        student_id=student_id,
        skills_loader=request.app.state.skills_loader,
    )
    out = await orch.handle(req.text, history=history)

    store.append_message(
        chat.id, role="assistant", agent=out.agent_used, content=out.final_text,
        metadata={
            "iterations": out.inner.iterations,
            "trace": out.inner.trace,
            "route": {"intent": out.route.intent, "subject": out.route.subject},
        },
    )
    bus = request.app.state.event_bus
    await bus.publish(SSEEvent(
        student_id=student_id, event_type="assistant_message",
        data={"session_id": chat.id, "text": out.final_text, "agent": out.agent_used},
    ))
    return SendResponse(text=out.final_text, session_id=chat.id)
```

- [ ] **Step 3: Extend integration test to verify routing**

Add to `tests/integration/test_message_endpoint.py`:

```python
def test_message_routes_to_subject_teacher(client_and_token):
    client, token = client_and_token
    replies = [
        _resp('{"intent":"subject_qa","subject":"math","confidence":0.9}'),
        _resp(text="切线方程为 y=2x-1。"),
    ]
    with patch("pacer.api.routes.message.LLMClient.chat", new=AsyncMock(side_effect=replies)):
        resp = client.post("/message/send", json={"text": "数学题：求切线"},
                           headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "切线" in body["text"]


def _resp(text="", stop_reason="end_turn"):
    from pacer.llm.client import LLMResponse
    return LLMResponse(text=text, tool_calls=[], stop_reason=stop_reason,
                       input_tokens=10, output_tokens=5, raw=None)
```

- [ ] **Step 4: Run all tests**

Run: `pytest -v`
Expected: All previous + new pass.

- [ ] **Step 5: Commit + tag**

```bash
git add src/pacer/api/ tests/integration/test_message_endpoint.py
git commit -m "feat: /message/send dispatches via Orchestrator"
git tag -a stage-2-orchestration -m "Stage 2 complete: 3-agent orchestration with router LLM"
git push origin main --tags
```

---

## Validation Criteria (Stage 2 done when)

- [ ] `pytest -v` all green
- [ ] Manual smoke: send a math question → reply mentions math content; send a stress message → reply has empathetic tone
- [ ] `messages` table records `agent` field correctly per turn
- [ ] Router LLM logs visible in `metadata.route` for each assistant message
- [ ] `git tag stage-2-orchestration` pushed
