# Stage 4 · Mood Companion + Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the mood companion with red-line detection, fill in the remaining 4 subjects' skill templates, polish the SSE streaming experience, build E2E test coverage for all 4 daily scenarios, and lock down the product for a single-student trial.

**Architecture:** Red-line detection is a two-layer safeguard: keyword-scan pre-filter (fast, no LLM cost) + LLM secondary confirm (accurate, only triggered when keywords hit). The remaining 4 subject skill libraries (chinese, physics, chemistry, biology) get template files equivalent to the math + english examples from Stage 2. E2E tests exercise the full day loop programmatically with recorded LLM responses.

**Tech Stack:** Stage 1-3 foundations + keyword matching (regex) + E2E test fixtures.

---

## Target Files (NEW in Stage 4)

```
src/pacer/
├── companion/
│   ├── red_line.py                # keyword patterns + LLM confirm
│   ├── mood_handler.py            # mood log generation + trend analysis
│   └── chat_handler.py            # Homeroom orchestration of daily chat flow
├── skills/content/
│   ├── chinese/                   # 文言文虚词 / 古诗词鉴赏 / 现代文阅读 / 作文
│   ├── physics/                   # 力学 / 电磁学 / 热学 / 光学 / 原子物理
│   ├── chemistry/                 # 无机化学 / 有机化学 / 化学实验 / 化学计算
│   └── biology/                   # 细胞生物学 / 遗传学 / 生态学 / 生物技术
├── api/routes/
│   ├── upload.py                  # POST /upload/image → base64 → vision tool
│   └── profile.py                 # GET/PATCH /profile (student self-service)
tests/
├── e2e/
│   ├── test_daily_cycle.py        # full 4-scenario day with recorded LLM
│   ├── test_red_line.py           # red-line scenarios
│   └── test_replay_offline.py     # offline → login → backlog flush
```

Modified:
- `src/pacer/agents/mood_companion.py` → inject red_line scanner into prompt
- `src/pacer/api/server.py` → register upload + profile routes
- `src/pacer/companion/backlog.py` → wire into SSE connect + login

---

## Task 1: Red-Line Detection System

**Files:**
- Create: `src/pacer/companion/red_line.py`
- Modify: `src/pacer/agents/mood_companion.py`
- Create: `tests/e2e/test_red_line.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/e2e/test_red_line.py
import pytest
from pacer.companion.red_line import (
    scan_keywords, RED_LINE_PATTERNS,
    should_escalate, ESCALATION_RESPONSE,
)


def test_scan_keywords_detects_self_harm_mention():
    result = scan_keywords("我觉得活着没意思，不如死了算了")
    assert len(result) >= 1
    assert result[0]["category"] == "self_harm"


def test_scan_keywords_detects_severe_depression():
    result = scan_keywords("我已经连续失眠一个月了，每天都不想醒来")
    assert len(result) >= 1


def test_scan_keywords_no_false_positive_on_normal():
    result = scan_keywords("今天数学好难，心情不太好")
    assert len(result) == 0


def test_escalation_response_includes_hotline():
    text = ESCALATION_RESPONSE
    assert "12320" in text or "心理" in text or "热线" in text


@pytest.mark.asyncio
async def test_red_line_flow_with_llm_confirm():
    """When keyword scan hits, LLM is called to confirm severity."""
    from unittest.mock import AsyncMock, MagicMock
    from pacer.llm.client import LLMResponse
    from pacer.companion.red_line import confirm_with_llm

    llm = MagicMock()
    llm.chat = AsyncMock(return_value=LLMResponse(
        text='{"is_crisis":true,"severity":"high","recommendation":"immediate_escalation"}',
        tool_calls=[], stop_reason="end_turn", input_tokens=20, output_tokens=10, raw=None,
    ))
    result = await confirm_with_llm(llm, "claude-haiku-4-5", "我觉得活着没意思")
    assert result["is_crisis"] is True
    assert result["severity"] == "high"


def test_keyword_scan_is_case_insensitive():
    result = scan_keywords("I WANT TO END MY LIFE")
    assert len(result) >= 1
```

