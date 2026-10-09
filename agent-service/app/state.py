import copy
import time
from uuid import uuid4,UUID
from .schemas import AgentFailure

class Sessions:
    """Bounded single-process sessions with opaque IDs, TTL and optimistic versions."""
    def __init__(self,ttl=1800,capacity=500):
        self.ttl,self.capacity=ttl,capacity;self.items={}
    def read(self,session_id):
        now=time.monotonic();self.items={k:v for k,v in self.items.items() if now-v["updated"]<self.ttl}
        if session_id is None:return None
        try:UUID(session_id)
        except ValueError as error:raise AgentFailure("stale_session","Invalid session ID") from error
        if session_id not in self.items:raise AgentFailure("stale_session","会话已过期，请重新查询。")
        return copy.deepcopy(self.items[session_id])
    def commit(self,session_id,state,entities,location,location_at=None):
        if session_id is None:
            if len(self.items)>=self.capacity:raise AgentFailure("session_capacity","会话容量已满。")
            session_id=str(uuid4());version=0;turns=0
        else:
            current=self.items.get(session_id)
            if current is None or state is None or current["version"]!=state["version"]:raise AgentFailure("state_conflict","会话发生并发更新，请重试。")
            version=current["version"];turns=current["turns"]
        if turns>=20:raise AgentFailure("stale_session","会话达到 20 轮上限，请开始新查询。")
        now=time.monotonic()
        self.items[session_id]={"entities":copy.deepcopy(entities),"location":location,"location_at":location_at if location_at is not None else now,"version":version+1,"turns":turns+1,"updated":now}
        return session_id
