# Team Standard：从工程证据到编码决策

Team Standard 帮助开发者在修改代码前回答三个问题：**哪些边界必须保持、应该复用哪个现有能力、默认怎样实现和验证**。它由首次初始化的 K5 阶段提炼，随后交给人工维护。

这条链路有三个独立边界：内置指南提供调查与写法候选，项目证据决定适用范围，发布协议保护已交付正文。解析器识别了语言、目录中存在框架依赖，都不能替代适用性核验；人工拥有一份文档，也不意味着其中每条建议都是强制政策。

## 从哪里开始阅读

| 维护任务 | 主定义 |
| --- | --- |
| 查找语言、能力或框架指南 | [规范模块索引](../src/modus/scaffold/templates/skills/modus-init/references/constraint-profiles/index.md) |
| 决定模块如何选择、组合与处理冲突 | [选择与组合](../src/modus/scaffold/templates/skills/modus-init/references/constraint-profiles/composition.md) |
| 理解项目最终应该交付什么 | [团队规范契约](../src/modus/scaffold/templates/skills/using-modus/references/authoring/framework/deliverables/team-standard.md) |
| 修改路径身份、写入权限或检索行为 | 本页的[运行时边界](#运行时边界) |
| 检验指南能否支撑具体编码任务 | [编码演练](../tests/fixtures/team_standard/README.md) |

## 内容按变化原因拆分

内置资源继续放在 `constraint-profiles/`，保留已有取证入口。六个维度分别拥有一种变化原因；新增框架只补实现差异，无需复制每种语言与工程类型的组合。

| 维度 | 拥有的内容 | 不承担的责任 |
| --- | --- | --- |
| `foundation` | 值契约、复用、方法与条件组织、错误、资源、注释 | 指定语言语法或团队排版 |
| 语言入口 | 版本、类型、集合、错误与并发惯用法 | 把同一语言的所有运行平台视为相同环境 |
| `engineering-types` | 服务、前端、客户端、CLI、库、Worker 等生命周期差异 | 根据目录名推断实际入口 |
| `capabilities/` | 数据库、配置、并发、I/O、缓存和消息的共同契约 | 预设框架、方言或生产容量 |
| `adapters/` | 框架与产品的装配、API、版本限制和实现差异 | 重复专项的完整规则 |
| 项目与团队材料 | 已有封装、工具配置、真实调用、明确偏好与例外 | 由内置指南预填项目政策 |

选择单位是构建单元及其运行边界。同仓的浏览器 TypeScript 与 Node Worker 可以共享值契约，但分别选择资源和生命周期规则；共享包只采用其承诺平台都能满足的实现。解析注册和 Surface 画像提供候选，装配与调用证据决定是否选用。未适配技术沿通用调查降级，并明确未覆盖部分。

规则组合比较性质、来源、范围和版本，不按加载顺序覆盖。源码事实、明确约束、归纳约定、通用建议和待确认事项分别表达；示例承载某种规则性质，本身不增加权威。冲突处理和模块扩展的完整规则由[组合契约](../src/modus/scaffold/templates/skills/modus-init/references/constraint-profiles/composition.md)维护。

## 从调查到消费

| 阶段 | 需要留下的结果 |
| --- | --- |
| K1：范围 | 团队材料、偏好、版本、平台与规范的保护状态 |
| K2：计划 | 编码场景、候选模块、主定义位置、待核验条件和验证任务 |
| K3：取证 | 准确签名、空值与单位、错误、副作用、资源所有者、代表调用和反例 |
| K5：提炼 | 选用与排除理由、场景导航、默认方案、示例前提、例外及验证结果 |
| 编码消费 | 从任务定位适用条目，核验当前源码后落实到实现与检查 |

这些记录保存在既有执行卡中；Markdown 索引和稳定锚点承担导航，当前不需要额外规则引擎或状态机。一个事实保留一个主定义：领域不变量留在域规则，模块专属条件留在场景，共享工程要求归 Team Standard。

## 运行时边界

项目保留 `modus/knowledge/constraint/team-standard.md` 作为入口。需要拆分时增加一级 `team-standard/<topic>.md`，入口仍负责场景与范围导航；已有更深专题同样受到保护。内置模块目录不直接复制成项目目录。

| 实现 | 责任与不变量 |
| --- | --- |
| [knowledge_identity.py](../src/modus/knowledge_identity.py) | 统一识别入口及专题命名空间；磁盘路径安全检查通过后才赋予人工所有权 |
| [knowledge_write_session.py](../src/modus/knowledge_write_session.py) | 区分保护、首次填充和明确维护；锁内复查当前正文、精确种子和 CAS |
| [knowledge_update.py](../src/modus/knowledge_update.py) | 整批形状预检，逐文件报告写入、未变和冲突；已完成写入不回滚 |
| [retrieval/stages/documents.py](../src/modus/retrieval/stages/documents.py) | 入口和专题均使用 `document-declaration`；未显式声明 facet 时按 `rule` 检索 |

首次创建专题时，写入器先锁入口、再锁专题，并在锁内确认入口仍缺失或为精确种子。入口发布成稿后，新增专题也需要明确维护授权；专题没有“精确种子可覆盖”的例外。文档锁协调遵守同一协议的写者，CAS 拒绝过时摘要；二者不提供跨文件事务。

发布采用两步：先写专题并确认结果，再更新入口导航。专题部分成功时保留已写文件，回读冲突后恢复；不能把初始化失败自动升级为维护权限。相同正文可幂等重试。权限条件和操作步骤以[团队规范契约](../src/modus/scaffold/templates/skills/using-modus/references/authoring/framework/deliverables/team-standard.md#稳定入口与可选专题)及 [CAS 发布](../src/modus/scaffold/templates/skills/using-modus/references/authoring/publication.md#cas-发布)为准。

检索示例沿稳定 item 锚点带回所属条目的性质、前提和例外，不将专题提升为人工强制政策，也不扩大默认读取预算。升级只更新随包技能资源；既有项目规范保持原字节。入口种子的字节身份影响初始化权限，修改种子必须单独评估兼容性。

## 如何验证这个设计

验证分成三个层次，结论各自有明确范围：

- **运行时契约**：路径身份、初始化权限、人工保护、并发交接、部分成功重试和检索上下文。测试证明写入与读取边界。
- **分发契约**：模板链接、wheel 资源读取和安装后的 CLI 行为。测试证明交付物可用。
- **编码演练**：独立任务输入驱动 Java 与 TypeScript 实现，编译并执行失败、并发和复用检查；Kotlin、混合及未知技术保留人工回读。演练检查具体实现，不能替代真实框架集成或生成质量评测。

演练的 API 是仓库夹具定义，Store/HTTP 替身不证明生产数据库、Spring、Apollo、Android 或容量行为。缺工具时显式跳过，人工回读不报告为编译通过。扩展模块时补充适用条件、证据、默认方案和例外，并增加能区分正确与错误实现的任务；链接、篇幅与关键词不作为内容质量分数。
