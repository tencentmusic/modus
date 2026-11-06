# Go 约束调查

## 编码默认方案

组合[公共基础](foundation.md)和专项，以下为通用建议。nil slice/map、空集合和接口持有 typed nil 分别核验；map 迭代不提供业务排序，唯一索引检测重复。错误沿已有类型和 errors.Is/As 传播，不靠字符串匹配；包装与日志责任层保持一致。

创建成功后登记 defer 清理，长循环不要让资源堆到整个函数返回才释放。goroutine 有启动者、停止条件和结果消费者，channel 关闭者明确；复用有界执行能力，context 传递 deadline/取消，cancel 释放派生资源。捕获循环变量前核对工具链与语言版本行为；没有 errgroup 依赖不凭空 import。检查取消、慢依赖、错误链、Rows.Err 与退出等待。

以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读[共享方法](../constraint-extraction.md)。以 `go.mod/go.work`、构建标签、启动装配和实际包依赖确定调查范围；Gin/Echo/Chi/Kratos、gRPC、GORM/sqlx/sqlc 只在存在时选读。不要把 Java 分层名称强加给 Go 包。

## 1. 架构/分层/链路事实

- **证据入口与追查**：module/replace/workspace、`cmd` 入口、`internal` 包、路由注册、HTTP/gRPC server、Wire/Fx 或手工构造、任务与消费者；将接口、具体实现、构造参数和调用方法连接起来。查 build tags、平台文件、测试替换实现和生成代码的来源。
- **可沉淀与误判**：二进制/包职责、装配点、协议到业务与存储的链路及写入归属。目录名不是业务分层证据，接口名不证明选中哪个实现；`go.work` 的本地组合不一定是发布时依赖。接口和函数值未解析时写候选关系。

## 2. 架构约束

- **证据入口与追查**：`internal` 可见性、导入检查/lint、团队声明、公共接口/Proto 与生成源；检查业务包能否直接拿到 DB/client，以及服务间是否绕过封装。追 `BeginTx`/事务闭包、传入 repository 的 `*sql.Tx`/DBTX 或 GORM tx、提交/回滚结果及中途使用全局 DB 的旁路。
- **可沉淀与误判**：包与契约边界、权威写入、同一业务事务必须使用的句柄和范围。某次接口抽象或包布局只支持该范围事实；不能从“没有反向 import”归纳团队禁止所有同层协作，也不能把开启事务等同后续所有 SQL 都在事务中。

## 3. 服务治理

- **证据入口与追查**：从路由组/中间件和 gRPC interceptor 到 handler/service/client，追 `context.Context` 的创建、deadline/取消、派生、传递与 `cancel`；查 `context.Background/TODO` 是否切断请求生命周期。核对共享 `http.Client/Transport`、server timeout、SDK 重试、错误映射、metrics/trace 注册、goroutine 启停、errgroup/channel、有界并发、进程信号和 Shutdown。
- **可沉淀与误判**：请求上下文与超时传播约定、后台工作的独立生命周期、客户端复用、并发上限、错误传播和退出等待。后台任务脱离请求可能是合法设计，需独立终止机制的证据；不能一律禁止 Background。默认零值、环境覆盖和代码显式值分开，不推测生产超时。

## 4. 中间件知识

- **证据入口与追查**：migration、SQL/sqlc 源、GORM scope/hooks、sqlx 查询、数据库池与 `QueryContext/ExecContext`，核对租户过滤、软删、稳定排序、唯一键和扫描/NULL 类型；检查 `Rows.Close/Err`、事务内使用正确句柄。沿 Redis key/TTL/锁封装、消息 handler/ack/offset 到状态落库和失败返回；查序列化、重复、重放、配置加载及定时任务去重。
- **可沉淀与误判**：项目采用的查询、事务、资源释放、缓存和消息幂等规则；按实际 scope 明确 ORM 默认过滤与 raw SQL 的差异。`defer Rollback` 不代表 commit 失败被处理；请求 context 取消不证明所有驱动/远端副作用已撤销。生成 SQL 文件只作证据，修改入口是查询源与生成命令。

## 5. 代码规范约束

- **证据入口与追查**：公共错误/状态码、`errors.Is/As`/包装、日志与 trace、构造器、接口使用方、nil/零值、defer/panic/recover、资源所有权和并发访问；核对 golangci-lint/staticcheck 配置及实际 CI、table tests、fake/mock、integration/build tags。
- **可沉淀与误判**：本项目的错误传递、日志责任层、依赖装配、context 参数与生命周期、资源关闭、测试替身及代码生成约定。不要把每层都记录相同堆栈当作规范，recover 存在不等于所有 goroutine 都被保护；少数命名或接口定义位置只能描述有证据的默认写法。

## 6. 工程规范

- **证据入口与追查**：go/toolchain 指令、workspace/replace/vendor、Go 环境设置、Make/Task 脚本、`go generate`/Proto/sqlc/mock 生成、CI 的 test/vet/lint/race、CGO、交叉编译与镜像。查生成器版本和生成产物的兼容条件，测试命令实际选中的包与标签。
- **可沉淀与误判**：可执行构建/验证、生成源维护方式、目标平台与本地/CI 差异。race 未启用或未覆盖的路径明确说明；工具存在不证明已运行，生成指令也不能未经检查直接执行其外部命令。

## 组合查证示例

若 API handler 传入请求 context、repository 使用 QueryContext，而异步补偿使用独立根 context：分别描述请求链取消约定与补偿任务生命周期；再查重试幂等和退出时等待。不可归纳成“所有操作必须继承 HTTP context”，也不能声称取消已经回滚远端动作。

机制核验参考：[取消传播](https://go.dev/doc/database/cancel-operations)、[数据库事务与事务句柄](https://go.dev/doc/database/execute-transactions)。按目标驱动、ORM 和框架版本核对具体行为。
