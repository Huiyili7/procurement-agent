# 采购受理 Agent · PRD

> 版本 v0.1（草案，待评审）· 作者 毛文妍
> 北极星：**父 Orchestrator + 角色化 Subagent**（工具裁剪 / 提示词专门化 / 模型分层 / 上下文隔离 / 结构化摘要回传），对标 Claude Code 与 OmniSupply 的多 agent 范式。

---

## 1. 概述

把研发采购从"飞书群聊里靠人来回沟通"，变成一个**自助、结构化、工具精良、人在环、可评测**的采购 Agent。
脱胎于 xTool 机械部自采系统（已上线、51 名工程师在用、月环比 +104%）——本项目把它的"大脑"用 Python + LangGraph 重写为独立、可在 GitHub 展示、作者完全掌控的 Agent 仓库。

## 2. 问题陈述

| 现状（私聊时代 / 旧流程） | 目标（Agent） |
|---|---|
| 需求散在群聊、信息不全、平均 6.5 轮往复 | 一次自助、信息一次到位、往复 ≈0 |
| 采购被随机打断、跨天多线程切换 | 队列化、可批量、可追溯 |
| 无结构化数据、无法分析 | 结构化落库 + 花费/结构分析 |
| 寻源/比价/合规靠人工经验 | 工具化（P2：寻源比价、合规查验） |

## 3. 目标 / 非目标

**目标**
- 一个工程精良的采购受理 Agent：能把模糊需求收集成完整结构化采购单。
- 父 + Subagent 架构：受理为核心 subagent，可渐进扩展（分析 / 寻源 / 合规）。
- 工程严谨度作为第一优先：HITL、持久化、评测、可观测、护栏——这是与玩具项目的分水岭，也是 Agent 岗考察重点。

**非目标**
- 不做可视化工作流编排平台（不是 Dify/Coze 克隆）。
- 不 fork 任何现有项目（学范式、写自己的代码）。
- 不接管公司妙搭生产系统（它单独作为"生产影响"背书）。
- 不追求长程自主（采购受理是短程、强人在环；不 cargo-cult 编码 agent 的超长上下文机制）。

## 4. 用户与核心场景

- **工程师（需求方）**："我要买几个轴承" → Agent 查历史复用、追问缺失项、校验链接、汇总确认 → 下单。
- **采购员**：收到完整结构化采购单（无需追问）；P2：寻源比价、合规标志。
- **管理者**：花费/结构分析（Analytics Copilot）。

## 5. 北极星架构

```
                 用户
                  │
        ┌─────────▼──────────┐
        │  父 Orchestrator    │  ← 理解意图 → 选 subagent → 聚合结构化摘要 → 回复
        │  (规划/路由, 深模型) │
        └──┬─────┬─────┬─────┬┘
           │     │     │     │      每个 Subagent：自己的 state / 工具裁剪 /
   ┌───────▼┐ ┌──▼───┐ ┌▼────┐ ┌▼──────┐   提示词专门化 / 独立模型 / 上下文隔离 /
   │ Intake │ │Analy │ │Sourc│ │Compli │   只回 Pydantic 结构化摘要
   │ 受理   │ │ tics │ │ ing │ │ ance  │
   │(P0/P1) │ │(M4)  │ │(P2) │ │(P2)   │
   └───┬────┘ └──┬───┘ └─┬───┘ └─┬─────┘
       └─────────┴───────┴───────┘
                  │
        ┌─────────▼──────────┐
        │ 存储：SQL + 向量库   │  历史复用 / 花费 / 合规表(mock)
        └────────────────────┘
```

**5 个机制（逐条落地）**
1. 角色化 Subagent → 每个 = 独立 compiled 子图。
2. 工具裁剪 → 每个 subagent 只 `bind_tools` 自己那几个。
3. 提示词专门化 → 每个 subagent 自己的 system prompt。
4. 模型分层 → 受理用快/省模型(`deepseek-chat`)，分析/寻源用深模型(`deepseek-reasoner`)。
5. 上下文隔离 + 结构化摘要 → subagent 用自己的 messages；父用 task 调用、只收 Pydantic 摘要存入父 state，**不并入 subagent 内部消息**。

