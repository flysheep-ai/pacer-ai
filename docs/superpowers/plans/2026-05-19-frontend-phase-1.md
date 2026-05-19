# Frontend Optimization — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-19-frontend-optimization-design.md`

**Goal:** Stand up a Vue 3 + Vite SPA under `src/pacer/web-next/`, port the existing chat functionality 1:1, apply the new "静谧东方文人感" visual system, and have FastAPI prefer-serve the built SPA when present — leaving legacy `web/` working as a rollback anchor.

**Architecture:** Greenfield Vue 3 + TypeScript + Pinia + Vue Router under `src/pacer/web-next/`. Dev: Vite proxies API to FastAPI. Prod: FastAPI mounts the Vite `dist/` output. Legacy `web/` directory is untouched until later phases.

**Tech Stack:** Vue 3.5+, Vite 5, TypeScript strict, Pinia 2, Vue Router 4, Vitest 2, pnpm 10, Node 20+.

**Scope:** Phase 1 only. Streaming, Markdown enhancements, session history, multi-page navigation, and removal of legacy `web/` are scheduled for Phases 2–4.

---

## File Structure (Phase 1)

```
src/pacer/
  web/                                  # legacy, untouched
  web-next/                             # new
    package.json
    pnpm-lock.yaml
    tsconfig.json
    tsconfig.node.json
    vite.config.ts
    vitest.config.ts
    index.html
    .gitignore                          # node_modules, dist
    src/
      main.ts                           # createApp + Pinia + Router + mount
      App.vue                           # <RouterView/>
      router.ts                         # routes + nav guard
      shims.d.ts                        # *.vue module declarations
      api/
        client.ts                       # auth-aware fetch wrapper
        sse.ts                          # legacy assistant_message consumer
      stores/
        auth.ts                         # token, studentId, profile
        ui.ts                           # theme
        session.ts                      # currentSid (minimal in Phase 1)
        chat.ts                         # messages[], send()
      composables/
        useAutoScroll.ts                # auto-scroll a ref to bottom
        useToast.ts                     # toast push/remove
      utils/
        markdown.ts                     # subset md → html (port of current md())
        fluid-background.ts             # TS port of current fluid-background.js
      components/
        AppShell.vue                    # layout: Sidebar + main slot
        Sidebar.vue                     # brand + new-chat + quick actions + footer
        TopBar.vue                      # title + theme toggle
        MessageList.vue                 # scroll container, auto-scroll
        UserMessage.vue                 # right-aligned bubble
        AssistantMessage.vue            # left accent rule + markdown
        MarkdownRender.vue              # uses utils/markdown
        Composer.vue                    # textarea + upload + send
        EmptyState.vue                  # greeting + suggestions
        SuggestionChip.vue              # single chip
        IconButton.vue                  # button + slot + focus ring
        Toast.vue                       # toast root, listens to useToast
      views/
        LoginView.vue                   # login form + fluid background
        ChatView.vue                    # composes AppShell + MessageList + Composer
      styles/
        reset.css                       # minimal reset
        tokens.css                      # design tokens from spec §2
        base.css                        # body, scrollbar, fonts
    tests/
      unit/
        client.test.ts
        sse.test.ts
        auth-store.test.ts
        ui-store.test.ts
        chat-store.test.ts
        session-store.test.ts
        markdown.test.ts
        router.test.ts
        composables.test.ts
```

`src/pacer/api/server.py` is modified to prefer-serve `web-next/dist/` when it exists. `src/pacer/web/` is **not** modified.

---

## Conventions

- **Package manager**: `pnpm` (locked in by committing `pnpm-lock.yaml`)
- **Node**: 20 or later (your current 25 is fine)
- **All `pnpm` commands are run from `src/pacer/web-next/`** unless noted
- **Backend test commands** (`pytest …`) are run from repo root with the existing virtualenv active
- **Frontend test commands** (`pnpm test`) are run from `src/pacer/web-next/`
- **Commit policy**: small, after each task. Use Conventional Commits style (`feat:`, `chore:`, `test:`, `refactor:`, `fix:`)
- **Path alias**: `@/*` resolves to `src/pacer/web-next/src/*` (configured in tsconfig + vite)
- **TDD**: write the failing test → run → write impl → run → commit. For pure presentational `.vue` files (no logic), no unit test is required — those are verified visually in the final smoke task

---

## Task 1: Backend — prefer-serve `web-next/dist` when present

**Files:**
- Modify: `src/pacer/api/server.py`
- Create: `tests/api/test_static_serving.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_static_serving.py`:

```python
from __future__ import annotations
from pathlib import Path
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient
from pacer.api.server import create_app


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_serves_legacy_web_when_no_dist(monkeypatch, tmp_path):
    legacy = tmp_path / "web"
    _write(legacy / "index.html", "<!doctype html>LEGACY")
    _write(legacy / "static" / "app.css", "/* css */")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", legacy)
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", tmp_path / "doesnotexist")
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    r = client.get("/")
    assert r.status_code == 200
    assert "LEGACY" in r.text


def test_serves_web_next_dist_when_present(monkeypatch, tmp_path):
    legacy = tmp_path / "web"
    _write(legacy / "index.html", "<!doctype html>LEGACY")
    next_dist = tmp_path / "dist"
    _write(next_dist / "index.html", "<!doctype html>NEXT")
    _write(next_dist / "assets" / "main.js", "console.log(1)")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", legacy)
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", next_dist)
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    r = client.get("/")
    assert r.status_code == 200
    assert "NEXT" in r.text
    r2 = client.get("/assets/main.js")
    assert r2.status_code == 200
    assert "console.log" in r2.text


def test_spa_fallback_returns_index_for_unknown_path(monkeypatch, tmp_path):
    next_dist = tmp_path / "dist"
    _write(next_dist / "index.html", "<!doctype html>NEXT")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", tmp_path / "nope")
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", next_dist)
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    r = client.get("/chat/42")
    assert r.status_code == 200
    assert "NEXT" in r.text


def test_api_routes_not_shadowed_by_spa_fallback(monkeypatch, tmp_path):
    next_dist = tmp_path / "dist"
    _write(next_dist / "index.html", "<!doctype html>NEXT")
    monkeypatch.setattr("pacer.api.server.LEGACY_WEB_DIR", tmp_path / "nope")
    monkeypatch.setattr("pacer.api.server.NEXT_DIST_DIR", next_dist)
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    r = client.post("/auth/login", json={"student_id": 999999, "pin": "wrong"})
    # 401 or 404 from auth route, NOT 200 NEXT html
    assert r.status_code in (401, 404, 422)
    assert "NEXT" not in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run from repo root:
```
pytest tests/api/test_static_serving.py -v
```

Expected: FAIL (module-level attributes `LEGACY_WEB_DIR` / `NEXT_DIST_DIR` don't exist).

- [ ] **Step 3: Modify `src/pacer/api/server.py`**

Replace the existing static-serving block. Full new file:

```python
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pacer.api import deps
from pacer.api.routes.auth import router as auth_router
from pacer.api.routes.message import router as message_router
from pacer.api.routes.events import router as events_router
from pacer.api.routes.internal import router as internal_router
from pacer.api.routes.upload import router as upload_router
from pacer.api.routes.profile import router as profile_router
from pacer.session.events import EventBus
from pacer.skills.loader import SkillsLoader
from pacer.config import get_settings

LEGACY_WEB_DIR = Path(__file__).parent.parent / "web"
NEXT_DIST_DIR = Path(__file__).parent.parent / "web-next" / "dist"


def _create_llm_client(settings):
    if settings.llm_provider == "openai-compat":
        from pacer.llm.openai_client import OpenAICompatClient
        return OpenAICompatClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.main_model,
        )
    else:
        from pacer.llm.client import LLMClient
        return LLMClient(api_key=settings.llm_api_key, model=settings.main_model)


def create_app(database_url: str | None = None) -> FastAPI:
    deps.init_db(database_url)
    app = FastAPI(title="pacer-ai")
    settings = get_settings()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.event_bus = EventBus()
    app.state.llm = _create_llm_client(settings)
    skills_root = Path(__file__).parent.parent / "skills" / "content"
    app.state.skills_loader = SkillsLoader(root=skills_root)

    app.include_router(auth_router)
    app.include_router(message_router)
    app.include_router(events_router)
    app.include_router(internal_router)
    app.include_router(upload_router)
    app.include_router(profile_router)

    if NEXT_DIST_DIR.exists():
        _mount_spa(app, NEXT_DIST_DIR)
    elif LEGACY_WEB_DIR.exists():
        _mount_legacy(app, LEGACY_WEB_DIR)

    return app


def _mount_legacy(app: FastAPI, web_dir: Path) -> None:
    static_dir = web_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def legacy_index():
        return FileResponse(str(web_dir / "index.html"))


def _mount_spa(app: FastAPI, dist_dir: Path) -> None:
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    index_path = dist_dir / "index.html"

    @app.get("/", include_in_schema=False)
    async def spa_index():
        return FileResponse(str(index_path))

    # SPA fallback — catches unknown paths and returns index.html.
    # Must be registered AFTER all API routers.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Files under /static (legacy) and /assets are already mounted.
        # API routes match before this generic route because routers are included first.
        return FileResponse(str(index_path))
```

- [ ] **Step 4: Run tests to verify pass**

```
pytest tests/api/test_static_serving.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run full backend test suite to make sure nothing else broke**

```
pytest -x
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/pacer/api/server.py tests/api/test_static_serving.py
git commit -m "feat(api): prefer-serve web-next/dist with SPA fallback"
```

---

## Task 2: Scaffold Vite + Vue 3 + TypeScript project

**Files:**
- Create: `src/pacer/web-next/package.json`
- Create: `src/pacer/web-next/tsconfig.json`
- Create: `src/pacer/web-next/tsconfig.node.json`
- Create: `src/pacer/web-next/vite.config.ts`
- Create: `src/pacer/web-next/vitest.config.ts`
- Create: `src/pacer/web-next/index.html`
- Create: `src/pacer/web-next/.gitignore`
- Create: `src/pacer/web-next/src/shims.d.ts`
- Create: `src/pacer/web-next/src/App.vue`
- Create: `src/pacer/web-next/src/main.ts`

- [ ] **Step 1: Create the directory and initialize files**

From repo root:
```bash
mkdir -p src/pacer/web-next/src
cd src/pacer/web-next
```

Create `package.json`:
```json
{
  "name": "pacer-web-next",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "vue-tsc --noEmit"
  },
  "dependencies": {
    "pinia": "^2.2.4",
    "vue": "^3.5.13",
    "vue-router": "^4.4.5"
  },
  "devDependencies": {
    "@types/node": "^20.16.10",
    "@vitejs/plugin-vue": "^5.1.4",
    "@vue/test-utils": "^2.4.6",
    "happy-dom": "^15.7.4",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2",
    "vue-tsc": "^2.1.6"
  },
  "packageManager": "pnpm@10.33.0"
}
```

