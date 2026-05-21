# Mastery Visualization + KP Seeds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `knowledge_points` with ~200 entries across 6 subjects, then build a `/mastery` page showing per-subject averages, top-5 weak points, and click-to-review chat via `POST /mastery/start-review`.

**Architecture:** Data layer: YAML → seed script with stable hashing → upsert into `knowledge_points`. Backend: tweak `GET /mastery` to expose `knowledge_point_id`; add `POST /mastery/start-review` reusing `start_assistant_stream`; `SaveErrorRecordTool` gains best-effort async KP classifier. Frontend: `MasteryView.vue` with subject cards, progress bars, top-5-weak, `→` review buttons.

**Tech Stack:** Python (YAML stdlib PyYAML, hashlib, SQLAlchemy) · FastAPI · Vue 3 · vitest · pytest

**Spec:** `docs/superpowers/specs/2026-05-21-mastery-visualization-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `data/knowledge_points.yaml` | create | ~200 KP entries across 6 subjects |
| `scripts/seed_knowledge_points.py` | create | reads YAML, stable-id upsert, prereq resolution |
| `tests/unit/test_seed_kp.py` | create | stable-id determinism, upsert idempotency, prereq resolution |
| `pyproject.toml` | modify | add `pyyaml` to dev deps if missing |
| `src/pacer/api/routes/resources.py` | modify | add `knowledge_point_id` to `GET /mastery`; add `POST /mastery/start-review` |
| `src/pacer/tools/error_tools.py` | modify | `SaveErrorRecordTool` gains optional `llm` param + async KP auto-classifier |
| `src/pacer/agents/subject_teacher.py` | modify | pass `llm` to `SaveErrorRecordTool` constructor |
| `tests/api/test_mastery_start_review.py` | create | 202 + session, 404 unknown KP, 401 unauthenticated |
| `src/pacer/web-next/src/views/MasteryView.vue` | create | subject cards, top-5-weak, expand, `→` buttons |
| `src/pacer/web-next/src/router.ts` | modify | add `/mastery` route |
| `src/pacer/web-next/src/components/Sidebar.vue` | modify | add "学习掌握度" nav entry |

---

## Tasks

### Task 1: Generate KP YAML data file

**Files:**
- Create: `data/knowledge_points.yaml`

Data generation task. No code — prompt Claude 6 times (one per subject) and concatenate.

- [ ] **Step 1: Generate per-subject YAML with this prompt**

```
Generate ~35 knowledge points for the Gaokao subject "{subject}". Output ONLY valid YAML starting with the subject key "{key}".  Each entry:
- name: concise Chinese name (6-12 chars)
- chapter: broader chapter/section (e.g. "函数与导数", "文言文阅读")
- difficulty: 1-5 (1=easiest)
- prereqs: list of prerequisite names within SAME subject; [] if none
- exam_freq: 1-5 (5=most common)

