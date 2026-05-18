# AI 教育陪伴助手 · 设计文档

**日期**：2026-05-18
**目标**：基于 Vibe-Trading 架构，构建面向高三学生的全程陪伴型 AI 产品

---

## 1. 产品定义

### 1.1 目标用户
高三学生（中国大陆，高考备考阶段）。

### 1.2 产品定位
**全程陪伴型 AI**，扮演"懂这个学生 + 能教他/她"的角色，覆盖学习与生活（学业陪伴 + 计划督促 + 心态支持）。区别于：
- 错题工具型产品（如作业帮）：本产品强调"懂学生 + 主动陪伴"
- 单科辅导工具（如学而思 AI）：本产品全学科覆盖 + 跨学科串场
- 通用对话 AI（如 ChatGPT）：本产品有持久学生画像 + 主动唤起

### 1.3 载体
学习平板（用户已有硬件）+ Web 前端 + Python 后端。中心-客户端架构，所有学生共用一个中心后端 + SQLite 数据库，平板做客户端。

### 1.4 MVP 范围
**4 个核心陪伴场景** 构成一日闭环：

| 场景 | 时段 | 触发 | 主导 Agent |
|------|------|------|----------|
| 🌅 早安 + 今日计划 | 07:00 | Scheduler | 班主任 |
| 💬 答疑 / 讲题 | 随时 | 学生主动 | 学科老师 |
| 📝 错题复盘 | 18:00 | Scheduler | 班主任 → 学科老师 |
| 📊 学习日报 + 情绪 check | 21:30 | Scheduler | 班主任 → 心态陪伴（条件性） |

**学科覆盖**：主课 6 门（语文 / 数学 / 英语 / 物理 / 化学 / 生物）。每科有独立 skill 库。

**学习数据**：题库内容 + 知识点图谱由用户自行导入；学生使用过程产生的错题、记忆、情绪日志由系统自动沉淀。

---

## 2. 架构设计

### 2.1 整体分层

```
┌─────────────────────────────────────────────────────────────┐
│                  📱 前端 (平板 Web 页面)                     │
│    对话流UI · 任务卡 · 错题本 · 拍照入口 · SSE 接收          │
└──────────────────┬───────────────────────▲──────────────────┘
                   │ HTTP/POST              │ SSE 流
                   ▼                        │
┌─────────────────────────────────────────────────────────────┐
│              🌐 FastAPI 接入层 (api_server.py)               │
│   /auth/login · /message/send · /events/stream · /upload    │
└──────────────────┬───────────────────────▲──────────────────┘
                   ▼                        │
┌─────────────────────────────────────────────────────────────┐
│              📞 SessionService (会话生命周期)                │
│   消息持久化 → 触发 Orchestrator → 发布 SSE 事件             │
└──────────────────┬───────────────────────▲──────────────────┘
                   ▼                        │
┌─────────────────────────────────────────────────────────────┐
│         🎓 班主任 Orchestrator (自研多 Agent 编排)            │
│   1. 接收所有消息 / 系统事件                                  │
│   2. 路由 LLM (轻量) → 意图标签 + subject                    │
│   3. 委派给对应 Agent + 拼装上下文                           │
└────┬──────────────┬──────────────────┬─────────────────────┘
     ▼              ▼                  ▼
 ┌───────┐   ┌──────────┐         ┌──────────┐
 │班主任 │   │学科老师  │         │心态陪伴   │
 │Agent  │   │Agent     │         │Agent     │
 │(ReAct)│   │(ReAct)   │         │(ReAct)   │
 └───┬───┘   └─────┬────┘         └─────┬────┘
     │             │                     │
     └─────────────┼─────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  🛠️ 共享工具层 (ToolRegistry · 复用 Vibe BaseTool)            │
└─────┬─────────────────┬─────────────────┬───────────────────┘
      ▼                 ▼                 ▼
 ┌────────────┐  ┌────────────┐  ┌────────────────────┐
 │📚 6 科     │  │🧠 长期记忆 │  │🗃️ 业务数据库       │
 │Skills      │  │(DB)        │  │(SQLite, 中心)     │
 │(Markdown)  │  │学生画像/   │  │students/questions/│
 │            │  │薄弱点等    │  │error_records/...   │
 └────────────┘  └────────────┘  └────────────────────┘

       ╔══════════════════════════════════════════╗
       ║  ⏰ Scheduler (APScheduler, 独立进程)     ║
       ║  07:00 / 18:00 / 21:30 / 22:30 触发事件   ║
       ║  → HTTP POST /internal/system-event       ║
       ║  学生离线时任务积压, 下次登录按序播放      ║
       ╚══════════════════════════════════════════╝
```

