# JavaScript 编码入口

适用实际 JS 构建单元；先核对 ECMAScript target、运行时/浏览器矩阵、模块格式与包 exports。与 [TypeScript](typescript.md)共享本页运行语义，框架调查按需读 [Web](web.md)。默认是通用建议，不证明项目已采用。

- 空值区分 null/undefined、空串、0、false；仅缺失才兜底时选兼容 target 的 `??` 或显式判断，不以 `||` 吞有效值。`Map` 建索引前明确重复键；对象比较与 Set 对象去重按引用，业务唯一性需真实键。
- 纯转换用短 array 链；有副作用/失败分支用可读循环。异步逐项操作不能用未收集返回值的 `forEach(async ...)`；串行、项目已有有界队列和批接口按负载选择。`Promise.all` 聚合不限制在途量，也不自动取消其他工作。
- 浏览器 UI、Web Worker、Node、SSR 的全局对象、秘密、状态、线程与资源分别核验；共享包不直接导入平台专有能力。语言版本、类型声明、polyfill 和实际运行时能力不是一回事。
- 默认复用 request/error/转换与清理封装。异常与拒绝保留失败语义；取消向真实支持 `AbortSignal` 的调用传播，晚到结果仍需隔离。库资源按 API 所有权关闭。

检查 null/undefined/零、重复键、运行时输入、取消/晚返回与目标环境。精确 API 按锁定版本和官方文档核验，不能以本机 Node 版本代替部署版本。
