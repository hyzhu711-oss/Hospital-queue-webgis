import os
import sys
from pathlib import Path
import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[2]
WINDOW={"start_time":"2026-05-29T00:00:00Z","end_time":"2026-05-30T00:00:00Z"}

@pytest.mark.asyncio
async def test_real_mcp_protocol_and_shared_tools(node_service):
    parameters=StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp'/'server.py')],
        env={**os.environ,"GIS_API_URL":node_service,"GIS_TOOLS_TOKEN":""})
    async with httpx.AsyncClient(base_url=node_service) as client:
        catalog=(await client.get('/api/tools/catalog')).json()
        async with stdio_client(parameters) as (read,write):
            async with ClientSession(read,write) as session:
                initialized=await session.initialize()
                assert initialized.serverInfo.name=='QueueLens Spatial Tools'
                listed=await session.list_tools()
                assert len(listed.tools)==8
                for tool in listed.tools:
                    original=next(t for t in catalog['tools'] if t['name']==tool.name)
                    assert tool.inputSchema==original['input_schema']
                    assert tool.outputSchema['properties']['data']==original['output_schema']
                    assert tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
                calls={
                    'resolve_hospitals':{'query':'Hospital A'},
                    'search_nearby_hospitals':{'latitude':51.5,'longitude':-0.13,'radius_m':2000},
                    'get_hospital_details':{'hospital_id':1},
                    'get_hospital_reports':{'hospital_id':1,**WINDOW},
                    'get_queue_statistics':{'hospital_id':1,**WINDOW},
                    'get_cleanliness_statistics':{'hospital_id':1,**WINDOW},
                    'compare_hospitals':{'hospital_ids':[1,2],**WINDOW},
                    'rank_hospitals':{'candidate_ids':[1,2,3,4],'latitude':51.5,'longitude':-0.13,
                        'distance_weight':0.3,'queue_weight':0.4,'cleanliness_weight':0.3,**WINDOW}
                }
                for name,args in calls.items():
                    result=await session.call_tool(name,args)
                    direct=(await client.post('/api/tools/'+name,json=args)).json()
                    assert not result.isError, result
                    assert result.structuredContent['data']==direct['data']
                    assert result.structuredContent['arguments']==args
                    assert result.structuredContent['evidence']['data_source']=='memory'
                invalid=await session.call_tool('search_nearby_hospitals',{'latitude':91,'longitude':0})
                assert invalid.isError
                unknown=await session.call_tool('execute_sql',{'sql':'DROP TABLE reports'})
                assert unknown.isError
