# Rust 调查指南

## 编码默认方案

组合[公共基础](foundation.md)和专项，以下为通用建议。Option 表示缺失，Result 表示失败；不为通过编译盲目 unwrap/clone/Arc。集合去重与 map 覆盖按业务键决定；迭代器用于纯转换，副作用和错误顺序显式展开。

资源沿所有权与 RAII 管理，Drop 不代表外部异步操作已成功；锁与 await 的组合核对运行时和类型约束。复用 runtime、错误类型、client 与任务管理，spawn 结果须被观察；不为小功能另建 runtime。依赖 feature、MSRV、平台分别验证；丢弃 future 的取消安全性回到真实操作，不默认回滚副作用。

先读[共享方法](../constraint-extraction.md)。以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读 Cargo workspace、crate target、feature、build script 与公开文档。调查 binary subcommand、public crate API、Web handler、trait/宏扩展点、任务和 FFI；feature-gated 行为必须注明实际构建条件。

结合 enum/newtype/serde/schema 与读写点解释对象和状态。沿 ownership、borrow、Send/Sync、async runtime、channel、锁、错误类型和 Drop 追资源及失败边界；类型能力不等于运行策略。核对 test、doctest、clippy、fmt、feature matrix 和发布配置的实际入口。
