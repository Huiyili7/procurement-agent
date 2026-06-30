"""Compliance subagent：供应商合规查验(四标志 REACH/RoHS/CMRT/RBA)。

第 3 个角色化 subagent，证明架构能**线性扩展**：加它几乎没动既有 agent。
它和 intake/analytics 不同的一点——**合规判定是确定性查表，不靠 LLM 推断**：
LLM 只负责"从自然语言里认出供应商"，真正的合规结论由 check_compliance 查 mock 表给出
(合规必须可审计、可复现)。这正是"该用 LLM 的地方用、不该用的地方不用"。

图结构：
    START → agent(快模型,识别供应商→调 check_compliance) → [tool_calls?]
            --是--> tools → agent --否--> structure(结构化成 ComplianceReport) → END
"""
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from ..config import get_llm, get_structured_llm
from ..schemas import ComplianceReport
from ..state import ComplianceState
from ..tools import COMPLIANCE_TOOLS
from .common import make_tools_node

AGENT_PROMPT = """你是供应商合规查验助手。
从用户消息里识别出供应商名称，调用 check_compliance 查它的四标志(REACH/RoHS/CMRT/RBA)。
不要自己臆断是否合规——一切以工具返回为准。"""

STRUCT_PROMPT = """把工具查到的结果整理成结构化报告：
- supplier：供应商名称。
- flags：四标志各自的状态(键为 REACH/RoHS/CMRT/RBA，值为 合规/不合规)。
- compliant：是否四项全部合规。
- note：给采购员的一句话提示(如有不合规项，点出是哪项)。"""

_llm_with_tools = get_llm("fast").bind_tools(COMPLIANCE_TOOLS)
tools_node = make_tools_node(COMPLIANCE_TOOLS)


def agent_node(state: ComplianceState) -> dict:
    return {"messages": [_llm_with_tools.invoke([SystemMessage(AGENT_PROMPT), *state["messages"]])]}


def should_continue(state: ComplianceState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "structure"


def structure_node(state: ComplianceState) -> dict:
    try:
        result = get_structured_llm(ComplianceReport).invoke(
            [*state["messages"], SystemMessage(STRUCT_PROMPT)]
        )
    except Exception:
        result = ComplianceReport(supplier="", note=state["messages"][-1].content)
    return {"result": result}


def build_compliance_graph():
    builder = StateGraph(ComplianceState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("structure", structure_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", "structure": "structure"}
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("structure", END)
    return builder.compile()


compliance_app = build_compliance_graph()
