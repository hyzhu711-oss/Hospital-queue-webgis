import copy
import json
from pathlib import Path
from datetime import timedelta
from oracle import Oracle,instant,materialize
from metrics import score
from contracts import validate_result
import pytest
from app.agent import render_answer

BASE=Path(__file__).resolve().parents[1]

def test_fixture_boundaries_missing_metrics_and_ties():
    fixture=json.loads((BASE/'benchmark/fixture.json').read_text(encoding='utf-8'))
    oracle=Oracle(fixture);end=instant(fixture['reference_time'])
    stats=oracle.statistics(1,end-timedelta(hours=24),end)
    assert stats['report_ids']==[2,3] and stats['average_cleanliness']==4.5
    assert stats['average_queue_severity']==2 and stats['report_count']==2
    assert oracle.statistics(6,end-timedelta(hours=24),end)['average_queue_severity'] is None
    assert oracle.statistics(7,end-timedelta(hours=24),end)['report_count']==0
    distance=oracle.distances({'latitude':51.5,'longitude':-.13})
    assert distance[1]==distance[11]

def test_benchmark_size_categories_and_scoring_mutations():
    fixture=json.loads((BASE/'benchmark/fixture.json').read_text(encoding='utf-8'))
    definitions=json.loads((BASE/'benchmark/definitions.json').read_text(encoding='utf-8'))
    oracle=Oracle(fixture);cases=materialize(oracle,definitions)
    assert len(cases)==120 and len({c['category'] for c in cases})==13
    assert len({c['id'] for c in cases})==120
    assert materialize(oracle,cases)==cases
    case=next(c for c in cases if c['category']=='multi_step' and c['expected_status']=='ok')
    result={'status':'ok','entities':case['expected_entities'],'statistics':case['expected_statistics'],
        'map_actions':case['expected_map_actions'],'trace':case['expected_calls']}
    result['answer']=render_answer(result['entities'],result['statistics'],case['expected_time_window'])
    assert all(score(case,result,oracle).values())
    changed=copy.deepcopy(result);changed['entities'][0]['distance_m']+=10
    assert not score(case,changed,oracle)['answer_groundedness']
    changed=copy.deepcopy(result);changed['answer']+=' 并且另一家医院 ID 999 距离 20 米。'
    assert not score(case,changed,oracle)['answer_groundedness']
    changed=copy.deepcopy(result);changed['map_actions'][0]['hospital_ids']=[999]
    assert not score(case,changed,oracle)['map_action_accuracy']

@pytest.mark.parametrize('bad',[{'status':'ok','answer':'x','entities':['x']}, {'status':'ok','answer':'x','entities':[{'hospital_id':True,'name':'x'}]}, {'status':'ok','answer':'x','statistics':[{}]}, {'status':'ok','answer':'x','entities':[{'hospital_id':1,'name':'x','distance_m':float('nan')}]}])
def test_malformed_baseline_is_a_recorded_failure(bad):
    with pytest.raises(ValueError):validate_result(bad)
