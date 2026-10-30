<!--
语义回读、机械核验与安全写入是三个独立责任。
机械检查通过只能证明可检查的不变量。
读时哈希保护编辑期间的人工变更，不能省略冲突处理。
发布回执描述实际写入结果，不反向证明正文深度。
-->

# 语义回读、机械核验与安全发布

发布分成三个不能互相替代的层次：Agent 语义回读、确定性机械核验、安全写入。

## 语义回读

只做一次全局回读，并对发现的问题定向返回：

- 新人能否理解系统/Domain 边界并复述一个完整场景；
- 贡献者能否找到主定义、修改点、扩展边界和真实验证入口；
- 维护者能否区分受理与完成，定位失败残留及自动/人工恢复；
- 公开入口、关键字段、规则、状态、资源与协作是否各有唯一主定义；
- 跨域方向、事实所有者、术语和完成信号是否一致；
- 图是否必要、可由证据逐边支持，并且没有重复主图。

Domain 阶段逐个回读本域 Module；全局阶段至少覆盖最薄、最新和最复杂的 Domain，并在每个被抽查 Domain 中读取 Domain 路由、六专题以及简单、普通和最复杂的代表性 Module。回读时隐藏 frontmatter，只根据正文判断开发者能否说明怎样运行、哪里权威写入、何时完成、失败停在哪里以及怎样修改和验证。正文不得出现完整源码路径、`path#L` 或“证据”清单；限定符号只有在解释修改责任或扩展点时保留。不同 Domain 若明显分成“详实工程手册”和“同长度摘要”两档，且没有事实复杂度理由，不能发布。

出现下列模式时，即使 publication 验证为 `clean`，也要返回对应 Domain 重写，而不是直接发布：

- 大量 Module 是同长度短文、相同三段话或没有真实场景 H3；
- API 只有“调用 Service 后返回”，Object 只有类名，Rule 只有职责介绍；
- State Machine 已出现多个持久状态却没有迁移表或状态图；
- Downstream 只列依赖名，Infrastructure 只列中间件名；
- 图表只有目录树、Module 导航表或名称对照，没有解释真实方向、状态、决策、关系或生命周期；
- frontmatter 源码锚点大多集中在文件首行、类声明或文件列表，无法支撑触发、判定、写入、完成与恢复；
- Team Standard 没有把本项目的命名、结构、模块边界、注释、错误处理、扩展兼容和一致性机制落实为可执行约束。

抽查不是固定篇幅、标题数或图数门禁。它要求作者回到实际事实判断：本页是否让目标读者完成任务，表格是否精确，图是否解释了真实复杂关系，源码证据是否支撑正文结论。

发现边界变化回到 Scope；发现证据缺口回到场景闭合；发现跨域冲突回到相关 Domain。不要用根概览的宽泛描述掩盖下层冲突。

## 机械核验与发布承诺

普通 `modus knowledge verify --json` 只检查机械完整性：Markdown 可读与 fence 闭合、canonical 知识路径、相对链接和锚点、仓库相对源码引用、锚点漂移、本机绝对路径、高置信敏感值、路径/符号链接安全，以及声明过的 Module metadata 能否解析且不与物理身份冲突。需要局部反馈时可以运行 `--domain <slug>`。

init/reinit 终稿在删除执行卡之前运行一次 `modus knowledge verify --publication --json`。发布模式要求 `schemaVersion: 2` 执行卡，并额外核对：确认的 Domain/Module 是否全部落地并 reviewed；每个 Module 是否记录精确 requestedScope、selector 与 ready evidence；每个 Domain 是否完成源码 coverage；outcome 是否终结；四个 Domain Business 索引是否位于 canonical 路径；implemented Module 是否有至少一个 frontmatter `anchors.locations`；机器生成正文是否没有源码路径；每项图表决定是否记录 readerQuestion/mechanism 并按 visual id 落地或带理由豁免。

验证器不得要求固定标题、章节顺序、H3/分片数量、topic 齐全、页首导航、business 固定字节、额外 coverage receipt、方法级证据预算、全局图数量或中文正则。普通 `clean` 只表示机械完整；publication `clean` 只表示结构化证据、执行状态和声明的发布承诺已兑现。两者都不替代正文真实性、充分性、可读性和专业性的人工语义回读。

## CAS 发布

`modus knowledge update` 只接受项目根相对的 `modus/knowledge/` 下 Markdown 路径。`documents` 和 `deletions` 不得混入根目录 `README.md`、`evidence.md`、源码或测试；需要同步这些普通项目文件时，按任务授权使用宿主编辑工具单独修改。路径或请求形状不合法时，CLI 在任何写入前拒绝整批请求（退出码 `2`）；这与合法请求执行中的逐文件 CAS 冲突不同。

通过 `modus knowledge update --input <更新请求.json>` 提交，临时 JSON 放在正式知识目录之外。输入字段如下；示例中的路径、完整正文和摘要都要替换为本轮真实值：

```json
{
  "documents": {"modus/knowledge/domain/example/references/rule.md": "修订后的完整 Markdown"},
  "expectedHashes": {"modus/knowledge/domain/example/references/rule.md": "读取原正文时记录的 SHA-256"},
  "deletions": [],
  "allowTeamStandard": false
}
```

摘要按原正文的 UTF-8 编码计算，例如 `hashlib.sha256(before.encode("utf-8")).hexdigest()`；`before` 必须是本轮理解、修订所依据的完整读取结果。新建文件的预期摘要为 `null`，删除已有生成正文时在 `deletions` 列出路径并提供原摘要。普通同步保留 `allowTeamStandard: false`，不写人工约束或业务资料。退出码 `1` 表示存在逐文件冲突，已成功的写入不会回滚；检查报告的 `writes`、`unchanged`、`deleted` 和 `conflicts`，重读冲突正文后重新判断，不能只刷新摘要重试。

1. 完整读取目标并记录哈希；内容不变就跳写。
2. 新增先写目标并回读；更新保持原语义位置，不追加日期式 changelog。
3. 移动先写新落点、修复全部入站链接和导航，再按原读时哈希删除旧生成文件。
4. 人工 constraint/business 默认不改不删；明确授权时仍使用 CAS。
5. 冲突只重读受影响目标，禁止刷新哈希后盲目覆盖。
6. 发布后回读实际正文；只有 `schemaVersion: 2` 执行卡中的全部已确认目标均为 `reviewed`、每个 Module evidence 为 `ready`、每个 Domain coverage 为 `audited`、每个 Domain 有 `changed / unchanged` 终态，根概览和 Team Standard 已完成，且本轮实际运行的 `modus knowledge verify --publication --json` 为 `clean` 时，才删除执行卡并只清理空目录；存在 `blocked` 时保留卡片供恢复。普通 verify 的 `clean` 不得替代 publication。执行卡不得提前删除；删除后发现正文仍需补写，不能从输出反向拼装一张最小执行卡获取 `clean`，而应如实报告收尾顺序错误并从完整权威状态恢复。

最终报告真实写入、删除、未更新原因、机械结果和仍存在的事实缺口；不得把未运行的检查描述为通过。
