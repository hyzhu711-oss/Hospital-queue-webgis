# QueueLens benchmark v2

本集合用于固定研究问题：未见自然语言空间查询上，Plan–Execute–Verify 是否比三组同模型 baseline 更可靠地理解约束、执行 GIS 并返回结果。

## 划分与数据来源

| Split | 数量 | 用途 |
|---|---:|---|
| dev | 120 | 映射既有 Development / Regression Benchmark；已见模板的软件回归 |
| validation | 60 | 模型接口、公共任务语义与输出契约适配；运行三次 |
| test | 180 | 首次正式推理前冻结；四系统各三次；不再调参 |

总计360条；使用同一12家合成医院、45条显式报告。`generate_benchmark_v2.py` 编写自然语言与形式约束；独立 `oracle.py` 从原始记录和 PostGIS 距离生成真值，不调用生产 tool/domain。固定参考时钟为2026-06-01T12:00:00Z，生成 seed 为20261007。

主问题在三个划分间不重合。test包含资格与目标区别、筛选后top-k、缺失观测、连续指代、否定约束、模糊标准、非法边界和不可信文本。不同坐标或上下文可复用相同语言结构，因此180条不能解读为180种独立语言现象；unseen只指未用于本项目开发和validation，不是外部盲测或预训练数据保证。

## test 分布

| Category | Cases |
|---|---:|
| lookup | 8 |
| nearest | 8 |
| radius | 8 |
| attribute_filter | 10 |
| spatial_attribute | 12 |
| temporal | 12 |
| ranking | 12 |
| comparison | 12 |
| multi_step | 30 |
| follow_up | 24 |
| ambiguous | 14 |
| no_result | 12 |
| invalid_input | 10 |
| adversarial | 8 |

任务类别与期望状态不同：112条期望实体，68条期望空结果、拒绝、澄清或引用失败。保留负例，分别报告正负例成绩。

## 冻结与暴露

[freeze.json](freeze.json)记录冻结时版本、分布、原文件/规范JSON哈希、独立真值、fixture、原始数据库快照、执行实现、Git基点、时钟、seed和时间。该文件中的`frozen_unexposed`是冻结瞬间状态；首次正式模型请求已在[exposure.json](exposure.json)记录，当前集合已被评测使用。原始冻结清单保持不变。

原文件SHA-256：`95fc064b1faea4afb125daec0e5844ff5b63a52385b1850b3449582010a61ea5`。

模型、执行与评分冻结实现：`007132b4161bbbb8f08b72b8c7e638cfae2f8d1e6177f0a0bddea18c323e318b`。

执行脚本在每次正式运行前检查test、执行实现、fixture和数据库快照；生成与冻结脚本拒绝覆盖已冻结集合。事先计划的相同实现重复推理允许；任何基于结果的系统修改必须使用新holdout，不继续将此集合称为未见调参集。

## 数据可靠性与范围

缺失报告、Unknown排队等级、没有数值评分与“没有排队”不同。沿用`report_count`、各指标样本量、最新报告时间、半开窗口与nullable平均值，不将Unknown或缺失值当成0；排名排除缺少所需指标的候选。最新状态查询可返回旧报告时间，不能宣称当前实时状态。

QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。

[中文真实实验结果](../reports/LLM_EXPERIMENT_RESULTS_ZH.md) · [中文失败分析](../../docs/FAILURE_ANALYSIS_ZH.md)
