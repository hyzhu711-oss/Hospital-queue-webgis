# 最终 AI 实验阶段记录

研究问题固定为：在未见过的自然语言空间查询上，Plan–Execute–Verify 是否比 LLM-only、Text-to-SQL 和 Single-Step Tool Calling 更可靠地完成空间约束理解、执行和结果返回？本阶段只完成 benchmark、真实模型比较、失败分析与必要复现材料。

## 1. 当前仓库审计

已完整读取工作点、验证记录、确定性结果、评测说明、失败分析、架构、Agent 设计及当前 Git 改动。工程修改保持在本地；此前 120 条结果来自规则工作流，名称为 **Development / Regression Benchmark（确定性回归评测集）**，不作为 LLM 推理或 unseen 准确率。

既有 PlanSpec 已覆盖 intent、半径、相对时间、筛选、权重、数量和 ordinal referent，因此复用其作为 Typed Spatial IR，不增加重复表示或新 GIS 工具。绝对日历窗口、含糊的“晚上/不太远/比较干净”、临床判断和写数据库请求应澄清或拒绝，不能猜数值。

## 2. 配置与真实 API 检查

- 本地 `agent-service/.env` 存在，三个模型变量均非空；模型配置为 deepseek-flash。
- `.env` 与 `agent-service/.env` 均通过 `git check-ignore`，没有输出密钥内容。
- 新增仅加载模型配置的本地 loader；应用选择 http_chat 时加载，实验入口显式加载。单元测试不自动从文件恢复已清除的密钥。
- 真实单次兼容性请求成功，返回 nearest 类型的合法 JSON 计划和 token usage；证据为 `eval/reports/provider-probe.json`。
- 请求统一使用 JSON mode、temperature=0、输出上限4096 tokens，并通过可配置 extension 设置 thinking=disabled；最多一次临时网络/429/502/503/504重试，每个主请求或会话前置请求总上限30秒。不会无限重试或自动修复失败问题。

DeepSeek 官方说明支持 JSON mode，并要求明确提示 JSON 与限制输出；非 thinking 模式用于本阶段一致的温度设置。[JSON 输出说明](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) · [模式与温度说明](https://api-docs.deepseek.com/guides/thinking_mode/)

## 3. 开发集 smoke 及保留的失败

第一轮16条、四系统检查暴露了 localhost HTTP 请求受到环境代理影响，以及 baseline 的 JSON collection/intent/hours 输出说明不足。初始结果保留于 `eval/reports/llm/smoke-initial/`，不能解释成模型方法优劣。

兼容性修复后重跑结果保留于 `smoke-compatible/`：LLM-only 2/16，Text-to-SQL 10/16，Single-Step 6/16，Proposed 12/16。这些仍是已见开发集 smoke 任务结果，不是正式 holdout 结果。Proposed 的失败包括阈值/最高清洁度 intent 混淆、未提取排队优先权重以及前置推荐顺序错误。

针对公共任务语义，四系统共享相同默认策略与安全边界说明；不提供任何测试答案、医院统计、测试专属提示或参考实体。Baseline B/C 继续使用不同的受限执行接口，单工具 baseline 保持最多一个 GIS 调用。所有初始失败都保留。

## 4. Benchmark v2 设计与 validation

总计360条：dev 120、validation 60、test 180。复用12家合成医院和45条报告，不扩大数据集。validation 与 test 覆盖14类，test 强化组合约束、多步、连续指代、歧义、无结果、非法输入和 adversarial 请求。

生成脚本只编写问题和形式约束；独立 oracle 从原始记录与 PostGIS 距离生成实体、统计和地图真值。holdout 相对于开发/validation 的语言与组合设计，不宣称医院实体或真实运营数据也是未见数据。公共会话前置问题可复用，主问题结构不同。最终 freeze 之前不会对 test 发起模型评测。

已完成 validation 60条 × 四系统 × 三次。正式 test 前将保存数据和执行实现哈希、版本、时钟、分布、工作树标识与冻结时间。正式 test 之后不再调整同一 holdout 的 prompt、系统或真值；若必要修复，须标为 exposed 并建立新版本。

## 范围和安全边界

所有数据是合成 fixture；只访问本机隔离数据库，SQL baseline 使用非特权只读角色和 AST 防护。不 push、不部署生产、不修改生产数据库。

QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。

阶段最终记录见下文；早期记录按实际发生顺序保留。

## 5. validation、冻结与正式实验

validation共720条结果、753次真实模型请求、2,690,030个API记录token、0重试。原始Proposed为174/180；validation发现复合no_result真值路径过早跳过ranking。修复独立oracle并断言最终状态后，仅重新计分同一批输出，得到177/180（98.33%）；A45/180、B91/180、C57/180不变。原始/重计分日志均保留，不改变模型输出或查询。修复发生在正式test冻结前。

最终开发集smoke为A2/16、B8/16、C6/16、D14/16；接口、JSON、真实工具、验证和地图路径可用，但任务失败仍保留，不声称16/16。

test180条于2026-10-07T19:30:46.275531+08:00冻结；冻结清单和首次评测暴露记录位于eval/benchmark_v2。原文件SHA为95fc064b1faea4afb125daec0e5844ff5b63a52385b1850b3449582010a61ea5；执行实现SHA为007132b4161bbbb8f08b72b8c7e638cfae2f8d1e6177f0a0bddea18c323e318b。正式test后没有修改模型提示、执行、评分、真值或fixture。

正式test已完成四系统各三轮、2160条结果；实际模型请求2326次，已知总token 8,368,040，货币cost unavailable。

| System | 三次平均 E2E | Severe Error Rate |
|---|---:|---:|
| LLM Only | 27.22% | 62.22% |
| Text-to-SQL | 42.04% | 34.26% |
| Single-Step | 31.48% | 42.96% |
| Proposed | 93.15% | 0.56% |

## 6. 最终回归与停止条件

Node/Jest59项、Agent/MCP31项、Evaluation28项，共118项全部通过，无跳过。fresh/repeated/legacy-preserving迁移检查通过。独立PostGIS规则回归120/120，单工具规则50/120，保存于eval/reports/regression-final.json；这不计入模型accuracy。

Python/JavaScript语法、依赖锁、文档链接、workflow/Compose YAML和git diff空白检查单列静态检查；容器构建、Linux、远程GitHub Actions、生产部署未运行。没有push、线上升级或生产库修改。最新完整性/密钥扫描证据为eval/reports/FINAL_INTEGRITY_CHECK.json；临时本地服务在收尾时停止。

已完成unseen benchmark、真实baseline比较、失败分析、中文报告与简历材料；后续改动若使用本test反馈，须建立新的holdout。

QueueLens 当前阶段开发冻结。后续仅进行必要 bug fix、依赖维护或针对实际岗位需求的小规模适配，不再继续增加 RAG、Multi-Agent 或其他非必要功能。

## 7. 按用户要求暂停与存档

本批测试、报告与回归检查完成后暂停模型实验；没有启动新的推理批次。临时服务已停止。存档位置：`D:\Project\Hospital\archives\QueueLens-AI-experiment-2026-10-07-200428.zip`。全部原始日志和冻结证据保留，密钥和依赖排除；旁边manifest记录内容及校验值。
