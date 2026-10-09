# Executable spatial evaluation

## Implemented scope

`eval/` contains a fixed synthetic fixture (12 hospitals, 45 explicit observations), 120 bilingual query definitions in 13 categories, an independent oracle, a deterministic scorer, three model baseline adapters, and a CI workflow. The reference clock is `2026-06-01T12:00:00Z`.

| Category | Cases |
|---|---:|
| lookup | 10 |
| nearest | 10 |
| radius | 10 |
| attribute filter | 8 |
| spatial + attribute | 10 |
| temporal | 10 |
| ranking | 10 |
| comparison | 10 |
| multi-step | 12 |
| follow-up | 10 |
| ambiguous | 6 |
| no-result / unsatisfiable | 8 |
| invalid request input | 6 |

The fixture includes tied coordinates, multiple contributors, missing scores/waits, Unknown queue categories, duplicate partial names, a report exactly at each temporal boundary, and an instruction-like cleanliness note. These are synthetic observations, not measurements of real hospitals.

## Independent ground truth

`oracle.py` imports no agent/tool/domain/verifier/map implementation. In PostGIS mode it reads raw hospitals, reports and queue categories through a read-only connection, asks PostGIS directly for spheroidal distances, and independently aggregates raw observations and computes the documented ranking formula. Generated `benchmark/cases.json` records expected calls/arguments, constraints, entities, statistics, map actions, status and source. `definitions.json` retains authored expectations separately from computed status; recomputing materialized ground truth is tested for idempotence.

`generate_cases.py` rebuilds the source fixture and definitions. `load_fixture.py` only resets records in a database named **queuelens_eval**. `bootstrap_db.py` requires a separate **queuelens_test** source database and provisions a reader without write/admin privileges. No production connection is supported by this harness.

## Metrics and denominators

All rates report passed/total, not just percentages. No LLM judge is used.

| Metric | Deterministic definition |
|---|---|
| Tool Selection Accuracy | Main-turn tool sequence matches an accepted executable workflow; name resolver alone may replace a redundant detail call |
| Tool Argument Accuracy | Tool arguments match an accepted workflow, with timestamp normalization and numeric tolerance |
| Execution Success Rate | Final status matches the expected successful or safely handled negative outcome |
| Constraint Satisfaction Rate | Expected outcome, ordered IDs and requested-window statistics match independent ground truth |
| Final Entity Accuracy | Expected status and ordered hospital IDs match |
| Answer Groundedness | Every supplied entity/statistic fact matches raw-record truth; prose matches the independently reconstructed closed answer template |
| Map Action Accuracy | Full action sequence, action types and ordered IDs match the declared map policy |
| End-to-End Success Rate | All applicable checks pass, including correct setup ranking for follow-ups |
| Latency | Core agent/baseline wall time plus actual Express HTTP requests; follow-up setup is included |
| Tool Call Count | Main and follow-up setup calls both included; catalog fetches are excluded |

LLM-only and Text-to-SQL tool-selection/argument rates are **N/A**, since they do not select GIS tools. Provider token counts are recorded when supplied; unavailable usage and unconfigured monetary prices remain null. SQL selection/projection query counts are separate from GIS calls. Percentiles use nearest indexed observations, with the indexing rule in `metrics.py`.

Answer Groundedness is a **closed-format factual check**, not a general-purpose free-text entailment score. Unsupported prose/malformed output fails the contract and must not automatically be interpreted as a clinical hallucination. Intentional refusal/validation/no-result cases count toward the 120-case total; category reports show their effect.

## Baselines

