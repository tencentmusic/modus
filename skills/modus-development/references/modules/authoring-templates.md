# 模板与 K1–K6 知识创作工作流

## 主定义

`docs/authoring-contract.md` 是创作设计；`docs/knowledge-lifecycle-boundary.md` 拥有 N/K 交接。安装后的运行协议来自 `src/modus/scaffold/templates/skills/using-modus/references/authoring/`。`TemplateCatalog` 原样读资源，Python 不维护竞争性的正文规范。

修改正文生成、范围确认、机器包消费或收尾规则时，联读设计与对应运行参考。不要只改顶层 SKILL 摘要而留下相反的细则。

| 模板目录 | 用途 |
| --- | --- |
| `skills/using-modus/SKILL.md`、router-details、constraint-usage | 按任务取证、约束适用、知识留存检查点 |
| `skills/modus-init/SKILL.md`、references/workspace-init.md | 首次完整知识、工作区盘点/确认 |
| `skills/modus-reinit/SKILL.md` | 既有完整快照复核、稳定身份、真实变化与精确退役 |
| `skills/modus-update-knowledge/SKILL.md` | 明确材料或局部新事实的增量维护 |
| `skills/modus-sync-knowledge/SKILL.md` | 当前代码任务确有长期影响后的静默最小修订 |
| `using-modus/references/authoring/evidence/` | machine-packet、scope-modeling、scenario-closure、语言证据适配 |
| `.../authoring/framework/` | 布局、运行形态、自然语言、图文、各 deliverable 的读者任务 |
| `.../authoring/framework/editorial.md`、`examples.md` | 稳定的阅读排版合同与随包成对片段；按问题加载，不复制教学业务事实 |
| `.../authoring/execution-strategy.md` | 可替换的上下文、成文和读者测试组织方式，不降低质量合同、不新增状态 |
| `.../authoring/publication.md` | 回读、核验、读时哈希、发布与执行卡清理 |
| `.../authoring/parallel-domain-authoring.md`、domain-worker-prompt | 用户明确授权时完整 Domain 委派，根作者拥有执行卡与共享产物 |
| `modus-init/references/constraint-*`、constraint-profiles | 从实际项目提炼 Team Standard；不是语言常识复制 |
| `commands/`、`knowledge/` | 三种显式命令薄入口，constraint/business/handbook 种子 |

## 六阶段创作

K1：调查能力/公开入口族，决定领域与模块，保持稳定身份；K2：规划唯一主定义、模块选择器、图表、读时哈希与执行卡；K3：按真实场景闭合方法体/配置/测试证据；K4：完成一个领域的六专题、模块场景与 router；K5：校准跨域权威、方向、完成信号与根概览；K6：语义回读、机械/publication、CAS 与发布后回读。

模块围绕“触发→输入→前置/决策→编排→权威写入/产物→同步返回/异步交接→最终可见结果→残留/恢复”。九类读者问题是评审维度，不是九个固定标题。backend/frontend/cli/library/worker/data/infrastructure/plugin 是运行形态，语言与框架是另一个轴。

正式知识的 API/Object/Rule/State/Collaboration/Infrastructure 有唯一专题主定义，模块拥有完整场景并链接它们。不为每个类/DTO/endpoint 创建竞争目录，也不复制同一事实到每个模块。

生成知识的源码坐标进入少量 frontmatter `anchors.locations`，正文仍须独立可读；复杂异步/状态/决策/对象/资源机制用对应图表或表格，不用导航图替代机制图。

编辑安排和实际回读/预览缺口复用唯一执行卡的现有正文。域作者逐篇回读全部目标专题、分片、Module 与路由，根作者抽样只作二次校准；未实际预览不能宣称布局已通过。维护者完整教学样稿位于 `tests/fixtures/authoring/`，不进入用户技能；只运行样稿自验不代表真实项目生成质量已验证。

## 不同工作流的关键差异

init/reinit 单仓每轮至多构建一次初始化包，失败直接用当前源码并记录缺口，不重复 build 或读旧包。init 先 scope-discovery，reinit 先 reinit-diff；逐模块 module-authoring 需精确 selector，域 coverage-audit 用已确认源码范围。

update/sync 不构建或消费初始化 bundle。sync 只有本轮实际实现变化影响长期语义时才发生，不能接管已有脏改动；无影响静默结束，不固定执行 noop 检查。普通项目消费材料不等于授权持久保存材料。

Scope 一次完整确认，已有完整授权复用；reinit 仅合并确认真实新增/拆并/迁移/退役，不因锚点/标题变化反复确认。执行卡只由主作者维护，保留完整调查状态；不能丢失后从输出重建缩小的全 reviewed 卡。并行领域创作需明确授权，串行确认不授权委派。

## 扩展与验证

新工作流先改 `surface.py` 的显式集合，再加有效 frontmatter、description 和末尾换行的模板，并维护 catalog、宿主调用维度与发布合同。相对链接按技能包布局检查。

测试：`test_scaffold.py`、`test_documented_cli.py`、`test_verify_knowledge.py`、`test_platforms.py`、`test_release_smoke.py`。机械检查不证明助手将写出完整场景；涉及实质行为变化时用一个真实小项目走相应创作流程并回读内容，不用篇幅/标题 regex 代替验收。
