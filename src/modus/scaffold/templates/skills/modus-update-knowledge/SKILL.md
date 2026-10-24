---
name: modus-update-knowledge
description: 根据源码或用户提供的材料，增量更新受影响的项目知识，无需重跑全仓分析。
---

# modus-update-knowledge

局部维护正文时使用，不构建或读取初始化 bundle。复用[证据指南](../using-modus/references/authoring/evidence/index.md)、[生成框架](../using-modus/references/authoring/framework/index.md)和[发布合同](../using-modus/references/authoring/publication.md)。

1. 以用户目标、当前源码/diff/材料和相关完整正文的交集确定范围，并记录读时哈希。
2. 既有稳定身份、主定义和语义分组默认保持。新能力或真实拆并/移动/退役按[Scope 建模](../using-modus/references/authoring/evidence/scope-modeling.md)合并确认一次；anchor-only、标题和分片调整不确认。
3. 按[场景闭合](../using-modus/references/authoring/evidence/scenario-closure.md)调查一次，按[编辑规则](../using-modus/references/authoring/framework/editorial.md)核对受影响页面的读者问题、叙述顺序、图文分工与案例，按需参考[对照样稿](../using-modus/references/authoring/framework/examples.md)，再在原语义位置修订。同步维护主定义、引用与导航，不扩大为全库重写，不追加日期式更新块，也不为编辑验收新建执行卡。
4. 保护无关正文和人工文件。API/Object 移动先写新落点、修根入口与入链，再 CAS 删除旧详情；空分片先合并剩余事实。
5. 按[发布合同](../using-modus/references/authoring/publication.md)逐篇完整回读受影响页面及关联上下文，核对事实、行文、图文与案例，用真实读者任务检查能否独立理解。对变化的图表或版式使用可用的实际预览，修复后重看受影响内容；不可用时记录具体页面、未验证项和影响，不宣称通过。运行对应 Domain 的机械核验，CAS 写入并回读。`clean` 不替代语义判断，独立读者仅是授权与隔离上下文可用时的增强，不能以自查冒充。
