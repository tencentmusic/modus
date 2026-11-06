# 平台适配与常驻指引

## 布局与主定义

入口：`src/modus/platforms/registry.py: BUILTIN_REGISTRY`。中立模型为 `platforms/models.py` 的 Skill、Command、PlatformLayout；生命周期由 `PlatformAdapter` 实现，具体适配器声明布局和局部渲染差异。

| 平台 | 技能位置 | 指令/规则 |
| --- | --- | --- |
| Claude | `.claude/skills` | `CLAUDE.md` 的 `modus-claude` 区块 |
| Codex | `.agents/skills` | `AGENTS.md` 的共享 `modus` 区块 |
| Cursor | `.cursor/skills` | `.cursor/rules/modus.mdc` |
| CodeBuddy | `.codebuddy/skills`，另有 `.codebuddy/commands` | `CODEBUDDY.md` 的 `modus-codebuddy` 区块 |
| DSH | `.dsh/skills` | `AGENTS.md` 的共享 `modus` 区块；原生插件提供运行时指引与工具 |

`.modus/skills` 是接入项目的中立权威源，宿主目录是投影副本。扩展不要让模板硬编码宿主路径或通过目录扫描隐式新增用户工作流。

Codex 与 DSH 通过 `platforms/rendering.py: render_agents_instructions` 渲染同一份 `AGENTS.md` 指引。安装清单按 `(path, marker)` 记录一份区块；平台增减仍保留这份指引，直到最后一个使用它的平台移除。适配器卸载同时更新清单的平台列表，完整卸载的预览按相同顺序计算共享区块的删除归属。

Claude 与 DSH 的 model-invocable/user-invocable 两轴独立：自动能力 model-only，显式 init/reinit user-only，update-knowledge 支持二者。两者通过 `platforms/rendering.py: render_invocation_metadata` 共享已验证的 frontmatter 转换，其他宿主由各自适配器决定权限投影。

共享权限渲染复用 `skillmd.split_frontmatter` 的有界 YAML 解析，保留已有顶层配置，并补充缺失的布尔权限字段。仅序列化头部，正文逐字保留；头部沿用 LF/CRLF 换行，已有完整权限时直接返回原文。中立模板和其他宿主副本不受此转换影响。

## 常驻指引与旧安装迁移

`activation_guidance.py: MODUS_ENTRY_HINT` 定义任务适用性、按需读取技能与知识影响检查点；`precedence.py` 和 `platforms/rendering.py` 将它写入各宿主常驻说明。新安装不生成会话启动 hook、启动器或会话环境变量。

`legacy_hooks.py` 仅供旧清单升级和卸载使用：识别命令中的 `.modus/hooks/run-hook.cmd`，保留同一事件或 matcher 内的外部命令、未知字段及用户配置。`commands/update.py` 将旧 hook 配置作为退役资产清理，启动脚本仍按旧清单摘要保护用户修改，仅删除空的 `.modus/hooks/` 目录。损坏配置保留并报告，修复后可重试；预览不写真实项目，升级失败按安装事务回滚。

共享文本区块在 `platforms/sections.py`。重复/缺失 marker、陌生条目都需保留用户内容并形成可解释结果。

## 扩展/验证

新增平台一起更新平台注册、展示词汇、布局、调用权限及发布平台集合；不要改变全局可变注册表。检查 `paths.py` 输出排除规则，防止源码分析把自己的宿主投影当项目事实。

测试：`test_platforms.py`、`test_legacy_hook_cleanup.py`、`test_install_safety.py`、`test_project_lifecycle.py`。覆盖布局路径约束、调用权限、常驻指引、新安装不写 hook、旧项目升级/卸载、共享命令保留、预览与失败回滚。

DSH 将项目投影与 profile 插件分开管理；插件通过宿主执行服务调用 Modus CLI。会话绑定、只读工具和失败语义见 [DSH 集成设计](../../../../integrations/dsh/architecture.md)。
