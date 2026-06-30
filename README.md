# procurement-agent

基于 **LangGraph** 的采购受理 Agent。脱胎于 xTool 机械部自采系统（生产环境、51 名工程师在用），
把"规则驱动的对话表单"重构为"LLM 自主规划 + 工具调用 + 人在环"的 Agent。

## 这是什么（架构）

**父 Orchestrator + 角色化 Subagent**，全手写（不用 `create_react_agent`/`langgraph-supervisor` 黑盒）：

```
用户 → 父图 route(结构化路由) ──intake──> Intake 子图(自有 state/工具/prompt)
                              └─direct──> 直接回复          │
父图只收 IntakeResult 摘要(上下文隔离) ◄───────────────────┘
Intake 子图：agent ──tool_calls?──是──> tools(自定义,破坏性→interrupt 确认) ──> agent
                                  └─否──> summarize(结构化输出 IntakeResult) → END
```

- `agent/config.py` — LLM 入口 + `get_structured_llm`（DeepSeek 兼容的结构化输出）
- `agent/schemas.py` — Pydantic 数据契约：`RequirementDraft / IntakeResult / RouteDecision`
- `agent/state.py` — `IntakeState`(子) / `ParentState`(父)，两个不同 schema = 隔离的根
- `agent/tools.py` — **工具契约层**：副作用标志 `SideEffects` + 4 个 Intake 工具
- `agent/data/` — **Repository Pattern**：`DATA_SOURCE=seed|real` 切换，工具不感知数据来源
- `agent/subagents/intake.py` — Intake 子图（含 HITL `interrupt` 二次确认）
- `agent/orchestrator.py` — 薄父图（路由 + 调子图 + 存摘要，带 checkpointer）
- `main.py` — 命令行多轮对话 + HITL 确认循环
- `api.py` + `web/index.html` — FastAPI 服务 + 极简聊天前端（多轮 / 下单确认弹窗）
- `Dockerfile` + `docker-compose.yml` — app + Postgres 双容器部署
- `eval/` — 评测集 + 指标 harness（routing / 字段抽取 / LLM-judge）
- `tests/` — 契约/数据层/隔离/HITL/持久化/分析/护栏 的确定性单测（不联网）
- `docs/INTERVIEW.md` — 面试题库（题目 + 答案）· `docs/DEPLOY.md` — 部署/Docker 指南

## 运行

```bash
# 需 Python 3.11+
uv venv && uv pip install -e .      # 或：python -m venv .venv && pip install -e .
cp .env.example .env                # 填入 API key

python main.py                      # A. 命令行
uvicorn api:app --reload            # B. Web 服务(需 pip install -e ".[server]")，开 http://127.0.0.1:8000
docker compose up --build           # C. Docker：app + Postgres 双容器，开 http://localhost:8000
```
三种用法与 Docker 概念详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

试：`我要买几个轴承` →（agent 自动查历史复用、追问缺失项；补齐四项后说"确认下单"会触发 HITL 确认）

测试：`python -m pytest tests/ -q` →（13 passed，确定性、不联网）

## 迭代路线

1. ✅ **M1 最小 ReAct 图** — StateGraph / 条件边 / ToolNode / tool-calling 循环
2. ✅ **M2 父+Subagent 地基** — 工具契约层 / Repository 数据层 / Intake 子图(含 HITL) / 薄父 Orchestrator + 上下文隔离 / 结构化输出
3. ✅ **M3 持久化强化** — checkpointer 工厂(memory/sqlite/postgres) + 跨重启续跑 + 跨轮 draft 上下文
4. ✅ **M4 第 2 个 subagent(Analytics) + 模型分层** — 快模型工具调用 / 深模型纯推理综合 / 工具裁剪
5. ✅ **M5 评测 + 可观测** — eval 集 + LLM-as-judge + CI 门槛 + LangSmith(env 驱动)
6. ✅ **护栏** — 父图入口确定性输入校验(拦 prompt-injection)
7. ⬜ **P2** — Compliance(查表四标志,可 mock) / Sourcing(接 PartFuse 真实 API)

## 面试自检

所有里程碑的面试题（**题目 + 答案**）见 [`docs/INTERVIEW.md`](docs/INTERVIEW.md)。
