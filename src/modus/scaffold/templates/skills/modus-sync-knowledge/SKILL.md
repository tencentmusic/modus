---
name: modus-sync-knowledge
description: using-modus 确认当前代码任务影响长期知识后，执行最小语义修订；机械检查只提供待评审候选。
---

# modus-sync-knowledge

这是代码任务确认存在长期知识影响后的静默执行器，不是用户工作流。`using-modus` 初步判定为正向影响后仍先做安全复核：当前任务的实际 diff 决定范围，正文职责决定落点，人工所有权决定权限；不构建或读取初始化 bundle。

只归因本轮任务实际修改，不接管工作区已有脏改动。证据不足时静默解析检查点，不运行固定命令、不输出 noop。

1. 复核本轮实际修改、已确认事实和相关完整正文，不接管工作区原有或其他作者的变化。只读、测试/格式、生成物、第三方或无长期语义影响时静默结束。
2. 按[场景闭合](../using-modus/references/authoring/evidence/scenario-closure.md)确认职责、契约、对象、规则、状态恢复、协作、资源或源码锚点的真实变化；机械候选只用于定位。
3. 在[生成框架](../using-modus/references/authoring/framework/index.md)规定的原主定义做最小修订，不追加 changelog。结构变化只在当前任务已有授权范围内处理，否则留给显式 init/reinit/update。
   新增或调整校验、阈值、优先级时，逐条重算受影响的已有正反例会首先命中哪个分支；不能只新增规则段落而保留已失效的失败原因。联读相同场景的步骤、表格和流程图，确认前置条件与执行顺序一致；可运行的关键例子用当前实现复核。
4. 按[发布合同](../using-modus/references/authoring/publication.md)保护无关及人工内容，使用读时哈希、CAS 和回读；发生正文写入时运行受影响 Domain 的机械核验。

`explicit`、`symbol`、`path-only` 和 `anchorReviewCandidates` 都不是覆盖或退役结论。无影响时不输出 noop，也不运行固定命令。