### 2.2 核心设计决策

1. **班主任永远在场**：所有用户消息和系统事件先到班主任 Orchestrator，由它决定路由。用户感知"始终在跟一个 AI 对话"，但背后是 3 个 agent 在协作。
2. **学科老师不分科**：1 个 agent + 6 科 skill 库，按对话内容动态加载（`load_skill("math-导数应用")`）。这是 Vibe-Trading 设计哲学的直接迁移。
3. **3 个存储分工**：
   - **Skills**（Markdown 文件）：6 科教学法、解题套路、知识点讲解—— 人工可读可编辑的静态知识
   - **Memory**（DB 表 `memory_entries`）：学生的性格/目标/薄弱点演变等软数据
   - **DB**（SQLite，9 张表）：学生、题库、知识点、错题、计划、会话、消息、记忆、情绪日志 —— 结构化硬数据
4. **路由 LLM**：班主任每条消息都先调一次轻量 LLM（如 Haiku）输出意图标签，避免让主对话 LLM 每次都跑完整推理。
5. **Scheduler 独立进程**：APScheduler 运行在独立进程，通过 IPC/HTTP 接口注入事件到 SessionService。学生离线时任务积压，下次登录按时序播放，保持陪伴连续性。

---

## 3. Agent 角色定义

### 3.1 🎓 班主任 Agent
- **人设**：温和、有耐心，像陪伴三年的班主任。不专研学科，但懂学生、懂高三节奏。
- **核心职责**：意图路由 / 计划生成与督促 / 串场 / 定时场景执行 / 渐进画像探询
- **工具白名单**：`delegate_to_subject_teacher`、`delegate_to_mood_companion`、`get_student_profile`、`update_student_profile`、`get_today_plan`、`update_plan`、`get_recent_errors`、`get_session_history`、`search_memory`、`remember`、`generate_daily_report`
- **不能做**：不直接答疑、不做深度情绪疏导

### 3.2 📚 学科老师 Agent
- **人设**：专业、严谨、爱启发。不寒暄、专注题目。被班主任召唤后接管。
- **核心职责**：答疑 / 讲题 / 出变式题 / 错题诊断 / 动态加载学科 skill / 知识点归类 → 写入错题库 / 讲完后移交回班主任串场
- **工具白名单**：`load_skill`（动态加载 6 科任一）、`vision_understand_image`（多模态 LLM 视觉处理题目图片）、`query_questions`、`generate_variant`、`save_error_record`、`get_knowledge_point`、`get_student_weakness`、`update_student_mastery`、`search_web`、`return_to_homeroom`
- **Skills 库结构**：`skills/{subject}/{chapter}/{point}.md` —— 每个考点一个 Markdown 文件

### 3.3 💗 心态陪伴 Agent
- **人设**：温柔、不评判，像心理咨询取向的姐姐/哥哥。不解题、不催进度。
- **核心职责**：例行情绪 check-in（21:30）+ 班主任检测到压力信号时召唤 / 压力疏导对话（共情技术，不敷衍）/ 红线识别 / 写入情绪日志
- **工具白名单**：`log_mood`、`get_mood_history`、`search_memory`、`escalate_to_parent`（MVP 只记录，V1.1 接入）、`return_to_homeroom`
- **红线设计**：检测到自伤 / 严重抑郁 / 极端表述 → 立即触发兜底响应模板 + 标记 `red_flag=True` + 记录事件。这是高中生产品的合规底线。

### 3.4 路由 LLM 机制

班主任接收消息后，先调一次轻量 LLM 输出意图标签：

```json
{
  "intent": "subject_qa | mood_support | planning | chitchat",
  "subject": "math | chinese | english | physics | chemistry | biology | null",
  "confidence": 0.0-1.0
}
```

根据 intent 决定走哪条分支。规则后处理覆盖（用户消息显式提到学科名时强制覆盖路由结果）。

---

## 4. 数据模型

业务硬数据全部入 SQLite。`student_id` 多租户隔离。

### 4.1 表清单

