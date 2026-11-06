<!--
证据包是有界导航，不能替代作者的业务判断。
包摘要绑定同一轮输入，修改读取流程时保留基线一致性检查。
省略计数与展开句柄共同说明预算边界。
不可用提供方的回执是能力缺口，不能按空事实解释。
局部查询的范围必须与调用方问题一致。
-->

# 机器证据包消费合同

N6 Authoring Context Packet 使用 `schemaVersion: 1`，契约随 CLI 与正文模板同步更新；分析包、select 页也各自使用版本 1。它是有界导航层，不是正文草稿，可以提供 capability proposal、代表性入口到效果路径、权威对象和终止信号、coverage receipt、omitted count、ambiguity、remainder、needs-split 与定向展开句柄，但不能决定 Domain/Module，也不能证明运行时必然关系。

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

`coverage-audit` 必须复用当前 Domain 已确认的源码请求并取结果并集。同一轴内多个值取并集，不同轴之间是交集；不得把 Module A 的 candidate 与 Module B 的 path 混入一次请求当作 OR。分别请求各 Module 的精确范围，再按 `recordId`/源码位置去重；卡中 `selector` 的 `OR` 表示这些独立请求的结果并集，不是 CLI 参数。`modus/knowledge/**`、执行卡和其他生成文档是调查结果，不是源码 selector；传入这些路径的调用无效。`no-matching-evidence`、空结果、partial 或 budget-exhausted 不阻断直接读源码，但不能记录为 coverage 完成，必须基于公开入口族和源码 selector 补做覆盖回读或保留具体缺口。

先用 `scope-discovery` 识别入口族、候选边界和稳定身份，再围绕当前决定使用 candidate、capability、boundary、path 或 symbol 句柄收窄。`select` 只用于 context 暴露的精确补证问题，例如：

```text
modus internal init-analysis select --root . --bundle-digest <bundleDigest> --baseline-digest <baselineDigest> --view evidence --path <repository-relative-path> --symbol <qualified-symbol> --json
```

`select` 的唯一继续条件是：

> 未展开内容是否可能改变 Scope 决策、公开入口归属或当前正文结论。

`nextCursor` 非空只表示仍可展开，`null` 只表示该查询耗尽；两者都不是完成门槛。续页必须原样复用过滤条件和上一页 cursor；允许调整预算，但只改页大小或不带 cursor 重跑不是续页。`expansionQueries` 给出公开 select 的完整初始过滤条件；只有省略内容可能改变当前判断时才重放该查询，随后用 select 返回的 cursor 接续。不把 packet 中的缺口或被裁剪内容当作已读。

## 六阶段消费与可恢复记录

| 当前问题 | 机器入口与应消费内容 | 作者负责的出口 |
| --- | --- | --- |
| K1 完整范围 | `scope-discovery`；reinit 用 `reinit-diff`；核对 `evidence` 中的 scopeSummary、候选、入口库存、remainder/needs-split 与省略 | 全部相关入口族的归属、共享、排除或具名缺口 |
| K2 共享边界 | `service-boundary`，按相关 boundary/candidate/path 收窄；`evidence` 中的 serviceRelation 包含入边和出边 | 交接双方、主定义、依赖顺序及待补证的一侧 |
| K3 场景与规则 | 逐 Module `module-authoring`；涉及规则目的/作用范围时用同范围 `constraint-extraction` | 当前事实、关键条件、反例/限制、源码回读及专题/模块落点 |
| K4 覆盖审计 | 独立源码请求的 `coverage-audit` 结果并集；`evidence` 中的 sourceFile/sourceEntry/sourceRelation 与 `coverageGaps` | 对照已确认入口清单，查漏落点、遗漏分支及无法证明的关系 |
| K5 项目约束 | 复用 K3 同源 `constraint-extraction` 信号；按机制与使用者范围补充查询，覆盖构建/CI/装配等共享工程路径 | 原始依据、强制机制、反例与适用范围支撑规则性质；K4 正文用于定位使用者，不升级为政策证据 |
| K6 系统概览与消费对账 | 按交接范围复用 `service-boundary` / serviceRelation，反查 K4/K5 最终文件；仅补查未决或失效范围 | 系统关系、规范入口和完成口径一致；每个相关事实或缺口有落点、排除理由或明确未决影响 |

`reinit-diff` 当前交付的是本轮范围证据，**不计算新旧差分**。作者结合已有稳定知识身份、旧正文与当前源码分类 unchanged/anchor-only/implementation-change/scope-change/content-repair，不能把该 intent 名称当作机器已证明“未变”或“退役”。

packet 的 `requestedScope` 是 candidateIds/capabilityIds/boundaryIds/paths/symbols 对象，必须与实际请求参数逐轴核对；执行卡的 `evidence.requestedScope` 是 `module:<domain>/<module>` 知识身份，两者不能直接比较相等。在原卡正文保存“Module ID → 实际命令/请求对象 → 双摘要 → 已读记录/源码位置 → 事实及正文落点”的映射。候选摘要及其代表路径可包含定位当前场景所需的周边信息，不据此将周边全部升级为当前 Module 事实。

