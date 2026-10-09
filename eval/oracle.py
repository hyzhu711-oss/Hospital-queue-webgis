"""Independent executable oracle over raw observations and PostGIS distances.

No imports from agent, Node domain, tool service, verifier or map adapters.
"""
import json
import math
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from psycopg.rows import dict_row

BASE=Path(__file__).resolve().parent
def instant(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
def iso(value):return instant(value).isoformat(timespec='milliseconds').replace('+00:00','Z')
def mean(values):return sum(values)/len(values) if values else None
def isolated_url(url):
    if urlparse(url).path!='/queuelens_eval':raise ValueError('Evaluation requires isolated database queuelens_eval')
    return url

class Oracle:
    def __init__(self,fixture,url=None):
        self.fixture=fixture;self.url=isolated_url(url) if url else None
        self.hospitals={h['id']:h for h in fixture['hospitals']}
        self.queues={q['id']:q for q in fixture['queueLengths']}
        self.reports=fixture['reports'];self.cache={}
        self.source='PostGIS WGS84 spheroid + independent raw-record Python aggregation' if url else 'Haversine sphere + independent raw-record Python aggregation'

    @classmethod
    def database(cls,url):
        with psycopg.connect(isolated_url(url),row_factory=dict_row,options='-c search_path=public,extensions -c default_transaction_read_only=on') as db:
            hospitals=db.execute('SELECT id,name,last_inspected,ST_Y(location) AS latitude,ST_X(location) AS longitude,user_id FROM hospitals ORDER BY id').fetchall()
            queues=db.execute('SELECT id,description,colour,sort_order FROM queue_lengths ORDER BY id').fetchall()
            reports=db.execute('SELECT id,hospital_id,user_id,queue_length_id,cleanliness,cleanliness_score,queue_wait_minutes,created_at FROM reports ORDER BY id').fetchall()
            version=db.execute("SELECT current_setting('server_version') AS postgres,postgis_lib_version() AS postgis").fetchone()
            fixture={'hospitals':[{'id':r['id'],'name':r['name'],'latitude':r['latitude'],'longitude':r['longitude']} for r in hospitals],
                'queueLengths':[{'id':r['id'],'description':r['description'],'sortOrder':r['sort_order']} for r in queues],
                'reports':[{'id':r['id'],'hospitalId':r['hospital_id'],'queueLengthId':r['queue_length_id'],
                    'cleanliness':r['cleanliness'],'cleanlinessScore':r['cleanliness_score'],'queueWaitMinutes':r['queue_wait_minutes'],
                    'createdAt':r['created_at'].isoformat()} for r in reports]}
        result=cls(fixture,url);result.database_version=version;return result

    def distances(self,origin):
        key=(origin['latitude'],origin['longitude'])
        if key in self.cache:return self.cache[key]
        if self.url:
            with psycopg.connect(self.url,options='-c search_path=public,extensions -c default_transaction_read_only=on') as db:
                rows=db.execute('SELECT id,ST_Distance(location::geography,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) FROM hospitals ORDER BY id',(origin['longitude'],origin['latitude'])).fetchall()
            result=dict(rows)
        else:
            lat,lon=map(math.radians,key);result={}
            for hid,h in self.hospitals.items():
                y,x=math.radians(h['latitude']),math.radians(h['longitude'])
                # Compute angular deltas from source degrees, avoiding cancellation of rounded radians.
                dy=math.radians(h['latitude']-key[0]);dx=math.radians(h['longitude']-key[1])
                a=math.sin(dy/2)**2+math.cos(lat)*math.cos(y)*math.sin(dx/2)**2
                result[hid]=6371000*2*math.atan2(math.sqrt(a),math.sqrt(1-a))
        self.cache[key]=result;return result

    def entity(self,hid,distance=None):
        h=self.hospitals[hid]
        observations=sorted((r for r in self.reports if r['hospitalId']==hid),key=lambda r:(instant(r['createdAt']),r['id']))
        r=observations[-1] if observations else None
        return {'hospital_id':hid,'name':h['name'],'latitude':h['latitude'],'longitude':h['longitude'],'distance_m':distance,
            'queue_description':self.queues[r['queueLengthId']]['description'] if r else 'Unknown',
            'cleanliness_note':r['cleanliness'] if r else 'No report yet','latest_report_id':r['id'] if r else None,
            'latest_report_at':iso(r['createdAt']) if r else None,'cleanliness_score':r.get('cleanlinessScore') if r else None,
            'queue_wait_minutes':r.get('queueWaitMinutes') if r else None}

    def statistics(self,hid,start,end):
        observations=sorted((r for r in self.reports if r['hospitalId']==hid and start<=instant(r['createdAt'])<end),key=lambda r:(instant(r['createdAt']),r['id']))
        severity=[self.queues[r['queueLengthId']]['sortOrder'] for r in observations]
        queues=[s for s in severity if s>0]
        waits=[r['queueWaitMinutes'] for r in observations if r.get('queueWaitMinutes') is not None]
        clean=[r['cleanlinessScore'] for r in observations if r.get('cleanlinessScore') is not None]
        return {'hospital_id':hid,'report_count':len(observations),'known_queue_count':len(queues),'average_queue_severity':mean(queues),
            'observed_wait_count':len(waits),'average_wait_minutes':mean(waits),'cleanliness_count':len(clean),'average_cleanliness':mean(clean),
            'min_cleanliness':min(clean) if clean else None,'max_cleanliness':max(clean) if clean else None,
            'first_report_at':iso(observations[0]['createdAt']) if observations else None,'last_report_at':iso(observations[-1]['createdAt']) if observations else None,
            'first_queue_severity':(severity[0] or None) if severity else None,'last_queue_severity':(severity[-1] or None) if severity else None,
            'report_ids':[r['id'] for r in observations[:200]],'report_ids_complete':len(observations)<=200}

    def expected(self,case,prior=None):
        c=case['expected_constraints'];intent=c['intent'];required=case.get('required_status');status=None if required=='no_result' else required;origin=case.get('location')
        end=instant(case['reference_time']);start=end-timedelta(hours=c.get('hours',24))
        window={'start_time':start.isoformat(),'end_time':end.isoformat()}
        calls=[];ids=[];distances={};stats=[]
        def call(name,args):calls.append({'tool':name,'arguments':args})
        if status=='invalid_input':pass
        elif c.get('referent'):
            ids=[prior[c['referent']-1]] if prior and len(prior)>=c['referent'] else []
            if not ids:status='reference_resolution_failure'
            else:call('get_hospital_details',{'hospital_id':ids[0]})
        elif c.get('names'):
            for name in c['names']:
                exact=[hid for hid,h in self.hospitals.items() if h['name'].lower()==name.lower()]
                matches=exact or [hid for hid,h in self.hospitals.items() if name.lower() in h['name'].lower()]
                call('resolve_hospitals',{'query':name})
                if len(matches)!=1:status='ambiguous' if matches else 'no_result';ids=[];break
                ids.extend(matches);call('get_hospital_details',{'hospital_id':matches[0]})
        elif intent in ('ambiguous','unsupported'):status=intent
        else:
            distances=self.distances(origin)
            ids=sorted((hid for hid,d in distances.items() if c.get('radius_m') is None or d<=c['radius_m']),key=lambda hid:(distances[hid],hid))
            args={**origin}
            if c.get('radius_m') is not None:args['radius_m']=c['radius_m']
            if intent=='nearest':args['limit']=1;ids=ids[:1]
            call('search_nearby_hospitals',args)
        if not status and ids:
            if intent=='temporal':
                call('get_queue_statistics',{'hospital_id':ids[0],**window});stats=[self.statistics(ids[0],start,end)]
            elif intent=='comparison':
                call('compare_hospitals',{'hospital_ids':ids,**window});ids=sorted(ids);stats=[self.statistics(hid,start,end) for hid in ids]
            elif intent in ('ranking','multi_step','attribute'):
                weights=c.get('weights',[1/3,1/3,1/3]);limit=1 if intent=='attribute' else c.get('limit',3)
                args={'candidate_ids':ids,**origin,**window,'distance_weight':weights[0],'queue_weight':weights[1],'cleanliness_weight':weights[2],'limit':limit}
                for key in ('radius_m','min_cleanliness','max_queue_severity','max_wait_minutes'):
                    if key in c:args[key]=c[key]
                call('rank_hospitals',args)
                eligible=[]
                for hid in ids:
                    s=self.statistics(hid,start,end);q=s['average_queue_severity'];clean=s['average_cleanliness'];wait=s['average_wait_minutes']
                    if (weights[1]>0 and q is None) or (weights[2]>0 and clean is None):continue
                    if 'min_cleanliness' in c and (clean is None or clean<c['min_cleanliness']):continue
                    if 'max_queue_severity' in c and (q is None or q>c['max_queue_severity']):continue
                    if 'max_wait_minutes' in c and (wait is None or wait>c['max_wait_minutes']):continue
                    cost=weights[0]*min(distances[hid]/c.get('radius_m',5000),1)+weights[1]*((q if q is not None else 1)-1)/4+weights[2]*(5-(clean if clean is not None else 5))/4
                    eligible.append((cost,hid,s))
                eligible.sort(key=lambda item:(item[0],item[1]));ids=[hid for _,hid,_ in eligible[:limit]];stats=[s for _,_,s in eligible[:limit]]
        status=status or ('ok' if ids else 'no_result')
        if required is not None and status != required:
            raise ValueError('Authored expected status disagrees with executable ground truth: '+case['id'])
        if status!='ok':ids=[];stats=[]
        entities=[self.entity(hid,distances.get(hid)) for hid in ids]
        actions=[]
        if ids:
            actions=[{'type':'fit_bounds','hospital_ids':ids},{'type':'highlight','hospital_ids':ids}]
            if intent in ('radius','ranking','multi_step','attribute'):actions.insert(0,{'type':'filter','hospital_ids':ids})
            if intent in ('ranking','multi_step','attribute'):actions.append({'type':'rank','hospital_ids':ids})
            if intent=='comparison':actions.append({'type':'compare','hospital_ids':ids})
            if intent in ('lookup','temporal'):actions[0]={'type':'fly_to','hospital_id':ids[0]}
            actions.append({'type':'open_popup','hospital_id':ids[0]})
        accepted=[calls]
        if c.get('names') and status=='ok':accepted.append([step for step in calls if step['tool']!='get_hospital_details'])
        return {'expected_status':status,'expected_hospital_ids':ids,'expected_entities':entities,'expected_statistics':stats,'expected_time_window':window,'accepted_calls':accepted,
            'expected_tools':[call['tool'] for call in calls],'expected_calls':calls,'expected_map_actions':actions,'oracle_source':self.source}

def materialize(oracle,cases):
    results=[]
    for case in cases:
        prior=None
        if case.get('setup_turns'):
            for turn in case['setup_turns']:
                setup={**case,'query':turn['query'],'required_status':None,'expected_constraints':turn['constraints']}
                outcome=oracle.expected(setup,prior)
                if outcome['expected_status']=='ok':prior=outcome['expected_hospital_ids']
        elif case.get('setup_query'):
            setup={**case,'query':case['setup_query'],'expected_constraints':case['setup_constraints']}
            prior=oracle.expected(setup)['expected_hospital_ids']
        results.append({**case,**oracle.expected(case,prior)})
    return results
