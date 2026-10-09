> 历史说明：以下为本阶段前的确定性回归/失败记录，保留当时状态；其中“模型未运行”不是当前状态。最新真实模型实验与中文分析见[FAILURE_ANALYSIS_ZH.md](FAILURE_ANALYSIS_ZH.md)。旧延迟为当时测量，最新规则JSON另存regression-final.json，不混入模型结果。

# Failure analysis

This document distinguishes observed implementation defects, injected regression faults, rule-baseline limitations and model failure categories that have not yet been observed. No real-model failure rates are fabricated.

## Taxonomy

| Category | Detection/handling | Representative evidence |
|---|---|---|
| Intent parsing failure | Strict PlanSpec rejects malformed model JSON | Mocked invalid HTTP JSON, missing choices and model-supplied fact fields rejected; real-model frequency unmeasured |
| Wrong tool selection | Catalog allowlist; no arbitrary SQL/write tool | MCP `execute_sql` rejection test |
| Wrong argument extraction | Pydantic/Ajv/range/explicit-threshold checks | Invalid coordinates, weights and score tests |
| Wrong temporal window | Explicit clock/duration and evidence boundaries | Real submillisecond mismatch; aggregate date mutation |
| Wrong spatial constraint | Radius anchor, PostGIS membership and candidate verification | Radius/invalid-position tests |
| Missing/unsupported tool | Explicit unsupported result | Routing/polygon/emergency requests remain unsupported |
| Tool execution failure | Timeout, HTTP failure, structured error trace | Injected slow tool test; isolated SQL rejection |
| Empty-result handling failure | No entities/actions; null metrics not guessed | Tiny-radius, missing-name, missing-score cases |
| Reference resolution failure | Verified prior order, TTL and bounds | Invalid second result in actual browser; follow-up tests |
| Verification failure | Source identity, complete statistics and global ranking checks | Injected ID, score, missing-statistic and date mutations |
| Answer grounding failure | Deterministic renderer + independent closed-template scoring | Mutated distance/prose scorer tests |
| Map-action failure | Shared schema and final-ID membership | Invalid ID/unsupported command/atomic-batch tests |
| Agent loop / unnecessary calls | 12 steps, 24 calls and deadlines | Call-limit test; explicit one-tool baseline comparison |

## Observed case 1: live timestamp precision

An actual Cesium comparison request returned `verification_failure: Evidence window mismatch`. Python's live clock supplied six decimal places of fractional seconds; Node serialized the same boundary to milliseconds. The deterministic verifier correctly refused a mismatched boundary, but the workflow had not standardized precision.

Repair: truncate the execution clock to milliseconds before constructing either window bound. Regression: `test_submillisecond_clock_shares_node_boundaries`. Browser re-run returned the two expected hospitals, zero current-window reports (the demo seed is historical), and real Cesium highlights/flyTo. It did not invent fresh data. Screenshot: `docs/screenshots/agent-cesium.jpg`.

## Observed case 2: stale browser result replay

Code review found sessionStorage replaying prior factual answers/map actions on navigation. Schema checks could validate IDs while the underlying facts were stale or client-edited. Repair: retain only the opaque session ID; facts/actions are queried again. Location reuse expires after five minutes and named follow-ups do not renew a stale location. Regression: `test_stale_location_is_not_extended_by_followup`; browser navigation starts with a fresh answer panel.

## Observed case 3: oracle floating-point cancellation

The first memory-mode run scored nearest-06 incorrectly because the oracle subtracted independently rounded radians while the store converted source degree differences. At a near-equidistant north/south boundary, this changed sub-micrometre ordering. The initial report was 119/120; this was a reference numeric implementation discrepancy, not a fabricated model failure.

Repair: compute the independent Haversine angular deltas from source degree differences. Production ground truth uses direct PostGIS spheroid distances. Co-located exact ties are explicitly tested and break by hospital ID. No production radius or distance value is modified to improve a score.

## Observed case 4: derived status reused as an oracle constraint

Adding setup correctness to the evaluator exposed a scorer defect: a materialized `expected_status` suppressed recomputation of a ranking in follow-up setup. An intermediate run showed 110/120 despite correct main-turn facts. Repair: separate authored `required_status` from computed `expected_status`, and test that re-materializing canonical ground truth is idempotent. This is an evaluation bug, not an agent success claim; only reports regenerated after the repair are presented as current results.

## Rule single-step limitations

The actual PostGIS one-tool rules smoke run passes 50/120 overall. It can return grounded nearest/radius/name facts, but one call cannot generally combine name resolution with temporal aggregation, candidate discovery with filtering/ranking, or produce a correct prior recommendation for follow-ups. Grounded individual facts therefore coexist with failed task constraints. These failures are reported by category in the JSON report.

This result is not Baseline C's LLM performance: the real model-selected tool baseline has not run. It only checks the software consequences of the stated one-tool restriction over known query templates.

## Provider response regression checks

Final review found HTTP response JSON decoding outside the provider's planning validation handler. Invalid response JSON could be classified as a generic execution failure, and a reused provider could retain old token usage after failure. Parsing now occurs inside the strict plan handler; malformed responses return `intent_parsing_failure`, usage resets for each plan, and only nonnegative integer usage counters are retained. Mock transport tests cover a valid semantic plan, non-JSON HTTP body, missing choices and a forbidden model-supplied `distance_m` fact. These are injected fixtures, not observed live-model failures or a prompt-injection resistance measurement.

## Remaining experimental gaps

Real-model parsing, prompt-injection resistance, unseen paraphrases, provider outages and cost distributions remain unmeasured. Tool boundaries prevent arbitrary SQL/writes even if a semantic plan is wrong, but they do not prove the model understood every query. The verifier checks declared filters and supported explicit anchors; arbitrary semantic omissions cannot all be determined by a numeric checker.

Separate gaps include external map tiles/location permissions, multi-instance session consistency, cross-tool data changes, live hospital observation quality, remote CI/container execution and production rollout. See [validation](VALIDATION.md) and [evaluation](EVALUATION.md) for the exact tested scope.
