# 独立编码任务：共享标识、浏览器查询与 Node 任务

`ports.ts` 是已有包：共享 normalizeIds、LookupClient、WorkerPorts；支持 TypeScript 5.6 / ES2020、浏览器与 Node 20。实现两个入口：浏览器 createLookup 在快速切换请求时只发布最后一次结果，复用 client 并传取消信号，停止后不更新状态，失败不能空成功；Node reserve 取得一次配置快照，调用现有有界 mapWindow 和条件更新，不自己引入 Promise 池/数据库依赖。非法 ID/配置在副作用前拒绝，重复 ID 保序处理。

选择 foundation + javascript/typescript；浏览器选 frontend/http，Node 选 worker/concurrency/configuration/database。共享 ports 只接受 ES2020 能力，不引用 DOM/Node 全局。依赖库存曾列 React，但输入没有 React 渲染/装配，排除 React 适配器。浏览器有 DOM 类型不授权 Node/共享代码使用 document；types 不提供 runtime polyfill。

`solution/` 是依据这些约束给出的代码，`checks.cjs` 检查独立输入的行为，分环境 tsc 检查依赖边界。它不证明真实 HTTP/数据库集成或 React 生命周期。
