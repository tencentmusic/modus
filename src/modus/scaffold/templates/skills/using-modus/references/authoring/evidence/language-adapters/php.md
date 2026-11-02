# PHP 证据适配

以 Composer package、autoload 和应用入口识别单元；从路由、Controller、命令、队列任务、public service 和 plugin hook 调查。核对容器绑定、array/DTO/model 序列化、事务、请求进程与常驻 worker 生命周期、queue ack、文件资源、配置和测试。

魔术方法、动态调用和框架约定必须由注册或真实调用证据确认；请求内状态不能直接外推到常驻 worker 的可变单例行为。
