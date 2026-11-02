# Rust 证据适配

以 Cargo workspace、crate、feature 和 binary/library target 识别单元；从 CLI、路由、public API、trait 实现、任务和插件边界调查。核对 serde 类型、`Result`/错误映射、ownership、`Drop`、`Send`/`Sync`、async runtime、锁/channel、feature/config 与测试。

宏展开、feature 条件和动态分发未闭合时保留明确降级；所有权约束能证明资源责任，但不能单独证明业务完成语义。
