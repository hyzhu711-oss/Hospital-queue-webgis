# QueueLens 项目最终总结

## 原项目与升级

原项目是Node.js/Express、PostgreSQL/PostGIS、Leaflet/Cesium与Chart.js构成的Hospital WebGIS，支持医院展示、定位、最近医院、上报与历史统计。升级保持原业务API和地图工程，新增严格GIS工具、独立FastAPI Agent、MCP桥接、确定性验证和系统评测。

## 为什么采用 Plan–Execute–Verify

LLM提取自然语言意图、约束和引用，PlanSpec作为Typed Spatial IR；程序编译有界流程，GIS工具和PostGIS计算距离/统计/排名，验证层检查证据、ID、范围、窗口和筛选后排名。结果驱动统一Leaflet/Cesium命令。模型不负责猜医院事实。

## 实验和结论

保留120条开发/回归问题，新增60条validation和180条冻结语言/组合holdout，总计360条。复用12家合成医院、45条观测，以独立原始记录/PostGIS oracle确定真值；四系统使用同一deepseek-flash，完成正式test三次推理，保存2160条逐case结果和全部失败。

Proposed三次平均E2E 93.15%，Text-to-SQL 42.04%，差值 +51.11 个百分点；Proposed Severe Error Rate 0.56%。这是合成固定任务和已支持能力下的应用架构结果，不是训练成绩、医疗效益或生产SLA。其他baseline、分层和一致性见完整报告。

LLM-only缺少真实观测访问，Single-Step缺少组合流程，SQL baseline同时受到生成质量和安全环境约束。未做verifier消融，不能独立归因其因果贡献。验证声明计划不等于验证全部自然语言语义；保留解析、引用和歧义等实际失败。

## 范围与限制

- 支持空间/运营信息：直线距离、排队等级与实际报告分钟、清洁度评分、报告历史与地图交互。
- QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。
- 数据为合成/众包设计；缺失观测不等于不排队，旧观测不代表当前状态，直线距离不是交通时间。
- 仅相对于项目开发/validation未见；固定小型fixture、重复结构和严格输出契约限制外推。
- Windows本地模型/PostGIS/测试已运行；Docker、Linux、远程CI和生产部署未运行，没有push或生产库修改。

## 项目冻结

unseen benchmark、真实模型baseline comparison、failure analysis、中文报告与简历材料已经完成；最终回归验证记录见阶段说明。

QueueLens 当前阶段开发冻结。后续仅进行必要 bug fix、依赖维护或针对实际岗位需求的小规模适配，不再继续增加 RAG、Multi-Agent 或其他非必要功能。

若未来针对本test失败改变prompt、执行或评分，当前test按exposed处理，并建立新的holdout；本次已冻结实现和原始结果保留。

[真实实验报告](../eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md) · [失败分析](FAILURE_ANALYSIS_ZH.md) · [简历材料](RESUME_MATERIAL_ZH.md)
