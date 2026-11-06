# PostgreSQL 适配差异

仅在实际 PostgreSQL 数据源/驱动已确认时选择；先读[数据库专项](../capabilities/database.md)，核对 server、driver、ORM 和迁移工具版本。

默认复用 schema/search_path、标识符、ID 生成、时间与 JSON 映射约定；MySQL 的反引号、AUTO_INCREMENT 和 ON UPDATE 时间列语法不可直接复制。是否采用 identity、RETURNING、upsert 或并发索引取决于版本与真实契约，不因产品支持就推定项目已采用。

核对 NULL/唯一性、隔离与锁、事务失败后的恢复和迁移命令是否可在事务中执行。检查实际返回行数/记录、并发冲突与旧代码兼容；使用[对应版本文档](https://www.postgresql.org/docs/)及实际环境验证，不以 SQLite 测试代替 PostgreSQL 方言与并发结论。
