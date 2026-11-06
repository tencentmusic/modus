# 项目安装、维护与资产所有权

## 读源码的路径

`cli_commands/initialize.py → commands/init_project.py: run_init → scaffold/project.py: scaffold_project → platforms/base.py → manifest.py`。

升级走 `commands/update.py: run_update/reconcile_desired_manifest`；预览是 `preview_update`。卸载走 `commands/uninstall.py: plan_uninstall/apply_uninstall`。安全支撑为 `commands/install_state.py`、`git_hygiene.py`、`atomic_writes.py`、`artifacts_io.py`。

## 安装事务

1. 验证已有根、安装模式、平台、完整模板、清单版本与非受管冲突。
2. 在临时根构造 desired 资产，真实写入前检查目标路径、Git 忽略与索引，建立精确快照。
3. scaffold 写受管资产/用户种子，处理本地状态忽略，最后写 manifest。
4. 异常恢复计划目标、权限、目录形态与相关 Git 索引；恢复不完整报 `InitRollbackError`，不能声称已完整回滚。

`serialized_install` 使用临时位置中按项目根身份命名的重入锁。安装不在真实根增加锁文件作为提交前提。已有清单损坏不是全新安装；版本变化应走 update，同版本可安全重入。`validate_install_root` 要求已有、非文件系统根的目录；项目接入不要求目标目录必须是 Git 仓库。

## 所有权与合并

| 资产 | 机制 |
| --- | --- |
| 全文件受管资产 | Manifest 的 path/template/sha256；比较旧基线、当前内容、新模板 |
| 用户知识/种子 | 初次补缺，后续保留；不把用户手改重新哈希认领为可覆盖基线 |
| 共享文本 | marker 对应 ManagedSection；只合并 Modus 区块，坏/重复标记形成冲突 |
| 旧 Hook JSON | `legacy_hooks.py` 仅按命令签名清理旧清单条目，保留外部命令和字段；损坏配置保留并报告 |
| 本地分析缓存 | Git hygiene 排除，相关索引变更可精确恢复，不 stage 无关用户工作 |

更新先验证版本和新旧目标，再用安装事务包裹协调、配置修复与清单提交。用户编辑/碰撞可以返回 partial；操作中异常则尝试快照回滚。major/downgrade 的执行参数与现有授权规则独立于内容哈希保护。

卸载先生成不可变只读计划，执行时重新比较项目状态；变化后拒绝旧预览。默认保留长期知识，显式删除策略才纳入知识目录。共享文件只去掉自己区块/钩子，工作区卸载只影响外层，不能遍历成员。卸载不能套用安装事务的整批回滚承诺。

## 扩展与验证

新资产类型在 `scaffold/writer.py: AssetOwnership` 定义；新路径需进入预检/计划/快照与清单的正确所有权类别。新增宿主布局需一起验证 install/update/uninstall，见 [平台指南](platforms-hooks.md)。

测试入口：`test_project_lifecycle.py`、`test_install_safety.py`、`test_workspace_lifecycle.py`、`test_scaffold.py`。重点证明安装前无副作用、幂等、未知平台、未受管碰撞、用户编辑、损坏清单、路径链接、共享容器、失败恢复和暂存内容保护。
