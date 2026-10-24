---
name: modus-reinit
description: 全面评审并重建知识快照，保留稳定业务身份及人工材料；只有明确选中的内容才允许修改。
---

# modus-reinit

全量复核已有正文时使用。共享[证据指南](../using-modus/references/authoring/evidence/index.md)、[生成框架](../using-modus/references/authoring/framework/index.md)与[发布合同](../using-modus/references/authoring/publication.md)；本文件只描述 reinit 差异。

每个 Domain 生成或续写前都按[逐域加载与恢复](../using-modus/references/authoring/evidence/scope-modeling.md#逐域加载与恢复)先读执行卡中的本域范围、Module 归属、selector 和进度，再加载对应证据、相关已有正文和写作规范。上下文压缩后使用同一流程；全局盘点或之前读过规范不能替代本次加载。

## 先盘点，再证明变化

完整读取现有正文与哈希，将目标归为 `unchanged`、`anchor-only`、`implementation-change`、`scope-change`、`content-repair`、疑似退役或人工正文。稳定身份和主定义默认复用；源码路径/符号移动只修锚点，正文布局变化不是 Scope 变化。

`content-repair` 包括：通用模板段落替代真实场景、代表锚点替代事实、跨 Module 复制、完成/失败语义不清、复杂关系缺少能显著帮助理解的图表，以及实际影响理解的段落、表格或图文布局缺陷。真正满足读者任务且事实未变的正文保持 `unchanged` 并跳写，不因新版样稿或编辑偏好重排全库。

## 执行

1. 单仓同步构建一次本轮证据并取得 `reinit-diff` context；失败立即回当前源码。按[机器证据合同](../using-modus/references/authoring/evidence/machine-packet.md)定向展开，不直接读取 bundle 内部文件，也不追求 cursor 耗尽。
2. 按[Scope 建模](../using-modus/references/authoring/evidence/scope-modeling.md)以“稳定身份 → 入口/对象责任 → 语义变化 → 结构变化 → 文件变化”的顺序判断，把范围、句柄、读时哈希、精确 Domain/Module evidence/status、Domain coverage、outcome 与图表候选写入唯一 `schemaVersion: 2` 执行卡。只把新增、拆分、合并、移动、改名或已证明退役合并确认一次。默认串行；用户明确授权且存在多个互不重叠的受影响 Domain 时，加载[按 Domain 并行撰写](../using-modus/references/authoring/parallel-domain-authoring.md)并使用 [Domain worker 委托合同](../using-modus/references/authoring/domain-worker-prompt.md)，根作者继续独占执行卡和共享产物。
3. 每次进入或恢复当前 Domain，先读取执行卡并确定最早未完成动作，再对每个变化或 `content-repair` Module 分别使用精确 selector 请求 `module-authoring` context，核对双摘要与 `requestedScope`；覆盖整域多个独立 Module 的宽请求无效。互不依赖的精确请求可以并发，随后汇总并去重当前 Domain 的源码路径/符号，再分批回读。请求失败、空结果或 partial 时回到当前方法体、配置、SQL 与测试补证，不得把类名、接口签名或文件首行锚点当作内容已经恢复。禁止为不同专题重复扫描同一链路，也不得并发写同一正文。按[场景闭合](../using-modus/references/authoring/evidence/scenario-closure.md)重新证明后，继续完成逐域流程中的相关已有正文回读和写作规范加载，才可在原主定义修订；不追加 changelog，不因模板变化批量重写或重画。
4. 按完整 Domain 批次以“六专题主定义 → Module 场景 → Domain 路由”修订受影响范围。写前按[编辑规则](../using-modus/references/authoring/framework/editorial.md)核对页面安排，按需参考[对照样稿](../using-modus/references/authoring/framework/examples.md)，复用执行卡已有正文记录安排与用户明确的交付要求。源码路径和行号迁移到各生成文档 frontmatter 的少量 `anchors.locations`，正文删除完整源码路径、`path#L` 和证据清单；修复目标是恢复完整任务、字段语义、关键分支、状态与错误恢复，而不是让文件重新拥有标题、锚点或相似篇幅。证据闭合后按[图文表达](../using-modus/references/authoring/framework/visual-expression.md)重新评估候选并更新唯一主图，导航表不替代解释性图。域级 `coverage-audit` 必须复用本域 candidate/capability/source path/symbol 范围，不能使用 `modus/knowledge/**`；no-match、空结果或 partial 只触发补证或明确缺口。把有效结果记录为 Domain coverage，按[发布合同](../using-modus/references/authoring/publication.md)逐篇完整回读本轮六专题及其分片、全部目标 Module 和 Domain 路由，完成事实、编辑、三类读者回读与实际预览检查，在卡片已有正文记录未验证项；独立读者按[执行策略](../using-modus/references/authoring/execution-strategy.md)作为可用时的增强。根作者读取实际文件并标记 `reviewed`，抽样只作二次校准，不能替代域内逐篇验收。只有跨域方向、所有权、状态、条件、完成或恢复变化时才更新根概览；Team Standard 和已有 business 默认原字节保护，新增 Domain 使用 `modus knowledge seed-business --domain <slug> --json` 创建缺失索引。
5. 结构变化先写新落点并通过语义回读，修复生成正文入链和导航，再按读时哈希删除旧生成文件。不得从符号消失、partial 或覆盖缺口直接推导退役。
6. 全局语义回读后运行 `modus knowledge verify --publication --json`，CAS 发布并回读。publication 必须核对 `schemaVersion: 2` 执行卡、正文无源码路径、结构化锚点、逐 Module evidence、Domain coverage 和 visual 决定；`clean` 仍不是正文质量证明。大量同长度短文、没有真实场景、只有导航表、状态专题无转换或证据只落在文件首行时继续修订。不得提前删除执行卡，也不得在丢失后根据输出重建一张更小的“全部 reviewed”卡。只有全部确认目标达到终态且语义回读、实际 publication 与发布后回读都通过才清理执行卡；普通机械核验不能替代 publication。真实报告 unchanged、修订、删除、冲突与缺口。
