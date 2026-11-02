# Go 证据适配

以 module/workspace、`cmd` 和构建 target 识别单元；从 `main`、Cobra/flag 命令、HTTP/gRPC handler、导出 API、消费者与 worker 发现入口。核对接口绑定、JSON/Protobuf 类型、error 传播、context 取消、goroutine/channel/锁、事务、`defer`、文件/网络资源、配置和测试。

接口实现候选必须结合构造、注入与调用位置确认；启动 goroutine 不证明它在进程退出、取消或失败时得到回收。
