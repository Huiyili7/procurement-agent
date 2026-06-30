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

- ✅ **M1**：最小 ReAct StateGraph，2 个 mock 工具，CLI 多轮。
- ✅ **M2**：工具契约层 / 数据层 / Intake subagent+HITL / 薄父 Orchestrator+上下文隔离 / 新入口。
- ✅ **M3**：可切换 checkpointer（memory/sqlite/postgres 工厂）+ 跨重启续跑（sqlite 实测）+ §5b Q1 的 intake 跨轮 draft hint。
- ✅ **M4**：第 2 个 subagent（Analytics 花费分析）+ 模型分层（快模型工具调用 / 深模型纯推理综合）+ 工具裁剪。
- ✅ **M5**：eval 评测集 + 指标（routing/field/LLM-judge）+ CI 门槛 + LangSmith（env 驱动）。**基线 routing/field/task 全 100%。**
- ✅ **护栏**：父图入口确定性 guard 节点，拦 prompt-injection/越权/异常输入。
- ✅ **服务化 + 部署（2026-06-30 加）**：FastAPI(`api.py`：/chat、/resume 把多轮+HITL 映射到 HTTP) + 极简 Web 前端(`web/index.html`，含下单确认弹窗) + Docker(`Dockerfile`/`docker-compose.yml`：app+Postgres 双容器，`CHECKPOINTER=postgres` 跨重启续跑)。orchestrator 改惰性单例 `get_orchestrator()` 以适配容器启动顺序。本地 TestClient 已验证 /chat→interrupt→/resume 全流程；Docker 本机未装、文档化在 `docs/DEPLOY.md`。
- **测试**：24 passed + 1 skipped(eval)；全部不联网、确定性。**面试题库（题+答）见 `docs/INTERVIEW.md`**（含 M1–M5+护栏+部署 + 3 个工程故事 + 简历 bullet）。
- ✅ **Compliance subagent（第 3 个）**：查表四标志 REACH/RoHS/CMRT/RBA(确定性 mock)，路由/隔离/结构化回传齐全；真模型实测识别"米思米 CMRT 不合规"。
- ✅ **CI**：`.github/workflows/ci.yml` 跑 ruff + 28 个确定性测试(给 dummy key 让 import 通过)。
- ✅ **Demo 脚本**：`docs/DEMO.md`（2 分钟录屏分镜）。
- ⬜ **P2（未做）**：Sourcing（需 PartFuse 真实 API，无 key 暂缓）、真实 LangSmith trace 截图、录 demo 视频。

### 文件地图
```
agent/
  config.py        get_llm(tier=fast|deep) 模型分层 + get_structured_llm(function_calling)
  schemas.py       RequirementDraft / IntakeResult / RouteDecision / AnalysisResult
  state.py         IntakeState / AnalyticsState / ParentState —— 不同 schema = 隔离的根
  tools.py         工具契约层 SideEffects；INTAKE_TOOLS(4) / ANALYTICS_TOOLS(1) 工具裁剪
  guardrails.py    确定性输入护栏(规则,非 LLM)
  persistence.py   get_checkpointer(): memory|sqlite|postgres 工厂
  data/            Repository Pattern：repository/seed/real/models(含 SpendRecord)
  subagents/
    common.py      make_tools_node(): 契约驱动的工具节点工厂(intake/analytics 共用)
    intake.py      受理子图：agent→tools(HITL interrupt)→summarize
    analytics.py   分析子图：agent(快)→tools→synthesize(深)→structure(快)
  orchestrator.py  父图：guard → route → {intake|analytics|direct}，get_checkpointer()
main.py            CLI：多轮 + HITL 确认循环 + utf-8 stdout
eval/              golden.jsonl(样本) + run_eval.py(指标 harness)
tests/             contract/repository/isolation/hitl/persistence/analytics/guardrails/eval (24+1)
docs/INTERVIEW.md  面试题库(题+答) + 简历 bullet
```

