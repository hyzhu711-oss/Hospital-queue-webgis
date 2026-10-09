"""Run the agent or baselines against real HTTP tools and an independent oracle."""
import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from pydantic import ValidationError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent-service'))
from app.agent import Agent
from app.providers import RuleProvider,HttpChatProvider
from app.schemas import QueryRequest,AgentFailure
from app.tools import ToolClient
from oracle import Oracle,materialize
from metrics import aggregate,score
from baselines.runners import LLMOnly,SingleStep,TextToSQL,failure
from contracts import validate_result

async def evaluate(options):
    base=ROOT/'eval';definitions=json.loads((base/'benchmark/definitions.json').read_text(encoding='utf-8'))
    fixture=json.loads((base/'benchmark/fixture.json').read_text(encoding='utf-8'))
    url=os.getenv('EVAL_DATABASE_URL') if options.store=='postgres' else None
    if options.store=='postgres' and not url:raise ValueError('EVAL_DATABASE_URL is required')
    oracle=Oracle.database(url) if url else Oracle(fixture)
    cases=materialize(oracle,definitions)
    if options.write_ground_truth:(base/'benchmark/cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    systems=options.system or ['proposed_rules','single_step_rules','proposed_llm','llm_only','text_to_sql','single_step']
    metadata={'fixture_sha256':hashlib.sha256((base/'benchmark/fixture.json').read_bytes()).hexdigest(),'oracle':oracle.source,
        'oracle_snapshot_sha256':hashlib.sha256(json.dumps(oracle.fixture,sort_keys=True).encode()).hexdigest(),'database_version':getattr(oracle,'database_version',None),
        'case_count':len(cases),'category_counts':dict(Counter(c['category'] for c in cases)),'generated_at':datetime.now(timezone.utc).isoformat(),
        'planner_model':os.getenv('LLM_MODEL') or None,'evaluation_scope':'Agent core + real Express HTTP tools; browser/SSE/session API covered separately',
        'llm_semantic_evaluation':False,'limits':{'per_request_timeout_seconds':30,'follow_up_setup_is_separate_request':True,'max_tool_calls':24,'max_planning_steps':12}}
    report={'metadata':metadata,'systems':{}}
    env={**os.environ,'EVAL_STORE':options.store,'GIS_TOOLS_TOKEN':''}
    process=subprocess.Popen([shutil.which('node'),str(base/'start-api.js')],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        api=process.stdout.readline().strip()
        if not api.startswith('http://127.0.0.1:'):raise RuntimeError('Evaluation API did not start')
        for system in systems:
            llm=system not in ('proposed_rules','single_step_rules')
            if llm and options.offline:
                report['systems'][system]={'status':'not_run','reason':'User-selected offline evaluation; no model request sent'};continue
            if llm and not all(os.getenv(k) for k in ('LLM_BASE_URL','LLM_API_KEY','LLM_MODEL')):
                report['systems'][system]={'status':'not_run','reason':'LLM provider credentials/model are not configured'};continue
            if system=='text_to_sql' and not url:
                report['systems'][system]={'status':'not_run','reason':'Requires isolated read-only PostGIS evaluation database'};continue
            rows=[]
            for case in cases:
                tools=ToolClient(api,token='');provider=RuleProvider() if system=='proposed_rules' else HttpChatProvider()
                runner=Agent(tools,provider) if system.startswith('proposed_') else LLMOnly() if system=='llm_only' else TextToSQL(url) if system=='text_to_sql' else SingleStep(rules=system=='single_step_rules')
                prior=None;setup_result=None
                started=time.perf_counter()
                try:
                    request=QueryRequest.model_validate({k:case[k] for k in ('query','location','reference_time')})
                    if case.get('setup_query'):
                        setup_request=request.model_copy(update={'query':case['setup_query']})
                        setup_result=await asyncio.wait_for(runner.run(setup_request,None) if isinstance(runner,Agent) else runner.run(setup_request,None,tools),timeout=30)
                        if isinstance(runner,Agent):setup_result['usage']=getattr(provider,'last_usage',None)
                        prior=setup_result.get('entities',[])
                    result=await asyncio.wait_for(runner.run(request,prior) if isinstance(runner,Agent) else runner.run(request,prior,tools),timeout=30)
                    if isinstance(runner,Agent):result['usage']=getattr(provider,'last_usage',None)
                    validate_result(result)
                except ValidationError:result=failure('invalid_input','输入不符合 schema。')
                except (ValueError,KeyError,TypeError):result=failure('malformed_output','输出结构不符合评测契约。')
                except AgentFailure as error:result=failure(error.code,error.message)
                except asyncio.TimeoutError:result=failure('timeout','评测请求超时。')
                except Exception as error:result=failure('baseline_execution_failure',type(error).__name__)
                latency=(time.perf_counter()-started)*1000
                metric=score(case,result,oracle,tool_metrics=system not in ('llm_only','text_to_sql'))
                if setup_result is not None:
                    expected_setup=oracle.expected({**case,'expected_constraints':case['setup_constraints']})
                    if setup_result.get('status')!='ok' or [h.get('hospital_id') for h in setup_result.get('entities',[])]!=expected_setup['expected_hospital_ids']:metric['end_to_end_success_rate']=False
                count=sum('tool' in step for step in result.get('trace',[]))
                setup_count=sum('tool' in step for step in (setup_result or {}).get('trace',[]))
                usage=result.get('usage',{'prompt_tokens':0,'completion_tokens':0} if not llm else None)
                if setup_result:
                    setup_usage=setup_result.get('usage')
                    usage={key:usage.get(key,0)+setup_usage.get(key,0) for key in ('prompt_tokens','completion_tokens')} if usage is not None and setup_usage is not None else None
                rows.append({'id':case['id'],'category':case['category'],'metrics':metric,'latency_ms':latency,'tool_call_count':count,
                    'setup_tool_call_count':setup_count,'total_tool_call_count':count+setup_count,'usage':usage,'result':result,
                    'setup_status':setup_result.get('status') if setup_result else None})
            report['systems'][system]={'status':'completed','semantic_mode':'LLM' if llm else 'explicit rule template smoke test',
                'metrics':aggregate(rows),'by_category':{category:aggregate([r for r in rows if r['category']==category]) for category in metadata['category_counts']},'cases':rows}
            if llm:metadata['llm_semantic_evaluation']=True
            print(system+': '+str(report['systems'][system]['metrics']['end_to_end_success_rate']),flush=True)
    finally:
        process.terminate();process.communicate(timeout=10)
    target=Path(options.output or base/'reports'/'latest.json');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('Report: '+str(target),flush=True)
    failed=any(v['status']=='completed' and v['metrics']['end_to_end_success_rate']['rate']<1 for name,v in report['systems'].items() if name=='proposed_rules')
    if options.require_smoke_pass and failed:raise SystemExit(1)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--store',choices=['memory','postgres'],default='memory')
    parser.add_argument('--system',action='append',choices=['proposed_rules','proposed_llm','llm_only','single_step','single_step_rules','text_to_sql'])
    parser.add_argument('--output');parser.add_argument('--write-ground-truth',action='store_true');parser.add_argument('--require-smoke-pass',action='store_true')
    parser.add_argument('--offline',action='store_true',help='Never call a model; record model systems as not_run')
    asyncio.run(evaluate(parser.parse_args()))
