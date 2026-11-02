---
name: contact-import-evidence
anchors:
  locations:
    - path: import_source.py
      symbol: MAX_ROWS
      startLine: 13
      endLine: 13
    - path: import_source.py
      symbol: MAX_ATTEMPTS
      startLine: 14
      endLine: 14
    - path: import_source.py
      symbol: ContactImporter.__init__
      startLine: 45
      endLine: 49
    - path: import_source.py
      symbol: ContactImporter.submit
      startLine: 51
      endLine: 91
    - path: import_source.py
      symbol: ContactImporter.run_next
      startLine: 97
      endLine: 159
    - path: import_source.py
      symbol: ContactImporter.retry
      startLine: 161
      endLine: 168
    - path: import_source.py
      symbol: ContactImporter._find
      startLine: 170
      endLine: 174
    - path: import_source.py
      symbol: ContactImporter._view
      startLine: 177
      endLine: 192
    - path: import_source.py
      symbol: demonstrate
      startLine: 195
      endLine: 254
---

# 教学事实与图文复核底稿

本底稿记录本案例的实际实现，不为 Modus 生产能力背书。源码坐标只保存在元数据；正文用稳定主张、职责和可观察结果组织，便于与成文知识对照。代码变更后，应先重新运行示例，再更新受影响的图、字段、规则和读者答案。

## 范围确认

本例只有“联系人批量导入”一个领域，两个模块分别负责提交查询和执行恢复。公开入口全部覆盖：`submit`、`query`、`run_next`、`retry`。内部辅助职责只有任务查找、快照生成和内存资源装配；它们不是额外业务模块。

已核验没有真实 HTTP/RPC、用户鉴权、数据库、缓存服务、消息中间件、后台线程、自动重试、取消、分页、外部同步和持久恢复。没有用“待确认”包装已经明确不存在的教学能力。真实业务需求与教学范围不同，应另行调查，不从这套样稿外推。

## 核心主张与复核方式

| 主张 | 实现责任 | 可观察证据 |
| --- | --- | --- |
| E1：受理不执行联系人写入 | `ContactImporter.submit` | 新任务 `queued`、处理数 0，联系人字典未变 |
| E2：同租户同键同载荷不新增工作 | 提交的指纹比较和既有任务返回 | 同一任务号；处理后再次执行空队列得到 `None` |
| E3：载荷归一化与邮箱归一化不是一回事 | 提交指纹与执行行处理 | 对象键顺序不冲突；邮箱大小写或行顺序变化会冲突 |
| E4：坏行有结果但不写联系人 | 执行中的姓名和邮箱检查 | 中间坏行被拒绝，后一条有效行仍可更新 |
| E5：写入数不是独立人数 | 联系人复合键与快照聚合 | 三行样例两次写入、一次拒绝、一个联系人 |
| E6：故障保留前序结果 | 行前故障注入与异常处理 | 第二行前失败时已有第一条联系人和结果 |
| E7：恢复只继续未处理行 | 结果长度决定迭代起点 | 恢复后第一行仍为原始 `created`，没有重做成 `updated` |
| E8：恢复只适用于特定失败 | 恢复资格检查与次数常量 | 部分成功、全行拒绝、第二次故障都不能原任务恢复 |
| E9：查询与恢复检查租户相等 | `ContactImporter._find` | 错误租户读取任务得到 `JobNotFound`；不证明真实鉴权 |
| E10：输入和返回值都隔离可变引用 | 输入副本与快照深拷贝 | 修改原列表或响应，不改变已受理任务 |
| E11：执行是显式、单线程的 | 队列出队与执行入口 | 查询不会推进；`running` 是调用内部阶段 |
| E12：恢复追加队尾，不锁定已有联系人 | `retry` 追加与 `run_next` 先进先出执行 | A 故障后重排，B 先更新同邮箱，A 只继续剩余行；A 的旧结果不改写 |
| E13：恢复可以结束为部分成功 | 行结果保留与全批拒绝数判定 | 第一行有效、第二行无效，第二行前故障后恢复，终结为 `partial` |

样稿中的姓名代号、`tenant-demo-a/b`、邮箱与请求键均从零合成。源码、接口 JSON、模块代码及验收记录使用相同数据映射，便于比较大小写、重复邮箱和顺序覆盖；不从真实联系人或内部业务日志抽样。正文对当前行为的结论来自本例源码，参考文档仅影响组织和表达方式。

## 图中关系逐组对应什么事实

每幅图应从以下关系找到依据，不能因为常见架构通常存在某个服务就添加节点或边。

| 图的主定义 | 图中关系 | 对应主张或责任 |
| --- | --- | --- |
| [对象关系](modus/knowledge/domain/contact-import/references/object.md) | 幂等键定位任务、任务保存输入和结果 | E2、E10；任务初始化与结果追加 |
| 对象关系 | 有效行覆盖联系人、任务与结果生成快照 | E4、E5；执行写入与快照聚合 |
| [状态转换](modus/knowledge/domain/contact-import/references/state_machine.md) | 创建到等待、等待到执行、正常终结 | E1、E11；受理、出队、拒绝计数判定 |
| 状态转换 | 执行失败、可恢复失败回等待、不可恢复终结 | E6、E7、E8；故障处理与恢复资格 |
| [协作时序](modus/knowledge/domain/contact-import/references/downstream.md) | 提交保存任务再入队、返回受理快照 | E1、E2；只画首次合法提交主路径 |
| 协作时序 | 显式执行出队、有效行写入、无效行拒绝、更新任务 | E4、E5、E11；同一实例内的职责交接 |
| 协作时序 | 查询任务并返回结果 | E9、E10；快照读取，不是执行触发 |
| [协作的两批次对照](modus/knowledge/domain/contact-import/references/downstream.md#存储故障怎样暂停交接) | 重排到队尾、其他任务先写、恢复跳过旧行 | E7、E12；队列顺序不提供跨批次隔离 |
| [提交模块流程](modus/knowledge/domain/contact-import/references/modules/submission-query.md) | 结构检查、幂等存在与载荷分支、入队或旧快照 | E1、E2、E3；不同错误不产生新的工作 |
| 提交模块流程 | 新任务受理后由调度执行、查询结果 | E11；调度是另一次明确调用 |
| [恢复模块流程](modus/knowledge/domain/contact-import/references/modules/execution-recovery.md) | 计次、从结果长度继续、行处理循环 | E4、E7、E11；失败前已有结果保留 |
| 恢复模块流程 | 故障保留、检查次数、重排或停止 | E6、E8；重新排队后仍需显式执行 |

图中的状态和箭头只表达当前教学行为。没有取消、自动退避、消息确认、独立消费者或外部最终完成边，因此文中也不应声称这些能力。

## 验收分开记录

业务运行使用独立教学实例，通过确定性断言检查受理、部分成功、幂等、错误租户、故障保留、有条件恢复和次数耗尽。补充边界包括请求结构、输入与快照隔离、查询不推进、队列顺序以及归一化边界。实际记录见[验收结果](verification-results.json)，其中包含执行版本、教学源码摘要与各项检查结果。

链接与源码锚点应检查实际目标；字段、图边和规则需回读正文并对照实现。读者测试使用[预设任务](reader-tasks.md)，只给测试读者文档和问题，不给本底稿、源码或标准答案。业务运行通过、链接存在和语法通过分别只证明各自检查范围。

本夹具不内置渲染工具。Mermaid 是否在目标界面清晰可读，需要实际渲染后的检查记录；没有该记录时应写“未完成视觉验收”，不得把文本回读或运行断言称为渲染通过。
