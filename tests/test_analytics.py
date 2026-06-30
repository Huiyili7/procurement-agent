"""M4·Analytics：query_spend 聚合正确、analytics_node 同样隔离子图内部消息。"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import orchestrator as orch
from agent.schemas import AnalysisResult
from agent.tools import query_spend


def test_query_spend_by_category():
    out = query_spend.invoke({"group_by": "category"})
    # 刀具总额最高：3400+5600+2800=11800
    assert "刀具" in out
    assert "11800" in out


def test_query_spend_by_project_lists_projects():
    out = query_spend.invoke({"group_by": "project"})
    assert "IML001" in out and "IML002" in out


class _FakeAnalytics:
    def invoke(self, inp, config):
        return {
            "messages": [
                HumanMessage("哪个类别花最多"),
                AIMessage(
                    "", tool_calls=[{"name": "query_spend", "args": {"group_by": "category"}, "id": "1"}]
                ),
                ToolMessage("刀具: 11800元 ...", tool_call_id="1"),
                AIMessage("（深模型综合的长篇推理）"),
            ],
            "result": AnalysisResult(
                answer="刀具是最大开支，约 1.18 万元。", figures={"刀具": 11800.0}, method="按类别求和"
            ),
        }


def test_analytics_node_isolates_and_returns_summary(monkeypatch):
    monkeypatch.setattr(orch, "analytics_app", _FakeAnalytics())
    update = orch.analytics_node(
        {"messages": [HumanMessage("哪个类别花最多")]},
        config={"configurable": {"thread_id": "t"}},
    )
    msgs = update["messages"]
    assert len(msgs) == 1 and isinstance(msgs[0], AIMessage)
    assert "刀具" in msgs[0].content  # 用的是 AnalysisResult.answer
    assert all(not isinstance(m, ToolMessage) for m in msgs)  # 子图内部消息没泄漏
    assert update["analysis_result"].figures["刀具"] == 11800.0