Create `.gitignore`:
```
node_modules
dist
.vite
*.log
```

Create `tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "useDefineForClassFields": true,
    "verbatimModuleSyntax": true,
    "allowImportingTsExtensions": false,
    "noEmit": true,
    "types": ["vitest/globals"],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.d.ts", "src/**/*.vue", "tests/**/*.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts", "vitest.config.ts"]
}
```

Create `vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const API_TARGET = 'http://localhost:8000'
const API_PREFIXES = [
  '/auth', '/message', '/events', '/upload',
  '/profile', '/sessions', '/errors', '/plans', '/mastery',
]

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      API_PREFIXES.map(p => [
        p,
        { target: API_TARGET, changeOrigin: true, ws: false },
      ]),
    ),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2022',
  },
})
```

Create `vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['tests/**/*.test.ts'],
  },
})
```

Create `index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>pacer · 高考陪跑AI</title>
</head>
<body>
<div id="app"></div>
<script type="module" src="/src/main.ts"></script>
</body>
</html>
```

Create `src/shims.d.ts`:
```ts
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
```

Create `src/App.vue`:
```vue
<script setup lang="ts">
</script>

<template>
  <div>pacer-next scaffold</div>
</template>
```

Create `src/main.ts`:
```ts
import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
```

- [ ] **Step 2: Install dependencies**

From `src/pacer/web-next/`:
```bash
pnpm install
```

Expected: lockfile created, `node_modules/` populated.

- [ ] **Step 3: Verify dev server boots**

```bash
pnpm dev
```

Expected: Vite prints `Local: http://localhost:5173/`. Open it manually in a browser and verify "pacer-next scaffold" renders. Then `Ctrl+C` to stop.

- [ ] **Step 4: Verify build works**

```bash
pnpm build
```

Expected: `dist/` is created with `index.html` and an `assets/` directory.

- [ ] **Step 5: Verify typecheck passes**

```bash
pnpm typecheck
```

Expected: no errors.

- [ ] **Step 6: Commit**

From repo root:
```bash
git add src/pacer/web-next/.gitignore src/pacer/web-next/package.json \
        src/pacer/web-next/pnpm-lock.yaml src/pacer/web-next/tsconfig.json \
        src/pacer/web-next/tsconfig.node.json src/pacer/web-next/vite.config.ts \
        src/pacer/web-next/vitest.config.ts src/pacer/web-next/index.html \
        src/pacer/web-next/src/
git commit -m "chore(web-next): scaffold vite + vue 3 + ts + vitest"
```

Then build once and verify backend serves the SPA:

```bash
pnpm build
cd ../../..  # back to repo root
pytest tests/api/test_static_serving.py -v
```

Expected: still green.

---

## Task 3: Design tokens + base styles

**Files:**
- Create: `src/pacer/web-next/src/styles/reset.css`
- Create: `src/pacer/web-next/src/styles/tokens.css`
- Create: `src/pacer/web-next/src/styles/base.css`

No unit tests — purely declarative CSS. Verified in the smoke task.

- [ ] **Step 1: Write `src/styles/reset.css`**

```css
*, *::before, *::after { box-sizing: border-box; }
* { margin: 0; padding: 0; }
html, body, #app { height: 100%; }
body { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; }
input, textarea { font: inherit; color: inherit; }
a { color: inherit; text-decoration: none; }
img { display: block; max-width: 100%; }
```

- [ ] **Step 2: Write `src/styles/tokens.css`**

```css
:root {
  --paper-0: #F7F3EA;
  --paper-1: #F1ECDF;
  --paper-2: #E9E2D2;
  --ink-900: #1C1815;
  --ink-700: #4A413A;
  --ink-500: #8A7F70;
  --ink-300: #C9BFAE;
  --accent: #6B8A92;
  --accent-soft: #DDE6E8;
  --seal: #A33E2A;
  --moss: #5C7A4F;

  --font-serif: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", serif;
  --font-sans: "Source Han Sans SC", "Noto Sans SC", -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif;
  --font-mono: "JetBrains Mono", "SF Mono", "Cascadia Code", "Fira Code", monospace;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;

  --radius-xs: 2px;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;

  --shadow-hover: 0 1px 2px rgba(28, 24, 21, 0.05);

  --motion-fast: 160ms cubic-bezier(.4, 0, .2, 1);
  --motion-mid:  240ms cubic-bezier(.4, 0, .2, 1);
  --motion-slow: 380ms cubic-bezier(.4, 0, .2, 1);
}

[data-theme="dark"] {
  --paper-0: #1A1815;
  --paper-1: #221F1B;
  --paper-2: #2B2722;
  --ink-900: #E8DFCE;
  --ink-700: #B5AC9B;
  --ink-500: #80776A;
  --ink-300: #4A433B;
  --accent: #88A8B0;
  --accent-soft: #2A3A3F;
  --seal: #C76050;
  --moss: #7C9870;
  --shadow-hover: 0 1px 2px rgba(0, 0, 0, 0.4);
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-fast: 0ms;
    --motion-mid: 0ms;
    --motion-slow: 0ms;
  }
}
```

- [ ] **Step 3: Write `src/styles/base.css`**

```css
html, body {
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.65;
  color: var(--ink-900);
  background: var(--paper-0);
}

::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-thumb { background: var(--ink-300); border-radius: 2px; }
::-webkit-scrollbar-track { background: transparent; }

::selection { background: var(--accent-soft); color: var(--ink-900); }

:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--accent-soft);
  border-radius: var(--radius-sm);
}
```

- [ ] **Step 4: Import tokens + base in `main.ts`**

Replace `src/main.ts`:
```ts
import { createApp } from 'vue'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'

createApp(App).mount('#app')
```

- [ ] **Step 5: Verify dev server still boots and the page picks up paper-0 background**

```bash
pnpm dev
```

Visit `http://localhost:5173`, confirm body background is rice-paper beige (`#F7F3EA`). `Ctrl+C`.

- [ ] **Step 6: Commit**

```bash
git add src/pacer/web-next/src/styles/ src/pacer/web-next/src/main.ts
git commit -m "feat(web-next): add design tokens and base styles"
```

---

## Task 4: `utils/markdown.ts` — port simple md → html

**Files:**
- Create: `src/pacer/web-next/src/utils/markdown.ts`
- Create: `src/pacer/web-next/tests/unit/markdown.test.ts`

This is a TS port of the current `md()` function in `app.js`. Phase 2 will replace it with markdown-it + KaTeX. Phase 1 keeps the same minimal subset so chat content renders identically to today.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/markdown.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { mdToHtml } from '@/utils/markdown'

