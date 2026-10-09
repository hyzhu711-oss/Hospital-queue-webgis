"""Repeatable real-model experiment; emits resumable evidence, never credentials."""
import argparse
import asyncio
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent-service'))
from app.agent import Agent
from app.config import load_model_env
from app.llm import telemetry, redact
from app.providers import HttpChatProvider
from app.schemas import QueryRequest, AgentFailure
from app.tools import ToolClient
from baselines.runners import LLMOnly, SingleStep, TextToSQL, failure
from contracts import validate_result
from oracle import Oracle, materialize
from metrics import aggregate
from llm_metrics import evaluate_case, classify
from pydantic import ValidationError

SYSTEMS = ('llm_only', 'text_to_sql', 'single_step', 'proposed_llm')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def implementation_hash():
    paths = [p for directory in ('agent-service/app', 'src/tools', 'src/domain', 'src/store', 'eval/baselines') for p in (ROOT / directory).rglob('*') if p.suffix in ('.py', '.js')]
    paths += [ROOT / 'eval' / p for p in ('oracle.py', 'metrics.py', 'contracts.py', 'llm_metrics.py', 'llm_experiment.py')]
    value = hashlib.sha256()
    for path in sorted(paths):
        value.update(str(path.relative_to(ROOT)).replace('\\', '/').encode())
        value.update(path.read_bytes())
    return value.hexdigest()


def definitions_for(split):
    if split == 'smoke':
        definitions = json.loads((ROOT / 'eval/benchmark/definitions.json').read_text(encoding='utf-8'))
        ids = ['lookup-01', 'lookup-02', 'nearest-01', 'radius-02', 'attribute_filter-01', 'spatial_attribute-01', 'temporal-01', 'temporal-02', 'ranking-01', 'comparison-01', 'multi_step-01', 'multi_step-02', 'follow_up-01', 'follow_up-02', 'no_result-01', 'invalid_input-01']
        return [case for case in definitions if case['id'] in ids]
    path = ROOT / f'eval/benchmark_v2/{split}/definitions.json'
    if split == 'test':
        manifest = json.loads((ROOT / 'eval/benchmark_v2/freeze.json').read_text(encoding='utf-8'))
        if digest(path) != manifest['test_sha256'] or implementation_hash() != manifest['implementation_sha256']:
            raise ValueError('Frozen test or implementation changed; mark exposed and create a new holdout')
    return json.loads(path.read_text(encoding='utf-8'))


