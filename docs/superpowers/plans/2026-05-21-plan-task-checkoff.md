# Plan Task Check-off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every task inside `Plan.tasks_json` checkbox-toggleable from the frontend; ensure homeroom briefing and daily report can read real completion rates.

**Architecture:** Each task gains a stable uuid `id` and a boolean `done`. `CreatePlanTool` mints these at write time; a one-shot script back-fills legacy rows. A new `PATCH /plans/{plan_id}/tasks/{task_id}` endpoint flips `done`. `PlanView.vue` renders a checkbox per task with optimistic update + rollback, plus a per-plan progress bar.

**Tech Stack:** FastAPI · SQLAlchemy · Vue 3 · vue-router · vitest · pytest

**Spec:** `docs/superpowers/specs/2026-05-21-feature-roadmap-design.md` § Iteration 1 / subproject #1

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/pacer/tools/plan_tools.py` | modify | `CreatePlanTool.execute` assigns uuid + `done=false` per task |
| `src/pacer/api/routes/resources.py` | modify | new `PATCH /plans/{plan_id}/tasks/{task_id}` endpoint |
| `scripts/backfill_task_ids.py` | create | one-shot script: legacy `tasks_json` rows get ids + `done=false` |
| `src/pacer/web-next/src/views/PlanView.vue` | modify | checkbox per task, progress bar, optimistic PATCH |
| `tests/unit/test_plan_tools_ids.py` | create | `CreatePlanTool` mints uuid + `done=false` |
| `tests/api/test_plan_checkoff.py` | create | PATCH endpoint happy path + 404 cases |
| `tests/unit/test_backfill_task_ids.py` | create | back-fill script is idempotent |

`companion/briefing.py::_summarize` and `companion/daily_report.py::_completion_str` already read `t.get("done")` — no change needed; they start reporting real numbers automatically once tasks carry `done`.

---

## Tasks

### Task 1: CreatePlanTool mints uuid + done=false per task

**Files:**
- Modify: `src/pacer/tools/plan_tools.py`
- Test: `tests/unit/test_plan_tools_ids.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_plan_tools_ids.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Student
from pacer.tools.plan_tools import CreatePlanTool


@pytest.fixture
def student_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        s.commit()
    return engine


@pytest.mark.asyncio
async def test_create_plan_assigns_uuid_and_done_false(student_session):
    engine = student_session
    tool = CreatePlanTool(session_factory=lambda: Session(engine), student_id=1)
    out = await tool.execute(type="daily", tasks=[
        {"subject": "math", "duration_min": 30},
        {"subject": "english", "duration_min": 20, "done": True},
    ])
    assert "plan_id" in out
    tasks = out["tasks"]
    assert len(tasks) == 2
    for t in tasks:
        assert isinstance(t.get("id"), str) and len(t["id"]) == 36
    assert tasks[0]["done"] is False
    # Explicit done=True from caller is preserved
    assert tasks[1]["done"] is True


@pytest.mark.asyncio
async def test_create_plan_preserves_caller_supplied_id(student_session):
    engine = student_session
    tool = CreatePlanTool(session_factory=lambda: Session(engine), student_id=1)
    out = await tool.execute(type="daily", tasks=[
        {"id": "fixed-id-1234", "subject": "math"},
    ])
    assert out["tasks"][0]["id"] == "fixed-id-1234"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/unit/test_plan_tools_ids.py -v
```

Expected: FAIL — tasks lack `id`/`done` fields.

- [ ] **Step 3: Modify `CreatePlanTool.execute`**

In `src/pacer/tools/plan_tools.py`, add `import uuid` near the top, then replace `CreatePlanTool.execute`:

```python
import uuid

# ... existing imports ...

class CreatePlanTool(StudentScopedTool):
    name = "create_plan"
    description = "Create a new study plan (daily or weekly)."
    parameters = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["daily", "weekly"]},
            "tasks": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["type", "tasks"],
    }
    is_readonly = False

    async def execute(self, *, type: str, tasks: list[dict]) -> dict:
        sess = self._session_factory()
        # Stamp every task with a stable id + explicit done flag so the
        # frontend can toggle individual rows. Caller-supplied id/done win.
        decorated = [
            {**t, "id": t.get("id") or str(uuid.uuid4()), "done": bool(t.get("done", False))}
            for t in tasks
        ]
        plan = Plan(
            student_id=self._student_id, date=datetime.now(timezone.utc),
            type=type, tasks_json=decorated, generated_by="homeroom",
        )
        sess.add(plan); sess.commit(); sess.refresh(plan)
        return {"plan_id": plan.id, "tasks": decorated}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/unit/test_plan_tools_ids.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/tools/plan_tools.py tests/unit/test_plan_tools_ids.py
