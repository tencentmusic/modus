---
name: contact-import-api
anchors:
  locations:
    - path: import_source.py
      symbol: ContactImporter.submit
      startLine: 51
      endLine: 91
    - path: import_source.py
      symbol: ContactImporter.query
      startLine: 93
      endLine: 95
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

# 接口：提交、查询、执行与恢复

本教学项目通过 Python 对象提供四个公开方法，不提供 HTTP 路由、RPC 协议或消息消费服务。调用方持有同一个导入器实例，数据和队列才会保留。以下请求使用示例租户与示例联系人；完整字段含义由[对象专题](object.md)定义。

| 入口 | 谁在什么情况下使用 | 返回时点 |
| --- | --- | --- |
| `submit` | 提交者创建批次或确认一次重复提交 | 新任务已受理，或返回既有任务当前快照 |
| `query` | 提交者查看一个已知任务 | 读取当前快照，不推进任务 |
| `run_next` | 教学调度者执行队列最早任务 | 剩余行已处理完，或指定故障使执行停止 |
| `retry` | 提交者恢复符合条件的失败任务 | 已重新排队，尚未继续写入 |

## 调用的共同边界

这里没有登录态、令牌和角色权限。`tenant_id` 仅参与任务与联系人的分区；查询和恢复将不存在的任务和其他租户的任务统一表现为 `JobNotFound`。`run_next` 是实例内的调度操作，能够消费该实例任一租户的排队任务，不能作为已鉴权的租户接口发布。

所有返回的任务快照都是深拷贝。调用方修改返回字典不会修改任务；之后继续执行，也不会自动刷新以前保存的响应。要查看新状态，需要再次查询。查询只支持单任务，没有列表、分页、过滤或订阅。执行入口在空队列时成功返回 `None`，这不是任务快照。

## 受理一个批次

### `submit(tenant_id, idempotency_key, rows)`

适用于提交一组联系人，或使用同一个幂等键确认原请求结果。方法先校验整体结构，再比较幂等记录；因此，重复调用也必须满足当前结构要求。行内姓名为空、邮箱不合法属于执行阶段的业务问题，结构正确时仍会受理。

| 输入 | 约束与用途 |
| --- | --- |
| `tenant_id` | 必传字符串，去空白后不能空；实际保存和比较使用原字符串 |
| `idempotency_key` | 必传字符串，长度 1–64；空白字符也计入长度，不做去空白处理 |
| `rows` | 必传列表，1–100 行；顺序会影响指纹和后续覆盖顺序 |
| 每行 `name`、`email` | 必须恰好具有这两个键，值均为字符串；缺键、多键、非字符串都会整批拒绝 |

新任务保存输入副本并进入内存队列，初始 `status=queued`、`processed=0`、`attempts=0`。返回成功只表示受理，没有任何联系人因这次调用而被写入。提交者随后应保存 `job_id`，由调度者执行，再查询结果。

```python
# 示例数据；importer 是本例新建的空导入器实例，没有更早排队任务。
accepted = importer.submit("team-a", "batch-a", [
    {"name": "林禾", "email": "LIN@example.test"},
    {"name": "周宁", "email": "bad-address"},
    {"name": "林禾（更新）", "email": "lin@example.test"},
])
```

首次创建的示例响应如下。这里展示完整的空结果响应，执行后的逐行形状见[对象专题](object.md)。

```json
{"job_id":"import-1","status":"queued","total":3,"processed":0,
 "written":0,"rejected":0,"attempts":0,"retryable":false,
 "error":null,"results":[]}
```

同租户、同键且原始载荷相同，返回原任务的**当前**快照，不新增任务、不再次入队。若任务已经部分成功，重复提交会直接返回 `partial`，不会重新执行。对象键的排列不影响指纹，但行顺序、空格和邮箱大小写会影响；不能用执行时邮箱归一化来推导提交幂等。

