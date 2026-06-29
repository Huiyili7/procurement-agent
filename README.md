# procurement-agent

基于 **LangGraph** 的采购受理 Agent。脱胎于 xTool 机械部自采系统（生产环境、51 名工程师在用），
把"规则驱动的对话表单"重构为"LLM 自主规划 + 工具调用 + 人在环"的 Agent。

## 这是什么（架构）

一个手写的 **ReAct StateGraph**（不是 `create_react_agent` 黑盒）：

```
START → agent ──(LLM 想调工具?)──是──> tools ──> agent ──> …(循环)
                              └──否──> END
```

- `agent/state.py` — 图状态（含 `add_messages` reducer 的对话记忆）
- `agent/tools.py` — 工具：查历史复用、校验链接（MVP 用 mock，后接生产 Postgres）
- `agent/graph.py` — StateGraph 装配：`agent` 推理节点 + `tools` 执行节点 + 条件边
- `agent/config.py` — LLM 入口（OpenAI 兼容，换供应商只改 .env）
- `main.py` — 命令行多轮对话

## 运行

```bash
# 需 Python 3.11+
uv venv && uv pip install -e .      # 或：python -m venv .venv && pip install -e .
cp .env.example .env                # 填入 API key
python main.py
```

试：`我要买几个轴承` →（agent 应自动查历史复用并追问份数/项目代号）

## 迭代路线（每步对应一个 LangGraph 核心概念）

1. ✅ **最小 ReAct 图** — StateGraph / 条件边 / ToolNode / tool-calling 循环
2. ⬜ **结构化受理** — 把 messages 升级为 draft/missing 状态机 + 结构化输出(Pydantic)
3. ⬜ **人在环(HITL)** — `interrupt()` 做澄清/审批
4. ⬜ **持久化** — PostgresSaver checkpointer + thread_id（替代 main.py 的手动 history）
5. ⬜ **评测 + 可观测** — eval 集 + LLM-as-judge + LangSmith 追踪 + CI
6. ⬜ **MCP 工具 + 多 Agent** — supervisor 路由 受理/分析copilot/比价 子 agent

## 面试自检（搭完里程碑1你应能答）

- ReAct 循环在 LangGraph 里靠什么实现？（条件边 `should_continue` + `tools→agent` 回边）
- `State` 的更新是覆盖还是合并？`add_messages` 这个 reducer 解决什么？
- LLM 怎么"知道"有哪些工具、何时调？（`bind_tools` 把 docstring/类型转 JSON Schema）
- workflow 和 agent 的本质区别？（流程是写死的 DAG，还是 LLM 运行时决定下一步）
- 循环为什么不会无限转？（LLM 不再产生 tool_calls 时路由到 END）
