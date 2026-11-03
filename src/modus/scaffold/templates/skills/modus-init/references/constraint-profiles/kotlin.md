# Kotlin 调查指南

## 编码默认方案

组合[公共基础](foundation.md)、实际工程类型和专项；默认是通用建议。Kotlin 版本、JVM target、Android API、commonMain/platform source set 与 kotlinx.coroutines 版本分别核验，不把 JVM API 带入公共代码。

- 可空类型表达缺失；Java platform type 仍需校验，避免 `!!` 掩盖契约。`orEmpty()` 只用于缺失等价空，失败不能变空成功；`==` 与 `===` 分别核对值/引用语义。
- 集合短链用于纯转换，复杂校验与副作用用循环。associateBy 重复键会覆盖，唯一索引显式检查；distinctBy 仅用于允许去重的契约，分组用 groupBy。只读 List 不证明深不可变。
- suspend 不等于非阻塞；复用项目 scope/dispatcher/repository。普通工作用有生命周期的结构化并发，不擅自 GlobalScope；并发上限来自真实执行能力。捕获业务异常时保留 CancellationException 传播，finally/use 清理；页面取消与可靠后台工作分开。
- Flow 的冷/热、重放与收集生命周期由使用者核验；事务能否挂起、跨 dispatcher 查实际封装，不套 JVM 线程事务假设。

**通用建议示例（Kotlin 标准库，非空 `List<String>` 输入）**：唯一索引拒绝重复，不改写 ID；可用于 commonMain，不依赖 Java 集合。

```kotlin
val byId = mutableMapOf<String, Int>()
for ((position, id) in ids.withIndex()) {
    require(id.isNotEmpty()) { "id is required" }
    require(!byId.containsKey(id)) { "duplicate id" }
    byId[id] = position
}
```

require 表达输入契约，有项目错误模型时按真实入口细化。验证互操作 null、重复键、取消后不写存储与释放；[协程取消说明](https://kotlinlang.org/docs/cancellation-and-timeouts.html)结合锁定版本，未安装协程依赖不生成该 API。

先读[共享方法](../constraint-extraction.md)。以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读 Gradle/Maven target、source set、插件与启动装配，区分 JVM、Android 和 multiplatform 边界。调查 Spring/Ktor route、CLI、suspend API、Flow、任务和消息入口；Java interop 与生成代码需找到真实修改源。

结合 data/sealed/value class、序列化配置和使用点解释对象与状态。沿 coroutine scope、dispatcher、取消、结构化并发、事务和资源释放追失败传播；`suspend` 不自动表示非阻塞。核对测试 source set、静态检查、格式化和发布 target 的实际命令。
