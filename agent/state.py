"""图状态(State)：LangGraph 的核心抽象之一。

State 是整张图共享、在节点间流动并被"累积更新"的数据结构。
每个节点接收当前 State，返回"对 State 的局部更新"(一个 dict)，
LangGraph 负责把更新合并回全局 State。

MVP 只需要对话历史。后续里程碑(结构化受理)再往这里加
draft / missing_fields / stage 等字段——加字段不改图结构，体现可扩展性。
"""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """messages 用 Annotated[..., add_messages] 标了一个 reducer：

    普通字段的更新是"覆盖"；而 add_messages 是"追加并按 id 去重/更新"。
    所以节点只要 return {"messages": [新消息]}，历史会自动累积，
    不用自己手动拼接列表——这是 LangGraph 处理对话记忆的标准做法。
    """

    messages: Annotated[list, add_messages]
