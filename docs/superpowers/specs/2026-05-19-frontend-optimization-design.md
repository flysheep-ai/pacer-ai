# Frontend Optimization — Design Spec

- **Date**: 2026-05-19
- **Scope**: Full rewrite of `src/pacer/web/` plus targeted backend additions
- **Status**: Approved (pending implementation plan)

## Goal

Rewrite the pacer-ai web frontend as a modern Vue 3 SPA with a "静谧东方文人感"
visual language, while extending the backend with the endpoints and streaming
protocol needed to support real-time conversations, session history, error
review, and study plan views.

The current frontend (vanilla HTML + global JS + inline `onclick`) has reached
its iteration ceiling: state is tangled, visual polish is generic, no support
for streaming, no session history, no rich Markdown.

## Non-Goals

- Mobile-first redesign (responsive yes, but desktop is the primary target)
- Multi-language UI (中文 only)
- PWA / offline-first behavior beyond optimistic shell rendering
- Replacing the orchestrator architecture — only its streaming surface
- Real-time multi-device sync of session state

## §1 Architecture

### Stack

- **Frontend**: Vue 3 with `<script setup>`, Composition API, Pinia (state),
  Vue Router 4, Vite 5, TypeScript (strict mode)
- **Rendering**: markdown-it + KaTeX + highlight.js, lazy-loaded
- **Tooling**: ESLint + Prettier, Vitest (unit tests)
- **Backend**: FastAPI preserved; new GET endpoints; SSE protocol extended
  with `assistant_start` / `assistant_delta` / `assistant_done` events

### Directory layout

```
src/pacer/
  web/                      # legacy frontend, deleted after parity is reached
  web-next/                 # new frontend source
    src/
      api/                  # fetch + SSE client
      stores/               # pinia stores: auth, session, chat, ui
      composables/          # useStream, useAutoScroll, useToast, ...
      components/           # reusable components (Bubble, Composer, Sidebar, ...)
      views/                # routed pages (Login, Chat, Profile, Errors, Plan)
      styles/               # tokens.css + global styles
      router.ts
      main.ts
    index.html
    vite.config.ts
    package.json
```

### Build & integration

- **Dev**: `vite dev` runs on `http://localhost:5173`. `vite.config.ts`
  proxies `/auth /message /events /upload /profile /sessions /errors /plans /mastery`
  to FastAPI at `http://localhost:8000`.
- **Prod**: `vite build` writes to `src/pacer/web-next/dist/`. `create_app`
  detects the dist directory and mounts `dist/assets` at `/assets`, returns
  `dist/index.html` for the root and any unmatched path (SPA fallback).
- **Migration window**: `web-next/` and `web/` coexist. FastAPI prefers
  `web-next` when its dist exists. Legacy `web/` remains as a rollback anchor
  until all phases land, then is deleted in a single commit.

### Frontend / backend responsibilities

- **Frontend**: UI, routing, state, Markdown rendering, streaming delta
  accumulation, all interactions
- **Backend**: business logic, SSE stream, new sessions/errors/plans GETs.
  No server-side template rendering.

### Key trade-offs

- `web-next/` parallel rather than in-place replace: instant rollback,
  cleaner git diff during migration
- SSE delta rather than WebSocket: reuses existing `EventBus`, one-way
  stream is sufficient for chat
- Pinia rather than prop drilling: session state needs to be shared between
  sidebar, chat view, and profile / errors / plan views

## §2 Visual Design Language

**Metaphor**: paper, ink, inkstone, seal. The interface is unrolled rice paper.
Text is ink. Accents are vermilion or grey-cyan. Dividers are pale creases.
**Restraint over decoration.**

### Color tokens

**Light (宣纸)**
```
--paper-0:     #F7F3EA   /* primary bg, rice paper */
--paper-1:     #F1ECDF   /* secondary bg */
--paper-2:     #E9E2D2   /* dividers, hover */
--ink-900:     #1C1815   /* primary text, dark ink */
--ink-700:     #4A413A   /* secondary text */
--ink-500:     #8A7F70   /* tertiary, placeholder */
--ink-300:     #C9BFAE   /* borders, disabled icons */
--accent:      #6B8A92   /* grey-cyan, primary accent */
--accent-soft: #DDE6E8   /* accent-tinted background */
--seal:        #A33E2A   /* vermilion, brand + danger */
--moss:        #5C7A4F   /* moss green, success */
```

