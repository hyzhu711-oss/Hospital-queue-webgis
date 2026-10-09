# QueueLens 中文简历与面试材料

以下数字均来自本次实际实验；不是训练结果、真实医院运营数据或已上线生产指标。

## A. 项目名称

QueueLens Agent：基于 PostGIS 的工具增强空间 AI 系统

## B. 一句话概述

将既有医院WebGIS升级为自然语言驱动的Agentic GIS，通过Typed Spatial IR、多步工具执行和确定性验证返回空间事实与地图动作，并完成同模型冻结benchmark对比。

## C. 三条简历 bullet

- 复用Node.js/Express与PostGIS业务能力，封装8个严格schema GIS工具，采用参数化SQL、空间索引、只读执行和来源证据；以FastAPI提供有界Agent流程、会话指代和SSE。
- 实现Plan–Execute–Verify：LLM提取空间/时间/属性约束，确定性程序执行聚合与筛选后排名，验证来源及实体一致性，并输出Leaflet/Cesium共享地图命令；MCP复用同一工具实现。
- 建立360条合成查询的dev/validation/test划分，对冻结180条test开展四组deepseek-flash三次实测；Proposed平均E2E为93.15%，Text-to-SQL为42.04%，并保存逐case失败、严重程度和一致性分析。

## D. 30秒介绍

QueueLens原来是医院排队和清洁度的WebGIS。我保留了Express和PostGIS，把它升级为工具增强空间Agent：模型只解析意图，距离、聚合和排名由工具计算，再验证并驱动地图。我也建立了冻结的180条合成test，四组同模型各跑三次，Proposed平均端到端成功率为93.15%。结果、失败和限制都可复现，项目没有把规则成绩当成模型成绩，也没有宣称生产部署。

## E. 2分钟技术介绍

这个项目解决的是组合空间问题：例如限制距离和时间窗口，再筛清洁度、按排队偏好返回几家医院。原始工程已经有Express、PostGIS、两种地图和上报接口，因此我新增严格工具层而不是重写后端。每个工具验证参数范围并返回数据来源，PostGIS负责geography距离、半径和窗口选择，程序负责明确的聚合和排序。

Agent采用一个FastAPI服务。LLM输出PlanSpec，程序编译Plan–Execute流程并保存trace，Verifier检查医院ID、候选集合、半开时间窗口、过滤条件及完整候选排序。回答以确定性模板生成，地图使用共享action schema，避免模型输出HTML或随意改事实。简单会话引用只沿用已验证顺序，不猜“第二家”的身份。MCP通过同一Node工具服务提供能力。

实验上，我将已见120条保留为回归集，新增60条validation和180条冻结test，包含多步、连续引用、歧义、非法与对抗请求。四个系统共享deepseek-flash、fixture、时钟和超时，test各跑三次；Proposed平均E2E为93.15%，SQL baseline为42.04%。真值来自独立原始记录和PostGIS，不用LLM judge，全部失败按阶段与S0–S4保留。

限制也很明确：数据是合成的，直线距离不是交通时间，验证器验证的是已声明计划，不能证明模型没有遗漏自然语言条件。模型和工具权限不同，因此不把优势解释成纯模型推理能力；没有verifier消融或生产部署。QueueLens不提供诊断、紧急程度或临床适宜性判断。

## F. 核心竞争力与可解释边界

- 有可执行GIS工作流、数据库事实和地图结果，完整复用已有全栈工程。
- 有真实冻结模型比较、独立ground truth、重复推理、失败严重程度与可复现证据。
- 理解确定性计算、语义解析与验证的职责边界，不宣称训练新reasoning model或World Model。
- 能说明信息访问差异、输出契约、合成数据与单工具限制对实验的影响。

## G. 岗位关键词

Agentic AI Engineer · Applied AI Engineer · Spatial AI Engineer · Location AI Engineer · GeoAI Engineer · Full-stack AI Engineer

FastAPI · Express · PostGIS · GIS tool calling · structured output · orchestration · SSE · MCP · deterministic verification · agent evaluation · failure analysis · Leaflet · Cesium

[数字出处与完整实验](../eval/reports/LLM_EXPERIMENT_RESULTS_ZH.md) · [逐case原始证据](../eval/reports/llm/test-frozen-r1-r3/cases.jsonl)
