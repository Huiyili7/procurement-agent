# 面试题库（题目 + 答案）· 按里程碑/代码块组织

> 用法：每个块先看"这块在干嘛"，再逐题自测。答案是**能讲出口**的版本，不是背书。
> 配套代码位置都标了文件，面试时能立刻翻到。
> 总主线一句话：**把 Agent 当软件系统设计，而不是当大模型应用**——调度、隔离、配额、权限、扩展点、生命周期 hook。

---

## M1 · 最小 ReAct 循环

代码：`agent/subagents/intake.py`（M1 时在 `agent/graph.py`，M2 收进 subagent）。

**Q1. ReAct 循环在 LangGraph 里靠什么实现？**
A：靠**条件边**。`agent` 节点产出一条 AIMessage 后，路由函数 `should_continue` 看它有没有 `tool_calls`：有就去 `tools` 节点执行、再用一条普通边 `tools → agent` 回到推理（闭合环）；没有就离开循环。"下一步走哪"不是写死的，而是看 LLM 这步输出**运行时决定**——这就是 agentic 的本质。

**Q2. 循环为什么不会无限转？**
A：每轮 `agent` 都重新看全部消息（含上一轮工具结果）再决定。当模型认为信息够了、不再产生 `tool_calls`，路由就离开 `tools` 分支走向收尾/END。终止条件是"模型不再要求行动"，由模型判断、图结构兜底。

**Q3. State 的更新是覆盖还是合并？`add_messages` 解决什么？**
A：默认是**覆盖**（节点返回的字段直接替换）。`messages` 字段用 `Annotated[list, add_messages]` 标了 reducer，变成**追加并按 id 去重/更新**。所以节点只需 `return {"messages": [新消息]}`，历史自动累积，不用手动拼列表。这是 LangGraph 处理对话记忆的标准做法。

**Q4. LLM 怎么"知道"有哪些工具、何时调？**
A：`bind_tools(TOOLS)` 把每个工具的名字+类型注解+docstring 转成 JSON Schema 塞进请求；模型据此决定调不调、传什么参。所以 docstring 必须写清"什么时候用"。

**Q5. workflow 和 agent 的本质区别？**
A：workflow 是**流程写死的 DAG**（A→B→C，分支也是预定义条件）；agent 是 **LLM 在运行时决定下一步**（调哪个工具、要不要再调、何时收尾）。LangGraph 两者都能写——本项目父图偏 workflow（路由是结构化决策），子图是 agent（ReAct 动态循环）。

---

## M2 · 第 1 块：工具契约层（Tool-as-Contract）

代码：`agent/tools.py`。核心：Tool 不是函数，是**带契约的软件单元**；主循环只读契约标志做调度。

**Q1. schema 双用解决什么 bug？**
A：一份 Pydantic `args_schema` 同时当两件事——① 喂给 LLM 的 function-calling schema（模型据此知道参数形状）；② 运行时入参校验。弱模型（DeepSeek）常把 `quantity` 当字符串传、或传 0/负数；有了 `quantity: int = Field(gt=0)`，错的入参在**工具边界就被 ValidationError 挡掉**，根本进不了函数体——而不是在业务逻辑深处炸出难查的错。代码见 `CreateRequirementArgs`，测试见 `tests/test_contract.py::test_schema_dual_use_blocks_bad_quantity`。

**Q2. 副作用标志为什么挂在工具上，不挂在主循环里？**
A：如果"哪些工具要二次确认"写死进调度逻辑（`if name == "create_requirement"`），每加一个危险工具都要改主循环——违反开闭原则、耦合。把 `is_read_only/is_destructive/is_concurrency_safe` 作为契约挂在工具自身（`tool.extras`），调度器只读标志、不认工具名，加工具主循环一行不动。这是"声明（工具）与调度（主循环）解耦"。

