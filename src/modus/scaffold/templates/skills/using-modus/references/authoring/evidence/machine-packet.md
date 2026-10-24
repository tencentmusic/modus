<!--
证据包是有界导航，不能替代作者的业务判断。
包摘要绑定同一轮输入，修改读取流程时保留基线一致性检查。
省略计数与展开句柄共同说明预算边界。
不可用提供方的回执是能力缺口，不能按空事实解释。
局部查询的范围必须与调用方问题一致。
-->

# 机器证据包消费合同

N6 Authoring Context Packet 是有界导航层，不是正文草稿。它可以提供 capability proposal、代表性入口到效果路径、权威对象和终止信号、coverage receipt、omitted count、ambiguity、remainder、needs-split 与定向展开句柄，但不能决定 Domain/Module，也不能证明运行时必然关系。

## 一次构建，按问题读取

单仓 init/reinit 每轮至多构建一次证据包。只消费本轮成功回执绑定的 `bundleDigest` 与 `baselineDigest`；构建失败、校验失败或局部 Provider 不可用时，立即使用当前源码、配置和测试继续，不重试构建，也不回退旧包。

不得直接读取或解析 `modus/.cache/init-analysis/bundles/**` 中的 catalog、data、manifest 或其他内部文件。内部存储布局不是作者 API；绕过 `context`/`select` 会丢失预算、coverage、omission、当前源码漂移检查和稳定错误语义。

构建成功后保存双摘要，严格按任务意图消费：

```text
# K1：第一次结构判断，必须先执行
modus internal init-analysis context --root . --bundle-digest <bundleDigest> --baseline-digest <baselineDigest> --intent scope-discovery

# K3：每个 Module 或不可分割的同场景 Module，至少带一个精确 selector
modus internal init-analysis context --root . --bundle-digest <bundleDigest> --baseline-digest <baselineDigest> --intent module-authoring --candidate-id <candidate-id>

# 也可以直接消费 packet 返回的 capability/path/symbol handle
modus internal init-analysis context --root . --bundle-digest <bundleDigest> --baseline-digest <baselineDigest> --intent module-authoring --capability-id <capability-id>

# Domain 回读前：复用该 Domain 已确认的 candidate/capability/source path/symbol 参数
modus internal init-analysis context --root . --bundle-digest <bundleDigest> --baseline-digest <baselineDigest> --intent coverage-audit --candidate-id <candidate-id>
```

`module-authoring` 不带 candidate、capability、path 或 symbol 时是调用错误，不能用全仓宽包替代逐场景调查。`requestedScope` 必须能映射到当前一个 Module；Domain slug、整包目录或同时覆盖多个不同任务的宽 selector 只可作为导航，不能让任何 Module 进入 `evidence-ready`。只有触发、权威结果、完成信号和恢复责任确实属于同一不可分割场景时，多个 Module 才能共享请求，并在执行卡说明理由。每个 context 都回显 `bundleDigest`、`baselineDigest` 和 `requestedScope`；先核对它们与执行卡一致，再消费 proposal、coverage、omitted count、ambiguity 和 expansion handles。

`coverage-audit` 必须复用当前 Domain 已确认的 candidate/capability/source path/symbol selector 并取并集。`modus/knowledge/**`、执行卡和其他生成文档是调查结果，不是源码 selector；传入这些路径的调用无效。`no-matching-evidence`、空结果、partial 或 budget-exhausted 不阻断直接读源码，但不能记录为 coverage 完成，必须基于公开入口族和源码 selector 补做覆盖回读或保留具体缺口。

先用 `scope-discovery` 识别入口族、候选边界和稳定身份，再围绕当前决定使用 candidate、capability、boundary、path 或 symbol 句柄收窄。`select` 只用于 context 暴露的精确补证问题，例如：

```text
modus internal init-analysis select --root . --bundle-digest <bundleDigest> --baseline-digest <baselineDigest> --view evidence --path <repository-relative-path> --symbol <qualified-symbol> --json
```

`select` 的唯一继续条件是：

> 未展开内容是否可能改变 Scope 决策、公开入口归属或当前正文结论。

`nextCursor` 非空只表示仍可展开，`null` 只表示该查询耗尽；两者都不是完成门槛。续页必须原样复用过滤条件和上一页 cursor，修改页大小或不带 cursor 重跑都不是续页。

## 字段解释

| 字段族 | 可以支持 | 不能单独证明 |
| --- | --- | --- |
| proposal / candidate | 定位可能的能力、入口和责任边界 | 正式 Domain、Module 或业务名称 |
| navigation / representative path | 指向应回读的实现区域 | 完整调用链或全部分支 |
| source witness | 证明一条局部声明来自哪里 | 整个场景、事务或运行时可达性 |
| coverage / omitted count | 暴露机器已见范围和未展开规模 | 正文覆盖完整或能力不存在 |
| ambiguity / remainder / needs-split | 提醒作者保留歧义或拆分调查 | 自动拆分边界或退役结论 |
| expansion handle | 对当前问题定向补证 | 遍历全仓的理由 |

解析器 `partial`、未解析引用和 Provider 缺失只降低对应证据强度。候选调用、目录邻近、同名类型、依赖声明和机器聚类都必须经装配、调用方、协议、配置、读写或测试复核，才能进入正式正文。

context 无匹配证据、source-changed、partial 或 budget-exhausted 时，把具体缺口写入执行卡并直接读取当前源码。不要扩大为无 selector 的 `module-authoring`，不要重新 build，也不要把缺口改写成“能力不存在”。

同一 Domain 内先从执行卡核对 Module 到精确 selector 的映射，再执行不重复的 context 请求；相同 selector 和双摘要不得因写不同专题而重跑，互不依赖的精确请求可并发取得。汇总 packet 给出的 source anchor、path 和 symbol，去重后分批读取当前源码，一次场景调查同时服务六专题与 Module。结论改变、证据缺口或上下文压缩后原证据已不可用时，按[逐域加载与恢复](scope-modeling.md#逐域加载与恢复)定向重新请求或回读所需证据；恢复不重跑 build、不读取 bundle 内部文件，也不触发全仓重扫。原证据仍在当前上下文且身份与范围一致时复用，避免逐文件、逐章节反复 `sed`/搜索。同一 Domain 只能有一个正文所有者；用户明确授权时，不同完整 Domain 可以按[并行撰写协议](../parallel-domain-authoring.md)由不同作者处理。