describe('mdToHtml', () => {
  it('escapes HTML entities', () => {
    expect(mdToHtml('<script>x</script>'))
      .toBe('&lt;script&gt;x&lt;/script&gt;')
  })

  it('renders inline code', () => {
    expect(mdToHtml('use `let x = 1`'))
      .toBe('use <code>let x = 1</code>')
  })

  it('renders fenced code blocks', () => {
    const out = mdToHtml('```js\nconst a = 1\n```')
    expect(out).toBe('<pre><code>const a = 1\n</code></pre>')
  })

  it('renders bold', () => {
    expect(mdToHtml('this is **bold**'))
      .toBe('this is <strong>bold</strong>')
  })

  it('converts newlines to <br>', () => {
    expect(mdToHtml('line1\nline2'))
      .toBe('line1<br>line2')
  })

  it('handles ampersand correctly before other replacements', () => {
    expect(mdToHtml('a & b'))
      .toBe('a &amp; b')
  })

  it('handles empty input', () => {
    expect(mdToHtml('')).toBe('')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pnpm test
```

Expected: FAIL — module `@/utils/markdown` not found.

- [ ] **Step 3: Write the implementation**

Create `src/utils/markdown.ts`:

```ts
export function mdToHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}
```

- [ ] **Step 4: Run test to verify pass**

```bash
pnpm test
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/utils/markdown.ts \
        src/pacer/web-next/tests/unit/markdown.test.ts
git commit -m "feat(web-next): port simple markdown renderer"
```

---

## Task 5: `utils/fluid-background.ts` — TS port of WebGL ink background

**Files:**
- Create: `src/pacer/web-next/src/utils/fluid-background.ts`

No unit tests — WebGL behavior is verified visually in the LoginView smoke step.

- [ ] **Step 1: Create the file**

This is a direct TS port of `src/pacer/web/static/fluid-background.js`. Type annotations added; behavior identical.

Create `src/utils/fluid-background.ts`:

```ts
interface Particle {
  x: number
  y: number
  life: number
  decay: number
  size: number
}

interface Mouse {
  x: number
  y: number
  prevX: number
  prevY: number
  active: boolean
}

interface Uniforms {
  aPos: number
  aSize: number
  aAlpha: number
  uRes: WebGLUniformLocation | null
  uPtScale: WebGLUniformLocation | null
  uColor: WebGLUniformLocation | null
}

const VERT = `
  precision highp float;
  attribute vec2 aPos;
  attribute float aSize;
  attribute float aAlpha;
  uniform vec2 uRes;
  uniform float uPtScale;
  varying float vAlpha;
  void main() {
    vec2 ndc = aPos * 2.0 - 1.0;
    gl_Position = vec4(ndc.x, ndc.y, 0.0, 1.0);
    gl_PointSize = aSize * uPtScale;
    vAlpha = aAlpha;
  }
`

const FRAG = `
  precision highp float;
  varying float vAlpha;
  uniform vec3 uColor;
  void main() {
    float d = length(gl_PointCoord - 0.5) * 2.0;
    float alpha = vAlpha * exp(-d * d * 2.5);
    alpha *= smoothstep(1.0, 0.5, d);
    gl_FragColor = vec4(uColor, clamp(alpha, 0.0, 1.0));
  }
`

export class FluidBackground {
  private canvas: HTMLCanvasElement
  private gl: WebGLRenderingContext | null = null
  private program: WebGLProgram | null = null
  private uniforms: Uniforms | null = null
  private particles: Particle[] = []
  private maxParticles = 400
  private mouse: Mouse = { x: -1, y: -1, prevX: -1, prevY: -1, active: false }
  private rafId: number | null = null
  private lastTime = 0
  private onMouse?: (e: MouseEvent) => void
  private onLeave?: () => void
  private onTouch?: (e: TouchEvent) => void
  private onTouchEnd?: () => void
  private onResize?: () => void

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
    this.init()
  }

  private init(): void {
    const gl = this.canvas.getContext('webgl', {
      alpha: true, antialias: false, premultipliedAlpha: false,
      powerPreference: 'high-performance',
    })
    if (!gl) { console.warn('WebGL not available'); return }
    this.gl = gl
    this.resize()
    if (!this.buildProgram()) return
    this.bindEvents()
    this.loop()
  }

  private resize(): void {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = this.canvas.clientWidth * dpr
    const h = this.canvas.clientHeight * dpr
    if (this.canvas.width === w && this.canvas.height === h) return
    this.canvas.width = w
    this.canvas.height = h
    this.gl?.viewport(0, 0, w, h)
  }

  private compile(type: number, src: string): WebGLShader | null {
    const gl = this.gl!
    const s = gl.createShader(type)
    if (!s) return null
    gl.shaderSource(s, src)
    gl.compileShader(s)
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('shader error:', gl.getShaderInfoLog(s))
      gl.deleteShader(s)
      return null
    }
    return s
  }

  private buildProgram(): boolean {
    const gl = this.gl!
    const vs = this.compile(gl.VERTEX_SHADER, VERT)
    const fs = this.compile(gl.FRAGMENT_SHADER, FRAG)
    if (!vs || !fs) return false
    const pg = gl.createProgram()
    if (!pg) return false
    gl.attachShader(pg, vs)
    gl.attachShader(pg, fs)
    gl.linkProgram(pg)
    if (!gl.getProgramParameter(pg, gl.LINK_STATUS)) {
      console.warn('link error:', gl.getProgramInfoLog(pg))
      return false
    }
    gl.useProgram(pg)
    this.program = pg
    this.uniforms = {
      aPos: gl.getAttribLocation(pg, 'aPos'),
      aSize: gl.getAttribLocation(pg, 'aSize'),
      aAlpha: gl.getAttribLocation(pg, 'aAlpha'),
      uRes: gl.getUniformLocation(pg, 'uRes'),
      uPtScale: gl.getUniformLocation(pg, 'uPtScale'),
      uColor: gl.getUniformLocation(pg, 'uColor'),
    }
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    gl.disable(gl.DEPTH_TEST)
    return true
  }

  private spawn(x: number, y: number, count: number): void {
    for (let i = 0; i < count; i++) {
      if (this.particles.length >= this.maxParticles) this.particles.shift()
      const jx = (Math.random() - 0.5) * 0.002
      const jy = (Math.random() - 0.5) * 0.002
      this.particles.push({
        x: x + jx, y: y + jy, life: 1.0,
        decay: 0.025 + Math.random() * 0.025,
        size: 1.5 + Math.random() * 3.5,
      })
    }
  }

  private update(dt: number): void {
    const cappedDt = Math.min(dt, 33)
    if (this.mouse.active) {
      const dx = this.mouse.x - this.mouse.prevX
      const dy = this.mouse.y - this.mouse.prevY
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist > 0.0005) {
        const steps = Math.min(Math.ceil(dist * 200), 8)
        for (let s = 0; s < steps; s++) {
          const t = s / Math.max(steps - 1, 1)
          this.spawn(this.mouse.prevX + dx * t, this.mouse.prevY + dy * t, 1)
        }
      }
    }
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i]
      p.life -= p.decay * cappedDt * 0.06
      p.size += 0.004 * cappedDt
      if (p.life <= 0) this.particles.splice(i, 1)
    }
  }

  private render(): void {
    const gl = this.gl!
    const u = this.uniforms!
    const N = this.particles.length
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    if (N === 0) return
    const pos = new Float32Array(N * 2)
    const sz = new Float32Array(N)
    const al = new Float32Array(N)
    for (let i = 0; i < N; i++) {
      const p = this.particles[i]
      pos[i * 2] = p.x
      pos[i * 2 + 1] = p.y
      sz[i] = p.size
      al[i] = p.life * 0.25
    }
    const posBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf)
    gl.bufferData(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(u.aPos)
    gl.vertexAttribPointer(u.aPos, 2, gl.FLOAT, false, 0, 0)
    const szBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, szBuf)
    gl.bufferData(gl.ARRAY_BUFFER, sz, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(u.aSize)
    gl.vertexAttribPointer(u.aSize, 1, gl.FLOAT, false, 0, 0)
    const alBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, alBuf)
    gl.bufferData(gl.ARRAY_BUFFER, al, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(u.aAlpha)
    gl.vertexAttribPointer(u.aAlpha, 1, gl.FLOAT, false, 0, 0)
    gl.uniform2f(u.uRes, this.canvas.width, this.canvas.height)
    gl.uniform1f(u.uPtScale, 40.0)
    const dark = document.documentElement.getAttribute('data-theme') === 'dark'
    gl.uniform3f(u.uColor, dark ? 0.72 : 0.28, dark ? 0.74 : 0.26, dark ? 0.78 : 0.24)
    gl.drawArrays(gl.POINTS, 0, N)
    gl.deleteBuffer(posBuf)
    gl.deleteBuffer(szBuf)
    gl.deleteBuffer(alBuf)
  }

  private bindEvents(): void {
    this.onMouse = (e: MouseEvent) => {
      this.mouse.prevX = this.mouse.x
      this.mouse.prevY = this.mouse.y
      this.mouse.x = e.clientX / window.innerWidth
      this.mouse.y = 1.0 - e.clientY / window.innerHeight
      this.mouse.active = true
    }
    this.onLeave = () => { this.mouse.active = false }
    this.onTouch = (e: TouchEvent) => {
      if (e.touches.length > 0) {
        this.mouse.prevX = this.mouse.x
        this.mouse.prevY = this.mouse.y
        this.mouse.x = e.touches[0].clientX / window.innerWidth
        this.mouse.y = 1.0 - e.touches[0].clientY / window.innerHeight
        this.mouse.active = true
      }
    }
    this.onTouchEnd = () => { this.mouse.active = false }
    this.onResize = () => this.resize()
    window.addEventListener('mousemove', this.onMouse)
    window.addEventListener('mouseleave', this.onLeave)
    window.addEventListener('touchmove', this.onTouch, { passive: true })
    window.addEventListener('touchend', this.onTouchEnd)
    window.addEventListener('resize', this.onResize)
  }

  private unbindEvents(): void {
    if (this.onMouse) window.removeEventListener('mousemove', this.onMouse)
    if (this.onLeave) window.removeEventListener('mouseleave', this.onLeave)
    if (this.onTouch) window.removeEventListener('touchmove', this.onTouch)
    if (this.onTouchEnd) window.removeEventListener('touchend', this.onTouchEnd)
    if (this.onResize) window.removeEventListener('resize', this.onResize)
  }

  private loop(): void {
    const now = performance.now()
    const dt = Math.min(now - (this.lastTime || now), 50)
    this.lastTime = now
    this.update(dt)
    this.render()
    this.rafId = requestAnimationFrame(() => this.loop())
  }

  destroy(): void {
    if (this.rafId !== null) cancelAnimationFrame(this.rafId)
    this.unbindEvents()
    if (this.gl) {
      this.gl.getExtension('WEBGL_lose_context')?.loseContext()
      this.gl = null
    }
    this.particles.length = 0
  }
}
```

- [ ] **Step 2: Verify typecheck passes**

```bash
pnpm typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/pacer/web-next/src/utils/fluid-background.ts
git commit -m "feat(web-next): port fluid ink background to TS"
```

---

## Task 6: `api/client.ts` — auth-aware fetch wrapper

**Files:**
- Create: `src/pacer/web-next/src/api/client.ts`
- Create: `src/pacer/web-next/tests/unit/client.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/client.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, ApiError } from '@/api/client'

