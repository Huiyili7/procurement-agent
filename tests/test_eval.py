"""把 eval 接进 CI：默认跳过(要真实 LLM)，设 RUN_EVAL=1 才跑，并对指标设门槛。

这样确定性单测仍是快速、免费、必过的门禁；eval 作为带 secret 的回归 job 单独跑。
"""
import os

import pytest

RUN = os.environ.get("RUN_EVAL") == "1"


@pytest.mark.skipif(not RUN, reason="设 RUN_EVAL=1 且配好 LLM key 才跑评测")
def test_eval_meets_thresholds():
    from eval.run_eval import main

    summary = main()
    # 回归门槛：路由必须全对；其余指标不低于 0.8(弱模型留余量)。
    assert summary.get("routing", 0) == 1.0, f"routing 退化：{summary}"
    for metric in ("field_extraction", "task_success"):
        if metric in summary:
            assert summary[metric] >= 0.8, f"{metric} 退化：{summary}"
