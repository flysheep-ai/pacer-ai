# Mastery Visualization + Knowledge Point Seeds Design

**Status:** design / pending implementation
**Date:** 2026-05-21
**Spec:** `docs/superpowers/specs/2026-05-21-feature-roadmap-design.md` § Iteration 2 / subprojects #3 + #4

---

## Overview

Two tightly-coupled subprojects shipped as one feature:

1. **Knowledge-point seed data:** populate `knowledge_points` with ~200 points across 6 subjects, each with prerequisites and exam frequency. This gives the mastery system a vocabulary — without it every KP is `?` or `未知`.

2. **Mastery visualization:** a new `/mastery` page showing subject cards with average mastery, a "top 5 weak points" highlight, and inline expansion to per-KP progress bars. Clicking a weak KP opens a review chat.

---

## Locked design decisions

- **KP scale:** ~30–40 per subject, ~200 total. LLM generates the YAML in one pass; a human skims for obvious subject/chapter misclassifications.
- **ID scheme:** `hash(subject + name) % 2**31` — stable across re-runs, no sequence churn.
- **Seed loader:** `scripts/seed_knowledge_points.py` reads `data/knowledge_points.yaml`, resolves prereq names → ids, upserts by id.
- **Error auto-classification:** `SaveErrorRecordTool` fires a best-effort async LLM call (router model) to classify the stem into 1–2 KP ids. Failures are logged and do not block the save.
- **Mastery page layout:** subject cards + progress bars, no chart library. Expand-on-click for per-KP details. Top 5 weakest KPs pinned at the top.
- **KP → chat:** `POST /mastery/start-review` creates a session with a `[复习知识点 #N] …` seed message and returns the session id; the frontend navigates to `/chat/{sid}`. The subject teacher treats this like the error-review protocol.

---

## Component designs

### Part 1 — Knowledge point data

**File:** `data/knowledge_points.yaml`

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
chinese:
  - name: 文言文实词辨析
    chapter: 文言文阅读
    difficulty: 3
    prereqs: []
    exam_freq: 5
# ... ~200 entries across 6 subjects
```

**Generator prompt** (for Claude): "Generate ~35 knowledge points for {subject}. Format YAML with name/chapter/difficulty(1-5)/prereqs(list of names)/exam_freq(1-5). Cover the standard exam syllabus. Prerequisites must reference other names in the same subject."

**Seed script:** `scripts/seed_knowledge_points.py`

- `stable_id(subject, name) -> int` via `hashlib.md5(f"{subject}|{name}".encode()).digest()` truncated to 31 bits
- Load YAML → for each subject, upsert points with stable ids into `knowledge_points`
- Second pass: resolve `prereqs` name strings → `prereq_ids` list (integer array column)
- Idempotent: re-running updates existing rows, adds new ones, doesn't duplicate

**Error auto-classification** (in `tools/error_tools.py::SaveErrorRecordTool`):

After saving the `ErrorRecord`, spawn an async task (or inline after the commit if latency is acceptable): call the router model with a short prompt listing nearby KP names for the detected subject + the error stem → return 1–2 KP ids → update the `ErrorRecord.knowledge_point_ids` column. Best-effort; `try/except` with a logged warning on failure.

### Part 2 — Backend

**`POST /mastery/start-review`** (new endpoint in `resources.py`):

```
POST /mastery/start-review
Body: {"knowledge_point_id": int}
Auth: Bearer token

