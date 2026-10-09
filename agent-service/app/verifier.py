import math
from datetime import datetime
from .schemas import AgentFailure

def require(condition,message):
    if not condition:raise AgentFailure("verification_failure",message)
def timestamp(value):return datetime.fromisoformat(value.replace("Z","+00:00"))

def verify(plan,entities,statistics,trace,window):
    ids=[h["hospital_id"] for h in entities]
    require(len(ids)==len(set(ids)),"Duplicate final hospital IDs")
    source={};stat_source={};candidate_ids=None
    for entry in trace:
        require(entry.get("status")=="ok","Unsuccessful tool in final trace")
        result=entry["result"];args=entry["arguments"];data=result["data"];name=entry["tool"]
        require(result["tool"]==name and result["arguments"]==args,"Trace and envelope disagree")
        hospitals=[data] if name=="get_hospital_details" else data.get("hospitals",[])
        hospital_ids=[h['hospital_id'] for h in hospitals]
        require(len(hospital_ids)==len(set(hospital_ids)),"Duplicate tool hospital IDs")
        if name=='get_hospital_details':require(hospital_ids==[args['hospital_id']],"Detail hospital ID mismatch")
        if name=='compare_hospitals':require(set(hospital_ids)==set(args['hospital_ids']),"Comparison hospital set mismatch")
        if name=='resolve_hospitals':require(all(args['query'].strip().lower() in h['name'].lower() for h in hospitals),"Resolved name does not match query")
        if name=="search_nearby_hospitals":
            candidate_ids={h["hospital_id"] for h in hospitals};distances=[h["distance_m"] for h in hospitals]
            require(all(d is not None and math.isfinite(d) and d>=0 for d in distances),"Invalid distance")
            require(distances==sorted(distances),"Nearby search is not distance-sorted")
            if "radius_m" in args:require(all(d<=args["radius_m"] for d in distances),"Radius violation")
        if args.get("start_time"):
            start,end=timestamp(args["start_time"]),timestamp(args["end_time"])
            require(start==timestamp(window["start_time"]) and end==timestamp(window["end_time"]),"Wrong time window")
            ew=result["evidence"].get("time_window") or {}
            require(ew.get("end_exclusive") is True,"Missing exclusive window end")
            require(timestamp(ew["start"])==start and timestamp(ew["end"])==end,"Evidence window mismatch")
            for report in data.get("reports",[]):
                require(start<=timestamp(report["created_at"])<end,"Report outside window")
                require(report["hospital_id"]==args["hospital_id"],"Report from another hospital")
        batch=data["statistics"] if "statistics" in data else ([data] if name in ("get_queue_statistics","get_cleanliness_statistics") else [])
        expected=args.get("hospital_ids",args.get("candidate_ids",[args.get("hospital_id")]))
        if name in ('compare_hospitals','rank_hospitals','get_queue_statistics','get_cleanliness_statistics'):
            require(len(batch)==len(expected) and {s['hospital_id'] for s in batch}==set(expected),"Incomplete statistics coverage")
        for s in batch:
            require(s["hospital_id"] in expected,"Statistic from another hospital")
            for count in ("known_queue_count","observed_wait_count","cleanliness_count"):require(0<=s[count]<=s["report_count"],"Impossible sample count")
            for metric,low,high in [("average_queue_severity",1,5),("average_cleanliness",1,5),("average_wait_minutes",0,1440)]:
                value=s[metric];require(value is None or(math.isfinite(value) and low<=value<=high),"Impossible aggregate")
            require(len(s["report_ids"])==len(set(s["report_ids"])),"Duplicate report evidence")
            if s["report_ids_complete"]:require(len(s["report_ids"])==s["report_count"],"Incomplete report evidence")
            for field in ('first_report_at','last_report_at'):
                value=s[field]
                require(value is None if s['report_count']==0 else value is not None and start<=timestamp(value)<end,"Aggregate timestamp outside window")
            for count,metric in [('known_queue_count','average_queue_severity'),('observed_wait_count','average_wait_minutes'),('cleanliness_count','average_cleanliness')]:
                require((s[count]==0)==(s[metric] is None),"Aggregate sample count disagrees with metric")
            stat_source[s["hospital_id"]]=s
        if name=="rank_hospitals":
            require(candidate_ids is not None and set(args["candidate_ids"])==candidate_ids,"Ranking candidate set mismatch")
            verify_ranking(args,data)
        for h in hospitals:source[h["hospital_id"]]=h
    require(all(h==source.get(h["hospital_id"]) for h in entities),"Final entity differs from source")
    require(all(s==stat_source.get(s["hospital_id"]) for s in statistics),"Final statistics differ from source")
    require(set(s["hospital_id"] for s in statistics).issubset(ids),"Unrelated final statistic")
    if candidate_ids is not None:require(set(ids).issubset(candidate_ids),"Final ID outside candidates")
    for s in statistics:
        if plan.min_cleanliness is not None:require(s["average_cleanliness"] is not None and s["average_cleanliness"]>=plan.min_cleanliness,"Cleanliness filter violation")
        if plan.max_queue_severity is not None:require(s["average_queue_severity"] is not None and s["average_queue_severity"]<=plan.max_queue_severity,"Queue filter violation")
        if plan.max_wait_minutes is not None:require(s["average_wait_minutes"] is not None and s["average_wait_minutes"]<=plan.max_wait_minutes,"Wait filter violation")
    return {"passed":True,"checks":["tool_evidence","candidate_membership","time_window","entity_facts","statistics","filters","ranking"]}

