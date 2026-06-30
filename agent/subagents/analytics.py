"""Analytics subagent：自然语言花费/结构分析。

这是第 2 个角色化 subagent，用来证明多 agent 架构的"模型分层"机制(PRD §5 机制4)：
- agent 节点(快模型 deepseek-chat)：ReAct 调 query_spend 取数——**取数要工具调用，只能用快模型**。
- synthesize 节点(深模型 deepseek-reasoner)：对取到的数据做**纯推理综合**(无工具)——
  这是深模型唯一能用的地方(实测它不支持 function-calling)。这就是"分层"的真实边界。
- structure 节点(快模型)：把综合结论抽成 AnalysisResult 结构化回传(结构化只能快模型)。

图结构：
    START → agent → [tool_calls?] --是--> tools → agent → …
                                  --否--> synthesize(深) → structure(快) → END
"""
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from ..config import get_llm, get_structured_llm
from ..schemas import AnalysisResult
from ..state import AnalyticsState
from ..tools import ANALYTICS_TOOLS
from .common import make_tools_node

AGENT_PROMPT = """你是 xTool 机械部的采购花费分析助手。
用 query_spend 工具按 项目/类别/月份 取数，回答用户关于花费的问题。
需要哪个维度就调哪个维度；取到数后不要自己瞎算总额，用工具返回的数字。"""

SYNTHESIZE_PROMPT = """基于以上工具取到的花费数据，给出简明、有洞察的分析结论：
点出最大头、占比、可能的优化方向。只用数据里出现的数字，不要编造。"""

STRUCT_PROMPT = """把上面的分析整理成结构化结果：
- answer：给用户的分析结论(自然语言，2-4 句)。
- figures：关键数字(键为维度名，值为金额)。
- method：计算口径(一句话)。"""

_llm_with_tools = get_llm("fast").bind_tools(ANALYTICS_TOOLS)
tools_node = make_tools_node(ANALYTICS_TOOLS)


def agent_node(state: AnalyticsState) -> dict:
    return {"messages": [_llm_with_tools.invoke([SystemMessage(AGENT_PROMPT), *state["messages"]])]}


def should_continue(state: AnalyticsState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "synthesize"


def synthesize_node(state: AnalyticsState) -> dict:
    """深模型纯推理综合(无工具)——模型分层里"深"那一档真正发挥作用的地方。"""
    deep = get_llm("deep")
    narrative = deep.invoke([*state["messages"], SystemMessage(SYNTHESIZE_PROMPT)])
    return {"messages": [narrative]}


def structure_node(state: AnalyticsState) -> dict:
    """快模型把综合结论抽成 AnalysisResult 结构化回传父图。"""
    try:
        result = get_structured_llm(AnalysisResult).invoke(
            [*state["messages"], SystemMessage(STRUCT_PROMPT)]
        )
    except Exception:
        result = AnalysisResult(answer=state["messages"][-1].content)
    return {"result": result}


def build_analytics_graph():
    builder = StateGraph(AnalyticsState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("structure", structure_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", "synthesize": "synthesize"}
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("synthesize", "structure")
    builder.add_edge("structure", END)
    return builder.compile()


analytics_app = build_analytics_graph()