**Q3. 为什么 `is_destructive` 和 `is_concurrency_safe` 要分成两个标志，不合并？**
A：它们正交。`transfer_to_human` 不可逆（要确认）但幂等、可并发；`create_requirement` 不可逆且必须串行（防重复下单）。合并成一个布尔会丢信息。代码里就是 `WRITE_DESTRUCTIVE`（串行）vs `NOTIFY_DESTRUCTIVE`（并发安全）两种组合。

**Q4. 为什么用 frozen dataclass `SideEffects` 带不变式，而不是直接传 dict？**
A：裸 dict 是 stringly-typed、可自相矛盾（既 read_only 又 destructive）。`SideEffects.__post_init__` 在**定义期**就拒绝矛盾组合（fail fast），把"标错标志"这类静默 bug 提前到模块加载时暴露，而不是上线后调度误判。测试见 `test_side_effects_invariant_rejects_contradiction`。

**Q5. 元数据该放哪？`extras` vs `metadata` vs schema description？**
A：分受众放——给 **LLM** 看的放 schema/docstring；给**调度器**看的放 `tool.extras`（langchain v1 的工具级元数据入口，旧文档叫 metadata；它不会混进 function-calling schema）；给 **trace/回调**看的放 Runnable 的 `metadata`。混在一起会污染喂给模型的上下文。（踩坑：langchain_core 1.4 的 `@tool` 已不收 `metadata=`，要用 `extras=`。）

**Q6. model-facing 返回为什么要精简？**
A：工具结果会进 LLM 的 context，大 JSON 会挤占 token、稀释注意力、涨成本。所以 `search_purchase_history` 最多回 3 条、每条一行（`PurchaseRecord.to_model_facing()`）；给用户看的详情可以另渲染。这是 ACI（Agent-Computer Interface）设计的一部分。

---

## M2 · 第 2 块：数据层（Repository Pattern + seed/real 隔离）

代码：`agent/data/`（`repository.py` 接口 + 工厂、`seed.py`、`real.py`、`models.py`）。

**Q1. 为什么要在工具和数据之间插一层 Repository？**
A：副作用隔离。工具只调 `repo.search_history(keyword)`，**不知道**数据来自合成 seed、脱敏 real、还是生产 Postgres。好处：① 仓库可公开（默认 seed 进 git，real 走 `.gitignore`）；② 可测（测试注入假仓库）；③ 可演进（M4 接生产 DB 只新增一个实现，工具与图零改动）。这是经典 Repository Pattern。

**Q2. seed / real 怎么切换？谁感知？**
A：环境变量 `DATA_SOURCE=seed|real`，在 `get_repository()` 工厂里分派（默认 seed）。**只有工厂感知来源**，工具/图/agent 全不感知。`real` 实现从 `.gitignore` 的本地路径读脱敏 JSON，文件缺失时**清晰报错**而不是静默返回空（静默空会让人误以为"查无记录"）。测试见 `tests/test_repository.py`。

**Q3. 为什么 repository 返回 Pydantic 记录而不是直接返回字符串？**
A："数据"和"呈现"分离。`search_history` 返回 `list[PurchaseRecord]`（结构化），由记录自己负责 `to_model_facing()` 渲染成精简文本。换数据源不影响怎么把它讲给 LLM；将来要给用户做富展示也能复用同一份结构化数据。

---

## M2 · 第 3 块：Intake Subagent + HITL（人在环）

代码：`agent/subagents/intake.py`。自定义 tools 节点 + summarize 节点。

**Q1. 为什么不用预置 `ToolNode`，要手写 tools 节点？**
A：因为要在破坏性工具执行前插 HITL。手写的 `tools_node` 对每个 tool_call 先读契约 `is_destructive`：是 → `interrupt()` 把"要不要执行"交还给人，人放行才执行、否则回一条取消消息让 agent 自我纠正；否 → 直接执行。**只读契约标志做调度，不写死工具名**（呼应第 1 块）。