## 6. Agent 拆分

| Subagent | 角色 | 工具(裁剪) | 模型 | 输出(Pydantic) | 阶段 |
|---|---|---|---|---|---|
| **Intake** | 受理：收集成完整采购单 | search_purchase_history / validate_item_link / create_requirement / transfer_to_human | 快(chat) | `RequirementDraft` + status | P0/P1 |
| **Analytics** | NL 花费/结构分析 | query_spend / query_status | 深(reasoner) | `AnalysisResult` | M4 |
| **Sourcing** | 寻源比价(接 PartFuse) | partfuse_search / compare_price / check_stock | 深 | `SourcingRecommendation` | P2 |
| **Compliance** | 合规查表四标志 | check_compliance(查 mock 表) | 快/确定性 | `ComplianceReport`(REACH/RoHS/CMRT/RBA) | P2 |
| **Orchestrator(父)** | 意图理解 / 路由 / 聚合 | — | 深 | `RouteDecision` / 最终回复 | M2 |

## 7. 工具契约层（Tool-as-Contract，对应系列 01）

**原则**：Tool 不是函数，是带契约的软件单元。主循环只读契约标志做调度，不写死工具逻辑；加/改工具不动主循环。

**每个工具的契约**：
- `args_schema`(Pydantic)：**一份 schema 双用**——既当 LLM function-calling schema，又做运行时校验（LangChain `@tool`+Pydantic 自带，消除"传字符串但要 number"类 bug）。
- **副作用标志**（挂在 tool `metadata`）：`is_read_only` / `is_destructive` / `is_concurrency_safe`。
- `activity`：spinner 文案（"正在查历史采购…"）；>1s 工具配 `onProgress`（LangGraph custom stream）。
- **精简 model-facing 返回**：回给模型的内容要短（别把大 JSON 塞进 context）；用户展示另渲染。
- **ACI 反馈**：返回可行动信息让 agent 自我纠错（"链接不合法：仅支持淘宝/京东…"），不是裸 success/fail。

**标志驱动行为**：`is_destructive=True` → 执行前 **HITL `interrupt()` 二次确认**；`read_only & concurrency_safe` → 可并发（多源场景 M4/P2 再启用调度）。

| 工具 | read_only | destructive | concurrency_safe | 实现 | 阶段 |
|---|:--:|:--:|:--:|---|---|
| search_purchase_history | ✅ | ❌ | ✅ | 经 `PurchaseRepository`(seed/real) | P0/P1 |
| validate_item_link | ✅ | ❌ | ✅ | 规则(现成) | P0/P1 |
| create_requirement | ❌ | ✅ | ❌ | 写 SQL，**destructive→确认** | P1 |
| transfer_to_human | ❌ | ✅ | ✅ | 通知，**确认** | P1 |
| query_spend / query_status | ✅ | ❌ | ✅ | NL→查询 | M4 |
| partfuse_* | ✅ | ❌ | ✅ | 寻源比价(真 API) | P2 |
| check_compliance | ✅ | ❌ | ✅ | 查 mock 合规表(四标志) | P2 |

**明确不做（系列 01 的长期项 → 仅当面试谈资）**：工具懒加载 `shouldDefer`/`ToolSearch`（>30 工具才需，我们 <10）、复杂并发调度器（M4+ 多源再说）、`interruptBehavior` 撤/不撤细分（P2）。

## 8. 状态与数据

