"""护栏(Guardrails)：父图入口的确定性输入校验。

为什么用规则而不是 LLM：护栏要拦的是"越权/注入/异常输入"，这类判定必须**确定性、可解释、
不可被同一个被攻击的模型绕过**(PRD §9：不可逆动作走确定性校验)。用 LLM 判 LLM 的安全是循环论证。
所以这里是纯规则——快、稳、可测，挡在所有 subagent 之前。
"""
import re

from pydantic import BaseModel

MAX_LEN = 2000

# prompt-injection / 越权指令的常见特征(中英)
_INJECTION_PATTERNS = [
    r"ignore\s+(the\s+|all\s+)?(previous|above)",
    r"disregard\s+(the\s+|all\s+)?(previous|above)",
    r"reveal\s+your\s+(instructions|system\s+prompt|prompt)",
    r"you\s+are\s+now\b",
    r"忽略(上面|之前|以上).{0,6}(指令|提示|规则|设定)",
    r"(泄露|告诉我).{0,8}(系统提示|提示词|system\s*prompt)",
    r"你现在(是|要扮演)",
]


class GuardVerdict(BaseModel):
    ok: bool
    reason: str = ""


def screen_input(text: str) -> GuardVerdict:
    """放行返回 ok=True；命中规则返回 ok=False + 原因。"""
    if not text or not text.strip():
        return GuardVerdict(ok=False, reason="空输入")
    if len(text) > MAX_LEN:
        return GuardVerdict(ok=False, reason=f"输入过长(>{MAX_LEN} 字符)")
    low = text.lower()
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, low):
            return GuardVerdict(ok=False, reason="疑似 prompt-injection / 越权指令")
    return GuardVerdict(ok=True)