**Q2. `interrupt()` 怎么工作？为什么必须有 checkpointer？**
A：`interrupt(payload)` 在节点里抛出一个特殊信号，LangGraph 把当前**状态存进 checkpointer**、把 payload 透出给调用方，图就地暂停。人给出答复后用 `Command(resume=答复)` 再 `invoke`，图从断点**恢复**（`interrupt` 调用处拿到 resume 的值继续）。没有 checkpointer 就没法存断点、没法恢复。所以父图必须 `compile(checkpointer=...)`。

**Q3. interrupt 在子图里抛，怎么能让父图暂停、还能 resume？**
A：父图通过 wrapper 节点 `intake_app.invoke(input, config)` 调子图，**把父的 config 传下去**——子图的执行就挂在父的执行上下文里，`interrupt` 信号会冒泡到父图、由父图的 checkpointer 统一存断点。所以子图编译时**不带自己的 checkpointer**。（这一点我专门写了探针实测，见本文末"工程故事 2"。）

**Q4. summarize 节点是干嘛的？为什么不在回复里顺便求 JSON？**
A：ReAct 收尾时，summarize 用 `with_structured_output(IntakeResult)` 把整段对话**抽成结构化摘要**（draft/missing_fields/stage）回传父图。不靠 prompt 求 JSON 是因为：prompt 求 JSON 会有格式漂移、解析失败、字段缺漏；`with_structured_output` + Pydantic 是**强约束**，模型必须按 schema 产出。冒烟实测 draft 从 collecting→ready→submitted 逐步填齐。

**Q5. `with_structured_output` 在 DeepSeek 上踩了什么坑，怎么修的？**
A：默认 method 走 `json_schema` 的 `response_format`，DeepSeek **不支持**，报 400 `This response_format type is unavailable`。改 `method="function_calling"`（走 tools 通道，DeepSeek 支持）即修复。我把它集中封装在 `config.get_structured_llm()`，一处改、所有结构化输出共用。**更深的教训**：summarize 里的宽 `except` 一度把这个 400 静默兜底成"空草稿"，差点没发现——是靠冒烟脚本断言 draft 非空才揪出来，这正是 M5 要建 eval 的动机。

**Q6. 弱模型工具调用不稳，整体怎么兜底？**
A：① 结构化输出 + 明确 schema（function_calling）约束；② 关键不可逆步骤走 HITL 人确认；③ M5 用 eval 集以"工具调用正确率/字段抽取 F1"实测，prompt/模型变更前后回归对比。

---

## M2 · 第 4 块：薄父 Orchestrator + 上下文隔离

代码：`agent/orchestrator.py`、`agent/state.py`。

**Q1. 多 agent 的正当理由是什么？不是为了凑数吗？**
A：三个真理由——**上下文隔离**（子 agent 的工具调用/中间推理不污染父和别的 agent）、**角色专精**（各自的工具裁剪 + system prompt）、**模型分层**（受理用快模型、分析/寻源用深模型）。不满足这些就不该拆。本项目受理是核心 subagent，analytics/sourcing 渐进加。

**Q2. "上下文隔离"具体怎么落地的？怎么保证父 state 不被子图内部消息污染？**
A：父图 `ParentState` 和子图 `IntakeState` 是**两个不同的 state schema**。父图不直接挂 compiled 子图（那样同名 `messages` 会被框架合并→泄漏），而是用 **wrapper 节点 `intake_node`**：只把"用户可见对话"喂给子图当种子；子图跑完只取**最终回复 + IntakeResult 摘要**并入父 state，子图内部的 ToolMessage / 带 tool_calls 的中间 AIMessage **结构上进不了父 state**。隔离是结构性的、不是靠纪律。测试见 `tests/test_isolation.py`。

**Q3. 父图怎么只拿摘要、不拿一堆消息？**
A：见 `intake_node` 的返回：`return {"messages": [AIMessage(reply)], "intake_result": out.get("result")}`——只回一条干净的 AIMessage 和一个 Pydantic 摘要。子图返回的 `out["messages"]`（含工具消息）被丢弃。

