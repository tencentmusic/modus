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
| [`submit`](#受理一个批次) | 提交者创建批次或确认一次重复提交 | 新任务已受理，或返回既有任务当前快照 |
| [`query`](#查看可观察结果) | 提交者查看一个已知任务 | 读取当前快照，不推进任务 |
| [`run_next`](#驱动教学执行) | 教学调度者执行队列最早任务 | 剩余行已处理完，或指定故障使执行停止 |
| [`retry`](#重新排队等待恢复) | 提交者恢复符合条件的失败任务 | 已重新排队，尚未继续写入 |

## 调用的共同边界

这里没有登录态、令牌和角色权限。`tenant_id` 仅参与任务与联系人的分区；查询和恢复将不存在的任务和其他租户的任务统一表现为 `JobNotFound`。`run_next` 是实例内的调度操作，能够消费该实例任一租户的排队任务，不能作为已鉴权的租户接口发布。

所有返回的任务快照都是深拷贝。调用方修改返回字典不会修改任务；之后继续执行，也不会自动刷新以前保存的响应。要查看新状态，需要再次查询。查询只支持单任务，没有列表、分页、过滤或订阅。执行入口在空队列时成功返回 `None`，这不是任务快照。

四个方法都是普通同步 Python 调用；“异步导入”只描述受理与执行分离。除 `fail_before_row=None` 外，公开参数均无默认值；提交、查询和恢复可以用位置或关键字传参，故障注入参数只能用关键字传入。缺少必传参数、传入未知关键字或错误的位置参数会产生 Python `TypeError`，不包装为业务异常。JSON 示例仅用于展示 Python 字典的形状，`null` 对应 `None`，不存在 HTTP 状态码或统一网络响应外壳。

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
# 示例数据；在教学项目目录执行。
from import_source import ContactImporter

importer = ContactImporter()
accepted = importer.submit("tenant-demo-a", "batch-a", [
    {"name": "联系人甲", "email": "ALPHA@example.test"},
    {"name": "联系人乙", "email": "bad-address"},
    {"name": "联系人甲（更新）", "email": "alpha@example.test"},
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

| 异常请求示例 | 命中条件 | 结果及处置 |
| --- | --- | --- |
| `submit("tenant-demo-a", "empty", [])` | 行数小于 1 | `InvalidRequest`；补齐数据后提交，没有失败任务可查询 |
| 同键重提时多一个 `phone` 字段 | 行结构在幂等比较前检查 | `InvalidRequest`，不是幂等冲突；原任务不变 |
| 将上述第三行删掉后仍用 `batch-a` | 结构有效，载荷指纹改变 | `IdempotencyConflict`；查询旧任务或为新请求换键 |

幂等键空字符串被拒绝，但单个空格合法；这是当前长度校验的边界，不是推荐的键命名方式。租户的首尾空白也不会被去掉，调用者需在首次提交前确定稳定的分区标识。

## 查看可观察结果

### `query(tenant_id, job_id)`

| 参数 | 类型、必填与来源 | 判定方式 |
| --- | --- | --- |
| `tenant_id` | 字符串，必传；使用提交时的原值 | 与任务租户精确比较，不去空白 |
| `job_id` | 字符串，必传；取成功提交的响应 | 按实例内任务号查找，无前缀补全或默认任务 |

调用方提供任务所属租户和已保存的任务号。方法先查任务，再检查租户是否相等；成功返回任务快照，失败抛出 `JobNotFound`。参数预期为字符串；此接口没有额外的类型转换或完整输入校验，错误类型不应被当成正式业务契约。

查询不会消费队列、重试任务或验证邮箱。持续得到 `queued` 时应检查调度是否发生；持续轮询不会改变结果。单进程顺序调用中，`running` 是执行期间的内部状态，不会在 `run_next` 返回之后作为该次执行结果保留，也不承诺可被并发轮询观察。

完成判断要组合字段：`partial` 表示所有行已处理而有行被拒绝；`failed` 可能是全行拒绝，也可能是中途故障，需继续看 `error`、`processed` 和 `retryable`。详细判据见[状态专题](state_machine.md)。

继续上述三行示例，调度者执行一次后再查询：

```python
importer.run_next()
observed = importer.query("tenant-demo-a", accepted["job_id"])
```

完整查询响应如下；`written=2` 包括一次创建、一次更新，不表示新增两个人。

```json
{"job_id":"import-1","status":"partial","total":3,"processed":3,
 "written":2,"rejected":1,"attempts":1,"retryable":false,"error":null,
 "results":[
   {"row_index":0,"email":"alpha@example.test","outcome":"created","reason":null},
   {"row_index":1,"email":"bad-address","outcome":"rejected","reason":"invalid_email"},
   {"row_index":2,"email":"alpha@example.test","outcome":"updated","reason":null}
 ]}
```

用 `tenant-demo-b` 查询这个任务会抛出 `JobNotFound`，与查询不存在的 `import-999` 相同；两种失败都不改变任务、队列或联系人。服务没有通过该异常区分“别人的任务”和“根本不存在”。

## 驱动教学执行

### `run_next(*, fail_before_row=None)`

教学调度者调用一次，按先进先出取出一个任务，增加一次 `attempts`，从已有结果数对应的下一行开始处理，直到剩余行结束或故障注入命中。此方法不需要任务号；多个任务排队时，调用方必须核对返回的 `job_id`。

`fail_before_row` 是仅用于教学的绝对输入行下标，默认 `None` 表示不注入故障。它只能是非负整数，布尔值也被拒绝。若指定下标不在本次剩余行范围内，则不会发生注入；参数错误会在出队前抛出 `InvalidRequest`。

无任务时返回 `None`。有任务时返回成功、部分成功或失败快照；模拟的 `StorageUnavailable` 在方法内部转为 `error=storage_unavailable`，不会作为该类异常抛给调度者。行校验失败也通过 `results` 表示。实现只专门处理这种模拟故障，不承诺将任意程序异常转换为可恢复状态。

| 调用示例 | 返回或异常 | 已执行什么 |
| --- | --- | --- |
| 上述三行已执行完，再调用 `importer.run_next()` | `None` | 队列为空，没有新增一次尝试 |
| 非空队列调用 `run_next(fail_before_row=True)` | `InvalidRequest` | 参数校验先于出队，任务仍在队首 |
| 两行新任务调用 `run_next(fail_before_row=0)` | 失败快照，处理数 0、次数 1、可恢复 | 任务已出队但尚未处理任何一行 |
| 两行新任务调用 `run_next(fail_before_row=2)` | 正常处理两行后的快照 | 下标等于行数，未命中注入点 |

返回字典本身不代表本批成功。调度者应保留返回的任务号及[任务快照全部字段](object.md#对外任务快照)，将业务拒绝交给提交者修正，将可恢复故障交给恢复入口。`run_next` 没有请求幂等语义：再次调用会消费下一个排队任务。

## 重新排队等待恢复

### `retry(tenant_id, job_id)`

两个参数均为必传字符串，来源与查询一致：提交时的原租户、原任务响应中的任务号，无默认值。调用者应先查询停止位置及恢复资格；接口仍会在动作时重新检查当前任务，旧响应不能代替这次检查。

先查找同租户任务，再要求 `status=failed` 且 `retryable=true`。满足时，清除任务错误标记、设回 `queued`、关闭当前可重试标记并追加到队列末尾。已写联系人、输入、已有行结果和尝试次数全部保留；本次调用不增加尝试次数。

```python
# 独立示例：新实例、两行有效输入，不接续前面的部分成功任务。
recovery = ContactImporter()
job = recovery.submit("tenant-demo-a", "batch-b", [
    {"name": "联系人丙", "email": "gamma@example.test"},
    {"name": "联系人丁", "email": "delta@example.test"},
])
failed = recovery.run_next(fail_before_row=1)
queued = recovery.retry("tenant-demo-a", job["job_id"])
finished = recovery.run_next()
```

这个独立实例的任务号也是 `import-1`，不与前一实例共享身份。`queued` 的完整响应如下，最后一次 `run_next` 才真正继续执行：

```json
{"job_id":"import-1","status":"queued","total":2,"processed":1,
 "written":1,"rejected":0,"attempts":1,"retryable":false,"error":null,
 "results":[
   {"row_index":0,"email":"gamma@example.test","outcome":"created","reason":null}
 ]}
```

继续执行成功后，状态为 `succeeded`，处理数和写入数均为 2，次数为 2，两条结果都是 `created`。第一条结果没有重做为更新。重新排队后的错误虽然清空，但完成必须以这次执行或之后的查询为准。

| 拒绝分支 | 校验顺序与结果 | 原任务是否改变 |
| --- | --- | --- |
| 错误租户或未知任务号 | 查找先失败，抛出 `JobNotFound` | 不变 |
| `partial`、`succeeded` 或全行拒绝 | 不满足失败且可恢复，抛出 `RetryNotAllowed` | 不变；需修正数据时用新任务 |
| 第二次存储故障 | 恢复标记为假，抛出 `RetryNotAllowed` | 前序写入仍保留 |
| 重排成功后立即再调用 `retry` | 当前已是 `queued`，抛出 `RetryNotAllowed` | 不重复追加队列 |

恢复入口不是“重复调用总返回同一结果”的幂等接口。若不确定重排是否完成，先查询当前快照，不能盲目重复动作。

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
