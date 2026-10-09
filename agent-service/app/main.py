import asyncio
import hmac
import json
import os
import time
from contextlib import suppress
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import StreamingResponse,JSONResponse
from .agent import Agent
from .providers import configured_provider
from .schemas import QueryRequest,Location,AgentFailure
from .state import Sessions
from .tools import ToolClient

app=FastAPI(title="QueueLens Agent",version="1.0.0")
sessions=Sessions()

@app.middleware("http")
async def authorize(request:Request,call_next):
    token=os.getenv("AGENT_API_TOKEN","")
    if token and request.url.path!="/health" and not hmac.compare_digest(request.headers.get("authorization","").encode('utf-8'),f"Bearer {token}".encode('utf-8')):
        return JSONResponse(status_code=401,content={"error":"Agent authorization required"})
    return await call_next(request)

@app.get("/health")
async def health():return {"status":"ok","planner_provider":os.getenv("PLANNER_PROVIDER","http_chat")}

def validate_request(body):
    if not body.query.strip():raise HTTPException(422,"Query cannot be blank")
    if body.reference_time is not None and os.getenv("EVAL_MODE")!="true":raise HTTPException(422,"Fixed reference times require isolated evaluation mode")

def failure(code,message,trace=None):
    return {"status":code,"answer":message,"entities":[],"statistics":[],"map_actions":[],"trace":(trace or [])+[{"stage":"failure","failure":code,"message":message}]}

async def execute(body,emit=None):
    agent=None
    try:
        state=sessions.read(body.session_id)
        location_at=time.monotonic() if body.location is not None else None
        if state and body.location is None and state["location"] and time.monotonic()-state["location_at"]<300:
            body=body.model_copy(update={"location":Location.model_validate(state["location"])})
            location_at=state["location_at"]
        agent=Agent(ToolClient(),configured_provider())
        result=await asyncio.wait_for(agent.run(body,state["entities"] if state else None,emit),timeout=30)
        if result["status"]=="ok" and result["entities"]:result["session_id"]=sessions.commit(body.session_id,state,result["entities"],body.location.model_dump() if body.location else None,location_at)
        elif body.session_id:result["session_id"]=body.session_id
        return result
    except asyncio.TimeoutError:return failure("timeout","请求超过 30 秒执行上限。",agent.trace if agent else None)
    except AgentFailure as error:return failure(error.code,error.message,agent.trace if agent else None)

@app.post("/query")
async def query(body:QueryRequest):
    validate_request(body);return await execute(body)

@app.post("/query/stream")
async def stream(body:QueryRequest):
    validate_request(body)
    async def events():
        queue=asyncio.Queue(maxsize=100)
        async def emit(stage,data):await queue.put((stage,data))
        async def worker():
            try:await queue.put(("done",await execute(body,emit)))
            except Exception:await queue.put(("done",failure("tool_execution_failure","Agent 执行失败。")))
        task=asyncio.create_task(worker())
        try:
            while True:
                try:stage,data=await asyncio.wait_for(queue.get(),timeout=5)
                except asyncio.TimeoutError:yield ": heartbeat\n\n";continue
                yield f"event: {stage}\ndata: {json.dumps(data,ensure_ascii=False,allow_nan=False)}\n\n"
                if stage=="done":break
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):await task
    return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
