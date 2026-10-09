# 本阶段暂停与存档说明

创建时间：2026-10-07T20:04:28.864949+08:00。按用户要求，本阶段测试成果完成后暂停实验。

存档文件：`QueueLens-AI-experiment-2026-10-07-200428.zip`；位置为仓库上一级archives目录，同名manifest.json记录ZIP和各文件SHA-256。

包含所有非忽略的仓库源码、原始WebGIS资源、benchmark、全部smoke/validation/正式三轮模型日志、确定性回归结果、失败分析和中文报告；没有只保存成功case。

排除.env、.tools、本地凭据、数据库数据目录、node_modules、.venv和Git对象。环境密钥和运行依赖需在恢复机器单独配置。源码保留本地未提交状态，不push或部署。

恢复流程：解压到新目录，核对manifest内容哈希，阅读WORK_CHECKPOINT与FINAL_PROJECT_SUMMARY_ZH；按照已有依赖锁和数据库文档准备环境。已经暴露的test不用于继续调参，不自动重新请求模型。

QueueLens 当前阶段开发冻结。后续仅进行必要 bug fix、依赖维护或针对实际岗位需求的小规模适配，不再继续增加 RAG、Multi-Agent 或其他非必要功能。
