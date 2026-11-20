<!--
发布验证在独立安装环境消费产物，不能依赖源码目录。
构建、内容审计与运行验收分别报告失败。
-->

# 发布验证工具

此目录验证一条边界：交付给用户的安装包包含预期架构，并在源码仓库不可用时仍能运行。

## 运行方式

- `./scripts/wheel-smoke.sh` 构建一个 wheel 和一个源码包，再验证两者，是 CI 与维护者的统一入口。
- `python scripts/package_smoke.py ARTIFACT...` 验证已有产物；每个 wheel 还会执行独立运行时验收。

设置 `MODUS_KEEP_SMOKE_ARTIFACTS=1` 可保留临时构建产物，`UV_BIN` 可指定 uv 可执行文件。验证脚本不会发布安装包。

## macOS 桌面发行包

桌面源码位于同一仓库的 `integrations/desktop/`。在装有 Node.js 22.12 或更新的 22.x 版本、npm、稳定版 Rust 工具链、Xcode 命令行工具与 uv 的 Apple Silicon Mac 上，从 Modus 仓库根目录运行：

```bash
bash scripts/build-macos-wheel.sh
```

脚本按锁文件安装前端和 Rust 依赖，生成 `integrations/desktop/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/modus-manager.app` 和 `dist/openmodus-*-py3-none-macosx_11_0_arm64.whl`。本地构建默认采用临时签名。正式分发时可设置构建所需的 Apple 签名和公证凭据，也可将处理完成的 `.app` 路径作为脚本参数。

发布时将桌面 wheel 与同版本通用 wheel 和源码包一起发布。兼容的 Mac 通过普通安装命令选中桌面 wheel。首次运行 `modus dashboard` 时直接使用随包应用。其他平台仍使用通用 Python 发行包。

## 模块责任

`package_smoke.py` 保持为稳定的薄适配器，实现在 `release_smoke/` 中：

| 模块 | 责任 |
| --- | --- |
| `contracts.py` | 架构见证文件、五个内置技能、元数据与排除项 |
| `diagnostics.py` | 确定性的维护者诊断 |
| `archive.py` | 拒绝不安全归档，规范化清单，防路径穿越解压 |
| `verification.py` | 应用发布策略，不耦合终端展示 |
| `runtime.py` | 隔离到解包后的 wheel，验证知识、分析、更新与卸载生命周期 |
| `cli.py` | 将契约失败转换为简明诊断和退出码 |

与打包无关的行为放入普通测试；这里增加的检查应保护产物边界或安装后才暴露的失败。

安装后分析验收包含 Kotlin、Swift、Objective-C/Objective-C++ 和 C++ 的真实语法输入，检查访问器与语法依赖已进入可运行产物，避免缺包后静默退回通用文本。具体结构与保守绑定由语言回归测试覆盖。
