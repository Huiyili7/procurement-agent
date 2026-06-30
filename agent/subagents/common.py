"""Subagent 共用件：契约驱动的工具执行节点工厂。

为什么抽工厂：这个 tools 节点的逻辑是"读工具契约 is_destructive 决定要不要 HITL"，
**与具体是哪些工具无关**——所以它该是 tool-set-agnostic 的。intake 和 analytics 共用同一份，
传入各自裁剪后的工具集即可。这正体现第 1 块"调度只认契约、不认工具名"。
"""
from langchain_core.messages import ToolMessage
from langgraph.types import interrupt


def _approved(decision) -> bool:
    """把人给的确认信号(bool 或字符串)归一成是否放行。"""
    if isinstance(decision, bool):
        return decision
    return str(decision).strip().lower() in ("y", "yes", "是", "确认", "approve", "true")


def make_tools_node(tools):
    """生成一个工具执行节点：破坏性工具(is_destructive)执行前 interrupt 二次确认，其余直接执行。"""
    by_name = {t.name: t for t in tools}

    def tools_node(state) -> dict:
        last = state["messages"][-1]
        out: list = []
        for call in last.tool_calls:
            tool = by_name[call["name"]]
            extras = tool.extras or {}
            if extras.get("is_destructive"):
                decision = interrupt(
                    {
                        "type": "confirm_destructive",
                        "tool": call["name"],
                        "args": call["args"],
                        "activity": extras.get("activity"),
                    }
                )
                if not _approved(decision):
                    out.append(
                        ToolMessage(
                            content=f"用户取消了 {call['name']}，请改问工程师下一步怎么办。",
                            tool_call_id=call["id"],
                        )
                    )
                    continue
            result = tool.invoke(call["args"])
            out.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        return {"messages": out}

    return tools_node
