"""LLM 统一入口。

为什么单独抽一个文件：整张图只从这里拿模型，换供应商(DeepSeek/通义/OpenAI/…)
只改 .env，不动 agent 逻辑——这是"配置与逻辑分离"，也是面试常考的可维护性点。
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    """返回一个 OpenAI 兼容的 Chat 模型。

    temperature=0：受理场景要稳定、可复现，不要发散。
    base_url 留空则走 OpenAI 官方；填 DeepSeek/通义的兼容端点即可切换。
    """
    return ChatOpenAI(
        model=os.environ.get("MODEL_NAME", "deepseek-chat"),
        temperature=temperature,
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
    )
