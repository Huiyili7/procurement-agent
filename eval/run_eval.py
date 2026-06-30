"""评测 harness：拿 golden 样本跑系统，算指标，出报告。

为什么 agent 项目离不开它：弱模型(DeepSeek)的工具调用/抽取/路由都不稳，
"看着能跑"≠"对"。eval 把质量变成**可度量、可回归**的数字——改 prompt/换模型前后对比，
防止"改一处崩一片"。（开发期 summarize 的宽 except 掩盖 400 的 bug，就是缺这层兜不住。）

指标：
- routing accuracy：父图路由到的 target 是否等于期望。
- field extraction accuracy：intake 抽出的 draft 关键字段是否等于期望。
- task success (LLM-as-judge)：用模型判断回复是否满足自然语言判据。

注意：本 harness **会真实调用 LLM**，不进默认的确定性单测；按需 `python -m eval.run_eval`。
CI 里用带 secret 的单独 job 跑(见 eval/README.md)。
"""
import json
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from agent.config import get_structured_llm
from agent.orchestrator import build_orchestrator

_GOLDEN = Path(__file__).parent / "golden.jsonl"


class Verdict(BaseModel):
    passed: bool = Field(description="回复是否满足判据")
    reason: str = Field(description="判定理由(一句话)")


def _judge(user_input: str, criterion: str, reply: str) -> Verdict:
    prompt = (
        f"用户输入：{user_input}\n判据：{criterion}\n助手回复：{reply}\n"
        "请判断助手回复是否满足判据。"
    )
    try:
        return get_structured_llm(Verdict).invoke(prompt)
    except Exception as e:  # 判官本身失败也要记录，不静默
        return Verdict(passed=False, reason=f"judge 调用失败：{e}")


def _run_case(case: dict) -> dict:
    """跑一个样本，返回它的实际结果与逐项判定。"""
    app = build_orchestrator()
    cfg = {"configurable": {"thread_id": f"eval-{case['id']}"}}
    state = app.invoke({"messages": [HumanMessage(case["input"])]}, cfg)
    # 评测中遇到下单确认就取消(n)，避免副作用、拿到最终回复
    while "__interrupt__" in state:
        state = app.invoke(Command(resume="n"), cfg)

    result = {"id": case["id"], "checks": {}}
    route = state.get("route")

    if "expect_route" in case:
        result["checks"]["routing"] = route == case["expect_route"]

    if "expect_draft" in case:
        draft = state.get("intake_result").draft.model_dump() if state.get("intake_result") else {}
        result["checks"]["field_extraction"] = all(
            draft.get(k) == v for k, v in case["expect_draft"].items()
        )

    if "judge" in case:
        reply = state["messages"][-1].content
        result["checks"]["task_success"] = _judge(case["input"], case["judge"], reply).passed

    return result


def main() -> dict:
    cases = [json.loads(line) for line in _GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [_run_case(c) for c in cases]

    # 按指标聚合
    agg: dict[str, list[bool]] = {}
    print(f"\n{'case':<20} {'metric':<18} {'result'}")
    print("-" * 50)
    for r in rows:
        for metric, ok in r["checks"].items():
            agg.setdefault(metric, []).append(ok)
            print(f"{r['id']:<20} {metric:<18} {'✓' if ok else '✗'}")

    print("\n=== 汇总 ===")
    summary = {}
    for metric, vals in agg.items():
        acc = sum(vals) / len(vals)
        summary[metric] = acc
        print(f"{metric:<18} {sum(vals)}/{len(vals)} = {acc:.0%}")
    return summary


if __name__ == "__main__":
    main()
