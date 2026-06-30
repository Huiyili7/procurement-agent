"""FastAPI 服务：把 orchestrator 包成 HTTP 接口，供 Web 前端调用。

难点是把"多轮 + HITL(interrupt/resume)"映射到无状态的 HTTP 上：
- 多轮：客户端带一个 thread_id，状态由 checkpointer 按 thread_id 持久化(HTTP 无状态，记忆在服务端)。
- HITL：/chat 若停在 interrupt，就返回 type=interrupt + 待确认动作；前端弹确认框，
  用户答复后调 /resume 把 Command(resume=...) 喂回同一 thread_id 续跑。
两个端点形状一致(_shape)，前端统一处理。
"""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel

from agent.orchestrator import get_orchestrator

app = FastAPI(title="采购受理 Agent")


class ChatIn(BaseModel):
    thread_id: str
    message: str


class ResumeIn(BaseModel):
    thread_id: str
    decision: str


def _shape(state: dict) -> dict:
    """把图的最终 state 压成前端要的 JSON(同时覆盖 interrupt / 普通回复两种)。"""
    if "__interrupt__" in state:
        p = state["__interrupt__"][0].value
        return {"type": "interrupt", "tool": p.get("tool"), "args": p.get("args")}

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
    return out


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse("web/index.html")