Subjects: 数学(math), 语文(chinese), 英语(english), 物理(physics), 化学(chemistry), 生物(biology)
```

Concatenate all 6 outputs into `data/knowledge_points.yaml`.

- [ ] **Step 2: Quick manual scan**

Skim for:
- Wrong-subject entries (e.g. "导数应用" under "chinese")
- Missing prereqs (e.g. "复合函数求导" without prereq "基本导数公式")
- Chapter names that are nonsense

Fix inline. Don't validate every entry.

- [ ] **Step 3: Commit**

```bash
git add data/knowledge_points.yaml
git commit -m "data: seed ~200 knowledge points across 6 subjects"
```

---

### Task 2: Seed script (TDD)

**Files:**
- Create: `scripts/seed_knowledge_points.py`
- Create: `tests/unit/test_seed_kp.py`
- Possibly modify: `pyproject.toml` (if `pyyaml` missing)

- [ ] **Step 1: Check if `pyyaml` is available**

```bash
python -c "import yaml; print('ok')"
```

If it fails, add `"pyyaml>=6.0"` to `pyproject.toml` dev-deps and `pip install -e '.[dev]'`.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_seed_kp.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, KnowledgePoint
from scripts.seed_knowledge_points import (
    stable_id, seed_from_yaml, upsert_knowledge_point,
)


def test_stable_id_is_deterministic():
    a = stable_id("math", "集合的基本概念")
    b = stable_id("math", "集合的基本概念")
    assert a == b
    assert isinstance(a, int)
    assert 0 < a < 2**31


def test_stable_id_differs_by_subject():
    assert stable_id("math", "导数") != stable_id("physics", "导数")


def test_upsert_creates_new_row(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        upsert_knowledge_point(s, kp_name="集合", subject="math",
                               chapter="集合与函数", difficulty=2, exam_freq=3)
        s.commit()
    with Session(engine) as s:
        kp = s.query(KnowledgePoint).filter_by(subject="math", point_name="集合").first()
        assert kp is not None
        assert kp.chapter == "集合与函数"
        assert kp.difficulty == 2
        assert kp.exam_freq == 3


def test_upsert_updates_existing_row(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        upsert_knowledge_point(s, kp_name="集合", subject="math",
                               chapter="旧章节", difficulty=1, exam_freq=1)
        s.commit()
        first_id = s.query(KnowledgePoint).filter_by(
            subject="math", point_name="集合").first().id
    with Session(engine) as s:
        upsert_knowledge_point(s, kp_name="集合", subject="math",
                               chapter="集合与函数", difficulty=3, exam_freq=5)
        s.commit()
        kp = s.query(KnowledgePoint).filter_by(
            subject="math", point_name="集合").first()
        assert kp.id == first_id
        assert kp.difficulty == 3
        assert kp.exam_freq == 5


def test_seed_from_yaml_resolves_prereqs(tmp_path, monkeypatch, tmpdir):
    import yaml
    yaml_text = """
math:
  - name: 集合
    chapter: 集合
    difficulty: 1
    prereqs: []
    exam_freq: 1
  - name: 函数
    chapter: 函数
    difficulty: 2
    prereqs: [集合]
    exam_freq: 3
"""
    yaml_path = tmpdir / "test_kp.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_from_yaml(s, str(yaml_path))
        s.commit()
    with Session(engine) as s:
        kps = s.query(KnowledgePoint).filter_by(subject="math").all()
        assert len(kps) == 2
        fn = next(kp for kp in kps if kp.point_name == "函数")
        assert len(fn.prereq_ids) == 1
        jihe = next(kp for kp in kps if kp.point_name == "集合")
        assert fn.prereq_ids[0] == jihe.id
```

- [ ] **Step 3: Run test → fail**

```bash
python -m pytest tests/unit/test_seed_kp.py -v
```

Expected: FAIL (module not found).

- [ ] **Step 4: Create `scripts/seed_knowledge_points.py`**