**Dark (夜读)**
```
--paper-0:     #1A1815
--paper-1:     #221F1B
--paper-2:     #2B2722
--ink-900:     #E8DFCE   /* warm white, never cold grey */
--ink-700:     #B5AC9B
--ink-500:     #80776A
--ink-300:     #4A433B
--accent:      #88A8B0
--accent-soft: #2A3A3F
--seal:        #C76050
--moss:        #7C9870
```

No pure black or white. All neutrals carry a warm (yellow-ochre) tint.

### Typography

```
--font-serif:  "Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", serif;
--font-sans:   "Source Han Sans SC", "Noto Sans SC", -apple-system, "PingFang SC", sans-serif;
--font-mono:   "JetBrains Mono", "SF Mono", "Cascadia Code", monospace;
```

- Headings, brand mark, large empty-state text → serif
- Body, buttons, inputs → sans (for legibility in long prose)
- Code, numbers → mono
- CJK fallback chain prioritizes PingFang / 思源, never Helvetica

### Scale

```
--space: 4/8/12/16/20/24/32/48/64   /* 8-step scale */
--radius-xs: 2px
--radius-sm: 4px
--radius-md: 8px
--radius-lg: 12px                   /* hard cap, avoid ChatGPT-style large radii */
--shadow: none                      /* default zero shadow; use 1px ink-300 borders */
--shadow-hover: 0 1px 2px rgba(28,24,21,0.05)
--motion-fast: 160ms cubic-bezier(.4,0,.2,1)
--motion-mid:  240ms cubic-bezier(.4,0,.2,1)
--motion-slow: 380ms cubic-bezier(.4,0,.2,1)
```

### Decorative elements (sparingly)

- **Brand mark**: `pacer` in serif top-left, with a small vermilion square
  ("印") beside it — not a circular dot
- **Dividers**: 1px `--ink-300` over `--paper-0`, reads as a paper crease
- **Empty states**: one serif headline + one small line + generous margin.
  No illustrations, no emoji, no decorative icons.
- **Scrollbars**: 3px wide, `--ink-300`, blends with paper
- **Focus ring**: `box-shadow: 0 0 0 2px var(--accent-soft)` + border swaps
  to `--accent`. No blue glow.
- **Assistant message style**: no bubble — content flows directly on paper,
  with a 2px `--accent` left rule as an identity marker, reading like
  a literary annotation rather than a chat bubble
- **User message style**: right-aligned, `--accent-soft` background, soft
  radius

### Anti-patterns (explicitly forbidden)

- Material Design layered shadows
- Gradient backgrounds (except the login WebGL ink)
- Pill-shaped buttons
- Emoji, cartoon illustrations
- Large color-block hero sections
- The current SaaS blue `#3b82f6`

## §3 Pages & Components

### Routes

```
/                → LoginView (unauthenticated; redirects to /chat if logged in)
/chat            → current session (default after login)
/chat/:sid       → specific session
/me              → ProfileView
/errors          → ErrorsView
/plan            → PlanView
```

SPA navigation, the sidebar is always present.

### State (Pinia stores)

```
useAuthStore        token, studentId, profile (lightweight), login(), logout()
useSessionStore     sessions[], currentSid, selectSession(), newSession()
useChatStore        messages[], isStreaming, send(text), receiveDelta(), reset()
useUiStore          theme, sidebarCollapsed
```

Single responsibility per store. `useChatStore` only manages the current
session's message stream. Session changes trigger reset + history fetch via
`useSessionStore`.

### Component inventory

**Layout**
- `AppShell.vue` — sidebar + main region frame
- `Sidebar.vue` — brand, new-session button, session history, quick-actions, footer
- `SidebarSessionItem.vue` — single session entry (title, time, delete)
- `TopBar.vue` — page title, theme toggle, user menu

**Chat**
- `ChatView.vue` — `/chat` container
- `MessageList.vue` — scroll container + auto-scroll logic
- `UserMessage.vue` — right-aligned with `--accent-soft` background
- `AssistantMessage.vue` — left 2px accent rule + agent badge + Markdown;
  blinking cursor while streaming
- `MarkdownRender.vue` — sanitized markdown-it output, KaTeX + highlight.js lazy-loaded
- `Composer.vue` — auto-grow textarea, upload, send, stop-during-stream
- `EmptyState.vue` — serif greeting + 4 suggestion chips
- `SuggestionChip.vue` — single chip