| System | Actual implementation | Current experiment status |
|---|---|---|
| A: LLM only | Query/context to configurable model; no GIS/SQL access | Not run, per user choice |
| B: Text-to-SQL | Model selects/orders IDs with generated SELECT; isolated reader; fixed SQL projection formats selected facts | Not run, per user choice |
| C: Single-step tool calling | Model chooses exactly one catalog tool; no explicit workflow plan or verifier | Not run, per user choice |
| Proposed with LLM | Semantic PlanSpec → bounded GIS workflow → deterministic verification → answer/actions | Not run, per user choice |
| Proposed rules smoke test | Explicit limited regex planner exercises the production workflow | Executed locally |
| Single-step rules smoke test | Same limited semantic vocabulary, one tool, no workflow/verification | Executed locally |

The two rule-mode results are regression evidence for software orchestration. They are **not** an LLM baseline comparison or evidence of semantic generalization. Queries are generated from known templates; real-model evaluation, unseen paraphrases and external data remain outstanding experiments. No proposed-system winner is assumed.

Text-to-SQL rejects multi-statement SQL, non-SELECT AST nodes, CTEs, SELECT INTO, locks, non-allowlisted tables/types/operators/functions, privileged/write-capable roles and non-evaluation databases. It additionally uses read-only transactions, 3-second statement timeout, 1-second lock timeout and a 200-row cap. See [pglast's AST API](https://pglast.readthedocs.io/en/latest/usage.html). Fixed projection after generated selection uses no semantic filtering/ranking/verification and is disclosed as part of Baseline B's cost.

## Reproduce

Install Node dependencies and `python -m pip install -r requirements.lock.txt` in a Python 3.12 virtual environment. Lock files record the tested local dependency versions.

```bash
python eval/generate_cases.py
python eval/evaluator.py --store memory --system proposed_rules --system single_step_rules --require-smoke-pass --output eval/reports/run-memory.json
```

For real PostGIS, export `TEST_DATABASE_URL` (queuelens_test), `EVAL_ADMIN_DATABASE_URL` (queuelens_eval), `EVAL_READER_PASSWORD`, and `EVAL_DATABASE_URL` (the resulting reader connection), then:

```bash
node scripts/migrate.js
node scripts/verify-migrations.js
python eval/bootstrap_db.py
python -m pytest eval/tests -q
python eval/evaluator.py --store postgres --write-ground-truth --require-smoke-pass --output eval/reports/run-postgis.json
```

The default evaluator records unconfigured model systems as `not_run`. To run actual model experiments, explicitly configure `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` and select `--system proposed_llm`, `--system llm_only`, `--system text_to_sql` and `--system single_step`. The Python service does not automatically load `.env`; export variables in the calling process. Never use production credentials for Text-to-SQL.

The CI job runs PostGIS 16/3.4, migration checks, existing WebGIS tests, Python/MCP tests, SQL isolation tests and the rule workflow benchmark; it uploads `run-ci.json`. The workflow has been configured locally; no remote GitHub Actions run or production deployment has been claimed.

Actual local outputs and limitations are recorded in [validation](VALIDATION.md), [results](../eval/reports/RESULTS.md) and [failure analysis](FAILURE_ANALYSIS.md).

## 本阶段真实模型评测更新

既有120条仅称Development / Regression Benchmark。本阶段新增60条validation和180条冻结test，四个真实deepseek-flash系统各跑三次。公共任务默认语义、温度、时钟、fixture、超时和shuffle固定；A/B/C的权限和接口限制明确单列，不能把其差异全部归因模型能力。PlanSpec复用为Typed Spatial IR，单独报告槽位提取，不额外只对D增加E2E门槛。

模型变量在本地agent-service/.env加载，环境文件必须忽略；EVAL_DATABASE_URL需显式设置为隔离非特权reader。真实运行和独立真值在第一次test前冻结；test结果没有用于修改prompt/评分。配置与复现命令、计量定义、三轮一致性与限制见[中文实验报告](../eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md)和[benchmark v2](../eval/benchmark_v2/README.md)。未来根据这些结果修复须使用新holdout。

validation发现复合no_result的oracle路径错误，在test冻结前修复并单独重新计分；原始模型输出与初始失败不删除。正式test日志、模型response、SQL、tool trace、usage和失败分类全部保存，不选最好轮次。
