# Spring 适配差异

仅在实际 Spring 容器装配和调用已确认时选择，核对 Boot/Framework 版本、Profile 与 Bean 条件。联读语言、[并发](../capabilities/concurrency.md)、[配置](../capabilities/configuration.md)、[数据库](../capabilities/database.md)中涉及的主题。

默认复用项目已注册的 Bean、事务管理器、配置门面和执行器；注入形式来自项目工具/材料，不强推字段或构造器。@Qualifier 选择的名称须存在且负载适用。代理事务需核对实际调用、传播、数据源与异常回滚；同类调用、异步线程或多库不会凭注解自动满足事务要求。

配置多字段优先沿项目已有类型绑定与校验；@Value 表达式只用于已验证的简单绑定，不把配置更新等同 Bean/资源重建。TaskExecutor 的关闭、拒绝和任务装饰按对应版本实现核验。验证激活装配、代理入口、同步拒绝、异常与资源退出；[事务官方说明](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)须切到目标版本使用。
