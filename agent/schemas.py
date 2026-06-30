"""结构化输出(Structured Output)：全程用 Pydantic 约束，不靠 prompt 求 JSON。

为什么单列一个文件：这些模型是 subagent ↔ 父 Orchestrator 之间的"数据契约"。
父图只认这些结构化摘要(不碰 subagent 内部对话消息)，所以它们必须独立、稳定、可被多处复用
(intake 产出 / 父图存储 / 未来 eval 断言期望字段)。
"""
from typing import Literal

from pydantic import BaseModel, Field


class RequirementDraft(BaseModel):
    """采购单草稿：四个必填字段，未知的留 None(而不是空字符串——None 表示"还没问到")。"""

    item_name: str | None = Field(default=None, description="物料名称")
    item_url: str | None = Field(default=None, description="商品链接")
    quantity: int | None = Field(default=None, description="采购份数")
    project_code: str | None = Field(default=None, description="项目代号")


class IntakeResult(BaseModel):
    """Intake subagent 回传给父 Orchestrator 的结构化摘要。

    这是"上下文隔离"的载体：父图只存这个摘要，**不并入 subagent 内部的 messages**。
    """

    draft: RequirementDraft = Field(default_factory=RequirementDraft)
    missing_fields: list[str] = Field(default_factory=list, description="四个必填里还缺哪些")
    stage: Literal["collecting", "ready", "submitted", "transferred"] = Field(
        default="collecting",
        description="collecting=还在收集; ready=四项齐了待确认; submitted=已下单; transferred=已转人工",
    )


class RouteDecision(BaseModel):
    """父 Orchestrator 的路由决策：把用户输入分派到哪个 subagent。

    加 subagent 时往 target 里加枚举 + 在父图加一个节点即可，路由"机制"不变。
    """

    target: Literal["intake", "analytics", "compliance", "direct"] = Field(
        description=(
            "intake=采购受理(买东西/补信息); analytics=花费/统计分析提问; "
            "compliance=供应商合规查验(REACH/RoHS/CMRT/RBA); direct=寒暄或无关,直接回复"
        )
    )
    reason: str = Field(description="为何这样路由(一句话)")
    direct_reply: str | None = Field(
        default=None, description="当 target=direct 时，直接回给用户的话"
    )


class AnalysisResult(BaseModel):
    """Analytics subagent 的结构化摘要(回传父图，与 IntakeResult 对称)。"""

    answer: str = Field(description="给用户的分析结论(自然语言)")
    figures: dict[str, float] = Field(default_factory=dict, description="关键数字，便于审计/复核")
    method: str = Field(default="", description="怎么算的(口径)，可审计")


class ComplianceReport(BaseModel):
    """Compliance subagent 的结构化摘要：供应商的四标志合规情况。"""

    supplier: str = Field(description="供应商名称")
    flags: dict[str, str] = Field(
        default_factory=dict, description="四标志状态，如 {REACH: 合规, RoHS: 不合规}"
    )
    compliant: bool = Field(default=False, description="四项是否全部合规")
    note: str = Field(default="", description="补充说明")
