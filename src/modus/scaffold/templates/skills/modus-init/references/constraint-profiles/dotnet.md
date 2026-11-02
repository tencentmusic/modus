# C#/.NET 调查指南

先读[共享方法](../constraint-extraction.md)。以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读 solution/project、target framework、NuGet lock、launch/host 配置与 source generator。调查 ASP.NET endpoint/controller、public type、CLI command、hosted service、消息 handler 和插件/DI 注册；区分接口声明、实现与生成源。

沿 middleware、身份、async/await、CancellationToken、EF transaction、序列化和异常映射追调用链。`IDisposable`/`IAsyncDisposable`、scope 与线程安全需结合创建和释放点说明。核对 nullable、analyzer、format、test、publish 与兼容 target 是否在实际构建中启用。
