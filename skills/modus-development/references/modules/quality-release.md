# 开发验证、CI 与发布产物

## 环境与真实源码 CLI

当前贡献指南覆盖 Python 3.11–3.14；requires-python 声明 >=3.11。从项目根按锁安装：

```bash
uv sync --locked --extra test
uv run --locked --extra test python -m modus --version
uv run --locked --extra test python -m modus --help
```

这些命令使用当前 checkout，避免误用 PATH 中其他安装版本。需要隔离项目环境时，可显式给 `UV_PROJECT_ENVIRONMENT` 一个任务临时目录，不替换用户 HOME/CODEX_HOME。

## 按契约选最小测试

| 改动 | 主要测试 |
| --- | --- |
| CLI 隔离/中文/真实命令 | `test_cli_boundaries.py`、`test_cli_localization.py`、`test_documented_cli.py` |
| 项目生命周期/用户文件保护 | `test_project_lifecycle.py`、`test_install_safety.py`、`test_scaffold.py` |
| 平台/Hook | `test_platforms.py`、`test_hooks.py`、安装安全测试 |
| 分析生命周期/包确定性/漂移 | `test_analysis_pipeline.py`、`test_evidence_selection.py` |
| 语义分层/状态/语言缓存 | `machine/test_architecture.py`、`test_states.py`、`test_contracts.py`、`test_language_fixtures.py`、`test_extraction_cache_identity.py`、`test_corpus.py` |
| 能力/投影/局部降级 | `machine/test_capability_composer.py`、`test_projection.py`、`test_lifecycle_degradation.py` |
| 有界交付/Schema/目录存储 | `machine/test_context_builder.py`、`test_public_contracts.py`、`test_store_validation.py`、`test_progress.py` |
| 检索/路径/回退 | `test_knowledge_retrieval.py`、`test_orchestrator.py` |
| CAS/人工知识/核验/敏感输出 | `test_knowledge_update.py`、`test_verify_knowledge.py`、`test_sensitive_literals.py` |
| 工作区隔离 | `test_workspace_lifecycle.py`、检索与项目生命周期测试 |
| 产物 | `test_release_smoke.py`、`scripts/wheel-smoke.sh` |

文件名如未写前缀，位于 `tests/`；machine 表中首个路径以 `tests/machine/` 为根，其余同组文件也在 machine。以当前 `tests/README.md` 和实际文件核对，文件移动后不要强跑旧路径。

行为测试验证成功、失败、恢复和用户数据保留；不把偶然措辞、文件长度、固定标题或函数拆分形状当质量。架构/语言回归可断言明确不变量和稳定协议。

## 完整检查

提交前遵循当前 CONTRIBUTING：

```bash
uv run --locked --extra test pytest -q
uv run --locked --extra test ruff check src tests scripts
uv run --locked --extra test ruff format --check src tests scripts
uv run --locked --extra test mypy
git diff --check
```

依赖改动同步 `pyproject.toml`/`uv.lock` 并审查约束。mypy strict frontier、fixtures 排除、pytest markers 等以 pyproject 为主，不维护第二套工具版本。

## 产物与发布边界

发布前 `./scripts/wheel-smoke.sh` 在临时目录重新构建一个 wheel 和源码包，再调用 package_smoke；已有产物可用 `python scripts/package_smoke.py ARTIFACT...`。该脚本验证，不发布。

`release_smoke/contracts.py` 声明架构见证、工作流与平台集合、元数据和排除项；archive 拒绝危险成员与路径穿越；verification 执行静态策略；runtime 在脱离源码路径的独立 wheel 环境验证知识、分析、更新、卸载。源码单测通过不能替代安装产物验收。

wheel 将 schemas 打包到 `modus/_bundled/schemas`；source 包保留源码、文档、模板、模式、测试、脚本和锁文件。`schema_resources.py` 统一读源码/安装资源；新增资源需检查两种分发形态。

CI 定义 Linux 3.11–3.14，以及 macOS/Windows 最低与最高版本；Linux 3.14 执行静态/类型/分发检查。本地结果只代表实际 OS、Python、可用工具链与运行命令，不等于矩阵已通过。

DSH 原生插件独立运行 Node.js 检查；源码入口、真实 CLI 测试与隔离安装要求见 [DSH 贡献与验证](../../../../integrations/dsh/architecture.md#贡献与验证)。Python 测试不能替代该插件的运行时验证。
