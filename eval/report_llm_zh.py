"""Analysis only: never edits frozen cases, prompts, execution or inference logs."""
import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'eval/reports/llm/test-frozen-r1-r3'
SYSTEMS = ('llm_only', 'text_to_sql', 'single_step', 'proposed_llm')
LABELS = {'llm_only': 'LLM Only', 'text_to_sql': 'Text-to-SQL', 'single_step': 'Single-Step', 'proposed_llm': 'Proposed'}
TAXONOMY = ('intent_parsing_failure', 'wrong_tool_selection', 'wrong_arguments', 'spatial_constraint_error',
    'temporal_constraint_error', 'missing_filter', 'wrong_ranking_objective', 'wrong_follow_up_reference',
    'SQL_generation_failure', 'schema_hallucination', 'tool_execution_failure', 'timeout', 'malformed_structured_output',
    'verification_failure', 'verifier_missed_error', 'hallucinated_factual_answer', 'map_action_mismatch',
    'unnecessary_tool_calls', 'agent_loop', 'empty_result_handling_failure', 'ambiguity_handling_failure')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rate(rows, key):
    values = [row['metrics'][key] for row in rows if row['metrics'].get(key) is not None]
    return sum(values)/len(values) if values else None


def pct(value):
    return 'N/A' if value is None else f'{value*100:.2f}%'


def wilson(passed, total):
    z = 1.96
    p = passed/total
    center = (p+z*z/(2*total))/(1+z*z/total)
    margin = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/(1+z*z/total)
    return [max(0, center-margin), min(1, center+margin)]


def plan_signature(row):
    if row['system'] != 'proposed_llm':
        return None
    plan = row['result'].get('plan')
    if not plan and row['model_calls']:
        try:
            plan = json.loads(row['model_calls'][-1].get('content', ''))
        except (ValueError, TypeError):
            return None
    if not plan:
        return None
    import sys
    sys.path.insert(0, str(ROOT / 'agent-service'))
    from app.schemas import PlanSpec
    try:
        plan = PlanSpec.model_validate(plan).model_dump()
    except ValueError:
        return None
    return json.dumps(plan, sort_keys=True)


def analyze(rows):
    result = {}
    for system in SYSTEMS:
        chosen = [row for row in rows if row['system'] == system]
        grouped = {case_id: sorted([row for row in chosen if row['id'] == case_id], key=lambda row: row['repeat']) for case_id in {row['id'] for row in chosen}}
        rates = [rate([row for row in chosen if row['repeat'] == repeat], 'end_to_end_success_rate') for repeat in (1,2,3)]
        first = [row for row in chosen if row['repeat'] == 1]
        stable = 0
        identical_plans = 0
        eligible_plans = 0
        recurrences = Counter()
        for group in grouped.values():
            assert len(group) == 3
            recurrences[sum(not row['metrics']['end_to_end_success_rate'] for row in group)] += 1
            signatures = [json.dumps({key: row['result'].get(key) for key in ('status','entities','statistics','map_actions')}, sort_keys=True) for row in group]
            stable += len(set(signatures)) == 1
            plans = [plan_signature(row) for row in group]
            if all(plan is not None for plan in plans):
                eligible_plans += 1
                identical_plans += len(set(plans)) == 1
        failures = [row for row in chosen if row['failure']]
        calls = [call for row in chosen for call in row['model_calls']]
        known = [call['usage'] for call in calls if call['usage']]
        metrics = {key: rate(chosen, key) for key in chosen[0]['metrics']}
        latencies = sorted(row['latency_ms'] for row in chosen)
        result[system] = {'rows': len(chosen), 'metrics': metrics, 'pass_at_1': rate(first, 'end_to_end_success_rate'),
            'round_rates': rates, 'mean_success_rate': statistics.mean(rates), 'sample_standard_deviation': statistics.stdev(rates),
            'first_run_wilson_interval': wilson(sum(row['metrics']['end_to_end_success_rate'] for row in first), len(first)),
            'consistency_rate': stable/len(grouped), 'identical_plan_rate': identical_plans/eligible_plans if eligible_plans else None,
            'identical_plan_denominator': eligible_plans, 'failure_recurrence': dict(recurrences), 'total_failures': len(failures),
            'severity_distribution': dict(Counter(row['failure']['severity'] for row in failures)),
            'failure_types': dict(Counter(kind for row in failures for kind in row['failure']['types'])),
            'severe_error_rate': sum(row['failure']['severe'] for row in failures)/len(chosen),
            'fabricated_fact_rate': sum(row['failure']['severity']=='S4' for row in failures)/len(chosen),
            'recoverable_failures': sum(row['failure']['recoverable'] for row in failures),
            'verifier_caught': sum(row['failure']['verifier_caught'] for row in failures),
            'verifier_missed': sum(row['failure']['verifier_missed'] for row in failures),
            'latency_ms': {'mean': statistics.mean(latencies), 'p50': latencies[int((len(latencies)-1)*.5)], 'p95': latencies[int((len(latencies)-1)*.95)]},
            'model_calls': len(calls), 'retries': sum(row['retries'] for row in chosen),
            'tool_calls': sum(row['total_tool_call_count'] for row in chosen), 'usage_coverage': len(known)/len(calls) if calls else None,
            'known_input_tokens': sum(usage['prompt_tokens'] for usage in known), 'known_output_tokens': sum(usage['completion_tokens'] for usage in known),
            'known_total_tokens': sum(usage['total_tokens'] for usage in known), 'cost': None,
            'positive_case_success': rate([row for row in chosen if CASES[row['id']]['expected_status']=='ok'], 'end_to_end_success_rate'),
            'negative_case_success': rate([row for row in chosen if CASES[row['id']]['expected_status']!='ok'], 'end_to_end_success_rate')}
    return result


