# K1：范围建模

把当前源码、已有知识和用户材料转成完整且稳定的 Domain/Module 范围。新一轮 init/reinit 从这里开始；续作先走[上下文保存与恢复](../context-continuity.md)，不重新调查已确认范围。

## 输入与必读

- 输入：当前工作流、用户授权、已有知识树、本轮构建结果或不可用原因。
- 读取[证据原则](../evidence/index.md)、[机器证据合同](../evidence/machine-packet.md)、[范围与执行卡](../evidence/scope-modeling.md)。
- reinit 同时读取现有 Domain/Module 身份、人工材料和相关正文，按稳定身份比较变化。

## 执行

1. 单仓每轮同步执行至多一次 `modus internal init-analysis build --root . --compiler auto --json`，等待自然完成，记录双摘要及构建回执的覆盖/诊断摘要。init 请求 `scope-discovery`，reinit 请求 `reinit-diff`；只经 context/select 消费机器证据。失败或结果不可确认时记录原因，回当前源码，不重试构建或读取旧包。
2. 按[材料覆盖](../evidence/index.md#材料覆盖)盘点全部已确认材料，逐步读完相关子目录、子文档及授权网页功能；不能用机器包或网页目录代替内容核验。读取现有 global/team 规范及其适用范围，按[团队规范合同](../framework/deliverables/team-standard.md)记录 Team Standard 的实际状态、读时哈希、维护授权与保护边界；现有要求从本阶段起参与判断。将来源缺失、冲突和影响写入执行卡。收集团队明确偏好（格式、注释、方法组织、工具与复用要求）及声明范围；按服务/包/构建单元记录语言版本、目标平台、运行环境和实际工具配置。按[规范选择合同](../../../../modus-init/references/constraint-profiles/composition.md)形成候选；材料要求与当前生效情况分开，不从解析支持推断规范覆盖。
3. 核对 packet 的范围库存、候选、remainder/needs-split、coverageGaps 和省略；按机器合同定向补齐会影响边界的条目，记录其处置。为全部公开入口族确定正式 Domain/Module、跨域平台能力、共享基础设施或有理由的排除；未决项具名记录。以业务结果、权威对象和变更责任划分，不能从目录、类名或聚类直接生成业务域。
4. 建立唯一 `modus/.cache/knowledge-authoring/scope-confirmation.md`，按范围合同初始化 `schemaVersion: 2`，保留完整调查、稳定 ID、selector、Surface、证据会话与 `pending` 状态。按[跨域协作](../cross-domain.md)记录已知依赖和主定义归属，未知边界不猜测。
5. init 合并确认完整结构；reinit 只确认真实新增、拆并、迁移、改名或已证明退役。按范围合同输出完整表格和执行选项；已有完整授权直接沿用。并行必须有明确授权，不能因确认范围自动委派。

## 产出与出口

执行卡中的完整范围、入口处置、材料清单和授权依据足以复核后，进入 [K2 创作计划](k2-plan.md)。确认尚未取得时保留调查结果，等待用户；不写正式正文。身份或边界争议留在 K1，资料细节缺口交 K3 定向补证。
