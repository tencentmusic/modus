# TypeScript 编码入口

先选 [JavaScript 运行基础](javascript.md)，再核对每个 tsconfig 的 target/lib/module/strict、类型依赖、包 exports 与实际运行环境。TS 编译器版本、JS 产物目标与部署运行时分别记录。浏览器、Node Worker、SSR、共享包按独立范围组合规范，不能全仓应用 DOM 或 Node API。

通用建议：外部输入先作为 unknown 经项目已有 parser/schema 缩窄；不以 `as`、非空断言或 any 消除未经验证的错误。联合类型表达真实结果分支，沿项目错误模型处理；不要为简单返回值重造 Result 框架。可空、可缺省和显式 undefined 语义取决于项目配置与协议。

集合按键的语义选择 Map/Set，唯一索引检测重复；readonly 不证明运行时深不可变。字符串/数值/日期与 DTO 转换先复用真实入口。组件属性、服务契约、生成类型的修改源分别核验。

类型库声明某 API 不会给运行环境安装实现；以目标运行时测试和打包依赖检查补充 typecheck。[TS lib 说明](https://www.typescriptlang.org/tsconfig/lib.html)用于核验声明范围，实际能力仍查目标平台。检验共享包在各承诺环境的依赖、无 DOM/Node 泄漏、非法输入及异步错误。
