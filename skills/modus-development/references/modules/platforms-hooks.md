# 平台适配与启动钩子

## 布局与主定义

入口：`src/modus/platforms/registry.py: BUILTIN_REGISTRY`。中立模型为 `platforms/models.py` 的 Skill、Command、PlatformLayout；生命周期由 `PlatformAdapter` 实现，具体适配器声明布局和局部渲染差异。

| 平台 | 技能位置 | 指令/规则 | Hook 配置 |
| --- | --- | --- | --- |
| Claude | `.claude/skills` | `CLAUDE.md` 的 `modus-claude` 区块 | `.claude/settings.json` |
| Codex | `.agents/skills` | `AGENTS.md` 的 `modus-codex` 区块 | `.codex/hooks.json` |
| Cursor | `.cursor/skills` | `.cursor/rules/modus.mdc` | `.cursor/hooks.json` |
| CodeBuddy | `.codebuddy/skills`，另有 `.codebuddy/commands` | `CODEBUDDY.md` 的 `modus-codebuddy` 区块 | `.codebuddy/settings.json` |
| DSH | `.dsh/skills` | `AGENTS.md` 的 `modus-dsh` 区块 | 原生插件提供运行时指引与工具 |

`.modus/skills` 是接入项目的中立权威源，宿主目录是投影副本。扩展不要让模板硬编码宿主路径或通过目录扫描隐式新增用户工作流。

Claude 与 DSH 的 model-invocable/user-invocable 两轴独立：自动能力 model-only，显式 init/reinit user-only，update-knowledge 支持二者。两者通过 `platforms/rendering.py: render_invocation_metadata` 共享已验证的 frontmatter 转换，其他宿主由各自适配器决定权限投影。

共享权限渲染复用 `skillmd.split_frontmatter` 的有界 YAML 解析，保留已有顶层配置，并补充缺失的布尔权限字段。仅序列化头部，正文逐字保留；头部沿用 LF/CRLF 换行，已有完整权限时直接返回原文。中立模板和其他宿主副本不受此转换影响。

## Hook 路径

`hooks/bootstrap.py` 生成启动器与宿主配置；`hooks/contracts.py` 定义宿主输入/输出封套；`protocol.py` 处理不可信事件并限制字节、标识；`runtime.py` 组合解析/根校验/上下文/输出；`environment.py` 仅拥有 Claude 的最小环境绑定。

当前 `hooks/context.py: build_runtime_context` 返回稳定最小指引，不读取整个项目知识，不导入初始化分析。Hook 在宿主启动边界 fail-open：内部不可用返回空上下文，入口退出 0。这是此边界的明确责任，不能推广到安装、知识写入或分析发布失败。

Codex JSON 输出按 wire bytes 限制，包括 ASCII 转义；宿主的会话/持久环境通道不同。基于真实 host contract 判断能力，不能用 Claude 环境写入方式推断 Codex 后续进程可自动绑定。

共享 Hook 合并在 `platforms/hooks.py`，共享文本区块在 `platforms/sections.py`。损坏 JSON、重复/缺失 marker、陌生条目都需保留用户内容并形成可解释结果。

## 扩展/验证

新增平台一起更新平台注册、宿主合同、展示词汇、布局、启动器及发布平台集合；不要改变全局可变注册表。检查 `paths.py` 输出排除规则，防止源码分析把自己的宿主投影当项目事实。

测试：`test_platforms.py`、`test_hooks.py`、`test_install_safety.py`、`test_project_lifecycle.py`。覆盖布局路径约束、调用维度、共享条目保留、事件上限/错误、启动放行、输出封套、安装后的真实运行。宿主配置渲染正确不能替代实际宿主运行验证。

DSH 将项目投影与 profile 插件分开管理；插件通过宿主执行服务调用 Modus CLI。会话绑定、只读工具和失败语义见 [DSH 集成设计](../../../../integrations/dsh/architecture.md)。
