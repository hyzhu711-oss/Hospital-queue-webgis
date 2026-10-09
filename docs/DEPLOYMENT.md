# Deployment and reproduction

## Existing WebGIS

Node 20+ and the existing start command still run the demo with no AI configuration:

```bash
npm ci
npm start
```

The original `docker-compose.yml` and `render.yaml` remain the WebGIS deployment path. Memory changes last for that process; persistent deployment uses PostgreSQL/PostGIS. Set `DATA_SOURCE=postgres`, `DATABASE_URL`, and the appropriate `DATABASE_SSL` value. Migrate before starting. Migration 003 adds nullable observations and an indexed geography expression; the ledger prevents re-running seeds on an established legacy schema.

The upgrade has **not** been deployed to the public Render/Supabase demo. Fresh/repeated/legacy migrations have been exercised against isolated local databases, not production. Existing `DATABASE_SSL=true` inherits the legacy driver's certificate handling; configure managed certificate verification for a hardened deployment.

## Optional Agent service

Use Python 3.12. Install `agent-service/requirements.lock.txt` for runtime, or root `requirements.lock.txt` for tests/MCP/evaluation.

本阶段配置更新：应用选择`http_chat`时，从本地`agent-service/.env`补充未设置的LLM_BASE_URL、LLM_MODEL、LLM_API_KEY和可选LLM_EXTRA_BODY；已有进程环境变量优先。其他数据库/服务变量仍需显式设置，不从模型配置文件自动导入。`rules`和单元测试不自动加载真实模型密钥。所有`.env`必须留在Git忽略规则内。

```bash
cd agent-service
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Set Node's `AGENT_SERVICE_URL=http://127.0.0.1:8000`, then restart Node. Both browser pages receive the optional panel. Browser calls stay same-origin through `/api/agent/query` and `/api/agent/query/stream`; provider and service tokens remain server-side.

| Variable | Service | Purpose |
|---|---|---|
| GIS_API_URL | Python/MCP | Trusted Express base URL |
| GIS_TOOLS_TOKEN | Express + Python/MCP | Matching optional tool Bearer token |
| AGENT_SERVICE_URL | Node | Trusted FastAPI base URL; unset disables panel |
| AGENT_API_TOKEN | Node + Python | Matching service Bearer token |
| PLANNER_PROVIDER | Python | `http_chat` (default), or explicitly labelled `rules` demo |
| LLM_BASE_URL / LLM_MODEL / LLM_API_KEY | Python | Configurable compatible chat model endpoint |
| EVAL_MODE | Python | `false` in application deployment; fixed clocks are eval-only |

Unconfigured `http_chat` returns `provider_not_configured`. A zero-key demo must explicitly set `PLANNER_PROVIDER=rules`; the response says it did not call an LLM. No silent provider fallback is implemented.

## Docker overlay

```bash
docker compose -f docker-compose.yml -f docker-compose.agent.yml --profile agent up --build
```

This adds an internal Python service and enables Node's proxy. Set provider/token variables in the Compose environment. `PLANNER_PROVIDER=rules` is available for a labelled demo. The new service is not separately exposed on a host port. The base Compose path remains usable independently.

The Agent Dockerfile uses its exact runtime lock and copies the shared map contract. `.dockerignore` excludes local databases, downloaded tooling, virtual environments and environment secrets. Docker builds were not run locally because this workstation has no Docker runtime; do not describe this as a validated container deployment.

## Render

Retain the existing Node Blueprint. Host the Python service separately with `agent-service` as the working directory, install its runtime lock, and start `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set reciprocal trusted URLs and matching tokens. Set the Node service's Agent URL only after Python's `/health` is ready. No new Render services were created during this work.

## Operating limits

Current sessions live in one Python process (500 sessions, 30-minute TTL, 20 successful turns). Use a single worker or sticky routing until shared storage is implemented. Location reuse expires after five minutes. Requests cap planning at 12 steps, calls at 24, each HTTP tool at five seconds, Python execution at 30 seconds and proxy at 35 seconds.

Before a public paid-model launch, configure service authentication, trusted reverse-proxy behavior, request/user quotas and provider budgets. These deployment controls are operator responsibilities; per-request execution bounds do not provide an account-wide spending quota.

See [MCP](MCP.md) for local external-agent access and [evaluation](EVALUATION.md) for isolated benchmark reproduction.