```python
"""Seed knowledge_points from a YAML file. Idempotent — re-running upserts by stable id.

Usage:
    python scripts/seed_knowledge_points.py [path/to/knowledge_points.yaml]
"""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pacer.config import get_settings
from pacer.db.models import KnowledgePoint


def stable_id(subject: str, name: str) -> int:
    """Deterministic 31-bit integer id from (subject, name)."""
    digest = hashlib.md5(f"{subject}|{name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def upsert_knowledge_point(
    session: Session, *,
    kp_name: str, subject: str, chapter: str,
    difficulty: int, exam_freq: int | None,
    prereq_ids: list[int] | None = None,
) -> KnowledgePoint:
    kp_id = stable_id(subject, kp_name)
    existing = session.get(KnowledgePoint, kp_id)
    if existing is not None:
        existing.point_name = kp_name
        existing.subject = subject
        existing.chapter = chapter
        existing.difficulty = difficulty
        existing.exam_freq = exam_freq
        existing.prereq_ids = prereq_ids or []
        session.flush()
        return existing
    kp = KnowledgePoint(
        id=kp_id, point_name=kp_name, subject=subject,
        chapter=chapter, difficulty=difficulty,
        exam_freq=exam_freq, prereq_ids=prereq_ids or [],
    )
    session.add(kp)
    session.flush()
    return kp


def seed_from_yaml(session: Session, yaml_path: str) -> int:
    """Upsert all KPs from YAML. Returns count written."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    total = 0
    for subject_key, entries in data.items():
        kp_by_name: dict[str, KnowledgePoint] = {}
        for entry in entries:
            name = entry["name"]
            kp = upsert_knowledge_point(
                session, kp_name=name, subject=subject_key,
                chapter=entry.get("chapter", ""),
                difficulty=entry.get("difficulty", 3),
                exam_freq=entry.get("exam_freq"),
            )
            kp_by_name[name] = kp
            total += 1
        # Second pass: resolve prereqs by name → id
        for entry in entries:
            prereq_names = entry.get("prereqs") or []
            if not prereq_names:
                continue
            kp = kp_by_name[entry["name"]]
            resolved = [
                kp_by_name[n].id for n in prereq_names if n in kp_by_name
            ]
            if resolved and resolved != kp.prereq_ids:
                kp.prereq_ids = resolved
                session.flush()
    return total


def main() -> None:
    yaml_path = (
        sys.argv[1] if len(sys.argv) > 1
        else str(Path(__file__).parent.parent / "data" / "knowledge_points.yaml")
    )
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as s:
        n = seed_from_yaml(s, yaml_path)
        s.commit()
        print(f"seeded {n} knowledge point(s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests → pass**

```bash
python -m pytest tests/unit/test_seed_kp.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/seed_knowledge_points.py tests/unit/test_seed_kp.py
# if pyproject.toml was changed: git add pyproject.toml
git commit -m "feat(kp): seed script with stable-id upsert + prereq resolution"
```

---

### Task 3: Run seed against dev DB

Operational — no code.

- [ ] **Step 1: Verify empty baseline**

```bash
sqlite3 pacer.db "SELECT COUNT(*) FROM knowledge_points;"
```

Expected: `0`.

- [ ] **Step 2: Run seed**

```bash
python scripts/seed_knowledge_points.py
```

Expected: `seeded N knowledge point(s)` with N ≈ 200.

- [ ] **Step 3: Verify subject distribution**

```bash
sqlite3 pacer.db "SELECT subject, COUNT(*) FROM knowledge_points GROUP BY subject;"
```

Expected: 6 subjects, 30-40 each.

- [ ] **Step 4: Verify idempotency** — re-run, same N, no duplicates. No commit (DB is gitignored).

---

### Task 4: Add `knowledge_point_id` to `GET /mastery`

**Files:**
- Modify: `src/pacer/api/routes/resources.py`

The current `get_mastery` handler iterates `StudentMastery` rows and joins `KnowledgePoint` to get `point_name`. It doesn't include `knowledge_point_id` in the output. The frontend needs this to call `POST /mastery/start-review`.

- [ ] **Step 1: Read `get_mastery` — it's at `resources.py` lines 111-123. Add `"knowledge_point_id": m.knowledge_point_id` to the item dict.**

```python
@router.get("/mastery")
def get_mastery(db: Session = Depends(get_db), student_id: int = Depends(current_student_id)):
    items = db.query(StudentMastery).filter_by(student_id=student_id).all()
    result: dict[str, list[dict]] = {}
    for m in items:
        kp = db.query(KnowledgePoint).filter_by(id=m.knowledge_point_id).first()
        subject = kp.subject if kp else "未知"
        result.setdefault(subject, []).append({
            "knowledge_point_id": m.knowledge_point_id,  # ← added
            "point_name": kp.point_name if kp else "?",
            "mastery_score": m.mastery_score,
            "correct_count": m.correct_count,
            "wrong_count": m.wrong_count,
        })
    return result
```

- [ ] **Step 2: Full test suite — no regression expected**

```bash
python -m pytest -q
```

Expected: 78 passed (73 baseline + 5 from seed test).

- [ ] **Step 3: Commit**

```bash
git add src/pacer/api/routes/resources.py
git commit -m "feat(mastery): expose knowledge_point_id in GET /mastery"
```

---

### Task 5: SaveErrorRecordTool auto-classification

**Files:**
- Modify: `src/pacer/tools/error_tools.py`
- Modify: `src/pacer/agents/subject_teacher.py`

- [ ] **Step 1: Read `SaveErrorRecordTool` in `error_tools.py` — replace the class with this augmented version**

The `__init__` gains an optional `llm` param. After saving the record, it fires a best-effort async LLM call to classify the stem into 1-2 KP ids.

```python
import asyncio
import json
import logging

log = logging.getLogger("pacer.tools")


