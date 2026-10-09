import json
import httpx
import pytest
from app.config import load_model_env
from app.llm import completion, telemetry, redact
from app.schemas import AgentFailure


def client_fixture(monkeypatch, responses):
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.invalid/v1')
    monkeypatch.setenv('LLM_MODEL', 'fixture-model')
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-placeholder')
    monkeypatch.setenv('LLM_EXTRA_BODY', '{}')
    original = httpx.AsyncClient
    requests = []
    def handler(request):
        requests.append(request)
        return responses[min(len(requests)-1, len(responses)-1)]
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return requests


@pytest.mark.asyncio
async def test_transient_retry_is_bounded_and_usage_recorded(monkeypatch):
    requests = client_fixture(monkeypatch, [httpx.Response(503), httpx.Response(200, json={'model': 'fixture-model', 'choices': [{'message': {'content': '{"intent":"nearest"}'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 4, 'total_tokens': 14}})])
    calls = []
    token = telemetry.set(calls)
    try:
        content, usage = await completion('Return JSON.', {})
    finally:
        telemetry.reset(token)
    assert len(requests) == 2 and calls[1]['attempt'] == 2
    assert json.loads(content)['intent'] == 'nearest' and usage['total_tokens'] == 14
    assert 'synthetic-placeholder' not in json.dumps(calls)


@pytest.mark.asyncio
async def test_terminal_failure_does_not_retry_or_log_body(monkeypatch):
    requests = client_fixture(monkeypatch, [httpx.Response(401, json={'error': 'synthetic-placeholder'})])
    calls = []
    token = telemetry.set(calls)
    try:
        with pytest.raises(AgentFailure) as error:
            await completion('Return JSON.', {})
    finally:
        telemetry.reset(token)
    assert error.value.code == 'provider_http_failure' and len(requests) == 1
    assert 'synthetic-placeholder' not in json.dumps(calls)


@pytest.mark.asyncio
async def test_truncated_response_is_rejected(monkeypatch):
    client_fixture(monkeypatch, [httpx.Response(200, json={'choices': [{'message': {'content': '{"intent":'}, 'finish_reason': 'length'}]})])
    with pytest.raises(AgentFailure) as error:
        await completion('Return JSON.', {})
    assert error.value.code == 'malformed_output'


def test_local_config_loads_only_model_keys_and_redacts(monkeypatch, tmp_path):
    for key in ('LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / '.env'
    path.write_text('LLM_BASE_URL=https://provider.invalid/v1\nLLM_MODEL=fixture-model\nLLM_API_KEY=synthetic-placeholder\nUNRELATED_SETTING=forbidden\n')
    assert all(load_model_env(path).values())
    assert 'UNRELATED_SETTING' not in __import__('os').environ
    assert redact({'message': 'synthetic-placeholder', 'api_key': 'synthetic-placeholder'}) == {'message': '[REDACTED]'}
