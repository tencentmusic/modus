# N1–N2：源码基线、观察与语言扩展

## 生命周期与源码地图

`machine/api.py: analyze_repository → pipeline.py: build_pipeline` 在单个项目锁内执行六阶段；workspace 外层不能作为一个源码仓库分析，应按已确认成员分析。管线持有资源策略与观察计时，不复制语义算法。

| 责任 | 源码 |
| --- | --- |
| N1 冻结/封存 | `machine/corpus/lifecycle.py`、`contracts.py`、`input_snapshot.py` |
| 文件发现、过滤、来源角色 | corpus 的 `scan.py`、`source_filters.py`、`source_inventory.py`、`source_roles.py` |
| 冻结文件坐标 | `source_snapshot.py`、`source_coordinates.py` |
| N2 调度 | `facts/lifecycle.py: observe`、`extension_registry.py`、`languages.py`、`language-registry.json` |
| 结构提取/绑定 | `facts/structural.py`、`native_parser.py`、`native_syntax.py`、`native_visitor.py`、`native_binding.py` |
| 框架/公开入口 | `entry_observation.py`、`entry_contracts.py`、`framework_facts.py`、`frontend*.py`、`source_contracts.py` |
| 规则/源码值 | `rule_signals.py`、`source_evidence.py`、`value_summary.py`、`generic.py` |
| 构建单元 | `build_context.py`、`build_contracts.py`、`build_support.py`、`build_resolvers/` |
| 编译语义 | `semantic_providers.py`、`semantic_ir.py`、`semantic_contracts.py`、`compiler/`、`provider_assets/` |
| 缓存身份 | `facts/extraction_cache.py`、`compiler/cache.py`、`machine/implementation.py`、`store/fingerprint.py` |

## 输入与身份

N1 一次捕获字节，分类 included/excluded/unsupported/oversized/unavailable，记录输入与上下文，不解释语法。corpusDigest 绑定路径/角色/内容，analysisContextDigest 绑定分析配置与外部输入，baselineDigest 组合二者与契约版本。N2 使用本轮冻结输入，封存编译输入闭包；发布前漂移必须阻止错误包生效。

N2 的生产者为 StructuralExtractor、CompilerProvider、EntryDetector、BoundaryResolver。注册不可变且名称/版本明确；开始观察前拒绝重复、未知实现和声明不一致。N2 输出事实与各提供方覆盖，不决定最终业务领域。

机器状态为五个独立轴，见 `states.py`：选择结果、执行状态、完整度、解析度、产物生命周期。不能用 analyzed/reused 表示语义完整，聚合通过 floor 保持最弱证据精度。

## 语言能力和工具边界

编译提供方当前为 Python、Java、Go、C++、TypeScript；结构能力与通用文本后缀更广。Kotlin、Swift、Objective-C/Objective-C++ 有专用结构访问器，C++ 补充命名空间、原型和模板调用；头文件按语法分流，移动端绑定仍保留 candidate/partial 边界。语言证据适配指南存在，不等于该语言拥有精确 compiler provider。实际 tier 由 `capability_for`/注册表和工具链共同决定。

compiler mode：`off` 不探测工具；`auto` 局部不可用返回覆盖/诊断；`required` 在必需语义失败后阻止发布。缺失工具不能被记录为能力不存在。一个构建单元的来源/上下文参与缓存，闭包不完整可禁止复用。

Java/Go 随包分析器分别在 `provider_assets/ModusJavaAnalyzer.java`、`modus_go_analyzer.go`；TypeScript 在 `modus_typescript_analyzer.cjs`。它们经共享 JSONL/IR 边界交付。Go 使用离线、local 工具链与只读模块模式；TS 使用已有本地 compiler API，禁止 emit/plugins，不自动安装；C++ 编译数据库只分词/过滤为 argv，不能交 shell。受限进程在 `compiler/process.py` 控制环境、输出、超时和进程清理。

## 修改与验证

增加语言/框架观察须一起维护声明、注册、具名版本、能力坐标、构建单元和夹具。移动访问器/语法契约也可能改变解析指纹；不能让旧缓存继续命中。原始 AST、无类型解析字典止于观察边界，公开 IR 保留来源、坐标、解析强度与覆盖。

测试：`test_analysis_pipeline.py`、`machine/test_contracts.py`、`test_language_fixtures.py`、`test_extraction_cache_identity.py`、`test_corpus.py`、`test_architecture.py`、`test_states.py`。至少证明发现、类型/入口、源输入变化、声明/实现不一致、缺工具局部降级、required 拒绝及实现变化失效。
