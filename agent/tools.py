"""工具(Tools) + 工具契约层(Tool-as-Contract)。

第一性原理：Tool 不是一个普通函数，是一个带"契约"的软件单元。
主循环/调度器只读契约上的标志做决策(要不要二次确认、能不能并发)，
而不把工具名写死进调度逻辑——加一个新工具，主循环一行都不用改。

契约由三部分组成：
1. args_schema(Pydantic)：一份 schema 双用——既是喂给 LLM 的 function-calling
   schema(它据此决定怎么调)，又是运行时入参校验(挡掉"该传 int 却传了 str"这类 bug)。
2. 副作用标志(挂在 tool.extras)：is_read_only / is_destructive / is_concurrency_safe。
   调度器读它决定行为(destructive → 执行前 interrupt 二次确认；read_only 且并发安全 → 可并行)。
   (extras 是 langchain v1 给工具挂"工具级元数据"的入口，旧文档里叫 metadata；
    它不会混进喂给 LLM 的 function-calling schema，纯供我们自己的调度器读。)
3. activity：给用户看的 spinner 文案。

@tool 装饰器原生支持 args_schema= 和 extras=，所以契约不需要自造框架，
只需把"标志"约束成一个不会自相矛盾的类型。
"""
from dataclasses import asdict, dataclass
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .data import get_repository

ALLOWED_PLATFORMS = ("taobao.com", "tmall.com", "jd.com", "1688.com")


# ── 副作用契约 ────────────────────────────────────────────────
@dataclass(frozen=True)
class SideEffects:
    """工具的副作用契约。三个标志正交回答三个调度问题：

    - is_read_only：只读、无副作用？(纯查询)
    - is_destructive：不可逆、需人确认？(下单 / 通知人)
    - is_concurrency_safe：可与其他工具并发执行？

    不变式：只读工具不可能同时是破坏性的——若两者都为真，说明标错了，
    调度器会误判，这里在定义期直接抛错(fail fast)。
    """

    is_read_only: bool
    is_destructive: bool
    is_concurrency_safe: bool

    def __post_init__(self) -> None:
        if self.is_read_only and self.is_destructive:
            raise ValueError("矛盾的契约：is_read_only 与 is_destructive 不能同时为真")


# 三种语义清晰的组合，避免在每个工具上手抄三个布尔(抄错一个就是埋 bug)
READ_ONLY = SideEffects(is_read_only=True, is_destructive=False, is_concurrency_safe=True)
WRITE_DESTRUCTIVE = SideEffects(is_read_only=False, is_destructive=True, is_concurrency_safe=False)
NOTIFY_DESTRUCTIVE = SideEffects(is_read_only=False, is_destructive=True, is_concurrency_safe=True)


def contract(effects: SideEffects, activity: str) -> dict:
    """把副作用标志 + spinner 文案打成一个字典，挂到工具的 extras 上。
    所有契约相关的"魔法字符串"只在这里出现一次；调度器也只认这个结构。
    """
    return {**asdict(effects), "activity": activity}


# ── 工具 ──────────────────────────────────────────────────────
@tool(extras=contract(READ_ONLY, "正在查历史采购…"))
def search_purchase_history(keyword: str) -> str:
    """按物料关键词查询历史采购记录，返回可复用的物料名/规格/链接/上次项目。

    工程师高频复购相同物料，先查历史能一键复用、减少来回沟通。
    收到任何具体物料名时都应先调用本工具。
    """
    # 经 PurchaseRepository 取数：工具不感知数据来自 seed 还是 real(副作用隔离)。
    records = get_repository().search_history(keyword)
    if not records:
        return "未找到历史记录，需要走新采购，请向工程师索取商品链接。"
    # 精简 model-facing 返回：最多 3 条，避免把大 JSON 塞进 context。
    return "\n".join(r.to_model_facing() for r in records[:3])


