# Agent design and implementation status

P2 introduces a separate Python FastAPI service and a schema-driven HTTP client for the existing Node GIS tools. `http_chat` accepts a configurable chat-completions-compatible endpoint and model; the provider emits only a validated semantic plan. The executor compiles the intent and constraints into a bounded workflow and calls real Node tools. It does not accept SQL, model-supplied coordinates instead of request coordinates, or model-supplied result facts.

`rules` is a limited bilingual zero-key demo, explicitly identified in responses. It is not evidence of LLM performance. `http_chat` is the default and reports missing configuration when no API key is supplied. Facts are rendered using deterministic templates, including sample counts, timestamp windows, source IDs and the distinction between severity categories and observed minutes.

Run from `agent-service`: `../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` (on Linux use `.venv/bin/python`). Export environment variables before startup; the example file is documentation and is not automatically loaded. The Node service must run at `GIS_API_URL`.

Implemented workflows cover lookup, nearest/radius search, temporal statistics, attribute filters, comparison, weighted ranking and ordinal follow-up. P2–P4 are locally validated; MCP and the independent deterministic benchmark are also implemented. See [validation](VALIDATION.md) for evidence and the exact unrun environments.

The Python suite has 27 passing tests, including real Node HTTP tools, actual MCP stdio protocol, mutated facts/scores/IDs, missing statistics, ordinal follow-up, timeouts, call limits, session expiry/conflicts, authorization, SSE ordering and mocked provider JSON/usage validation. Verification independently recomputes ranking from all candidate metrics and checks exact result provenance, spatial membership, filters, aggregate coverage and half-open evidence windows. Incomplete radius candidates cannot be presented as a complete answer.

Limits: 12 planned steps, 24 calls, 5s per tool, 30s overall, 500 sessions, 30-minute TTL and 20 successful turns. Location reuse expires after five minutes without preventing named/ordinal follow-up from querying fresh hospital facts. Python timestamps are normalized to milliseconds before Node calls to preserve identical evidence boundaries. Failed queries do not overwrite verified referents.

Sessions are single-process; multiple replicas need an external session store. Each tool has its own read-only database snapshot; cross-tool consistency under concurrent writes is a remaining limitation. Public deployment should keep FastAPI private or require `AGENT_API_TOKEN`, and apply operator quotas before enabling paid models. Map actions are generated only from verified entities and validated again in the browser. Neither stored browser facts nor model HTML are replayed.

The 120-case PostGIS rule benchmark tests software workflow correctness. Real `http_chat` semantic planning and all three model baselines remain unrun by the user's offline choice. No model capability or comparative performance is inferred from rule-mode success.
