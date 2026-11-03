# 保留任务的人工回读

本文件提供独立于 Java 调优样稿的输入、修改草稿和验收判断。代码是夹具声明与示意，没有 Android/iOS、协程或真实数据库运行环境；人工回读不计编译/集成通过。

## Kotlin Android：刷新本地快照

输入契约：Kotlin 1.9、JVM 8；Android source set 已依赖 kotlinx.coroutines 1.7。现有 `SnapshotRepository.fetch(): Snapshot` 是可取消挂起网络调用；`replace(snapshot)` 是挂起本地事务入口，原子替换，提交后不可撤销。调用方已提供页面生命周期 scope 和项目 `UiFailure.from(Exception)`；公共 commonMain 没有 Java/Android API。修改任务：页面刷新写入本地存储，取消不能显示错误，也不能创建全局 scope；一次刷新失败保留旧数据。

选 foundation + kotlin + mobile/android + concurrency/database/http；本地存储不意味着 backend/MySQL。复用上述 repository、scope 和错误映射，不复制 Java 池或开启第二个数据库连接。建议的 Android 入口结构：

```kotlin
scope.launch {
    try {
        val snapshot = repository.fetch()
        ensureActive()
        repository.replace(snapshot)
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (failure: Exception) {
        showFailure(UiFailure.from(failure))
    }
}
```

依赖导入为 kotlinx.coroutines.launch/ensureActive/CancellationException；scope、repository、showFailure 与 UiFailure 是输入项目定义，不能宣称任意项目都存在。前提：本页面不接受并发刷新，已有入口负责禁用或串行化；fetch/replace 的实现不阻塞 UI 线程。没有这些证据就不能套此例。

人工回读：fetch 期间取消应传播且不进入 replace；替换失败由原子事务保留旧数据；提交后取消可能已写入，不能承诺撤销。页面取消不承担可靠后台同步任务。应运行的独立检查是取消中的 fetch、事务写入失败、提交后取消和页面销毁；本样本未运行这些检查。

## 同语言不同环境与混合契约

输入：同仓 TS 浏览器/Node 与上述 Kotlin 客户端共享 JSON 协议 `revision: string`（十进制 64 位标识），TS target ES2020，Kotlin commonMain 无 JVM。任务：构造 DTO 并比较是否为同一次修订。

选共同的协议不变量，语言写法分开。TS 不把 revision 转 number，Kotlin 不把它强行转 Int；沿输入契约保留精确字符串相等。若需数值排序，先确定协议是否允许前导零，再使用各平台可验证的精确解析；不能引入 Java BigInteger 到 commonMain。共享 API 的兼容定义只维护一份，语言入口各补转换例外。人工判断：无平台专属依赖，保留大值精度；数值排序需求未被本任务授权推定。

## 未适配 Swift + SQLite CLI

输入只确认 Swift 5.9 命令入口与已有 `Store.inTransaction`、`Store.updateIfRevision`，没有专用 Swift 规范，依赖库存另有未调用的 PostgreSQL driver。任务：更新一条记录并报告冲突。

选 foundation + cli + database + 通用降级；排除 PostgreSQL adapter，不套 C++ RAII 或 Kotlin coroutine。先核实上述函数精确签名/失败/所有权，默认复用它们处理条件更新与退出码；输入尚未提供这些定义，所以当前只能给“验证输入 → 已有事务入口 → 条件更新 → 影响行数映射 → 错误输出”的结构，不能编造可编译 Swift 调用。下一动作是读 Store 定义与代表调用者。人工判断：明确专用覆盖限制和缺口，未把解析可见的 .swift 当作规范完备。

## 冲突、重复与版本负例

| 保留输入 | 合理输出与检查 |
| --- | --- |
| Java 8，外部样例采用 List.of/orTimeout；团队只要求返回不可变结果 | 排除不支持 API；可核验后用 Collections.unmodifiableList(new ArrayList<>(result))，保留语义，不升级 JDK |
| 团队材料明确字段注入，通用文章推荐构造器 | 在声明范围遵循团队，记录通用建议被细化；不得把参考项目偏好传播到无声明模块 |
| 团队材料要求复杂度阈值 A，启用 analyzer 阈值 B，无替代声明 | 并列要求与执行现状；本次代码尽可能同时满足，实质冲突才澄清，不按加载顺序覆盖 |
| language、database、MyBatis 都提条件更新 | database 保存完整行为，MyBatis 只补绑定/插件覆盖，项目条目指出真实 Mapper；不生成三份全文 |
| 旧 Java 任务裸用 commonPool、join，无超时，出现次数很多 | 记现状/反例，不归纳强制；核实适用 executor 后给有条件建议，不捏造已经存在的超时保障 |

这些任务验证选择与推理边界；缺工具或缺真实定义时保留限制，比提供虚构 API 更符合编码目标。它们未构成统计意义上的独立生成评测。
