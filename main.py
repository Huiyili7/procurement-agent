"""命令行入口：和采购受理 Agent 多轮对话(含 HITL 二次确认)。

多轮不再靠手动维护 history：父图带 checkpointer + 固定 thread_id，
每轮只投喂新的一条用户消息，历史由 LangGraph 持久化(MVP 是进程内 MemorySaver)。
破坏性工具(下单/转人工)执行前会 interrupt()，这里把确认权交还给人。
"""
import sys

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent.orchestrator import get_orchestrator

# Windows 控制台默认 GBK，LLM 可能吐 emoji/生僻字导致 print 崩溃；统一按 utf-8 输出。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONFIG = {"configurable": {"thread_id": "cli-session"}}
orchestrator = get_orchestrator()


def _handle_interrupts(state: dict) -> dict:
    """只要图停在 interrupt，就把待确认动作展示给人，拿到答复后 resume，直到跑完。"""
    while "__interrupt__" in state:
        payload = state["__interrupt__"][0].value
        print("\n⚠ 需要确认（不可逆动作）：")
        print(f"  动作：{payload.get('tool')}")
        print(f"  参数：{payload.get('args')}")
        ans = input("  执行吗？(y/n)：").strip()
        state = orchestrator.invoke(Command(resume=ans), CONFIG)
    return state


def _show_draft(state: dict) -> None:
    """把父 state 里的结构化摘要打出来——直观看到'隔离回传'的成果。"""
    result = state.get("intake_result")
    if result is None:
        return
    d = result.draft
    print(
        f"  [采购单草稿] 物料={d.item_name} 链接={d.item_url} "
        f"份数={d.quantity} 项目={d.project_code} | 缺={result.missing_fields} | 阶段={result.stage}"
    )


def main() -> None:
    print("采购受理助手已启动（输入 q 退出）")
    while True:
        user = input("\n你：").strip()
        if user.lower() in ("q", "quit", "exit"):
            break
        state = orchestrator.invoke({"messages": [HumanMessage(user)]}, CONFIG)
        state = _handle_interrupts(state)
        print("助手：", state["messages"][-1].content)
        _show_draft(state)


if __name__ == "__main__":
    main()
