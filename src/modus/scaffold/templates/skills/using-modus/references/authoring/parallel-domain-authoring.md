<!--
并行改变调度方式，不改变领域所有权与验收语义。
一个领域同时只有一个正文作者，公共产物由根作者汇总。
固定摘要用于让各领域共享同一证据会话。
恢复任务先读唯一执行卡，再加载证据、正文与规范，并核对交接状态。
-->

# 按 Domain 并行撰写

并行用于缩短多个独立 Domain 的墙钟时间，并让每个 Domain 在独立上下文中完成证据闭合；它不是质量证明，也不是正确性或 CI 前提。宿主具备 subagent/worker 能力、用户明确授权并行、Scope 已确认、唯一执行卡已建立且至少有两个边界清楚的 Domain 时，才加载本协议。普通的“确认业务域及功能模块”只授权继续撰写，不授权委派；串行执行必须产生相同语义结果。

## 所有权边界

- 一个 Domain 在任一时刻只有一个正文所有者。该作者完整负责本域六专题、全部 Module、Domain 路由、图表决策和域级回读；禁止按文件类型或 Module 把同一 Domain 拆给多个正文作者，也不得继续委派本域正文。
- 根作者独占用户与 Scope 决策、唯一执行卡、根概览、Team Standard、business seed、跨域术语/所有权/主图校准和最终 publication。worker 不修改这些共享目标，不提交 Git，也不改源码。
- Domain worker 只读源码、当前证据和合同，只写被分配的 `modus/knowledge/domain/<slug>/SKILL.md` 与 `references/**` 生成正文；`references/business/**` 仍按人工所有权保护。不得写其他 Domain。
- 强耦合、selector 高度重叠或所有权仍有争议的 Domain 先由根作者消歧，不能靠并行掩盖边界冲突。

## 调度与输入包

根作者保留一个可用槽位和审阅能力，根据可用 worker 槽位分波调度互不重叠的完整 Domain；不要让同一 worker 连续吞下多个 Domain。每次委托必须使用[Domain worker 委托合同](domain-worker-prompt.md)生成完整输入包，不发送只有目标名称的宽泛提示。首波覆盖一个复杂域和一个普通或证据较薄的域，根作者读取实际文件、校准结果和委托模板后再继续后续批次。并发度服从宿主能力，不写死数量。

每个 Domain 的分配包至少包含：

- Domain/Module 稳定 ID、确认后的边界和 canonical 目标目录；
- 唯一执行卡的实际路径、本域条目、Domain/Module 进度、缺口和下一动作；工作区包含成员身份；
- 每个 Module 的 candidate/capability/source path/symbol 精确 selector 映射；
- 固定的 `bundleDigest`、`baselineDigest`、Surface、构建单元与语言；
- 必读的 Evidence、Framework、deliverable、图文和发布合同；
- 当前 visual 候选、用户明确的交付要求、已有编辑安排、读时哈希、保护路径、三类读者问题和允许写入的精确路径。
- 相关已有正文、跨域主定义、人工材料与约束路径，以及待核对的交接状态。

