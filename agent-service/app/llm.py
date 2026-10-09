"""Shared bounded model transport; telemetry never retains headers, keys or URLs."""
import asyncio
import json
import os
import time
from contextvars import ContextVar
import httpx
from .config import load_model_env
from .schemas import AgentFailure

telemetry = ContextVar('model_telemetry', default=None)


def redact(value):
    key = os.getenv('LLM_API_KEY', '')
    if isinstance(value, str):
        return value.replace(key, '[REDACTED]') if key else value
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k.lower() not in ('authorization', 'api_key', 'llm_api_key')}
    return value


async def completion(prompt, payload):
    configured = {key: bool(os.getenv(key, '').strip()) for key in ('LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY')}
    if not all(configured.values()):
        raise AgentFailure('provider_not_configured', 'Model configuration is incomplete')
    records = telemetry.get()
    body = {'model': os.environ['LLM_MODEL'], 'temperature': 0, 'max_tokens': 4096,
        'response_format': {'type': 'json_object'}, 'messages': [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]}
    # Provider-specific extensions are configured, not hard-coded to a vendor.
    extra = json.loads(os.getenv('LLM_EXTRA_BODY', '{}'))
    if not isinstance(extra, dict) or set(extra) - {'thinking', 'reasoning_effort'}:
        raise AgentFailure('provider_not_configured', 'Unsupported provider extension')
    body.update(extra)
    for attempt in range(2):  # At most one transient retry; outer request deadline remains 30s.
        entry = {'attempt': attempt + 1, 'model': body['model'], 'status': 'started', 'usage': None}
        if records is not None:
            records.append(entry)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                response = await client.post(os.environ['LLM_BASE_URL'].rstrip('/') + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + os.environ['LLM_API_KEY']}, json=body)
            entry['http_status'] = response.status_code
            if response.status_code in (429, 502, 503, 504) and attempt == 0:
                entry['status'] = 'transient_http_failure'
                await asyncio.sleep(.5)
                continue
            if response.status_code >= 400:
                entry['status'] = 'http_failure'
                raise AgentFailure('provider_http_failure', f'Model HTTP status {response.status_code}')
            data = response.json()
            choice = data['choices'][0]
            content = choice['message']['content']
            entry.update(status='ok', response_model=data.get('model'), finish_reason=choice.get('finish_reason'), content=redact(content))
            usage = data.get('usage')
            if isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens')):
                entry['usage'] = {k: usage[k] for k in ('prompt_tokens', 'completion_tokens')}
                entry['usage']['total_tokens'] = usage.get('total_tokens', sum(entry['usage'].values()))
            if choice.get('finish_reason') == 'length':
                raise AgentFailure('malformed_output', 'Model output exceeded token limit')
            return content, entry['usage']
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            entry['status'] = 'transport_failure'
            if attempt == 0:
                await asyncio.sleep(.5)
                continue
            raise AgentFailure('provider_transport_failure', type(error).__name__) from None
        except (ValueError, KeyError, IndexError, TypeError):
            entry['status'] = 'malformed_output'
            raise AgentFailure('intent_parsing_failure', 'Provider returned malformed JSON response') from None
        except asyncio.CancelledError:
            entry['status'] = 'cancelled'
            raise
        finally:
            entry['latency_ms'] = (time.perf_counter() - started) * 1000