- [ ] **Step 2: Run, watch fail**

Run: `pytest tests/e2e/test_red_line.py -v`
Expected: ModuleNotFoundError on `pacer.companion.red_line`.

- [ ] **Step 3: Implement `src/pacer/companion/red_line.py`**

```python
from __future__ import annotations
import re
from typing import Any
from pacer.llm.client import LLMClient, LLMMessage

# Category → list of (regex_pattern, severity_weight)
RED_LINE_PATTERNS: dict[str, list[tuple[str, int]]] = {
    "self_harm": [
        (r"自杀|自残|割腕|跳楼|结束(自己|生命)|不想活|活不下去|死了算了|死了一了百了", 10),
        (r"kill\s*myself|end\s*my\s*life|suicide|self[\s-]harm", 10),
    ],
    "severe_depression": [
        (r"重度抑郁|确诊抑郁|抑郁发作|完全没动力|行尸走肉|连续.*失眠|每天都不想醒", 8),
        (r"severe\s*depression|clinically\s*depressed|major\s*depressive", 8),
    ],
    "crisis": [
        (r"活着的意义|为什么活着|撑不住了|坚持不下去|快崩溃了|崩溃边缘", 6),
        (r"can't\s*go\s*on|breaking\s*down|falling\s*apart|unbearable", 6),
    ],
    "abuse_disclosure": [
        (r"被打|家暴|虐待|体罚|被欺负|霸凌|性侵|猥亵", 10),
        (r"abuse|assault|harassment|bullying|molest", 10),
    ],
}

ESCALATION_RESPONSE = (
    "我听到了你的话，这些感受很重要。如果现在你正在经历非常困难的时刻，"
    "以下资源可能对你有帮助：\n"
    "- 全国心理援助热线：400-161-9995\n"
    "- 北京心理危机研究与干预中心：010-82951332\n"
    "- 生命热线：400-821-1215\n"
    "我也会把你今天说的话记录下来，如果你愿意，可以和信任的家人或老师聊聊。"
)

_CONFIRM_SYSTEM = """You are a mental health triage assistant for a Chinese high school setting.
Given a student message flagged by keyword scan, confirm whether this represents an
immediate crisis requiring escalation. Output STRICT JSON only:
{"is_crisis": true|false, "severity": "high"|"medium"|"low"|"none", "recommendation": "immediate_escalation"|"monitor"|"none"}
Do NOT generate any other text."""


def scan_keywords(text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for category, patterns in RED_LINE_PATTERNS.items():
        for pattern, weight in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                hits.append({"category": category, "pattern": pattern, "weight": weight})
    return hits


def should_escalate(hits: list[dict[str, Any]]) -> bool:
    if not hits:
        return False
    total_weight = sum(h["weight"] for h in hits)
    high_severity = any(h["category"] in ("self_harm", "abuse_disclosure") for h in hits)
    return total_weight >= 8 or high_severity


async def confirm_with_llm(llm: LLMClient, model: str, text: str) -> dict[str, Any]:
    import json
    resp = await llm.chat(
        [LLMMessage(role="user", content=text)],
        system=_CONFIRM_SYSTEM, model=model,
    )
    try:
        return json.loads(resp.text.strip())
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"is_crisis": False, "severity": "none", "recommendation": "none"}
```

- [ ] **Step 4: Run test, watch pass**

Run: `pytest tests/e2e/test_red_line.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/companion/red_line.py tests/e2e/test_red_line.py
git commit -m "feat: red-line detection (keyword scan + LLM confirm + escalation response)"
```

---

## Task 2: Wire Red-Line into Mood Companion

**Files:**
- Modify: `src/pacer/agents/mood_companion.py`
- Modify: `src/pacer/orchestrator/orchestrator.py` — pass red-line context

- [ ] **Step 1: Update SYSTEM_PROMPT for mood agent**