| 表 | 作用 | 关键字段 |
|----|------|---------|
| `students` | 学生画像核心 | id, name, grade, school, target_school, stream(文/理), profile_json |
| `knowledge_points` | 知识图谱节点（**用户导入**） | id, subject, chapter, point_name, difficulty(1-5), prereq_ids[], exam_freq |
| `questions` | 题库（**用户导入**） | id, subject, stem, options, answer, explanation, knowledge_point_ids[], difficulty, image_url |
| `error_records` | 学生错题（使用中沉淀） | id, student_id, question_id?, user_answer, error_type, knowledge_point_ids[], mastery_level, source, review_count, explanation_text |
| `student_mastery` | 知识点掌握度 | student_id, knowledge_point_id, mastery_score, correct_count, wrong_count, last_practice_at |
| `plans` | 学习计划 | id, student_id, date, type(daily/weekly), tasks_json, feedback |
| `sessions` | 会话 | id, student_id, status, started_at, last_active_at |
| `messages` | 消息流 | id, session_id, role, agent(homeroom/subject/mood), content, metadata, created_at |
| `memory_entries` | 长期记忆 | id, student_id, type(profile/weakness/habit/goal/event), key, content, importance, embedding?(V1.1) |
| `mood_logs` | 情绪日志 | id, student_id, session_id, self_score(1-5), topics[], summary, red_flag, created_at |

### 4.2 关键设计点

1. **knowledge_points 是 DAG**：通过 `prereq_ids` 形成前置依赖图——学生在"导数应用"翻车时，AI 可反查"导数定义"是否已掌握。
2. **knowledge_points 粒度到考点级**：如数学"导数应用"拆为"切线方程 / 单调性 / 极值 / 最值"4 个 point，诊断更精准。
3. **error_records 与 questions 解耦**：拍照 OCR 进来的题不强求录入正式题库（噪声多），只在错题表挂独立题干。后期可人工审核提升到 questions。
4. **memory_entries 入 DB**：MVP 用关键词 LIKE 检索；V1.1 加 `embedding` 列做语义检索（pgvector 或 sqlite-vss）。
5. **sessions / messages 入 DB（替代 Vibe-Trading 的 JSONL）**：便于跨会话查询（"上周做了 30 道题，错 8 道"这种统计）。

---

## 5. 核心场景数据流

### 5.1 🌅 早安 + 今日计划（07:00）

1. Scheduler 触发 → 生成 `SystemEvent { type: "morning_briefing", student_id }`
2. 通过 HTTP POST `/internal/system-event` 调用 `SessionService.handle_system_event()`（内部端点，仅本机访问）
3. 班主任 Orchestrator 接管：读 students(profile) + plans(yesterday) + error_records(uncompleted_review) + memory_entries(近期目标) + mood_logs(近 3 天趋势)
4. 班主任 Agent ReAct loop → 生成今日计划文案 + 任务列表（3-5 个任务）
5. 写入 `plans` 表
6. SSE 推送早安消息 + 任务卡到前端
7. 学生可调整 → `update_plan` → 重新生成

### 5.2 💬 答疑 / 讲题（学生主动）

1. 学生输入题目（文字或图片）→ POST /message
2. SessionService 持久化 message → 班主任 Orchestrator
3. **路由 LLM**（Haiku）→ 输出 `{intent: "subject_qa", subject: "math"}`
4. 班主任委派 → 学科老师 Agent，注入：当前掌握度（`student_mastery WHERE subject=math`）+ 近期错题 + 加载 `skills/math/相关章节.md`
5. 学科老师 ReAct loop：
   - 调 `vision_understand_image`（如果是图片）→ 提取题干 + 直接理解
   - 识别考点 → 关联 knowledge_points
   - 检查学生该考点 mastery_score → 调整讲解深度（薄弱讲基础 / 中等直接解题 / 熟练拓展）
   - 输出分步讲解 + 关键提示
   - `save_error_record`（如果是错题）+ `update_student_mastery`
   - 询问："要不要做一道变式题？" → `generate_variant`
6. `return_to_homeroom` → 班主任串场："理解了吗？还有别的题吗？"
7. SSE 流式推送全程

### 5.3 📝 错题复盘（18:00）

1. Scheduler 触发 → 班主任检查今日错题（`error_records WHERE created_at = today`）
2. 分支：
   - 无错题 → 跳过 / 推送轻提醒
   - 有错题 → 班主任推送："今天积累了 N 道错题，要现在复盘吗？"
3. 学生确认 → 班主任委派学科老师 + 传入 `error_record_ids[]`
4. 学科老师逐题：重新讲解 + `generate_variant` → 学生答 → 评判 → `update_student_mastery`
5. 全部讲完 → 输出"今日复盘小结"（薄弱点变化）
6. 写入 `memory_entries`（type=weakness, content=...）

### 5.4 📊 学习日报 + 情绪 check（21:30）

1. Scheduler 触发 → 班主任聚合：plans 完成率、error_records 今日新增/复盘、student_mastery 变化、互动次数
2. 班主任 Agent 生成日报文案（总结段 + 数据卡 + 1 句鼓励）
3. SSE 推送
4. 5 秒后班主任主动接续："今天感觉怎么样？" → 路由 LLM 判意图
5. 分支：
   - 轻松/正常 → 班主任简短互动 → 晚安
   - 低落/焦虑/疲惫 → 委派心态陪伴 Agent
