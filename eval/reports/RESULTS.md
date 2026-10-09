> 历史说明：以下为本阶段前的确定性回归/失败记录，保留当时状态；其中“模型未运行”不是当前状态。最新真实模型实验与中文分析见[LLM_EXPERIMENT_RESULTS_ZH.md](LLM_EXPERIMENT_RESULTS_ZH.md)。旧延迟为当时测量，最新规则JSON另存regression-final.json，不混入模型结果。

# Observed deterministic evaluation results

Local Windows run on 2026-10-07. These are **rule-template workflow regression results**, not LLM reasoning measurements. The user selected offline evaluation; no model request was sent.

PostGIS database version: `{"postgres": "16.15", "postgis": "3.6.2"}`.
Reference clock: `2026-06-01T12:00:00Z`; 12 synthetic hospitals, 45 observations, 120 cases in 13 categories.
Fixture SHA-256: `6ffd1b4737e2f2d6258d161e07a3f8fe7c83a1925baca491fdc5b3ffac7f3b88`.
Raw database snapshot SHA-256: `78ad896d62cb4f31f8d5a5545e4cb40c43368d73d523e72fe01da38de9a4194f`.

## End-to-end results

| Store | System | Passed | Rate | Mean latency (ms) | p95 (ms) | Tool calls |
|---|---|---:|---:|---:|---:|---:|
| postgis | proposed_rules | 120/120 | 100.00% | 506.40 | 975.65 | 251 |
| postgis | single_step_rules | 50/120 | 41.67% | 329.59 | 647.52 | 121 |
| memory | proposed_rules | 120/120 | 100.00% | 504.05 | 972.87 | 251 |
| memory | single_step_rules | 50/120 | 41.67% | 330.14 | 644.26 | 121 |

Latency is a local measurement taken alongside other validation work, includes follow-up setup requests, and is not a controlled performance comparison or production capacity estimate. There were no repeated timing trials. Call counts include follow-up setup but exclude catalog fetches. Each setup or main request has its own 30-second evaluation timeout. Both rule systems consumed zero model tokens; monetary cost is unavailable (`null`), not inferred.

## PostGIS metrics

| Metric | Proposed rules | Single-step rules |
|---|---:|---:|
| tool_selection_accuracy | 120/120 (100.00%) | 50/120 (41.67%) |
| tool_argument_accuracy | 120/120 (100.00%) | 50/120 (41.67%) |
| execution_success_rate | 120/120 (100.00%) | 117/120 (97.50%) |
| constraint_satisfaction_rate | 120/120 (100.00%) | 50/120 (41.67%) |
| final_entity_accuracy | 120/120 (100.00%) | 66/120 (55.00%) |
| answer_groundedness | 120/120 (100.00%) | 120/120 (100.00%) |
| map_action_accuracy | 120/120 (100.00%) | 66/120 (55.00%) |
| end_to_end_success_rate | 120/120 (100.00%) | 50/120 (41.67%) |

`answer_groundedness` verifies the closed factual output contract. A grounded response can still miss a requested filter or operation; therefore the single-step rule system can have 120/120 grounded answers and only 50/120 end-to-end successes. This metric is not a general semantic judge. Execution success measures expected status, including correctly rejected or empty requests; it does not mean every case returns hospitals.

## By category (PostGIS)

| Category | Cases | Proposed rules | Single-step rules |
|---|---:|---:|---:|
| lookup | 10 | 10/10 | 10/10 |
| nearest | 10 | 10/10 | 10/10 |
| radius | 10 | 10/10 | 10/10 |
| attribute_filter | 8 | 8/8 | 0/8 |
| spatial_attribute | 10 | 10/10 | 0/10 |
| temporal | 10 | 10/10 | 0/10 |
| ranking | 10 | 10/10 | 0/10 |
| comparison | 10 | 10/10 | 0/10 |
| multi_step | 12 | 12/12 | 0/12 |
| follow_up | 10 | 10/10 | 0/10 |
| ambiguous | 6 | 6/6 | 6/6 |
| no_result | 8 | 8/8 | 8/8 |
| invalid_input | 6 | 6/6 | 6/6 |

## Model experiments

| System | Status |
|---|---|
| llm_only | Not run: user-selected offline evaluation |
| text_to_sql | Not run: user-selected offline evaluation |
| single_step | Not run: user-selected offline evaluation |
| proposed_llm | Not run: user-selected offline evaluation |

All four model adapters are implemented. No conclusion about their comparative accuracy, hallucination, token cost or latency is available. Proposed is not assumed to outperform the baselines in those experiments.

## Reproduction and evidence

- [PostGIS report with all case results and tool evidence](postgis-smoke.json)
- [Memory report](memory-smoke.json)
- [Actual multistep trace](../../docs/EXAMPLE_TRACE.json)
- [Definitions, isolated database setup and scoring](../../docs/EVALUATION.md)
- [Validation scope and unrun environments](../../docs/VALIDATION.md)
- [Observed failures and limitations](../../docs/FAILURE_ANALYSIS.md)

The independent oracle reads raw observations and PostGIS distances rather than calling production tool/domain implementations. The fixture has been used during development and is not an unseen-language holdout. Remote GitHub Actions, Linux container builds and production deployment have not been run.