class SaveErrorRecordTool(StudentScopedTool):
    name = "save_error_record"
    description = "Persist an error record for the student."
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

    def __init__(self, session_factory, student_id, llm=None):
        super().__init__(session_factory, student_id)
        self._llm = llm

    async def execute(self, *, stem_text: str, user_answer: str, correct_answer: str,
                      error_type: str, source: str, question_id: int | None = None,
                      knowledge_point_ids: list[int] | None = None,
                      explanation_text: str = "", subject: str = "") -> dict:
        sess = self._session_factory()
        if question_id is None and subject:
            q = Question(subject=subject, stem=stem_text, answer=correct_answer,
                         knowledge_point_ids=knowledge_point_ids or [])
            sess.add(q); sess.flush(); question_id = q.id
        e = ErrorRecord(
            student_id=self._student_id, question_id=question_id,
            user_answer=user_answer, correct_answer=correct_answer,
            error_type=error_type, knowledge_point_ids=knowledge_point_ids or [],
            source=source, explanation_text=explanation_text,
        )
        sess.add(e); sess.commit(); sess.refresh(e)

        # Best-effort async KP auto-classification
        if self._llm is not None and subject:
            try:
                asyncio.create_task(_classify_kp(e.id, stem_text, subject, sess, self._llm))
            except RuntimeError:
                pass

        return {"error_id": e.id}
```

And add the standalone async helper function (outside the class, in the same file):

```python
async def _classify_kp(error_id: int, stem: str, subject: str, sess, llm) -> None:
    try:
        from pacer.db.models import KnowledgePoint
        from pacer.llm.client import LLMMessage
        kps = sess.query(KnowledgePoint).filter_by(subject=subject).all()
        if not kps:
            return
        kp_list = "\n".join(f"- id={kp.id} name={kp.point_name}" for kp in kps)
        prompt = (
            f"题目: {stem[:300]}\n"
            f"可用知识点:\n{kp_list}\n\n"
            f"请选出最相关的 1-2 个知识点 id，严格的 JSON 数组返回，如 [101, 204]。"
        )
        resp = await llm.chat(
            [LLMMessage(role="user", content=prompt)],
            system="你是一个学科分类助手。只输出 JSON 数组。",
        )
        ids = json.loads(resp.text.strip())
        if isinstance(ids, list) and len(ids) > 0:
            ids = [int(i) for i in ids if isinstance(i, (int, float))]
            if ids:
                e = sess.get(ErrorRecord, error_id)
                if e is not None:
                    e.knowledge_point_ids = ids
                    sess.commit()
    except Exception:
        log.debug("KP auto-classify failed for error %s", error_id, exc_info=True)
```

Remove unused imports that remain after the change (`asyncio`, `json`, `logging` were added; `LLMMessage` was already imported).

- [ ] **Step 2: Update `subject_teacher.py` to pass `llm` to `SaveErrorRecordTool`**

In `src/pacer/agents/subject_teacher.py`, change the `SaveErrorRecordTool` registration line from:

```python
reg.register(SaveErrorRecordTool(session_factory, student_id))
```

to:

```python
reg.register(SaveErrorRecordTool(session_factory, student_id, llm=llm))
```

- [ ] **Step 3: Run full suite → no regressions**

```bash
python -m pytest -q
```

Expected: 78 passed (no new tests; auto-classification is fire-and-forget).

- [ ] **Step 4: Commit**

```bash
git add src/pacer/tools/error_tools.py src/pacer/agents/subject_teacher.py
git commit -m "feat(errors): best-effort KP auto-classification on save"
```

---

### Task 6: POST /mastery/start-review endpoint (TDD)

**Files:**
- Modify: `src/pacer/api/routes/resources.py`
- Test: `tests/api/test_mastery_start_review.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_mastery_start_review.py`:

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
from pacer.db.models import Base, KnowledgePoint, Message, Student
from pacer.llm.client import LLMResponse


def _llm(text="ok"):
    return LLMResponse(
        text=text, tool_calls=[], stop_reason="end_turn",
        input_tokens=5, output_tokens=5, raw=None,
    )


@pytest.mark.asyncio
async def test_start_mastery_review_creates_session(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(KnowledgePoint(id=42, subject="math", chapter="函数",
               point_name="导数的几何意义", difficulty=3, prereq_ids=[]))
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
                "/mastery/start-review",
                json={"knowledge_point_id": 42},
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
        msgs = (s.query(Message).filter_by(session_id=session_id)
                 .order_by(Message.id).all())
        assert len(msgs) >= 2
        seed = msgs[0]
        assert seed.role == "user"
        assert "[复习知识点 #42]" in seed.content
        assert "导数的几何意义" in seed.content
        assert msgs[1].role == "assistant"


@pytest.mark.asyncio
async def test_start_mastery_review_404_unknown_kp(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.commit()
    app = create_app(database_url=url)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
    ) as ac:
        tok = (await ac.post(
            "/auth/login", json={"student_id": 1, "pin": "123456"},
        )).json()["token"]
        r = await ac.post(
            "/mastery/start-review",
            json={"knowledge_point_id": 99999},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_start_mastery_review_requires_auth(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    app = create_app(database_url=url)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
    ) as ac:
        r = await ac.post("/mastery/start-review", json={"knowledge_point_id": 1})
        assert r.status_code == 401
```

