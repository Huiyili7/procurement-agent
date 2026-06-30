"""Compliance：check_compliance 查表确定性正确 + compliance_node 隔离子图内部消息。"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import orchestrator as orch
from agent.schemas import ComplianceReport
from agent.tools import check_compliance


def test_check_compliance_all_pass():
    out = check_compliance.invoke({"supplier": "SKF"})
    assert "SKF" in out and "全部合规" in out


def test_check_compliance_has_failing_flag():
    out = check_compliance.invoke({"supplier": "米思米"})
    assert "CMRT:不合规" in out and "存在不合规项" in out


def test_check_compliance_unknown_supplier():
    out = check_compliance.invoke({"supplier": "火星供应商"})
    assert "人工核验" in out


class _FakeCompliance:
    def invoke(self, inp, config):
        return {
            "messages": [
                HumanMessage("SKF 合规吗"),
                AIMessage("", tool_calls=[{"name": "check_compliance", "args": {"supplier": "SKF"}, "id": "1"}]),
                ToolMessage("SKF | REACH:合规 ... | 四项全部合规", tool_call_id="1"),
                AIMessage("（内部）"),
            ],
            "result": ComplianceReport(
                supplier="SKF",
                flags={"REACH": "合规", "RoHS": "合规", "CMRT": "合规", "RBA": "合规"},
                compliant=True,
            ),
        }


def test_compliance_node_isolates_and_summarizes(monkeypatch):
    monkeypatch.setattr(orch, "compliance_app", _FakeCompliance())
    update = orch.compliance_node(
        {"messages": [HumanMessage("SKF 合规吗")]},
        config={"configurable": {"thread_id": "t"}},
    )
    msgs = update["messages"]
    assert len(msgs) == 1 and isinstance(msgs[0], AIMessage)
    assert "SKF" in msgs[0].content
    assert all(not isinstance(m, ToolMessage) for m in msgs)
    assert update["compliance_result"].compliant is True