**Q4. plan-execute（父 Supervisor）vs ReAct（子）何时用哪个？**
A：父图做**路由/规划**——意图分类是结构化决策（`RouteDecision`），可预先规划、成本可控、好审计，偏 plan-execute；子图做**受理**——需求模糊、要动态查历史/校验/追问，步数不定，适合 ReAct 动态循环。**能预先规划的用 plan-execute，必须边走边定的用 ReAct。**

**Q5. 路由为什么用结构化输出而不是让模型自己喊工具名？**
A：路由是分类决策，用 `with_structured_output(RouteDecision)` 强制模型只在 `intake/direct` 里选并给理由，可解析、可审计、可兜底（解析失败默认 intake，宁可多受理不漏需求）。让模型自由文本喊名字要再解析、易漂移。

**Q6. 为什么说这个父图"薄"？**
A：它自己不收集采购信息（那是 intake 的活），只做路由 + 调子图 + 存摘要。业务复杂度下沉到 subagent，父图保持稳定——加 subagent 只是多一个分支和节点，父图骨架不变。

---

## M2 · 第 5 块：入口 + 持久化雏形

代码：`main.py`。

**Q1. 多轮对话的历史现在存哪？比 M1 好在哪？**
A：M1 在 `main.py` 手动维护 `history` 列表。M2 父图带 `MemorySaver` checkpointer + 固定 `thread_id`，每轮只投喂**新的一条**用户消息，历史由 LangGraph 持久化（`add_messages` 自动累积）。好处：状态是图的一等公民、可断点续跑、可换持久化后端。

**Q2. MemorySaver 和 PostgresSaver 区别？什么时候换？**
A：`MemorySaver` 进程内，重启即丢——MVP 够用。`PostgresSaver`（M3）落库，**跨进程/重启凭 thread_id 续跑**，是生产做法。换它只改 `build_orchestrator(checkpointer=...)` 一处，图结构不变。

**Q3. CLI 怎么处理 interrupt？**
A：`invoke` 返回的 state 里若有 `__interrupt__`，就把待确认动作（工具名+参数）展示给人，读取 y/n，用 `orchestrator.invoke(Command(resume=答复), config)` 续跑，循环直到没有 interrupt。见 `main.py::_handle_interrupts`。

---

## 跨切面 / 工程故事（面试最加分的部分）

**故事 1 · DeepSeek 结构化输出 400，以及"宽 except 掩盖 bug"。**
现象：父图能路由、子图能对话，但回传的 `IntakeResult` draft 永远是空、stage 永远 collecting。
排查：直接单独调 `with_structured_output(IntakeResult).invoke(...)` 复现，拿到 `400 This response_format type is unavailable`——根因是 DeepSeek 不支持默认的 json_schema response_format。
修复：`method="function_calling"`，并集中到 `config.get_structured_llm()`。
反思：summarize 里的宽 `except Exception` 把这个配置错误静默兜底成"空草稿"，让 bug 在端到端层面"看起来没报错"。是冒烟脚本里"断言 draft 非空"才暴露它。**结论：宽 except 要么别用，要么配可观测/断言；这就是为什么 agent 项目离不开 eval。**

**故事 2 · 用探针实测框架假设，而不是猜。**
M2 最不确定的是"父子图的上下文隔离 + interrupt 跨父子图 resume"在 langgraph 1.2.6 到底怎么表现。我没去赌，而是先写了个 30 行探针（fake 状态、不联网）实测三件事：① 不同 schema 时子图消息会不会泄漏进父 state（结论：不会）；② wrapper 方式调子图、子图状态是否跨父轮持久化（结论：同一轮内 interrupt→resume 持久化，跨轮新鲜启动）；③ 子图 interrupt 能否冒泡并被 `Command(resume=)` 续跑（结论：能）。**正是②让我决定"多轮靠父图 durable 对话喂种子、而不依赖脆弱的嵌套持久化"。** 这是"先验证再设计"的工程习惯。