- [ ] **Step 2: Run → fail**

```bash
python -m pytest tests/api/test_mastery_start_review.py -v
```

Expected: FAIL (endpoint not registered).

- [ ] **Step 3: Add the endpoint**

In `src/pacer/api/routes/resources.py`, add `MasteryStartReviewRequest` near the other request models, and the endpoint at the bottom:

```python
class MasteryStartReviewRequest(BaseModel):
    knowledge_point_id: int


@router.post("/mastery/start-review", status_code=202)
async def start_mastery_review(
    req: MasteryStartReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    kp = db.get(KnowledgePoint, req.knowledge_point_id)
    if kp is None:
        raise HTTPException(status_code=404, detail="knowledge point not found")

    seed_text = (
        f"[复习知识点 #{kp.id}] {kp.subject} · {kp.point_name}\n"
        f"请帮我讲解这个知识点，并出几道练习题。"
    )

    store = SessionStore(db)
    chat = store.create_session(student_id=student_id)
    store.append_message(
        chat.id, role="user", agent=None, content=seed_text,
        metadata={"knowledge_point_id": kp.id},
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

- [ ] **Step 4: Run tests → pass**

```bash
python -m pytest tests/api/test_mastery_start_review.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/api/routes/resources.py tests/api/test_mastery_start_review.py
git commit -m "feat(mastery): POST /mastery/start-review for KP-directed chat"
```

---

### Task 7: MasteryView.vue frontend

**Files:**
- Create: `src/pacer/web-next/src/views/MasteryView.vue`

- [ ] **Step 1: Create `src/pacer/web-next/src/views/MasteryView.vue`**

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

type KP = {
  knowledge_point_id: number
  point_name: string
  mastery_score: number
  correct_count: number
  wrong_count: number
}
type MasteryData = Record<string, KP[]>

const SUBJECT_LABELS: Record<string, string> = {
  math: '数学', chinese: '语文', english: '英语',
  physics: '物理', chemistry: '化学', biology: '生物',
}

const data = ref<MasteryData | null>(null)
const loading = ref(true)
const expanded = ref<string | null>(null)
const reviewing = ref<number | null>(null)
const router = useRouter()

onMounted(async () => {
  try { data.value = await apiFetch<MasteryData>('/mastery') }
  catch { /* keep null */ }
  finally { loading.value = false }
})

const subjects = computed(() => {
  if (!data.value) return []
  return Object.entries(data.value).map(([subject, kps]) => {
    const total = kps.length
    const avg = total === 0 ? 0
      : kps.reduce((s, kp) => s + kp.mastery_score, 0) / total
    return {
      subject,
      label: SUBJECT_LABELS[subject] ?? subject,
      kps,
      avg: Math.round(avg * 100),
      total,
    }
  })
})

const top5Weak = computed(() => {
  if (!data.value) return []
  const all: (KP & { subject: string })[] = []
  for (const [subject, kps] of Object.entries(data.value)) {
    for (const kp of kps) {
      if (kp.correct_count + kp.wrong_count >= 1) {
        all.push({ ...kp, subject })
      }
    }
  }
  all.sort((a, b) => a.mastery_score - b.mastery_score)
  return all.slice(0, 5)
})

function toggleExpand(subject: string): void {
  expanded.value = expanded.value === subject ? null : subject
}

async function startReview(kp: KP & { subject: string }): Promise<void> {
  if (reviewing.value !== null) return
  reviewing.value = kp.knowledge_point_id
  try {
    const r = await apiFetch<{ session_id: number }>(
      '/mastery/start-review',
      { method: 'POST', json: { knowledge_point_id: kp.knowledge_point_id } },
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
      <h1>学习掌握度</h1>
      <p v-if="loading" class="hint">翻阅中…</p>
      <p v-else-if="subjects.length === 0" class="empty">
        还没有答题记录——去聊天里找老师练几道题吧
      </p>
      <template v-else>
        <div class="subject-grid">
          <button
            v-for="s in subjects" :key="s.subject"
            class="subject-card"
            :class="{ active: expanded === s.subject }"
            @click="toggleExpand(s.subject)"
          >
            <div class="subject-name">{{ s.label }}</div>
            <div class="subject-bar"><div class="subject-fill" :style="{ width: s.avg + '%' }" /></div>
            <div class="subject-pct">{{ s.avg }}%</div>
          </button>
        </div>

        <div v-if="top5Weak.length > 0" class="section">
          <h2>最弱 5 项</h2>
          <div
            v-for="kp in top5Weak" :key="kp.subject + kp.point_name"
            class="weak-row"
          >
            <span class="weak-label">{{ kp.point_name }} · {{ SUBJECT_LABELS[kp.subject] ?? kp.subject }}</span>
            <div class="weak-bar"><div class="weak-fill" :style="{ width: Math.round(kp.mastery_score * 100) + '%' }" /></div>
            <span class="weak-pct">{{ Math.round(kp.mastery_score * 100) }}%</span>
            <button
              class="review-btn"
              :disabled="reviewing === kp.knowledge_point_id"
              @click="startReview(kp)"
            >
              →
            </button>
          </div>
        </div>

        <div v-if="expanded" class="section">
          <h2>{{ SUBJECT_LABELS[expanded] ?? expanded }} 详情</h2>
          <div
            v-for="kp in data?.[expanded] ?? []"
            :key="kp.point_name"
            class="kp-row"
          >
            <span class="kp-name">{{ kp.point_name }}</span>
            <div class="kp-bar"><div class="kp-fill" :style="{ width: Math.round(kp.mastery_score * 100) + '%' }" /></div>
            <span class="kp-pct">{{ Math.round(kp.mastery_score * 100) }}%</span>
            <span class="kp-counts">{{ kp.correct_count }}/{{ kp.correct_count + kp.wrong_count }}</span>
          </div>
        </div>
      </template>
    </div>
  </AppShell>
</template>

<style scoped>
.page { max-width:960px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:28px; margin-bottom:var(--space-6); }
.hint, .empty { color:var(--ink-500); font-family:var(--font-serif); font-size:16px; text-align:center; padding:var(--space-12) 0; }

.subject-grid { display:flex; flex-wrap:wrap; gap:var(--space-3); margin-bottom:var(--space-6); }
.subject-card {
  flex:1 1 calc(33.333% - var(--space-3));
  min-width:160px;
  background:var(--paper-1); border:1px solid var(--ink-300);
  border-radius:var(--radius-md); padding:var(--space-4);
  cursor:pointer; text-align:left;
  transition: border-color var(--motion-fast);
}
.subject-card:hover, .subject-card.active { border-color:var(--ink-900); }
.subject-name { font-size:15px; font-weight:500; color:var(--ink-900); margin-bottom:var(--space-2); }
.subject-bar { height:6px; background:var(--ink-300); border-radius:3px; overflow:hidden; margin-bottom:var(--space-1); }
.subject-fill { height:100%; background:var(--ink-900); transition:width 0.3s; }
.subject-pct { font-size:13px; color:var(--ink-700); }

.section { margin-bottom:var(--space-6); }
.section h2 { font-family:var(--font-serif); font-size:18px; margin-bottom:var(--space-3); color:var(--ink-800); }

.weak-row { display:flex; align-items:center; gap:var(--space-3); padding:var(--space-2) 0; }
.weak-label { flex:1; font-size:14px; color:var(--ink-900); }
.weak-bar { width:120px; height:5px; background:var(--ink-300); border-radius:3px; overflow:hidden; flex-shrink:0; }
.weak-fill { height:100%; background:var(--ink-900); transition:width 0.3s; }
.weak-pct { font-size:13px; color:var(--ink-700); width:36px; text-align:right; flex-shrink:0; }
.review-btn {
  font-size:14px; width:28px; height:28px; border:1px solid var(--ink-500);
  background:var(--paper-0); color:var(--ink-700); border-radius:var(--radius-sm);
  cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center;
}
.review-btn:hover:not(:disabled) { background:var(--ink-900); color:var(--paper-0); }
.review-btn:disabled { opacity:0.3; cursor:wait; }

.kp-row { display:flex; align-items:center; gap:var(--space-3); padding:var(--space-2) 0; border-bottom:1px solid var(--ink-200); }
.kp-name { flex:1; font-size:14px; color:var(--ink-900); }
.kp-bar { width:120px; height:5px; background:var(--ink-300); border-radius:3px; overflow:hidden; flex-shrink:0; }
.kp-fill { height:100%; background:var(--ink-900); transition:width 0.3s; }
.kp-pct { font-size:13px; color:var(--ink-700); width:36px; text-align:right; }
.kp-counts { font-size:12px; color:var(--ink-500); width:48px; text-align:right; }
</style>
```

