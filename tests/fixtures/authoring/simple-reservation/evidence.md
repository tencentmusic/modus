---
anchors:
  locations:
    - path: reservation_source.py
      symbol: Room
      startLine: 19
      endLine: 22
    - path: reservation_source.py
      symbol: Reservation
      startLine: 26
      endLine: 34
    - path: reservation_source.py
      symbol: ReservationService.__init__
      startLine: 40
      endLine: 46
    - path: reservation_source.py
      symbol: ReservationService.create_reservation
      startLine: 48
      endLine: 92
    - path: reservation_source.py
      symbol: ReservationService.cancel_reservation
      startLine: 94
      endLine: 105
    - path: reservation_source.py
      symbol: ReservationService._utc
      startLine: 114
      endLine: 117
---

# 事实说明与样稿范围

本页供维护者复核，不是生成知识的替代品。案例目的和人物场景是明确标注的教学设定；下表中的行为则由可执行实现决定。评审时不得将“常见预约系统通常如此”当成本案例事实。

## 已实现事实

| 编号 | 可复核主张 | 知识主定义 |
| --- | --- | --- |
| F01 | 只有创建、取消两个业务调用，没有 HTTP 端点或查询列表接口 | [接口](modus/knowledge/domain/reservation/references/api.md) |
| F02 | 固定会议室为 A201（6 人）和 B105（12 人），构造服务实例时装入 | [资源](modus/knowledge/domain/reservation/references/infrastructure.md) |
| F03 | 文本去除首尾空白；人数必须是正整数且不接受布尔值；容量不足时拒绝。实现不核实参会名单 | [规则](modus/knowledge/domain/reservation/references/rule.md) |
| F04 | 起止时间必须带时区，写入前统一为 UTC；区间要求开始早于结束 | [对象](modus/knowledge/domain/reservation/references/object.md) |
| F05 | 同一会议室的 confirmed 记录按半开区间判断冲突，相邻边界不冲突 | [冲突规则](modus/knowledge/domain/reservation/references/rule.md#同一会议室的区间冲突) |
| F06 | 所有预期业务拒绝都发生在写入前；成功创建后才推进实例内编号 | [创建契约](modus/knowledge/domain/reservation/references/api.md#创建预约) |
| F07 | 取消保留原预约，替换状态和取消原因；新的冲突检查忽略 cancelled 记录 | [状态机](modus/knowledge/domain/reservation/references/state_machine.md) |
| F08 | 取消先检查编号、存在性、原因，再判断是否已取消；有效重复取消返回原取消结果，原因不覆盖 | [取消契约](modus/knowledge/domain/reservation/references/api.md#取消预约) |
| F09 | 返回值是不可变对象；服务取消时替换对象，早先拿到的对象仍显示旧状态 | [返回快照](modus/knowledge/domain/reservation/references/object.md#不可变返回值与当前状态) |
| F10 | 调用及写入都在当前进程同步完成；没有返回后的后台阶段 | [协作](modus/knowledge/domain/reservation/references/downstream.md) |

## 明确未实现的能力

下面的否定结论以本教学项目的完整服务实现为范围，不向任何真实业务系统推广。

| 范围 | 结论与影响 |
| --- | --- |
| 身份与权限 | 不校验组织者身份、角色或房间权限；能调用对象的人都能按编号取消 |
| 持久化与恢复 | 没有数据库、文件保存、备份、重放或恢复入口；实例销毁后数据不可恢复 |
| 并发一致性 | 没有锁、事务、唯一约束或跨实例协调；仅按顺序调用解释冲突保证 |
| 日历政策 | 不读取当前时间，不限制过去时间、营业时间或最大时长，也不自动结束或过期 |
| 可观察性 | 没有查询、列表、历史日志、指标或审计 API；调用方保留收到的结果与异常 |
| 重试与通知 | 不自动重试、不发送通知、不使用消息；创建没有请求幂等键 |

`confirmed` 表示预约占用，不表示会议真的发生；`cancelled` 表示业务取消，不表示删除。内存状态不是持久状态，UTC 归一也不是排期调度。

## 用于复核的业务样本

所有下列值均为教学示例。主线为林青预约 A201，人数为 4，时间为 `2026-11-05 09:00—10:00 +08:00`；返回时间为 `01:00—02:00 UTC`。在空实例内它得到 `RES-0001`，取消原因为“会议改期”。

“参会人数包含组织者”是本教学业务约定，用来明确输入数字的含义；它不是代码已经核验过的事实。实现只接收一个整数并检查其合法性和容量，没有名单或身份信息，无法验证调用方是否确实把组织者计入。成品应保留这一区别。

正例应覆盖同房间相邻时段、不同房间同一时段、取消后原时段重订；反例应覆盖重叠、超容量、无时区、等长为零的区间、空白组织者和未知预约。修改错误检查顺序时，应同步修改多条件失败的读者问题，避免文档仍承诺旧优先级。

本基线不以逐字匹配成品作为正确性判断。评审关注上述事实有无改变、读者能否完成预设任务、图表是否表达真实条件，以及不支持的能力是否被错误补写。