- `ParentState`: messages / route / subagent_results(结构化摘要) / final_response。
- `IntakeState`: messages / draft(`RequirementDraft`) / missing_fields / stage。
- **结构化输出**：全程 Pydantic + `with_structured_output`，不靠 prompt 求 JSON。
- **数据源**：抽象 `PurchaseRepository` 接口，两套实现——`seed`（合成数据，提交进仓库、可公开，**默认**）/ `real`（脱敏真实数据，放 `.gitignore` 的本地路径、**不公开**）。`DATA_SOURCE=seed|real` 环境变量切换；**agent 与工具不感知数据从哪来**（副作用隔离）。合规表为 mock（供应商 × 四标志）。

## 9. 工程要求（第一优先）

- **HITL**：`interrupt()` 在不可逆动作（下单 / 转人工）前确认。
- **持久化**：MVP `MemorySaver` → M3 `PostgresSaver` + thread_id（断点续跑）。
- **评测**：见 §12（数据集 + LLM-as-judge + CI 回归）。
- **可观测**：LangSmith 全链路 trace（节点路径 / 工具调用 / token / 延迟 / 成本）。
- **护栏**：输入校验、敏感词、prompt-injection 检测；不可逆动作走确定性校验。
- **流式**：LangGraph streaming，步骤对用户透明。

## 10. 里程碑与验收

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| **M1** ✅ | Intake 的 ReAct 循环 | "我要买轴承"→ 自动查历史复用 + 追问缺失项 |
| **M2** | **Tool 契约层** + Intake 包成 Subagent（自有 state + Pydantic 摘要）+ 薄父 Orchestrator | 工具带副作用标志；父路由到 intake，父 state 只存摘要、不含 subagent 内部消息 |
| **M3** | HITL + 持久化 | 下单前 `interrupt` 确认；重启后凭 thread_id 续跑 |
| **M4** | 第 2 个 subagent(Analytics) + 模型分层 | NL 问花费能答；intake 用快模型、analytics 用深模型，trace 可见 |
| **M5** | eval + LangSmith | 评测集跑出指标 + CI 回归；trace 可查 |
| **P2** | Sourcing(接 PartFuse) + Compliance(查表四标志) | 比价 demo + 四标志报告 |

## 11. 技术栈

Python 3.11+ · LangGraph · langchain-openai(OpenAI 兼容：DeepSeek/通义/OpenAI) · Pydantic · PostgreSQL(checkpointer + 业务) · 向量库(ChromaDB, 复用推荐用) · LangSmith(可观测/评测) · FastAPI(可选服务化) · uv · ruff/pytest。

## 12. 评测计划（差异化重点）

- **数据集**：`(用户输入 → 期望抽取字段 / 期望工具调用 / 期望路由 / 期望最终动作)`。
- **指标**：字段抽取 F1、工具调用正确率、路由准确率、任务成功率(LLM-as-judge)、平均轮次、token/延迟/成本。
- **回归**：golden 样本进 CI；prompt/模型变更前后对比。

## 13. 风险与取舍

- **模型较弱**：DeepSeek/Qwen 的 agentic 工具调用弱于 Claude → 用**结构化输出 + 明确工具 schema** 兜底，必要时关键步骤分层用深模型；**在 §12 eval 以"工具调用正确率"实测验证，并备好"怎么发现、怎么兜底"的面试故事**。
- **为何 LangGraph**：需要可控的状态/分支/HITL/持久化，而非纯 prompt 链。
- **为何不 fork**：要可讲、可掌控的作品；现有项目当参考架构，不当代码底座。
- **多 agent 的克制**：subagent 的理由是"上下文隔离 + 专精 + 模型分层"，不是凑数。

## 14. 决策记录（已定）

1. ✅ **仓库数据**：默认 `seed`（合成、可公开）；预留 `real`（脱敏真实、`.gitignore`、不公开）口子，经 `PurchaseRepository` 接口隔离。
2. ✅ **M4 第 2 个 subagent**：Analytics（无外部依赖、贴已有花费分析）；Sourcing 放 P2。
3. ✅ **评测/LangSmith**：M5 再定规模，先不强接。
