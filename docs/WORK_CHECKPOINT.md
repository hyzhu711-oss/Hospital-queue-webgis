# QueueLens 当前工作点

状态：最终AI实验与中文材料完成；实验保持暂停、开发冻结；源码与成果已按用户授权推送至GitHub。更新时间：2026-10-09（Asia/Shanghai）。

## 当前事实

- 路径：D:\Project\Hospital\Hospital-queue-webgis；Git基点72952e94992a70d97130bda18afb656043709328。
- P0–P7本地实现保留原Express REST、PostGIS、GeoJSON、报告/统计、Leaflet/Cesium与原部署路径；新增8个严格工具、FastAPI Plan–Execute–Verify、共享地图命令、MCP和独立评测。
- 本阶段完成dev120、validation60、冻结test180；真实deepseek-flash四系统各三轮正式test，共2160条结果。全部原始失败/SQL/模型输出/trace保存。
- Proposed平均E2E 93.15%；详见[中文真实实验](../eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md)、[失败分析](FAILURE_ANALYSIS_ZH.md)、[最终总结](FINAL_PROJECT_SUMMARY_ZH.md)、[简历材料](RESUME_MATERIAL_ZH.md)。
- 59+31+28=118项测试通过；迁移检查和规则PostGIS120/120通过。旧规则结果是Development / Regression Benchmark，不是LLM reasoning accuracy。
- test/实现/fixture/真值与原始DB快照仍符合冻结哈希；首次正式推理的exposure记录保留，当前test已被评测使用，不再用于调参。
- 升级源码、完整实验日志与报告保存于提交`86b98b14754d85b25472ec72500cea842f4d6a77`，已按2026-10-09用户后续明确授权推送到指定仓库的`main`。本次仅进行Git推送，未执行生产数据库迁移或独立部署操作；线上运行状态未核验。

## 安全与本地环境

模型配置由本地agent-service/.env提供，进程变量优先；只加载模型配置，密钥未输出且不进入报告。环境文件、.tools、.venv与本地数据库凭据均忽略。局部隔离数据库为queuelens_test/queuelens_eval，正式SQL使用非特权只读reader；本次官方portable PostgreSQL16.15/PostGIS3.6.2仅监听127.0.0.1:55432，收尾后停止。

Docker/Linux、远程CI、Render/Supabase生产迁移和上线未运行。YAML解析不是运行证明；cost unavailable，不根据token推算真实账单。详见[阶段记录](EXPERIMENT_STAGE_ZH.md)和[验证记录](VALIDATION.md)。

## 后续边界

QueueLens 不提供医疗诊断、紧急程度判断或临床适宜性建议。

QueueLens 当前阶段开发冻结。后续仅进行必要 bug fix、依赖维护或针对实际岗位需求的小规模适配，不再继续增加 RAG、Multi-Agent 或其他非必要功能。

任何根据本次test失败修改的模型提示、执行或评分必须使用新的holdout/版本。本轮不继续优化成绩。

## 历史归档

2026-10-04暂停归档：D:\Project\Hospital\archives\QueueLens-checkpoint-2026-10-04-222829.zip，64个源码文件、665177字节，SHA-256 cfb9341e6f0a469b0673cd56d13fbdf14f1e60c3eeecbf60f631aeb4c5e215d3。它只包含旧P0–P4，不是本阶段快照；当前工作树和冻结实验原始结果为事实依据。

## 本阶段存档与暂停

按用户2026-10-07要求，完成本批测试后停止新的模型实验。全部模型输出、成功/失败日志、SQL、tool trace、benchmark冻结/暴露清单、中文报告和源码保留。临时服务已停止。

存档：`D:\Project\Hospital\archives\QueueLens-AI-experiment-2026-10-07-200428.zip`；ZIP及同名manifest.json在仓库外的archives目录。存档不包含环境密钥、数据库凭据、下载工具、依赖、临时数据库或Git对象；外部manifest记录每个文件与ZIP的SHA-256。

恢复时以本工作点、冻结清单及原始结果为依据，不重新生成/覆盖已暴露test，也不自动发起付费模型请求。模型凭据需在本机自行保留。

## 2026-10-09 本地 Git 交接

用户最初明确选择整理并创建本地 Git 提交、不 push；之后在本轮明确授权推送指定GitHub仓库。提交覆盖既有WebGIS升级、严格GIS工具、Agent/MCP、benchmark与全部模型日志、中文报告、依赖锁、CI/部署配置及测试源码。环境密钥、本地数据库凭据、下载工具和依赖目录继续忽略。

整理前重新校验2026-10-07存档的ZIP哈希、CRC及159个文件哈希，工作区与存档一致；冻结实现、test、ground truth以及2160条唯一正式结果完整。本次更新Git交接说明，增加冻结文件换行属性，并清除2处测试文件末尾空行；未更改业务逻辑或测试断言。冻结时的Git基点与实现哈希不改写，原始存档保持不变。

本次没有重跑付费模型实验，没有修改模型提示、评分、数据库fixture或业务功能。118项自动测试及120/120确定性回归成绩仍指2026-10-07实际运行，不作为本次新测试结果。最新本地提交标识以`git log -1 --oneline`为准；工作目录与原始存档分别保留。

实验保持暂停，开发冻结边界继续生效。下一步若修复已暴露test中的问题，应创建新的holdout；发布、push或生产变更需要另行明确任务。

## 2026-10-09 GitHub 推送交接

用户已明确授权push到`https://github.com/hyzhu711-oss/Hospital-queue-webgis.git`。主提交`86b98b1`已成功推送`main`，完整实验日志和中文报告进入GitHub；没有强制推送或更改原始实验结果。

- [固定提交](https://github.com/hyzhu711-oss/Hospital-queue-webgis/commit/86b98b14754d85b25472ec72500cea842f4d6a77)
- [中文实验结果](../eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md)
- [中文失败分析](FAILURE_ANALYSIS_ZH.md)
- [正式test全部2160条日志](../eval/reports/llm/test-frozen-r1-r3/cases.jsonl)
- [validation原始日志](../eval/reports/llm/validation-r1/cases.jsonl)

历史报告中的“未push/未部署”描述2026-10-07实验阶段的操作范围；当前源码推送状态以上述交接为准。远程Actions及线上服务状态未在本次验证，不把Git推送等同于生产部署验证。模型实验继续暂停，冻结实现、fixture和benchmark哈希保持不变。
