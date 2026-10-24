---
name: contact-import-reader-tasks
anchors:
  locations:
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
      symbol: ContactImporter._view
      startLine: 177
      endLine: 192
---

# 读者任务与有依据的参考答案

这份材料用于测试知识库是否能让没有参与写作的人完成真实阅读任务。每次只向独立读者提供目标文档和下列问题；不要同时提供本文的参考答案、源码、证据底稿或作者对话。要求读者写出答案、引用支持答案的文档位置，并指出无法确定的内容。

通过标准是事实与操作判断正确，关键边界没有被省略；不能只按包含几个关键词计分。下面的答案用于审阅者核对，不表示独立读者已经实际通过。若要评测新的写作规范，保留同一组任务和业务事实，另增加未参与打磨的变体，避免只记住本例。

## 提供给读者的问题

1. 你刚收到 `queued`、`processed=0` 的提交响应，能否向运营者宣称联系人已经导入？接下来必须发生什么？
2. 同一租户用原幂等键重提相同三行时，原任务已经 `partial`。会新建任务或再次执行吗？
3. 三行结果分别是 `created`、`rejected`、`updated`，其中两条有效行的邮箱归一化后相同。处理数、写入数、拒绝数和独立联系人数各是多少？
4. 第一次执行在第二行前发生模拟存储故障。第一行已经成功，查询应显示什么？已经写入的数据会回滚吗？
5. 上一题随后调用 `retry` 成功，是否可以宣布恢复完成？下一次执行从哪里开始，次数如何变化？
6. `failed` 是否总能重试？比较全部行被拒绝、第一次存储故障和第二次存储故障。
7. 原任务邮箱为大写，重提时改为小写，但使用同一个键。它是不是同一次幂等请求？为什么？
8. `partial` 中有一个坏邮箱，提交者应怎样修正？新任务成功后，旧任务是否变成成功？
9. 查询一直是等待状态，持续轮询会让任务开始吗？能否从 `running` 状态推断存在后台工作线程？
10. 错误租户查不到任务，是否足以说明系统具备真正的用户权限校验？
11. 某次执行 `written=2`，重启进程后新实例找不到任务。能否恢复？为什么？
12. `run_next` 返回 `None` 与 `query` 抛出 `JobNotFound` 分别说明什么？是否都是执行失败？

## 审阅者使用的参考答案

### 1：受理与最终完成

不能。新批次只保存了任务和输入副本并排队，还没有写联系人。教学调度者必须显式执行，之后读取执行结果或查询终结状态。依据：[提交模块的场景一](modus/knowledge/domain/contact-import/references/modules/submission-query.md#场景一提交三行确认已经受理)、[接口受理语义](modus/knowledge/domain/contact-import/references/api.md#受理一个批次)。

### 2：重复提交的当前快照

不会新建或重跑。相同租户、键和原始载荷命中原任务，直接返回当前 `partial` 快照，队列不增加工作。依据：[规则 R2](modus/knowledge/domain/contact-import/references/rule.md#r2幂等键保护同一次请求不修改旧请求)。

### 3：不同统计口径

处理数 3、写入数 2、拒绝数 1；在这个从空联系人集开始的示例中，独立联系人只有 1 个，姓名取最后一条有效写入。`processed` 包含拒绝，`written` 包含创建和更新。若不限定原有数据，不能从本批结果推导整个实例的联系人总数。依据：[对象快照与三行案例](modus/knowledge/domain/contact-import/references/object.md#对外任务快照)。

### 4：故障保留什么

任务为 `failed`、`error=storage_unavailable`、`processed=1`、`written=1`、`attempts=1`、`retryable=true`。第一行联系人及结果保留，第二行尚未处理，不做整批回滚。依据：[执行模块恢复场景](modus/knowledge/domain/contact-import/references/modules/execution-recovery.md#场景二在第二行前失败后继续剩余行)。

### 5：恢复的完成信号

不能在 `retry` 返回后宣称完成。该调用只重新排队，处理数仍为 1、次数仍为 1；再次执行才从第二行开始，次数变为 2。没有新故障且剩余行合法时最终成功，已有第一条结果不被重做。依据：[状态恢复案例](modus/knowledge/domain/contact-import/references/state_machine.md#贯穿案例保留第一行后继续第二行)。

### 6：失败与恢复资格

不是所有失败都能恢复。全行拒绝已经完成所有检查，需改数据建新任务；第一次模拟存储故障可重排一次；第二次故障耗尽次数，原任务不可恢复。部分成功也不能走原任务恢复。依据：[规则 R6](modus/knowledge/domain/contact-import/references/rule.md#r6恢复继续未处理行不重做已有结果)。

### 7：原始载荷与业务归一化

不是。幂等指纹保留字符串大小写，而执行阶段才归一化邮箱，所以同键改变大小写发生冲突。对象键顺序可以变化，输入行顺序和字符串内容不可以。依据：[规则 R2 的变化表](modus/knowledge/domain/contact-import/references/rule.md#r2幂等键保护同一次请求不修改旧请求)。

### 8：坏行修正是新请求

读取拒绝行，修正邮箱后使用新幂等键提交，例如只提交需要修正的一行，再显式执行。旧任务仍保留 `partial`，不会被新任务改写历史。依据：[提交模块修正场景](modus/knowledge/domain/contact-import/references/modules/submission-query.md#场景三读懂部分成功并完成坏行修正)。

### 9：调度边界

轮询不推进任务，需显式执行队列。`running` 是同步执行调用内部阶段；单线程顺序调用不能在中间插入查询，不表示有真实后台线程或并发进度保证。依据：[执行模块场景一](modus/knowledge/domain/contact-import/references/modules/execution-recovery.md#场景一执行队列中的一批联系人)。

### 10：数据隔离与身份认证

不能。当前实现只比较调用方提供的租户与任务租户，调用者仍可以声称任意租户。它有数据索引隔离，没有真实认证授权。依据：[规则 R7](modus/knowledge/domain/contact-import/references/rule.md#r7租户隔离是数据索引规则)。

### 11：实例内状态不是持久化

不能用本实现恢复。所有任务、联系人、幂等键和队列都在实例内存，新实例为空；没有数据库或重启恢复协议。`written=2` 还不能推导独立联系人数为 2。依据：[基础设施资源边界](modus/knowledge/domain/contact-import/references/infrastructure.md#基础设施一个进程内的受理与执行模拟)、[对象统计](modus/knowledge/domain/contact-import/references/object.md#对外任务快照)。

### 12：空队列与任务不可见

`run_next` 返回 `None` 是队列当前没有任务，并未执行失败任务；`query` 的 `JobNotFound` 表示指定任务在该租户中不存在或不可见，不说明队列是否为空。依据：[执行接口](modus/knowledge/domain/contact-import/references/api.md#驱动教学执行)、[查询接口](modus/knowledge/domain/contact-import/references/api.md#查看可观察结果)。

## 怎样根据失败回修正文

读者把受理当完成，优先修改入口响应与案例的时点；把写入数当人数，补充同邮箱覆盖案例；不知道失败后还剩什么，补充故障前后的记录变化；能复述状态却不能决定操作，补充恢复资格和新请求路径。修订后重新交给独立读者，避免只在作者自己的上下文中“看起来已经清楚”。
