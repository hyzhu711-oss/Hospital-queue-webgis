"""Keep original inference journal; produce separately versioned scoring evidence."""
import argparse
import json
import os
from collections import Counter
from pathlib import Path
from llm_experiment import ROOT, SYSTEMS, implementation_hash
from oracle import Oracle, materialize
from llm_metrics import evaluate_case, classify
from metrics import aggregate


def rescore(run_id):
    target = ROOT / 'eval/reports/llm' / run_id
    metadata = json.loads((target / 'metadata.json').read_text(encoding='utf-8'))
    definitions = json.loads((ROOT / f"eval/benchmark_v2/{metadata['split']}/definitions.json").read_text(encoding='utf-8'))
    oracle = Oracle.database(os.environ['EVAL_DATABASE_URL'])
    cases = {case['id']: case for case in materialize(oracle, definitions)}
    rows = [json.loads(line) for line in (target / 'cases.jsonl').read_text(encoding='utf-8').splitlines()]
    for row in rows:
        case = cases[row['id']]
        row['metrics'] = evaluate_case(case, row['result'], oracle, row['system'], row['model_calls'])
        if not row['setup_correct']:
            row['metrics']['workflow_success_rate'] = row['metrics']['end_to_end_success_rate'] = False
        row['failure'] = classify(case, row['result'], row['metrics'], oracle, row['system'])
        if row['failure'] and not row['setup_correct']:
            row['failure']['types'].append('wrong_follow_up_reference')
    metadata['scoring_implementation_sha256'] = implementation_hash()
    metadata['rescore_reason_zh'] = 'validation 发现复合无结果案例被 authored status 过早跳过 ranking。修复独立 oracle 的执行路径并断言真值一致；仅重新计分，保留原始推理和失败日志，不改模型输出、prompt 或约束。'
    result = {'metadata': metadata, 'systems': {}}
    for system in SYSTEMS:
        chosen = [row for row in rows if row['system'] == system]
        result['systems'][system] = {'metrics': aggregate(chosen), 'severities': dict(Counter(row['failure']['severity'] for row in chosen if row['failure'])),
            'by_category': {category: aggregate([row for row in chosen if row['category'] == category]) for category in metadata['category_counts']}}
    (target / 'rescored-cases.jsonl').write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n', encoding='utf-8')
    (target / 'rescored-summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name, value in result['systems'].items():
        print(name, value['metrics']['end_to_end_success_rate'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('run_id')
    rescore(parser.parse_args().run_id)