### 运行 & 验收
- 安装：`./.venv/Scripts/python.exe -m pip install -e .`（dev：`pip install pytest ruff`）→ `.env` 已填 → `python main.py`。
- 单测：`python -m pytest tests/ -q` → 24 passed, 1 skipped（**确定性、不联网**）。
- 评测：`RUN_EVAL=1 python -m eval.run_eval`（真调 LLM，出指标表）。
- 持久化 demo：`.env` 设 `CHECKPOINTER=sqlite` 后 `python main.py`，下单时确认前 Ctrl-C，重开同 thread 仍能续。
- 已实测端到端：寒暄→direct；买轴承→intake 多轮 collecting→ready→submitted（含 interrupt）；花费提问→analytics（深模型综合"刀具占 70.9%"）；注入输入→guard 拦截。

## 4. 本会话自主决策记录（请过目，有异议说一声即可回退）

1. **删 `agent/graph.py`**（收进 subagents/intake.py，避免两份真相）。
2. **工具元数据用 `extras=`**（langchain_core 1.4 `@tool` 不再收 `metadata=`）。
3. **结构化输出统一 `method="function_calling"`**（DeepSeek 不支持默认 json_schema，400）。
4. **上下文隔离 = 不同 state schema + wrapper 节点**（探针实测后定方案，INTERVIEW 故事 2）。
5. **多轮 = 父图 durable 对话喂子图种子**，子图跨轮新鲜启动；§5b Q1 用 **draft hint** 解决重复查历史。
6. **持久化做成 `get_checkpointer()` 工厂**：默认 memory（测试），sqlite 演示跨重启续跑，postgres 生产口子。**没强上 Postgres**——理由：portfolio 仓库要零部署可跑，sqlite 已证明同一"durable resume"性质，postgres 同接口可换。
7. **模型分层按"步骤能力"而非"agent"分**：实测 deepseek-reasoner 不支持 function-calling，故深模型只用于无工具的纯推理综合。
8. **eval 默认跳过、`RUN_EVAL=1` 才跑**：确定性单测当门禁，eval 当带 secret 的回归 job。
9. **护栏用规则不用 LLM**，放父图入口（PRD §9 不可逆动作走确定性校验）。
10. **`create_requirement` 仍是 mock 回执**（不真写库）：真正落库等接生产 DB。
11. **`main.py` 加 `sys.stdout.reconfigure(utf-8)`**（防 Windows GBK 遇 emoji 崩）。

## 5b. 原疑问 → 已按推荐处理 ✅

- **Q1 子图跨轮重复查历史** → 已加 `_draft_hint`：父图把上轮 draft 当上下文喂子图（M3 完成）。
- **Q2 路由必要性** → 保留路由；M4 加了 Analytics，路由现在区分 intake/analytics/direct，**已物有所值**。
- **Q3 每轮多次 LLM 调用** → 模型分层已落地；进一步降延迟（如单 subagent 跳过路由、缓存）列入 P2 优化。
- **Q4 简历口径** → 已整理成可直接用的 bullet，见 `docs/INTERVIEW.md` 末尾"简历口径"。

## 已知告警（非阻塞）

- langgraph 日志：`Deserializing unregistered type agent.schemas.IntakeResult from checkpoint ... blocked in a future version`。
  原因：父 state 里存了 Pydantic 模型(IntakeResult/AnalysisResult)，checkpointer 持久化时按 msgpack 序列化。
  现状：当前版本能正常反序列化、只是告警；sqlite/postgres 续跑实测正常。
  以后要彻底消除：① 在持久化通道里改存 `model_dump()` 的 dict、用到时再构 Pydantic；或 ② 注册 allowed_msgpack_modules。
  暂不改（要动 state/orchestrator/tests，收益小）。

## 4next. 下一步建议（P2 / 打磨）

- **Compliance subagent**（查表四标志 REACH/RoHS/CMRT/RBA）：纯 mock 查表，最快能加的第 3 个 subagent，进一步证明架构可扩展。
- **Sourcing subagent**：接 PartFuse 真实电子料 API（需 key/access，先留接口）。
- **打磨**：扩 eval golden 集（更多边界样本）；接一次真实 LangSmith 看 trace 截图（放简历/作品集）；README 加架构图。
- **简历**：把 bullet 落到中英文简历；准备 demo 录屏（多轮受理 + HITL + 分析 + 护栏拦截）。

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
