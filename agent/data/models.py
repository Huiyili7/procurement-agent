"""数据层的领域模型：一条历史采购记录长什么样。

为什么用 Pydantic 而不是裸 dict/字符串：repository 返回**结构化记录**，
"给模型看的精简文本"由记录自己负责渲染(to_model_facing)。
这样"数据"和"呈现"分离——换数据源(seed→real)不影响工具怎么把它讲给 LLM。
"""
from pydantic import BaseModel, Field


class PurchaseRecord(BaseModel):
    """一条可复用的历史采购记录。"""

    item_name: str = Field(description="物料名称/规格")
    url: str = Field(description="商品链接")
    last_project: str = Field(description="上次采购的项目代号")
    note: str = Field(default="", description="补充说明，如'上次买过 10 个'")
    match_terms: list[str] = Field(default_factory=list, description="用于关键词匹配的词")

    def to_model_facing(self) -> str:
        """精简的 model-facing 文本：回给 LLM 的内容要短，别把整个对象 JSON 塞进 context。"""
        tail = f" | {self.last_project} {self.note}".rstrip()
        return f"{self.item_name} | {self.url}{tail}"


class SpendRecord(BaseModel):
    """一条花费记录(供 Analytics 做花费/结构分析)。"""

    project: str = Field(description="项目代号")
    category: str = Field(description="物料类别，如 轴承/刀具/紧固件")
    amount: float = Field(description="金额(元)")
    month: str = Field(description="月份 YYYY-MM")
