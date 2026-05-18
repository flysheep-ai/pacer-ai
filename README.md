# pacer-ai

> AI 教育陪伴助手 · 高考陪跑者

面向中国高三学生的多 Agent AI 陪伴系统。不是替你跑，而是陪你跑完高考这一程——学业陪伴、计划督促、心态支持。

## 核心架构

**3 个 Agent 协作**：
- 🎓 **班主任** — 永远在场的总调度，意图路由 / 计划生成 / 串场
- 📚 **学科老师** — 1 个 agent + 6 科 skill 库，按需动态加载
- 💗 **心态陪伴** — 不评判式倾听，含红线检测

**一日陪伴闭环**：
```
07:00 🌅 早安 + 今日计划
  ↓
随时 💬 答疑 / 讲题（拍照或文字）
  ↓
18:00 📝 错题复盘 + 变式训练
  ↓
21:30 📊 学习日报 + 情绪 check-in
```

## 技术栈

- **后端**：Python 3.11+ / FastAPI / SQLite + SQLAlchemy / APScheduler
- **LLM**：Claude Sonnet 4.6（主对话） + Haiku 4.5（路由），全部可配
- **视觉**：商用多模态 LLM API（理解题目图片）
- **前端**：平板 Web 页面（用户自有硬件）

## 设计文档

完整设计见 [`docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md`](docs/superpowers/specs/2026-05-18-ai-edu-companion-design.md)（12 节 · 24 条设计决策）。

## 状态

🚧 设计阶段完成，实施计划生成中。

## License

Apache License 2.0
