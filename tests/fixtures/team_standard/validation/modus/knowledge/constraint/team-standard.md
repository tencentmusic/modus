# 演练项目 Team Standard

适用于此夹具的 Java 8 批量服务和 TypeScript 5.6 / ES2020 浏览器、Node 20 任务包。依据是本目录保留的任务声明及 Kit/ports 源码，非组织政策或生产系统规范。Kotlin/Swift 的人工回读材料未参与这份已核验入口。外部依赖清单不证明框架激活，本项目不选择 Spring、React、Apollo 适配。

| 编码场景 | 范围 | 默认入口与规则 |
| --- | --- | --- |
| Java 批量预留 | Java 请求线程，非共享执行池内部 | Kit.Store.tryReserve + Kit.executor + Kit.Limits；[批量规则](#item-java-reserve) |
| 浏览器快速查询 | 浏览器 DOM 环境 | LookupClient.lookup；[取消与晚到结果](#item-browser-lookup) |
| Node 批量预留 | Node Worker；不读 DOM | WorkerPorts.readPolicy/mapWindow/updateIfPending；[任务规则](#item-node-reserve) |
| TS 标识集合处理 | 共享 ES2020 包 | normalizeIds；非法项失败、允许重复且保序，不重复实现 |

源码事实解释已经存在的接口；明确约束来自各任务契约；通用建议说明选型，不伪装成组织硬规定。示例属于表达形式，引用的代码已显式区分输入 API 和实现草稿。完整源文件可定位真实签名，不能因包含旧代码就复制整个文件。

## 默认写法与复用

### Java 批量预留

<a id="item-java-reserve"></a>
性质: 明确约束（本夹具任务）
状态: current
适用: Java 8，调用方提供可信租户及非静默丢弃的专用 Executor；请求线程不属于该池。

先校验全部 ID，再按首现顺序去重；空批是成功空结果，非法项不能过滤后宣称全批成功。复用 [Kit](../../../java/Kit.java) 的 `Store.tryReserve(String tenant, String id): boolean`，false 表示状态冲突；单条写入原子，不承诺整批事务。配置是构造时验证的不可变 `Limits(window, waitMillis)`，单位毫秒，一次操作用同一快照；没有动态刷新能力。

默认用带已注入 executor 的 CompletableFuture 按窗口提交，以剩余总预算 get 结果。依据为[任务契约](../../../java/TASK.md)，实现示例见 [ReserveBatch](../../../java/solution/ReserveBatch.java)。示例依赖仅 JDK 8 与 Kit，不创建新池、不引入 Guava 或 Java 9 API。

#### 失败与例外

同步拒绝在提交处传播，异步失败保留 cause，中断恢复标记。超时/cancel 不保证运行中的任务停止，已经预留的记录可能保留；调用方以原条件写入契约恢复，不能假设事务撤销。共享池由宿主管理；不适用于可靠后台任务、poll 线程或不接受部分完成的批事务。

#### 如何检查

[行为检查](../../../java/checks/ReserveBatchCheck.java)覆盖非法输入无副作用、顺序、配置、状态冲突、异常、拒绝、超时及中断。测试替身不证明真实 DB 事务、线程池容量或部署时限；需要真实环境才可写相应保证。

### 浏览器查询取消与晚到结果

<a id="item-browser-lookup"></a>
性质: 明确约束（本夹具任务），序号隔离是通用建议的实现选择
状态: current
适用: 浏览器 DOM，LookupClient.lookup 接受本项目 CancelSignal；客户端可能忽略取消。

复用 [ports](../../../typescript/ports.ts) 的 `lookup(id, signal): Promise<string>` 和 normalizeIds；加载新 ID 时取消旧请求并增加序号，仅当前序号且未停止时发布结果。失败发布 failed 分支，不返回空字符串当成功；停止后不更新 UI。不要因 client 接受信号就假定服务端撤销或旧回调不会发生。

示例 [createLookup](../../../typescript/solution/browser.ts) 的 AbortController 只在浏览器入口使用，不能搬入只承诺 ES2020 的共享包。此项目没有 React lifecycle，不能发明 hook；真正接 React 时需额外核验 effect cleanup 与依赖。

检查快速切换、旧成功/旧错误、最新失败和停止后晚返回，见[行为检查](../../../typescript/checks.cjs)。UI 展示和真实 HTTP 状态映射由当前未提供的调用方承担，不宣称覆盖。

### Node 批量任务

<a id="item-node-reserve"></a>
性质: 明确约束（本夹具任务）
状态: current
适用: Node Worker，TypeScript 5.6 / ES2020，不含 DOM 类型或浏览器全局。

复用 normalizeIds、WorkerPorts 的 readPolicy、mapWindow 和 updateIfPending。校验 ID 后只读取一次配置快照；window 必须为正安全整数。把实际写入交给已有 mapWindow 控制并发，false 映射冲突，拒绝继续传播。完整[实现示例](../../../typescript/solution/worker.ts)不增加库或重复封装调度器。

mapWindow 的 Promise.all 不自动取消同窗口其他写入，失败可以部分完成，后续窗口不再提交；没有可靠任务日志，不能宣称重启恢复。需要整批原子性或持久化重试时必须重新核实存储和任务能力。按纯 ES2020 编译，并检查配置读取次数、复用入口、并发峰值、重复顺序与失败；真实数据库和 Node 进程停机另验。

## 方法与工具的取舍

性质: 通用建议
适用: 本页范围的新增/修改代码及示例。

让校验、集合转换、提交和结果处理可辨认，复杂条件命名，副作用不隐藏在纯转换中。没有项目 formatter 或圈复杂度阈值证据，不捏造强制数值/注释样式；遵循已声明接口与当前局部格式。只有真实变化点才新增抽象，本样例现有端口已足够。
