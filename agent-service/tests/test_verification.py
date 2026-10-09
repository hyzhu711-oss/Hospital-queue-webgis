import copy
import asyncio
from uuid import uuid4
import httpx
import pytest
from app.agent import Agent
from app.providers import RuleProvider
from app.schemas import AgentFailure,PlanSpec
from app.verifier import verify
from app.tools import ToolClient
from app.state import Sessions
from test_agent import request

@pytest.mark.asyncio
async def test_verifier_rejects_fact_mutation(node_service):
    result=await Agent(ToolClient(node_service),RuleProvider()).run(request("recommend three hospitals within 2 km"))
    assert result["status"]=="ok",result
    plan=PlanSpec.model_validate(result["plan"])
    entities=copy.deepcopy(result["entities"]);entities[0]["distance_m"]+=10
    args=result["trace"][-1]["arguments"];window={k:args[k] for k in ("start_time","end_time")}
    with pytest.raises(AgentFailure,match="Final entity"):verify(plan,entities,result["statistics"],result["trace"],window)
    corrupted=copy.deepcopy(result["trace"]);corrupted[-1]["result"]["data"]["ranking"][0]["score"]+=0.1
    with pytest.raises(AgentFailure,match="score mismatch"):verify(plan,result["entities"],result["statistics"],corrupted,window)

@pytest.mark.asyncio
async def test_followup_reuses_verified_order_and_rejects_unknown(node_service):
    agent=Agent(ToolClient(node_service),RuleProvider())
    first=await agent.run(request("recommend three hospitals within 2km"))
    second=await agent.run(request("第二个过去24小时怎么样？",False),first["entities"])
    assert [h["hospital_id"] for h in second["entities"]]==[first["entities"][1]["hospital_id"]]
    assert (await agent.run(request("第二个过去24小时怎么样？",False)))["status"]=="reference_resolution_failure"

@pytest.mark.asyncio
async def test_limits_and_timeout(node_service):
    result=await Agent(ToolClient(node_service),RuleProvider(),max_calls=1).run(request('"Hospital A" queue status'))
    assert result["status"]=="agent_loop"
    class SlowClient(ToolClient):
        async def call(self,*args):await asyncio.sleep(1)
    result=await Agent(SlowClient(node_service),RuleProvider(),tool_timeout=0.01).run(request("nearest hospital"))
    assert result["status"]=="tool_timeout" and result["trace"][0]["status"]=="failed"

def test_session_expiration_and_version_conflict():
    sessions=Sessions(ttl=30);sid=sessions.commit(None,None,[{"hospital_id":1}],None);state=sessions.read(sid)
    sessions.commit(sid,state,[{"hospital_id":2}],None)
    with pytest.raises(AgentFailure):sessions.commit(sid,state,[],None)
    sessions.items[sid]["updated"]-=31
    with pytest.raises(AgentFailure):sessions.read(sid)

@pytest.mark.asyncio
async def test_api_sessions_stream_and_invalid_input(node_service,monkeypatch):
    from app.main import app,sessions
    sessions.items.clear()
    monkeypatch.setenv("GIS_API_URL",node_service);monkeypatch.setenv("PLANNER_PROVIDER","rules");monkeypatch.setenv("EVAL_MODE","true")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        body=request("recommend three hospitals within 2km").model_dump()
        result=(await client.post("/query",json=body)).json();assert result["status"]=="ok",result
        body=request("第二个过去24小时怎么样？",False).model_dump();body["session_id"]=result["session_id"]
        follow=(await client.post("/query",json=body)).json();assert follow["entities"][0]["hospital_id"]==result["entities"][1]["hospital_id"]
        streamed=await client.post("/query/stream",json=request("nearest hospital").model_dump())
        assert "event: planning" in streamed.text and "event: verifying" in streamed.text and "event: done" in streamed.text
        assert (await client.post("/query",json={"query":"x","location":{"latitude":True,"longitude":0}})).status_code==422
        stale=(await client.post("/query",json={"query":"second hospital","session_id":str(uuid4())})).json()
        assert stale["status"]=="stale_session"
