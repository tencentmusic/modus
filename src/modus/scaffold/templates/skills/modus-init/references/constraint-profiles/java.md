# Java 约束调查

## 编码默认方案

组合[公共基础](foundation.md)与实际专项。以下为通用建议；项目封装与团队写法经核验后细化。源码级别、字节码、运行 JDK 和依赖 API 分别确认。

- 字符串/集合工具核对完整包名、版本、blank/empty/null 语义；没有适用依赖时用 JDK，不为两次判空新增库。包装数值用值比较并处理拆箱空值；BigDecimal 的数值与 scale 相等分开。
- 纯转换用简短 Stream；校验、外部调用、异常分流用显式循环。保序去重、分组、唯一索引分别选择结构，唯一索引检测重复。DTO 复用真实 converter/基类；Lombok 相等/日志/继承核对生成行为。
- 异步先核验共享 executor 的负载与拒绝，再使用带 executor 的 CompletableFuture。使用参数化 Future；allOf 不限流也不收集结果。Java 8 使用 get(timeout, unit)，不能生成 Java 9 的 orTimeout。总预算、中断恢复、同步拒绝和池所有权见[并发专项](capabilities/concurrency.md)；cancel 不保证中断正在运行的 CompletableFuture 任务。
- 局部 AutoCloseable 用 try-with-resources；容器资源由容器关闭。语言惯用法不授权改变团队注入、排版或公开契约。

**通用建议示例（JDK 8 标准库）**：非 null 的 `List<String> ids` 允许重复且要保序；非法项拒绝，不 trim/改变大小写。返回集合是新建可变列表。

```java
Set<String> unique = new LinkedHashSet<>();
for (String id : ids) {
    if (id == null || id.isEmpty()) {
        throw new IllegalArgumentException("id is required");
    }
    unique.add(id);
}
List<String> orderedIds = new ArrayList<>(unique);
```

导入为 java.util.List/Set/LinkedHashSet/ArrayList。有项目错误模型时替换通用异常；空白 ID 是否有效由契约决定，唯一关系不能用去重掩盖重复。检查空集合、非法项、顺序及输入未变。并发语义参考 [JDK 8 CompletableFuture](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html)。

以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读[共享方法](../constraint-extraction.md)。以实际 POM/Gradle、锁定依赖、源码和配置确定版本与模块；Spring、Dubbo、Feign、gRPC、MyBatis/JPA 仅在项目确实使用时调查。下面是查证问题，不是默认施加给所有 Java 项目的规范。

## 1. 架构/分层/链路事实

- **证据入口与追查**：根/子 `pom.xml`、Gradle settings/sourceSets、启动类、`@Configuration`、组件/Mapper/Entity 扫描、XML Bean 和 Profile 条件；从 HTTP Controller、RPC 声明及实现、消息监听器、调度任务进入方法体，追到 Manager/Application/Service、Repository/Mapper 和权威数据写入。核对接口的实际注入实现，不用包名猜层级，不把父 POM 聚合关系等同运行依赖。
- **可沉淀与误判**：模块职责、公共契约归属、实际装配及调用方向；说明实现、DTO 与接口放在哪个工程，跨域通过谁协作。多个实现/条件 Bean 无法确定激活项时保留条件。异步事件发出、受理成功与业务完成分开描述；模板后缀只是线索。

## 2. 架构约束

- **证据入口与追查**：团队/ADR、ArchUnit/模块检查、Maven Enforcer/依赖限制、包可见性、Facade DTO/IDL、公共校验与鉴权入口；对公共 Service 查所有入口及 DAO 旁路。追 `@Transactional` 的事务管理器、数据源、传播/隔离/回滚配置、代理模式和实际调用点；检查同类调用、异步线程、事件发送及多库写入是否脱离边界。
- **可沉淀与误判**：有依据的依赖限制、共享契约兼容、数据归属和事务生效条件。注解不独立证明事务开启；方法返回类型、代理方式和配置版本都需核验。多个数据源不等于支持跨库事务，不能把参考项目的自调用代理技巧变成本项目规定。现有违规调用是偏差，不自动成为合法例外。

