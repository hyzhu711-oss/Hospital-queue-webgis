# QueueLens 真实模型实验结果

## 实验设计与边界

研究问题：在相对于开发与 validation 未见的自然语言空间查询上，Plan–Execute–Verify 是否比三组受限 baseline 更可靠地完成理解、执行和返回？

本实验使用同一个 deepseek-flash、相同合成 fixture、相同冻结 test、相同参考时钟。temperature=0，thinking=disabled，单次输出上限4096 tokens；请求/前置会话各30秒，临时故障最多重试一次，不针对失败问题自修复或调参。正式 test 在冻结后进行了四系统各三次独立 HTTP 推理，共2160条系统-问题-轮次结果。

四系统能力不同：A 无 GIS/数据库；B 生成一个受限 SELECT，执行后以固定 SQL 投影返回事实；C 只允许一个 GIS 工具调用，无 workflow/verifier；D 从 PlanSpec 编译多步流程并校验。所有系统共享公共默认语义、模型参数和结构契约，未向任何系统提供真值。它们比较的是应用架构与信息访问能力，不是四种不同模型的推理优劣。

## Benchmark 与冻结

- dev：120条既有确定性回归问题，不能称为 LLM reasoning accuracy。
- validation：60条，三次推理用于适配和检查；原始失败与重新计分日志保留。
- test：180条，14类；112条期望返回医院，68条期望空结果、拒绝、澄清或引用错误。
- fixture：12家合成医院、45条报告；不是现实医院运营数据。
- reference clock：2026-06-01T12:00:00Z；generation seed：20261007。
- 冻结时间：2026-10-07T19:30:46.275531+08:00。
- benchmark 原文件 SHA-256：`95fc064b1faea4afb125daec0e5844ff5b63a52385b1850b3449582010a61ea5`。
- benchmark 规范 JSON SHA-256：`f11ad6e1e7aad387345749bb14090274dcedeb8b9988535bf71c94e257e4c9b5`。
- fixture SHA-256：`6ffd1b4737e2f2d6258d161e07a3f8fe7c83a1925baca491fdc5b3ffac7f3b88`。
- 冻结执行实现：`007132b4161bbbb8f08b72b8c7e638cfae2f8d1e6177f0a0bddea18c323e318b`。

test 主问题与 dev/validation 不重合，包含资格与目标区分、先筛选后截断、连续指代、否定条件、无数值门槛、SQL样式名称和不可信文本。不同坐标/上下文可复用同一语言结构，因此180条不是180个互相独立的语言现象。独立 oracle 读取原始观测与 PostGIS 距离，不调用生产 tool/domain；正式评测后没有更改 prompt、执行、评分、fixture 或 test。

validation 揭示了复合无结果案例的 oracle 执行路径缺陷：原始 authored no_result 过早跳过 ranking。修复后重新计分同一批模型输出，不改变查询或模型输出；初始/重计分结果均保存。此修复发生在 test 冻结前。

## 主结果（三次平均；每系统540条结果）

| System | E2E | Tool Sel. | Args | Constraint | Entity | Grounded | Map | Severe Error | Mean latency | Tokens（已知总量） |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LLM Only | 27.22% | N/A | N/A | 28.89% | 28.89% | 93.70% | 37.78% | 62.22% | 3440 ms | 412,834 |
| Text-to-SQL | 42.04% | N/A | N/A | 42.04% | 42.04% | 98.70% | 65.74% | 34.26% | 3624 ms | 492,362 |
| Single-Step | 31.48% | 35.56% | 35.56% | 32.04% | 38.70% | 97.59% | 57.04% | 42.96% | 4249 ms | 3,391,200 |
| Proposed | 93.15% | 96.67% | 94.07% | 95.74% | 98.52% | 99.44% | 99.44% | 0.56% | 5535 ms | 4,071,644 |

在本冻结合成评测中，Proposed 的平均 E2E 为 93.15%，高于最强 baseline Text-to-SQL（42.04%），差值 +51.11 个百分点。这不是部署效果或真实医疗收益。

### 指标定义

- Tool Sel./Args：与可接受执行流程及参数匹配；名称解析次序、ID集合顺序与名称大小写不作为语义差异。A/B 不调用 GIS tools，记N/A。
- Execution Success：最终状态符合预期或明确列出的安全拒绝状态；负例也在分母中。
- Constraint：状态、排序后的目标实体及请求窗口统计符合独立真值。Entity同时检查状态与有序ID。
- Grounded：验证已返回的结构事实和闭合回答格式。缺失目标/安全拒绝仍可能通过，因此高Grounded不意味着完成任务或取得了数据库事实；错误请求窗口的统计或格式也可使其失败，不能将其补集全部叫幻觉率。
- Map：完整动作序列、类型与实体顺序符合共享策略。E2E为各适用公共指标全部通过，并要求会话前置结果正确。
- Typed IR提取指标单独报告，不仅对D增加额外E2E门槛。
- Severe Error：S3+S4，含错误/遗漏核心实体与已声明事实虚构；不等于医疗伤害概率。S4依据独立记录检查，真实但错误时间窗口属于语义错误而不自动视为数据库虚构。

