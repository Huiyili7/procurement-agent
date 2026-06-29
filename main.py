"""命令行入口：在终端和采购受理 agent 对话。

MVP 用一个本地 history 列表手动维护多轮对话——足够把循环跑通。
里程碑4 会用 checkpointer + thread_id 取代它(持久化记忆)，那才是生产做法。
"""
from langchain_core.messages import HumanMessage

from agent.graph import graph


def main() -> None:
    print("采购受理助手已启动（输入 q 退出）")
    history: list = []
    while True:
        user = input("\n你：").strip()
        if user.lower() in ("q", "quit", "exit"):
            break
        # invoke 会把图从 START 跑到 END，返回最终 State
        result = graph.invoke({"messages": history + [HumanMessage(user)]})
        history = result["messages"]  # 含本轮 AI 回复 + 工具消息，作为下轮上下文
        print("助手：", history[-1].content)


if __name__ == "__main__":
    main()
