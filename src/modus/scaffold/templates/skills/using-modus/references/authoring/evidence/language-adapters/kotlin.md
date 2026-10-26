<!--
本页只适配取证方法，领域身份、稳定路径与正文职责由共享框架维护。
-->

# Kotlin 证据适配

以 Gradle target、source set、JVM/Native/JS 平台和发布单元识别边界；从 Spring/Ktor 入口、命令、public API、任务和 Flow 消费端调查。核对 data/sealed class、序列化、`suspend`/Flow、coroutine scope、dispatcher、取消、跨协程事务、资源释放和 Java interop。

不得把 suspend 调用自动描述为并发或后台执行；必须确认调用上下文、scope 所有者和完成/取消传播。共享源码集也不自动证明各 target 行为一致。

## Android / Compose / 多平台客户端

将 `commonMain`、`androidMain`、`iosMain`、各平台后缀与 test source set 放回实际 Gradle module、source-set dependsOn 和构建变体核验。`expect`/`actual` 是候选关系，不凭同包同名就认定当前产物使用了某实现。`internal` 受模块边界限制；import alias/star、顶层声明、extension receiver、companion/object、属性委托及泛型约束均可能改变名称绑定，不能照搬 Java 文件名等于类型名的规则。

从 Composable、导航注册、用户 action、ViewModel 绑定、Flow/StateFlow 订阅与生命周期停止点追踪。`Box`、`Column`、`WithViewModel<T> { … }` 等 DSL 是函数调用和尾随 lambda，不是类声明；核对 recomposition、`remember`、`LaunchedEffect` key、collect 的 scope/dispatcher 与取消。属性 `by` 不等于普通赋值，读取状态不等于执行副作用，Compose 回调中的操作也不一定只运行一次。

对 JNI、Kotlin/Native cinterop 或 IDL 生成绑定，联读[原生与跨端适配](native.md#跨端契约与状态链)：核对生成来源、Action 参数映射、对象所有权、State/Event 回调、线程和解绑；大小写转换后的 `uploadConfig`/`UploadConfig` 本身不足以证明跨语言调用。生成目录不重复计入业务实体，端侧权限、路由和系统操作不能从知识中省略。