6. 心态陪伴接管：不评判式倾听 → 必要时使用呼吸/认知重构提示 → **红线检测**（关键词清单 + LLM 二次确认）→ 必要时触发兜底响应 + `red_flag=True`
7. 对话结束 → `log_mood`（self_score 学生自评 1-5）→ `return_to_homeroom` → 班主任晚安

### 5.5 共通设计

- **所有 Agent 输出走 SSE 流式推送**（复用 `session/events.py`）
- **每个场景结束必写 `memory_entries`** —— 这是"陪伴感"积累的关键
- **定时任务不强制弹窗** —— 学生离线则积压，下次登录按序播放
- **学生可随时打断** —— 即使在场景流程中，新消息优先处理

---

## 6. 模块复用 vs 自研清单

### 6.1 直接复用（来自 Vibe-Trading）

- `memory/persistent.py` → 适配 DB 后端
- `session/events.py`（SSE 总线）
- `session/service.py`（会话生命周期）
- `session/search.py`（FTS5 检索，可选）
- `agent/skills.py`（Skills 加载机制）
- `agent/tools.py` + `BaseTool` 基类
- `agent/loop.py` ReAct 核心 + 五层上下文压缩
- `agent/context.py`（上下文构建）
- `api_server.py`（FastAPI 骨架，精简）

### 6.2 改造（有现成基础）

- Memory 后端：Markdown 文件 → SQLite
- Session 存储：JSONL → SQLite
- Skills 内容：金融 74 个 → 教育 6 科
- Tools 集合：金融 23 个 → 教育 10+ 个

### 6.3 自研

- 多 Agent Orchestrator（替代 Vibe-Trading 的 `swarm/` DAG）
- 路由 LLM 模块
- APScheduler 调度层 + 任务积压队列
- 学生认证（学号+PIN）
- 业务 DB schema + 迁移
- 多模态视觉 Tool 封装（`vision_understand_image`）
- 6 科 Skills 内容（用户提供大纲，可生成模板）

### 6.4 丢弃（Vibe-Trading 金融部分）

- `backtest/` 整目录
- `shadow_account/` 整目录
- `providers/`（金融数据源）
- `swarm/`（DAG 编排，由新 orchestrator 替代）
- 74 个金融 skills
- 29 个金融 swarm presets

---

## 7. 技术栈

| 层 | 选型 |
|----|------|
| 后端语言 | Python 3.11+ |
| Web 框架 | FastAPI（HTTP + SSE） |
| ORM / DB | SQLAlchemy + SQLite（MVP）/ Postgres（升级） |
| 定时任务 | APScheduler（独立进程） |
| 数据校验 | Pydantic |
| LLM SDK | Anthropic SDK + OpenAI SDK（可配多模型） |
| 视觉理解（替代 OCR） | 多模态 LLM API（Claude vision / GPT-4o / Qwen-VL）—— 封装为 Tool 接口可切换 |
| 主对话 LLM（可配） | 默认 Claude Sonnet 4.6 |
| 路由 LLM（可配） | 默认 Claude Haiku 4.5 |
| 前端 | 用户自有平板 Web 页面 + EventSource（SSE）+ 上传接口 |
| 认证 | 学号 + PIN 本地认证（MVP）|

---

## 8. MVP 路线（约 5 周）

### 阶段 1 · 骨架打通（~1 周）
- Fork Vibe-Trading 砍掉金融模块
- 搭 SQLite + SQLAlchemy schema（9 张表）
- 跑通单 Agent ReAct loop
- FastAPI + SSE 跑通最小消息流
- **验收**：能跟最简 AI 在网页上来回聊

### 阶段 2 · 3 Agent 编排（~1.5 周）
- 自研 Orchestrator + 路由 LLM
- 班主任 / 学科老师 / 心态师三套 system prompt + 工具白名单
- 学科 Skills 模板 + 写 1-2 章示例（数学 / 英语）
- Memory 入 DB + 自动写入策略
- **验收**：完成"答疑"完整数据流

### 阶段 3 · 主动陪伴 + 错题闭环（~1.5 周）
- APScheduler 独立进程 + 积压队列
- 4 个定时场景实现
- 多模态视觉 Tool 集成
- `error_records` 闭环 + 变式生成
- `student_mastery` 自动更新
- **验收**：4 个 MVP 场景全跑通