async def evaluate(args):
    if not all(load_model_env().values()):
        raise ValueError('Model configuration is incomplete')
    os.environ['LLM_EXTRA_BODY'] = '{"thinking":{"type":"disabled"}}'
    definitions = definitions_for(args.split)
    oracle = Oracle.database(os.environ['EVAL_DATABASE_URL'])
    if args.split == 'test':
        frozen = json.loads((ROOT / 'eval/benchmark_v2/freeze.json').read_text(encoding='utf-8'))
        snapshot = hashlib.sha256(json.dumps(oracle.fixture, sort_keys=True).encode()).hexdigest()
        if snapshot != frozen['database_snapshot_sha256'] or digest(ROOT / 'eval/benchmark/fixture.json') != frozen['fixture_sha256']:
            raise ValueError('Frozen database fixture changed')
    cases = materialize(oracle, definitions)
    target = ROOT / 'eval/reports/llm' / args.run_id
    target.mkdir(parents=True, exist_ok=True)
    metadata = {'benchmark_version': 'v2' if args.split != 'smoke' else 'development-smoke', 'split': args.split,
        'case_count': len(cases), 'category_counts': dict(Counter(case['category'] for case in cases)),
        'model': os.environ['LLM_MODEL'], 'temperature': 0, 'thinking': 'disabled', 'max_tokens': 4096,
        'benchmark_sha256': hashlib.sha256(json.dumps(definitions, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'fixture_sha256': digest(ROOT / 'eval/benchmark/fixture.json'), 'implementation_sha256': implementation_hash(),
        'reference_clock': '2026-06-01T12:00:00Z', 'database_version': oracle.database_version,
        'repeats': args.repeat, 'concurrency': args.concurrency, 'shuffle_seed': 20261007,
        'max_request_seconds': 30, 'max_transient_retries': 1, 'cost': None,
        'created_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
    meta_path = target / 'metadata.json'
    if meta_path.exists():
        old = json.loads(meta_path.read_text(encoding='utf-8'))
        if any(old[k] != metadata[k] for k in ('benchmark_sha256', 'implementation_sha256', 'model', 'repeats')):
            raise ValueError('Run cannot resume under changed configuration')
        metadata = old
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.split == 'test':
        exposure = ROOT / 'eval/benchmark_v2/exposure.json'
        if not exposure.exists():
            exposure.write_text(json.dumps({'first_formal_evaluation_started_at': metadata['created_at'], 'first_run_id': args.run_id,
                'implementation_sha256': metadata['implementation_sha256'], 'policy_zh': '不根据此 test 的结果调整后重用为 unseen；预先计划的相同冻结实现重复推理允许。'}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (target / 'ground-truth.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    journal = target / 'cases.jsonl'
    rows = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()] if journal.exists() else []
    done = {(row['repeat'], row['system'], row['id']) for row in rows}
    env = {**os.environ, 'EVAL_STORE': 'postgres', 'GIS_TOOLS_TOKEN': ''}
    process = subprocess.Popen([shutil.which('node'), str(ROOT / 'eval/start-api.js')], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    semaphore = asyncio.Semaphore(args.concurrency)
    try:
        api = process.stdout.readline().strip()
        if not api.startswith('http://127.0.0.1:'):
            raise RuntimeError('Isolated evaluation API did not start')
        async def one(repeat, system, case):
            if (repeat, system, case['id']) in done:
                return
            async with semaphore:
                tools = ToolClient(api, token='')
                runner = Agent(tools, HttpChatProvider()) if system == 'proposed_llm' else LLMOnly() if system == 'llm_only' else TextToSQL(os.environ['EVAL_DATABASE_URL']) if system == 'text_to_sql' else SingleStep()
                calls = []
                context_token = telemetry.set(calls)
                start = time.perf_counter()
                turn_results = []
                actual_prior = None
                setup_ok = True
                try:
                    # Multiple chronological turns use each system's own prior results.
                    turns = case.get('setup_turns') or ([{'query': case['setup_query'], 'constraints': case['setup_constraints']}] if case.get('setup_query') else [])
                    expected_prior = None
                    for turn in turns:
                        request = QueryRequest.model_validate({key: case[key] for key in ('query', 'location', 'reference_time')}).model_copy(update={'query': turn['query']})
                        turn_result = await asyncio.wait_for(runner.run(request, actual_prior) if isinstance(runner, Agent) else runner.run(request, actual_prior, tools), 30)
                        turn_results.append(turn_result)
                        expected = oracle.expected({**case, 'required_status': None, 'expected_constraints': turn['constraints']}, expected_prior)
                        expected_prior = expected['expected_hospital_ids']
                        if turn_result.get('status') != expected['expected_status'] or [h['hospital_id'] for h in turn_result.get('entities', [])] != expected_prior:
                            setup_ok = False
                        if turn_result.get('status') == 'ok' and turn_result.get('entities'):
                            actual_prior = turn_result['entities']
                    request = QueryRequest.model_validate({key: case[key] for key in ('query', 'location', 'reference_time')})
                    result = await asyncio.wait_for(runner.run(request, actual_prior) if isinstance(runner, Agent) else runner.run(request, actual_prior, tools), 30)
                    validate_result(result)
                except ValidationError:
                    result = failure('malformed_output' if calls else 'invalid_input', '输入或模型输出不符合 schema。')
                except asyncio.TimeoutError:
                    result = failure('timeout', '模型实验请求超时。')
                except AgentFailure as error:
                    result = failure(error.code, error.message)
                except Exception as error:
                    result = {**failure('baseline_execution_failure', '实验执行失败。'), 'error_class': type(error).__name__}
                finally:
                    telemetry.reset(context_token)
                # Keep generated SQL/choice even if its execution failed, without unsafe error text.
                if system == 'text_to_sql' and calls:
                    try:
                        result.setdefault('sql', json.loads(calls[-1].get('content', ''))['sql'])
                    except (ValueError, KeyError, TypeError):
                        pass
                metric = evaluate_case(case, result, oracle, system, calls)
                if not setup_ok:
                    metric['end_to_end_success_rate'] = False
                    metric['workflow_success_rate'] = False
                result = redact(result)
                count = sum('tool' in step for step in result.get('trace', []))
                setup_count = sum('tool' in step for turn in turn_results for step in turn.get('trace', []))
                usage = None if any(call['usage'] is None for call in calls) else {key: sum(call['usage'][key] for call in calls) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
                row = {'id': case['id'], 'query': case['query'], 'category': case['category'], 'repeat': repeat, 'system': system,
                    'metrics': metric, 'latency_ms': (time.perf_counter() - start) * 1000, 'tool_call_count': count,
                    'total_tool_call_count': count + setup_count, 'model_call_count': len(calls), 'retries': sum(call['attempt'] > 1 for call in calls),
                    'usage': usage, 'model_calls': calls, 'setup_results': turn_results, 'setup_correct': setup_ok, 'result': result,
                    'failure': classify(case, result, metric, oracle, system)}
                # A failed setup can make an otherwise correct main turn fail E2E.
                if row['failure'] and not setup_ok:
                    row['failure']['types'].append('wrong_follow_up_reference')
                with journal.open('a', encoding='utf-8') as output:
                    output.write(json.dumps(redact(row), ensure_ascii=False, allow_nan=False) + '\n')
                    output.flush()
                rows.append(row)
                if len(rows) % 20 == 0:
                    print(f"completed={len(rows)}/{len(cases)*len(SYSTEMS)*args.repeat}", flush=True)
        jobs = [(repeat, system, case) for repeat in range(1, args.repeat + 1) for case in cases for system in SYSTEMS]
        random.Random(20261007).shuffle(jobs)
        await asyncio.gather(*(one(*job) for job in jobs))
    finally:
        process.terminate()
        process.communicate(timeout=10)
    summary = {'metadata': metadata, 'systems': {}}
    for system in SYSTEMS:
        chosen = [row for row in rows if row['system'] == system]
        summary['systems'][system] = {'metrics': aggregate(chosen), 'by_category': {category: aggregate([row for row in chosen if row['category'] == category]) for category in metadata['category_counts']},
            'model_call_count': sum(row['model_call_count'] for row in chosen), 'retries': sum(row['retries'] for row in chosen),
            'severities': dict(Counter(row['failure']['severity'] for row in chosen if row['failure'])),
            'failure_types': dict(Counter(kind for row in chosen if row['failure'] for kind in row['failure']['types']))}
    (target / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for system, value in summary['systems'].items():
        print(system, value['metrics']['end_to_end_success_rate'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['smoke', 'validation', 'test'], required=True)
    parser.add_argument('--repeat', type=int, choices=[1, 3], default=1)
    parser.add_argument('--concurrency', type=int, choices=[1, 2, 4, 6], default=4)
    parser.add_argument('--run-id', required=True)
    try:
        asyncio.run(evaluate(parser.parse_args()))
    except Exception as error:
        print('Experiment stopped: ' + type(error).__name__, flush=True)
        raise SystemExit(1) from None
