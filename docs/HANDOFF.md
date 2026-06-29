# HANDOFF — 上下文交接（新窗口请先读这份）

> 目的：让新会话**无缝接续**，不只知道"做什么"，更懂"为什么"。读完本文 + `CLAUDE.md` + `PRD.md`，你就拥有了之前所有有效上下文。

## 0. 必读顺序

1. `CLAUDE.md`（自动加载）— 协作原则 + 技术栈 + 项目一句话
2. **本文 `docs/HANDOFF.md`** — 决策理由 / 当前进度 / 下一步 / 面试叙事
3. `docs/PRD.md` — 完整产品规格（架构 / agent 拆分 / 工具契约 / 里程碑 / 评测）
4. 全局记忆 `project_procurement_agent.md`（自动加载）— 跨会话要点

## 1. 一分钟理解

- **作者**：毛文妍，CUHK 机械硕士(CS 本科)，2026 应届，求 **AI/Agent 开发岗**。
- **这个项目**：独立的 Python + LangGraph **采购受理 Agent**，是求职**作品**（不是公司生产系统本身）。
- **作者的真实背书**：xTool 机械部自采系统已上线、51 名工程师在用、月环比 +104%、沟通轮次 6.5→0.2、月省 ~40h。**这是"生产影响"证据；本仓库是"agent 工程能力"证据。两个互补。**
- **简历口径**：" 基于我在 xTool 上线、51 人在用的自采系统经验，独立将其核心重写为基于 LangGraph 的多 agent 采购系统……"——**别让人误以为整个生产系统是一人所写**。

## 2. 决策日志（是什么 / 为什么）— 不要轻易推翻，要改先问作者

| 决策 | 为什么 |
|---|---|
| **Python + LangGraph**（非 Java/TS/LangGraph.js） | agent 岗最对口、生态最成熟、作者要逐行掌控 |
| **新建独立仓库，不在妙搭上改** | 妙搭是托管 aPaaS，跑不了 Python、底座不可控 = 永远 vibe；简历要可展示、可掌控的 GitHub repo |
| **不 fork 任何参考项目** | fork=对黑盒 vibe + 零差异化；只**学范式、写自己的代码** |
| **北极星=父 Orchestrator + 角色化 Subagent** | 对标 Claude Code / OmniSupply；多 agent 的正当理由是**上下文隔离 + 角色专精 + 模型分层**，不是凑数 |
| **受理(Intake)为核心，渐进加 subagent** | intake 是作者真实生产强项；渐进式，加 subagent 只是"注册"、不返工 |
| **Tool-as-Contract**（系列 01） | 主循环只读工具标志做调度，加/改工具不动主循环；schema 双用防 bug；`is_destructive`→HITL |
| **模型分层**（chat 快 / reasoner 深） | 省钱 + 提质，简历亮点 |
| **数据：seed 默认 + real 脱敏口子(gitignore)** | repo 可公开；真实数据私有、不公开 |
| **手写 ReAct/父子图，不用 create_react_agent / langgraph-supervisor 黑盒（MVP 阶段）** | 不 vibe，要能在面试讲清内部 |
| **工程严谨度（eval/trace/HITL/持久化/护栏）= 第一优先** | agent 岗考察重点；与玩具项目的分水岭 |
| **合规、平台级能力延后/不做** | 见 §6 |

## 3. 当前进度

- ✅ **M1 完成且作者已本机跑通**：最小 ReAct StateGraph（`agent` 节点 ↔ `tools` 节点 + 条件边 `should_continue`），2 个 mock 工具，CLI 多轮对话。
- **已有文件**：`agent/{config,state,tools,graph}.py`、`main.py`、`pyproject.toml`（已修打包：`[tool.setuptools] packages=["agent"]`）、`.env.example`、`README.md`、`docs/PRD.md`、`eval/README.md`。
- **运行**：`pip install -e .` → `copy .env.example .env`（填 DeepSeek key）→ `python main.py`。验收：输入"我要买几个轴承"→ agent 自动调 `search_purchase_history` + 追问缺失项。

## 4. 下一步：M2（Tool 契约层 + Intake Subagent + 薄父 Orchestrator）

**目标**：把 M1 的单循环升级为"父 + 一个 subagent"地基，并落地工具契约。**逐块写、逐块讲、配面试题。**

1. `agent/tools.py`：给工具加 `metadata` 副作用标志 `is_read_only / is_destructive / is_concurrency_safe`；`create_requirement / transfer_to_human` 标 `is_destructive=True`。
2. `agent/data/`：`PurchaseRepository` 接口 + `SeedRepository`（合成数据）；`search_purchase_history` 走它（为 seed/real 口子打地基，`DATA_SOURCE=seed|real` 切换，real 路径进 `.gitignore`）。
3. `agent/subagents/intake.py`：把 M1 ReAct 图收进来，做成**自带 state、返回 Pydantic `IntakeResult` 摘要**的 subagent；用**自定义 tools 节点**实现 `is_destructive`→`interrupt()` 二次确认。
4. `agent/orchestrator.py`：薄父图，路由用户输入 → 调 intake 子图 → **父 state 只存 `IntakeResult` 摘要，不并入 subagent 内部 messages**（上下文隔离的实现）。
5. `agent/state.py` / `main.py`：补 `ParentState`、改入口。

