"""第 3 块·HITL：破坏性工具执行前 interrupt()，放行才执行、否则取消；只读工具不打断。

直接手搓一个带 tool_calls 的 AIMessage 喂给真实 tools_node，无需 LLM。
"""
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.state import IntakeState
from agent.subagents.intake import tools_node


def _mini_graph():
    b = StateGraph(IntakeState)
    b.add_node("tools", tools_node)
    b.add_edge(START, "tools")
    b.add_edge("tools", END)
    return b.compile(checkpointer=MemorySaver())


def _destructive_call_state():
    return {
        "messages": [
            AIMessage(
                "",
                tool_calls=[
                    {
                        "name": "create_requirement",
                        "args": {
                            "item_name": "SKF 6204",
                            "item_url": "https://item.taobao.com/item.htm?id=123",
                            "quantity": 10,
                            "project_code": "IML001",
                        },
                        "id": "c1",
                    }
                ],
            )
        ]
    }


def test_destructive_interrupts_then_executes_on_yes():
    g, cfg = _mini_graph(), {"configurable": {"thread_id": "h1"}}
    s = g.invoke(_destructive_call_state(), cfg)
    assert "__interrupt__" in s
    assert s["__interrupt__"][0].value["tool"] == "create_requirement"
    s = g.invoke(Command(resume="y"), cfg)
    assert isinstance(s["messages"][-1], ToolMessage)
    assert "已创建采购单" in s["messages"][-1].content


def test_destructive_cancels_on_no():
    g, cfg = _mini_graph(), {"configurable": {"thread_id": "h2"}}
    g.invoke(_destructive_call_state(), cfg)
    s = g.invoke(Command(resume="n"), cfg)
    assert isinstance(s["messages"][-1], ToolMessage)
    assert "取消" in s["messages"][-1].content


def test_readonly_tool_does_not_interrupt():
    g, cfg = _mini_graph(), {"configurable": {"thread_id": "h3"}}
    s = g.invoke(
        {
            "messages": [
                AIMessage(
                    "",
                    tool_calls=[
                        {"name": "search_purchase_history", "args": {"keyword": "轴承"}, "id": "r1"}
                    ],
                )
            ]
        },
        cfg,
    )
    assert "__interrupt__" not in s
    assert isinstance(s["messages"][-1], ToolMessage)