**故事 3 · Windows 控制台 GBK 撞 LLM emoji。**
真模型常吐 emoji，cmd 默认 GBK 编码 print 会抛 `UnicodeEncodeError` 直接崩。`main.py` 启动时 `sys.stdout.reconfigure(encoding="utf-8")` 兜住。小，但 demo 现场崩很尴尬——细节决定可演示性。

---

---

## M3 · 持久化强化（可切换 checkpointer + 跨重启续跑）

代码：`agent/persistence.py`、`agent/orchestrator.py`。

**Q1. checkpointer 是什么？为什么 HITL 和多轮都靠它？**
A：checkpointer 是图状态的持久化后端。每个 super-step 后把 State 存一份(按 thread_id)。它支撑两件事：① 多轮——下轮 invoke 自动读回历史；② HITL——`interrupt()` 把状态存盘后暂停，`Command(resume=)` 再读回续跑。没有它，interrupt 之后状态就丢了，没法恢复。

**Q2. 为什么做成工厂 `get_checkpointer()`、支持 memory/sqlite/postgres 三种？**
A：不同场景不同需求，但**接口一致**(都是 `BaseCheckpointSaver`)。memory→测试/CI(确定性、零依赖)；sqlite→演示"重启后续跑"(落文件、零部署)；postgres→生产(跨进程、并发)。换后端只改这一个工厂、**图结构一行不动**——这正是 PRD "MVP MemorySaver→生产 PostgresSaver" 的落地证明。我用 sqlite 写了"模拟进程重启"的测试：跑到 interrupt→丢弃 app/连接→用全新实例+同一文件/thread_id→`Command(resume="y")` 能续跑完成(`tests/test_persistence.py`)。

**Q3.（§5b Q1）多轮里子图是"跨轮新鲜启动"，会重复查历史吗？怎么解决？**
A：实测 langgraph 的 wrapper-调子图方式下，子图每个父轮是新任务、状态不跨轮累积(同一轮 interrupt→resume 内才持久化)。所以多轮靠**父图的 durable 对话**喂种子。为避免子图每轮重复调 `search_purchase_history`，父图把上一轮的 `IntakeResult.draft` 压成一句"已知信息"`hint` 传进子图(`_draft_hint`)，模型据此跳过已问到的字段。这是"用结构化摘要做跨轮上下文"，而不是把一堆消息塞回去。

---

## M4 · 第 2 个 Subagent（Analytics）+ 模型分层

代码：`agent/subagents/analytics.py`、`agent/subagents/common.py`、`agent/config.py`。

**Q1. 加第 2 个 subagent 改了父图几处？这说明什么？**
A：三处——RouteDecision 的 target 加一个枚举、父图加一个 `analytics` 节点 + 一条边、router prompt 加一句。子图本身完全独立。说明"薄父 + 角色化 subagent"的扩展成本是**线性、隔离**的：加能力不动既有 agent，符合开闭原则。

**Q2. 模型分层具体怎么分？为什么不能让深模型干所有活？**
A：实测 **deepseek-reasoner（深）不支持 function-calling**(报 400 "Thinking mode does not support this tool_choice")，所以它**不能 bind_tools、不能结构化输出**。于是分层规则是按"步骤能力需求"分，不是按 agent 分：
- 工具调用 / 结构化输出 → **快模型** deepseek-chat（intake 全程、analytics 的取数+structure、所有路由）。
- 纯推理综合（无工具）→ **深模型** deepseek-reasoner（analytics 的 synthesize 节点，对取到的数据做洞察）。
这是 `get_llm(tier="fast"|"deep")` 的真实边界。**面试点：我没有教条地"分析用深模型"，而是先实测了模型能力边界，把深模型用在它唯一擅长且兼容的地方。** 实测 analytics 端到端：快模型查到各类别花费→深模型综合出"刀具占 70.9%、建议降本"→快模型抽成 AnalysisResult。

