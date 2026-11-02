# Kotlin 调查指南

先读[共享方法](../constraint-extraction.md)。以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读 Gradle/Maven target、source set、插件与启动装配，区分 JVM、Android 和 multiplatform 边界。调查 Spring/Ktor route、CLI、suspend API、Flow、任务和消息入口；Java interop 与生成代码需找到真实修改源。

结合 data/sealed/value class、序列化配置和使用点解释对象与状态。沿 coroutine scope、dispatcher、取消、结构化并发、事务和资源释放追失败传播；`suspend` 不自动表示非阻塞。核对测试 source set、静态检查、格式化和发布 target 的实际命令。
