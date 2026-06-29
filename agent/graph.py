"""图(Graph)：把 state / nodes / edges 装配成一个可执行的 ReAct agent。

ReAct = Reason + Act 的循环：
    LLM 思考 → 决定调工具(Act) → 看工具结果 → 再思考 → … → 给出最终答复。
本文件手写这个循环(不用 create_react_agent 黑盒)，这样你能讲清每一步。

结构：
    START → agent → [有 tool_calls?] --是--> tools → agent → …(环)
                                      --否--> END
"""
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .config import get_llm
from .state import AgentState
from .tools import TOOLS

SYSTEM_PROMPT = """你是 xTool 机械部的采购受理助手。
目标：把工程师模糊的采购需求，收集成完整、结构化的采购单。
规则：
- 必填字段：物料名称、商品链接、采购份数、项目代号。缺什么就追问什么，一次只问一项。
- 收到具体物料名时，先用 search_purchase_history 查历史复用，有就推荐给工程师确认是否沿用。
- 收到商品链接时，用 validate_item_link 校验平台合法性。
- 四个必填都齐了，用一句话汇总采购单，请工程师确认。
- 语气简洁专业，不要一次抛一堆问题。"""

# bind_tools：把工具的 schema 绑到模型上，模型才"知道"有哪些工具可调
_llm = get_llm().bind_tools(TOOLS)


def agent_node(state: AgentState) -> dict:
    """推理节点：喂入 system + 历史消息，LLM 返回一条 AIMessage。

    这条 AIMessage 要么是给用户的回复(content)，
    要么带 tool_calls(表示模型想调工具)。我们不在这里判断，交给路由函数。
    """
    messages = [SystemMessage(SYSTEM_PROMPT), *state["messages"]]
    return {"messages": [_llm.invoke(messages)]}


def should_continue(state: AgentState) -> str:
    """路由(条件边的判断函数)：决定 agent 之后走 tools 还是 END。

    LangGraph 的"agentic"正在于此：下一步不是写死的，而是看 LLM 这步的输出动态决定。
    """
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(TOOLS))  # 预置节点：自动执行 AIMessage 里的 tool_calls
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")  # 工具结果回到 agent → 闭合 ReAct 环
    return builder.compile()


graph = build_graph()
