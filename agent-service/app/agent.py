import asyncio
from datetime import datetime, timedelta, timezone
from .schemas import AgentFailure
from .planner import validate_plan
from .verifier import verify
from .actions import map_actions


def parse_clock(value):
    if value is None:
        return datetime.now(timezone.utc)
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("Offset required")
        return instant.astimezone(timezone.utc)
    except ValueError as error:
        raise AgentFailure("wrong_temporal_window", "Reference time must have an explicit time zone") from error


class Agent:
    def __init__(self, tools, provider, max_calls=24, max_steps=12, tool_timeout=5):
        self.tools, self.provider = tools, provider
        self.max_calls,self.max_steps,self.tool_timeout=max_calls,max_steps,tool_timeout
        self.trace=[]

    async def run(self, request, prior=None, emit=None):
        trace = []
        self.trace=trace
        async def event(stage, data=None):
            if emit:
                await emit(stage, data or {})
        async def call(name, arguments):
            if len(trace) >= self.max_calls:
                raise AgentFailure("agent_loop", "Maximum tool call count exceeded")
            await event("tool_start", {"tool":name})
            entry={"step":len(trace)+1,"tool":name,"arguments":arguments,"status":"running"}
            trace.append(entry)
            try:
                result=await asyncio.wait_for(self.tools.call(name,arguments),timeout=self.tool_timeout)
                entry.update(status="ok",result=result)
                await event("tool_result",{"tool":name,"step":entry["step"]})
                return result["data"]
            except asyncio.CancelledError:
                entry.update(status="cancelled",failure="timeout");raise
            except asyncio.TimeoutError as error:
                entry.update(status="failed",failure="tool_timeout")
                raise AgentFailure("tool_timeout","GIS 工具调用超时。") from error
            except Exception as error:
                entry.update(status="failed",failure=getattr(error,"code","tool_execution_failure"))
                raise
        try:
            now = parse_clock(request.reference_time)
            # PostgreSQL/Node tool timestamps use milliseconds; share the exact boundary.
            now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
            await event("planning")
            catalog=await self.tools.load_catalog()
            plan=await self.provider.plan(request.query,{"reference_time":now.isoformat(),"location":request.location.model_dump() if request.location else None,"previous_entities":prior or []},catalog)
            steps=validate_plan(plan,request.query,self.max_steps)
            if abs(plan.distance_weight+plan.queue_weight+plan.cleanliness_weight-1)>1e-9:
                raise AgentFailure("wrong_argument_extraction","Ranking weights must sum to one")
            if plan.intent in ("ambiguous","unsupported"):
                raise AgentFailure(plan.intent,"请明确医院名称或支持的距离、排队和清洁度条件。")
            window={"start_time":(now-timedelta(hours=plan.hours)).isoformat(),"end_time":now.isoformat()}
            entities=[]; stats=[]; data={}; candidates=[]
            await event("executing",{"intent":plan.intent})
            if plan.referent is not None:
                if not prior or plan.referent>len(prior):
                    raise AgentFailure("reference_resolution_failure","没有可用的已验证排序结果来解析该引用。")
                entities=[await call("get_hospital_details",{"hospital_id":prior[plan.referent-1]["hospital_id"]})]
            elif plan.names:
                for name in plan.names:
                    resolved=await call("resolve_hospitals",{"query":name})
                    if not resolved["complete"] or len(resolved["hospitals"])!=1:
                        raise AgentFailure("ambiguous" if resolved["hospitals"] else "no_result","医院名称未匹配或有多个匹配，请使用完整名称。")
                    entities.append(await call("get_hospital_details",{"hospital_id":resolved["hospitals"][0]["hospital_id"]}))
            else:
                if request.location is None:
                    raise AgentFailure("missing_location","需要浏览器提供位置或显式坐标。")
                arguments=request.location.model_dump()
                if plan.radius_m is not None: arguments["radius_m"]=plan.radius_m
                if plan.intent=="nearest": arguments["limit"]=1
                data=await call("search_nearby_hospitals",arguments)
                candidates=data["hospitals"]
                entities=candidates
                if plan.intent != "nearest" and not data["complete"]:
                    raise AgentFailure("incomplete_candidates","候选超过安全上限，不能证明全范围最佳结果；请缩小半径。")
            if plan.intent=="temporal" and entities:
                stats=[await call("get_queue_statistics",{"hospital_id":entities[0]["hospital_id"],**window})]
            elif plan.intent=="comparison" and entities:
                if len(entities)<2: raise AgentFailure("ambiguous","比较需要至少两家明确的医院。")
                data=await call("compare_hospitals",{"hospital_ids":list(dict.fromkeys(h["hospital_id"] for h in entities)),**window})
                entities=data["hospitals"];stats=data["statistics"]
            elif plan.intent in ("ranking","attribute","multi_step") and entities:
                args={"candidate_ids":[h["hospital_id"] for h in entities],**request.location.model_dump(),**window,
                      "distance_weight":plan.distance_weight,"queue_weight":plan.queue_weight,"cleanliness_weight":plan.cleanliness_weight,
                      "limit":1 if plan.intent=="attribute" else plan.limit}
                for key in ("radius_m","min_cleanliness","max_queue_severity","max_wait_minutes"):
                    if getattr(plan,key) is not None: args[key]=getattr(plan,key)
                data=await call("rank_hospitals",args);entities=data["hospitals"]
                selected={h["hospital_id"] for h in entities};stats=[s for s in data["statistics"] if s["hospital_id"] in selected]
            await event("verifying")
            verification=verify(plan,entities,stats,trace,window)
            actions=map_actions(plan,entities)
            await event("responding")
            answer=render_answer(entities,stats,window if stats else None)
            return {"status":"ok" if entities else "no_result","answer":answer,"entities":entities,"statistics":stats,
                    "map_actions":actions,"plan":plan.model_dump(),"planned_tools":steps,"verification":verification,"trace":trace,"provider":self.provider.name,
                    "warnings":["规则规划演示，未调用 LLM。"] if self.provider.name=="rules" else []}
        except Exception as error:
            code=getattr(error,"code","tool_execution_failure")
            message=getattr(error,"message","执行失败，未生成未经验证的答案。")
            trace.append({"stage":"failure","failure":code,"message":message})
            return {"status":code,"answer":message,"entities":[],"statistics":[],"map_actions":[],"trace":trace,"provider":self.provider.name}


