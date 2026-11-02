---
name: modus-init
description: 基于当前源码与用户材料，初始化完整的项目知识树。
---

# modus-init

首次建立正文知识时使用。正文执行路线只有[六阶段入口](../using-modus/references/authoring/index.md)，质量与写入规则在其共享细则维护；本文件负责选择工作流。

## 先判断新任务或续作

开始 status、build 或调查前，先检查唯一执行卡 `modus/.cache/knowledge-authoring/scope-confirmation.md`。存在未完成卡，或当前请求/宿主是在继续中断任务时，先实际读卡并执行[上下文保存与恢复](../using-modus/references/authoring/context-continuity.md)，再进入记录的阶段。压缩、容量/服务错误、工具中断、取消后继续都适用；不得凭摘要续写、重跑 build 或重做 Scope。原卡缺失/冲突按恢复合同处理，不从已有输出拼装缩小的完成卡。

确属新一轮任务时，只读执行一次 `modus status --json`。仅当根配置明确 `kind: workspace` 时转入[workspace 流程](references/workspace-init.md)；普通项目进入下表。已有正式完整知识且本轮需要全量重建时转 [modus-reinit](../modus-reinit/SKILL.md)。

## 六个阶段入口

| 阶段 | 必须读取的入口 | 本工作流的动作 |
| --- | --- | --- |
| K1 | [范围建模](../using-modus/references/authoring/stages/k1-scope.md) | 本轮构建一次、scope-discovery、完整调查与一次范围确认 |
| K2 | [创作计划](../using-modus/references/authoring/stages/k2-plan.md) | 全局依赖与主定义先行，再安排当前域的目标与验收 |
| K3 | [证据闭环](../using-modus/references/authoring/stages/k3-evidence.md) | 逐 Module 精确取证、逐接口/字段/规则/场景核对 |
| K4 | [领域成稿](../using-modus/references/authoring/stages/k4-domain.md) | 完成六专题、模块与路由，逐篇回读和实际预览 |
| K5 | [系统组装](../using-modus/references/authoring/stages/k5-system.md) | 双向核对跨域事实，根概览、缺失规范与 business seed |
| K6 | [核验发布](../using-modus/references/authoring/stages/k6-publish.md) | 全局回读、publication、发布后核验及原卡清理 |

K1 后先做全局 K2，再按完整 Domain 循环 K2 → K3 ↔ K4，全部域完成后执行 K5/K6。进入阶段时完整读取入口列出的适用细则，不只读此表。默认串行，只有用户明确授权且边界可拆分时才按[并行协议](../using-modus/references/authoring/parallel-domain-authoring.md)委派；范围确认不自动授权 subagent。

## 不变量

- 质量优先于一次写完的域数。遵守[初始化质量要求](../using-modus/references/authoring/framework/index.md#初始化质量要求)，全面覆盖已确认材料与正文，并完成相应案例、图形与实际预览。
- 每个可恢复单元都保存具体条目、关键判断、跨域关联和待验项；压缩后重新加载，不能降低后续域深度。
- 一个 Domain 同时只有一个正文作者；根作者独占执行卡、共享事实与最终验收。跨域信息按[协作合同](../using-modus/references/authoring/cross-domain.md)持续传播，不等 K5 才拼接。
- 人工 constraint/business 默认保护；全部写入遵守读时哈希、锁、CAS 与原子替换，脚本不批量生成自然语言正文。
- publication clean 不替代内容与视觉验收；存在待验位置时保留原卡并如实说明。