def write_reports(rows, summary, manifest, metadata):
    lines = ['# QueueLens 真实模型实验结果', '',
        '## 实验设计与边界', '',
        '研究问题：在相对于开发与 validation 未见的自然语言空间查询上，Plan–Execute–Verify 是否比三组受限 baseline 更可靠地完成理解、执行和返回？', '',
        '本实验使用同一个 deepseek-flash、相同合成 fixture、相同冻结 test、相同参考时钟。temperature=0，thinking=disabled，单次输出上限4096 tokens；请求/前置会话各30秒，临时故障最多重试一次，不针对失败问题自修复或调参。正式 test 在冻结后进行了四系统各三次独立 HTTP 推理，共2160条系统-问题-轮次结果。', '',
        '四系统能力不同：A 无 GIS/数据库；B 生成一个受限 SELECT，执行后以固定 SQL 投影返回事实；C 只允许一个 GIS 工具调用，无 workflow/verifier；D 从 PlanSpec 编译多步流程并校验。所有系统共享公共默认语义、模型参数和结构契约，未向任何系统提供真值。它们比较的是应用架构与信息访问能力，不是四种不同模型的推理优劣。', '',
        '## Benchmark 与冻结', '',
        '- dev：120条既有确定性回归问题，不能称为 LLM reasoning accuracy。',
        '- validation：60条，三次推理用于适配和检查；原始失败与重新计分日志保留。',
        '- test：180条，14类；112条期望返回医院，68条期望空结果、拒绝、澄清或引用错误。',
        '- fixture：12家合成医院、45条报告；不是现实医院运营数据。',
        '- reference clock：2026-06-01T12:00:00Z；generation seed：20261007。',
        f"- 冻结时间：{manifest['freeze_timestamp']}。",
        f"- benchmark 原文件 SHA-256：`{manifest['test_sha256']}`。",
        f"- benchmark 规范 JSON SHA-256：`{manifest['test_canonical_sha256']}`。",
        f"- fixture SHA-256：`{manifest['fixture_sha256']}`。",
        f"- 冻结执行实现：`{manifest['implementation_sha256']}`。", '',
        'test 主问题与 dev/validation 不重合，包含资格与目标区分、先筛选后截断、连续指代、否定条件、无数值门槛、SQL样式名称和不可信文本。不同坐标/上下文可复用同一语言结构，因此180条不是180个互相独立的语言现象。独立 oracle 读取原始观测与 PostGIS 距离，不调用生产 tool/domain；正式评测后没有更改 prompt、执行、评分、fixture 或 test。', '',
        'validation 揭示了复合无结果案例的 oracle 执行路径缺陷：原始 authored no_result 过早跳过 ranking。修复后重新计分同一批模型输出，不改变查询或模型输出；初始/重计分结果均保存。此修复发生在 test 冻结前。', '',
        '## 主结果（三次平均；每系统540条结果）', '',
        '| System | E2E | Tool Sel. | Args | Constraint | Entity | Grounded | Map | Severe Error | Mean latency | Tokens（已知总量） |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for system in SYSTEMS:
        s = summary[system];m=s['metrics']
        values = [pct(m[key]) for key in ('end_to_end_success_rate','tool_selection_accuracy','tool_argument_accuracy','constraint_satisfaction_rate','final_entity_accuracy','answer_groundedness','map_action_accuracy')]
        lines.append(f"| {LABELS[system]} | {' | '.join(values)} | {pct(s['severe_error_rate'])} | {s['latency_ms']['mean']:.0f} ms | {s['known_total_tokens']:,} |")
    best_baseline = max(SYSTEMS[:3], key=lambda k: summary[k]['mean_success_rate'])
    delta = summary['proposed_llm']['mean_success_rate'] - summary[best_baseline]['mean_success_rate']
    direction = '高于' if delta > 0 else '低于' if delta < 0 else '等于'
    lines += ['', f"在本冻结合成评测中，Proposed 的平均 E2E 为 {pct(summary['proposed_llm']['mean_success_rate'])}，{direction}最强 baseline {LABELS[best_baseline]}（{pct(summary[best_baseline]['mean_success_rate'])}），差值 {delta*100:+.2f} 个百分点。这不是部署效果或真实医疗收益。", '',
        '### 指标定义', '',
        '- Tool Sel./Args：与可接受执行流程及参数匹配；名称解析次序、ID集合顺序与名称大小写不作为语义差异。A/B 不调用 GIS tools，记N/A。',
        '- Execution Success：最终状态符合预期或明确列出的安全拒绝状态；负例也在分母中。',
        '- Constraint：状态、排序后的目标实体及请求窗口统计符合独立真值。Entity同时检查状态与有序ID。',
        '- Grounded：验证已返回的结构事实和闭合回答格式。缺失目标/安全拒绝仍可能通过，因此高Grounded不意味着完成任务或取得了数据库事实；错误请求窗口的统计或格式也可使其失败，不能将其补集全部叫幻觉率。',
        '- Map：完整动作序列、类型与实体顺序符合共享策略。E2E为各适用公共指标全部通过，并要求会话前置结果正确。',
        '- Typed IR提取指标单独报告，不仅对D增加额外E2E门槛。',
        '- Severe Error：S3+S4，含错误/遗漏核心实体与已声明事实虚构；不等于医疗伤害概率。S4依据独立记录检查，真实但错误时间窗口属于语义错误而不自动视为数据库虚构。', '',
        '### 正例与负例', '', '| System | 期望返回实体（112×3） | 空结果/拒绝等（68×3） | Execution Success |', '|---|---:|---:|---:|']
    for system in SYSTEMS:
        s=summary[system]
        lines.append(f"| {LABELS[system]} | {pct(s['positive_case_success'])} | {pct(s['negative_case_success'])} | {pct(s['metrics']['execution_success_rate'])} |")
    lines += ['', 'LLM-only 的正确拒绝/空结果可能提高总分，但不表示其查询到了数据库。报告正负例分层，避免把无法获取观测的拒绝解释为空间事实能力。', '',
        '## 分类别 E2E', '', '| Category | Cases | LLM Only | Text-to-SQL | Single-Step | Proposed |', '|---|---:|---:|---:|---:|---:|']
    for category,count in manifest['category_distribution'].items():
        values=[pct(rate([r for r in rows if r['system']==s and r['category']==category], 'end_to_end_success_rate')) for s in SYSTEMS]
        lines.append(f"| {category} | {count} | {' | '.join(values)} |")
    lines += ['', '## 三次推理一致性与统计描述', '', '| System | Pass@1 | 三次 E2E | 均值 | 样本SD | 结果一致率 | 有效计划一致率 |', '|---|---:|---|---:|---:|---:|---:|']
    for system in SYSTEMS:
        s=summary[system]
        lines.append(f"| {LABELS[system]} | {pct(s['pass_at_1'])} | {' / '.join(pct(x) for x in s['round_rates'])} | {pct(s['mean_success_rate'])} | {s['sample_standard_deviation']*100:.2f} pp | {pct(s['consistency_rate'])} | {pct(s['identical_plan_rate'])} |")
    lines += ['', 'Pass@1固定为第1轮，不选择最好轮次。SD为三轮成功率的样本标准差。结果一致率同时比较status、实体、统计和地图动作，忽略来源UUID与模型措辞。计划一致率只针对D三轮都产生合法PlanSpec的case，默认字段经schema展开；A/B/C记N/A，不把三轮同样无计划的错误算作计划一致。', '', '| System | 三轮都成功 | 失败1次 | 失败2次 | 失败3次 | 第1轮 Wilson 描述区间 |', '|---|---:|---:|---:|---:|---|']
    for system in SYSTEMS:
        s=summary[system];rec=s['failure_recurrence'];ci=s['first_run_wilson_interval']
        lines.append(f"| {LABELS[system]} | {rec.get(0,0)} | {rec.get(1,0)} | {rec.get(2,0)} | {rec.get(3,0)} | {pct(ci[0])}–{pct(ci[1])} |")
    lines += ['', 'Wilson区间仅作为180条第1轮结果的二项描述。问题共享模板、参数、fixture和上下文，不能视为独立抽样的真实用户人群；三次重复也不是540条独立语言问题，不作显著性或人群泛化宣称。', '',
        '## Typed Spatial IR（Proposed）', '', '| Metric | 准确率（适用case分母） |', '|---|---:|']
    drows=[row for row in rows if row['system']=='proposed_llm']
    for key in ('intent_accuracy','spatial_constraint_accuracy','temporal_constraint_accuracy','filter_extraction_accuracy','objective_extraction_accuracy','limit_extraction_accuracy','reference_resolution_accuracy','semantic_success_rate'):
        vals=[row['metrics'][key] for row in drows if row['metrics'].get(key) is not None]
        lines.append(f'| {key} | {sum(vals)}/{len(vals)} ({pct(sum(vals)/len(vals))}) |')
    lines += ['', 'best-cleanliness intent的结果数量内置为1，因此其limit不另行依赖模型未使用的limit字段。模糊/非法请求只计可定义的intent处理，其余槽位记N/A。', '',
        'intent槽位采用严格标签匹配，而公共E2E依据可接受工具执行与结果。正式结果中68次ranking/attribute被标为multi_step，但编译出等效执行且E2E通过；另9次越界引用以lookup计划在引用检查处正确终止。因此81.48%的intent标签准确率与93.15%的E2E不矛盾，也不能把100次标签差异全部解释成任务失败。未在test后合并标签或修改评分。', '',
        '## 延迟、调用和 token', '', '| System | p50 / p95 | Model calls | GIS calls | Retries | Input / Output tokens（已知） | Usage覆盖 |', '|---|---:|---:|---:|---:|---:|---:|']
    for system in SYSTEMS:
        s=summary[system]
        lines.append(f"| {LABELS[system]} | {s['latency_ms']['p50']:.0f} / {s['latency_ms']['p95']:.0f} ms | {s['model_calls']} | {s['tool_calls']} | {s['retries']} | {s['known_input_tokens']:,} / {s['known_output_tokens']:,} | {pct(s['usage_coverage'])} |")
    lines += ['', '延迟包括各系统实际执行的前置会话，正式实验以固定shuffle seed混合提交，六并发；validation为四并发。并发和外部API状态影响延迟，因此不将本地数字当成生产容量或与validation直接比较。GIS calls不含catalog，SQL选择/投影与角色安全检查不属于GIS call，不能把B的GIS零调用理解成没有数据库成本。', '',
        'API提供的usage直接保存；缺失usage的请求不估造token。已知token总量与coverage同时报告。没有账单或可靠货币cost记录，**cost unavailable**。', '',
        '## 失败、验证与限制', '',
        '详细失败类型、S0–S4分布、代表case、实际SQL/工具轨迹与建议见[中文失败分析](../../docs/FAILURE_ANALYSIS_ZH.md)。所有失败保留，不删除问题、不仅展示成功、不在test后调参。', '',
        '- unseen仅指相对于本项目开发/validation未用于调试的语言与组合；作者定义的合成集合不是外部盲测，也不能证明预训练数据未包含类似语言。',
        '- 数据少、报告时间稀疏；不测交通时间、实时医院运营、科室或临床适宜性。',
        '- Baseline C被明确限制为一个工具；B有SQL AST/函数/表限制与固定事实投影。差异包含工程能力，不能全部归因语义规划或单独verifier。',
        '- 未做去掉verifier的消融，也没有对正式test注入篡改工具结果；因此无法从本实验独立量化verifier的因果贡献。',
        '- 本次实际运行Windows/PostGIS、Jest、Agent/MCP与Evaluation测试；Docker、Linux、远程Actions、生产部署未运行。',
        '- QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。', '',
        '## 复现与原始证据', '',
        '安装根目录requirements.lock.txt与Node依赖，按既有部署/评测文档准备隔离queuelens_eval及非特权reader，在本地agent-service/.env配置模型。严禁输出密钥。', '',
        '```bash', 'python eval/llm_experiment.py --split validation --repeat 3 --run-id YOUR_VALIDATION',
        '# 仅在没有freeze且未做正式test时创建一次；已有冻结集直接核验', 'python eval/freeze_benchmark_v2.py',
        'python eval/llm_experiment.py --split test --repeat 3 --concurrency 6 --run-id YOUR_TEST', 'python eval/report_llm_zh.py --run-id YOUR_TEST', '```', '',
        '命令要求显式EVAL_DATABASE_URL指向隔离reader，不能使用生产数据库。报告脚本读取本次固定run目录；复跑需显式选择对应目录。已冻结生成脚本拒绝覆盖。任何基于test修复的系统都必须建立新holdout，不继续冒称同一集合unseen。', '',
        '- [机器可读分析](LLM_EXPERIMENT_ANALYSIS.json)', '- [正式运行元数据](llm/test-frozen-r1-r3/metadata.json)', '- [所有逐case结果/推理/SQL/工具证据](llm/test-frozen-r1-r3/cases.jsonl)', '- [冻结清单](../benchmark_v2/freeze.json)', '- [test真值](../benchmark_v2/test/cases.json)', '- [validation原始结果](llm/validation-r1/cases.jsonl)', '- [validation重计分](llm/validation-r1/rescored-cases.jsonl)']
    (ROOT/'eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write_failures(rows, summary)
    write_project(summary, metadata)


def write_failures(rows, summary):
    lines=['# QueueLens 真实模型失败分析', '', '本报告分析正式冻结test三轮结果；不修改系统或问题，不将格式错误直接说成数据库幻觉。每个失败可有多个类型标签，因此类型计数之和不等于失败总数。', '',
        '## 严重程度与处理', '',
        '| Severity | 定义 |', '|---|---|', '| S0 | 格式、拒绝类型等差异，未返回错误实体事实 |', '| S1 | 实体与关键约束正确，但说明不完整/闭合格式不合格 |', '| S2 | 条件、目标、时间或动作不满足，有序核心ID未改变 |', '| S3 | 有序核心ID不同或遗漏，含安全拒绝造成的任务未完成 |', '| S4 | 声明的距离、观测或其他结构事实与独立数据库真值不符 |', '',
        'S3不是医疗伤害：无法获取数据而拒绝回答、遗漏目标实体也计入核心结果失败。冻结自动分类以有序ID列表作核心结果，顺序不同但集合相同也可归S3；例如B的24次radius结果成员正确、按ID而非距离排列，仍被严格契约判失败。该保守口径不能解释成24次错误半径包含。真实数据来自错误但已声明的时间窗口，按语义错误而不是自动S4。自由文本不符闭合格式也不自动S4；S4主要检查结构事实，不能保证捕获任意自由文本暗示。', '',
        '| System | Failures / 540 | S0 | S1 | S2 | S3 | S4 | Severe Error Rate | 可恢复 / 当前不可恢复 |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for system in SYSTEMS:
        s=summary[system];sev=s['severity_distribution']
        lines.append(f"| {LABELS[system]} | {s['total_failures']} | {' | '.join(str(sev.get(k,0)) for k in ('S0','S1','S2','S3','S4'))} | {pct(s['severe_error_rate'])} | {s['recoverable_failures']} / {s['total_failures']-s['recoverable_failures']} |")
    lines += ['', '可恢复仅表示当前状态可通过澄清、提供位置/有效引用或重新连接处理，不意味着已经自动修复。实际没有自动调参、修SQL或重试语义失败。', '', '## Failure taxonomy', '', '| Type | LLM Only | Text-to-SQL | Single-Step | Proposed |', '|---|---:|---:|---:|---:|']
    types=sorted({kind for s in summary.values() for kind in s['failure_types']})
    for kind in sorted(set(TAXONOMY) | set(types)):
        lines.append(f"| {kind} | {' | '.join(str(summary[s]['failure_types'].get(kind,0)) for s in SYSTEMS)} |")
    lines += ['', '检测标签覆盖解析、工具选择/参数、空间/时间、筛选、目标、引用、SQL/schema、执行/超时/格式、verification、幻觉、地图、循环、空结果和歧义。0表示冻结自动分类未触发，不证明该类绝对不存在；没有观测到的类型不虚构案例。Typed IR槽位标签主要适用于D，B的时空/筛选语义需要结合原始SQL复核，自动SQL_generation_failure也包含受限AST拒绝与空SQL协议错误。下文分别记录，不能全当作SQL语法错误或模型幻觉。', '',
        '## 主要根因复核', '',
        '- D共37次严格E2E失败，其中15次追问把temporal标为lookup：referent和hours正确、医院正确，但没有执行窗口聚合；验证已声明lookup计划可通过，形成语义遗漏。另有数量limit误提取、5次排队优先权重遗漏，以及安全澄清/拒绝与严格状态或工具轨迹不匹配。D的S3为3次返回了额外医院，S4为0。',
        '- B的radius-02选择了正确半径集合[1,2,3,9,10,11]，却按ID排列；真值策略要求距离次序[1,11,2,9,10,3]。24次radius失败均是这个排序契约差异。',
        '- B的temporal-05生成row_number()，该函数不在预先说明的函数白名单；以ValueError拒绝。该案例涉及安全能力约束，不能声称数据库时间聚合算错。',
        '- B的spatial_attribute-04在外层ORDER BY引用仅存在于EXISTS子查询的r.cleanliness_score，触发UndefinedTable；multi_step-05/23引用未JOIN的ql.sort_order。属于SQL作用域/schema引用错误。',
        '- B的multi_step-06第3轮遗漏LIMIT 2，实际返回[8,1,11,2,12]，请求真值[1,11]；数据真实，选择/截断语义错误。空SQL拒绝和禁止CTE另计协议/安全约束失败。',
        '- C的attribute_filter-01直接提交candidate_ids=[]，没有先发现候选；follow_up-01沿用自身错误前置推荐后查询医院3，真值为医院11。其单工具权限确实限制组合任务，结果不能概括为同模型规划水平的纯比较。',
        '- A对112条实体正例均没有完成数据库实体任务；主要是无信息访问时安全拒绝，S3包含遗漏。另有2次nearest-03编造“圣托马斯医院”的坐标与1234.5米距离，触发S4；不能把其他全部任务失败都归为事实编造。', '',
        '以上根因复核仅解释冻结原始记录，不重新计分，也未调整系统。', '', '## Verifier effectiveness', '']
    d=summary['proposed_llm']
    lines += [f"Proposed 正式失败中，结果验证明确拒绝 {d['verifier_caught']} 次；status=ok但任务约束不满足的语义遗漏/错误 {d['verifier_missed']} 次。", '',
        '本实验的工具来自确定性只读服务，未在正式test主动注入伪造输出。若拒绝次数为0，不能计算0/0捕获率，也不能解释为verifier没有作用。故意篡改ID、分数、时间、统计的回归测试提供机制验证；真实自然语言理解错误仍可能通过对“已声明计划”的验证。本实验没有单独验证器消融，不能把总体优势全部归因给verifier。', '', '## 代表性失败（每个主要类型最多3例）', '']
    representatives=[]
    for kind in types:
        chosen=[]
        used=set()
        ordered=sorted(rows,key=lambda r:(r['id'],r['repeat']))
        # Prefer one representative per architecture over three copies of A.
        for system in ('proposed_llm', 'text_to_sql', 'single_step', 'llm_only'):
            candidates=[r for r in ordered if r['system']==system and r['failure'] and kind in r['failure']['types']]
            if candidates:
                chosen.append(candidates[0]);used.add((system,candidates[0]['id']))
            if len(chosen)==3:break
        for row in ordered:
            if len(chosen)==3:break
            if row['failure'] and kind in row['failure']['types'] and (row['system'],row['id']) not in used:
                chosen.append(row);used.add((row['system'],row['id']))
        lines += [f'### {kind}', '']
        for row in chosen:
            case=CASES[row['id']]
            output=row['result'];failure=row['failure']
            content=row['model_calls'][-1].get('content') if row['model_calls'] else None
            actual_ids=[h.get('hospital_id') for h in output.get('entities',[])]
            lines += [f"**{row['id']} / {LABELS[row['system']]} / 第{row['repeat']}轮**", '', f"Query：{row['query']}", '',
                f"Ground truth：状态 `{case['expected_status']}`；有序医院ID `{case['expected_hospital_ids']}`；约束 `{json.dumps(case['expected_constraints'], ensure_ascii=False)}`。", '',
                f"实际：状态 `{output.get('status')}`，医院ID `{actual_ids}`；阶段/标签 `{failure['types']}`；Severity `{failure['severity']}`；verifier caught `{failure['verifier_caught']}` / missed `{failure['verifier_missed']}`。", '',
                'Model Plan / SQL / Tool choice：', '', '```json', str(content or json.dumps(output.get('plan'),ensure_ascii=False)), '```', '',
                f"工具轨迹：`{[s.get('tool') for s in output.get('trace',[]) if s.get('tool')]}`；完整参数、结果、前置会话与来源见逐case JSONL。", '',
                '根因提示：'+root_cause(row,case), '',
                '可能修复：'+possible_fix(kind)+' 该建议未用于调整本冻结test。', '']
            representatives.append({'type':kind,'system':row['system'],'id':row['id'],'repeat':row['repeat'],'severity':failure['severity']})
    lines += ['## 限制与冻结后的处理', '', '自动分类以结构事实与可执行真值为主；自由文本、同一实体下复杂SQL语义与潜在临床暗示仍需人工复核。保留全部原始响应，不把安全拒绝伪装成事实幻觉。后续若根据这些失败修复prompt或执行，必须使用新的final holdout/benchmark版本。', '', 'QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。']
    (ROOT/'docs/FAILURE_ANALYSIS_ZH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'eval/reports/FAILURE_REPRESENTATIVES.json').write_text(json.dumps(representatives,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def root_cause(row,case):
    plan=row['result'].get('plan')
    raw=row['model_calls'][-1].get('content') if row['model_calls'] else None
    if plan is None and raw:
        try:plan=json.loads(raw)
        except ValueError:plan={}
    plan=plan or {}
    c=case['expected_constraints']
    if row['system']=='proposed_llm':
        differences=[]
        for key in ('intent','hours','referent','radius_m','min_cleanliness','max_queue_severity','max_wait_minutes','limit'):
            if key in c and plan.get(key,24 if key=='hours' else 3 if key=='limit' else None)!=c[key]:
                differences.append(f"{key} 应为 {c[key]}，模型给出 {plan.get(key)}")
        if 'weights' in c:
            weights=[plan.get(k,1/3) for k in ('distance_weight','queue_weight','cleanliness_weight')]
            if weights!=c['weights']:differences.append(f"排序权重应为 {c['weights']}，模型给出 {weights}")
        if differences:
            return '；'.join(differences)+'。'+('实体ID正确，但lookup流程未执行请求的时间聚合。' if c.get('intent')=='temporal' and plan.get('intent')=='lookup' else '')+'验证器核对已声明计划与工具，未重新解析原始问题，因而不能补齐未提取的语义。'
        if row['result']['status']!=case['expected_status']:
            return f"期望状态为 {case['expected_status']}，实际为 {row['result']['status']}；未输出医院或伪造事实。这是严格状态契约失败，不能称为事实幻觉。"
    if row['system']=='text_to_sql':
        sql=(plan.get('sql') or row['result'].get('sql') or '')
        if not sql.strip():return '模型以intent字段表达拒绝，却输出空SQL；adapter只识别status形式拒绝，因此空SQL被长度检查拒绝。这包含输出协议限制，不能仅归因SQL语义生成弱。'
        if 'WITH ' in sql.upper() and row['result'].get('error_class')=='ValueError':return '模型生成WITH/CTE，违反预先说明的SQL AST白名单；安全层拒绝执行。拒绝不是数据库查询算错，协议/能力限制参与了该baseline的成绩。'
        if row['result'].get('error_class')=='UndefinedTable' and 'ql.' in sql and 'queue_lengths' not in sql:
            return 'SQL引用ql.sort_order，但FROM/JOIN中没有声明ql；PostgreSQL以UndefinedTable拒绝。属于未定义别名/schema引用，不是工具编造结果。'
        if c.get('limit') and 'LIMIT ' not in sql.upper():return f"SQL遗漏请求的top-{c['limit']}截断；固定事实投影忠实返回已选择ID，无法补齐缺失LIMIT。"
        if 'Shared Clinic' in row['query']:return 'SQL使用子串匹配返回两个Shared Clinic实体，未执行唯一名称消歧；固定投影不能将多匹配改为澄清。'
    if row['system']=='llm_only':
        if row['failure']['severity']=='S4':return '模型没有读取fixture，却给出“圣托马斯医院”、经纬度与1234.5米距离；结构坐标/距离与独立PostGIS记录不符。同一查询三轮中两轮出现该输出，不能用前后轮平均掩盖事实虚构。'
        return '系统无法读取当前合成医院/报告表；拒绝或格式失败造成任务未完成。必须区分信息不可访问与已返回事实的虚构，不能归结为模型推理能力弱。'
    if row['system']=='single_step':
        return '限制为一个工具。名称解析、发现候选与窗口筛选/聚合通常需要依赖调用；也需检查模型所选工具参数和前置推荐是否正确。'
    if row['system']=='text_to_sql':
        return '结合生成SQL检查名称/排序/过滤和窗口语义；若存在error class则检查AST限制、schema或语法。固定事实投影不修复错误选择，正确数据库事实也可能来自错误目标或窗口。'
    return '计划语义可能遗漏查询条件或错误处理引用/歧义；确定性验证只检查声明的计划与工具证据，不能证明所有自然语言约束均已提取。'


def possible_fix(kind):
    if 'SQL' in kind or 'schema' in kind:return '在新的validation/holdout中改进schema表达和受限SQL生成，继续保留只读角色及AST防护。'
    if 'reference' in kind:return '在新版本中明确前置会话成功状态和引用作用域，对跨轮语义进行单独评测。'
    if 'argument' in kind or 'filter' in kind or 'constraint' in kind or 'objective' in kind:return '在新版本validation中改进Typed IR槽位与显式语义校验，再使用新holdout验证。'
    if 'hallucinated' in kind:return '拒绝没有可执行来源的事实，并在新的故障注入/独立评测中检查验证覆盖。'
    return '基于新validation复核输出契约、能力边界和失败处理，避免针对本test个别问题写规则。'


def write_project(summary,metadata):
    d=summary['proposed_llm'];b=summary['text_to_sql'];delta=(d['mean_success_rate']-b['mean_success_rate'])*100
    lines=['# QueueLens 项目最终总结', '',
        '## 原项目与升级', '',
        '原项目是Node.js/Express、PostgreSQL/PostGIS、Leaflet/Cesium与Chart.js构成的Hospital WebGIS，支持医院展示、定位、最近医院、上报与历史统计。升级保持原业务API和地图工程，新增严格GIS工具、独立FastAPI Agent、MCP桥接、确定性验证和系统评测。', '',
        '## 为什么采用 Plan–Execute–Verify', '',
        'LLM提取自然语言意图、约束和引用，PlanSpec作为Typed Spatial IR；程序编译有界流程，GIS工具和PostGIS计算距离/统计/排名，验证层检查证据、ID、范围、窗口和筛选后排名。结果驱动统一Leaflet/Cesium命令。模型不负责猜医院事实。', '',
        '## 实验和结论', '',
        '保留120条开发/回归问题，新增60条validation和180条冻结语言/组合holdout，总计360条。复用12家合成医院、45条观测，以独立原始记录/PostGIS oracle确定真值；四系统使用同一deepseek-flash，完成正式test三次推理，保存2160条逐case结果和全部失败。', '',
        f"Proposed三次平均E2E {pct(d['mean_success_rate'])}，Text-to-SQL {pct(b['mean_success_rate'])}，差值 {delta:+.2f} 个百分点；Proposed Severe Error Rate {pct(d['severe_error_rate'])}。这是合成固定任务和已支持能力下的应用架构结果，不是训练成绩、医疗效益或生产SLA。其他baseline、分层和一致性见完整报告。", '',
        'LLM-only缺少真实观测访问，Single-Step缺少组合流程，SQL baseline同时受到生成质量和安全环境约束。未做verifier消融，不能独立归因其因果贡献。验证声明计划不等于验证全部自然语言语义；保留解析、引用和歧义等实际失败。', '',
        '## 范围与限制', '',
        '- 支持空间/运营信息：直线距离、排队等级与实际报告分钟、清洁度评分、报告历史与地图交互。',
        '- QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。',
        '- 数据为合成/众包设计；缺失观测不等于不排队，旧观测不代表当前状态，直线距离不是交通时间。',
        '- 仅相对于项目开发/validation未见；固定小型fixture、重复结构和严格输出契约限制外推。',
        '- Windows本地模型/PostGIS/测试已运行；Docker、Linux、远程CI和生产部署未运行，没有push或生产库修改。', '',
        '## 项目冻结', '',
        'unseen benchmark、真实模型baseline comparison、failure analysis、中文报告与简历材料已经完成；最终回归验证记录见阶段说明。', '',
        'QueueLens 当前阶段开发冻结。后续仅进行必要 bug fix、依赖维护或针对实际岗位需求的小规模适配，不再继续增加 RAG、Multi-Agent 或其他非必要功能。', '',
        '若未来针对本test失败改变prompt、执行或评分，当前test按exposed处理，并建立新的holdout；本次已冻结实现和原始结果保留。', '',
        '[真实实验报告](../eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md) · [失败分析](FAILURE_ANALYSIS_ZH.md) · [简历材料](RESUME_MATERIAL_ZH.md)']
    (ROOT/'docs/FINAL_PROJECT_SUMMARY_ZH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    lines=['# QueueLens 中文简历与面试材料', '', '以下数字均来自本次实际实验；不是训练结果、真实医院运营数据或已上线生产指标。', '',
        '## A. 项目名称', '', 'QueueLens Agent：基于 PostGIS 的工具增强空间 AI 系统', '',
        '## B. 一句话概述', '', '将既有医院WebGIS升级为自然语言驱动的Agentic GIS，通过Typed Spatial IR、多步工具执行和确定性验证返回空间事实与地图动作，并完成同模型冻结benchmark对比。', '',
        '## C. 三条简历 bullet', '',
        '- 复用Node.js/Express与PostGIS业务能力，封装8个严格schema GIS工具，采用参数化SQL、空间索引、只读执行和来源证据；以FastAPI提供有界Agent流程、会话指代和SSE。',
        '- 实现Plan–Execute–Verify：LLM提取空间/时间/属性约束，确定性程序执行聚合与筛选后排名，验证来源及实体一致性，并输出Leaflet/Cesium共享地图命令；MCP复用同一工具实现。',
        f"- 建立360条合成查询的dev/validation/test划分，对冻结180条test开展四组deepseek-flash三次实测；Proposed平均E2E为{pct(d['mean_success_rate'])}，Text-to-SQL为{pct(b['mean_success_rate'])}，并保存逐case失败、严重程度和一致性分析。", '',
        '## D. 30秒介绍', '',
        f"QueueLens原来是医院排队和清洁度的WebGIS。我保留了Express和PostGIS，把它升级为工具增强空间Agent：模型只解析意图，距离、聚合和排名由工具计算，再验证并驱动地图。我也建立了冻结的180条合成test，四组同模型各跑三次，Proposed平均端到端成功率为{pct(d['mean_success_rate'])}。结果、失败和限制都可复现，项目没有把规则成绩当成模型成绩，也没有宣称生产部署。", '',
        '## E. 2分钟技术介绍', '',
        '这个项目解决的是组合空间问题：例如限制距离和时间窗口，再筛清洁度、按排队偏好返回几家医院。原始工程已经有Express、PostGIS、两种地图和上报接口，因此我新增严格工具层而不是重写后端。每个工具验证参数范围并返回数据来源，PostGIS负责geography距离、半径和窗口选择，程序负责明确的聚合和排序。', '',
        'Agent采用一个FastAPI服务。LLM输出PlanSpec，程序编译Plan–Execute流程并保存trace，Verifier检查医院ID、候选集合、半开时间窗口、过滤条件及完整候选排序。回答以确定性模板生成，地图使用共享action schema，避免模型输出HTML或随意改事实。简单会话引用只沿用已验证顺序，不猜“第二家”的身份。MCP通过同一Node工具服务提供能力。', '',
        f"实验上，我将已见120条保留为回归集，新增60条validation和180条冻结test，包含多步、连续引用、歧义、非法与对抗请求。四个系统共享deepseek-flash、fixture、时钟和超时，test各跑三次；Proposed平均E2E为{pct(d['mean_success_rate'])}，SQL baseline为{pct(b['mean_success_rate'])}。真值来自独立原始记录和PostGIS，不用LLM judge，全部失败按阶段与S0–S4保留。", '',
        '限制也很明确：数据是合成的，直线距离不是交通时间，验证器验证的是已声明计划，不能证明模型没有遗漏自然语言条件。模型和工具权限不同，因此不把优势解释成纯模型推理能力；没有verifier消融或生产部署。QueueLens不提供诊断、紧急程度或临床适宜性判断。', '',
        '## F. 核心竞争力与可解释边界', '',
        '- 有可执行GIS工作流、数据库事实和地图结果，完整复用已有全栈工程。',
        '- 有真实冻结模型比较、独立ground truth、重复推理、失败严重程度与可复现证据。',
        '- 理解确定性计算、语义解析与验证的职责边界，不宣称训练新reasoning model或World Model。',
        '- 能说明信息访问差异、输出契约、合成数据与单工具限制对实验的影响。', '',
        '## G. 岗位关键词', '',
        'Agentic AI Engineer · Applied AI Engineer · Spatial AI Engineer · Location AI Engineer · GeoAI Engineer · Full-stack AI Engineer', '',
        'FastAPI · Express · PostGIS · GIS tool calling · structured output · orchestration · SSE · MCP · deterministic verification · agent evaluation · failure analysis · Leaflet · Cesium', '',
        '[数字出处与完整实验](../eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md) · [逐case原始证据](../eval/reports/llm/test-frozen-r1-r3/cases.jsonl)']
    (ROOT/'docs/RESUME_MATERIAL_ZH.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',default='test-frozen-r1-r3')
    args=parser.parse_args()
    RUN=ROOT/'eval/reports/llm'/args.run_id
    manifest=load(ROOT/'eval/benchmark_v2/freeze.json')
    metadata=load(RUN/'metadata.json')
    CASES={case['id']:case for case in load(ROOT/'eval/benchmark_v2/test/cases.json')}
    rows=[json.loads(line) for line in (RUN/'cases.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==180*4*3 and len({(r['system'],r['id'],r['repeat']) for r in rows})==len(rows), '正式实验尚未完整结束'
    summary=analyze(rows)
    (ROOT/'eval/reports/LLM_EXPERIMENT_ANALYSIS.json').write_text(json.dumps({'metadata':metadata,'freeze':manifest,'systems':summary},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_reports(rows,summary,manifest,metadata)
    print('中文实验报告、失败分析、项目总结和简历材料已从完整实际结果生成。')
