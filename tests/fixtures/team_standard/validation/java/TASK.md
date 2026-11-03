# 独立编码任务：预留批次

输入为本目录 Kit.java，Java 8，无第三方依赖。实现 ReserveBatch.reserve：可信租户已由调用方建立，逐项验证非空非空串 ID，允许重复并保序；非法输入在任何写入前失败。使用现有 Store.tryReserve(tenant, id) 条件写入，false 表示状态不允许，不能包装成成功。每次操作使用已验证 Limits 快照，最多一个 window 的任务在途，总等待预算为 waitMillis。必须复用注入 Executor，不能创建池、引入 Spring/Guava 或虚构事务。

声明来源：本任务明确要求采用 JDK 8 与 IllegalArgumentException 输入错误；Kit 的接口注释为当前契约。Executor 可能同步拒绝；任务可能失败、超时或中断。错误传播，允许已有单条写入完成，不承诺整批原子性或 cancel 撤销写入。线程池不属于调用者，静默丢弃任务的执行器不适用。

选择记录：foundation + java + backend/worker 的批量边界 + concurrency/configuration/database。没有 Spring/Apollo/MyBatis 装配，排除这些适配器；Store 是已有条件写入能力，数据库方言与线上事务未被本样本验证。实现草稿是 solution/ReserveBatch.java，行为检查位于 checks/ReserveBatchCheck.java。