describe('apiFetch', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('returns parsed JSON on 2xx', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const r = await apiFetch<{ ok: boolean }>('/x')
    expect(r).toEqual({ ok: true })
  })

  it('attaches Authorization header when token is set', async () => {
    localStorage.setItem('pacer_token', 'tk')
    const spy = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    globalThis.fetch = spy as unknown as typeof fetch
    await apiFetch('/x')
    const req = spy.mock.calls[0]
    const headers = req[1].headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer tk')
  })

  it('omits Authorization when no token', async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    globalThis.fetch = spy as unknown as typeof fetch
    await apiFetch('/x')
    const headers = spy.mock.calls[0][1].headers as Record<string, string>
    expect('Authorization' in headers).toBe(false)
  })

  it('throws ApiError on non-2xx with detail', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'nope' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      }),
    )
    await expect(apiFetch('/x')).rejects.toBeInstanceOf(ApiError)
    try {
      await apiFetch('/x')
    } catch (e) {
      expect((e as ApiError).status).toBe(404)
      expect((e as ApiError).detail).toBe('nope')
    }
  })

  it('serializes JSON body and sets content-type', async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    globalThis.fetch = spy as unknown as typeof fetch
    await apiFetch('/x', { method: 'POST', json: { a: 1 } })
    const init = spy.mock.calls[0][1]
    expect(init.body).toBe('{"a":1}')
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pnpm test
```

Expected: FAIL — `@/api/client` not found.

- [ ] **Step 3: Write the implementation**

Create `src/api/client.ts`:

```ts
const TOKEN_KEY = 'pacer_token'

export class ApiError extends Error {
  status: number
  detail: string
  code: string | undefined
  constructor(status: number, detail: string, code?: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.code = code
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  json?: unknown
  body?: BodyInit
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { json, body, headers: rawHeaders, ...rest } = options
  const headers: Record<string, string> = { ...(rawHeaders as Record<string, string>) }

  const token = localStorage.getItem(TOKEN_KEY)
  if (token) headers.Authorization = `Bearer ${token}`

  let finalBody = body
  if (json !== undefined) {
    finalBody = JSON.stringify(json)
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(path, { ...rest, headers, body: finalBody })

  let payload: unknown = null
  const ct = res.headers.get('content-type') ?? ''
  if (ct.includes('application/json')) {
    payload = await res.json().catch(() => null)
  } else {
    payload = await res.text().catch(() => '')
  }

  if (!res.ok) {
    const p = payload as { detail?: string; code?: string } | null
    throw new ApiError(res.status, p?.detail ?? res.statusText, p?.code)
  }
  return payload as T
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token === null) localStorage.removeItem(TOKEN_KEY)
  else localStorage.setItem(TOKEN_KEY, token)
}
```

- [ ] **Step 4: Run test to verify pass**

```bash
pnpm test
```

Expected: all client tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/api/client.ts \
        src/pacer/web-next/tests/unit/client.test.ts
git commit -m "feat(web-next): add auth-aware fetch client"
```

---

## Task 7: `stores/auth.ts` — token + profile

**Files:**
- Create: `src/pacer/web-next/src/stores/auth.ts`
- Create: `src/pacer/web-next/tests/unit/auth-store.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/auth-store.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('starts unauthenticated by default', () => {
    const s = useAuthStore()
    expect(s.isAuthenticated).toBe(false)
    expect(s.token).toBeNull()
  })

  it('hydrates from localStorage on first access', () => {
    localStorage.setItem('pacer_token', 'tk')
    localStorage.setItem('pacer_student_id', '42')
    const s = useAuthStore()
    expect(s.isAuthenticated).toBe(true)
    expect(s.token).toBe('tk')
    expect(s.studentId).toBe(42)
  })

  it('login() stores token and student id', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ token: 'tk', student_id: 7 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useAuthStore()
    await s.login(7, '0000')
    expect(s.token).toBe('tk')
    expect(s.studentId).toBe(7)
    expect(localStorage.getItem('pacer_token')).toBe('tk')
    expect(localStorage.getItem('pacer_student_id')).toBe('7')
  })

  it('login() throws on bad credentials', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'unauthorized' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useAuthStore()
    await expect(s.login(7, 'x')).rejects.toThrow()
    expect(s.token).toBeNull()
  })

  it('logout() clears state and storage', () => {
    localStorage.setItem('pacer_token', 'tk')
    localStorage.setItem('pacer_student_id', '7')
    const s = useAuthStore()
    s.logout()
    expect(s.token).toBeNull()
    expect(s.studentId).toBeNull()
    expect(localStorage.getItem('pacer_token')).toBeNull()
    expect(localStorage.getItem('pacer_student_id')).toBeNull()
  })

  it('loadProfile() fetches and stores profile', async () => {
    localStorage.setItem('pacer_token', 'tk')
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ name: '小明', grade: 3 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const s = useAuthStore()
    await s.loadProfile()
    expect(s.profile?.name).toBe('小明')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pnpm test
```

Expected: FAIL — `@/stores/auth` not found.

- [ ] **Step 3: Write the implementation**

Create `src/stores/auth.ts`:

```ts
import { defineStore } from 'pinia'
import { apiFetch, setToken } from '@/api/client'

interface Profile {
  id?: number
  name?: string
  grade?: number
  school?: string | null
  target_school?: string | null
  stream?: string | null
}

interface LoginResponse {
  token: string
  student_id: number
}

const SID_KEY = 'pacer_student_id'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('pacer_token') as string | null,
    studentId: (() => {
      const raw = localStorage.getItem(SID_KEY)
      return raw === null ? null : Number(raw)
    })() as number | null,
    profile: null as Profile | null,
  }),
  getters: {
    isAuthenticated: (s) => s.token !== null,
  },
  actions: {
    async login(studentId: number, pin: string): Promise<void> {
      const r = await apiFetch<LoginResponse>('/auth/login', {
        method: 'POST',
        json: { student_id: studentId, pin },
      })
      this.token = r.token
      this.studentId = r.student_id
      setToken(r.token)
      localStorage.setItem(SID_KEY, String(r.student_id))
    },
    logout(): void {
      this.token = null
      this.studentId = null
      this.profile = null
      setToken(null)
      localStorage.removeItem(SID_KEY)
    },
    async loadProfile(): Promise<void> {
      if (!this.token) return
      this.profile = await apiFetch<Profile>('/profile/')
    },
  },
})
```

- [ ] **Step 4: Run test to verify pass**

```bash
pnpm test
```

Expected: all auth tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/stores/auth.ts \
        src/pacer/web-next/tests/unit/auth-store.test.ts
git commit -m "feat(web-next): add auth store"
```

---

## Task 8: `stores/ui.ts` — theme

**Files:**
- Create: `src/pacer/web-next/src/stores/ui.ts`
- Create: `src/pacer/web-next/tests/unit/ui-store.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/ui-store.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUiStore } from '@/stores/ui'

describe('useUiStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('defaults to light', () => {
    const s = useUiStore()
    expect(s.theme).toBe('light')
  })

  it('hydrates dark from localStorage', () => {
    localStorage.setItem('pacer_theme', 'dark')
    const s = useUiStore()
    expect(s.theme).toBe('dark')
  })

  it('applyTheme writes the documentElement attribute', () => {
    const s = useUiStore()
    s.theme = 'dark'
    s.applyTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('toggleTheme flips and persists', () => {
    const s = useUiStore()
    s.toggleTheme()
    expect(s.theme).toBe('dark')
    expect(localStorage.getItem('pacer_theme')).toBe('dark')
    s.toggleTheme()
    expect(s.theme).toBe('light')
    expect(localStorage.getItem('pacer_theme')).toBe('light')
  })

  it('applyTheme removes attribute for light theme', () => {
    document.documentElement.setAttribute('data-theme', 'dark')
    const s = useUiStore()
    s.theme = 'light'
    s.applyTheme()
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pnpm test
```

- [ ] **Step 3: Write implementation**

Create `src/stores/ui.ts`:

```ts
import { defineStore } from 'pinia'

type Theme = 'light' | 'dark'

const KEY = 'pacer_theme'

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: (localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light') as Theme,
  }),
  actions: {
    applyTheme(): void {
      if (this.theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark')
      } else {
        document.documentElement.removeAttribute('data-theme')
      }
    },
    toggleTheme(): void {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem(KEY, this.theme)
      this.applyTheme()
    },
  },
})
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pnpm test
```

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/stores/ui.ts \
        src/pacer/web-next/tests/unit/ui-store.test.ts
git commit -m "feat(web-next): add ui store (theme)"
```

---

## Task 9: `stores/session.ts` — minimal

**Files:**
- Create: `src/pacer/web-next/src/stores/session.ts`
- Create: `src/pacer/web-next/tests/unit/session-store.test.ts`

In Phase 1, this store just holds the `currentSid` and exposes `reset()`. Phase 3 will extend it with the list-of-sessions logic.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSessionStore } from '@/stores/session'

describe('useSessionStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts with no current session', () => {
    const s = useSessionStore()
    expect(s.currentSid).toBeNull()
  })

  it('reset clears the sid', () => {
    const s = useSessionStore()
    s.currentSid = 5
    s.reset()
    expect(s.currentSid).toBeNull()
  })
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pnpm test
```

- [ ] **Step 3: Write implementation**

Create `src/stores/session.ts`:

```ts
import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    currentSid: null as number | null,
  }),
  actions: {
    reset(): void { this.currentSid = null },
  },
})
```

- [ ] **Step 4: Run — expect PASS**

```bash
pnpm test
```

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/stores/session.ts \
        src/pacer/web-next/tests/unit/session-store.test.ts
git commit -m "feat(web-next): add minimal session store"
```

---

## Task 10: `stores/chat.ts` — messages and send

**Files:**
- Create: `src/pacer/web-next/src/stores/chat.ts`
- Create: `src/pacer/web-next/tests/unit/chat-store.test.ts`

Phase 1 protocol: no deltas. `send()` POSTs to `/message/send`, awaits the response (which contains the full text and session id), pushes assistant content. We also support receiving an `assistant_message` SSE event as the canonical path — the POST response and the SSE event will both deliver the same text; whichever arrives first sets it, the other is a no-op.

To keep behavior identical to today's frontend, the store:
- Pushes the user message immediately
- Shows a typing indicator (`isAwaiting = true`)
- Resolves the typing indicator when EITHER the POST returns OR the SSE arrives
- Adds the assistant message **exactly once** keyed by content identity

- [ ] **Step 1: Write the failing test**

Create `tests/unit/chat-store.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'

describe('useChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('pacer_token', 'tk')
  })

  it('starts empty and not awaiting', () => {
    const s = useChatStore()
    expect(s.messages).toEqual([])
    expect(s.isAwaiting).toBe(false)
  })

  it('send pushes a user message immediately', async () => {
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {})) as unknown as typeof fetch
    const s = useChatStore()
    void s.send('hello')
    expect(s.messages.length).toBe(1)
    expect(s.messages[0].role).toBe('user')
    expect(s.messages[0].content).toBe('hello')
    expect(s.isAwaiting).toBe(true)
  })

  it('send appends assistant from POST response when SSE has not arrived', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        text: 'world', session_id: 42, agent: 'subject_teacher',
      }), { status: 200, headers: { 'content-type': 'application/json' } }),
    )
    const s = useChatStore()
    await s.send('hello')
    expect(s.messages.length).toBe(2)
    expect(s.messages[1].role).toBe('assistant')
    expect(s.messages[1].content).toBe('world')
    expect(s.messages[1].agent).toBe('subject_teacher')
    expect(s.isAwaiting).toBe(false)
    const session = useSessionStore()
    expect(session.currentSid).toBe(42)
  })

  it('receiveAssistantMessage adds assistant and stops awaiting', () => {
    const s = useChatStore()
    s.isAwaiting = true
    s.receiveAssistantMessage({ session_id: 42, text: 'hi', agent: 'homeroom' })
    expect(s.messages.length).toBe(1)
    expect(s.messages[0].role).toBe('assistant')
    expect(s.messages[0].content).toBe('hi')
    expect(s.isAwaiting).toBe(false)
  })

  it('deduplicates assistant message when POST and SSE both deliver same content', async () => {
    const s = useChatStore()
    let resolveFetch!: (r: Response) => void
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(r => { resolveFetch = r })) as unknown as typeof fetch
    const pending = s.send('hello')
    s.receiveAssistantMessage({ session_id: 42, text: 'reply', agent: 'homeroom' })
    expect(s.messages.filter(m => m.role === 'assistant').length).toBe(1)
    resolveFetch(new Response(JSON.stringify({
      text: 'reply', session_id: 42, agent: 'homeroom',
    }), { status: 200, headers: { 'content-type': 'application/json' } }))
    await pending
    expect(s.messages.filter(m => m.role === 'assistant').length).toBe(1)
  })

  it('reset clears messages and isAwaiting', () => {
    const s = useChatStore()
    s.messages.push({ role: 'user', content: 'x' })
    s.isAwaiting = true
    s.reset()
    expect(s.messages).toEqual([])
    expect(s.isAwaiting).toBe(false)
  })

  it('send marks error when network fails', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('net'))
    const s = useChatStore()
    await s.send('hello')
    expect(s.isAwaiting).toBe(false)
    expect(s.messages.length).toBe(2)
    expect(s.messages[1].role).toBe('assistant')
    expect(s.messages[1].content).toMatch(/出错/)
  })
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pnpm test
```

- [ ] **Step 3: Write implementation**

Create `src/stores/chat.ts`:

```ts
import { defineStore } from 'pinia'
import { apiFetch } from '@/api/client'
import { useSessionStore } from './session'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  agent?: string
}

interface SendResponse {
  text: string
  session_id: number
  agent: string
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
  }),
  actions: {
    reset(): void {
      this.messages = []
      this.isAwaiting = false
      this._lastAssistantContent = null
    },

    receiveAssistantMessage(payload: AssistantPayload): void {
      const session = useSessionStore()
      session.currentSid = payload.session_id
      if (this._lastAssistantContent === payload.text) return
      this._lastAssistantContent = payload.text
      this.messages.push({ role: 'assistant', content: payload.text, agent: payload.agent })
      this.isAwaiting = false
    },

    async send(text: string): Promise<void> {
      const trimmed = text.trim()
      if (!trimmed) return
      this.messages.push({ role: 'user', content: trimmed })
      this.isAwaiting = true
      const session = useSessionStore()

      try {
        const r = await apiFetch<SendResponse>('/message/send', {
          method: 'POST',
          json: { text: trimmed, session_id: session.currentSid },
        })
        session.currentSid = r.session_id
        if (this._lastAssistantContent !== r.text) {
          this._lastAssistantContent = r.text
          this.messages.push({ role: 'assistant', content: r.text, agent: r.agent })
        }
      } catch {
        this.messages.push({ role: 'assistant', content: '出错了，请稍后重试。' })
      } finally {
        this.isAwaiting = false
      }
    },
  },
})
```

- [ ] **Step 4: Run — expect PASS**

```bash
pnpm test
```

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/stores/chat.ts \
        src/pacer/web-next/tests/unit/chat-store.test.ts
git commit -m "feat(web-next): add chat store with POST+SSE dedup"
```

---

## Task 11: `api/sse.ts` — SSE client

**Files:**
- Create: `src/pacer/web-next/src/api/sse.ts`
- Create: `src/pacer/web-next/tests/unit/sse.test.ts`

Phase 1 only consumes the legacy `assistant_message` event. The SSE consumer is exposed as a function `startSSE(token, handlers)` that returns a `stop()` function. Reconnection backoff is implemented; manual `stop()` cancels reconnection.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/sse.test.ts`:

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

describe('startSSE', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    _setEventSourceImpl(FakeEventSource as unknown as typeof EventSource)
    vi.useFakeTimers()
  })
  afterEach(() => {
    _resetEventSourceImpl()
    vi.useRealTimers()
  })

  it('opens with token in query string', () => {
    startSSE('tk', { onAssistantMessage: () => {} })
    expect(FakeEventSource.instances[0].url).toBe('/events/stream?token=tk')
  })

  it('dispatches assistant_message events', () => {
    const handler = vi.fn()
    startSSE('tk', { onAssistantMessage: handler })
    FakeEventSource.instances[0].emit('assistant_message', {
      session_id: 1, text: 'hi', agent: 'a',
    })
    expect(handler).toHaveBeenCalledWith({ session_id: 1, text: 'hi', agent: 'a' })
  })

  it('ignores ping events', () => {
    const handler = vi.fn()
    startSSE('tk', { onAssistantMessage: handler })
    FakeEventSource.instances[0].emit('ping', {})
    expect(handler).not.toHaveBeenCalled()
  })

  it('reconnects with backoff on error', () => {
    startSSE('tk', { onAssistantMessage: () => {} })
    expect(FakeEventSource.instances.length).toBe(1)
    FakeEventSource.instances[0].emitError()
    vi.advanceTimersByTime(1000)
    expect(FakeEventSource.instances.length).toBe(2)
    FakeEventSource.instances[1].emitError()
    vi.advanceTimersByTime(2000)
    expect(FakeEventSource.instances.length).toBe(3)
  })

  it('stop() prevents reconnection', () => {
    const stop = startSSE('tk', { onAssistantMessage: () => {} })
    FakeEventSource.instances[0].emitError()
    stop()
    vi.advanceTimersByTime(60000)
    expect(FakeEventSource.instances.length).toBe(1)
  })
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pnpm test
```

- [ ] **Step 3: Write implementation**

Create `src/api/sse.ts`:

```ts
export interface AssistantMessagePayload {
  session_id: number
  text: string
  agent: string
}

export interface SSEHandlers {
  onAssistantMessage: (payload: AssistantMessagePayload) => void
}

let EventSourceImpl: typeof EventSource = globalThis.EventSource

export function _setEventSourceImpl(impl: typeof EventSource): void {
  EventSourceImpl = impl
}
export function _resetEventSourceImpl(): void {
  EventSourceImpl = globalThis.EventSource
}

const BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]