### 阶段 4 · 心态陪伴 + 红线 + 打磨（~1 周）
- 心态陪伴 Agent + `mood_logs`
- 红线检测（关键词清单 + LLM 二次确认）
- 兜底响应模板
- 6 科 Skills 内容完善
- E2E 测试覆盖
- **验收**：完整产品可交付一个学生试用

**V1.1+ 候选**：周报 / 家长端 / 语义检索（embedding）/ 题库扩充 / 离线模式

---

## 9. 错误处理

| 失败点 | 处理策略 |
|-------|---------|
| 路由 LLM 调用失败 | 默认走班主任，不阻塞主流程 |
| 学科老师 / 心态师 LLM 失败 | 班主任兜底道歉 + 自动重试 |
| 视觉理解失败 | 自动回退要求学生文字输入 |
| DB 写入失败 | 消息暂存内存队列，DB 恢复后补写 |
| Scheduler 进程崩溃 | systemd 自动重启 + 任务幂等性保证（按 student_id + date + type 去重） |
| 路由 LLM 误判 | 规则后处理覆盖（用户消息显式提到学科名时强制） |
| 红线漏检 | 关键词清单 + LLM 二次确认双层；漏检视为高优先级 bug |

---

## 10. 测试策略

| 类型 | 范围 |
|------|------|
| 单元测试 | 每个 Tool / Schema / 路由 LLM（mock LLM 输出） |
| 集成测试 | 4 个 MVP 场景的完整数据流（fixtures + recorded LLM 输出） |
| E2E 测试 | 3-5 条"一天剧本"（07:00-22:30）端到端跑通 |
| 红线测试 | 手工准备含敏感词的对话集，验证心态师能识别 + 兜底 |
| 学科评估集 | 50 道高考题样本 + 期望讲解要点，定期跑评估学科老师质量 |

---

## 11. 冷启动策略

**不做大问卷**。班主任 Agent 的 system prompt 内置"自然探询策略"：

- 长期记忆里有"学生画像"专区，预留字段（年级 / 学校 / 目标 / 各科分数 / 薄弱点 / 学习习惯 / 作息），未填写的留 `null`
- 班主任遇到合适时机自然探询（"对了，你的目标院校是哪个？"），但不审问
- 兜底：哪怕啥都不知道，第一句也能聊起来（"嗨，第一次见，我是你的 AI 班主任。可以叫你什么？"）
- 每次答疑 / 复盘 / 情绪对话都自动累积画像 → 写入 `memory_entries`

---

## 12. 设计决策记录（已锁定）

| # | 决策 | 选项 |
|---|------|------|
| 1 | 目标用户 | 高三学生 |
| 2 | 载体 | 学习平板（已有）+ Web 前端 + Python 后端 |
| 3 | 架构 | 中心-客户端，多学生共用一 DB |
| 4 | 产品定位 | 全程陪伴型（学习+生活+助教+学科老师） |
| 5 | Agent 数量 | 3 个（班主任 / 学科老师 / 心态陪伴） |
| 6 | 学科细分 | 1 个学科老师 + 6 科 skill（不按学科开 agent） |
| 7 | 主动程度 | 全主动（定时唤醒 + 情境推送 + 被动响应） |
| 8 | MVP 环节 | 早安 + 答疑 + 错题复盘 + 学习日报+情绪（4 个全要） |
| 9 | 学科覆盖 | 主课 6 门 |
| 10 | 冷启动 | 对话式渐进画像（不做大问卷） |
| 11 | 题库 | DB schema 系统建，内容用户自行导入 |
| 12 | 题目录入 | 多模态视觉理解 + 文字输入兜底 |
| 13 | 实现路径 | 数据层复用 + 编排层自研 |
| 14 | 班主任职责 | 不直接答疑，统一路由委派 |
| 15 | 学科老师交接 | 讲完移交回班主任串场 |
| 16 | 心态红线 | MVP 只记录 + 兜底响应；告知家长放 V1.1 |
| 17 | LLM 选型 | 全可配，默认主对话 Sonnet 4.6 / 路由 Haiku 4.5 |
| 18 | 离线任务 | 积压 + 下次登录按序播放 |
| 19 | 路由 LLM | 接受额外 Haiku 成本，避免 Sonnet 每次跑完整推理 |
| 20 | 视觉处理 | 商用多模态 LLM API（替代传统 OCR） |
| 21 | 学生认证 | 学号 + PIN 本地认证 |
| 22 | 数据库 | SQLite（MVP）→ Postgres（升级） |
| 23 | knowledge_points 粒度 | 考点级 |
| 24 | Scheduler | 独立进程（APScheduler） |
