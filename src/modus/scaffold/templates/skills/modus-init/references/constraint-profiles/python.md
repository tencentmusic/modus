# Python 调查指南

## 编码默认方案

组合[公共基础](foundation.md)和专项，以下为通用建议。`is None` 区分缺失和 0/False/空集合；默认参数避免可变容器。dict 索引明确重复策略，生成器惰性与资源生命周期联读消费者；复杂副作用不放推导式。

复用项目 client/session、转换器和异常类型；在能解释的边界捕获具体异常并保留原因。局部资源用 with/async with，不关闭调用方共享对象。async 路径避免阻塞 I/O；复用限流与生命周期。TaskGroup 仅适用 Python 3.11+，旧目标沿既有任务收集/清理机制；取消不转为空结果。检查单位、重复、异常、取消与释放，格式/复杂度阈值取实际工具配置。

先读[共享方法](../constraint-extraction.md)。以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读 `pyproject.toml`、lock、包布局、entry points、框架配置与测试配置。区分可导入公共 API、console script、Web route、任务/消费者和内部模块；`__all__`、文档与实际调用共同判断稳定契约。

沿同步/async 边界追 context、session、事务、依赖注入、异常映射和资源清理。Pydantic/dataclass/ORM 声明需结合序列化、迁移与读写点解释字段；装饰器存在不证明所有入口执行同一校验。核对 pytest fixture、类型检查、lint、迁移和打包命令是否真实启用。
