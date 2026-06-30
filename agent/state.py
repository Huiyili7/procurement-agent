"""图状态(State)：父图与子图各有自己的 state schema——这是"上下文隔离"的根。

关键设计：
- IntakeState.messages = Intake subagent 内部的 ReAct 消息(工具调用/结果/中间推理)。
- ParentState.messages = 父↔用户的对话(用户可见的那一条线)。
两者是**不同的 state schema**。父图调子图时只通过 wrapper 节点拿回结构化摘要(IntakeResult)，
把"给用户的最终回复"塞回 ParentState.messages，而**子图内部那一堆消息根本进不了父 state**。
LangGraph 不会自动把两个 schema 的同名字段合并(我们用的是 wrapper 函数节点，不是直接挂 compiled 子图)，
所以隔离是结构性的，不是靠纪律维持的。

State 是累积更新的：节点返回"局部更新 dict"，LangGraph 合并回全局 State。
messages 用 add_messages reducer→追加并按 id 去重；普通字段→覆盖。
"""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from .schemas import AnalysisResult, IntakeResult


class IntakeState(TypedDict, total=False):
    """Intake subagent 自己的状态。total=False：result/hint 可缺省。"""

    messages: Annotated[list, add_messages]
    result: IntakeResult
    # hint：父图把"上一轮已知的草稿"作为上下文传进来，避免子图每轮重复查历史(见 §5b Q1)。
    hint: str


class AnalyticsState(TypedDict, total=False):
    """Analytics subagent 自己的状态(与 IntakeState 对称，各自独立 = 隔离)。"""

    messages: Annotated[list, add_messages]
    result: AnalysisResult


class ParentState(TypedDict, total=False):
    """父 Orchestrator 的状态。只存用户可见对话 + 路由 + 各 subagent 的结构化摘要。"""

    messages: Annotated[list, add_messages]
    route: str
    intake_result: IntakeResult
    analysis_result: AnalysisResult
