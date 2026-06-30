"""FastAPI 服务：把 orchestrator 包成 HTTP 接口，供 Web 前端调用。

难点是把"多轮 + HITL(interrupt/resume)"映射到无状态的 HTTP 上：
- 多轮：客户端带一个 thread_id，状态由 checkpointer 按 thread_id 持久化(HTTP 无状态，记忆在服务端)。
- HITL：/chat 若停在 interrupt，就返回 type=interrupt + 待确认动作；前端弹确认框，
  用户答复后调 /resume 把 Command(resume=...) 喂回同一 thread_id 续跑。
两个端点形状一致(_shape)，前端统一处理。
"""
import json

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from agent.orchestrator import get_orchestrator

app = FastAPI(title="采购受理 Agent")

# 节点 → 给用户看的步骤文案(流式渲染用)。
_STEP_LABELS = {
    "guard": "🛡 输入安全检查",
    "route": "🧭 意图路由",
    "intake": "🛒 采购受理",
    "analytics": "📊 花费分析",
}


class ChatIn(BaseModel):
    thread_id: str
    message: str


class ResumeIn(BaseModel):
    thread_id: str
    decision: str


def _final(state: dict) -> dict:
    """把(已跑完的)state 压成最终回复 JSON。"""
    out: dict = {
        "type": "reply",
        "reply": state["messages"][-1].content,
        "route": state.get("route"),
    }
    if state.get("intake_result"):
        r = state["intake_result"]
        out["draft"] = r.draft.model_dump()
        out["missing"] = r.missing_fields
        out["stage"] = r.stage
    if state.get("analysis_result"):
        out["analysis"] = state["analysis_result"].model_dump()
    if state.get("compliance_result"):
        out["compliance"] = state["compliance_result"].model_dump()
    return out


def _shape(state: dict) -> dict:
    """非流式端点用：覆盖 interrupt / 普通回复两种。"""
    if "__interrupt__" in state:
        p = state["__interrupt__"][0].value
        return {"type": "interrupt", "tool": p.get("tool"), "args": p.get("args")}
    return _final(state)


def _sse(obj: dict) -> str:
    """打包成一条 SSE 事件。"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _stream_events(payload, cfg):
    """流式生成器：逐节点吐 step 事件；撞 interrupt 吐 interrupt；跑完吐 reply + done。

    流式的依据(探针实测)：stream_mode='updates' 正常时 emit {节点名: 更新}，
    中断时 emit {'__interrupt__': (Interrupt,)}。
    """
    app_ = get_orchestrator()
    interrupted = False
    for chunk in app_.stream(payload, cfg, stream_mode="updates"):
        for node, update in chunk.items():
            if node == "__interrupt__":
                v = update[0].value
                yield _sse({"type": "interrupt", "tool": v.get("tool"), "args": v.get("args")})
                interrupted = True
            else:
                label = _STEP_LABELS.get(node, node)
                if isinstance(update, dict) and update.get("route"):
                    label += f" → {update['route']}"
                yield _sse({"type": "step", "node": node, "label": label})
    if not interrupted:
        yield _sse(_final(app_.get_state(cfg).values))
    yield _sse({"type": "done"})


@app.post("/chat")
def chat(inp: ChatIn) -> dict:
    cfg = {"configurable": {"thread_id": inp.thread_id}}
    state = get_orchestrator().invoke({"messages": [HumanMessage(inp.message)]}, cfg)
    return _shape(state)


@app.post("/resume")
def resume(inp: ResumeIn) -> dict:
    cfg = {"configurable": {"thread_id": inp.thread_id}}
    state = get_orchestrator().invoke(Command(resume=inp.decision), cfg)
    return _shape(state)


@app.post("/chat/stream")
def chat_stream(inp: ChatIn) -> StreamingResponse:
    cfg = {"configurable": {"thread_id": inp.thread_id}}
    return StreamingResponse(
        _stream_events({"messages": [HumanMessage(inp.message)]}, cfg),
        media_type="text/event-stream",
    )


@app.post("/resume/stream")
def resume_stream(inp: ResumeIn) -> StreamingResponse:
    cfg = {"configurable": {"thread_id": inp.thread_id}}
    return StreamingResponse(
        _stream_events(Command(resume=inp.decision), cfg),
        media_type="text/event-stream",
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse("web/index.html")
