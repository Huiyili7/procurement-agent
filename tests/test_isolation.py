"""第 4 块·上下文隔离：父图调子图后，子图内部消息不得进入父 state。

不依赖真实 LLM——直接给 intake_node 喂一个"内部有一堆工具消息"的假子图，
验证 wrapper 只把【最终回复 + 结构化摘要】并入父 state。
"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import orchestrator as orch
from agent.schemas import IntakeResult, RequirementDraft


class _FakeIntake:
    """模拟 Intake 子图返回：内部含 tool_calls / ToolMessage，外加最终回复 + result。"""

    def invoke(self, inp, config):
        return {
            "messages": [
                HumanMessage("我要买轴承"),
                AIMessage(
                    "",
                    tool_calls=[
                        {"name": "search_purchase_history", "args": {"keyword": "轴承"}, "id": "1"}
                    ],
                ),
                ToolMessage("SKF 6204 | url", tool_call_id="1"),
                AIMessage("给你找到 SKF 6204，要几个？"),
            ],
            "result": IntakeResult(
                draft=RequirementDraft(item_name="SKF 6204"), missing_fields=["quantity"]
            ),
        }


def test_intake_node_isolates_internal_messages(monkeypatch):
    monkeypatch.setattr(orch, "intake_app", _FakeIntake())
    update = orch.intake_node(
        {"messages": [HumanMessage("我要买轴承")]},
        config={"configurable": {"thread_id": "t"}},
    )
    msgs = update["messages"]
    # 父 state 只拿到一条干净的最终回复
    assert len(msgs) == 1
    assert isinstance(msgs[0], AIMessage) and not getattr(msgs[0], "tool_calls", None)
    assert msgs[0].content == "给你找到 SKF 6204，要几个？"
    # 没有任何子图内部的工具消息泄漏进父 state
    assert all(not isinstance(m, ToolMessage) for m in msgs)
    # 结构化摘要被回传
    assert update["intake_result"].draft.item_name == "SKF 6204"
    assert "quantity" in update["intake_result"].missing_fields
