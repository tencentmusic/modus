# K1～K6 正文创作入口

init/reinit 按六个阶段入口执行；每个入口明确输入、必读细则、动作、产出与退回条件。入口负责编排，共享细则各有唯一所有者，不把整套规则复制六遍。

| 阶段 | 文件入口 | 可检查的产出 |
| --- | --- | --- |
| K1 范围建模 | [k1-scope.md](stages/k1-scope.md) | 完整范围、入口/材料处置、稳定身份与授权 |
| K2 创作计划 | [k2-plan.md](stages/k2-plan.md) | 目标页、主定义、依赖、案例/图形与检查点计划 |
| K3 证据闭环 | [k3-evidence.md](stages/k3-evidence.md) | 逐接口/字段/规则/场景事实、来源与具名缺口 |
| K4 领域成稿 | [k4-domain.md](stages/k4-domain.md) | 六专题、全部模块与路由，以及逐篇验收 |
| K5 项目约束 | [k5-constraints.md](stages/k5-constraints.md) | Team Standard、规则适用边界与独立验收 |
| K6 系统概览与发布 | [k6-publish.md](stages/k6-publish.md) | 消费 K4/K5 的系统概览、全局核验与发布结果 |

```text
K1 确定完整范围
  → K2 全局主定义与跨域依赖计划
  → 当前 Domain：K2 细化 → K3 ↔ K4（按契约组/对象/场景推进）
  → 下一 Domain：K2 → K3 ↔ K4
  → K5 项目约束 → K6 系统概览与发布
```

阶段不是新增机器状态。续作首先实际读取唯一执行卡，按[上下文保存与恢复](context-continuity.md)定位当前阶段和最早未完成条目；不从 K1 重启，不凭压缩摘要生成正文。

## 共享细则

K4 交付业务事实和场景，K5 从原始证据中提炼工程要求，K6 消费两者形成系统入口。已有规范始终是前序阶段的输入；新规范不能倒过来证明实现已经符合要求。跨域关系从 K2 开始维护，K6 复核最终双方文件。各阶段只修复自身负责的问题，证据变化时定向重开受影响主定义，不重做整轮调查。

- [证据](evidence/index.md)：凭什么写，如何覆盖材料并闭合事实。
- [框架](framework/index.md)：写到哪里、业务解释与图文质量、各产物的详细合同。
- [发布](publication.md)：逐篇回读、实际预览、机械核验、CAS 与清理。
- [增量维护](incremental.md)：update/sync 的影响传播、约束边界、定向验收与冲突恢复。
- [上下文](context-continuity.md)：压缩前保存、摘要保留项、异常恢复与作者交接。
- [跨域协作](cross-domain.md)：主定义、依赖、共享基线、冲突传播与双向核对。
- [执行策略](execution-strategy.md)：工作单元、样稿与可用时的独立读者测试。
- [并行协议](parallel-domain-authoring.md)及[固定委托合同](domain-worker-prompt.md)：只在用户已明确授权委派时加载。

update/sync 从增量维护入口复用受影响范围的证据、框架和发布细则，不运行全量六阶段、不建初始化卡、不消费 bundle，也不为新增配图要求扩大局部写入范围。Python 不生成、扩写或评分自然语言正文，机械 clean 不代表业务正确、完整或可读。
