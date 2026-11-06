# MyBatis / MyBatis-Plus 适配差异

仅在实际 Mapper 调用与扫描/SqlSession 装配存在时选择，版本和 MyBatis-Plus 插件另核实；先读[数据库](../capabilities/database.md)。Mapper 包、XML、数据源和事务管理器必须由证据连接，目录相似不能证明生效。

默认复用已有 Mapper/Service 和参数命名；新增 SQL 改生成源或 XML 正确 namespace/statement。复杂条件可先命名 wrapper 再执行以便阅读，但是否强制独立变量由团队决定。参数绑定与动态标识符分别处理，不能用字符串拼接替代值绑定。

逻辑删除、租户、分页、防全表更新等插件分别核对 raw SQL/批量/自定义路径覆盖；空权限条件不能被条件构造器省略。对象转换、影响行数、事务见公共专项，不复制整套规则。检查实际 BoundSql/参数、扫描范围和真实方言，XML 可解析不代表运行 SQL 正确。
