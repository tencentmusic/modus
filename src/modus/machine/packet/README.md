<!--
包身份与展开句柄共同约束后续读取，不能跨基线混用。
-->

# N6 证据包

本层回答：作者完成当前任务最少需要哪些证据？

| 可以做 | 不得做 |
| --- | --- |
| 核验并打包有界意图上下文，统计省略内容，附覆盖回执与精确展开句柄 | 暴露无界图、隐藏降级或要求翻完全部分页 |

公开生命周期动词：`package`。

| 模块 | 所有权 |
| --- | --- |
| `lifecycle.py` | 核验封存输入，原子发布分析包 |
| `query.py` / `cursor.py` | 范围匹配、源码新鲜度、查询页预算与游标身份 |
| `context_builder.py` | 按意图组装候选、信号与完整路径，保留查询和缺口 |
| `context_budget.py` | 收敛最终封套预算，按实际交付重算回执 |
| `contracts.py` | 请求、预算、选择器与返回值的公开契约 |

消费者通过分析包根入口 `build_authoring_context` 组装创作上下文。传输模式携带经过认证的 `bundleDigest` / `baselineDigest`，并回显 `requestedScope`。`module-authoring` 至少需要一个候选、能力、仓库路径或符号选择器；禁止无界请求，避免把全仓摘要误当成模块证据闭环。所有展开句柄都能直接用于公开 `context` / `select` 入口。

创作上下文、分析包和 select 页各自使用 `schemaVersion: 1`；上下文契约随 CLI 与正文模板同步更新。`evidence` 交付库存/入口/关系原记录；`coverageGaps` 汇总所有子查询的缺口；`expansionQueries` 给出可重放的公开 select 过滤条件。选择轴之间取交集，无匹配不扩大范围。`reinit-diff` 提供当前基线，差异判断仍由作者结合已有知识完成。

子查询预算与最终交付预算分别生效。代表路径按整条裁剪，保留步骤顺序、来源与精度；缺口最后裁剪，遗漏显式计数。`coverageReceipt` 只统计最终交付，不证明作者已消费。`omittedCounts` 使用协议字段名：`representativePaths` 计路径，`navigationSteps` 计裁剪步骤，`*Pages` 计尚可续读的查询；不同维度不能相加作剩余记录总数。即使所有内容均被裁剪，身份、请求范围与展开查询仍保留；连固定封套都无法容纳时抛出 `machine.packet.fixed-envelope-exceeds-budget`。

`authoringSignal` 按意图嵌入候选，或按 entry/effect/resource 放在提议、效果和资源数组；它不一定出现在 `evidence`。消费者以记录身份、精度和来源解释实际含义，同一行的锁、数据写入和发送信号也须分别保留，不能按行号和大类合并为一条事实。

默认 select 将连续的大量缺口压成 `machine.packet.coverage-gap-summary`，保留 `totalCount`、有界原因计数、代表记录和 `expansionQuery`。摘要只推进所覆盖区间，后页不重复其缺口；计数不是已读证明。使用同范围的 `recordTypes: ["coverageGap"]` 可分页读取完整缺口，此时数量预算约束缺口数，允许仅有缺口的续页。两种查询的游标各自绑定过滤条件，不能互换。默认页的正向证据仍受原条数预算约束，所有内容共用总字节预算。

服务记录分别保留 `name`、`qualifiedName`、`displayName` 与稳定 `boundaryId`。`sourceBasis` 区分声明、冻结输入中的配置来源和调用关系来源，`resourceNature` 区分动态引用、一般引用与声明；这些均不证明已部署。没有真实源码见证的边界或关系以具名缺口交付，不借其他文件补锚点。完全相同的目录观察幂等合并，同键不同内容仍拒绝发布。