### 正例与负例

| System | 期望返回实体（112×3） | 空结果/拒绝等（68×3） | Execution Success |
|---|---:|---:|---:|
| LLM Only | 0.00% | 72.06% | 32.41% |
| Text-to-SQL | 45.54% | 36.27% | 47.78% |
| Single-Step | 24.11% | 43.63% | 48.70% |
| Proposed | 93.75% | 92.16% | 99.07% |

LLM-only 的正确拒绝/空结果可能提高总分，但不表示其查询到了数据库。报告正负例分层，避免把无法获取观测的拒绝解释为空间事实能力。

## 分类别 E2E

| Category | Cases | LLM Only | Text-to-SQL | Single-Step | Proposed |
|---|---:|---:|---:|---:|---:|
| lookup | 8 | 0.00% | 100.00% | 100.00% | 100.00% |
| nearest | 8 | 0.00% | 100.00% | 100.00% | 100.00% |
| radius | 8 | 0.00% | 0.00% | 100.00% | 100.00% |
| attribute_filter | 10 | 0.00% | 0.00% | 0.00% | 100.00% |
| spatial_attribute | 12 | 25.00% | 72.22% | 0.00% | 100.00% |
| temporal | 12 | 0.00% | 75.00% | 0.00% | 100.00% |
| ranking | 12 | 25.00% | 27.78% | 0.00% | 100.00% |
| comparison | 12 | 0.00% | 86.11% | 0.00% | 100.00% |
| multi_step | 30 | 50.00% | 37.78% | 0.00% | 84.44% |
| follow_up | 24 | 0.00% | 0.00% | 0.00% | 76.39% |
| ambiguous | 14 | 71.43% | 0.00% | 92.86% | 92.86% |
| no_result | 12 | 100.00% | 66.67% | 66.67% | 100.00% |
| invalid_input | 10 | 50.00% | 50.00% | 76.67% | 90.00% |
| adversarial | 8 | 12.50% | 50.00% | 50.00% | 100.00% |

## 三次推理一致性与统计描述

| System | Pass@1 | 三次 E2E | 均值 | 样本SD | 结果一致率 | 有效计划一致率 |
|---|---:|---|---:|---:|---:|---:|
| LLM Only | 27.22% | 27.22% / 27.22% / 27.22% | 27.22% | 0.00 pp | 96.11% | N/A |
| Text-to-SQL | 41.67% | 41.67% / 42.78% / 41.67% | 42.04% | 0.64 pp | 93.89% | N/A |
| Single-Step | 32.22% | 32.22% / 30.56% / 31.67% | 31.48% | 0.85 pp | 83.89% | N/A |
| Proposed | 92.78% | 92.78% / 93.89% / 92.78% | 93.15% | 0.64 pp | 97.22% | 90.17% |

Pass@1固定为第1轮，不选择最好轮次。SD为三轮成功率的样本标准差。结果一致率同时比较status、实体、统计和地图动作，忽略来源UUID与模型措辞。计划一致率只针对D三轮都产生合法PlanSpec的case，默认字段经schema展开；A/B/C记N/A，不把三轮同样无计划的错误算作计划一致。

| System | 三轮都成功 | 失败1次 | 失败2次 | 失败3次 | 第1轮 Wilson 描述区间 |
|---|---:|---:|---:|---:|---|
| LLM Only | 49 | 0 | 0 | 131 | 21.25%–34.15% |
| Text-to-SQL | 72 | 2 | 7 | 99 | 34.71%–48.97% |
| Single-Step | 55 | 2 | 1 | 122 | 25.83%–39.36% |
| Proposed | 165 | 3 | 2 | 10 | 88.04%–95.73% |

Wilson区间仅作为180条第1轮结果的二项描述。问题共享模板、参数、fixture和上下文，不能视为独立抽样的真实用户人群；三次重复也不是540条独立语言问题，不作显著性或人群泛化宣称。

## Typed Spatial IR（Proposed）

