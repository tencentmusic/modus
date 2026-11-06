# .NET 证据适配

以 solution/project、target framework 和发布目标识别单元；从 Controller、endpoint、命令、public API、BackgroundService、消息处理器与插件入口调查。核对 DI scope、DTO/序列化、`async`/Task、CancellationToken、EF transaction、`IDisposable`、配置绑定与测试。

反射、source generator 与容器关系需由生成物或装配验证；注册服务不证明某个实现实际解析，Task 返回也不自动等于最终业务完成。
