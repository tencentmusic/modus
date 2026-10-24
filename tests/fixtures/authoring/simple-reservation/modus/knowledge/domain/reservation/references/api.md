---
anchors:
  locations:
    - path: reservation_source.py
      symbol: ReservationService.create_reservation
      startLine: 48
      endLine: 92
    - path: reservation_source.py
      symbol: ReservationService.cancel_reservation
      startLine: 94
      endLine: 105
    - path: reservation_source.py
      symbol: ReservationError
      startLine: 10
      endLine: 15
    - path: reservation_source.py
      symbol: ReservationService._text
      startLine: 108
      endLine: 111
---

# 接口契约

本教学项目提供两个 Python 实例方法，调用方是持有同一个 `ReservationService` 对象的宿主代码。它们不是 HTTP 端点，没有状态码、分页、认证头或异步回执。参数通过关键字传入；正常返回 `Reservation`，可预期的业务拒绝抛出带稳定 `code` 的 `ReservationError`。

| 调用目的 | 入口与结果 | 详情 |
| --- | --- | --- |
| 占用会议室时段 | `create_reservation` 返回已确认预约 | [创建预约](#创建预约) |
| 释放已占用时段 | `cancel_reservation` 返回已取消预约 | [取消预约](#取消预约) |

调用前应创建并复用服务实例，且仅按顺序调用。这里没有鉴权；`organizer` 是输入文本，不是验证过的用户身份。完整运行限制见[基础设施](infrastructure.md)。

## 创建预约

### 调用与输入

`create_reservation(*, room_id, organizer, attendee_count, start_at, end_at)` 用于一场会议占用一个会议室的连续时段。五个参数均无默认值，不能省略。文本会去除首尾空白；字段的业务主定义见[预约对象](object.md#预约记录)。

| 参数 | 类型 | 本次调用的要求 |
| --- | --- | --- |
| `room_id` | `str` | 去空白后为 1—40 个字符，且必须存在于目录；不转换大小写 |
| `organizer` | `str` | 去空白后为 1—80 个字符；仅作为会议组织者标签 |
| `attendee_count` | `int` | 正整数；布尔值不合法，不能超过容量 |
| `start_at` | `datetime` | 必须带时区；写入前转换为 UTC |
| `end_at` | `datetime` | 必须带时区，并在同一时间轴上晚于开始时间 |

检查先后为会议室文本与存在性、组织者、人数与容量、开始时间、结束时间、区间顺序、冲突。遇到第一个问题即拒绝，不承诺一次收集全部错误。没有当前日期、营业时间或最大时长限制；跨日和历史区间只要满足这些已实现条件也可提交。

教学业务约定 `attendee_count` 是包含组织者的参会总人数。实现只检查这个数字，不读取人员名单，因此无法核实调用方是否遵守该计数约定。

### 成功意味着什么

服务检查同一会议室现有 `confirmed` 记录，确认半开区间不重叠后，分配实例内编号并写入内存，再返回 `status="confirmed"`、`cancel_reason=None` 的预约。此时已完成本接口承诺的占用，不是仅受理，也不需要等待通知或异步落库。

编号在当前实例内递增，最少以四位数字显示，例如 `RES-0001`；不保证跨实例唯一。返回对象是不可变快照，全部响应字段见[对象字段](object.md#预约记录)。调用后应保留返回编号，后续取消需要它。本项目没有查询或列表接口。

**示例数据：** 在一个空实例中，林青为 4 人会议预约 A201：

```python
result = service.create_reservation(
    room_id="A201",
    organizer="林青",
    attendee_count=4,
    start_at=datetime.fromisoformat("2026-11-05T09:00:00+08:00"),
    end_at=datetime.fromisoformat("2026-11-05T10:00:00+08:00"),
)
```

代码片段假设已导入 `datetime` 并取得空服务实例。下列是该返回对象各字段的示意值，不是 HTTP JSON 响应；其中时间字段实际为 `datetime` 对象。

| 字段 | 返回示例 |
| --- | --- |
| `reservation_id` | `RES-0001` |
| `room_id` | `A201` |
| `organizer` | `林青` |
| `attendee_count` | `4` |
| `start_at` | `2026-11-05T01:00:00+00:00` |
| `end_at` | `2026-11-05T02:00:00+00:00` |
| `status` | `confirmed` |
| `cancel_reason` | `None` |

### 拒绝与重试

以下错误都在创建写入前发生，既不留下“失败预约”，也不推进编号。调用方按错误原因修正输入；对时间冲突，应更换房间或时段，或在原预约有效取消后再提交。

| 错误码 | 触发条件 | 调用方动作 |
| --- | --- | --- |
| `invalid_room_id` | 会议室标识非字符串、空白或超过 40 字符 | 修正标识格式 |
| `room_not_found` | 格式有效，但目录中无该会议室 | 使用已登记标识 |
| `invalid_organizer` | 组织者非字符串、空白或超过 80 字符 | 提供有效标签 |
| `invalid_attendee_count` | 人数非正整数，或传入布尔值 | 重新提供总人数 |
| `capacity_exceeded` | 人数超过该会议室容量 | 更换会议室或调整人数 |
| `invalid_start_at` / `invalid_end_at` | 对应参数不是带时区的 `datetime` | 明确时区再提交 |
| `invalid_interval` | 开始不早于结束 | 修正时间区间 |
| `room_unavailable` | 与同房间的已确认预约重叠 | 调整时段或处理原占用 |

创建没有请求幂等键。第一次成功后原样再调用，会被已存在的占用拒绝为 `room_unavailable`，不会返回第一次编号。进程中断或结果丢失也没有自动重试、结果查询或恢复协议；不能把“重试失败”直接解读为“第一次没有成功”。

## 取消预约

### 调用与输入

`cancel_reservation(*, reservation_id, reason)` 用于取消同一服务实例内的已知预约。它不接收操作者身份，因此不验证谁可以取消；宿主如需权限控制，必须另行实现。

| 参数 | 类型 | 本次调用的要求 |
| --- | --- | --- |
| `reservation_id` | `str` | 去空白后为 1—40 字符，且当前实例内存在该记录 |
| `reason` | `str` | 去空白后为 1—200 字符，首次取消时写入 `cancel_reason` |

顺序是校验编号、查找记录、校验原因，最后判断是否已经取消。不存在的记录首先报不存在；已取消记录也仍要求本次原因格式有效。

### 返回与重复请求

首次取消替换内存中的预约对象，返回 `cancelled` 及规范化后的原因；其余字段保持原值。记录没有被删除，但后续创建不再把它视为占用。取消没有时间限制，不会根据会议已开始或结束而拒绝。

**示例数据：** `service.cancel_reservation(reservation_id="RES-0001", reason="会议改期")` 返回该编号的 `cancelled` 快照，`cancel_reason` 为“会议改期”。以另一有效原因重复取消，返回第一次取消的同一个对象，不覆盖原因，也不增加记录。这个有限的幂等语义仅适用于同实例、同编号和有效输入。

| 错误码 | 触发条件 | 已有状态与恢复 |
| --- | --- | --- |
| `invalid_reservation_id` | 编号非字符串、空白或超过 40 字符 | 不变；修正输入 |
| `reservation_not_found` | 格式有效，但当前实例无此编号 | 不变；检查实例和编号来源 |
| `invalid_reason` | 原因非字符串、空白或超过 200 字符 | 不变；提供有效原因后重试 |

完整取消过程见[取消手册](modules/cancel-reservation.md)。创建时拿到的旧快照不会随取消自动刷新，宿主应使用取消返回值更新显示；不能把旧对象的 `confirmed` 当作当前权威状态。

## 契约之外的调用错误

漏传参数、多传参数或改用不符合签名的位置参数属于 Python 调用错误，通常抛出 `TypeError`，不映射为业务错误码。内存耗尽、进程终止等运行故障也没有被包装成业务拒绝或补偿流程。自动化调用方应分别处理业务拒绝与非预期异常，不根据本表推断后者一定没有副作用。
