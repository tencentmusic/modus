<!--
本模板与并行协议共同定义委托边界，维护时成对核对。
输入包必须足够独立执行，不能依赖根作者未传递的上下文。
占位符是待填事实，不是默认推断。
共享文件与业务人工区不归领域工作者拥有。
交接摘要用于验收导航，实际正文仍是最终检查对象。
-->

# 领域工作者委托契约

只有用户已经授权按 Domain 并行，且根作者确认目标 Domain 与其他正在写入的 Domain 没有正文所有权重叠时，才使用本合同。根作者为每个 worker 生成一份完整、可独立执行的任务；不得只发送“把这个域写详细一点”或让 worker 自行重做 Scope。

## 必填输入包

委托前填充下列事实，缺一项就留在根线程补齐：

- Domain 稳定 ID、业务边界、目标自然语言、Surface、构建单元与实现语言；
- canonical 写入根 `modus/knowledge/domain/<slug>/`，以及完整 Module 稳定 ID/中文任务名；
- 唯一执行卡的实际路径、本域条目定位和当前 Domain/Module 进度、缺口与下一动作；工作区同时标明成员身份；
- 每个 Module 独立的 candidate/capability/path/symbol selector 与预期 `requestedScope`；
- 固定 `bundleDigest`、`baselineDigest`，或机器层不可用的明确原因；
- 读时哈希、受保护的 `references/business/**`、共享文件和禁止写入路径；
- 当前 visual 决定、读者问题、机制触发、目标文件和未闭合证据；
- 本域相关已有正文、跨域主定义、人工材料与约束路径，以及待根作者核对的实际文件/交接状态；
- 必读的证据、框架、产物、图文、发布合同及本委托合同路径。

## 委托模板

根作者把方括号占位符替换为当前事实后再发送；不要删除验收与禁止项。

```text
你是 Domain `[domain-id]` 的唯一正文作者。完整负责本域六专题、全部 Module、Domain 路由、图表决定、域级回读和 handoff；不要继续委派本域正文。

目标与边界
- 业务边界：[boundary]
- 目标语言 / Surface / 构建单元 / 语言：[profile]
- 唯一允许写入：[domain-root]/SKILL.md 与 [domain-root]/references/** 中的生成正文
- 禁止写入：references/business/**、其他 Domain、scope-confirmation.md、根概览、Team Standard、源码、Git
- 读时哈希与保护路径：[hashes-and-protected-paths]
- 唯一执行卡（只读）与本域条目：[execution-card-path-and-domain-entry]
- 当前进度、缺口与下一动作：[domain-module-progress-and-gaps]
- 相关已有正文与交接：[existing-content-and-handoff-paths-or-absence]

固定证据会话
- bundleDigest：[bundle-digest-or-unavailable-reason]
- baselineDigest：[baseline-digest-or-unavailable-reason]
- Module 与 selector：[complete-module-selector-map]

必须执行
1. 每次开始或恢复本域，包括上下文压缩后，执行 scope-modeling.md 的“逐域加载与恢复”：先实际读取指定的唯一执行卡，核对本域范围、Module 归属、selector 和进度；再按第 2 步加载对应证据，然后回读相关已有正文与交接，最后完整读取适用写作规范：[required-contract-paths]。完成这套顺序后才从最早未完成动作续作；不得只凭本任务消息或压缩摘要写作。卡片与实际文件不一致时将差异交给根作者核对，不自行改卡或覆盖正文。
2. 取证时按 Module 逐个请求 module-authoring context，并核对 requestedScope 必须等于 `module:[domain-id]/[module-id]`。独立 Module 不得使用整域宽请求替代；失败、空结果或 partial 时回当前源码、配置、SQL、迁移、测试和运行证据定向补查，并在 handoff 说明 fallback。压缩导致证据丢失时按原 selector 定向重新加载，不重跑 build；卡中 ready 不能代替证据读取。
3. 先按真实任务闭合触发、输入、判定、权威写入、返回/异步交接、完成、失败残留、恢复和验证，再把同一事实投影到六专题与 Module；不要为不同文件重复扫描同一链路。
4. 正文写成可独立阅读的工程手册，不是证据目录。仓库源码路径和行号只写入目标文件 frontmatter 的少量 `anchors.locations`；正文不得出现 `path#L`、完整源码路径或“证据”清单。移除 frontmatter 后，正文仍须让新人复述任务、贡献者安全修改、维护者定位失败与恢复。
5. 每个非平凡 Module 使用真实场景 H3，解释独有字段、分支、受理/完成、失败残留、恢复和修改验证。六专题逐项定义契约、对象、规则、状态、协作和资源，不得只列接口、类、枚举、表或中间件。
6. 证据闭合后重新评估 [visual-decisions]。异步交接、持久状态、多条件决策、对象映射和资源生命周期分别登记 readerQuestion、mechanism、kind、target；一张总览图不能豁免独立机制。图表使用业务名称，正文说明方向、责任、完成、失败与恢复。
7. 用本域源码 selector 执行 coverage-audit；不得用 modus/knowledge/**。no-match、空结果或 partial 只能补证或报告缺口，不能宣称 reviewed。
8. 运行本域机械校验，回读实际文件。预计无法保持当前深度时停在 Domain 边界并如实 handoff，不得压缩剩余 Module。

handoff 必须返回
- 实际写入、未写、冲突与保护文件；
- 本域当前进度、未闭合问题、下一动作及执行卡与实际文件的差异，供根作者保存后恢复；
- 每个 Module 的 requestedScope、selector、证据模式、触发/判定/权威写入/完成/失败恢复/验证摘要及缺口；
- 六专题覆盖与每项 visual 决定；
- coverage-audit 的源码范围、结果和本域 verify 结果；
- 三类读者回读、跨域调用、事实所有者、术语和完成信号；
- 建议根作者写入执行卡的 Module evidence、status、Domain coverage、visual 与 outcome 字段。

不要把 verify clean 当作正文质量证明，不要修改执行卡或共享产物。完成 handoff 后等待根作者验收。
```

## 根作者校准

首波选择一个复杂域和一个普通或证据较薄域，并分别发送完整模板。根作者必须读取实际文件而非只看 handoff，校准正文无源码路径、场景深度、六专题主定义、解释型图表与失败恢复；不合格就定向退回原 worker 并修正后续输入包。首波通过前不批量派发剩余 Domain。