**Q3. 工具裁剪体现在哪？**
A：`INTAKE_TOOLS`(4 个) / `ANALYTICS_TOOLS`(1 个 query_spend) 分开定义，各 subagent 只 `bind_tools` 自己那几个。好处：① 模型选择面小→调用更准；② context 里工具描述更短；③ 权限边界清晰(analytics 拿不到 create_requirement 这种破坏性工具)。

**Q4. tools 节点为什么抽成 `make_tools_node(tools)` 工厂、两个 subagent 共用？**
A：那个节点的逻辑是"读契约 is_destructive 决定要不要 HITL"，**与具体工具无关**——天然是 tool-set-agnostic 的。抽成工厂传入各自裁剪后的工具集，既消除重复，又再次印证第 1 块"调度只认契约、不认工具名"。analytics 全是只读工具，所以它永不触发 interrupt——同一份代码、不同契约、不同行为。

---

## M5 · 评测（eval）+ 可观测（差异化重点）

代码：`eval/run_eval.py`、`eval/golden.jsonl`、`tests/test_eval.py`。

**Q1. 为什么 agent 项目必须有 eval？**
A：弱模型的路由/抽取/工具调用都不稳，"看着能跑"≠"对"。eval 把质量变成**可度量、可回归**的数字：改 prompt/换模型前后对比，防止"改一处崩一片"。我这项目就吃过亏——summarize 的宽 except 把 DeepSeek 400 静默兜底成空草稿，是"断言 draft 非空"才揪出来。eval 就是把这种断言系统化。

**Q2. 你的指标怎么设计的？分别度量什么？**
A：① **routing accuracy**——父图路由 target 是否等于期望(分类是否准)；② **field extraction accuracy**——intake 抽出的 draft 关键字段是否等于期望(抽取是否准)；③ **task success (LLM-as-judge)**——对开放式回复，用模型按自然语言判据判通过(没有唯一答案时的成功率)。每条 golden 样本标注期望路由/期望字段/判据，按指标聚合。**当前基线：routing 8/8=100%、field 1/1=100%、task_success 3/3=100%。**

**Q3. LLM-as-judge 怎么做的？它自己不可靠怎么办？**
A：judge 用 `with_structured_output(Verdict{passed,reason})`，给它"用户输入+判据+助手回复"让它判。它本身不可靠，所以：① 只用在没有唯一正确答案的开放题(确定性能判的就用规则)；② judge 调用失败也记成 fail、不静默；③ 判据写得尽量具体(可证伪)。这是"分而治之"——能确定性判的别交给 LLM。

**Q4. eval 怎么进 CI 又不拖慢日常测试？**
A：确定性单测(24 个、不联网、免费)是**必过门禁**；eval 真调 LLM，用 `@pytest.mark.skipif(RUN_EVAL!=1)` 默认跳过，靠带 secret 的单独 CI job(`RUN_EVAL=1`)跑，并对指标设回归门槛(routing 必须 100%，其余≥80%)。这样开发循环快、回归有保障、密钥不进主流程。

