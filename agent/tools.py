"""工具(Tools)：agent 的"手"。

@tool 把一个普通函数变成 LLM 可调用的工具。关键点：
- 函数名 + 类型注解 + docstring 会被自动转成 JSON Schema 喂给 LLM，
  LLM 据此决定"要不要调、用什么参数调"。所以 docstring 必须写清楚"什么时候用"。
- MVP 用假数据(mock)，目的是先把 ReAct 循环跑通；
  里程碑4 再把实现换成查你的生产 Postgres(procurement_requirement 表)，
  接口签名不变 → 图完全不用改。这就是"用接口隔离副作用"。
"""
from langchain_core.tools import tool

ALLOWED_PLATFORMS = ("taobao.com", "tmall.com", "jd.com", "1688.com")


@tool
def search_purchase_history(keyword: str) -> str:
    """按物料关键词查询历史采购记录，返回可复用的物料名/规格/链接/上次项目。

    工程师高频复购相同物料，先查历史能一键复用、减少来回沟通。
    收到任何具体物料名时都应先调用本工具。
    """
    mock = {
        "轴承": "SKF 6204-2RS 深沟球轴承 | https://item.taobao.com/item.htm?id=123 | IML001 项目上次买过 10 个",
        "螺丝": "M3x10 内六角圆柱头螺丝 304 不锈钢 | https://item.jd.com/100012.html | 高频复购件",
        "铣刀": "硬质合金立铣刀 4 刃 D6 | https://detail.1688.com/offer/456.html | 加工工具",
    }
    for k, v in mock.items():
        if k in keyword:
            return v
    return "未找到历史记录，需要走新采购，请向工程师索取商品链接。"


@tool
def validate_item_link(url: str) -> str:
    """校验商品链接是否为公司允许的平台(淘宝/天猫/京东/1688)。收到链接时调用。"""
    if any(d in url for d in ALLOWED_PLATFORMS):
        return f"链接合法：{url}"
    return "链接不合法：公司仅允许 淘宝/天猫/京东/1688，请工程师换一个链接。"


TOOLS = [search_purchase_history, validate_item_link]
