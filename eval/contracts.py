"""Structural baseline output checks; these do not verify factual correctness."""
import json

def validate_result(result):
    if not isinstance(result,dict) or not isinstance(result.get('status'),str) or not isinstance(result.get('answer'),str):raise ValueError('Invalid result envelope')
    json.dumps(result,allow_nan=False)
    for collection in ('entities','statistics','map_actions','trace'):
        if not isinstance(result.get(collection,[]),list) or any(not isinstance(row,dict) for row in result.get(collection,[])):raise ValueError('Invalid '+collection)
    for entity in result.get('entities',[]):
        if type(entity.get('hospital_id')) is not int or entity['hospital_id']<=0 or not isinstance(entity.get('name'),str):raise ValueError('Invalid entity schema')
    for stat in result.get('statistics',[]):
        if type(stat.get('hospital_id')) is not int:raise ValueError('Invalid statistic schema')
    return result