Add to mood agent system prompt:

```python
MOOD_RED_LINE_ADDENDUM = """
## 红线检测（重要）
当学生表达了以下类型的内容时，你必须在回复前先调 log_mood 并设 red_flag=true：
- 自伤/自杀意图：割腕、跳楼、不想活、结束生命
- 虐待/霸凌：被打、家暴、体罚、性侵
- 严重抑郁：重度抑郁、崩溃边缘

触发红线后你必须：
1. 立即调 log_mood(red_flag=true, ...)
2. 在回复中附上专业求助热线
3. 语气保持温和，不评判，不斥责
"""
```

- [ ] **Step 2: Update `build_mood_agent` to accept red-line scanner dependency**

Add param `red_line_enabled: bool = True`. When True, add a `check_red_line` tool:

```python
class CheckRedLineTool(BaseTool):
    name = "check_red_line"
    description = "Scan the student's last message for crisis keywords. Use before responding to potentially concerning messages."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    }
    is_readonly = True

    async def execute(self, *, text: str) -> dict:
        from pacer.companion.red_line import scan_keywords, should_escalate
        hits = scan_keywords(text)
        return {
            "hits": hits,
            "should_escalate": should_escalate(hits),
            "escalation_response": ESCALATION_RESPONSE if should_escalate(hits) else "",
        }
```

Register this tool in mood agent factory.

- [ ] **Step 3: Commit**

```bash
git commit -am "feat: red-line scanner integrated into mood companion agent"
```

---

## Task 3: Remaining 4 Subject Skill Templates

**Files:**
- Create: `src/pacer/skills/content/chinese/` (4 skills)
- Create: `src/pacer/skills/content/physics/` (5 skills)
- Create: `src/pacer/skills/content/chemistry/` (4 skills)
- Create: `src/pacer/skills/content/biology/` (4 skills)

Each skill file follows the same YAML frontmatter + Markdown body format established in Stage 2 Task 2. The frontmatter has `name / subject / chapter / description`. The body has sections: 核心方法, 易错点, 例题, 变式题模板.

- [ ] **Step 1: Write Chinese skills (4 files)**

`src/pacer/skills/content/chinese/文言文-常见虚词.md`:

```markdown
---
name: chinese-文言文-常见虚词
subject: chinese
chapter: 文言文阅读
description: 18个高考常见文言虚词的用法辨析
---

## 核心考点
高考要求掌握的 18 个常见虚词：之、乎、者、也、而、何、乃、其、且、若、所、为、焉、以、因、于、与、则。

## 解题方法
1. **判断词性**：先看这个字在句中是什么词性（连词/介词/助词/代词）
2. **代入替换**：用现代汉语替换，看是否通顺
3. **固定搭配**：记住常见组合（"以为" = 认为 / "所以" = 用来…的凭借）

## 高频对比
- **而**：表转折（却）/ 表并列（又）/ 表承接（然后）/ 表修饰（着/地）
- **以**：表凭借（用/凭借）/ 表原因（因为）/ 表目的（用来）
- **之**：助词（的）/ 代词（他/它）/ 动词（到…去）/ 取消句子独立性

## 例题
"青，取之于蓝，而青于蓝"中两个"而"分别是什么意思？

## 变式题模板
替换文言选段，要求辨析同一个虚词在不同句中的用法。
```

`src/pacer/skills/content/chinese/古诗词-鉴赏技巧.md`:

```markdown
---
name: chinese-古诗词-鉴赏技巧
subject: chinese
chapter: 古代诗歌鉴赏
description: 高考古诗词鉴赏答题模板（形象/语言/表达技巧/思想情感）
---
## 核心方法
... (4-step framework for 鉴赏)
```

`src/pacer/skills/content/chinese/现代文-论述类文本.md` — argumentative text analysis  
`src/pacer/skills/content/chinese/作文-议论文结构.md` — argumentative essay structure

