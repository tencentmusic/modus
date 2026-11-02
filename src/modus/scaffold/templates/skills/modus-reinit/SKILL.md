---
name: modus-reinit
description: 全面评审并重建知识快照，保留稳定业务身份及人工材料；只有明确选中的内容才允许修改。
---

# modus-reinit

全量复核已有正文时使用，与 init 共用[六阶段入口](../using-modus/references/authoring/index.md)及全部质量细则；本文件只规定重建差异。

## 先恢复，再判断变化

盘点或构建前先检查唯一执行卡。存在本轮未完成卡或正在继续中断任务时，先实际读卡，再按[上下文保存与恢复](../using-modus/references/authoring/context-continuity.md)加载证据、已有正文与规范，从最早未完成动作继续。压缩、容量/服务错误、工具中断或取消后继续都适用；不重跑 build、重做 Scope 或凭摘要续写。卡片缺失或与请求冲突按恢复合同处理。

新一轮重建完整读取已确认范围的正文与哈希，以稳定身份 → 入口/对象责任 → 语义变化 → 结构变化 → 文件变化判断。目标归为 `unchanged`、`anchor-only`、`implementation-change`、`scope-change`、`content-repair`、疑似退役或人工正文。

`content-repair` 包括简略条目、接口/字段缺漏、模板套话、复制内容、完成/失败不清、已定义中文未应用、缺失[初始化质量要求](../using-modus/references/authoring/framework/index.md#初始化质量要求)规定的案例/图形，以及已观察到的阅读缺陷。文件存在不能证明 unchanged；准确且已满足质量要求的正文、图表保持原位并跳写。

## 六个阶段入口与差异

| 阶段 | 必须读取的入口 | reinit 差异 |
| --- | --- | --- |
| K1 | [范围建模](../using-modus/references/authoring/stages/k1-scope.md) | 构建本轮证据一次，使用 reinit-diff；复用身份，只合并确认真实结构变化 |
| K2 | [创作计划](../using-modus/references/authoring/stages/k2-plan.md) | 全面盘点目标与保护内容，记录分类、写前哈希和跨域影响 |
| K3 | [证据闭环](../using-modus/references/authoring/stages/k3-evidence.md) | 对变化/content-repair 模块精确取证；未变结论也须核对当前依据，不能沿用失效证据 |
| K4 | [领域成稿](../using-modus/references/authoring/stages/k4-domain.md) | 原主定义修订，逐篇核对；不追加 changelog，不因模板措辞重排全库 |
| K5 | [系统组装](../using-modus/references/authoring/stages/k5-system.md) | 核对全部交接，按真实影响修订根概览；保护已有 Team Standard/business，新增域补种子 |
| K6 | [核验发布](../using-modus/references/authoring/stages/k6-publish.md) | 全范围终态、publication、发布后回读；有待验项保留原卡 |

先做全局 K2，再逐域 K2 → K3 ↔ K4，最后 K5/K6。进入阶段完整读取其适用细则，逐域保留相同深度；默认串行，仅明确授权后按[并行协议](../using-modus/references/authoring/parallel-domain-authoring.md)和固定委托合同执行。

图表在参与者、方向、所有权、状态、条件、完成/恢复变化或阅读缺陷时更新；准确且满足要求的原图复用。结构迁移先写新落点、回读并修入链，再按原哈希删除旧生成文件；符号消失、partial 或锚点移动都不能单独证明退役。每次写入遵守 CAS，冲突只处理受影响目标。

最后分别报告 unchanged、修订、删除、冲突、内容覆盖、机械核验、整页/逐图结果及缺口；语义 reviewed 或 clean 不代表未执行的预览通过。