git commit -m "feat(plan): assign uuid + done=false to every new plan task"
```

---

### Task 2: PATCH /plans/{plan_id}/tasks/{task_id} endpoint

**Files:**
- Modify: `src/pacer/api/routes/resources.py`
- Test: `tests/api/test_plan_checkoff.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_plan_checkoff.py`:

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.api import deps
from pacer.api.server import create_app
from pacer.db.models import Base, Plan, Student


def _auth(client: TestClient, sid: int = 1, pin: str = "123456") -> dict[str, str]:
    r = client.post("/auth/login", json={"student_id": sid, "pin": pin})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def client_with_plan(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    task_a = str(uuid.uuid4())
    task_b = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Plan(
            id=10, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[
                {"id": task_a, "subject": "math", "done": False},
                {"id": task_b, "subject": "english", "done": False},
            ],
            generated_by="homeroom",
        ))
        s.commit()
    return TestClient(create_app(database_url=url)), task_a, task_b


def test_patch_task_marks_done(client_with_plan):
    client, task_a, task_b = client_with_plan
    h = _auth(client)
    r = client.patch(f"/plans/10/tasks/{task_a}", json={"done": True}, headers=h)
    assert r.status_code == 204
    plan = client.get("/plans/10", headers=h).json()
    targets = {t["id"]: t["done"] for t in plan["tasks"]}
    assert targets[task_a] is True
    assert targets[task_b] is False


def test_patch_task_can_toggle_back_to_false(client_with_plan):
    client, task_a, _ = client_with_plan
    h = _auth(client)
    client.patch(f"/plans/10/tasks/{task_a}", json={"done": True}, headers=h)
    r = client.patch(f"/plans/10/tasks/{task_a}", json={"done": False}, headers=h)
    assert r.status_code == 204
    plan = client.get("/plans/10", headers=h).json()
    assert next(t for t in plan["tasks"] if t["id"] == task_a)["done"] is False


def test_patch_task_404_when_plan_owned_by_other_student(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    other_task = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash=deps.hash_pin("123456")))
        s.add(Student(id=2, name="B", grade=12, pin_hash=deps.hash_pin("000000")))
        s.add(Plan(
            id=20, student_id=2, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[{"id": other_task, "subject": "math", "done": False}],
            generated_by="homeroom",
        ))
        s.commit()
    client = TestClient(create_app(database_url=url))
    r = client.patch(f"/plans/20/tasks/{other_task}", json={"done": True}, headers=_auth(client))
    assert r.status_code == 404


def test_patch_task_404_unknown_task_id(client_with_plan):
    client, _, _ = client_with_plan
    r = client.patch(
        f"/plans/10/tasks/{uuid.uuid4()}",
        json={"done": True}, headers=_auth(client),
    )
    assert r.status_code == 404


def test_patch_task_requires_auth(client_with_plan):
    client, task_a, _ = client_with_plan
    r = client.patch(f"/plans/10/tasks/{task_a}", json={"done": True})
    assert r.status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/api/test_plan_checkoff.py -v
```

Expected: FAIL with 404/405 (endpoint not registered).

- [ ] **Step 3: Add endpoint to `src/pacer/api/routes/resources.py`**

Append below the existing `/plans/{pid}` GET handler:

```python
from pydantic import BaseModel


class TaskUpdateRequest(BaseModel):
    done: bool


@router.patch("/plans/{plan_id}/tasks/{task_id}", status_code=204)
def patch_plan_task(
    plan_id: int,
    task_id: str,
    req: TaskUpdateRequest,
    db: Session = Depends(get_db),
    student_id: int = Depends(current_student_id),
):
    p = db.query(Plan).filter_by(id=plan_id, student_id=student_id).first()
    if p is None:
        raise HTTPException(status_code=404, detail="plan not found")
    tasks = list(p.tasks_json or [])
    found = False
    for t in tasks:
        if isinstance(t, dict) and t.get("id") == task_id:
            t["done"] = req.done
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="task not found")
    # Reassign so SQLAlchemy detects the JSON column change.
    p.tasks_json = tasks
    db.commit()
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/api/test_plan_checkoff.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/api/routes/resources.py tests/api/test_plan_checkoff.py
git commit -m "feat(plan): PATCH /plans/{id}/tasks/{tid} toggles done"
```

---

### Task 3: One-shot back-fill script for legacy task ids

