"""M3·持久化：sqlite 下"重启后凭 thread_id 续跑"、checkpointer 工厂、草稿 hint。"""
import sqlite3

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.orchestrator import _draft_hint
from agent.persistence import get_checkpointer
from agent.schemas import IntakeResult, RequirementDraft
from agent.state import IntakeState
from agent.subagents.intake import tools_node


def _build(saver):
    b = StateGraph(IntakeState)
    b.add_node("tools", tools_node)
    b.add_edge(START, "tools")
    b.add_edge("tools", END)
    return b.compile(checkpointer=saver)


def _destructive_state():
    return {
        "messages": [
            AIMessage(
                "",
                tool_calls=[
                    {
                        "name": "create_requirement",
                        "args": {
                            "item_name": "SKF 6204",
                            "item_url": "https://item.taobao.com/x",
                            "quantity": 10,
                            "project_code": "IML001",
                        },
                        "id": "c1",
                    }
                ],
            )
        ]
    }


def test_resume_across_restart_with_sqlite(tmp_path):
    """模拟"进程崩溃后重启"：丢弃 app1/连接，用全新 app2 + 同一文件/thread_id 续跑。"""
    path = str(tmp_path / "cp.sqlite")
    cfg = {"configurable": {"thread_id": "t1"}}

    conn1 = sqlite3.connect(path, check_same_thread=False)
    app1 = _build(SqliteSaver(conn1))
    s = app1.invoke(_destructive_state(), cfg)
    assert "__interrupt__" in s  # 停在确认点，断点已落 sqlite
    conn1.close()
    del app1  # “进程退出”

    conn2 = sqlite3.connect(path, check_same_thread=False)
    app2 = _build(SqliteSaver(conn2))
    s2 = app2.invoke(Command(resume="y"), cfg)  # 全新实例，凭 thread_id 续
    assert isinstance(s2["messages"][-1], ToolMessage)
    assert "已创建采购单" in s2["messages"][-1].content
    conn2.close()


def test_get_checkpointer_factory(monkeypatch, tmp_path):
    monkeypatch.setenv("CHECKPOINTER", "memory")
    assert isinstance(get_checkpointer(), MemorySaver)
    monkeypatch.setenv("CHECKPOINTER", "sqlite")
    monkeypatch.setenv("CHECKPOINTER_PATH", str(tmp_path / "x.sqlite"))
    assert get_checkpointer().__class__.__name__ == "SqliteSaver"
    monkeypatch.setenv("CHECKPOINTER", "mars")
    with pytest.raises(ValueError):
        get_checkpointer()


def test_draft_hint():
    assert _draft_hint(None) == ""
    assert _draft_hint(IntakeResult(draft=RequirementDraft())) == ""
    h = _draft_hint(
        IntakeResult(draft=RequirementDraft(item_name="轴承"), missing_fields=["quantity"])
    )
    assert "轴承" in h and "quantity" in h
