"""LLM 统一入口。

为什么单独抽一个文件：整张图只从这里拿模型，换供应商(DeepSeek/通义/OpenAI/…)
只改 .env，不动 agent 逻辑——这是"配置与逻辑分离"，也是面试常考的可维护性点。
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm(tier: str = "fast", temperature: float = 0.0) -> ChatOpenAI:
    """返回一个 OpenAI 兼容的 Chat 模型，按 tier 做模型分层(PRD §5 机制4)。

    - tier="fast"(默认)：deepseek-chat，省/快，**支持 function-calling**(工具调用/结构化输出靠它)。
    - tier="deep"：deepseek-reasoner，强推理，但**不支持 function-calling**
      (实测报 400 "Thinking mode does not support this tool_choice")——
      所以深模型只用于"纯推理综合"这类无工具步骤，绝不用于 bind_tools / 结构化输出。

    temperature=0：受理/分析场景要稳定可复现，不发散。
    base_url 留空走 OpenAI 官方；填 DeepSeek/通义兼容端点即可切换。
    """
    model = (
        os.environ.get("MODEL_NAME", "deepseek-chat")
        if tier == "fast"
        else os.environ.get("DEEP_MODEL_NAME", "deepseek-reasoner")
    )
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
    )


def get_structured_llm(schema, temperature: float = 0.0):
    """返回一个被强制输出指定 Pydantic schema 的模型。**固定走 fast tier**——

    method="function_calling" 是关键：DeepSeek 等 OpenAI 兼容端点**不支持**
    with_structured_output 默认走的 json_schema response_format(会报 400
    "This response_format type is unavailable now")，必须走 function-calling 通道。
    而深模型连 function-calling 都不支持，所以结构化输出只能用快模型。
    集中在这里：所有结构化输出共用，换供应商/换方法只改这一处。
    """
    return get_llm("fast", temperature).with_structured_output(schema, method="function_calling")
