# pacer-ai

> AI 教育陪伴助手 · 高考陪跑者

**简体中文** · [English](README.md)

<p align="center">
  <img src="pic/readme.png" alt="pacer-ai 概览" width="720">
</p>

面向高三学生的多 Agent AI 陪伴系统。三个角色（班主任 / 学科老师 / 心态陪伴）共享同一个对话，背后是跨月积累的长期学生记忆。不是替你跑——是陪你跑完高考这一程。

---

## 功能亮点

- **多 Agent 对话** — 一个聊天窗口，三个 AI 角色。Haiku 路由模型按意图自动切换，学生感知到的是"一个一直在的陪伴者"。
- **拍照答疑** — 拍一道数学题，自动 OCR → 识别学科 → 分步讲解。
- **错题本** — 每道错题自动记录。点击「开始复盘」进入对话，学科老师重讲 → 出变式题 → 批改 → 更新掌握度。
- **掌握度追踪** — 6 大学科、207 个知识点的得分可视化。最弱 5 项高亮，一键跳转复习。
- **计划勾选** — 每早生成的计划可逐条勾选完成，日报读的是真实完成率。
- **一日陪伴闭环** — 07:00 早安计划 → 随时答疑 → 18:00 错题复盘 → 21:30 日报 → 22:30 晚安。
- **红线兜底** — 关键词扫描 + LLM 二次确认，触发自伤信号时直接短路返回危机热线，主对话模型不会被调用。
- **长期记忆** — 384 维向量嵌入（all-MiniLM-L6-v2），余弦去重，自动从对话中提取值得记住的事实。

---

## 快速开始

```bash
# 1. 克隆并安装
git clone git@github.com:flysheep-ai/pacer-ai.git
cd pacer-ai
pip install -e '.[dev]'

# 2. 配置环境
cp .env.example .env
# 编辑 .env — 填入 LLM_API_KEY 和 PACER_INTERNAL_TOKEN

# 3. 数据库迁移 + 种子数据
alembic upgrade head
python scripts/seed_dev_student.py
python scripts/seed_knowledge_points.py

# 4. 启动后端（终端 1）
uvicorn pacer.api.server:create_app --factory --reload --port 8001

# 5. 启动调度器（终端 2）
python -m pacer.scheduler.runner

# 6. 启动前端（终端 3）
cd src/pacer/web-next && pnpm install && pnpm dev

# 浏览器打开 http://localhost:5173 — 学号 1，PIN 123456 登录
```

---

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Python 3.11+ · FastAPI · SQLAlchemy · Alembic |
| 前端 | Vue 3 · Vite · Pinia · TypeScript |
| 主模型 | Claude Sonnet 4.6 |
| 路由模型 | Claude Haiku 4.5 |
| 嵌入模型 | all-MiniLM-L6-v2（384 维，numpy） |
| 数据库 | SQLite（开发） → Postgres（生产） |
| 调度 | APScheduler（独立进程） |
| 鉴权 | bcrypt PIN + DB 持久化 Token（带 TTL） |

---

## 架构

```
POST /message/send
  ├─ 红线扫描 → 触发？→ 直接返回危机资源（不调 LLM）
  ├─ 创建 streaming 占位消息 → 202 应答
  └─ 后台任务（独立 DB session）
       ├─ RouterLLM (Haiku): 意图 → 选择 Agent
       ├─ AgentLoop.run_streaming（工具 ↔ LLM）
       │    ├─ 班主任: 计划、画像、错题、记忆
       │    ├─ 学科老师: 技能库、视觉、变式题
       │    └─ 心态陪伴: 记录情绪、交回班主任
       ├─ SSE 增量 → EventBus → GET /events/stream
       ├─ LLMUsage 用量入库
       └─ 记忆提取器（每 N 轮触发一次）
```

测试：`tests/{unit,integration,api,e2e}/` · `pytest`（81 条）· `pnpm test`（vitest，66 条）

---

## 开发

```bash
# 后端
pytest                              # 全部测试
pytest tests/unit/test_memory.py    # 单个文件
alembic revision --autogenerate -m "描述"

# 前端
cd src/pacer/web-next
pnpm dev          # 开发服务器（端口 5173）
pnpm build        # 生产构建
pnpm test         # vitest
pnpm typecheck    # vue-tsc --noEmit

# 种子数据
python scripts/seed_dev_student.py        # 学生 id=1, pin=123456
python scripts/seed_knowledge_points.py   # ~200 条高考知识点
```

完整设计文档：[`docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md`](docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md)

---

## 许可证

Apache License 2.0
