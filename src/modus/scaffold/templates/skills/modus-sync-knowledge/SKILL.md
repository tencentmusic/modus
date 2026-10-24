---
name: modus-sync-knowledge
description: using-modus 确认当前代码任务影响长期知识后，执行最小语义修订；机械检查只提供待评审候选。
---

# modus-sync-knowledge

这是代码任务确认存在长期知识影响后的静默执行器，不是用户工作流。`using-modus` 初步判定为正向影响后仍先做安全复核：当前任务的实际 diff 决定范围，正文职责决定落点，人工所有权决定权限；不构建或读取初始化 bundle。

只归因本轮任务实际修改，不接管工作区已有脏改动。证据不足时静默解析检查点，不运行固定命令、不输出 noop。

1. 复核本轮实际修改、已确认事实和相关完整正文，不接管工作区原有或其他作者的变化。只读、测试/格式、生成物、第三方或无长期语义影响时静默结束。
2. 按[场景闭合](../using-modus/references/authoring/evidence/scenario-closure.md)确认职责、契约、对象、规则、状态恢复、协作、资源或源码锚点的真实变化；机械候选只用于定位。
3. 在[生成框架](../using-modus/references/authoring/framework/index.md)规定的原主定义做最小修订，按[编辑规则](../using-modus/references/authoring/framework/editorial.md)核对受影响页面的读者问题、叙述顺序与图文分工；按需参考[对照样稿](../using-modus/references/authoring/framework/examples.md)，不为新版样稿重排无关正文，不追加 changelog，也不为编辑验收新建执行卡。结构变化只在当前任务已有授权范围内处理，否则留给显式 init/reinit/update。
4. 按[发布合同](../using-modus/references/authoring/publication.md)保护无关及人工内容，使用读时哈希、CAS 和回读；逐篇完整回读受影响页面与关联上下文，核对事实、行文及图文一致性，对变化的图表或版式使用可用的实际预览。修复后重看受影响内容，预览不可用时如实说明具体未验证项，不能宣称通过。发生正文写入时运行受影响 Domain 的机械核验；独立读者仅是授权与隔离上下文可用时的增强，不以自查冒充，也不因此扩大检查范围。

`explicit`、`symbol`、`path-only` 和 `anchorReviewCandidates` 都不是覆盖或退役结论。无影响时不输出 noop，也不运行固定命令。
