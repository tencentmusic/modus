# Python 调查指南

先读[共享方法](../constraint-extraction.md)。以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读 `pyproject.toml`、lock、包布局、entry points、框架配置与测试配置。区分可导入公共 API、console script、Web route、任务/消费者和内部模块；`__all__`、文档与实际调用共同判断稳定契约。

沿同步/async 边界追 context、session、事务、依赖注入、异常映射和资源清理。Pydantic/dataclass/ORM 声明需结合序列化、迁移与读写点解释字段；装饰器存在不证明所有入口执行同一校验。核对 pytest fixture、类型检查、lint、迁移和打包命令是否真实启用。