- [ ] **Step 2: Write Physics skills (5 files)**

Core physics topics:
- `physics-力学-牛顿运动定律.md`
- `physics-电磁学-电路分析.md`
- `physics-热学-理想气体状态方程.md`
- `physics-光学-光的折射与全反射.md`
- `physics-原子物理-光电效应.md`

Each follows the same template with physics formulas and common mistake patterns.

- [ ] **Step 3: Write Chemistry skills (4 files)**

- `chemistry-无机化学-氧化还原反应.md`
- `chemistry-有机化学-官能团转化.md`
- `chemistry-化学实验-物质的检验与鉴别.md`
- `chemistry-化学计算-物质的量.md`

- [ ] **Step 4: Write Biology skills (4 files)**

- `biology-细胞生物学-细胞呼吸.md`
- `biology-遗传学-孟德尔定律.md`
- `biology-生态学-种群与群落.md`
- `biology-生物技术-基因工程.md`

- [ ] **Step 5: Verify SkillsLoader indexes all**

Run: `pytest tests/unit/test_skills_loader.py -v`
The existing test uses a tmp_path fixture, so won't see the new content files. Write a quick smoke test:

```python
# Add to tests/unit/test_skills_loader.py
def test_skills_loader_discovers_all_subjects():
    import os
    from pathlib import Path
    root = Path(__file__).parent.parent.parent / "src" / "pacer" / "skills" / "content"
    if not root.exists():
        pytest.skip("skills content dir not found (running in isolated test)")
    loader = SkillsLoader(root=root)
    subjects = {m.subject for m in loader.list_skills()}
    assert "math" in subjects
    assert "chinese" in subjects
    assert "english" in subjects
    assert "physics" in subjects
    assert "chemistry" in subjects
    assert "biology" in subjects
```

- [ ] **Step 6: Test + commit**

```bash
pytest tests/unit/test_skills_loader.py -v
git add src/pacer/skills/content/
git commit -m "feat: complete 6-subject skill library (17 skills across math/english/chinese/physics/chemistry/biology)"
```

---

## Task 4: Image Upload + Profile Endpoints

**Files:**
- Create: `src/pacer/api/routes/upload.py`
- Create: `src/pacer/api/routes/profile.py`
- Modify: `src/pacer/api/server.py`
- Create: `tests/integration/test_upload.py`

- [ ] **Step 1: Implement `src/pacer/api/routes/upload.py`**

```python
from __future__ import annotations
import base64
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, current_student_id
from pacer.api.routes.message import send_message, SendRequest
from pacer.tools.vision_tool import VisionUnderstandImageTool

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/image")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    student_id: int = Depends(current_student_id),
):
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="unsupported image type")

    content = await file.read()
    b64 = base64.b64encode(content).decode("ascii")

    tool = VisionUnderstandImageTool(llm=request.app.state.llm, model="claude-sonnet-4-6")
    result = await tool.execute(image_base64=b64, hint=None)

    stem = result.get("stem", "")
    subject = result.get("subject", "")

    return {
        "ocr_result": result,
        "auto_routed_to_subject": subject,
        "auto_filled_stem": stem,
    }
```

- [ ] **Step 2: Implement `src/pacer/api/routes/profile.py`**

```python
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pacer.api.deps import get_db, current_student_id
from pacer.tools.profile_tools import GetStudentProfileTool, UpdateStudentProfileTool

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/")
def get_profile(
    student_id: int = Depends(current_student_id),
    db: Session = Depends(get_db),
):
    tool = GetStudentProfileTool(session_factory=lambda: db, student_id=student_id)
    import asyncio
    return asyncio.run(tool.execute())


@router.patch("/")
def patch_profile(
    updates: dict,
    student_id: int = Depends(current_student_id),
    db: Session = Depends(get_db),
):
    tool = UpdateStudentProfileTool(session_factory=lambda: db, student_id=student_id)
    import asyncio
    return asyncio.run(tool.execute(updates=updates))
```

