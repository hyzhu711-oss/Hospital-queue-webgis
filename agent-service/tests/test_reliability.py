import httpx
import pytest
from app.agent import Agent
from app.providers import RuleProvider
from app.tools import ToolClient
from app.schemas import AgentFailure,PlanSpec
from app.verifier import verify
import copy
from test_agent import request

@pytest.mark.asyncio
async def test_submillisecond_clock_shares_node_boundaries(node_service):
    body=request('compare "Hospital A" and "Hospital B"').model_copy(update={'reference_time':'2026-05-30T00:00:00.123456Z'})
    result=await Agent(ToolClient(node_service),RuleProvider()).run(body)
    assert result['status']=='ok',result
    assert result['trace'][-1]['arguments']['end_time'].endswith('.123000+00:00')

@pytest.mark.asyncio
async def test_invalid_clock_returns_traced_error(node_service):
    body=request('nearest hospital').model_copy(update={'reference_time':'2026-02-30T00:00:00Z'})
    result=await Agent(ToolClient(node_service),RuleProvider()).run(body)
    assert result['status']=='wrong_temporal_window'
    assert not result['entities'] and not result['map_actions']
    assert result['trace'][-1]['failure']=='wrong_temporal_window'

@pytest.mark.asyncio
async def test_stale_location_is_not_extended_by_followup(node_service,monkeypatch):
    from app.main import app,sessions
    sessions.items.clear()
    monkeypatch.setenv('GIS_API_URL',node_service)
    monkeypatch.setenv('PLANNER_PROVIDER','rules')
    monkeypatch.setenv('EVAL_MODE','true')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        first=(await client.post('/query',json=request('recommend three hospitals within 2km').model_dump())).json()
        sid=first['session_id']
        sessions.items[sid]['location_at']-=301
        body=request('nearest hospital',False).model_dump();body['session_id']=sid
        stale=(await client.post('/query',json=body)).json()
        assert stale['status']=='missing_location'
        body['query']='第二个过去24小时怎么样？'
        follow=(await client.post('/query',json=body)).json()
        assert follow['status']=='ok'
        assert follow['entities'][0]['hospital_id']==first['entities'][1]['hospital_id']
        assert sessions.items[sid]['location'] is None

@pytest.mark.asyncio
async def test_truncated_radius_cannot_claim_all_results(node_service):
    class TruncatedClient(ToolClient):
        async def call(self,name,args):
            result=await super().call(name,args)
            if name=='search_nearby_hospitals':result['data']['complete']=False
            return result
    result=await Agent(TruncatedClient(node_service),RuleProvider()).run(request('hospitals within 2km'))
    assert result['status']=='incomplete_candidates'
    assert not result['entities']

@pytest.mark.asyncio
async def test_verifier_rejects_inconsistent_detail_id(node_service):
    result=await Agent(ToolClient(node_service),RuleProvider()).run(request('"Hospital A" queue status'))
    trace=copy.deepcopy(result['trace']);trace[-1]['result']['data']['hospital_id']=2
    with pytest.raises(AgentFailure,match='Detail hospital ID mismatch'):
        verify(PlanSpec.model_validate(result['plan']),[trace[-1]['result']['data']],[],trace,{})

@pytest.mark.asyncio
async def test_verifier_checks_aggregate_observation_window(node_service):
    result=await Agent(ToolClient(node_service),RuleProvider()).run(request('过去24小时 "Hospital A"'))
    trace=copy.deepcopy(result['trace']);trace[-1]['result']['data']['first_report_at']='2020-01-01T00:00:00Z'
    args=trace[-1]['arguments'];window={key:args[key] for key in ('start_time','end_time')}
    with pytest.raises(AgentFailure,match='Aggregate timestamp outside window'):
        verify(PlanSpec.model_validate(result['plan']),result['entities'],result['statistics'],trace,window)

@pytest.mark.asyncio
async def test_verifier_rejects_missing_comparison_statistics(node_service):
    result=await Agent(ToolClient(node_service),RuleProvider()).run(request('compare "Hospital A" and "Hospital B"'))
    trace=copy.deepcopy(result['trace']);trace[-1]['result']['data']['statistics'].pop()
    args=trace[-1]['arguments'];window={key:args[key] for key in ('start_time','end_time')}
    with pytest.raises(AgentFailure,match='Incomplete statistics coverage'):
        verify(PlanSpec.model_validate(result['plan']),result['entities'],result['statistics'],trace,window)

@pytest.mark.asyncio
async def test_agent_auth_rejects_nonascii_and_accepts_server_token(node_service,monkeypatch):
    from app.main import app
    monkeypatch.setenv('AGENT_API_TOKEN','test-token')
    monkeypatch.setenv('GIS_API_URL',node_service)
    monkeypatch.setenv('PLANNER_PROVIDER','rules')
    monkeypatch.setenv('EVAL_MODE','true')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        assert (await client.get('/health')).status_code==200
        assert (await client.post('/query',json={'query':'nearest hospital'},headers={'Authorization':b'Bearer \xff'})).status_code==401
        response=await client.post('/query',json=request('nearest hospital').model_dump(),headers={'Authorization':'Bearer test-token'})
        assert response.status_code==200 and response.json()['status']=='ok'