复用原卡的场景、结果和缺口部分记录消费处置，不另建 receipt：可按接口族或场景分组记录相关 `recordId`/源码位置、确认的事实与限制、主定义页面/章节，以及用于案例/图的关系；未采用材料写排除理由，待补证项写缺失侧、影响和下一精确查询。无须逐条复制机器数据，但影响范围、完成/恢复或正文结论的证据、反证、歧义及省略必须有处置。已读、已核验、已写入不能混成一个“ready”。

## 回包解释

K5 按“工程主题 → 机制源码范围 → 机器请求/同源记录 → 已核验使用者和反例 → 规范条目”复用原卡记录；不能把跨域工程主题伪装成某个 Module 的 `requestedScope`，也不能为它新增 Module 状态。现有证据足够时直接复用；共享机制缺口按其源码范围查询，跨 selector 轴仍是交集。K6 用最终版本反查这些映射，规范要求、实际行为和待确认项分别保留。

- 同一种信号在不同 intent 中的位置不同：`module-authoring` 优先放在 `proposals[].authoringSignals[].details`，未绑定候选的放在 `ambiguities[].signal.details`；`constraint-extraction` 和 `coverage-audit` 按 kind 将扁平 `authoringSignal` 分别放在 `proposals`（entry）、`terminalEffects`（effect）、`authoritativeObjects`（resource）。不能只读 `evidence` 或只读候选摘要而漏掉这些材料。按 `recordId` 识别同源记录，结合 `recordType`、`evidenceKind`、来源和精度解释，不能仅凭所在数组把资源线索认作权威实体、把写入线索认作最终完成。
- `evidence` 保留完整记录身份、kind、resolution、sourceLayer、witness 和 details。scopeSummary/sourceFile 是库存导航；sourceEntry/sourceRelation/serviceRelation 是待核对的声明或关系，均不自动证明业务结论。
- `coverageGaps` 汇总主查询、信号、库存和路径查询缺口；源码漂移、不可读或只有缺口时不能成为 complete。与当前结论有关的缺口即使已有其他正向证据仍需处理。
- 大量连续缺口可以汇总为 `machine.packet.coverage-gap-summary`；`totalCount`、原因计数和代表项只说明范围，不表示详情已读。需要详情时按其中 `expansionQuery` 从头查询 `recordTypes: ["coverageGap"]`，再用该查询自己的游标分页。缺口专用页可以只有 `coverageGaps`；普通页有正向证据也不能消除相关缺口。
- 服务边界的限定名、显示名和稳定 ID 分别使用。调用推导的资源引用、动态名称和已声明资源不等于已部署资源；无来源记录会成为具名缺口，需回到对应配置或调用补证，不能引用无关文件填充来源。
- `coverageReceipt` 描述**本包交付**，counts 对应最终裁剪后的内容；候选内的上游 receipt/精度还要单独阅读。complete 不证明源码完整、所有入口已归属或正文已消费。`representativePaths` 计数按整条路径，`navigationSteps` 按步骤；步骤具有 stepIndex，按 capabilityId/pathIndex 分组，不能把不同路径拼接成一条。
- `omittedCounts` 包含未交付记录、路径或仍有后续页的查询数，后者不是精确剩余记录数。预算内只交付连续且有终点的代表路径；未交付路径、被裁剪缺口仍可通过保留的 `expansionQueries` 定向查看。
- `expansionHandles` 的 boundary 用 `--boundary-id` 定向读取 services；candidate/capability/path/symbol 各用对应参数。`expansionQueries` 是可选取证入口，不是要求耗尽全部游标的任务清单。

实际如何把入口、关系、资源和效果线索转为接口、字段、规则、状态、协作与模块正文，按[事实投影](scenario-closure.md#从机器线索到正文主定义)执行。充分利用机器层指复用与当前读者问题有关的证据、限制和反证，不指把所有记录粘进正文或强制耗尽整个包。

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

边界过滤仅适用于 `service-boundary` intent 或 `select --view services`；其他组合明确拒绝，不能把回显的 boundaryIds 当成已执行过滤。文件相关信号若没有声明归属，会保留为 unbound 歧义及展开线索，不属于提案的已绑定证据；代表路径以外的已观察关联仍可交付，但不证明遍历完整。

### 对象与入口库存

`sourceEntry.objectFacts` 表达声明类型、显式初始化、注解依据、可选成员和明确序列化名；枚举实参仍是声明事实，不自动等于线上的编码。`hasInitializer: false` 不代表值为 false；Java `Boolean` 与 `boolean`、省略与 null、字段初始化与反序列化/业务赋值分别核对。解释深度按[对象合同](../framework/deliverables/object.md)，需要运行结论时继续回读构造、映射和使用者。

公开记录的细节也有长度边界：`<字段名>OmittedCount` 表示列表省略项数，材料关联的 `entryIdsOmittedCount` 表示同名候选未展示数量；需要补证时按材料原文与符号查询定位，不能把展示候选认作全部。`signatureOmittedCharacters` 合计上游观察和公开投影的已知签名截断量，`initializerOmittedCharacters` 表示初始化表达式省略字符数。它们不是完整声明；若省略部分影响类型、默认或行为判断，按见证位置回读当前源码，不能把展示前缀当作完整值。

`sourceEntry.capabilitySeed` 保留有效入口摘要与 `expanded / not-expanded` 及原因；深度展开预算不删除入口。按真实入口集合逐项对账，区分未展开、未解析和确实不存在；查询不重新执行 N4。