| Metric | 准确率（适用case分母） |
|---|---:|
| intent_accuracy | 440/540 (81.48%) |
| spatial_constraint_accuracy | 459/459 (100.00%) |
| temporal_constraint_accuracy | 459/459 (100.00%) |
| filter_extraction_accuracy | 459/459 (100.00%) |
| objective_extraction_accuracy | 199/204 (97.55%) |
| limit_extraction_accuracy | 195/204 (95.59%) |
| reference_resolution_accuracy | 458/459 (99.78%) |
| semantic_success_rate | 426/540 (78.89%) |

best-cleanliness intent的结果数量内置为1，因此其limit不另行依赖模型未使用的limit字段。模糊/非法请求只计可定义的intent处理，其余槽位记N/A。

intent槽位采用严格标签匹配，而公共E2E依据可接受工具执行与结果。正式结果中68次ranking/attribute被标为multi_step，但编译出等效执行且E2E通过；另9次越界引用以lookup计划在引用检查处正确终止。因此81.48%的intent标签准确率与93.15%的E2E不矛盾，也不能把100次标签差异全部解释成任务失败。未在test后合并标签或修改评分。

## 延迟、调用和 token

| System | p50 / p95 | Model calls | GIS calls | Retries | Input / Output tokens（已知） | Usage覆盖 |
|---|---:|---:|---:|---:|---:|---:|
| LLM Only | 2722 / 7435 ms | 618 | 0 | 0 | 382,641 / 30,193 | 100.00% |
| Text-to-SQL | 3220 / 7117 ms | 528 | 0 | 0 | 394,191 / 98,171 | 100.00% |
| Single-Step | 3540 / 8850 ms | 562 | 267 | 0 | 3,345,340 / 45,860 | 100.00% |
| Proposed | 4561 / 12582 ms | 618 | 1116 | 0 | 4,033,545 / 38,099 | 100.00% |

延迟包括各系统实际执行的前置会话，正式实验以固定shuffle seed混合提交，六并发；validation为四并发。并发和外部API状态影响延迟，因此不将本地数字当成生产容量或与validation直接比较。GIS calls不含catalog，SQL选择/投影与角色安全检查不属于GIS call，不能把B的GIS零调用理解成没有数据库成本。

API提供的usage直接保存；缺失usage的请求不估造token。已知token总量与coverage同时报告。没有账单或可靠货币cost记录，**cost unavailable**。

## 失败、验证与限制

详细失败类型、S0–S4分布、代表case、实际SQL/工具轨迹与建议见[中文失败分析](../../docs/FAILURE_ANALYSIS_ZH.md)。所有失败保留，不删除问题、不仅展示成功、不在test后调参。

- unseen仅指相对于本项目开发/validation未用于调试的语言与组合；作者定义的合成集合不是外部盲测，也不能证明预训练数据未包含类似语言。
- 数据少、报告时间稀疏；不测交通时间、实时医院运营、科室或临床适宜性。
- Baseline C被明确限制为一个工具；B有SQL AST/函数/表限制与固定事实投影。差异包含工程能力，不能全部归因语义规划或单独verifier。
- 未做去掉verifier的消融，也没有对正式test注入篡改工具结果；因此无法从本实验独立量化verifier的因果贡献。
- 本次实际运行Windows/PostGIS、Jest、Agent/MCP与Evaluation测试；Docker、Linux、远程Actions、生产部署未运行。
- QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。

## 复现与原始证据

安装根目录requirements.lock.txt与Node依赖，按既有部署/评测文档准备隔离queuelens_eval及非特权reader，在本地agent-service/.env配置模型。严禁输出密钥。

```bash
python eval/llm_experiment.py --split validation --repeat 3 --run-id YOUR_VALIDATION
# 仅在没有freeze且未做正式test时创建一次；已有冻结集直接核验
python eval/freeze_benchmark_v2.py
python eval/llm_experiment.py --split test --repeat 3 --concurrency 6 --run-id YOUR_TEST
python eval/report_llm_zh.py --run-id YOUR_TEST
```

命令要求显式EVAL_DATABASE_URL指向隔离reader，不能使用生产数据库。报告脚本读取本次固定run目录；复跑需显式选择对应目录。已冻结生成脚本拒绝覆盖。任何基于test修复的系统都必须建立新holdout，不继续冒称同一集合unseen。

- [机器可读分析](LLM_EXPERIMENT_ANALYSIS.json)
- [正式运行元数据](llm/test-frozen-r1-r3/metadata.json)
- [所有逐case结果/推理/SQL/工具证据](llm/test-frozen-r1-r3/cases.jsonl)
- [冻结清单](../benchmark_v2/freeze.json)
- [test真值](../benchmark_v2/test/cases.json)
- [validation原始结果](llm/validation-r1/cases.jsonl)
- [validation重计分](llm/validation-r1/rescored-cases.jsonl)