- [ ] **Step 2: Run typecheck**

```bash
cd src/pacer/web-next && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 3: Run frontend tests — verify no regression**

```bash
cd src/pacer/web-next && pnpm test
```

Expected: existing tests pass (no new test for MasteryView).

---

### Task 8: Router + Sidebar entries

**Files:**
- Modify: `src/pacer/web-next/src/router.ts`
- Modify: `src/pacer/web-next/src/components/Sidebar.vue`

- [ ] **Step 1: Add `/mastery` route**

In `router.ts`, add after the `/plan` route:

```ts
{ path: '/mastery', name: 'mastery', component: () => import('@/views/MasteryView.vue') },
```

- [ ] **Step 2: Add sidebar entry**

In `Sidebar.vue`, add after the "学习计划" button:

```html
<button class="row" type="button" @click="router.push('/mastery')">学习掌握度</button>
```

- [ ] **Step 3: Verify typecheck + build**

```bash
cd src/pacer/web-next && pnpm typecheck && pnpm build
```

Expected: both succeed.

- [ ] **Step 4: Commit**

```bash
git add src/pacer/web-next/src/router.ts src/pacer/web-next/src/components/Sidebar.vue
git commit -m "feat(mastery-ui): add /mastery route + sidebar entry"
```

---

### Task 9: Full regression + build

- [ ] **Step 1: Full Python test suite**

```bash
python -m pytest -q
```

Expected: 81 passed (73 baseline + 5 seed_kp + 3 mastery_start_review).

- [ ] **Step 2: Frontend typecheck + build**

```bash
cd src/pacer/web-next && pnpm typecheck && pnpm build
```

Expected: both succeed.

- [ ] **Step 3: Quick manual smoke**

```bash
python scripts/seed_knowledge_points.py
```

Then open `http://localhost:5173/mastery` in the browser. Expect to see the empty state ("no records yet"). Create a `StudentMastery` record manually to verify the card rendering:

```bash
sqlite3 pacer.db "INSERT INTO student_mastery (student_id, knowledge_point_id, mastery_score, correct_count, wrong_count) VALUES (1, 42, 0.65, 6, 3);"
```

Refresh the page → should show "数学" card with 65% average and one KP listed.

- [ ] **Step 4: No commit if all green — done.**

---

## Definition of Done

- `knowledge_points` holds ≥ 180 rows after seeding.
- `GET /mastery` returns `knowledge_point_id` per item.
- `POST /mastery/start-review` creates a session with `[复习知识点 #N]` seed message.
- `SaveErrorRecordTool` auto-classifies KP ids when an `llm` is available; passes through silently when not.
- `/mastery` page renders subject cards + top-5-weak + expand-on-click.
- `→` button on a weak point creates a review session and navigates.
- All existing tests green; new tests pass; `pnpm typecheck` + `pnpm build` succeed.
