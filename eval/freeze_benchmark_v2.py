"""Seal the holdout before any official inference; do not overwrite a freeze."""
import hashlib
import json
import os
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from llm_experiment import implementation_hash, digest, ROOT
from oracle import Oracle, materialize


def freeze():
    target = ROOT / 'eval/benchmark_v2/freeze.json'
    if target.exists():
        raise ValueError('A freeze already exists')
    test_path = ROOT / 'eval/benchmark_v2/test/definitions.json'
    validation_path = ROOT / 'eval/benchmark_v2/validation/definitions.json'
    definitions = json.loads(test_path.read_text(encoding='utf-8'))
    validation = json.loads(validation_path.read_text(encoding='utf-8'))
    dev = json.loads((ROOT / 'eval/benchmark/definitions.json').read_text(encoding='utf-8'))
    overlap = {case['query'].strip().lower() for case in definitions} & {case['query'].strip().lower() for case in validation + dev}
    if overlap:
        raise ValueError('Holdout main-query overlap detected')
    oracle = Oracle.database(os.environ['EVAL_DATABASE_URL'])
    cases = materialize(oracle, definitions)
    for case in cases:
        json.dumps(case, allow_nan=False)
    ground_path = ROOT / 'eval/benchmark_v2/test/cases.json'
    ground_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    manifest = {'benchmark_version': '2.0.0', 'status': 'frozen_unexposed', 'case_count': len(cases),
        'category_distribution': dict(Counter(c['category'] for c in cases)),
        'expected_outcomes': dict(Counter(c['expected_status'] for c in cases)),
        'test_sha256': digest(test_path), 'test_canonical_sha256': hashlib.sha256(json.dumps(definitions, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'ground_truth_sha256': digest(ground_path), 'validation_sha256': digest(validation_path),
        'fixture_sha256': digest(ROOT / 'eval/benchmark/fixture.json'),
        'database_snapshot_sha256': hashlib.sha256(json.dumps(oracle.fixture, sort_keys=True).encode()).hexdigest(),
        'reference_clock': '2026-06-01T12:00:00Z', 'generation_seed': 20261007,
        'git_base_commit': head, 'working_tree_identifier': implementation_hash(), 'implementation_sha256': implementation_hash(),
        'freeze_timestamp': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'policy': 'First formal test inference exposes the holdout. Do not tune and reuse it as unseen; create a new version if system changes are needed.'}
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'frozen': True, 'test_cases': len(cases), 'test_sha256': manifest['test_sha256'], 'fixture_sha256': manifest['fixture_sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    freeze()
