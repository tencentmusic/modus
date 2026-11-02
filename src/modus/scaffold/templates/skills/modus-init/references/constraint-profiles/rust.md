# Rust 调查指南

先读[共享方法](../constraint-extraction.md)。以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读 Cargo workspace、crate target、feature、build script 与公开文档。调查 binary subcommand、public crate API、Web handler、trait/宏扩展点、任务和 FFI；feature-gated 行为必须注明实际构建条件。

结合 enum/newtype/serde/schema 与读写点解释对象和状态。沿 ownership、borrow、Send/Sync、async runtime、channel、锁、错误类型和 Drop 追资源及失败边界；类型能力不等于运行策略。核对 test、doctest、clippy、fmt、feature matrix 和发布配置的实际入口。