**Other views**
- `LoginView.vue` — keeps the fluid WebGL ink background (only here)
- `ProfileView.vue` — profile field editor
- `ErrorsView.vue` — error list, filter by subject / date
- `PlanView.vue` — daily / weekly plan
- `EmptyHint.vue` — generic empty state for non-chat pages

**Primitives**
- `IconButton.vue` — unified icon button with focus ring
- `Spinner.vue` — minimal dot animation (reuses the typing-dot style)
- `Toast.vue` + `useToast()` — replaces all `alert()` calls

### Data flow

**Sending a message**
```
Composer → chatStore.send(text)
  → POST /message/send  body {text, session_id}
  → push user message into messages[]
  → push placeholder assistant message (streaming=true) into messages[]
Long-lived SSE (established at main.ts mount)
  → assistant_delta → chatStore.appendDelta(text)
  → assistant_done  → chatStore.finalize(meta)
  → assistant_message (legacy fallback) → chatStore replaces placeholder wholesale
```

**Switching session**
```
Sidebar click
  → sessionStore.selectSession(sid) → router.push(/chat/:sid)
  → ChatView watches route.params.sid
  → chatStore.loadHistory(sid) → GET /sessions/:sid/messages
```

**Session list loading**
```
AppShell mount (or after login)
  → sessionStore.fetchList() → GET /sessions
  → SSE session_created / session_renamed → incremental updates
```

### File contracts

- Each `.vue` SFC ≤ 200 lines. If it grows beyond, it is doing two things.
- Each `stores/*.ts` file ≤ 150 lines.

### Responsive behavior

- ≥ 1024px: sidebar always visible
- 640–1024px: sidebar collapses to a 60px icon-only rail; expands on hover
- < 640px: sidebar is a drawer triggered by a hamburger in TopBar

## §4 Backend Changes

### New REST endpoints

```
GET    /sessions                       list (id, title, last_msg_at, message_count)
GET    /sessions/{sid}                 single session metadata
GET    /sessions/{sid}/messages        message history, paginated (limit, before_id)
PATCH  /sessions/{sid}                 rename, body: {title}
DELETE /sessions/{sid}                 soft-delete (status='archived')

GET    /errors                         error list, query: subject, page, page_size
GET    /errors/{id}                    single error with question stem + explanation_text

GET    /plans                          plan list, query: type=daily|weekly
GET    /plans/{id}                     single plan

GET    /mastery                        mastery overview, grouped by subject
```

All require `Authorization: Bearer <token>`, reuse the existing
`current_student_id` dependency. JSON responses. Errors return
`{detail, code}` with the appropriate HTTP status. No `{success, data}` wrapper.

Session `title` is server-generated: first 24 characters of the first user
message. The PATCH endpoint allows overriding it.

### SSE protocol extension

Legacy event (kept for compatibility):
```
event: assistant_message
data: {"session_id":1,"text":"...full text...","agent":"subject_teacher"}
```

New events:
```
event: assistant_start
data: {"session_id":1, "message_id":42, "agent":"subject_teacher"}

event: assistant_delta
data: {"message_id":42, "delta":"...fragment..."}

event: assistant_done
data: {"message_id":42, "agent":"subject_teacher", "iterations":3, "stop_reason":"completed"}

event: session_created
data: {"session_id":1, "title":"..."}
```

`assistant_message` is a fallback when a path cannot stream (e.g. early
provider failure). The frontend handles both: deltas accumulate into the
placeholder; a full message replaces the placeholder wholesale.

### LLM client streaming

`src/pacer/llm/client.py` and `openai_client.py` add:

```python
async def stream_complete(
    self, messages: list[LLMMessage], **kwargs
) -> AsyncIterator[StreamChunk]
```

Each `StreamChunk` carries `delta_text` or `tool_call_delta`. The non-streaming
`complete()` stays as an internal fallback for non-interactive callers
(scheduler, batch jobs).

The OpenAI-compatible client uses `stream=True` and parses HTTP SSE chunks
into `StreamChunk`s. **No "fake streaming" character-slicing fallback** —
real provider streams only.

### Orchestrator streaming

