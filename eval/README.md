# eval（评测）

Agent 工程严谨度的核心：把质量变成**可度量、可回归**的数字。弱模型(DeepSeek)的路由/抽取/工具调用都不稳，"看着能跑"≠"对"——eval 在改 prompt/换模型前后做对比，防止"改一处崩一片"。

## 怎么跑

```bash
# 真实调用 LLM(需 .env 配好 key)，打印逐项判定 + 指标汇总
RUN_EVAL=1 python -m eval.run_eval
```

也接进了 pytest（默认跳过，避免日常测试调 API）：
```bash
RUN_EVAL=1 python -m pytest tests/test_eval.py -q   # 对指标设回归门槛
```

## 数据集

`golden.jsonl`，每行一个样本，按需标注期望：
- `expect_route`：期望父图路由到的 target（intake/analytics/direct）。
- `expect_draft`：期望 intake 抽出的关键字段（子集匹配）。
- `judge`：开放式判据，交给 LLM-as-judge 判通过与否。

## 指标

| 指标 | 度量什么 | 怎么算 |
|---|---|---|
| routing accuracy | 意图分类准不准 | `state.route == expect_route` |
| field extraction | 结构化抽取准不准 | `IntakeResult.draft` 命中 `expect_draft` |
| task success | 开放式回复成功率 | `with_structured_output(Verdict)` LLM-as-judge |

**当前基线**：routing 8/8=100% · field 1/1=100% · task_success 3/3=100%。

## CI 思路

确定性单测(24 个、不联网、免费)是必过门禁；eval 真调 LLM，用带 secret 的单独 job 跑(`RUN_EVAL=1`)，并设回归门槛(routing 必须 100%，其余 ≥80%)。这样开发循环快、回归有保障、密钥不进主流程。

## 可观测（LangSmith）

env 驱动、零代码改动：`.env` 设 `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY`，每次 run 的节点路径/工具调用/token/延迟/成本自动上报。不设则零开销。
