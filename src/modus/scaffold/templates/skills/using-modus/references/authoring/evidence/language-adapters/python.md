# Python 证据适配

以 `pyproject.toml`、package、entry point、应用入口和作业定义识别单元；从路由、命令、公开模块、任务/消费者、数据流水线和插件入口调查。核对 Pydantic/dataclass/ORM 的运行时语义、decorator 注册、session/transaction、sync/async、线程/进程、上下文管理器、配置和测试 fixture。

动态导入、猴子补丁和框架自动发现必须由实际注册、启动路径或测试补证；async 函数不自动证明调用链非阻塞或资源生命周期正确。
