import copy
import json
from pathlib import Path
import pytest
from oracle import Oracle, materialize
from llm_metrics import factual_mismatch, classify

BASE = Path(__file__).resolve().parents[1]


def test_v2_counts_structural_tags_and_disjoint_main_queries():
    values = {split: json.loads((BASE / f'benchmark_v2/{split}/definitions.json').read_text(encoding='utf-8')) for split in ('dev', 'validation', 'test')}
    assert [len(values[split]) for split in ('dev', 'validation', 'test')] == [120, 60, 180]
    assert {case['query'] for case in values['test']}.isdisjoint({case['query'] for case in values['dev'] + values['validation']})
    assert len({case['category'] for case in values['test']}) == 14
    assert any(len(case.get('setup_turns', [])) == 2 for case in values['test'])
    assert any('filter_before_top_k' in case['design_tags'] for case in values['test'])


def test_multi_turn_oracle_resolves_latest_successful_order():
    fixture = json.loads((BASE / 'benchmark/fixture.json').read_text())
    oracle = Oracle(fixture)
    cases = json.loads((BASE / 'benchmark_v2/test/definitions.json').read_text(encoding='utf-8'))
    case = next(case for case in cases if len(case.get('setup_turns', [])) == 2)
    expected = materialize(oracle, [case])[0]
    first = oracle.expected({**case, 'expected_constraints': case['setup_turns'][0]['constraints']})
    assert expected['expected_hospital_ids'] == [first['expected_hospital_ids'][1]]


def test_severity_does_not_treat_format_as_fabricated_fact():
    oracle = Oracle(json.loads((BASE / 'benchmark/fixture.json').read_text()))
    definition = json.loads((BASE / 'benchmark/definitions.json').read_text(encoding='utf-8'))[0]
    case = materialize(oracle, [definition])[0]
    result = {'status': 'ok', 'entities': case['expected_entities'], 'statistics': [], 'answer': '不符合闭合格式的说明', 'map_actions': case['expected_map_actions']}
    assert not factual_mismatch(result, oracle, case)
    result['entities'] = copy.deepcopy(result['entities'])
    result['entities'][0]['cleanliness_score'] = 1.
    assert factual_mismatch(result, oracle, case)


def test_no_result_conjunction_is_executed_before_status_assertion():
    oracle = Oracle(json.loads((BASE / 'benchmark/fixture.json').read_text()))
    definitions = json.loads((BASE / 'benchmark_v2/validation/definitions.json').read_text(encoding='utf-8'))
    case = next(case for case in definitions if case['category'] == 'no_result' and case['expected_constraints']['intent'] == 'multi_step')
    expected = oracle.expected(case)
    assert expected['expected_status'] == 'no_result'
    assert expected['expected_tools'] == ['search_nearby_hospitals', 'rank_hospitals']


def test_wrong_stated_window_is_semantic_error_not_fabrication():
    from oracle import instant
    oracle = Oracle(json.loads((BASE / 'benchmark/fixture.json').read_text()))
    definition = json.loads((BASE / 'benchmark/definitions.json').read_text(encoding='utf-8'))[0]
    case = materialize(oracle, [definition])[0]
    window = {'start_time': '2026-05-30T12:00:00Z', 'end_time': '2026-06-01T12:00:00Z'}
    stat = oracle.statistics(1, instant(window['start_time']), instant(window['end_time']))
    result = {'entities': case['expected_entities'], 'statistics': [stat], 'answer': f"时间窗口 [{window['start_time']}, {window['end_time']})。", 'trace': []}
    assert not factual_mismatch(result, oracle, case)
