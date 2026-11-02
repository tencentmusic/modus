# K4：领域成稿

把当前完整 Domain 写成可独立阅读、用于理解、开发和排障的手册，并逐篇验收。正文暴露证据缺口就返回 K3，不先填模板套话。

## 输入与必读

- 输入：本域执行卡、K3 事实与清单、相关已有正文、已接受的跨域交接。
- 每次进入或恢复先执行[上下文保存与恢复](../context-continuity.md)；完整读取下列适用合同，不能用上一个域的摘要代替。

| 当前产物或问题 | 共享细则 |
| --- | --- |
| 全部正文 | [框架与质量要求](../framework/index.md)、[布局](../framework/layout.md)、[Surface](../framework/surface-profiles.md)、[本地化](../framework/localization.md)、[编辑](../framework/editorial.md)、[图文](../framework/visual-expression.md) |
| 领域与场景 | [Domain](../framework/deliverables/domain.md)、[Module](../framework/deliverables/module.md) |
| 六专题 | [总则](../framework/deliverables/topics.md)、[API](../framework/deliverables/api.md)、[Object](../framework/deliverables/object.md)、[Rule](../framework/deliverables/rule.md)、[State](../framework/deliverables/state-machine.md)、[Downstream](../framework/deliverables/collaboration.md)、[Infrastructure](../framework/deliverables/infrastructure.md) |
| 回读与写入 | [发布合同](../publication.md)、[跨域协作](../cross-domain.md) |

## 执行

1. 按[工作单元](../execution-strategy.md#在现有阶段内组织工作)先稳定当前场景涉及的专题主定义，随即写出对应 Module 场景、案例与图并交叉回读，再进入下一单元；不要求等全域六专题全部写完才开始模块。全部单元完成后补齐专题总览与 Domain 路由。每次写完整契约组、对象或场景并立即对账、编辑、保存进度；大域按单元继续同一深度，不把后续模块压成摘要。
2. 逐接口解释业务契约，逐对象/字段解释含义与变化，逐规则展开目的、条件、顺序、影响与复核，逐状态解释转换，逐协作解释输入输出、交接、失败责任，逐资源解释配置、生效和故障。详细要求以上表为准；一句话、名称清单和相同三段式不算成稿。
3. 每个模块兑现贯穿案例与关键流程图，每份状态、协作文档兑现本页图形，并配文字解读。明显不同的路径分别展开；无持久状态用真实阶段流程，未实现的重试/取消/降级不得补造。图、表、案例与正文使用相同术语、条件、状态与完成口径。
4. 保持既定结构、层级和元数据，保护人工内容；整合重复说明，精确链接事实主定义。重要结论的可定位来源进入现有 frontmatter `anchors.locations`，正文解释怎样复核，不堆源码路径或证据清单。每次写入都遵循读时哈希、锁、CAS 和原子替换，不能拖到 K6 才启用保护。
5. 完成本域后用确认过的 candidate/capability/source path/symbol 范围请求 `coverage-audit`。逐请求合并结果，按 sourceFile/sourceEntry/sourceRelation 与公开入口清单反查正文落点，并核对 coverageGaps/省略的处置；不同 selector 轴不能直接当作 OR。不使用 `modus/knowledge/**`；空、partial 或 no-match 不算 audited，按机器合同补查或记录带原因的源码回退。
6. 按[逐篇验收](../publication.md#逐篇验收与事实对账)完整回读六专题及分片、全部模块和路由，从清单查遗漏、从证据查结论、跨页查条件。首个有图页面就验证渲染能力，整页预览、逐图核验事实/渲染/布局，发现问题修订后重看。不能把 Markdown 围栏存在当作实际渲染通过。
7. 运行 `modus knowledge verify --domain <slug> --json`。根作者核对实际文件、逐篇结果和跨域影响，再更新 evidence、coverage、visual、status 和 outcome；根作者抽样只是二次校准，不能替代域内全量回读。工具限制保留具体待验位置，按发布合同区分语义 reviewed 与视觉待验。

## 产出与出口

当前域正文与回读记录完整后，保存[恢复检查点](../context-continuity.md)，下一域回 [K2](k2-plan.md)。所有 Domain 完成语义验收后进入 [K5 项目约束](k5-constraints.md)，交付最终主定义、公共机制使用处、差异和原始依据；系统概览由 K6 消费领域与规范结果后创作。跨域冲突回相关 K3/K4；只有事实边界变化才回 K1，机械 clean 不替代上述验收。