export function startSSE(token: string, handlers: SSEHandlers): () => void {
  let stopped = false
  let attempt = 0
  let source: EventSource | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function open(): void {
    if (stopped) return
    source = new EventSourceImpl(`/events/stream?token=${encodeURIComponent(token)}`)
    source.addEventListener('assistant_message', (e: MessageEvent) => {
      attempt = 0
      try {
        handlers.onAssistantMessage(JSON.parse(e.data) as AssistantMessagePayload)
      } catch (err) {
        console.warn('sse parse error', err)
      }
    })
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

- [ ] **Step 4: Run — expect PASS**

```bash
pnpm test
```

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/api/sse.ts \
        src/pacer/web-next/tests/unit/sse.test.ts
git commit -m "feat(web-next): add sse client with backoff"
```

---

## Task 12: Composables — `useAutoScroll` + `useToast`

**Files:**
- Create: `src/pacer/web-next/src/composables/useAutoScroll.ts`
- Create: `src/pacer/web-next/src/composables/useToast.ts`
- Create: `src/pacer/web-next/tests/unit/composables.test.ts`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/composables.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useAutoScroll } from '@/composables/useAutoScroll'
import { useToast, _resetToastsForTest } from '@/composables/useToast'

describe('useAutoScroll', () => {
  it('scrolls element to bottom when watched value changes', async () => {
    const el = document.createElement('div')
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true })
    el.scrollTop = 0
    const r = ref(el as HTMLElement | null)
    const dep = ref(0)
    useAutoScroll(r, dep)
    dep.value = 1
    await nextTick()
    expect(el.scrollTop).toBe(1000)
  })
})

describe('useToast', () => {
  beforeEach(() => _resetToastsForTest())

  it('push adds a toast', () => {
    const { toasts, push } = useToast()
    push({ type: 'info', text: 'hi' })
    expect(toasts.value.length).toBe(1)
    expect(toasts.value[0].text).toBe('hi')
  })

  it('dismiss removes a toast', () => {
    const { toasts, push, dismiss } = useToast()
    const id = push({ type: 'error', text: 'bad' })
    dismiss(id)
    expect(toasts.value.length).toBe(0)
  })

  it('caps at 3 concurrent toasts', () => {
    const { toasts, push } = useToast()
    push({ type: 'info', text: '1' })
    push({ type: 'info', text: '2' })
    push({ type: 'info', text: '3' })
    push({ type: 'info', text: '4' })
    expect(toasts.value.length).toBe(3)
    expect(toasts.value[0].text).toBe('2')
  })
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pnpm test
```

- [ ] **Step 3: Write `useAutoScroll.ts`**

Create `src/composables/useAutoScroll.ts`:

```ts
import { watch, type Ref } from 'vue'

export function useAutoScroll(
  elementRef: Ref<HTMLElement | null>,
  dep: Ref<unknown>,
): void {
  watch(dep, () => {
    const el = elementRef.value
    if (!el) return
    queueMicrotask(() => {
      el.scrollTop = el.scrollHeight
    })
  }, { flush: 'post' })
}
```

- [ ] **Step 4: Write `useToast.ts`**

Create `src/composables/useToast.ts`:

```ts
import { ref } from 'vue'

export type ToastType = 'info' | 'error'

export interface Toast {
  id: number
  type: ToastType
  text: string
}

const _toasts = ref<Toast[]>([])
let _id = 0
const MAX = 3
const AUTO_DISMISS_MS = 3000

export function _resetToastsForTest(): void { _toasts.value = []; _id = 0 }

export function useToast() {
  function push(t: Omit<Toast, 'id'>): number {
    const id = ++_id
    _toasts.value = [..._toasts.value, { id, ...t }]
    while (_toasts.value.length > MAX) _toasts.value.shift()
    setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
    return id
  }
  function dismiss(id: number): void {
    _toasts.value = _toasts.value.filter(t => t.id !== id)
  }
  return { toasts: _toasts, push, dismiss }
}
```

- [ ] **Step 5: Run — expect PASS**

```bash
pnpm test
```

- [ ] **Step 6: Commit**

```bash
git add src/pacer/web-next/src/composables/ \
        src/pacer/web-next/tests/unit/composables.test.ts
git commit -m "feat(web-next): add useAutoScroll and useToast"
```

---

## Task 13: Router + App + main wiring

**Files:**
- Create: `src/pacer/web-next/src/router.ts`
- Modify: `src/pacer/web-next/src/App.vue`
- Modify: `src/pacer/web-next/src/main.ts`
- Create: `src/pacer/web-next/src/views/LoginView.vue` (stub for routing test)
- Create: `src/pacer/web-next/src/views/ChatView.vue` (stub for routing test)
- Create: `src/pacer/web-next/tests/unit/router.test.ts`

The full LoginView/ChatView are built in later tasks. Here we add minimal stubs so the router test can pass.

- [ ] **Step 1: Write the failing router test**

Create `tests/unit/router.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter } from '@/router'
import { useAuthStore } from '@/stores/auth'

describe('router guards', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('redirects authenticated user from / to /chat', async () => {
    localStorage.setItem('pacer_token', 'tk')
    localStorage.setItem('pacer_student_id', '1')
    const _auth = useAuthStore()
    void _auth
    const router = createRouter()
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/chat')
  })

  it('redirects unauthenticated user from /chat to /', async () => {
    const router = createRouter()
    await router.push('/chat')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('lets authenticated user visit /chat', async () => {
    localStorage.setItem('pacer_token', 'tk')
    const _auth = useAuthStore()
    void _auth
    const router = createRouter()
    await router.push('/chat')
    await router.isReady()
    expect(router.currentRoute.value.fullPath).toBe('/chat')
  })
})
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pnpm test
```

- [ ] **Step 3: Write the stub views**

Create `src/views/LoginView.vue`:
```vue
<script setup lang="ts"></script>
<template><div>login</div></template>
```

Create `src/views/ChatView.vue`:
```vue
<script setup lang="ts"></script>
<template><div>chat</div></template>
```

- [ ] **Step 4: Write `src/router.ts`**

```ts
import { createRouter as createVueRouter, createMemoryHistory, createWebHistory } from 'vue-router'
import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export function createRouter(): Router {
  const mode = (import.meta as unknown as { env: { MODE: string } }).env.MODE
  const isTest = mode === 'test'
  const router = createVueRouter({
    history: isTest ? createMemoryHistory() : createWebHistory(),
    routes: [
      { path: '/', name: 'login', component: () => import('@/views/LoginView.vue') },
      { path: '/chat', name: 'chat', component: () => import('@/views/ChatView.vue') },
      { path: '/chat/:sid', name: 'chat-sid', component: () => import('@/views/ChatView.vue') },
      { path: '/:path(.*)*', redirect: '/' },
    ],
  })
  router.beforeEach((to) => {
    const auth = useAuthStore()
    if (auth.isAuthenticated && to.name === 'login') return { path: '/chat' }
    if (!auth.isAuthenticated && to.name !== 'login') return { path: '/' }
    return true
  })
  return router
}
```

Note: the test imports `createRouter` (a factory) so each test gets a fresh instance.

- [ ] **Step 5: Update `src/App.vue`**

```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
onMounted(() => ui.applyTheme())
</script>

<template>
  <RouterView />
</template>
```

- [ ] **Step 6: Update `src/main.ts`**

```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'
import { createRouter } from './router'

const app = createApp(App)
app.use(createPinia())
app.use(createRouter())
app.mount('#app')
```

- [ ] **Step 7: Run — expect PASS**

```bash
pnpm test
pnpm typecheck
```

- [ ] **Step 8: Smoke check**

```bash
pnpm dev
```

Visit `http://localhost:5173`. Unauthenticated → see "login". Manually set token: `localStorage.setItem('pacer_token','x')` in DevTools console → reload → URL becomes `/chat`, see "chat". Clear: `localStorage.clear()` → reload → back to "login". `Ctrl+C`.

- [ ] **Step 9: Commit**

```bash
git add src/pacer/web-next/src/router.ts \
        src/pacer/web-next/src/App.vue \
        src/pacer/web-next/src/main.ts \
        src/pacer/web-next/src/views/LoginView.vue \
        src/pacer/web-next/src/views/ChatView.vue \
        src/pacer/web-next/tests/unit/router.test.ts
git commit -m "feat(web-next): wire router with auth guard"
```

---

## Task 14: `LoginView.vue` (full)

**Files:**
- Modify: `src/pacer/web-next/src/views/LoginView.vue`

No new unit tests — the form's behavior is exercised through the auth store (already tested). LoginView is visually verified.

- [ ] **Step 1: Replace `src/views/LoginView.vue`**

```vue
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { FluidBackground } from '@/utils/fluid-background'

const auth = useAuthStore()
const toast = useToast()
const router = useRouter()
const sid = ref('')
const pin = ref('')
const busy = ref(false)
const canvas = ref<HTMLCanvasElement | null>(null)
let fluid: FluidBackground | null = null

onMounted(() => {
  if (canvas.value) fluid = new FluidBackground(canvas.value)
})
onBeforeUnmount(() => {
  fluid?.destroy()
  fluid = null
})

async function onSubmit(): Promise<void> {
  if (busy.value) return
  const sidNum = Number(sid.value.trim())
  const pinTrim = pin.value.trim()
  if (!sidNum || !pinTrim) {
    toast.push({ type: 'error', text: '请填写学号和密码' })
    return
  }
  busy.value = true
  try {
    await auth.login(sidNum, pinTrim)
    await auth.loadProfile()
    await router.push('/chat')
  } catch {
    toast.push({ type: 'error', text: '学号或密码不对' })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-root">
    <canvas ref="canvas" class="login-canvas" aria-hidden="true" />
    <form class="login-card" @submit.prevent="onSubmit">
      <div class="login-brand">
        <span class="login-brand-seal" aria-hidden="true" />
        <span class="login-brand-text">pacer</span>
      </div>
      <p class="login-sub">高考陪跑AI</p>
      <label class="login-field">
        <span>学号</span>
        <input v-model="sid" type="text" inputmode="numeric" autofocus />
      </label>
      <label class="login-field">
        <span>密码</span>
        <input v-model="pin" type="password" />
      </label>
      <button type="submit" class="login-btn" :disabled="busy">
        {{ busy ? '正在进入…' : '进入 pacer' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-root {
  position: fixed; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--paper-0);
}
.login-canvas {
  position: fixed; inset: 0;
  width: 100%; height: 100%;
  background: transparent;
  pointer-events: none;
  z-index: 0;
}
.login-card {
  position: relative; z-index: 1;
  width: 360px;
  padding: var(--space-12) var(--space-8) var(--space-8);
  background: var(--paper-0);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-md);
}
.login-brand {
  display: flex; align-items: center; gap: var(--space-2);
  margin-bottom: var(--space-1);
}
.login-brand-seal {
  width: 10px; height: 10px;
  background: var(--seal);
  border-radius: var(--radius-xs);
}
.login-brand-text {
  font-family: var(--font-serif);
  font-size: 28px;
  letter-spacing: 0.04em;
  color: var(--ink-900);
}
.login-sub {
  font-family: var(--font-serif);
  color: var(--ink-500);
  font-size: 13px;
  margin-bottom: var(--space-8);
}
.login-field { display: block; margin-bottom: var(--space-4); }
.login-field span {
  display: block;
  font-size: 13px;
  color: var(--ink-700);
  margin-bottom: var(--space-2);
}
.login-field input {
  width: 100%;
  padding: 10px 12px;
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-sm);
  font-size: 15px;
  color: var(--ink-900);
  transition: border-color var(--motion-fast);
}
.login-field input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.login-btn {
  width: 100%;
  margin-top: var(--space-2);
  padding: 12px;
  background: var(--ink-900);
  color: var(--paper-0);
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  transition: opacity var(--motion-fast);
}
.login-btn:hover:not(:disabled) { opacity: 0.85; }
.login-btn:disabled { opacity: 0.5; cursor: default; }
</style>
```

- [ ] **Step 2: Run typecheck + tests (regression check)**

```bash
pnpm typecheck && pnpm test
```

Expected: green.

- [ ] **Step 3: Smoke check with the live backend**

In one terminal (repo root):
```bash
.venv/bin/uvicorn pacer.api.server:create_app --factory --reload --port 8000
```

In another terminal (`src/pacer/web-next/`):
```bash
pnpm dev
```

Visit `http://localhost:5173/`:
- WebGL ink follows the cursor
- Form is centered with serif "pacer" + vermilion square
- Wrong credentials → toast "学号或密码不对" (toast is invisible until Task 16, but the failed login is observable in the network tab — the form should not crash)
- Correct credentials → URL becomes `/chat`

Stop both with `Ctrl+C`.

- [ ] **Step 4: Commit**

```bash
git add src/pacer/web-next/src/views/LoginView.vue
git commit -m "feat(web-next): build login view with fluid background"
```

---

## Task 15: Primitives — `IconButton.vue` + `Toast.vue`

**Files:**
- Create: `src/pacer/web-next/src/components/IconButton.vue`
- Create: `src/pacer/web-next/src/components/Toast.vue`

- [ ] **Step 1: Create `IconButton.vue`**

```vue
<script setup lang="ts">
defineProps<{
  ariaLabel: string
  title?: string
}>()
</script>

<template>
  <button
    type="button"
    class="icon-btn"
    :aria-label="ariaLabel"
    :title="title ?? ariaLabel"
  >
    <slot />
  </button>
</template>

<style scoped>
.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border-radius: var(--radius-sm);
  color: var(--ink-500);
  transition: background var(--motion-fast), color var(--motion-fast);
}
.icon-btn:hover { background: var(--paper-2); color: var(--ink-900); }
.icon-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.icon-btn :slotted(svg) { width: 18px; height: 18px; }
</style>
```

- [ ] **Step 2: Create `Toast.vue`**

```vue
<script setup lang="ts">
import { useToast } from '@/composables/useToast'
const { toasts, dismiss } = useToast()
</script>

<template>
  <div class="toast-root" aria-live="polite">
    <button
      v-for="t in toasts"
      :key="t.id"
      class="toast"
      :class="t.type"
      type="button"
      @click="dismiss(t.id)"
    >
      {{ t.text }}
    </button>
  </div>
</template>

<style scoped>
.toast-root {
  position: fixed;
  right: var(--space-6);
  bottom: var(--space-6);
  display: flex; flex-direction: column; gap: var(--space-2);
  z-index: 100;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  text-align: left;
  padding: 10px 14px;
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  color: var(--ink-900);
  font-size: 13px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-hover);
  animation: toast-in var(--motion-mid);
}
.toast.error { border-color: var(--seal); }
@keyframes toast-in {
  from { transform: translateY(8px); opacity: 0; }
  to   { transform: translateY(0);   opacity: 1; }
}
</style>
```

- [ ] **Step 3: Mount Toast globally in `App.vue`**

Replace `src/App.vue`:

```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { useUiStore } from '@/stores/ui'
import Toast from '@/components/Toast.vue'

const ui = useUiStore()
onMounted(() => ui.applyTheme())
</script>

<template>
  <RouterView />
  <Toast />
</template>
```

- [ ] **Step 4: Verify typecheck + tests pass**

```bash
pnpm typecheck && pnpm test
```

- [ ] **Step 5: Smoke check**

`pnpm dev` → enter wrong credentials at `/` → toast appears bottom-right, dismisses in ~3s or on click.

- [ ] **Step 6: Commit**

```bash
git add src/pacer/web-next/src/components/IconButton.vue \
        src/pacer/web-next/src/components/Toast.vue \
        src/pacer/web-next/src/App.vue
git commit -m "feat(web-next): add icon button + global toast"
```

---

## Task 16: `Sidebar.vue` + `TopBar.vue`

**Files:**
- Create: `src/pacer/web-next/src/components/Sidebar.vue`
- Create: `src/pacer/web-next/src/components/TopBar.vue`

- [ ] **Step 1: Create `Sidebar.vue`**

```vue
<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'

const auth = useAuthStore()
const session = useSessionStore()
const chat = useChatStore()
const router = useRouter()

const presets = [
  '帮我制定今天的学习计划',
  '帮我复盘最近的错题',
  '生成今天的学习日报',
]

function newChat(): void {
  session.reset()
  chat.reset()
  void router.push('/chat')
}

async function logout(): Promise<void> {
  auth.logout()
  session.reset()
  chat.reset()
  await router.push('/')
}

function preset(text: string): void {
  void chat.send(text)
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <span class="brand-seal" aria-hidden="true" />
      <span class="brand-text">pacer</span>
    </div>

    <button class="row primary" type="button" @click="newChat">新对话</button>

    <div class="section">快捷入口</div>
    <button
      v-for="p in presets"
      :key="p"
      class="row"
      type="button"
      @click="preset(p)"
    >
      {{ p === '帮我制定今天的学习计划' ? '今日计划'
        : p === '帮我复盘最近的错题'   ? '错题复盘'
        : '学习日报' }}
    </button>

    <div class="spacer" />
    <div class="footer">
      <button class="footer-row" type="button" @click="logout">退出</button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 240px;
  min-width: 240px;
  background: var(--paper-1);
  border-right: 1px solid var(--ink-300);
  display: flex; flex-direction: column;
  padding: var(--space-5) var(--space-3);
  gap: var(--space-1);
}
.brand {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-5);
}
.brand-seal {
  width: 9px; height: 9px;
  background: var(--seal);
  border-radius: var(--radius-xs);
}
.brand-text {
  font-family: var(--font-serif);
  font-size: 18px;
  letter-spacing: 0.04em;
}
.row {
  text-align: left;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--ink-900);
  transition: background var(--motion-fast);
}
.row:hover { background: var(--paper-2); }
.row.primary { font-weight: 500; }
.section {
  font-size: 11px;
  color: var(--ink-500);
  letter-spacing: 0.08em;
  padding: var(--space-4) var(--space-3) var(--space-1);
}
.spacer { flex: 1; }
.footer { border-top: 1px solid var(--ink-300); padding-top: var(--space-2); }
.footer-row {
  text-align: left;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--ink-700);
  transition: background var(--motion-fast);
  width: 100%;
}
.footer-row:hover { background: var(--paper-2); color: var(--ink-900); }

@media (max-width: 640px) {
  .sidebar { display: none; }
}
</style>
```

- [ ] **Step 2: Create `TopBar.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import IconButton from './IconButton.vue'

const auth = useAuthStore()
const ui = useUiStore()
const title = computed(() => {
  const n = auth.profile?.name ?? '同学'
  return `${n} · pacer`
})
</script>

<template>
  <header class="topbar">
    <div class="title">{{ title }}</div>
    <IconButton aria-label="切换主题" @click="ui.toggleTheme">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
      </svg>
    </IconButton>
  </header>
</template>

<style scoped>
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-3) var(--space-6);
  border-bottom: 1px solid var(--ink-300);
  background: var(--paper-0);
}
.title {
  font-family: var(--font-serif);
  font-size: 15px;
  letter-spacing: 0.04em;
  color: var(--ink-900);
}
</style>
```

- [ ] **Step 3: Typecheck**

```bash
pnpm typecheck
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/pacer/web-next/src/components/Sidebar.vue \
        src/pacer/web-next/src/components/TopBar.vue
git commit -m "feat(web-next): add sidebar and topbar"
```

---

## Task 17: `EmptyState.vue` + `SuggestionChip.vue`

**Files:**
- Create: `src/pacer/web-next/src/components/SuggestionChip.vue`
- Create: `src/pacer/web-next/src/components/EmptyState.vue`

- [ ] **Step 1: Create `SuggestionChip.vue`**

```vue
<script setup lang="ts">
defineProps<{ label: string }>()
defineEmits<{ click: [] }>()
</script>

<template>
  <button type="button" class="chip" @click="$emit('click')">
    {{ label }}
  </button>
</template>

<style scoped>
.chip {
  padding: 8px 14px;
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--ink-700);
  background: var(--paper-0);
  transition: border-color var(--motion-fast), color var(--motion-fast), background var(--motion-fast);
}
.chip:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-soft);
}
</style>
```

- [ ] **Step 2: Create `EmptyState.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import SuggestionChip from './SuggestionChip.vue'

const auth = useAuthStore()
const emit = defineEmits<{ preset: [text: string] }>()

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const name = computed(() => auth.profile?.name ?? '同学')

const suggestions = [
  '帮我讲一道导数题',
  '帮我制定今天的学习计划',
  '帮我分析一下这道错题',
  '最近有点焦虑，想聊聊',
]
</script>

<template>
  <div class="empty">
    <h1>{{ greeting }}，{{ name }}</h1>
    <p>我是你的 AI 班主任。试试下面这些，或者直接问我任何问题。</p>
    <div class="chips">
      <SuggestionChip
        v-for="s in suggestions"
        :key="s"
        :label="s"
        @click="emit('preset', s)"
      />
    </div>
  </div>
</template>

<style scoped>
.empty {
  flex: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: var(--space-12) var(--space-8);
  text-align: center;
}
.empty h1 {
  font-family: var(--font-serif);
  font-size: 28px;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: var(--ink-900);
  margin-bottom: var(--space-3);
}
.empty p {
  color: var(--ink-500);
  font-size: 14px;
  max-width: 420px;
  margin-bottom: var(--space-8);
}
.chips {
  display: flex; flex-wrap: wrap; gap: var(--space-2);
  justify-content: center;
  max-width: 540px;
}
</style>
```

- [ ] **Step 3: Typecheck**

```bash
pnpm typecheck
```

- [ ] **Step 4: Commit**

```bash
git add src/pacer/web-next/src/components/SuggestionChip.vue \
        src/pacer/web-next/src/components/EmptyState.vue
git commit -m "feat(web-next): add empty state and suggestion chip"
```

---

## Task 18: Message components

**Files:**
- Create: `src/pacer/web-next/src/components/MarkdownRender.vue`
- Create: `src/pacer/web-next/src/components/UserMessage.vue`
- Create: `src/pacer/web-next/src/components/AssistantMessage.vue`

- [ ] **Step 1: Create `MarkdownRender.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { mdToHtml } from '@/utils/markdown'

const props = defineProps<{ text: string }>()
const html = computed(() => mdToHtml(props.text))
</script>

<template>
  <div class="md" v-html="html" />
</template>

<style scoped>
.md { font-size: 15px; line-height: 1.7; color: var(--ink-900); }
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
  font-size: 13px;
  line-height: 1.5;
}
.md :deep(strong) { color: var(--ink-900); font-weight: 600; }
</style>
```

- [ ] **Step 2: Create `UserMessage.vue`**

```vue
<script setup lang="ts">
defineProps<{ content: string }>()
</script>

<template>
  <div class="row">
    <div class="bubble">{{ content }}</div>
  </div>
</template>

<style scoped>
.row {
  display: flex; justify-content: flex-end;
  margin: 12px 0;
}
.bubble {
  max-width: 80%;
  padding: 10px 14px;
  background: var(--accent-soft);
  color: var(--ink-900);
  border-radius: var(--radius-md);
  border-bottom-right-radius: var(--radius-xs);
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
</style>
```

- [ ] **Step 3: Create `AssistantMessage.vue`**

```vue
<script setup lang="ts">
import MarkdownRender from './MarkdownRender.vue'

defineProps<{ content: string; agent?: string }>()

function agentLabel(agent: string | undefined): string {
  if (agent === 'subject_teacher') return '学科老师'
  if (agent === 'mood_companion') return '心态陪伴'
  return ''
}
</script>

<template>
  <div class="row">
    <span v-if="agentLabel(agent)" class="badge">{{ agentLabel(agent) }}</span>
    <MarkdownRender :text="content" />
  </div>
</template>

<style scoped>
.row {
  position: relative;
  padding: 4px 0 4px 16px;
  margin: 14px 0;
  border-left: 2px solid var(--accent);
}
.badge {
  display: inline-block;
  font-family: var(--font-serif);
  font-size: 11px;
  color: var(--ink-500);
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}
</style>
```

- [ ] **Step 4: Typecheck**

```bash
pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add src/pacer/web-next/src/components/MarkdownRender.vue \
        src/pacer/web-next/src/components/UserMessage.vue \
        src/pacer/web-next/src/components/AssistantMessage.vue
git commit -m "feat(web-next): add message components"
```

---

## Task 19: `MessageList.vue`

**Files:**
- Create: `src/pacer/web-next/src/components/MessageList.vue`

- [ ] **Step 1: Create the file**

```vue
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAutoScroll } from '@/composables/useAutoScroll'
import UserMessage from './UserMessage.vue'
import AssistantMessage from './AssistantMessage.vue'
import EmptyState from './EmptyState.vue'

const emit = defineEmits<{ preset: [text: string] }>()
const chat = useChatStore()
const scrollEl = ref<HTMLElement | null>(null)

const tick = computed(() => `${chat.messages.length}-${chat.isAwaiting ? 1 : 0}`)
useAutoScroll(scrollEl, tick)
</script>

<template>
  <div ref="scrollEl" class="list">
    <div class="inner">
      <EmptyState v-if="chat.messages.length === 0" @preset="emit('preset', $event)" />
      <template v-else>
        <template v-for="(m, i) in chat.messages" :key="i">
          <UserMessage v-if="m.role === 'user'" :content="m.content" />
          <AssistantMessage v-else :content="m.content" :agent="m.agent" />
        </template>
        <div v-if="chat.isAwaiting" class="typing" aria-label="正在输入">
          <span /><span /><span />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-8) 0;
  scroll-behavior: smooth;
}
.inner {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 var(--space-6);
  display: flex; flex-direction: column;
}
.typing {
  display: flex; gap: 5px;
  padding: 14px 0 14px 18px;
  border-left: 2px solid var(--accent);
  margin: 14px 0;
}
.typing span {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--ink-300);
  animation: bounce 1.4s infinite both;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-5px); opacity: 1; }
}
</style>
```

- [ ] **Step 2: Typecheck**

```bash
pnpm typecheck
```

- [ ] **Step 3: Commit**

```bash
git add src/pacer/web-next/src/components/MessageList.vue
git commit -m "feat(web-next): add message list"
```

---

## Task 20: `Composer.vue`

**Files:**
- Create: `src/pacer/web-next/src/components/Composer.vue`

- [ ] **Step 1: Create the file**

```vue
<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useToast } from '@/composables/useToast'
import { apiFetch, ApiError } from '@/api/client'
import IconButton from './IconButton.vue'

const chat = useChatStore()
const toast = useToast()
const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const MAX_TEXT = 8000

function autoResize(): void {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}

async function onSend(): Promise<void> {
  if (chat.isAwaiting) return
  const t = text.value.trim()
  if (!t) return
  if (t.length > MAX_TEXT) {
    toast.push({ type: 'error', text: '消息过长' })
    return
  }
  text.value = ''
  await nextTick()
  autoResize()
  await chat.send(t)
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void onSend()
  }
}

interface UploadResponse {
  auto_filled_stem?: string
  auto_routed_to_subject?: string
}

async function onFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    toast.push({ type: 'error', text: '只支持 jpg / png / webp' })
    input.value = ''
    return
  }
  if (file.size > 8 * 1024 * 1024) {
    toast.push({ type: 'error', text: '图片不能超过 8MB' })
    input.value = ''
    return
  }
  uploading.value = true
  const fd = new FormData()
  fd.append('file', file)
  try {
    const r = await apiFetch<UploadResponse>('/upload/image', { method: 'POST', body: fd })
    if (r.auto_filled_stem) {
      text.value = r.auto_filled_stem
      await nextTick()
      autoResize()
      textarea.value?.focus()
    }
  } catch (err) {
    const msg = err instanceof ApiError ? err.detail : '上传失败'
    toast.push({ type: 'error', text: msg })
  } finally {
    uploading.value = false
    input.value = ''
  }
}
</script>

<template>
  <div class="wrap">
    <div class="composer">
      <IconButton
        aria-label="上传题目图片"
        :title="uploading ? '正在上传…' : '上传题目图片'"
        @click="fileInput?.click()"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <path d="M21 15l-5-5L5 21"/>
        </svg>
      </IconButton>
      <textarea
        ref="textarea"
        v-model="text"
        class="input"
        rows="1"
        placeholder="输入消息，或拍照上传题目…"
        @keydown="onKeydown"
        @input="autoResize"
      />
      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        @change="onFile"
      />
      <button
        type="button"
        class="send"
        :disabled="chat.isAwaiting || !text.trim()"
        @click="onSend"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <path d="M2 21l21-9L2 3v7l15 2-15 2z"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  padding: var(--space-3) var(--space-6) var(--space-5);
  background: var(--paper-0);
}
.composer {
  max-width: 720px; margin: 0 auto;
  display: flex; gap: var(--space-2); align-items: flex-end;
  background: var(--paper-1);
  border: 1px solid var(--ink-300);
  border-radius: var(--radius-md);
  padding: 6px 6px 6px 12px;
  transition: border-color var(--motion-fast), box-shadow var(--motion-fast);
}
.composer:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.input {
  flex: 1;
  border: none; outline: none; resize: none;
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.5;
  padding: 8px 0;
  max-height: 180px;
  background: transparent;
  color: var(--ink-900);
}
.input::placeholder { color: var(--ink-500); }
.send {
  width: 32px; height: 32px;
  border-radius: var(--radius-sm);
  background: var(--ink-900);
  color: var(--paper-0);
  display: inline-flex; align-items: center; justify-content: center;
  transition: opacity var(--motion-fast), transform var(--motion-fast);
}
.send:hover:not(:disabled) { opacity: 0.85; }
.send:active:not(:disabled) { transform: scale(0.95); }
.send:disabled { opacity: 0.35; cursor: default; }
</style>
```

- [ ] **Step 2: Typecheck**

```bash
pnpm typecheck
```

- [ ] **Step 3: Commit**

```bash
git add src/pacer/web-next/src/components/Composer.vue
git commit -m "feat(web-next): add composer"
```

---

## Task 21: `AppShell.vue` + `ChatView.vue` wiring + SSE startup

**Files:**
- Create: `src/pacer/web-next/src/components/AppShell.vue`
- Modify: `src/pacer/web-next/src/views/ChatView.vue`
- Modify: `src/pacer/web-next/src/main.ts`

- [ ] **Step 1: Create `AppShell.vue`**

```vue
<script setup lang="ts">
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
</script>

<template>
  <div class="shell">
    <Sidebar />
    <main class="main">
      <TopBar />
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--paper-0);
}
.main {
  flex: 1;
  display: flex; flex-direction: column;
  min-width: 0;
}
</style>
```

- [ ] **Step 2: Replace `src/views/ChatView.vue`**

```vue
<script setup lang="ts">
import AppShell from '@/components/AppShell.vue'
import MessageList from '@/components/MessageList.vue'
import Composer from '@/components/Composer.vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
function onPreset(text: string): void { void chat.send(text) }
</script>

<template>
  <AppShell>
    <MessageList @preset="onPreset" />
    <Composer />
  </AppShell>
</template>
```

- [ ] **Step 3: Update `src/main.ts` to start SSE when authenticated**

```ts
import { createApp, watch } from 'vue'
import { createPinia } from 'pinia'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'
import { createRouter } from './router'
import { useAuthStore } from './stores/auth'
import { useChatStore } from './stores/chat'
import { startSSE } from './api/sse'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(createRouter())

const auth = useAuthStore(pinia)
const chat = useChatStore(pinia)

let stopSSE: (() => void) | null = null

function reconcileSSE(token: string | null): void {
  if (stopSSE) { stopSSE(); stopSSE = null }
  if (token !== null) {
    stopSSE = startSSE(token, {
      onAssistantMessage: (p) => chat.receiveAssistantMessage(p),
    })
  }
}

reconcileSSE(auth.token)
watch(() => auth.token, reconcileSSE)

if (auth.isAuthenticated) {
  void auth.loadProfile()
}

app.mount('#app')
```

- [ ] **Step 4: Typecheck + tests**

```bash
pnpm typecheck && pnpm test
```

Expected: green. (Note: `main.ts` is excluded from unit tests; its behavior is verified in the next smoke step.)

- [ ] **Step 5: Smoke check end-to-end**

Two terminals.

Backend (repo root):
```bash
.venv/bin/uvicorn pacer.api.server:create_app --factory --reload --port 8000
```

Frontend (`src/pacer/web-next/`):
```bash
pnpm dev
```

Then:

1. Visit `http://localhost:5173/` → see login with ink background
2. Log in with a valid student → URL becomes `/chat`
3. See greeting + 4 suggestion chips
4. Click a chip → user message appears right-aligned, typing dots appear left, assistant reply appears with a 2px accent rule on the left
5. Type a free-form message + `Enter` → same flow
6. Click upload icon → choose an image → stem auto-fills the textarea
7. Toggle theme (top-right) → paper goes dark, ink goes warm white
8. Click "新对话" → messages clear, greeting reappears
9. Click "退出" → URL returns to `/`, ink background restarts
10. Re-login → still works

Each step must be observed, not assumed. Note any visual or behavioral issues.

- [ ] **Step 6: Commit**

```bash
git add src/pacer/web-next/src/components/AppShell.vue \
        src/pacer/web-next/src/views/ChatView.vue \
        src/pacer/web-next/src/main.ts
git commit -m "feat(web-next): wire chat view with SSE bootstrap"
```

---

## Task 22: Build artifact + end-of-phase verification

**Files:** none modified; this is a verification task.

- [ ] **Step 1: Build the SPA**

```bash
cd src/pacer/web-next
pnpm build
```

Expected:
- `vue-tsc --noEmit` passes (strict typecheck)
- `vite build` produces `dist/index.html`, `dist/assets/*.js`, `dist/assets/*.css`

- [ ] **Step 2: Run backend serving the built SPA**

From repo root:
```bash
.venv/bin/uvicorn pacer.api.server:create_app --factory --port 8000
```

Visit `http://localhost:8000/` — should serve the **built** Vue SPA (not the legacy `web/index.html`).

Verify the same 10-step smoke list from Task 21 against the production-built version (no Vite dev server proxy involved).

- [ ] **Step 3: Run the full backend test suite**

```bash
pytest
```

Expected: all tests pass (the static-serving test from Task 1 still green; legacy code untouched).

- [ ] **Step 4: Run the full frontend test suite**

```bash
cd src/pacer/web-next
pnpm test
pnpm typecheck
```

Expected: green.

- [ ] **Step 5: Verify legacy still works (rollback drill)**

```bash
mv src/pacer/web-next/dist /tmp/pacer-dist-saved
.venv/bin/uvicorn pacer.api.server:create_app --factory --port 8000
```

Visit `http://localhost:8000/` — should now serve the legacy `web/index.html` (unchanged, original behavior).

Restore:
```bash
mv /tmp/pacer-dist-saved src/pacer/web-next/dist
```

- [ ] **Step 6: Final commit (only if any leftover changes)**

If the previous tasks left untracked files (e.g. updated `pnpm-lock.yaml`), stage and commit:
```bash
git status
git add -A
git commit -m "chore(web-next): finalize phase 1"
```

If nothing remains, skip.

- [ ] **Step 7: Mark phase complete**

Append a single line to `docs/superpowers/specs/2026-05-19-frontend-optimization-design.md` under a new `## Progress` section:
```markdown
## Progress

- [x] Phase 1 (2026-MM-DD): Vite + Vue 3 scaffold, visual rewrite, chat parity
- [ ] Phase 2: streaming + Markdown enhancements
- [ ] Phase 3: session history
- [ ] Phase 4: profile / errors / plan views; delete legacy web/
```

Then:
```bash
git add docs/superpowers/specs/2026-05-19-frontend-optimization-design.md
git commit -m "docs(spec): mark phase 1 complete"
```

---

## Phase 1 Acceptance

Run this checklist by hand before declaring Phase 1 done. **Each item must be visually verified — "looks fine" is not acceptance.**

- [ ] Login with valid credentials lands on `/chat` and shows the time-aware greeting + name
- [ ] Login with bad credentials shows a toast and stays on `/`
- [ ] Sending a message: user bubble right-aligned with `--accent-soft` background, typing dots appear, assistant reply appears with a 2px `--accent` left rule (no bubble)
- [ ] Suggestion chips on the empty state work
- [ ] Image upload auto-fills the textarea with the recognized stem
- [ ] Theme toggle switches paper light ↔ dark; contrast holds; no SaaS blue anywhere
- [ ] "新对话" clears messages, returns to greeting
- [ ] "退出" returns to `/`, the ink background reappears
- [ ] SSE auto-reconnects (kill backend → wait → restart → frontend recovers without page reload)
- [ ] Markdown: `**bold**`, `` `code` ``, fenced code render
- [ ] Production build (`pnpm build`) is served by FastAPI at port 8000 and behaves identically to dev
- [ ] Removing `dist/` falls back to legacy `web/` (rollback works)
- [ ] No emoji, no large radii, no Material shadows, no blue
- [ ] `pnpm test`, `pnpm typecheck`, `pytest` all green

If any item fails, add a fix task and resolve it before closing Phase 1.

---

## What's Next (Phases 2–4 outline)

These are **not** plans yet — they are stubs to be expanded into separate plan documents when Phase 1 is complete.

### Phase 2 — Streaming + Markdown enhancement
- Backend: `LLMClient.stream_complete` (OpenAI-compat); `Orchestrator.handle_streaming`; `Message.status` schema + alembic migration; SSE events `assistant_start` / `assistant_delta` / `assistant_done`; `POST /message/{id}/stop`
- Frontend: chat-store delta accumulation + placeholder model; cancellable in-flight stream; `markdown-it` + KaTeX + highlight.js replacing `utils/markdown.ts`
- New plan file: `docs/superpowers/plans/<date>-frontend-phase-2.md`

### Phase 3 — Session history
- Backend: `GET /sessions`, `GET /sessions/:sid/messages`, `PATCH /sessions/:sid`, `DELETE /sessions/:sid`; emit `session_created` SSE
- Frontend: extend `sessionStore` with list + CRUD; render in Sidebar; route param `/chat/:sid` loads history
- New plan file: `docs/superpowers/plans/<date>-frontend-phase-3.md`

### Phase 4 — Profile, errors, plan views; cleanup
- Backend: `GET /errors`, `GET /errors/:id`, `GET /plans`, `GET /plans/:id`, `GET /mastery`
- Frontend: views + routing for `/me /errors /plan`; profile form; toast on save
- Cleanup: delete `src/pacer/web/`; remove `_mount_legacy` and `LEGACY_WEB_DIR`
- New plan file: `docs/superpowers/plans/<date>-frontend-phase-4.md`
