"""父 Orchestrator：理解意图 → 路由到 subagent → 聚合结构化摘要 → 回复用户。

它很"薄"：本身不收集采购信息(那是 intake 的活)，只做三件事——
1. route：判断用户输入该走哪个 subagent(M2 只有 intake / direct 直接回复)。
2. intake：调 Intake 子图，**只把最终回复和 IntakeResult 摘要并入父 state**，
   子图内部的工具消息/中间推理一概不进父 state(上下文隔离的落地)。
3. (M2 只有一个 subagent，聚合就是把摘要存起来；M4 多 subagent 时这里做汇总)。

图结构：
    START → route → [intake?] --是--> intake → END
                              --否(direct)--> END(route 节点已写好 direct_reply)
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from .config import get_structured_llm
from .guardrails import screen_input
from .persistence import get_checkpointer
from .schemas import IntakeResult, RouteDecision
from .state import ParentState
from .subagents.analytics import analytics_app
from .subagents.compliance import compliance_app
from .subagents.intake import intake_app

ROUTER_PROMPT = """你是 xTool 采购系统的调度器。看用户最新一条消息，判断该怎么分派：
- target=intake：用户在提采购需求、补充采购信息、或问能不能买某物料(进入受理流程)。
- target=analytics：用户在问花费/统计/分析(哪个项目花得多、各类别占比、各月趋势等)。
- target=compliance：用户在问某供应商是否合规、四标志(REACH/RoHS/CMRT/RBA)情况。
- target=direct：寒暄、问"你能做什么"、或与采购无关。此时给出 direct_reply 直接回答用户。
只输出结构化决策。"""


def guard_node(state: ParentState) -> dict:
    """确定性护栏：拦住注入/越权/异常输入，挡在所有 subagent 与 LLM 调用之前。"""
    last_user = [m for m in state["messages"] if isinstance(m, HumanMessage)][-1]
    verdict = screen_input(last_user.content)
    if not verdict.ok:
        return {
            "route": "blocked",
            "messages": [AIMessage(f"抱歉，无法处理该输入（{verdict.reason}）。请用正常的采购需求描述。")],
        }
    return {"route": "pass"}  # 显式置位，避免上一轮的 route 在 checkpointer 里残留


def guard_selector(state: ParentState) -> str:
    return END if state.get("route") == "blocked" else "route"


def route_node(state: ParentState) -> dict:
    """用结构化输出做意图分类。失败兜底为 intake(宁可多受理，不漏需求)。"""
    router = get_structured_llm(RouteDecision)
    try:
        decision: RouteDecision = router.invoke([SystemMessage(ROUTER_PROMPT), *state["messages"]])
    except Exception:
        decision = RouteDecision(target="intake", reason="路由解析失败，默认走受理")

    update: dict = {"route": decision.target}
    if decision.target == "direct":
        update["messages"] = [
            AIMessage(decision.direct_reply or "你好，我是采购受理助手，直接说要买什么吧。")
        ]
    return update


def route_selector(state: ParentState) -> str:
    route = state.get("route")
    return route if route in ("intake", "analytics", "compliance") else END


def _draft_hint(result: IntakeResult | None) -> str:
    """把上一轮的草稿压成一句"已知信息"提示给子图(§5b Q1：减少跨轮重复查历史)。"""
    if result is None:
        return ""
    d = result.draft
    known = {k: v for k, v in d.model_dump().items() if v is not None}
    if not known:
        return ""
    return f"已知的采购单信息(无需重复查询)：{known}；仍缺：{result.missing_fields}。"


def intake_node(state: ParentState, config) -> dict:
    """Wrapper：调 Intake 子图。隔离的关键就在这一层——

    输入：只把"用户可见对话"(Human + 不带 tool_calls 的 AI)喂给子图当上下文，
         外加上一轮草稿的 hint(子图跨父轮是新鲜启动的，靠 hint 续上下文、不重复查历史)。
    输出：只取子图最终回复 + IntakeResult 摘要并入父 state。
    子图内部的 ToolMessage / 带 tool_calls 的中间 AIMessage 全部留在子图，进不了父 state。
    传入 config 是为了让子图内的 interrupt() 能冒泡到父图、并支持 Command(resume=) 续跑。
    """
    seed = [
        m
        for m in state["messages"]
        if isinstance(m, HumanMessage)
        or (isinstance(m, AIMessage) and not getattr(m, "tool_calls", None))
    ]
    out = intake_app.invoke(
        {"messages": seed, "hint": _draft_hint(state.get("intake_result"))}, config
    )
    reply = out["messages"][-1].content
    return {"messages": [AIMessage(reply)], "intake_result": out.get("result")}


def analytics_node(state: ParentState, config) -> dict:
    """Wrapper：调 Analytics 子图(同样隔离——只把最终结论 + AnalysisResult 摘要并入父 state)。

    Analytics 是一次性问答，无需 hint；用最新用户问题做输入。
    """
    question = [m for m in state["messages"] if isinstance(m, HumanMessage)][-1]
    out = analytics_app.invoke({"messages": [question]}, config)
    result = out.get("result")
    reply = result.answer if result is not None else out["messages"][-1].content
    return {"messages": [AIMessage(reply)], "analysis_result": result}


def compliance_node(state: ParentState, config) -> dict:
    """Wrapper：调 Compliance 子图(同样隔离，回传 ComplianceReport 摘要)。"""
    question = [m for m in state["messages"] if isinstance(m, HumanMessage)][-1]
    out = compliance_app.invoke({"messages": [question]}, config)
    result = out.get("result")
    if result is not None:
        flags = " ".join(f"{k}:{v}" for k, v in result.flags.items())
        reply = f"供应商「{result.supplier}」合规情况：{flags}。{result.note}"
    else:
        reply = out["messages"][-1].content
    return {"messages": [AIMessage(reply)], "compliance_result": result}


def build_orchestrator(checkpointer=None):
    builder = StateGraph(ParentState)
    builder.add_node("guard", guard_node)
    builder.add_node("route", route_node)
    builder.add_node("intake", intake_node)
    builder.add_node("analytics", analytics_node)
    builder.add_node("compliance", compliance_node)
    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", guard_selector, {"route": "route", END: END})
    builder.add_conditional_edges(
        "route",
        route_selector,
        {"intake": "intake", "analytics": "analytics", "compliance": "compliance", END: END},
    )
    builder.add_edge("intake", END)
    builder.add_edge("analytics", END)
    builder.add_edge("compliance", END)
    # 父图带 checkpointer：多轮对话靠 thread_id 续；interrupt/resume 也依赖它。
    # 后端由 get_checkpointer() 按 CHECKPOINTER 环境变量选(memory|sqlite|postgres)，图结构不变。
    return builder.compile(checkpointer=checkpointer or get_checkpointer())


_orchestrator = None


def get_orchestrator():
    """惰性单例：首次用到才编译(才连 checkpointer)。

    为什么惰性：postgres checkpointer 在编译时就要连 DB；若在 import 时就建，
    容器启动顺序(app 先于 DB ready)会直接炸。惰性 + 启动重试让 import 不触发连接。
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator
