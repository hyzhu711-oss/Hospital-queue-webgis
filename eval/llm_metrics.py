"""Deterministic semantic and severity checks for frozen model experiments."""
import json
import re
from metrics import score, same

IR_KEYS = ('intent_accuracy', 'spatial_constraint_accuracy', 'temporal_constraint_accuracy', 'filter_extraction_accuracy', 'objective_extraction_accuracy', 'limit_extraction_accuracy', 'reference_resolution_accuracy')


def extracted_plan(result, calls):
    if result.get('plan'):
        return result['plan']
    for call in reversed(calls):
        try:
            value = json.loads(call.get('content', ''))
            if isinstance(value, dict) and 'intent' in value:
                return value
        except (ValueError, TypeError):
            pass
    return None


def evaluate_case(case, result, oracle, system, calls):
    adjusted = dict(result)
    accepted = case.get('allowed_statuses', [case['expected_status']])
    if result.get('status') in accepted:
        adjusted['status'] = case['expected_status']
    metric = score(case, adjusted, oracle, tool_metrics=system in ('proposed_llm', 'single_step'))
    if system in ('proposed_llm', 'single_step'):
        def canonical(values):
            output = []
            for step in values:
                args = dict(step['arguments'])
                for key in ('candidate_ids', 'hospital_ids'):
                    if key in args:
                        args[key] = sorted(args[key])
                if step['tool'] == 'resolve_hospitals':
                    args['query'] = args['query'].strip().lower()
                output.append({'tool': step['tool'], 'arguments': args})
            # Name resolution/detail order is not itself a task constraint.
            lookups = [v for v in output if v['tool'] in ('resolve_hospitals', 'get_hospital_details')]
            remaining = [v for v in output if v['tool'] not in ('resolve_hospitals', 'get_hospital_details')]
            return sorted(lookups, key=lambda v: json.dumps(v, sort_keys=True)) + remaining
        actual = [{'tool': step['tool'], 'arguments': step['arguments']} for step in result.get('trace', []) if 'tool' in step]
        metric['tool_argument_accuracy'] = any(same(canonical(actual), canonical(accepted)) for accepted in case['accepted_calls'])
        metric['end_to_end_success_rate'] = all(v for v in metric.values() if v is not None)
    plan = extracted_plan(result, calls)
    c = case['expected_constraints']
    semantic = {key: None for key in IR_KEYS}
    # The full semantic PlanSpec is only supplied by Proposed. A/B/C are N/A,
    # not penalized for a representation they do not claim to produce.
    if system == 'proposed_llm':
        if c['intent'] in ('ambiguous', 'unsupported') or case['expected_status'] == 'invalid_input':
            semantic['intent_accuracy'] = result.get('status') in accepted
        else:
            plan = plan or {}
            semantic['intent_accuracy'] = plan.get('intent') == c['intent']
            semantic['spatial_constraint_accuracy'] = same(plan.get('radius_m'), c.get('radius_m'))
            semantic['temporal_constraint_accuracy'] = same(plan.get('hours', 24), c.get('hours', 24))
            semantic['filter_extraction_accuracy'] = all(same(plan.get(k), c.get(k)) for k in ('min_cleanliness', 'max_queue_severity', 'max_wait_minutes'))
            if c['intent'] in ('ranking', 'attribute', 'multi_step'):
                semantic['objective_extraction_accuracy'] = same([plan.get(k, 1/3) for k in ('distance_weight', 'queue_weight', 'cleanliness_weight')], c.get('weights', [1/3, 1/3, 1/3]))
                semantic['limit_extraction_accuracy'] = True if c['intent'] == 'attribute' else same(plan.get('limit', 3), c.get('limit', 3))
            semantic['reference_resolution_accuracy'] = same(plan.get('referent'), c.get('referent'))
    # E2E includes the applicable typed semantic extraction checks, not only an
    # accidentally correct entity set. Return both for transparent comparison.
    metric['workflow_success_rate'] = metric['end_to_end_success_rate']
    metric.update(semantic)
    metric['semantic_success_rate'] = all(value for value in semantic.values() if value is not None) if system == 'proposed_llm' else None
    return metric


def factual_mismatch(result, oracle, case):
    """Separate real fact mismatches from closed-template formatting failures."""
    distances = oracle.distances(case['location']) if case.get('location') else {}
    from oracle import instant
    window = case['expected_time_window']
    for step in result.get('trace', []):
        args = step.get('arguments', {})
        if args.get('start_time') and args.get('end_time'):
            window = {key: args[key] for key in ('start_time', 'end_time')}
    stated = re.search(r'时间窗口 \[([^,]+),\s*([^\)]+)\)', result.get('answer', ''))
    if stated:
        try:
            instant(stated[1]); instant(stated[2])
            window = {'start_time': stated[1], 'end_time': stated[2]}
        except ValueError:
            pass
    for entity in result.get('entities', []):
        hid = entity.get('hospital_id')
        if hid not in oracle.hospitals:
            if any(entity.get(k) is not None for k in ('distance_m', 'cleanliness_score', 'queue_wait_minutes', 'latest_report_at')):
                return True
            continue
        truth = oracle.entity(hid, distances.get(hid) if entity.get('distance_m') is not None else None)
        for key in ('distance_m', 'latitude', 'longitude', 'queue_description', 'cleanliness_note', 'latest_report_at', 'cleanliness_score', 'queue_wait_minutes'):
            if key in entity and entity[key] is not None and not same(entity[key], truth.get(key)):
                return True
    for stat in result.get('statistics', []):
        hid = stat.get('hospital_id')
        if hid not in oracle.hospitals:
            return True
        truth = oracle.statistics(hid, instant(window['start_time']), instant(window['end_time']))
        if any(k != 'hospital_id' and not same(value, truth.get(k)) for k, value in stat.items()):
            return True
    return False


def classify(case, result, metrics, oracle, system):
    if metrics['end_to_end_success_rate']:
        return None
    status = result.get('status')
    plan = result.get('plan') or {}
    c = case['expected_constraints']
    types = []
    status_types = {'intent_parsing_failure': 'intent_parsing_failure', 'malformed_output': 'malformed_structured_output',
        'verification_failure': 'verification_failure', 'timeout': 'timeout', 'tool_timeout': 'timeout',
        'tool_execution_failure': 'tool_execution_failure', 'provider_http_failure': 'tool_execution_failure',
        'reference_resolution_failure': 'wrong_follow_up_reference', 'agent_loop': 'agent_loop'}
    if status in status_types:
        types.append(status_types[status])
    if system == 'text_to_sql' and status not in ('ok', 'no_result', 'ambiguous', 'unsupported'):
        types.append('SQL_generation_failure')
        sql = result.get('sql') or ''
        if 'undefinedcolumn' in str(result.get('error_class', '')).lower() or 'undefinedtable' in str(result.get('error_class', '')).lower():
            types.append('schema_hallucination')
    for metric, kind in [('intent_accuracy', 'intent_parsing_failure'), ('spatial_constraint_accuracy', 'spatial_constraint_error'),
        ('temporal_constraint_accuracy', 'temporal_constraint_error'), ('filter_extraction_accuracy', 'missing_filter'),
        ('objective_extraction_accuracy', 'wrong_ranking_objective'), ('reference_resolution_accuracy', 'wrong_follow_up_reference'),
        ('tool_selection_accuracy', 'wrong_tool_selection'), ('tool_argument_accuracy', 'wrong_arguments')]:
        if metrics.get(metric) is False:
            types.append(kind)
    if metrics['final_entity_accuracy'] is False:
        types.append('empty_result_handling_failure' if not case['expected_hospital_ids'] else 'wrong_core_result')
    if case['expected_status'] == 'ambiguous' and status != 'ambiguous':
        types.append('ambiguity_handling_failure')
    if metrics['map_action_accuracy'] is False:
        types.append('map_action_mismatch')
    fabricated = factual_mismatch(result, oracle, case)
    if fabricated:
        types.append('hallucinated_factual_answer')
    missed = system == 'proposed_llm' and status == 'ok' and not metrics['constraint_satisfaction_rate']
    if missed:
        types.append('verifier_missed_error')
    if fabricated:
        severity = 'S4'
    elif [h.get('hospital_id') for h in result.get('entities', [])] != case['expected_hospital_ids']:
        severity = 'S3'
    elif not result.get('entities') and not case['expected_hospital_ids']:
        severity = 'S0'  # Safe rejection type/format disagreement, no entity or fact returned.
    elif not metrics['constraint_satisfaction_rate'] or any(metrics.get(k) is False for k in IR_KEYS):
        severity = 'S2'
    elif not metrics['answer_groundedness'] and result.get('entities'):
        severity = 'S1'
    else:
        severity = 'S0'
    return {'types': list(dict.fromkeys(types or ['format_or_execution_contract'])), 'severity': severity,
        'severe': severity in ('S3', 'S4'), 'verifier_caught': system == 'proposed_llm' and status == 'verification_failure',
        'verifier_missed': missed, 'recoverable': status in ('ambiguous', 'missing_location', 'reference_resolution_failure', 'timeout', 'provider_http_failure'),
        'factual_mismatch': fabricated}
