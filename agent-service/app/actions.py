import json
from pathlib import Path
from jsonschema import Draft7Validator
from .schemas import AgentFailure

SCHEMA=json.loads((Path(__file__).resolve().parents[2]/"contracts/map-actions.schema.json").read_text(encoding="utf8"))
VALIDATOR=Draft7Validator(SCHEMA)

def validate_actions(actions,entities):
    try:
        VALIDATOR.validate(actions)
        allowed={h["hospital_id"] for h in entities}
        for action in actions:
            ids=action.get("hospital_ids",[action.get("hospital_id")])
            if not set(ids).issubset(allowed):raise ValueError("Unverified hospital ID")
    except Exception as error:raise AgentFailure("map_action_failure","地图动作无效或包含未经验证的医院。") from error
    return actions

def map_actions(plan,entities):
    ids=[h["hospital_id"] for h in entities]
    if not ids:return []
    actions=[{"type":"fit_bounds","hospital_ids":ids},{"type":"highlight","hospital_ids":ids}]
    if plan.intent in ("ranking","attribute","multi_step"):actions.append({"type":"rank","hospital_ids":ids})
    if plan.intent in ("radius","ranking","attribute","multi_step"):actions.insert(0,{"type":"filter","hospital_ids":ids})
    if plan.intent=="comparison" and len(ids)>1:actions.append({"type":"compare","hospital_ids":ids[:20]})
    if plan.intent in ("lookup","temporal"):actions[0]={"type":"fly_to","hospital_id":ids[0]}
    actions.append({"type":"open_popup","hospital_id":ids[0]})
    return validate_actions(actions,entities)
