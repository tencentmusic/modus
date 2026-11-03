# 前后端主流栈约束调查

本页保留跨框架取证。语言分别从 [JavaScript](javascript.md) 或 [TypeScript](typescript.md) 进入，再选[工程类型](engineering-types.md)与专项；[React](adapters/react.md)维护编码差异。浏览器、SSR、Node 与各类 Worker 分别选择，不以 Web 总类覆盖全仓。

以下是取证维度，不是 Team Standard 的固定 H2 模板；最终章节按项目真实机制组织。

先读[共享方法](../constraint-extraction.md)。以 package.json、唯一实际使用的锁文件、workspace、框架配置和启动入口确认版本及运行边界。按项目组合 React/Vue/Angular/Svelte、Next/Nuxt 与 Express/Nest；其他栈沿用共同调查方法。框架支持某能力不证明项目启用它。

## 1. 架构/分层/链路事实

- **证据入口与追查**：monorepo packages、tsconfig paths/references、bundler、页面与 router、组件/状态目录、API client、BFF/server 入口、后台 Job；从用户事件追 state/action → 请求构造 → 服务端鉴权/处理 → 写入 → 响应/缓存更新与页面反馈。区分浏览器、SSR、server function、Node 服务及后台 worker。
- **可沉淀与误判**：页面/组件/状态/服务职责、可共享包和改动归属、前后端契约与异步受理/完成链路。import alias 不证明业务层级或包隔离，组件目录不证明独立业务模块；前端成功提示不证明后端业务已经完成。

## 2. 架构约束

- **证据入口与追查**：包 exports、lint import restriction、路由/API/IDL、类型生成源、后端 guard/middleware/policy、serializer；核对服务端鉴权实际覆盖的每个入口以及客户端直接调用/server action/BFF 旁路。检查 server-only/client 边界、浏览器可见 env、打包导入链、用户/租户状态在 SSR 的创建与隔离。
- **可沉淀与误判**：敏感逻辑与密钥留存位置、公共契约与生成客户端的修改入口、可信身份和依赖方向。TypeScript 类型不等于运行时校验，route guard/按钮隐藏不等于服务端授权；目录或文件标记也需结合框架版本与实际 import/执行语义。不能把类型共享当作运行依赖允许互通。

## 3. 服务治理

- **证据入口与追查**：fetch/Axios 或统一 request wrapper、拦截器、AbortController/订阅清理、重试/refresh-token、错误边界与后端 exception filter；查请求并发、旧响应覆盖新状态、切页/卸载后的回调，客户端与 BFF/SDK 的重试叠加。核对限流、trace/request ID、监控注册、健康检查、优雅停机与部署灰度配置。
- **可沉淀与误判**：默认请求入口、身份传递、取消/竞态、错误展示、登录失效与可重试操作的范围。请求取消不证明服务端撤销写入，loading/error UI 不等于系统降级；重试写接口需要回查幂等机制，不把库默认重试次数当成项目规范。

## 4. 中间件知识

- **证据入口与追查**：TanStack Query/SWR/Apollo、Redux/Pinia/NgRx/store、框架数据缓存、HTTP/CDN 缓存、BFF Redis/ORM/队列、对象上传与配置；核对 query key、用户/租户区分、失效触发、stale 时间、乐观更新失败回滚、持久化/退出清理、服务端缓存和浏览器缓存的责任。
- **可沉淀与误判**：本项目的数据来源、缓存键与隔离、写后刷新、重放/去重和上传权限约定；模块专属 key/失效事件进入模块规则，公共 client/cache wrapper 进入项目标准。状态库只是容器，不能据依赖推断一致性策略；SSR 单例状态、持久化 token 和公共 CDN 缓存都需追到实际边界再写结论。

## 5. 代码规范约束

- **证据入口与追查**：组件公共 API、hooks/composables/service/store、表单 schema、共享 UI/tokens、类型/错误映射、eslint/prettier/tsconfig、Vitest/Jest/Testing Library/Playwright/Cypress；追副作用依赖与清理、表单值到请求的转换、nullable/日期/金额/枚举、授权失败与重复操作反馈。
- **可沉淀与误判**：项目实际的状态责任层、组件组合与复用、API 类型和校验、错误交互、可访问性/国际化及测试约定。只在源码/检查/设计系统有证据时形成团队规则；不强迫所有 React 项目采用相同状态库，不把历史 any/硬编码颜色当作推荐。

## 6. 工程规范

- **证据入口与追查**：Node engines/packageManager、锁文件、workspace 构建顺序、scripts、tsconfig project references、bundler/env exposure、codegen、CI 的 lint/typecheck/test/e2e/build、Docker/SSR/静态部署、迁移和 release 配置。核对构建时与运行时 env、公开变量前缀、server/client 包产物、契约生成器和测试环境。
- **可沉淀与误判**：实际包管理器、启动/验证命令、类型/客户端生成流程、包边界检查、配置生效和部署兼容条件；已有体积预算或浏览器矩阵有证据才写。tsc 通过不等于运行时契约正确，静态构建通过不证明 SSR/服务端已部署，禁止把 scripts 名称当作执行结果。

## 按框架定位证据

| 栈 | 定向追查 | 需要形成的项目结论 |
| --- | --- | --- |
| React / Next | hooks 与 effect 清理、Context/store 创建、router、Server/Client Component 的 import 边界、server action/route handler、版本对应的 fetch/cache/revalidate 设置 | 副作用与请求责任层、服务端校验位置、敏感依赖边界和缓存失效范围；不假定不同 Next 版本默认缓存相同 |
| Vue / Nuxt | router、props/emits、composable/watch 清理、Pinia 创建、useFetch/useAsyncData、server routes、runtimeConfig、SSR 插件状态 | 页面与 store 职责、请求取消/隔离、public/private 配置和用户状态清理；服务端每次请求状态与客户端单例分开 |
| Angular | standalone/NgModule、providers 及注入范围、router guard、HttpClient interceptor、RxJS subscription/switchMap、signals/NgRx、SSR bootstrap | 服务实例范围、异步清理、错误/身份拦截顺序与真正后端鉴权；声明 guard 不证明后端限制 |
| Svelte / SvelteKit | store/context、版本相关响应式写法、load/+page.server/+server/actions、hooks、私有/公开 env、invalidate | SSR/客户端状态归属、server load/action 权限与数据暴露、写后失效和失败反馈；共享模块变量需检查跨请求影响 |
| Express | app/router 注册顺序、认证/解析/错误中间件、async handler 与版本、service/repository/client 工厂、进程退出钩子 | 中间件是否实际挂载、错误传播、请求上下文及外部依赖封装；定义但未注册的中间件不算生效 |
| Nest | modules imports/exports、provider token/scope、controller/resolver/微服务 handler、guard/pipe/interceptor/filter 的全局或局部注册 | DI 边界、校验/鉴权顺序、不同协议入口的覆盖、请求单例状态及统一异常机制；HTTP 全局配置不能推断到所有 transport |

## 组合查证示例

若订单列表通过统一 client 和租户化 query key 查询，提交后只失效该租户列表：把公共 client 约定写项目标准、身份隔离写域规则、提交后失效顺序写模块规则。再查切换租户、重复提交、旧请求晚返回、SSR 并发和后端权限的证据；未实现的取消或隔离不得补造。

机制核验参考：[Next Server/Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components)、[Vue SSR 与跨请求状态](https://vuejs.org/guide/scaling-up/ssr.html)。选择项目对应版本；外部文档只用于解释机制。
