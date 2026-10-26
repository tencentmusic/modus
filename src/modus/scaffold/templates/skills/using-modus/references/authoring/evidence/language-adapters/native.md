<!--
本页只适配取证方法，领域身份、稳定路径与正文职责由共享框架维护。
-->

# C / C++ / Objective-C / Swift 证据适配

## 构建边界先于目录与语言

以 CMake/Make/Bazel target、Xcode target/configuration、CocoaPods subspec、SwiftPM target、公开 header、链接边界和 build variant 识别单元。核对 `compile_commands.json`、`project.pbxproj`、`xcconfig`、`Podfile`/`podspec`、`Package.swift`、module map、bridging header 与条件编译；它们是取证输入，不授权自动执行构建、下载依赖或运行配置脚本。`LocalPods`、`legacy` 不自动等于第三方或无效代码；生成绑定与依赖实现单独标记来源，不与手写业务重复计数。

`.h` 可能包含 C、C++、Objective-C 或混合声明，不能只按后缀判断；`.mm` 必须同时核验 OC 消息与 C++ 对象调用。结构解析不具备预处理器、SDK、链接器和完整类型系统的上下文，恢复出的局部语法不能宣称编译成功。

## C / C++

从 executable、export、命令、callback、event loop 与 plugin ABI 调查。核对 namespace、声明与定义、重载/模板、结构体/序列化、指针与 ownership、RAII/析构、错误码/异常、线程/锁、句柄释放、编译宏、配置和测试。宏、函数指针、条件编译和动态链接必须标明证据强度；header 声明不证明符号在当前产物中导出或 ABI 兼容。

## Objective-C / Objective-C++

沿 `@interface`、class extension、具名 category、`@implementation`、protocol 与实际创建点核验类型职责；同名声明/实现不是多个业务模块，category 也不是独立宿主类。保留完整 selector、`+`/`-` 方法种类、属性 ownership/nullability、block 类型与源码位置。`@selector`、target/action、delegate、notification、KVO、swizzling 和 `NSClassFromString` 是间接关联，只有注册与触发证据闭合后才描述调用链，不把 selector 字符串当成调用成功。

核对 ARC 与 C++ RAII 的交界、weak/strong 捕获、回调解绑、UIView/控制器生命周期、主线程更新和失败回调。`.mm` 中的 `shared_ptr`、lambda、`std::move` 与 OC block 分别分析，不因语法树能恢复一侧便声称整个混编文件完整。

## Swift

沿 class/struct/enum/actor/protocol、extension、initializer、带参数标签的方法和属性核验职责；extension 的目标与 `where` 约束要回到宿主类型，重载不能仅按函数名合并。核对访问级别、`@objc`、property wrapper 及 `$property` 投影、`@MainActor`、`async`/`await`、Task 取消、weak capture、错误传播和 optional；`async` 不自动表示后台线程，返回 Task 不表示操作完成。

`import` 表示模块，不等于同名 `.swift` 文件。Swift/OC generated header、bridging header、C++ interop 和生成胶水是跨语言证据；名称相似、大小写转换或同一目录不能证明精确绑定。

## 跨端契约与状态链

对 IDL 驱动的 C++ / iOS / Kotlin 工程，沿「端侧事件 → ViewModel Action → BizModel → Service → State/Event → 端侧订阅」追踪同一场景。核对 `.idl.hpp` 的 Namespace、Action/Arguments、States、导出平台与生成来源，再核对生成绑定、注册宏、手写 handler 和消费方；宏 DSL 不能直接当作普通 C++ 类型模型。端侧路由、权限、上传、保存、分享、生命周期与订阅通常仍有业务决策，不能归入“纯 UI”后省略。

逐个区分派发、受理、异步完成和最终用户可见结果；记录状态所有者、线程、订阅/解绑、参数转换、取消/失败与测试证据。多语言实现围绕一个业务主线写入同一 Module，平台差异在有证据的位置说明，不机械复制三份手册。未解析桥接保留缺口，不按名称猜测调用边。
