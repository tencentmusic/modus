# React 适配差异

适用已确认 React 渲染路径；版本、客户端/SSR/Server Component 边界各自核实。联读 JS/TS、frontend 与所用 HTTP/缓存专项。默认复用项目 hooks、组件、请求与状态缓存；不因一个请求另建状态框架。

Effect 用于与外部系统同步，纯派生值优先直接计算。需要异步 Effect 时 setup 同步返回 cleanup，在内部启动任务；依赖如实声明，cleanup 清理订阅/请求并隔离旧结果，不能用关闭 lint 的方式隐藏依赖。共享 SSR 状态需要按请求创建，服务端密钥不随 import 进入客户端。

核对已有 query client 是否负责取消、失效和竞态，避免重复实现。验证快速切换输入、卸载、失败、重复 setup/cleanup 和 SSR 用户隔离。[useEffect 文档](https://react.dev/reference/react/useEffect)解释生命周期；框架数据请求与缓存能力按实际版本补差异，不把最新文档默认带入旧项目。