**Q5. 可观测怎么接的？**
A：LangSmith 是 env 驱动、langchain 自动埋点——设 `LANGSMITH_TRACING=true` + key，每次 run 的节点路径/工具调用/token/延迟/成本就自动上报，无需改代码。不设则零开销。生产排障("为什么这轮路由错了"")就靠翻 trace。

---

## 护栏（Guardrails）

代码：`agent/guardrails.py`、父图 `guard` 节点。

**Q1. 护栏为什么用规则、不用 LLM？放在哪？**
A：护栏要拦注入/越权/异常输入，这类判定必须**确定性、可解释、不能被同一个被攻击的模型绕过**——用 LLM 判 LLM 安全是循环论证(PRD §9：不可逆动作走确定性校验)。所以纯规则(长度/空输入/注入特征中英正则)，放在父图**入口 `guard` 节点**，挡在所有 subagent 和 LLM 调用之前；命中就短路到安全拒绝、连路由的 LLM 调用都省了。实测能拦 "ignore previous instructions / 忽略之前的指令 你现在是…"。

**Q2. guard 节点为什么要显式置 route="pass"？**
A：route 存在 checkpointer 里会跨轮残留。若 guard 放行时不置位，上一轮的 "blocked" 可能残留导致误判。所以 guard 每轮显式置 "blocked"/"pass"，route_node 再用真实 target 覆盖。**多轮 + 持久化场景下，"状态残留"是个真实坑。**

---

## 第 3 个 Subagent：Compliance（合规查表）

代码：`agent/subagents/compliance.py`、`agent/tools.py::check_compliance`。

**Q1. 加第 3 个 subagent 改了多少既有代码？说明什么？**
A：几乎没动既有 agent——加了 schema(`ComplianceReport`)、数据(`ComplianceRecord`+seed)、工具(`check_compliance`)、子图文件、父图一个节点+一条边+路由枚举。intake/analytics **一行没改**。这就是"薄父 + 角色化 subagent"的扩展成本：**线性、隔离、开闭**。

**Q2. 为什么 Compliance 的合规结论是"确定性查表"而不是让 LLM 判？**
A：合规判定必须**可审计、可复现、不能被模型幻觉带偏**。所以 `check_compliance` 是纯查表(mock 表，未来换真实合规库),LLM 只负责"从自然语言里认出供应商名"这件它擅长的事。**该用 LLM 的地方用(NL 理解)，不该用的地方坚决不用(合规裁决)**——这是 agent 工程的判断力，面试常考"哪些环节不能交给 LLM"。

**Q3. 三个 subagent 的工具/模型差异，体现了哪几条多 agent 机制？**
A：工具裁剪(intake 4 个/analytics 1 个/compliance 1 个，各 bind 各的)、提示词专门化(各自 system prompt)、模型分层(analytics 综合用深模型，其余用快模型)、上下文隔离(各自 state，父只收 Pydantic 摘要)。一套机制，三个角色复用。

---

## 持续集成（CI）

代码：`.github/workflows/ci.yml`。

**Q1. CI 里跑什么？为什么 eval 不进 CI 主流程？**
A：CI 跑 `ruff`(静态检查) + `pytest`(28 个确定性测试，不联网、免费)。eval 需要真实 LLM key、慢且花钱，所以用 `RUN_EVAL=1` 守卫、默认 skip，留给带 secret 的单独场景。**确定性测试当门禁(每次必跑)，eval 当回归(按需/定期)**——这是成本与信号的平衡。

**Q2. CI 没有 key 怎么 import 不报错？**
A：`intake/analytics/compliance` 在 import 时会构造 `ChatOpenAI`(读 `OPENAI_API_KEY`)。CI 里给一个假 key(`sk-ci-dummy`)即可——构造模型和 `bind_tools` 都是本地操作、不发请求，而确定性测试用手搓数据/打桩，不触发真实调用。

---

## 部署（FastAPI + Docker）

代码：`api.py`、`web/index.html`、`Dockerfile`、`docker-compose.yml`。详见 `docs/DEPLOY.md`。

**Q1. 多轮 + HITL 是有状态的，怎么搬到无状态的 HTTP 上？**
A：HTTP 每个请求独立，但记忆放在**服务端的 checkpointer**，客户端只带一个 `thread_id` 当钥匙。`POST /chat` 跑一轮：若图停在 `interrupt`，返回 `type=interrupt` + 待确认动作；前端弹确认框，用户答复后 `POST /resume` 把 `Command(resume=...)` 喂回**同一 thread_id** 续跑。两个端点返回同一形状(`_shape`)，前端统一处理。

**Q2. 为什么把 orchestrator 改成惰性单例 `get_orchestrator()`？**
A：postgres checkpointer 在**编译图时**就要连 DB。若在 import 时就建好单例，容器启动时 app 往往早于 DB ready，import 直接炸。改惰性后 import 不触发连接，等第一个请求来时再建，配合 `depends_on: healthy` + 代码里的连接重试，启动顺序问题就稳了。

**Q3. compose 里 app 怎么连到 db？为什么不是 localhost？**
A：compose 把同一文件里的服务放进一个虚拟网络，**服务名即主机名**——所以 `PG_CONN` 用 `postgresql://...@db:5432/...`。容器里的 `localhost` 指容器自己，连不到隔壁的 db 容器。

**Q4. `environment` 和 `env_file` 冲突时谁赢？这里为什么重要？**
A：`environment` 覆盖 `env_file`。`.env` 里 `CHECKPOINTER=memory`(本地用)，但容器里要 postgres，所以在 compose 的 `environment` 里写 `CHECKPOINTER=postgres` 强制覆盖。理解优先级才不会"本地是 memory、上了容器还是 memory"。

**Q5. Dockerfile 为什么先 COPY 依赖声明、再 COPY 代码？**
A：Docker 分层缓存。装依赖是最慢的层；把它放在"只依赖 pyproject/agent"的位置，改业务代码(api.py/web)时这层命中缓存、不重装依赖，重建从几分钟变几秒。

**Q6. 怎么用这套证明"跨重启续跑"？**
A：页面走到下单确认前，`docker compose restart app`，再用同一会话继续——状态还在，因为断点存在 Postgres 卷里、不随 app 容器重启而丢。这就是 `CHECKPOINTER=postgres` + `thread_id` 的价值，比口头说更有说服力。

---

## 简历口径（可直接用的 bullet，§5b Q4）

> 基于本人在 xTool 上线、51 名工程师在用的机械部自采系统经验（沟通轮次 6.5→0.2、月省≈40h），独立用 **Python + LangGraph** 将其核心重写为**多 Agent 采购系统**（个人作品，非生产系统本身）：

- **手写父 Orchestrator + 3 个角色化 Subagent**（Intake 受理 / Analytics 花费分析 / Compliance 合规查验），不用 `create_react_agent`/`supervisor` 黑盒；通过**不同 state schema + wrapper 节点**实现父子图**上下文隔离**（父只存 Pydantic 结构化摘要，子图内部消息不外泄）；加第 3 个 subagent 几乎零改动既有 agent，验证架构线性可扩展。
- **工具契约层（Tool-as-Contract）**：副作用标志（read_only/destructive/concurrency_safe）挂在工具上，调度器只读契约做决策；破坏性工具走 **HITL `interrupt()` 二次确认**；一份 Pydantic schema 双用（LLM function-calling + 运行时校验）兜底弱模型传参。
- **模型分层**：实测 deepseek-reasoner 不支持 function-calling，据此把**工具调用/结构化用快模型、纯推理综合用深模型**。
- **工程严谨度**：可切换 checkpointer（memory/sqlite/postgres）支持**跨重启续跑**；确定性**护栏**拦 prompt-injection；**28 个确定性单测 + GitHub Actions CI（ruff+pytest）+ eval 评测集 + LLM-as-judge**（基线 routing/field/task 均 100%）；LangSmith 全链路 trace。
- **可观测驱动的 debug**：通过 eval 断言发现并定位"宽 except 掩盖 DeepSeek 400 response_format 不兼容"的隐藏 bug，沉淀为 `get_structured_llm` 统一封装。
- **服务化与部署**：FastAPI 把多轮 + HITL 映射到 HTTP（`/chat` 返回 interrupt、`/resume` 续跑）；极简 Web 前端含下单确认弹窗；Docker Compose 编排 app + Postgres 双容器，`CHECKPOINTER=postgres` 实现跨容器重启的对话续跑。

（技术栈：Python 3.11 / LangGraph / langchain-openai / Pydantic / SQLite·Postgres checkpointer / pytest·ruff / LangSmith）