结构错误抛出 `InvalidRequest`，没有创建本次任务。同键不同载荷抛出 `IdempotencyConflict`，原任务和联系人保持既有状态。若要修改坏行，使用新键提交修正后的行；不要拿原键覆盖旧输入。

## 查看可观察结果

### `query(tenant_id, job_id)`

调用方提供任务所属租户和已保存的任务号。方法先查任务，再检查租户是否相等；成功返回任务快照，失败抛出 `JobNotFound`。参数预期为字符串；此接口没有额外的类型转换或完整输入校验，错误类型不应被当成正式业务契约。

查询不会消费队列、重试任务或验证邮箱。持续得到 `queued` 时应检查调度是否发生；持续轮询不会改变结果。单进程顺序调用中，`running` 是执行期间的内部状态，不会在 `run_next` 返回之后作为该次执行结果保留，也不承诺可被并发轮询观察。

完成判断要组合字段：`partial` 表示所有行已处理而有行被拒绝；`failed` 可能是全行拒绝，也可能是中途故障，需继续看 `error`、`processed` 和 `retryable`。详细判据见[状态专题](state_machine.md)。

## 驱动教学执行

### `run_next(*, fail_before_row=None)`

教学调度者调用一次，按先进先出取出一个任务，增加一次 `attempts`，从已有结果数对应的下一行开始处理，直到剩余行结束或故障注入命中。此方法不需要任务号；多个任务排队时，调用方必须核对返回的 `job_id`。

`fail_before_row` 是仅用于教学的绝对输入行下标，默认 `None` 表示不注入故障。它只能是非负整数，布尔值也被拒绝。若指定下标不在本次剩余行范围内，则不会发生注入；参数错误会在出队前抛出 `InvalidRequest`。

无任务时返回 `None`。有任务时返回成功、部分成功或失败快照；模拟的 `StorageUnavailable` 在方法内部转为 `error=storage_unavailable`，不会作为该类异常抛给调度者。行校验失败也通过 `results` 表示。实现只专门处理这种模拟故障，不承诺将任意程序异常转换为可恢复状态。

## 重新排队等待恢复

### `retry(tenant_id, job_id)`

先查找同租户任务，再要求 `status=failed` 且 `retryable=true`。满足时，清除任务错误标记、设回 `queued`、关闭当前可重试标记并追加到队列末尾。已写联系人、输入、已有行结果和尝试次数全部保留；本次调用不增加尝试次数。

```python
# 示例：第 2 行处理前注入故障，保留已经完成的第 1 行。
failed = importer.run_next(fail_before_row=1)
queued = importer.retry("team-a", failed["job_id"])
finished = importer.run_next()
```

上述例子要求队列最早任务属于 `team-a`、至少有两行且尚未执行过；第三行代码才是真正继续执行的动作。错误租户或未知任务抛出 `JobNotFound`；非失败状态、数据全拒绝、部分成功以及已耗尽次数的存储故障抛出 `RetryNotAllowed`。再次调用 `retry` 会因为任务已是 `queued` 而拒绝，避免同一恢复动作重复入队。

## 错误如何交给调用者

| 表现 | 含义与后续动作 |
| --- | --- |
| `InvalidRequest` | 请求结构或故障注入参数错误；修正输入后重新调用 |
| `IdempotencyConflict` | 同键绑定了不同输入；核对旧任务或换新键提交真实的新请求 |
| `JobNotFound` | 当前租户看不到该任务；核对租户和任务号 |
| `RetryNotAllowed` | 当前状态不允许原任务恢复；读取错误和逐行结果决定新任务策略 |
| `error=all_rows_rejected` | 全部行已判定无效；修正数据后用新键提交 |
| `error=storage_unavailable` | 模拟执行故障；保留已有结果，按可重试标记决定是否恢复 |

扩展接口时，需同步检查[幂等和统计规则](rule.md)、[字段字典](object.md)及[提交与查询](modules/submission-query.md)、[执行与恢复](modules/execution-recovery.md)两份模块手册。增加真实鉴权、持久化或自动调度会改变前提和失败边界，不能只在接口表中新增一个名称。