**Files:**
- Create: `scripts/backfill_task_ids.py`
- Test: `tests/unit/test_backfill_task_ids.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_backfill_task_ids.py`:

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.db.models import Base, Plan, Student
from scripts.backfill_task_ids import backfill_task_ids


def _setup(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return url, engine


def test_backfill_fills_missing_ids_and_done_defaults(tmp_path):
    url, engine = _setup(tmp_path)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        # Legacy tasks: no id, no done
        s.add(Plan(
            id=1, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[{"subject": "math"}, {"subject": "english", "done": True}],
            generated_by="homeroom",
        ))
        s.commit()
    n = backfill_task_ids(url)
    assert n == 2  # two tasks needed ids
    with Session(engine) as s:
        p = s.get(Plan, 1)
        for t in p.tasks_json:
            assert isinstance(t.get("id"), str) and len(t["id"]) == 36
        assert p.tasks_json[0]["done"] is False  # default added
        assert p.tasks_json[1]["done"] is True   # existing preserved


def test_backfill_is_idempotent(tmp_path):
    url, engine = _setup(tmp_path)
    existing_id = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        s.add(Plan(
            id=1, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=[{"id": existing_id, "subject": "math", "done": False}],
            generated_by="homeroom",
        ))
        s.commit()
    n = backfill_task_ids(url)
    assert n == 0
    with Session(engine) as s:
        assert s.get(Plan, 1).tasks_json[0]["id"] == existing_id


def test_backfill_skips_non_dict_entries(tmp_path):
    url, engine = _setup(tmp_path)
    with Session(engine) as s:
        s.add(Student(id=1, name="A", grade=12, pin_hash="x"))
        s.add(Plan(
            id=1, student_id=1, type="daily",
            date=datetime.now(timezone.utc),
            tasks_json=["bare string entry", {"subject": "math"}],
            generated_by="homeroom",
        ))
        s.commit()
    n = backfill_task_ids(url)
    assert n == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/unit/test_backfill_task_ids.py -v
```

Expected: FAIL — module `scripts.backfill_task_ids` doesn't exist.

- [ ] **Step 3: Create `scripts/backfill_task_ids.py`**

```python
"""One-shot back-fill: add uuid `id` + bool `done` to legacy Plan.tasks_json rows.

Idempotent — running it twice is a no-op on already-tagged tasks.

Usage:
    python scripts/backfill_task_ids.py
"""
from __future__ import annotations
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pacer.config import get_settings
from pacer.db.models import Plan


def backfill_task_ids(database_url: str | None = None) -> int:
    """Return the number of tasks that received a new id."""
    url = database_url or get_settings().database_url
    engine = create_engine(url)
    fixed = 0
    with Session(engine) as s:
        for p in s.query(Plan).all():
            tasks = list(p.tasks_json or [])
            mutated = False
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                if "id" not in t:
                    t["id"] = str(uuid.uuid4())
                    mutated = True
                    fixed += 1
                if "done" not in t:
                    t["done"] = False
                    mutated = True
            if mutated:
                p.tasks_json = tasks
        s.commit()
    return fixed


if __name__ == "__main__":
    print(f"backfilled {backfill_task_ids()} task(s)")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/unit/test_backfill_task_ids.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the back-fill against the dev DB**

```bash
python scripts/backfill_task_ids.py
```

Expected: prints `backfilled N task(s)` (N depends on legacy data; may be 0).

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_task_ids.py tests/unit/test_backfill_task_ids.py
git commit -m "feat(plan): one-shot back-fill for legacy task ids"
```

---

### Task 4: PlanView checkbox + progress UI

**Files:**
- Modify: `src/pacer/web-next/src/views/PlanView.vue`

(No frontend unit test in this task — `PlanView.vue` is presentational and the data layer is covered by the API tests in Task 2. If a regression surfaces we can add a vitest later.)

- [ ] **Step 1: Replace `src/pacer/web-next/src/views/PlanView.vue` entirely**

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

type Task = {
  id: string
  subject?: string
  duration_min?: number
  note?: string
  done?: boolean
}
type Plan = {
  id: number
  type: string
  tasks: Task[]
  feedback?: string
  date?: string
}

const plans = ref<Plan[]>([])
const loading = ref(true)

onMounted(async () => {
  try { const r = await apiFetch<{ items: Plan[] }>('/plans'); plans.value = r.items || [] }
  catch { /* leave empty */ }
  finally { loading.value = false }
})

function progress(p: Plan): { done: number; total: number; pct: number } {
  const total = p.tasks.length
  const done = p.tasks.filter(t => t.done).length
  return { done, total, pct: total === 0 ? 0 : Math.round((done / total) * 100) }
}

async function toggleTask(plan: Plan, task: Task): Promise<void> {
  if (!task.id) return  // legacy unmigrated row — backfill not yet run
  const before = task.done === true
  task.done = !before
  try {
    await apiFetch(`/plans/${plan.id}/tasks/${task.id}`, {
      method: 'PATCH',
      json: { done: task.done },
    })
  } catch {
    task.done = before
  }
}

function describe(t: Task): string {
  const parts: string[] = []
  if (t.subject) parts.push(t.subject)
  if (t.duration_min) parts.push(`${t.duration_min} 分钟`)
  if (t.note) parts.push(t.note)
  return parts.join(' · ') || '任务'
}
</script>

<template>
  <AppShell>
    <div class="page">
      <h1>学习计划</h1>
      <p v-if="loading" class="hint">翻阅中…</p>
      <p v-else-if="plans.length === 0" class="empty">今天还没有计划</p>
      <div v-for="p in plans" :key="p.id" class="card">
        <div class="head">
          <div class="type">{{ p.type === 'daily' ? '日计划' : '周计划' }}</div>
          <div class="progress">{{ progress(p).done }}/{{ progress(p).total }}</div>
        </div>
        <div class="bar"><div class="fill" :style="{ width: progress(p).pct + '%' }"></div></div>
        <ul class="tasks">
          <li v-for="t in p.tasks" :key="t.id ?? Math.random()" class="task" :class="{ done: t.done }">
            <label>
              <input type="checkbox" :checked="t.done === true" :disabled="!t.id" @change="toggleTask(p, t)" />
              <span>{{ describe(t) }}</span>
            </label>
          </li>
        </ul>
        <div v-if="p.feedback" class="feedback">{{ p.feedback }}</div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.page { max-width:720px; margin:0 auto; padding:var(--space-8) var(--space-6); }
h1 { font-family:var(--font-serif); font-size:24px; margin-bottom:var(--space-6); }
.hint,.empty { color:var(--ink-500); font-family:var(--font-serif); font-size:15px; text-align:center; padding:var(--space-12) 0; }
.card { background:var(--paper-1); border:1px solid var(--ink-300); border-radius:var(--radius-md); padding:var(--space-4); margin-bottom:var(--space-3); }
.head { display:flex; justify-content:space-between; align-items:baseline; }
.type { font-size:11px; color:var(--ink-500); text-transform:uppercase; letter-spacing:0.06em; }
.progress { font-size:12px; color:var(--ink-700); }
.bar { height:4px; background:var(--ink-300); border-radius:2px; margin:var(--space-2) 0 var(--space-3); overflow:hidden; }
.fill { height:100%; background:var(--ink-900); transition:width 0.2s; }
.tasks { list-style:none; padding:0; margin:0; }
.task { font-size:14px; color:var(--ink-900); padding:6px 0; }
.task label { display:flex; gap:var(--space-2); align-items:center; cursor:pointer; }
.task.done span { color:var(--ink-500); text-decoration:line-through; }
.feedback { font-size:13px; color:var(--ink-700); margin-top:var(--space-2); border-top:1px solid var(--ink-300); padding-top:var(--space-2); }
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

- [ ] **Step 4: Manual smoke test**

In one terminal:
```bash
uvicorn pacer.api.server:create_app --factory --reload --port 8001
```

In another:
```bash
cd src/pacer/web-next && pnpm dev
```

Open `http://localhost:5173`, log in, navigate to `/plan`. Toggle a checkbox, reload the page, confirm the state persists. (If no daily plan exists yet, create one through the chat: ask the homeroom agent "帮我列一下今天的计划".)

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/views/PlanView.vue
git commit -m "feat(plan-ui): checkbox + progress bar; optimistic PATCH"
```

---

### Task 5: Full regression + build

- [ ] **Step 1: Run the full Python test suite**

```bash
python -m pytest -q
```

Expected: all tests pass (previously 57 + new ones from this plan).

- [ ] **Step 2: Run the frontend type-check + build**

```bash
cd src/pacer/web-next && pnpm typecheck && pnpm build
```

Expected: both succeed.

- [ ] **Step 3: (No commit if all green — work is done.)**

---

## Definition of Done

- All Python tests pass.
- `pnpm typecheck` and `pnpm build` succeed.
- A toggled checkbox in `/plan` survives a page reload.
- `GET /plans` returns each task with `id: str` and `done: bool`.
- Morning briefing's "yesterday's completion" line shows real `done/total` instead of "未制定" (this is a side-effect — already-working consumer code reads the new field).
