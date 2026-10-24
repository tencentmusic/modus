---
name: modus-init
description: 基于当前源码与用户材料，初始化完整的项目知识树。
---

# modus-init

首次建立正文知识时使用。本 Skill 只负责编排；事实规则来自[证据指南](../using-modus/references/authoring/evidence/index.md)，写作规则来自[生成框架](../using-modus/references/authoring/framework/index.md)，收尾规则来自[发布合同](../using-modus/references/authoring/publication.md)。

## 核心不变量

- 当前源码、配置、测试和明确材料提供事实；Agent 判断边界并直接撰写正文。
- 单仓每轮至多构建一次机器证据；失败就回源码，不重试、不读旧包。
- Domain/Module 结构只确认一次；脚本不生成、扩写或评分自然语言正文。
- 每个 Domain 生成前先读本域执行卡，再加载对应证据、相关已有正文和写作规范；压缩恢复后的第一项本域工作就是读卡，不能先查源码或修改正文。
- 人工 constraint/business 默认保护；所有写入使用读时哈希、锁、CAS 和原子替换。

## 本轮必须交付的阅读深度

- **逐接口、逐字段。** 取证时建立精确清单，按[接口](../using-modus/references/authoring/framework/deliverables/api.md#逐接口展开与对账)与[对象](../using-modus/references/authoring/framework/deliverables/object.md#字段闭合)合同逐项展开并对账；契约族和字段组只负责导航。
- **排版与业务叙述。** 按[编辑合同](../using-modus/references/authoring/framework/editorial.md)写足前提、因果、分支、结果及案例，再安排段落、步骤、分组表格和内部导航；不把详实手册压成统一短摘要。
- **复杂场景图文结合。** 每个 Module 的核心场景按[图文合同](../using-modus/references/authoring/framework/visual-expression.md)判断；复杂交接用时序图，条件路径用流程图，精确比较用表格。场景图就近解释完成与失败，不能由域级导航表代替。
- **逐篇验收。** 按[发布合同](../using-modus/references/authoring/publication.md#逐篇验收与事实对账)留下逐页、可定位的对账与编辑结果；缺详情、事实矛盾或已知阅读缺陷未修复时不标 `reviewed`。

## 执行

1. 只读执行一次 `modus status --json`。仅当根配置明确 `kind: workspace` 时转入[workspace 流程](references/workspace-init.md)；普通项目继续单仓流程。
2. 同步运行一次 `modus internal init-analysis build --root . --compiler auto --json`，等待自然完成并记录双摘要。立即按[机器证据合同](../using-modus/references/authoring/evidence/machine-packet.md)请求 `scope-discovery` context；不得直接读取 bundle 内部文件，也不得跳过 context 只按目录命名能力。
3. 按[Scope 建模](../using-modus/references/authoring/evidence/scope-modeling.md)关闭所有公开入口族，形成四类分区和稳定身份，写入唯一执行卡 `modus/.cache/knowledge-authoring/scope-confirmation.md`。卡内 YAML frontmatter 同时初始化精确 Domain/Module 身份、主定义/图形决定、`pending` 状态和 `pending` outcome；正文保存面向人的证据与范围表。
4. 按[Scope 建模](../using-modus/references/authoring/evidence/scope-modeling.md)的固定对话格式输出确认卡链接、完整中文总览表和执行选项，向用户合并确认 Domain/Module 一次；用户已经给出完整范围时沿用授权。宿主支持且范围可安全拆分时，把“按 Domain subagent 并行”和“串行”作为两个同级确认选项，不能把并行藏在附注；串行确认不授权委派。未确认前不写正式正文。
5. 确认后按完整 Domain 批次推进，不先批量创建全库浅层正文，也不采用“先让 verify 通过、以后再精修”的骨架策略。默认串行；仅当用户明确授权且 Domain 边界互不重叠时，才加载[按 Domain 并行撰写](../using-modus/references/authoring/parallel-domain-authoring.md)，并用其中的 [Domain worker 委托合同](../using-modus/references/authoring/domain-worker-prompt.md)分波委托不同完整 Domain。每次进入或恢复当前 Domain，先按[逐域加载与恢复](../using-modus/references/authoring/evidence/scope-modeling.md#逐域加载与恢复)读取执行卡中的本域范围、Module 归属、selector 和进度，再依次加载对应证据、相关已有正文和完整写作规范。下一步细化其中的取证要求；整个加载流程完成前不得开始第 7 步正文生成。上下文压缩后即使仍在同一 Module，也必须从执行卡重新恢复，不能凭摘要直接续写。
6. 对当前 Domain 的每个 Module 分别使用 candidate/capability/path/symbol 请求 `module-authoring` context，核对返回的双摘要与 `requestedScope`；一个覆盖整域多个独立 Module 的宽请求无效，不能推进任何 Module 状态。同场景不可分割的 Module 才能共享请求，互不依赖的精确请求可以并发。请求成功时把执行卡对应 Module 的 evidence 更新为 `ready / machine-context`；请求失败、空结果或 partial 时改用当前源码定向补证，并记录 `ready / source-fallback` 与原因，不能因此降低正文深度或把类名、接口签名和 `#L1` 文件位置包装成场景证据。先汇总并去重精确源码路径/符号，再分批读取方法体、配置、SQL、测试和运行证据；一次调查同时服务专题与 Module，禁止为六专题重复扫描同一链路，也不得并发写同一正文。按[场景闭合](../using-modus/references/authoring/evidence/scenario-closure.md)闭合后，由唯一执行卡作者原位更新状态。
7. 以真实任务为写作单元。写前按[编辑规则](../using-modus/references/authoring/framework/editorial.md)形成页面安排，按需选择[对照样稿](../using-modus/references/authoring/framework/examples.md)，在现有执行卡正文保留安排与用户明确的交付要求，证据闭合后原位调整。先把当前 Domain 的契约、对象、规则、状态、协作和资源写入六专题的唯一主定义，再把这些事实组合成可独立阅读的 Module 场景手册，最后编写 Domain 路由。源码路径和行号只进入各生成文档 frontmatter 的少量 `anchors.locations`；正文不得出现完整源码路径、`path#L` 或“证据”清单，移除 frontmatter 后仍须完整回答行为、边界、失败恢复与修改验证。每个文件先规划内部导航和适合的总览表；遇到状态迁移、异步交接、多条件分支、对象关系或资源生命周期时，用对应 Mermaid/决策表解释，模块清单表不能替代这些解释性图表。禁止用相同的“三段概述＋方法名”批量生成不同 Module，也禁止六专题各写一句职责后结束。
8. 当前 Domain 完成后，复用本域 candidate/capability/source path/symbol 范围请求 `coverage-audit` context，并把执行卡 coverage 更新为 `audited / machine-context`；机器 coverage 不可用时才允许以带原因的 `source-review` 回退。生成后的 `modus/knowledge/**` 不能作为 coverage selector，no-match、空结果或 partial 不能推进 `reviewed`。随后按[发布合同](../using-modus/references/authoring/publication.md)逐篇完整回读本轮六专题及其分片、全部目标 Module 和 Domain 路由，完成事实、编辑与实际预览检查，在卡片已有正文记录未验证项；独立读者按[执行策略](../using-modus/references/authoring/execution-strategy.md)作为可用时的增强。三类读者回读确认新人能否复述完整任务、贡献者能否定位修改与验证入口、维护者能否判断失败残留和恢复责任。发现正文源码路径、接口未展开、字段无语义、状态无转换、下游无失败策略、资源无配置来源或图中关系无证据时，回到源码定向补查并修订；运行 `modus knowledge verify --domain <slug> --json` 后，由根作者回读实际文件并更新执行卡。根作者抽样仅作二次校准，不能替代域内逐篇验收。一个 Domain 同时只有一个正文所有者；并行只发生在互不重叠的完整 Domain 之间。
9. 所有 Domain 均 `reviewed` 后，由主作者校准跨域方向、状态所有者、术语和主图，再按[根概览合同](../using-modus/references/authoring/framework/deliverables/root.md)编写根概览。多 Domain 或多运行单元项目应有一张系统级关系/运行图，并用交接表解释方向、所有者与完成信号。按[Team Standard](../using-modus/references/authoring/framework/deliverables/team-standard.md)只初始化 `missing/framework-seed`；对每个新 Domain 调用一次 `modus knowledge seed-business --domain <slug> --json`，不得手写或在知识根创建 business。
10. 执行一次全局语义回读和一次全局机械核验：运行 `modus knowledge verify --publication --json`。publication 必须核对 `schemaVersion: 2` 执行卡中的逐 Module evidence、Domain coverage、结构化锚点、正文无源码路径和 visual 决定；`clean` 仍不证明正文详实。若出现大量同长度短文、无真实场景 H3、只有导航表、状态专题无转换或锚点集中在文件首行等信号，仍须返回相应 Domain 重写。执行卡必须持续保留完整调查状态；不得在丢失或提前删除后根据现有输出重建一张更小的“全部 reviewed”卡来通过发布。修完机械与语义问题、确认实际执行过 publication、发布并回读实际文件后才删除执行卡、清理空目录，最后可用普通 `modus knowledge verify --json` 复核机械完整性；普通 verify 不能替代 publication 或作为完成依据。

执行中按[写作策略](../using-modus/references/authoring/execution-strategy.md#在现有阶段内组织工作)先完成并验收一组接口/对象或一个场景，再推进当前域的下一组；保存到具体未完条目，压缩后恢复同一深度。机器 `clean` 仅表示完整性检查通过。最终结果必须同时报告实际写入、删除、未处理原因、逐篇验收与实际预览范围，以及仍然存在的证据缺口。
