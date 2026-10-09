import re
from .schemas import AgentFailure

def validate_plan(plan,query,max_steps=12):
    if plan.referent and plan.names:raise AgentFailure("reference_resolution_failure","Referent and names cannot be mixed")
    if plan.intent in ("ranking","attribute","multi_step") and plan.names:raise AgentFailure("unsupported","Named ranking is not supported in v1")
    if plan.intent in ("lookup","temporal","comparison") and not(plan.names or plan.referent):raise AgentFailure("ambiguous","Hospital name or referent required")
    if plan.intent in ("ambiguous","unsupported"):return []
    steps=["get_hospital_details"] if plan.referent else ([tool for name in plan.names for tool in ["resolve_hospitals","get_hospital_details"]] if plan.names else ["search_nearby_hospitals"])
    if plan.intent=="temporal":steps.append("get_queue_statistics")
    if plan.intent=="comparison":steps.append("compare_hospitals")
    if plan.intent in ("ranking","attribute","multi_step"):steps.append("rank_hospitals")
    if len(steps)>max_steps:raise AgentFailure("agent_loop","Maximum planning steps exceeded")
    radius=re.search(r"(\d+(?:\.\d+)?)\s*(km|公里|千米|m\b|米)",query.lower())
    if radius:
        expected=float(radius[1])*(1000 if radius[2] in ("km","公里","千米") else 1)
        if plan.radius_m is None or abs(plan.radius_m-expected)>1e-9:raise AgentFailure("wrong_spatial_constraint","Plan disagrees with explicit radius")
    hours=re.search(r"(?:过去|最近|past|last)\s*(\d+(?:\.\d+)?)\s*(小时|hours?|h\b|days?|天)",query.lower())
    if hours:
        expected=float(hours[1])*(24 if hours[2] in ("day","days","天") else 1)
        if abs(plan.hours-expected)>1e-9:raise AgentFailure("wrong_temporal_window","Plan disagrees with explicit temporal window")
    score=re.search(r"(?:至少|at least|cleanliness\s*>=)\s*([0-9]+(?:\.\d+)?)",query.lower())
    if score and plan.min_cleanliness!=float(score[1]):raise AgentFailure("wrong_argument_extraction","Plan disagrees with explicit cleanliness threshold")
    return steps