@tool(extras=contract(READ_ONLY, "正在校验商品链接…"))
def validate_item_link(url: str) -> str:
    """校验商品链接是否为公司允许的平台(淘宝/天猫/京东/1688)。收到链接时调用。"""
    if any(d in url for d in ALLOWED_PLATFORMS):
        return f"链接合法：{url}"
    return "链接不合法：公司仅允许 淘宝/天猫/京东/1688，请工程师换一个链接。"


class CreateRequirementArgs(BaseModel):
    """create_requirement 的入参契约：这份 Pydantic 同时是 LLM 的 schema 和运行时校验。

    quantity 约束为正整数——直接挡掉模型"把份数当字符串传"或传 0/负数的经典错误，
    错的入参根本进不了函数体(在工具边界 fail fast，而不是在业务逻辑里炸)。
    """

    item_name: str = Field(description="物料名称，如 'SKF 6204-2RS 深沟球轴承'")
    item_url: str = Field(description="商品链接，须为淘宝/天猫/京东/1688")
    quantity: int = Field(gt=0, description="采购份数，正整数")
    project_code: str = Field(description="项目代号，如 IML001")


@tool(args_schema=CreateRequirementArgs, extras=contract(WRITE_DESTRUCTIVE, "正在创建采购单…"))
def create_requirement(item_name: str, item_url: str, quantity: int, project_code: str) -> str:
    """把收集齐的四个必填字段落库为一张采购单。

    这是不可逆动作(destructive)：四个字段务必先收集完整、经工程师确认后再调用。
    """
    # mock 回执：真正落库走 PurchaseRepository(后续里程碑接入)，此处只回执确认信息。
    # 注意 is_destructive=True 的"执行前二次确认"行为由第 3 块自定义 tools 节点实现，
    # 本工具自身不关心确认——它只声明自己危险，怎么拦是调度器的事。
    return (
        f"已创建采购单：{item_name} ×{quantity}，项目 {project_code}，链接 {item_url}。"
        "（mock 回执，后续接入数据层真正写入）"
    )


class TransferToHumanArgs(BaseModel):
    reason: str = Field(description="转人工的原因，如 '需求超出自助受理范围'")
    summary: str = Field(description="给采购员的需求摘要，越完整越好")


@tool(args_schema=TransferToHumanArgs, extras=contract(NOTIFY_DESTRUCTIVE, "正在转交人工采购…"))
def transfer_to_human(reason: str, summary: str) -> str:
    """当需求超出自助受理能力(非标定制 / 紧急特批等)时，转交人工采购。

    这会真的通知到人(destructive)，确认后再调用。
    """
    return f"已转交人工采购。原因：{reason}。采购员将收到摘要：{summary}"


class QuerySpendArgs(BaseModel):
    group_by: Literal["project", "category", "month"] = Field(
        description="按哪个维度汇总花费：project=项目 / category=物料类别 / month=月份"
    )


@tool(args_schema=QuerySpendArgs, extras=contract(READ_ONLY, "正在统计花费…"))
def query_spend(group_by: str) -> str:
    """按项目/类别/月份汇总历史采购花费。回答"哪个项目/类别花得最多""各月花费"这类问题时调用。"""
    records = get_repository().spend_records()
    if not records:
        return "暂无花费数据。"
    agg: dict[str, float] = {}
    for r in records:
        key = getattr(r, group_by)
        agg[key] = agg.get(key, 0.0) + r.amount
    total = sum(agg.values())
    lines = [f"{k}: {v:.0f}元" for k, v in sorted(agg.items(), key=lambda x: -x[1])]
    return f"按 {group_by} 汇总(总计 {total:.0f}元)：\n" + "\n".join(lines)


# 工具裁剪(PRD §5 机制2)：每个 subagent 只绑定自己那几个工具，不是一股脑全给。
INTAKE_TOOLS = [search_purchase_history, validate_item_link, create_requirement, transfer_to_human]
ANALYTICS_TOOLS = [query_spend]
# 全量注册表(给契约测试/调度器用)。
TOOLS = INTAKE_TOOLS + ANALYTICS_TOOLS