def verify_ranking(args,data):
    require(data["algorithm"]=="weighted-cost-v1","Unknown ranking algorithm")
    scale=args.get("radius_m",5000);require(data["distance_scale_m"]==scale,"Wrong normalization")
    stats={s["hospital_id"]:s for s in data["statistics"]};candidates={h["hospital_id"]:h for h in data["candidate_hospitals"]}
    require(set(candidates)==set(args["candidate_ids"]) and set(stats)==set(candidates),"Incomplete ranking evidence")
    expected=[];excluded=[]
    for hid,h in candidates.items():
        s=stats[hid];d=h["distance_m"];require(d is not None and math.isfinite(d) and d>=0,"Missing distance")
        missing=(args["queue_weight"]>0 and s["average_queue_severity"] is None) or(args["cleanliness_weight"]>0 and s["average_cleanliness"] is None)
        filtered=("radius_m" in args and d>args["radius_m"]) or("min_cleanliness" in args and(s["average_cleanliness"] is None or s["average_cleanliness"]<args["min_cleanliness"])) or("max_queue_severity" in args and(s["average_queue_severity"] is None or s["average_queue_severity"]>args["max_queue_severity"])) or("max_wait_minutes" in args and(s["average_wait_minutes"] is None or s["average_wait_minutes"]>args["max_wait_minutes"]))
        if missing or filtered:excluded.append(hid);continue
        q=s["average_queue_severity"] if s["average_queue_severity"] is not None else 1;c=s["average_cleanliness"] if s["average_cleanliness"] is not None else 5
        cost=args["distance_weight"]*min(d/scale,1)+args["queue_weight"]*(q-1)/4+args["cleanliness_weight"]*(5-c)/4
        expected.append((cost,hid))
    expected.sort();expected=expected[:args.get("limit",3)]
    require([h["hospital_id"] for h in data["hospitals"]]==[hid for _,hid in expected],"Wrong global ranking order")
    require(set(data["excluded_ids"])==set(excluded),"Wrong excluded candidates")
    require(len(data["ranking"])==len(expected),"Ranking length mismatch")
    for i,((cost,hid),actual) in enumerate(zip(expected,data["ranking"]),1):require(actual["hospital_id"]==hid and actual["rank"]==i and abs(actual["score"]-cost)<=1e-9,"Ranking score mismatch")