→ 202 {"session_id": int, "assistant_message_id": int}
```

- Look up the `KnowledgePoint` by id.
- Create a `ChatSession`.
- Append a seed user message: `[复习知识点 #{id}] {subject} - {point_name}。请帮我讲解并出几道练习题。`
- Create a placeholder assistant message.
- Call `start_assistant_stream(...)` to spawn the background streaming task.
- Return 202 + session id.

**Existing `/mastery` GET:** returned data is already correct shape. No changes needed.

**Side effect:** `SaveErrorRecordTool` gains the KP auto-classifier (described above). Without this, `student_mastery` stays empty and the mastery page shows "no data yet."

### Part 3 — Frontend

**New route + sidebar entry:**

- `/mastery` route → lazy-import `views/MasteryView.vue`
- Sidebar "页面" section: add `router.push('/mastery')` button labeled "学习掌握度"

**`views/MasteryView.vue`** (new file):

States:

1. **Loading:** "翻阅中…" (matches PlanView/ErrorsView)
2. **Empty:** "还没有答题记录——去聊天里找老师练几道题吧" (actionable hint)
3. **Data present:**

```
┌──────────────────────────────────────┐
│  学习掌握度                           │
│                                      │
│  六学科卡片（flex-wrap, 一行3个）     │
│  ┌────────┐ ┌────────┐ ┌────────┐   │
│  │ 数学   │ │ 语文   │ │ 英语   │   │
│  │ ████░  │ │ ███░░  │ │ ██░░░  │   │
│  │ 72%    │ │ 58%    │ │ 41%    │   │
│  └────────┘ └────────┘ └────────┘   │
│  ┌────────┐ ┌────────┐ ┌────────┐   │
│  │ 物理   │ │ 化学   │ │ 生物   │    │
│  │ ███░░  │ │ ░░░░░  │ │ ████░  │   │
│  │ 55%    │ │ 0%     │ │ 68%    │   │
│  └────────┘ └────────┘ └────────┘   │
│                                      │
│  ⚠ 最弱 5 项（至少1次作答）           │
│  ┌──────────────────────────────┐    │
│  │ ● 导数应用 · 数学   ██░░░ 35% →│   │
│  │ ● 文言虚词 · 语文   ██░░░ 40% →│   │
│  │ ● 虚拟语气 · 英语   ██░░░ 42% →│   │
│  │ ● 解析几何 · 数学   ██░░░ 44% →│   │
│  │ ● 电化学 · 化学     ██░░░ 45% →│   │
│  └──────────────────────────────┘    │
│                                      │
│  ▼ 数学（点击后展开）                 │
│  ┌──────────────────────────────┐    │
│  │ 集合基本概念  ██████████ 90%  │    │
│  │ 函数定义域    ██████░░░░ 65%  │    │
│  │ 导数应用      ███░░░░░░░ 35%  │    │
│  │ ...                          │    │
│  └──────────────────────────────┘    │
└──────────────────────────────────────┘
```

- `onMounted`: `GET /mastery` → compute per-subject averages; sort KPs within each subject by score; derive top-5-weakest across all subjects (filter: `correct_count + wrong_count >= 1`).
- Subject card click: toggles `expanded` state; below the cards render that subject's full KP list with progress bars.
- Weak-point `→` click: `POST /mastery/start-review {knowledge_point_id}` → `router.push(\`/chat/${session_id}\`)`.
- All progress bars pure CSS `div` with dynamic `width` — no chart library.
- Styles use the existing design system variables (`--paper-*`, `--ink-*`, `--space-*`, `--radius-sm/md`, `--font-serif`).

---

## Testing

- `tests/unit/test_seed_kp.py`: stable_id is deterministic, upsert doesn't duplicate, prereq resolution handles missing refs gracefully.
- `tests/api/test_mastery_start_review.py`: happy path (valid KP → 202 + session), 404 for unknown KP, 401 unauthenticated. Same pattern as `tests/api/test_start_review.py`.
- No component test for `MasteryView.vue` (presentational; data layer covered by API tests).

---

## Out of scope

- Radar chart / bar charts / Chart.js integration.
- Historical mastery progression over time (that's weekly report territory).
- Adaptive exercise recommendation ("do these 3 problems for KP X") — needs a question bank.
- KP editing UI (manual CRUD — for now the YAML is the source of truth and re-running the seed script is the update path).
- Parent/teacher dashboard.

---

## Acceptance

- `knowledge_points` table holds ≥ 180 rows after seeding.
- `GET /mastery` returns grouped data when `student_mastery` has rows.
- The `/mastery` page renders subject cards with average percentages when data exists; shows the "no data yet" message when empty.
- Clicking a weak-point `→` creates a session whose seed message references the KP and navigates to `/chat/{sid}`.
- `SaveErrorRecordTool` auto-classifies new errors into KP ids (best-effort).
- All existing 73 tests remain green; new tests pass.
- `pnpm typecheck` + `pnpm build` succeed.