## 3. 服务治理

- **证据入口与追查**：Dubbo consumer/provider 与方法配置、Feign 的客户端实现/拦截器、gRPC deadline、RestTemplate/WebClient 或统一 HTTP 工厂；把全局→服务→方法/调用点的覆盖关系回连配置绑定。查客户端、SDK、业务循环和消息重试是否叠加，异常究竟传播、降级、转码还是吞掉；核对线程池队列/拒绝策略、连接池等待、MDC/安全上下文跨线程传递与优雅停机。
- **可沉淀与误判**：新增外部调用应复用的入口、超时/重试预算位置、可重试错误、降级结果和可观测字段。检查 Actuator/Micrometer、熔断限流及配置中心的注册/启用点；依赖存在不等于已启用，空返回不能称为有效降级。远程配置缺失时只记录键、代码默认和未知运行值，不编造 SLA/owner。

## 4. 中间件知识

- **证据入口与追查**：实体/DDL/迁移、Mapper XML 与实际 SQL、MyBatis-Plus 拦截器、JPA 查询/flush/懒加载；核对租户和软删过滤是否覆盖自定义 SQL、批量与内部任务。查主键/金额/时间单位、唯一键、状态条件更新及索引如何支持真实查询。沿 Redis 封装到 key builder、TTL 参数、序列化、空值与失效；锁查持有者校验、租期和释放。沿 Kafka/RocketMQ/RabbitMQ 等监听配置到业务写入、ack、异常与重放；查搜索索引常量/映射、对象存储权限、配置和任务恢复。
- **可沉淀与误判**：团队封装、命名、单位、事务/幂等和兼容约定；用唯一键/状态写入/消费记录证明具体幂等范围。Broker 重投不等于业务幂等，DB 回滚不证明远程副作用撤销，注解软删不证明全部 SQL 自动过滤。单模块 TTL 或 Topic 进入域/模块细则。

## 5. 代码规范约束

- **证据入口与追查**：统一 Request/Response、异常与错误码、Bean Validation、断言、异常处理器、Mapper/MapStruct、日志封装、Checkstyle/Spotless/PMD/SpotBugs，以及 JUnit/Mockito/Testcontainers 的实际测试。核对 DTO/Entity/VO 转换的类型、单位、空值和敏感字段；查事务方法异常是否被吞、线程池是否被业务临时创建、上下文是否清理。
- **可沉淀与误判**：本项目的依赖注入、对象边界、错误封装、日志脱敏、命名/测试与 Mock 默认约定，附公共符号和代表调用者。Lombok 或命名后缀反复出现只支持归纳；不能自动要求所有团队采用某种分层或四空格。序列化输出不能仅凭 Java 字段类型推断，还要核对注解与全局配置。

## 6. 工程规范

- **证据入口与追查**：Maven/Gradle wrapper、JDK toolchain/compiler release、父 BOM、依赖管理与直接覆盖、插件实际执行 phase、Surefire/Failsafe、CI 参数、Docker 基础镜像、migration 与发布脚本。区分源码兼容、目标字节码和运行时版本；找到生成源码/IDL 的命令及禁止手改的产物。
- **可沉淀与误判**：项目实际构建/聚焦测试/lint 命令、模块依赖构建顺序、schema/契约/配置变更顺序及已有回滚要求。`skipTests`、测试排除、环境依赖和未执行检查明确标注；POM 声明插件不证明 CI 执行，不能照搬参考仓库的 JDK 或构建命令。

## 组合查证示例

若某导入任务默认使用共享执行器并调用独立事务 Bean：追任务入口 → 执行器创建 → 代理调用 → 实际数据源 → 成功/失败状态写入 → 重试。可分别沉淀项目的执行器归纳约定、域内事务边界、该模块的行级幂等与恢复规则。若另一路直接同类调用，不声称全量受事务保护；记录旁路及影响。数值和类名全部从目标项目取得。

机制核验参考：[Spring 事务注解与代理](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)。使用项目匹配版本解释语义，官方默认值不冒充项目生效值。
