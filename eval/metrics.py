"""Deterministic, closed-contract scoring. No LLM judge or agent verifier imports."""
import math
import re
from collections import defaultdict
from datetime import datetime

def same(actual,expected):
    if isinstance(expected,dict):return isinstance(actual,dict) and actual.keys()==expected.keys() and all(same(actual[k],v) for k,v in expected.items())
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(same(a,b) for a,b in zip(actual,expected))
    if isinstance(expected,(float,int)) and not isinstance(expected,bool):return isinstance(actual,(float,int)) and not isinstance(actual,bool) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-6)
    if isinstance(expected,str) and re.match(r'^\d{4}-\d\d-\d\dT',expected):
        try:return datetime.fromisoformat(actual.replace('Z','+00:00'))==datetime.fromisoformat(expected.replace('Z','+00:00'))
        except (ValueError,AttributeError):return False
    return actual==expected

def facts_grounded(result,oracle,origin,window):
    if not result.get('entities'):
        return result.get('status')!='ok' and not result.get('statistics') and not re.search(r'医院 ID|直线距离|平均排队等级|平均等待|平均清洁度|\bdistance\b',result.get('answer',''),re.I)
    distances=oracle.distances(origin) if origin else {}
    for h in result.get('entities',[]):
        hid=h.get('hospital_id')
        if hid not in oracle.hospitals:return False
        expected=oracle.entity(hid,distances.get(hid) if h.get('distance_m') is not None else None)
        if any(k not in expected or not same(v,expected[k]) for k,v in h.items()):return False
    # Closed answer contract: independently reconstruct all factual lines; extra prose fails.
    entities=result.get('entities',[])
    if not entities:return not result.get('statistics')
    lines=[]
    stats={s['hospital_id']:s for s in result.get('statistics',[])}
    for index,h in enumerate(entities,1):
        line=f"{index}. {h['name']}（医院 ID {h['hospital_id']}）"
        if h.get('distance_m') is not None:line+=f"，直线距离 {h['distance_m']:.1f} 米"
        s=stats.get(h['hospital_id'])
        if s:
            line+=f"；窗口内 {s['report_count']} 条报告"
            if s.get('average_queue_severity') is not None:line+=f"，平均排队等级 {s['average_queue_severity']:.2f}/5（不是分钟）"
            if s.get('average_wait_minutes') is not None:line+=f"，报告的平均等待 {s['average_wait_minutes']:.2f} 分钟"
            if s.get('average_cleanliness') is not None:line+=f"，平均清洁度 {s['average_cleanliness']:.2f}/5（{s['cleanliness_count']} 条评分）"
            else:line+='，没有数值清洁度评分'
            if s.get('first_queue_severity') is not None and s.get('last_queue_severity') is not None:line+=f"，首末排队等级 {s['first_queue_severity']} → {s['last_queue_severity']}"
        else:line+=f"；最新报告状态：{h.get('queue_description')}，报告时间 {h.get('latest_report_at') or '无报告'}"
        lines.append(line)
    if stats:lines.append(f"时间窗口 [{window['start_time']}, {window['end_time']})。")
    return result.get('answer')=='\n'.join(lines)

def score(case,result,oracle,tool_metrics=True):
    actual_calls=[{'tool':s['tool'],'arguments':s['arguments']} for s in result.get('trace',[]) if 'tool' in s]
    ids=[h.get('hospital_id') for h in result.get('entities',[])]
    stats=sorted(result.get('statistics',[]),key=lambda s:s.get('hospital_id',-1))
    expected_stats=sorted(case['expected_statistics'],key=lambda s:s['hospital_id'])
    status=result.get('status')==case['expected_status']
    entities=ids==case['expected_hospital_ids']
    metric={
        'tool_selection_accuracy':any([c['tool'] for c in actual_calls]==[c['tool'] for c in accepted] for accepted in case.get('accepted_calls',[case['expected_calls']])) if tool_metrics else None,
        'tool_argument_accuracy':any(same(actual_calls,accepted) for accepted in case.get('accepted_calls',[case['expected_calls']])) if tool_metrics else None,
        'execution_success_rate':status,
        'constraint_satisfaction_rate':status and entities and same(stats,expected_stats),
        'final_entity_accuracy':status and entities,
        'answer_groundedness':facts_grounded(result,oracle,case.get('location'),case['expected_time_window']),
        'map_action_accuracy':same(result.get('map_actions',[]),case['expected_map_actions']),
    }
    # Statistics must independently agree with raw observations, not merely with tool evidence.
    metric['answer_groundedness']=metric['answer_groundedness'] and all(any(same(s,expected) for expected in expected_stats) for s in stats)
    metric['end_to_end_success_rate']=all(v for v in metric.values() if v is not None)
    return metric

def aggregate(rows):
    metrics=defaultdict(list)
    for row in rows:
        for name,value in row['metrics'].items():
            if value is not None:metrics[name].append(int(value))
    summary={name:{'passed':sum(values),'total':len(values),'rate':sum(values)/len(values)} for name,values in metrics.items()}
    latency=sorted(row['latency_ms'] for row in rows)
    summary['latency_ms']={'mean':sum(latency)/len(latency),'p50':latency[int((len(latency)-1)*.5)],'p95':latency[int((len(latency)-1)*.95)]}
    summary['tool_call_count']={'total':sum(row.get('total_tool_call_count',row['tool_call_count']) for row in rows),'mean':sum(row.get('total_tool_call_count',row['tool_call_count']) for row in rows)/len(rows)}
    tokens=[row.get('usage') for row in rows]
    summary['token_usage']=None if any(t is None for t in tokens) else {'prompt_tokens':sum(t.get('prompt_tokens',0) for t in tokens),'completion_tokens':sum(t.get('completion_tokens',0) for t in tokens)}
    summary['monetary_cost']=None  # Price/model billing is not inferred.
    return summary
