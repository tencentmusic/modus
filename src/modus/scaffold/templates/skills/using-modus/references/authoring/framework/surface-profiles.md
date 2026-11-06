<!--
运行形态是表达的适配轴，稳定路径和领域身份由其他契约拥有。
-->

# 运行形态画像

Surface 描述真实运行入口，是正文适配轴，不是目录模板。Module 可以命中多个画像；合并关注点，不拼接标题，也不重复章节。未知运行面使用 `generic`，不得默认套用 backend。

| Surface | 正文重点 | 优先图形 |
| --- | --- | --- |
| `backend` | 协议入口、鉴权、事务、权威写入、消息、受理与最终完成 | 时序图、状态图、资源关系图 |
| `frontend` | 用户动作、页面/路由、store、请求、渲染和错误反馈 | 交互流程、浏览器—服务时序、UI 状态图 |
| `cli` | 命令、参数优先级、stdin/stdout、文件/进程副作用、退出与清理 | 命令流程、文件时序、清理生命周期 |
| `library` | public API、调用方责任、资源所有权、异常、兼容和扩展点 | 调用时序、资源生命周期、对象关系 |
| `worker` | 调度/消费、并发、检查点、提交、部分成功、重试和停止 | 消费时序、任务状态、重试流程 |
| `data` | source/transform/sink、分区、水位、质量、发布和重放 | 数据血缘、作业时序、checkpoint 状态 |
| `infrastructure` | provider、state、依赖、漂移、回滚、销毁和秘密 | 依赖图、plan/apply/destroy 流程、状态图 |
| `plugin` | 宿主发现、注册、能力协商、隔离、错误传播和卸载 | 宿主时序、插件生命周期、协商流程 |
| `generic` | 只表达已核实的中性入口、状态、协作和资源 | 由事实决定 |

规范选择可复用这些候选，但有自己的适用条件；mobile/android/ios、desktop、SSR 等更细运行边界按[工程类型](../../../../modus-init/references/constraint-profiles/engineering-types.md)记录在原卡和规则范围，不因缺少机器 Surface 值强套 backend。

Surface 不能改变稳定目录或完成定义。语言适配只改变取证方法；正文自然语言只改变表达。三者始终正交。
