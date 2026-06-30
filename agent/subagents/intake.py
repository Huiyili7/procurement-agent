"""Intake subagent：采购受理。把模糊需求收集成完整结构化采购单。

它是一个**自带 state、自带工具、自带 system prompt 的独立 compiled 子图**(角色化 subagent)。
相比 M1，多了两件事：
1. 自定义 tools 节点：读工具契约 is_destructive 标志，破坏性工具执行前 interrupt() 二次确认。
   (标志在 tools.py 声明，行为在这里实现——声明与调度解耦。)
2. summarize 节点：ReAct 收尾时用 with_structured_output 抽出 IntakeResult 结构化摘要回传父图。

图结构：
    START → agent → [有 tool_calls?] --是--> tools → agent → …(ReAct 环)
                                      --否--> summarize → END
"""
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from ..config import get_llm, get_structured_llm
from ..schemas import IntakeResult, RequirementDraft
from ..state import IntakeState
from ..tools import INTAKE_TOOLS
from .common import make_tools_node

SYSTEM_PROMPT = """你是 xTool 机械部的采购受理助手。
目标：把工程师模糊的采购需求，收集成完整、结构化的采购单。
规则：
- 必填字段：物料名称、商品链接、采购份数、项目代号。缺什么就追问什么，一次只问一项。
- 收到具体物料名时，先用 search_purchase_history 查历史复用，有就推荐给工程师确认是否沿用。
- 收到商品链接时，用 validate_item_link 校验平台合法性。
- 四个必填都齐、且工程师确认后，调用 create_requirement 落库。
- 需求超出自助受理能力(非标定制/紧急特批)时，用 transfer_to_human 转人工。
- 语气简洁专业，不要一次抛一堆问题。"""

SUMMARIZE_PROMPT = """根据以上对话，抽取当前采购单的结构化状态：
- draft：已知的物料名称/链接/份数/项目代号，未知留 null。
- missing_fields：四个必填里还缺哪些(用字段名 item_name/item_url/quantity/project_code)。
- stage：collecting=还在收集; ready=四项齐了待确认; submitted=已调用 create_requirement; transferred=已转人工。"""

# bind_tools：只绑 Intake 自己的工具(工具裁剪)；快模型(fast tier)做受理。
_llm_with_tools = get_llm("fast").bind_tools(INTAKE_TOOLS)


def agent_node(state: IntakeState) -> dict:
    messages = [SystemMessage(SYSTEM_PROMPT)]
    # 若父图传了"已知草稿"提示，注入进去：模型据此跳过已问到的字段、不重复查历史。
    if state.get("hint"):
        messages.append(SystemMessage(state["hint"]))
    messages += state["messages"]
    return {"messages": [_llm_with_tools.invoke(messages)]}


def should_continue(state: IntakeState) -> str:
    """有 tool_calls → 执行工具；否则 → 收尾抽摘要。"""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "summarize"


# 契约驱动的工具执行节点(破坏性工具→interrupt 二次确认)，由共用工厂生成。
tools_node = make_tools_node(INTAKE_TOOLS)


def summarize_node(state: IntakeState) -> dict:
    """ReAct 收尾：用结构化输出把对话压成 IntakeResult，供父图存储(上下文隔离的回传物)。"""
    structured = get_structured_llm(IntakeResult)
    prompt = [*state["messages"], SystemMessage(SUMMARIZE_PROMPT)]
    try:
        result = structured.invoke(prompt)
    except Exception:
        # 兜底：单次抽取失败不该炸掉整条链，退回空草稿。
        # (注意：开发期这个宽 except 一度把 DeepSeek 的 400 配置错误掩盖成"空草稿"，
        #  靠冒烟断言 draft 非空才发现——这正是 M5 要建 eval 的动机。)
        result = IntakeResult(draft=RequirementDraft())
    return {"result": result}


def build_intake_graph():
    """编译 Intake 子图。注意：**不带自己的 checkpointer**——
    它作为父图节点被调用时，由父图的 checkpointer 统一管理(interrupt/resume 才能跨父子图工作)。"""
    builder = StateGraph(IntakeState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("summarize", summarize_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", "summarize": "summarize"}
    )
    builder.add_edge("tools", "agent")
    builder.add_edge("summarize", END)
    return builder.compile()


intake_app = build_intake_graph()
