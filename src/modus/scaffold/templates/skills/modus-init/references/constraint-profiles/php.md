# PHP 约束调查

## 编码默认方案

组合[公共基础](foundation.md)和专项，以下为通用建议。确认 PHP 版本、strict_types 与 FPM/常驻 worker；不能把请求结束清理假设套到常驻进程。null、空串、零与 false 分别处理，empty/宽松比较可能合并不同语义；数组键转换、覆盖与顺序需核验。

复用项目 service/container、DTO/validator、异常和 DB；简单映射用惯用表达，副作用显式循环。资源沿 try/finally 或真实框架生命周期清理；事务异常沿现有模型传播，长驻 worker 清理请求级状态。检查转换、重复键、跨请求状态、失败与释放，不生成目标版本不支持的语法。

以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读[共享方法](../constraint-extraction.md)。从 composer.json/lock、autoload、启动脚本、路由与容器配置确定 PHP/框架版本；Laravel、Symfony、ThinkPHP、Hyperf/Swoole/Octane 等只查项目实际使用的机制。区分 PHP-FPM 请求与常驻进程生命周期。

## 1. 架构/分层/链路事实

- **证据入口与追查**：PSR-4/classmap/files autoload、public/CLI 入口、路由注册、Service Provider/容器 binding、Symfony services/config、ThinkPHP 模块与事件配置；追 Controller/Action → Application/Service/Domain → Model/Repository/DB，再追命令、Job、Listener 和定时触发入口。Facade 静态外观需解析实际绑定，不把文件夹或类后缀当作业务边界。
- **可沉淀与误判**：应用/包职责、装配实现、HTTP/CLI/队列链路和数据写入归属。composer 依赖存在不证明某组件启用；容器按环境选择、魔术方法和动态事件未解析时保留条件，不编造唯一调用链。

## 2. 架构约束

- **证据入口与追查**：团队规范、包边界/Deptrac 等检查、请求验证、Gate/Policy/Voter/中间件、serializer/API resource、mass assignment 白名单、仓储与 raw DB 旁路；核对租户上下文来自哪里、全局 scope 是否被移除、CLI/队列是否复用鉴权或有独立可信来源。追 DB::transaction/Doctrine transaction、连接选择、异常及外部副作用。
- **可沉淀与误判**：接口与模型边界、可信身份、可写字段、权威存储及事务范围。中间件仅证明经过它的入口；模型白名单不等于业务授权，查询 scope 不保证 raw SQL 隔离，不能把数据库异常或强制转换当参数校验。已有业务不变量与团队声明分开说明。

## 3. 服务治理

- **证据入口与追查**：HTTP 客户端工厂/Guzzle options、超时/重试和错误转换，queue driver/connection/worker 配置、Supervisor/Horizon/部署命令；核对 Job tries/backoff/timeout、可见性或 retry_after、失败记录与人工重放。追事务提交与 dispatch/afterCommit/after_commit 的先后，事件/监听器也逐条核验；查限流、监控、日志上下文和 worker reload。
- **可沉淀与误判**：外部调用封装、可重试失败、队列超时与再次投递关系、事务后派发条件、任务失败处理和进程重启要求。队列只保证投递不保证业务幂等，重试会不会重复落库要回看唯一键/状态写入。常驻 worker 内单例/静态状态可能跨请求或任务保留，不能套用 FPM 请求结束即清理的假设。

## 4. 中间件知识

- **证据入口与追查**：migration/schema、Eloquent/Doctrine 映射、cast/fillable/hidden、global scope、软删/关系加载与真实 SQL；查金额精度、时间时区、主键类型、租户条件、N+1、批量遍历和事务连接。沿 Cache/Redis store 到 key/TTL/lock、序列化、cache tag/invalidate；沿 MQ Job/事件载荷到 ack、失败、唯一约束和重放；核对配置中心、scheduler 单实例锁、文件/对象存储权限。
- **可沉淀与误判**：项目的资源封装、字段映射、查询/缓存/消息约定和迁移兼容条件。模型的 hidden 不代表所有手工数组/日志都脱敏；应用配置中的 Redis 库编号或示例 TTL 不直接成为生产约束。业务锁与队列 unique job 的去重范围分开，不假定外部调用恰好一次。

## 5. 代码规范约束

- **证据入口与追查**：项目 PHP 版本、strict_types、类型声明、enum/value object、异常处理器/错误响应、日志、Request/DTO/Resource、依赖注入、PSR 工具配置与实际调用；核对 null/空串/零值、数组 shape、JSON cast、敏感字段、可变单例，以及 PHPUnit/Pest/Mockery 的测试/替身。
- **可沉淀与误判**：本项目的类型/校验/转换、异常、资源响应、容器生命周期、命名与测试约定。Composer 声明某 PSR 包不等于团队全面采用其风格，少量 strict_types 不能推广全项目强制；不引入当前 PHP 版本不支持的语法，也不把框架魔术属性误写成显式字段契约。

## 6. 工程规范

- **证据入口与追查**：Composer 锁、platform PHP/ext、autoload 优化、scripts/plugin、容器扩展和启动配置、PHPStan/Psalm/Pint/CS-Fixer/PHPCS、CI test 命令、迁移/发布脚本。核对 config/route/container cache 的生成位置和环境，配置改动的生效方式，常驻 worker 是否按部署重启。
- **可沉淀与误判**：可执行安装/构建/聚焦测试、静态检查范围、配置/迁移顺序、兼容与回滚条件。只从已配置且实际启用的机制提取要求；不臆造扫描/审批门禁，不执行未经检查的 Composer scripts，不假定 .env 修改会立即影响已缓存配置。

## 组合查证示例

若某 Job 在事务内派发：追 queue connection 的提交后派发设置与 Job 覆盖，再查 worker 读取的数据和失败重试。已验证使用提交后派发时，写清模块与连接范围；另一个连接没有该保证时单列差异。不能仅凭框架支持 afterCommit 就认定团队已采用，也不能把每个 Job 都视为天然幂等。

机制核验参考：[Laravel 队列、事务与 worker](https://laravel.com/framework/docs/10.x/queues)。该链接说明一种版本语义；实际调查以项目锁定版本的文档与实现为准。
