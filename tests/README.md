<!--
测试地图按可观察契约归类，文件拆分时同步主要验证入口。
跨平台和安装后行为由对应验收覆盖，本地单测不替代这些检查。
历史输入夹具保持原始内容，避免测试只与当前实现相互印证。
-->

# 测试地图

测试按贡献者能从产品识别的契约组织：安装、证据分析、知识、宿主接入与发布产物。每项契约有一个主要测试位置。

| 位置 | 保护的边界 |
| --- | --- |
| `test_cli_boundaries.py` | 终端隔离、分析依赖延迟加载、输入上限与运行错误 |
| `test_cli_localization.py` | 中文帮助、参数错误、交互、输出流及协议稳定性 |
| `test_project_lifecycle.py`、`test_install_safety.py`、`test_workspace_lifecycle.py` | 安装、五平台工作流升级、所有权、回滚、并发与工作区成员只读 |
| `test_analysis_pipeline.py`、`test_evidence_selection.py`、`machine/` | 公开分析生命周期、分层、模式、降级与存储 |
| `test_knowledge_retrieval.py`、`test_knowledge_update.py`、`test_verify_knowledge.py` | 检索边界、哈希条件写入与客观知识完整性 |
| `test_platforms.py`、`test_hooks.py`、`test_sensitive_literals.py` | 宿主扩展与安全输出 |
| `test_dsh.py`、[DSH 插件测试](../integrations/dsh/architecture.md#贡献与验证) | 项目投影与用户资产保护、宿主执行边界、CLI 报告与隔离分发 |
| `test_scaffold.py` | 随包模板目录 |
| `test_filesystem_portability.py` | 无 openat 时的读取与退役、软链/重解析点拒绝、替换冲突、Windows 编码与换行摘要 |
| `test_release_smoke.py`、`scripts/wheel-smoke.sh` | 拒绝损坏归档及真实产物验收 |

小型源码项目放在 `fixtures/`，共享构建与断言放在 `_support/`。

## 编写要求

1. 验证可观察行为或明确的架构不变量，不把偶然句式、已删除文件持续缺失或辅助函数形状当作契约。
2. 每个行为保留一组有决定性的断言；参数化的每项输入都应代表有意义的边界。
3. 文件系统状态使用 `tmp_path`，不依赖顺序、网络、墙钟时间或开发者个人目录。
4. 断言稳定错误码与协议字段；失败操作也要证明用户文件和已发布数据得到保护。
5. 夹具先保持局部，只有多模块共享时才抽取；不要用通用辅助函数隐藏产品工作流。
6. 语言回归检查用户看见的中文语义，同时验证原命令、JSON 键与状态码未被翻译。

完整验证：

```text
uv run --locked --extra test ruff check src tests scripts
uv run --locked --extra test ruff format --check src tests scripts
uv run --locked --extra test mypy
uv run --locked --extra test pytest -q
./scripts/wheel-smoke.sh
```