def render_answer(entities,stats,window):
    if not entities:
        return "没有符合条件且具备所需观测数据的医院。"
    by_id={s["hospital_id"]:s for s in stats}
    lines=[]
    for index,h in enumerate(entities,1):
        line=f"{index}. {h['name']}（医院 ID {h['hospital_id']}）"
        if h["distance_m"] is not None: line+=f"，直线距离 {h['distance_m']:.1f} 米"
        if h["hospital_id"] in by_id:
            s=by_id[h["hospital_id"]]
            line+=f"；窗口内 {s['report_count']} 条报告"
            if s["average_queue_severity"] is not None: line+=f"，平均排队等级 {s['average_queue_severity']:.2f}/5（不是分钟）"
            if s["average_wait_minutes"] is not None: line+=f"，报告的平均等待 {s['average_wait_minutes']:.2f} 分钟"
            if s["average_cleanliness"] is not None: line+=f"，平均清洁度 {s['average_cleanliness']:.2f}/5（{s['cleanliness_count']} 条评分）"
            else: line+="，没有数值清洁度评分"
            if s["first_queue_severity"] is not None and s["last_queue_severity"] is not None:
                line+=f"，首末排队等级 {s['first_queue_severity']} → {s['last_queue_severity']}"
        else:
            line+=f"；最新报告状态：{h['queue_description']}，报告时间 {h['latest_report_at'] or '无报告'}"
        lines.append(line)
    if window: lines.append(f"时间窗口 [{window['start_time']}, {window['end_time']})。")
    return "\n".join(lines)