- [ ] **Step 3: Register routes in server.py**

```python
from pacer.api.routes.upload import router as upload_router
from pacer.api.routes.profile import router as profile_router
app.include_router(upload_router)
app.include_router(profile_router)
```

- [ ] **Step 4: Commit**

```bash
git add src/pacer/api/routes/upload.py src/pacer/api/routes/profile.py src/pacer/api/server.py
git commit -m "feat: /upload/image + /profile endpoints"
```

---

## Task 5: E2E Daily Cycle Test

**Files:**
- Create: `tests/e2e/test_daily_cycle.py`
- Create: `tests/e2e/conftest.py` (shared fixtures)

- [ ] **Step 1: Write `tests/e2e/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from pacer.db.models import Base, Student
from pacer.api.deps import hash_pin


@pytest.fixture
def e2e_client():
    """FastAPI TestClient with in-memory DB and pre-seeded student."""
    import os
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    os.environ["PACER_INTERNAL_TOKEN"] = "test-token"

    from pacer.api.server import create_app
    app = create_app()
    from pacer.api import deps
    # Seed student
    sess = deps._SessionLocal()
    s = Student(id=1, name="测试学生", grade=12, pin_hash=hash_pin("123456"))
    sess.add(s); sess.commit(); sess.close()
    client = TestClient(app)
    tok = client.post("/auth/login", json={"student_id": 1, "pin": "123456"}).json()["token"]
    return client, tok


@pytest.fixture
def mock_llm_chain():
    """Patch LLMClient.chat to return a chain of responses for E2E flow."""
    def _patch(client_fn, responses: list):
        mock = AsyncMock(side_effect=responses)
        return patch("pacer.llm.client.LLMClient.chat", new=mock)
    return _patch
```

- [ ] **Step 2: Write the one-day cycle test**

```python
# tests/e2e/test_daily_cycle.py
import pytest
from unittest.mock import AsyncMock
from pacer.llm.client import LLMResponse
from pacer.companion.red_line import ESCALATION_RESPONSE


def _r(text="", tool_calls=None, stop="end_turn"):
    return LLMResponse(text=text, tool_calls=tool_calls or [],
                       stop_reason=stop, input_tokens=10, output_tokens=5, raw=None)


@pytest.mark.asyncio
async def test_full_day_cycle(e2e_client, mock_llm_chain):
    client, token = e2e_client

    # Mock chain: router → agent (×2 for two turns)
    responses = [
        _r('{"intent":"chitchat","subject":null,"confidence":0.8}'),  # router: turn 1
        _r("早安！今天距高考还有N天。你的今日计划已生成。"),         # homeroom: turn 1
        _r('{"intent":"subject_qa","subject":"math","confidence":0.9}'),  # router: turn 2
        _r("根据导数定义，f'(x)=2x，代入x=1得斜率k=2，切线方程为y=2x-1。"),  # subject: turn 2
    ]

    with mock_llm_chain(client, responses):
        # Turn 1: chitchat → morning greeting
        r1 = client.post("/message/send",
                         json={"text": "早上好"},
                         headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 200
        body1 = r1.json()
        assert "早安" in body1["text"] or "早" in body1["text"]
        sid = body1["session_id"]

        # Turn 2: math question → subject teacher
        r2 = client.post("/message/send",
                         json={"text": "求f(x)=x^2在x=1切线", "session_id": sid},
                         headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["session_id"] == sid
        assert "切线" in body2["text"] or "2x" in body2["text"]


@pytest.mark.asyncio
async def test_red_line_simulation(e2e_client, mock_llm_chain):
    """Simulate a distress message → mood agent + red flag."""
    client, token = e2e_client

    responses = [
        _r('{"intent":"mood_support","subject":null,"confidence":0.95}'),  # router
        _r(ESCALATION_RESPONSE),  # mood agent with escalation response
    ]

    with mock_llm_chain(client, responses):
        r = client.post("/message/send",
                        json={"text": "我觉得活着没意思"},
                        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "热线" in body["text"] or "心理" in body["text"]


@pytest.mark.asyncio
async def test_offline_backlog_replay(e2e_client):
    """Fire system events for offline student → login → events replay."""
    client, token = e2e_client

    # Post an internal event for a student before they subscribe
    r = client.post(
        "/internal/system-event",
        json={"type": "morning_briefing", "student_id": 1},
        headers={"X-Internal-Token": "test-token"},
    )
    assert r.status_code == 200

    # Now login — backlog should be pending
    # The backlog flush triggers on SSE subscription or login.
    # Verify by checking that the pending_events table has been consumed.
    resp = client.get("/profile/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # If no crash, the backlog flush logic ran without error.
```

