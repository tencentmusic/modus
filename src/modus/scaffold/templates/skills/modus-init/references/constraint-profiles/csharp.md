# C# 编码入口

从 LangVersion、target framework、nullable、analyzer 与发布 target 确认适用范围；装配与平台取证见 [.NET](dotnet.md)。其他 .NET 语言沿通用方法，不自动套 C# 语法。

通用建议：区分 nullable、默认值与失败；LINQ 适合纯转换，注意延迟执行、多次枚举与数据库 provider 翻译。ToDictionary 前明确重复键策略；DTO/Entity 转换沿已有映射，不能让延迟查询逃逸已释放的 scope。

async 方法沿调用传递 CancellationToken；不要用 Task.Run 包装本已异步的 I/O 或阻塞等待制造线程消耗。批量任务复用既有有界执行能力，Task.WhenAll 不负责限流。使用 using/await using 前核对类型接口、语言和 target 支持；调用方不 dispose 共享注入资源。

验证取消、部分失败、异步释放、nullable 边界及不同 target 编译；数值阈值与格式以启用的 analyzer/团队要求为准。
