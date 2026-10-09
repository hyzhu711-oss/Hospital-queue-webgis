import asyncio
import json
import os
from datetime import timedelta
import httpx
from app.actions import map_actions
from app.agent import render_answer,parse_clock
from app.providers import RuleProvider
from app.schemas import PlanSpec
from app.llm import completion
from app.semantics import POLICY
from .sql_guard import execute_sql
from .sql_projection import project

def failure(code,message):return {'status':code,'answer':message,'entities':[],'statistics':[],'map_actions':[],'trace':[]}

async def chat(prompt,payload):
    content, usage = await completion(POLICY + prompt, payload)
    return json.loads(content), usage

class LLMOnly:
    async def run(self,request,prior,tools):
        result,usage=await chat('Answer a hospital GIS question WITHOUT tools or database access. Return JSON with status,answer,entities,statistics,map_actions. '
            'entities,statistics,map_actions MUST be JSON arrays even when empty, never objects. Example of insufficient data: {"status":"no_result","answer":"没有数据库观测可供回答。","entities":[],"statistics":[],"map_actions":[]}. '
            'entities are hospital_id,name,latitude,longitude,distance_m,queue_description,cleanliness_note,latest_report_id,latest_report_at,cleanliness_score,queue_wait_minutes. '
            'Do not invent facts. Use no_result or ambiguous if unknown. For scoring, factual answer lines must use: 1. NAME（医院 ID ID），直线距离 D.D 米；最新报告状态：STATE，报告时间 TIME. '
            'Provide structured map actions using fit_bounds,highlight,filter,rank,compare,open_popup,fly_to.',
            {'query':request.query,'location':request.location.model_dump() if request.location else None,'reference_time':request.reference_time,'previous_entities':prior or []})
        if not isinstance(result,dict) or not isinstance(result.get('entities'),list):raise ValueError('Malformed baseline output')
        result['trace']=[];result['usage']=usage;return result

class SingleStep:
    def __init__(self,rules=False):self.rules=rules
    async def run(self,request,prior,tools):
        catalog=await tools.load_catalog();usage=None
        if self.rules:
            plan=await RuleProvider().plan(request.query,{},catalog);usage=RuleProvider.last_usage
            if plan.intent in ('ambiguous','unsupported'):return {**failure(plan.intent,'无法确定单步工具。'),'usage':usage}
            if plan.referent:
                if not prior or plan.referent>len(prior):return failure('reference_resolution_failure','无可用引用。')
                name='get_hospital_details';args={'hospital_id':prior[plan.referent-1]['hospital_id']}
            elif plan.names:name='resolve_hospitals';args={'query':plan.names[0]}
            elif request.location:
                name='search_nearby_hospitals';args=request.location.model_dump()
                if plan.radius_m is not None:args['radius_m']=plan.radius_m
                if plan.intent=='nearest':args['limit']=1
            else:return failure('missing_location','需要位置。')
        else:
            choice,usage=await chat('Select exactly ONE read-only GIS tool. Return JSON {tool,arguments,intent,hours}; no execution plan, no verification, no factual answer. '
                'intent is one of lookup,nearest,radius,attribute,temporal,ranking,comparison,multi_step,ambiguous,unsupported. hours is a NUMBER of preceding hours, default 24; it is not hour-of-day or an array. '
                'If unclear return {status:"ambiguous"}. Tool inputs must match catalog. Do not invent IDs; use resolve_hospitals for names.',
                {'query':request.query,'location':request.location.model_dump() if request.location else None,'reference_time':request.reference_time,'previous_entities':prior or [],'catalog':catalog})
            if choice.get('status'):return {**failure(choice['status'],'单步工具未执行。'),'usage':usage}
            name=choice['tool'];args=choice['arguments'];plan=PlanSpec(intent=choice['intent'],hours=choice.get('hours',24.))
        result=await tools.call(name,args);data=result['data']
        entities=[data] if name=='get_hospital_details' else data.get('hospitals',[])
        stats=data.get('statistics',[])
        if name=='resolve_hospitals' and len(entities)!=1:return {**failure('ambiguous' if entities else 'no_result','名称未唯一匹配。'),'trace':[{'tool':name,'arguments':args,'status':'ok','result':result}],'usage':usage}
        if name in ('get_queue_statistics','get_cleanliness_statistics'):
            stats=[data];entities=[h for h in prior or [] if h['hospital_id']==data['hospital_id']]
        if self.rules and plan.intent in ('ranking','multi_step','attribute'):entities=entities[:1 if plan.intent=='attribute' else plan.limit]
        window={'start_time':args['start_time'],'end_time':args['end_time']} if args.get('start_time') else None
        return {'status':'ok' if entities else 'no_result','answer':render_answer(entities,stats,window),'entities':entities,'statistics':stats,
            'map_actions':map_actions(plan,entities),'trace':[{'tool':name,'arguments':args,'status':'ok','result':result}],'usage':usage}

class TextToSQL:
    def __init__(self,url):self.url=url
    async def run(self,request,prior,tools):
        choice,usage=await chat('Generate ONE PostgreSQL SELECT that selects and orders hospital_id for this question. Return JSON {sql,intent,hours}. '
            'intent is one of lookup,nearest,radius,attribute,temporal,ranking,comparison,multi_step,ambiguous,unsupported. hours is a NUMBER of preceding hours, default 24, not hour-of-day. '
            'Latest-status lookup uses the latest report independent of the window; nearest and radius use distance only without report filters. Relative statistics windows end at reference_time and begin reference_time minus hours. Names are resolved by exact match first, then unique substring; never require user-supplied numeric IDs. '
            'No CTE, writes, locks, recursive query, system tables or arbitrary functions. Only hospitals(id,name,location geometry4326),reports(id,hospital_id,queue_length_id,cleanliness_score,queue_wait_minutes,created_at),queue_lengths(id,sort_order). '
            'Use ST_DWithin/ST_Distance on geography, parameter values in supplied context, and [start,end) time windows. sort_order 0=unknown; 1..5=queue severity, not minutes. '
            'Weighted ranking minimizes distance_weight*least(distance/radius,1)+queue_weight*(avg_severity-1)/4+cleanliness_weight*(5-avg_cleanliness)/4 with default equal weights, radius default5000. '
            'Filter missing weighted metrics. Tie-break hospital_id. For best cleanliness use weights 0,0,1; for shorter queue use 0,1,0. If ambiguous return {status:"ambiguous"}.',
            {'query':request.query,'location':request.location.model_dump() if request.location else None,'reference_time':request.reference_time,'previous_entities':prior or []})
        if choice.get('status'):return {**failure(choice['status'],'SQL 未执行。'),'usage':usage}
        plan=PlanSpec(intent=choice['intent'],hours=choice.get('hours',24.))
        rows=await asyncio.to_thread(execute_sql,self.url,choice['sql'])
        ids=[row['hospital_id'] for row in rows]
        end=parse_clock(request.reference_time);window={'start_time':(end-timedelta(hours=plan.hours)).isoformat(),'end_time':end.isoformat()}
        spatial=plan.intent in ('nearest','radius','ranking','attribute','multi_step')
        entities,stats=await asyncio.to_thread(project,self.url,ids,request.location.model_dump() if spatial and request.location else None,
            window['start_time'],window['end_time'],plan.intent in ('temporal','comparison','ranking','attribute','multi_step'))
        return {'status':'ok' if ids else 'no_result','answer':render_answer(entities,stats,window if stats else None),'entities':entities,'statistics':stats,
            'map_actions':map_actions(plan,entities),'trace':[],'sql':choice['sql'],'sql_query_count':3 if stats else 2,'usage':usage}
