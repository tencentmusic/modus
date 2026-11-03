# 编码规范模块索引

先读[选择与组合](composition.md)，再按当前构建单元和任务选读下表中的入口或锚点。这里是作者使用的内置内容库，不是目标项目的政策，也不是生成产物的目录模板。解析器能识别某种语言，不代表该语言已有专项规范覆盖。

| 维度 | 稳定入口 | 选择条件与职责 |
| --- | --- | --- |
| 公共基础 | [foundation.md](foundation.md) | 所有语言；方法组织、值契约、复用、错误和表达；不指定语言语法或团队排版 |
| 语言 | [Java](java.md)、[Kotlin](kotlin.md)、[JavaScript](javascript.md)、[TypeScript](typescript.md)、[Python](python.md)、[Go](go.md)、[Rust](rust.md)、[C](c.md)、[C++](cpp.md)、[C#](csharp.md)、[PHP](php.md) | 按实际编译版本、target、source set、运行平台选择；相关语言共享基础并保留差异 |
| 工程类型 | [工程类型](engineering-types.md) | backend、frontend、mobile/android/ios、desktop、cli、library、worker、data、infrastructure、plugin 可组合；按运行入口核验 |
| 专项能力 | [数据库](capabilities/database.md)、[配置](capabilities/configuration.md)、[并发任务](capabilities/concurrency.md)、[HTTP 与文件](capabilities/io.md)、[缓存与消息](capabilities/cache-messaging.md) | 实际读写、装配或任务明确需要时选；数据库同样适用于客户端和 CLI |
| 框架和产品 | [Spring](adapters/spring.md)、[MyBatis](adapters/mybatis.md)、[Apollo 配置中心](adapters/apollo.md)、[React](adapters/react.md)、[MySQL](adapters/mysql.md)、[PostgreSQL](adapters/postgresql.md) | 必须核实版本、激活机制和调用；只维护对公共/语言/专项规则的实现差异 |
| 项目和团队 | 目标项目的材料、工具配置、公共封装及代表使用者 | 本项目的明确要求、错误模型、基类、线程池、客户端和兼容条件；由调查产生，不从内置库预填 |

[Web](web.md) 和 [.NET](dotnet.md) 保留为已有调查导航；Web 不等于一门语言，.NET 不等于 C#。未列出的语言、框架、平台按[通用降级](composition.md#未适配与扩展)处理，不套相近语言的整套规则。现有语言入口中的六类调查维度继续用于定位证据，新增编码默认方案与之互补。
