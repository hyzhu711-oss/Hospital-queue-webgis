import json
import httpx
import pytest
from app.providers import HttpChatProvider
from app.schemas import AgentFailure


def configure(monkeypatch, response):
    monkeypatch.setenv('LLM_BASE_URL', 'https://provider.invalid/v1')
    monkeypatch.setenv('LLM_MODEL', 'fixture-model')
    monkeypatch.setenv('LLM_API_KEY', 'fixture-secret')
    original = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return response

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return requests


@pytest.mark.asyncio
async def test_provider_validated_plan_and_usage(monkeypatch):
    requests = configure(monkeypatch, httpx.Response(200, json={'choices': [{'message': {'content': '{"intent":"nearest"}'}}], 'usage': {'prompt_tokens': 17, 'completion_tokens': 8, 'total_tokens': 25}}))
    provider = HttpChatProvider()
    plan = await provider.plan('nearest hospital', {'location': {'latitude': 51.5, 'longitude': -.13}}, {'tools': []})
    assert plan.intent == 'nearest'
    assert provider.last_usage == {'prompt_tokens': 17, 'completion_tokens': 8}
    assert len(requests) == 1 and str(requests[0].url) == 'https://provider.invalid/v1/chat/completions'
    payload = json.loads(requests[0].content)
    assert payload['model'] == 'fixture-model' and payload['response_format'] == {'type': 'json_object'}
    assert payload['messages'][0]['role'] == 'system' and payload['messages'][1]['role'] == 'user'


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [
    httpx.Response(200, text='not JSON'),
    httpx.Response(200, json={'choices': []}),
    httpx.Response(200, json={'choices': [{'message': {'content': '{"intent":"nearest","distance_m":42}'}}]}),
])
async def test_provider_malformed_or_factual_plan_rejected(monkeypatch, response):
    configure(monkeypatch, response)
    provider = HttpChatProvider()
    provider.last_usage = {'prompt_tokens': 99, 'completion_tokens': 99}
    with pytest.raises(AgentFailure) as error:
        await provider.plan('nearest hospital', {}, {})
    assert error.value.code == 'intent_parsing_failure'
    assert provider.last_usage is None