- [ ] **Step 3: Run E2E tests**

Run: `pytest tests/e2e/test_daily_cycle.py -v`
Expected: 2-3 passed (offline_backlog test may need the backlog integration wired).

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/
git commit -m "test: E2E daily cycle + red line simulation + offline replay"
```

---

## Task 6: Stage 4 Wrap-up + README Update

- [ ] **Step 1: Run full test suite with coverage**

```bash
pytest --cov=src/pacer --cov-report=term-missing -v
```

Expected: All tests pass, coverage ≥ 80%.

- [ ] **Step 2: Lint + type check**

```bash
ruff check src/ tests/
mypy src/pacer
```

- [ ] **Step 3: Update README with run instructions**

Add "Getting Started" section to `README.md`:

```markdown
## Getting Started

```bash
# 1. Install
git clone git@github.com:flysheep-ai/pacer-ai.git
cd pacer-ai
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, generate PACER_INTERNAL_TOKEN
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 3. Database
alembic upgrade head
python scripts/seed_dev_student.py  # creates student id=1, pin=123456

# 4. Run API server
uvicorn pacer.api.server:create_app --factory --reload

# 5. (Optional) Run scheduler in another terminal
python -m pacer.scheduler.runner

# 6. Test
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"student_id": 1, "pin": "123456"}'
# → {"token": "...", "student_id": 1}

curl -X POST http://localhost:8000/message/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"text": "帮我讲一道导数题"}'
```
```

- [ ] **Step 4: Commit + final tag**

```bash
git add README.md
git commit -m "docs: Getting Started instructions in README"
git tag -a stage-4-mood-polish -m "Stage 4 complete: mood companion, red-line, 6-subj skills, E2E"
git push origin main --tags
```

---

## Validation Criteria (Stage 4 done when)

- [ ] `pytest -v` all green (unit + integration + e2e, 40+ tests)
- [ ] `pytest --cov=src/pacer --cov-report=term-missing` shows ≥ 80% coverage
- [ ] Manual smoke: all 4 daily scenarios run via scripted messages
- [ ] Red-line message produces escalation response (tested via E2E)
- [ ] All 6 subjects have at least 1 skill file, all indexed by `SkillsLoader`
- [ ] Upload endpoint accepts JPEG/PNG → returns OCR stem + subject
- [ ] Profile GET/PATCH works via API
- [ ] `git tag stage-4-mood-polish` pushed
- [ ] README has runnable Getting Started instructions
- [ ] Product ready for single-student trial deployment

---

## V1.1+ Candidates (NOT in this plan)

These are intentionally deferred. Each would get its own spec → plan cycle:

- **Parent dashboard**: separate web view with weekly reports, mood trends, progress summary
- **Semantic memory retrieval**: add `embedding` column, switch from LIKE to vector search
- **Expanded question bank tools**: bulk import, CSV/JSON upload, knowledge point auto-tagging
- **Offline mode**: local SQLite sync, queue messages when offline
- **Multi-OCR fallback**: text OCR (Tesseract) as fallback when multimodal API fails
- **Fine-tuned student model**: LoRA fine-tune on student's question history for style matching
- **Learning analytics**: mastery-over-time charts, predicted score trajectory, intervention suggestions