worker 每次开始或恢复本域都按[逐域加载与恢复](evidence/scope-modeling.md#逐域加载与恢复)先只读执行卡，再依次加载对应证据、相关已有正文和写作规范；上下文压缩后也从第一步恢复。输入包和 handoff 只用于定位，不能代替实际读取；卡片与实际文件的差异交由根作者核对。

worker 不重跑 build 或 Scope，不新增、合并、移动或改名 Domain/Module。它逐 Module 请求并核对 `module-authoring.requestedScope`；Domain 级宽请求不能替代逐 Module context。请求失败、空结果或 partial 时回当前方法体、配置、SQL、测试和运行证据定向补查，而不是降低正文深度。

## 领域内闭环

worker 先按场景形成可复用事实，再共同投影到六专题和 Module，避免为不同文件重复扫描同一链路。每个非平凡场景使用真实任务标题展开触发、判定、权威写入、完成、失败恢复与验证，不以 frontmatter、文件清单或导航表代替正文。源码路径和行号只进入各目标文件 frontmatter 的 `anchors.locations`；正文不得出现 `path#L`、完整源码路径或证据清单。

写前按[编辑规则](framework/editorial.md)安排目标页面的读者问题、事实主落点、叙述顺序、图文分工与案例，按需选择[对照样稿](framework/examples.md)；证据闭合后调整已有安排，通过 handoff 交给根作者保存到同一执行卡正文，不新建卡片或 receipt。[执行策略](execution-strategy.md)只能组织上述动作，不降低共享合同，也不授权 worker 继续委派本域。

证据闭合后重新评估 visual 候选。发现异步交接、持久状态、多条件决策、对象映射或资源生命周期时，新增或修订相应决定，并记录读者问题、复杂度触发、表达类型、唯一目标和支撑边；一个 Domain 总览图不能自动豁免 Module 或专题里的独立复杂机制，`waived` 也不能自动豁免用户明确的最低配图要求。

域级 `coverage-audit` 必须复用当前 Domain 的 candidate/capability/source path/symbol selector。`modus/knowledge/**` 是生成结果，不能充当源码 coverage selector；no-match、空结果或 partial 只能触发补证或明确缺口，不能宣称 Domain 已 `reviewed`。

worker 按[发布合同](publication.md)逐篇完整回读本轮六专题及其分片、全部目标 Module 和 Domain 路由，先核对事实与覆盖，再检查行文、图文和案例。使用可用的目标阅读器查看实际预览，修订后重看受影响页面；不可用时记录具体页面、未验证项与影响。独立读者仅是授权和隔离上下文可用时的增强，由根作者按现有委派规则组织；未执行时不能把 worker 自查描述为独立验收。

## 交接与主作者验收

worker 通过任务消息返回 handoff，不新建 receipt，也不直接修改唯一执行卡。handoff 至少说明：

- 输入摘要与逐 Module selector；
- 实际写入、未写和冲突文件；
- 每个 Module 的触发、判定、权威写入、完成、失败恢复证据及缺口；
- 六专题事实覆盖和 visual 决定；
- `coverage-audit` 的精确源码范围与结果、域级 verify 结果；
- 已逐篇回读的目标范围、编辑与实际预览结果、具体未验证项；区分三类读者自查与实际独立读者反馈，并说明跨域调用、事实所有者、术语和完成信号。

根作者读取实际文件和 handoff 后，串行更新唯一执行卡中的 Module evidence/status、Domain coverage、visual 和 outcome。worker 完成或 `verify --domain` 为 clean 都不等于 `reviewed`：根作者至少回读 Domain、六专题与简单/普通/最复杂的代表性 Module，核对正文无源码路径、场景叙事、结构化锚点、解释型图表、行文排版、失败恢复和验证入口，并处理跨域方向与术语差异。该抽查是对 worker 全量逐篇回读的二次校准，不能替代前者；同时核对实际预览范围与未验证项，不把未运行检查记为通过。通过后才把本域标为 `reviewed`；质量偏薄则定向退回原 worker 或由根作者补查。

## 恢复与冲突

worker 超时或失败时，根作者先读取执行卡的本域状态，再核对实际 diff 与 handoff，将已核实进度、未闭合问题和下一动作原位保存，不自动派新作者覆盖。优先让原 worker 定向续写；原 worker 恢复或必须更换作者时，都从[逐域加载与恢复](evidence/scope-modeling.md#逐域加载与恢复)的执行卡读取开始，依次加载证据、实际正文与写作规范，核对初始哈希和交接。卡记 `pending` 而文件已写入时也不能直接重写，须由根作者核对再续作。CAS 冲突只暂停受影响文件或 Domain，不能刷新哈希后盲目覆盖，其他 Domain 可以继续。

唯一执行卡始终由根作者单写，并保留最早未完成状态。不得因批次靠后、上下文变长或时间压力把后续 Domain 压缩为同长度短文。所有 Domain 验收完成后，根作者再串行执行跨域矩阵校准、根概览、business seed、全局语义回读与 publication，最后才删除执行卡。