**M2 验收**：父路由到 intake；父 state 只含结构化摘要、不含子 agent 内部消息；destructive 工具执行前触发确认。
**M2 面试题**：schema 双用解决什么 bug？副作用标志为何挂工具不挂主循环？父怎么只拿摘要、不污染上下文？plan-execute(父) vs ReAct(子) 何时用哪个？结构化输出 vs prompt 求 JSON？

## 5. 之后里程碑（详见 PRD §10）

M3 HITL(`interrupt` 下单确认)+ PostgresSaver(短期记忆/续跑) → M4 第 2 个 subagent(Analytics 花费分析)+ 模型分层 → M5 eval(LLM-judge + CI，含工具调用正确率验证 DeepSeek 兜底)+ LangSmith 追踪 → M6 长期记忆(LangGraph Store)+ 1 个 guardrail Hook + 1 个 MCP 工具(平台化点到为止) → P2 Sourcing(接 PartFuse 真实电子料 API)+ Compliance(查表四标志 REACH/RoHS/CMRT/RBA)。

## 6. 明确不做 / 反模式（避免过度设计）

- 不做可视化工作流编排平台（非 Dify/Coze 克隆）；不接管妙搭生产系统。
- 系列 01/02/03/05/07 里的**平台级**项**只取概念当面试谈资**：工具懒加载/ToolSearch(工具<10 不需)、复杂并发调度器、micro-compact/AutoCompact 熔断(短会话用不上)、policy 配置中心、Hook 平台、MCP server 集群、Plugin 市场、Grafana 平台。
- 不 cargo-cult 编码 agent 的超长上下文/长程自主机制（采购受理是短程、强 HITL）。
- 反模式：超级工具 `do_anything`、读写混在一个工具、工具描述里塞业务逻辑、工具返回大 JSON 进 context、create_react_agent 黑盒当 MVP。

## 7. 参考项目（学范式，不抄成 fork）

- **OmniSupply**（Bhardwaj-Saurabh，真 LangGraph）：父 Supervisor + BaseAgent/Registry + Pydantic 结构化输出 + Opik 可观测 → **架构北极星**。注意其短板（73% notebook、缺 eval/HITL）正是我们要超越的。
- **AWS RFQ**（aws-samples，Strands SDK 非 LangGraph）：抄**业务逻辑 + 合规四标志查表式**（REACH/RoHS/CMRT/RBA），不抄框架。
- **PartFuse**：电子料(Mouser/DigiKey/TME)比价/库存 API → P2 当真实工具接入。
- 系列文章《从 Claude Code 源码学到的 00–07》：01 Tool 契约、02 上下文、03 权限/Hook、04 多 agent、05 Skill/MCP/Plugin、06 记忆、07 路线图。已吸收要点见 PRD。

## 8. 面试叙事（总主线 + 关键问答）

**总主线**：" 把 Agent 当软件系统设计，而不是当大模型应用"——调度、隔离、配额、权限、扩展点、生命周期 hook。
- ReAct 循环怎么实现？→ 条件边 `should_continue` + `tools→agent` 回边；模型不再产生 tool_calls 时路由 END。
- Tool 为何是契约不是函数？→ 主循环只读 `is_read_only/is_destructive/is_concurrency_safe` 调度，加工具不改主循环；schema 双用(LLM+运行时校验)防字段错配。
- 多 agent 为何用、怎么隔离？→ 上下文隔离+专精+模型分层；父用 task 调子 agent、只收 Pydantic 摘要，不并入子 agent 内部消息。
- workflow vs agent？→ 流程写死(DAG) vs LLM 运行时决定下一步。
- plan-execute(父 Supervisor) vs ReAct(子)？→ 可预先规划/成本可控 vs 动态循环。
- 结构化输出 vs prompt 求 JSON？→ `with_structured_output`+Pydantic 强约束，不靠提示词祈求。
- 弱模型(DeepSeek)工具调用不稳怎么办？→ 结构化输出+明确 schema 兜底，eval 用"工具调用正确率"实测。

## 9. 给新窗口的引导语（复制粘贴）

> 在 `C:\Users\s11260\procurement-agent` 目录开新的 Claude Code 会话，CLAUDE.md 与全局记忆会自动加载。然后发：
> **"读 docs/HANDOFF.md 和 docs/PRD.md，我们继续 M2：从第 1 块（工具契约层）开始，逐块写、逐块讲、配面试题。遵循 CLAUDE.md 的第一性原理。"**