`Orchestrator.handle()` splits into two paths:
- `handle_streaming(text, history, on_delta) -> Result`: routing stage stays
  synchronous (it's a short decision); the final answer stage uses
  `async for chunk in llm.stream_complete(...)` and `await on_delta(chunk)`
- `handle(text, history)`: legacy synchronous interface, retained for
  non-interactive callers (scheduler)

Tool-call "thinking" phases do not emit deltas. The frontend only sees the
clean final-answer stream, prefixed by `assistant_start` after tool calls finish.

### `POST /message/send` changes

```python
@router.post("/send")
async def send_message(req, request, ...) -> SendAck:
    # persist user message + create empty assistant message (status='streaming')
    # spawn background task running orchestrator.handle_streaming
    # the task pushes deltas to EventBus and finalizes the message in DB
    return SendAck(session_id=chat.id, assistant_message_id=msg.id)
```

The response is now an immediate ack instead of waiting for the full text.
The full content arrives via SSE.

`Message` table adds a `status` column (`streaming` / `done` / `failed`). When
done, full content is written. When interrupted, status becomes `failed` but
accumulated fragments are kept — refreshing the page still shows the partial
content marked as incomplete.

### Stop a stream

```
POST /message/{message_id}/stop
```

Cancels the corresponding background task. EventBus emits `assistant_done`
with `stop_reason="user_stopped"`.

### Engineering risk

- The largest change is `LLM streaming` + `Orchestrator streaming`. OpenAI
  streaming is well-understood; for providers that fail to stream, the path
  falls back to a non-streaming `complete()` and emits a single
  `assistant_message` (which the frontend already handles).
- `Message.status` is a schema change requiring one Alembic migration.
- Compatibility: frontend implements the dual-path consumer first; backend
  switches its emit logic next. Legacy `web/` keeps working until `web-next/`
  reaches parity.

## §5 Errors, Loading, Edges

### Network errors

| Scenario | UI |
|---|---|
| 401 (token expired) | silently clear localStorage + redirect to `/`, no toast |
| 403 / 404 | replace main region with "看不到这里的内容" + a back button, leave the shell intact |
| 5xx | non-blocking toast at the top: "服务器没回应，稍后重试"; user input is preserved |
| Network failure (fetch reject) | same as 5xx |
| SSE disconnect | exponential backoff reconnect (1s/2s/5s/10s, max 30s); a thin "重连中" line appears at the bottom; clears on recovery |

### Loading states

**Global rule**: any request still pending after 200ms shows a loading state.
Faster requests show nothing.

| Region | Loading style |
|---|---|
| Session history load (switching sessions) | 1px accent progress bar above the message area |
| Initial sessions list | 3 skeleton rows in sidebar, paper-tinted grey |
| Errors / Plan / Profile initial load | centered serif line "翻阅中…", no spinner |
| Sending message → waiting for stream | reuse the typing-dot animation inside the assistant placeholder |
| Image upload in progress | composer upload icon swaps to a spinning line |

**Forbidden**: full-screen loading masks, blur backgrounds, large circular spinners.

### Empty states

| Location | Content |
|---|---|
| `/chat` no messages | serif greeting "早上好/下午好/晚上好，{name}" + a single sub-line + 4 suggestion chips |
| `/chat/:sid` empty history | "这卷还没写字" — single grey serif line, centered |
| `/errors` empty | "暂未记下错题" + "做题时遇到的错处，会自动汇集在这里" |
| `/plan` empty | "今天还没有计划" + a "让 pacer 帮你定" button that routes to chat with a preset |
| `/me` empty field | the value displays as a faint "——", not "未填写" |

### Input boundaries

- Message text: trim, max 8000 chars, disable send + show counter when exceeded; backend re-validates
- Image upload: jpeg/png/webp ≤ 8MB, frontend pre-check; over limit → toast
- PIN failure: generic "学号或密码不对", never tell which one
- Session rename: 1–40 chars, real-time validation

### Toast system

Replaces all `alert()`. Minimal:
- Bottom-right, max 3 concurrent
- Two types only: `info` (faint ink background) and `error` (vermilion thin border)
- 3-second auto-dismiss, click to dismiss earlier
- **No success toast** — success is the default, it should not interrupt focus

### Offline and refresh

- Initial paint: if localStorage has a token, optimistically render AppShell
  and call `/profile` to verify; 401 → login
- Mid-session refresh: re-fetch `/sessions/:sid/messages` so history survives
- Offline (`navigator.onLine === false`): a warm-grey banner above the
  composer reads "已离线"; the input stays enabled so drafts can be written

### Accessibility

- All IconButton instances must have `aria-label`
- Color contrast meets WCAG AA (vermilion, grey-cyan, paper combos verified)
- Keyboard: `Enter` send, `Shift+Enter` newline, `Cmd/Ctrl+K` focus input,
  `Esc` dismiss toast / drawer
- `prefers-reduced-motion`: disables the streaming cursor blink and sidebar
  slide transitions

## §6 Testing

Single-developer project — coverage is not the goal. Principle:
**test things that regress repeatedly; don't test things that are correct once.**

### Frontend (Vitest + Vue Test Utils)

Required:
- `useChatStore` delta accumulation — many edges (mid-stream disconnect,
  `message_id` mismatch, placeholder replacement, interleaved messages)
- `MarkdownRender` with KaTeX / code / table inputs → DOM snapshots, to catch
  silent regressions when markdown-it is upgraded
- `api/sse.ts` client: simulate event streams, assert store state transitions
- Router guards: unauthenticated → `/`, authenticated visiting `/` → `/chat`

Not tested:
- Purely presentational components (UserMessage, Sidebar) — eyes handle these
- Pinia plumbing (setActivePinia etc.)

### Backend (pytest, existing)

Add:
- `test_streaming.py`: mock `stream_complete` to return fixed chunks; assert
  the EventBus emits the expected `assistant_delta` sequence and the final
  `assistant_done` matches the persisted message content
- `test_sessions_api.py`: list / detail / rename / delete; authorization +
  cross-tenant guard (another student's session is 404)
- `test_message_status.py`: user calls `POST /message/{id}/stop` mid-stream;
  assert `message.status='failed'` and accumulated fragment is preserved

### End-to-end (manual checklist, not automated)

Run every item below before declaring a phase complete. "Looks fine" is not
acceptance — each item must be exercised.

1. Login → default to `/chat` → greeting visible
2. Send "讲一道导数题" → text streams in word-by-word → `\frac{dx}{dt}` renders correctly
3. Click "stop" mid-stream → output halts → refresh → the message persists, marked incomplete
4. Toggle theme → colors switch immediately, contrast holds
5. Upload a problem image → stem is auto-filled → send → streamed explanation
6. New session → appears in sidebar → switch to an older session → history reloads
7. Rename / delete a session
8. Visit `/errors` → list renders, or empty-state copy matches spec
9. Visit `/plan` → same
10. Visit `/me` → edit `target_school` → save → refresh → still saved
11. Logout → returns to `/` → token cleared → ink background re-appears
12. Mobile < 640px: sidebar drawer works

### Lint / type-check

- TypeScript `strict: true`
- ESLint: `no-explicit-any`, `no-unused-vars`, `vue/multi-word-component-names`
- Optional pre-commit hook: `pnpm typecheck && pnpm lint && pytest -x`

## Acceptance

The work is complete when:

1. All 12 manual end-to-end items above pass
2. All required Vitest + pytest tests pass in CI (or local equivalent)
3. Legacy `src/pacer/web/` directory is deleted and the FastAPI app serves
   only from `web-next/dist`
4. The visual result matches §2 — no SaaS blue, no emoji, no large radii,
   no Material shadows

## Progress

- [x] Phase 1 (2026-05-19): Vite + Vue 3 scaffold, visual rewrite, chat parity — **complete**
  - 21 commits: scaffold → stores → components → wiring → build verification
  - 44 Vitest, 38 pytest, `pnpm typecheck`, `pnpm build` all green
  - FastAPI prefer-serves `web-next/dist` with SPA fallback; legacy `web/` rollback verified
- [ ] Phase 2: streaming + Markdown enhancements
- [ ] Phase 3: session history
- [ ] Phase 4: profile / errors / plan views; delete legacy `web/`

## Phase 2–4 Implementation Notes

- Phase 2 plan file: `docs/superpowers/plans/<date>-frontend-phase-2.md`
- Phase 3 plan file: `docs/superpowers/plans/<date>-frontend-phase-3.md`
- Phase 4 plan file: `docs/superpowers/plans/<date>-frontend-phase-4.md`

## Open Questions (none blocking)

- Provider streaming compatibility: the chosen LLM provider must support
  SSE `stream=True`. If not, fall back to a single `assistant_message` event
  (already supported by the frontend).
- KaTeX bundle size: verify `markdown-it-katex` + KaTeX font subset stays
  under 100KB gzipped; if not, switch to server-side rendering of math during
  message persistence.
