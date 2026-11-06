# Modus × DeepSeek Harness

**让项目知识参与每一次代码任务。** DSH 执行任务；Modus 提供项目理解、业务约束、当前源码证据，以及变更后的知识维护流程。同仓的 `modus/knowledge/` 继续由不同 Coding Agent 共享。

集成包含两部分：Python 平台适配器把五个工作流投影到项目，独立 npm 插件为 DSH 注册四个只读工具。知识按需读取，维护沿用读取时哈希保护的写入协议。

**DSH 插件包：`@modus-ai/modus@1.0.0`。** npm 插件与 Python CLI 分别安装，版本独立管理。

[集成设计](architecture.md) · [贡献与验证](architecture.md#贡献与验证)

## 你会得到什么

| 工具 | 用途 | 可交付报告的退出码 |
| --- | --- | --- |
| `modus_status` | 检查项目接入、知识状态与更新情况 | `0` |
| `modus_context` | 按任务检索 Markdown、业务约束和当前源码，保留来源与证据缺口 | `0` |
| `modus_knowledge_impact` | 根据本任务实际修改检查受影响知识与锚点，返回候选 | `0`、`1` |
| `modus_verify_knowledge` | 核验结构、链接与源码锚点，可选择发布核验 | `0`、`4` |

一次任务的路径是：**读取证据 → DSH 实现与测试 → 评审知识影响 → 按需修订 → 回读与核验**。文件变动只提供线索；确认职责、规则、契约、状态或锚点变化后，才由共享 Skill 修订已有主定义。

## 兼容范围

| 组件 | 要求与验证范围 |
| --- | --- |
| DeepSeek Harness | `0.2.1-rc.3`、`0.2.2-alpha.2`；其他版本需先验证宿主接口与 peer 约束 |
| Node.js | `>=22.19.0`；开发与 CI 使用 Node.js 24 |
| Python | `>=3.11`；源码安装使用 uv |
| Modus CLI | 包含 DSH adapter 的本仓库源码；工具协议范围为 `openmodus >=0.0.5,<0.1.0` |
| DSH profile | 提供 `tools`、`systemPrompt`、Bash `shell`、`shellEnv` 与 `workingDirectory` |

工具执行跟随 DSH 会话的目录、环境、取消信号和沙箱策略。远程执行时，CLI 必须安装在远程执行环境；远程后端、PowerShell 专用执行器和其他 DSH 版本仍需单独验证。

## 安装

完整接入需要 **CLI、项目 Skills、profile 插件** 三部分。先使用一个样例项目验证，之后可将相同配置用于业务仓库。

### 1. 安装 CLI 并接入项目

在包含 DSH 集成的 Modus checkout 根目录执行：

```bash
uv sync --locked
.venv/bin/modus --version
.venv/bin/modus -C /absolute/path/to/your-project init --platform dsh
.venv/bin/modus -C /absolute/path/to/your-project status --json
```

记录该 checkout 中 `.venv/bin/modus` 的绝对路径，后续作为 `executable`。仅凭已安装 CLI 的版本号，不能判断它是否包含 DSH adapter。

已有多个平台的项目需在 `init` 中列出全部要保留的平台，例如 `--platform codex --platform dsh`。安装会写入 `.dsh/skills/` 和 `AGENTS.md` 中的 `modus-dsh` 区块，保留已有知识。知识正文由用户在 DSH 中明确调用 `/modus-init` 后创作。

### 2. 获取插件

npm 安装使用 `@modus-ai/modus@1.0.0`，无需构建。下节给出对应的 DSH 安装命令。

需要从源码构建或离线安装时，在 checkout 中执行：

```bash
cd integrations/dsh
npm ci --ignore-scripts
npm test
npm pack
```

产物为本目录的 `modus-ai-modus-1.0.0.tgz`。已有维护者提供的 Release tarball 时，可跳过构建。包内含预构建入口，安装不需要编译 TypeScript。

这是 monorepo 子目录包，支持 npm 与 tarball 分发；仓库根目录不能用于 `dsh plugin add github:tencentmusic/modus`。

### 3. 选择一个 DSH profile

**桌面应用（macOS）**：首次打开应用完成登录，完全退出后，使用应用自带的 CLI 安装：

```bash
DSH_CLI="/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"
"$DSH_CLI" plugin --profile desktop add @modus-ai/modus@1.0.0 --ignore-scripts
```

将下节配置合并到 `~/.dsh/profiles/desktop/cordis.patch.yml`，重新打开应用。插件页面应显示 `@modus-ai/modus` 已启用、组件运行中；添加目标项目为工作区即可使用。桌面 profile 由应用管理，不能用 `dsh --profile desktop` 启动。

离线安装时，将 `@modus-ai/modus@1.0.0` 替换为 `/absolute/path/to/modus-ai-modus-1.0.0.tgz`。

**独立 Web profile**：首次创建名为 `modus` 的 profile：

```bash
dsh modus --from-default-profile web --help
dsh plugin --profile modus add @modus-ai/modus@1.0.0 --ignore-scripts
dsh --profile modus --dump-config
```

`--from-default-profile` 会创建或重置 profile，仅用于首次创建；已有 profile 直接执行 `plugin add`。将配置合并到 `~/.dsh/profiles/modus/cordis.patch.yml`，从目标项目目录运行 `dsh --profile modus`，按 DSH 流程配置登录与模型。自定义 `DSH_HOME` 时，配置路径随之改变。

## 配置

profile 的 `cordis.patch.yml` 是 YAML 列表。按 `id` 更新本插件条目并保留其他条目；后续配置层会替换整行 `config`，因此需保留本插件仍要使用的配置项。

```yaml
- id: modus-project-knowledge
  name: '@modus-ai/modus'
  config:
    executable: /absolute/path/to/modus/.venv/bin/modus
    timeoutMs: 60000
    maxOutputBytes: 2097152
```

| 配置 | 默认值 | 约束 |
| --- | --- | --- |
| `executable` | `modus` | 程序名或 Bash 绝对路径；不能使用相对路径或 `uv run ...` 命令片段 |
| `timeoutMs` | `60000` | 每个 CLI 进程的超时，整数 `100–300000` 毫秒 |
| `maxOutputBytes` | `2097152` | 每个 CLI 进程的 stdout 上限，整数 `1024–16777216` 字节 |

每次工具调用先在当前执行环境检查 CLI 版本，再执行业务命令。运行时指引也绑定同一可执行文件，使 Skill 的知识写入与工具检索使用同一 CLI。

## 验证安装与日常使用

在目标项目的 DSH 会话中发送：

> 调用 modus_status，然后加载 using-modus，使用 modus_context 查询这个项目的主要职责、业务约束和相关源码。列出证据与缺口。

应能看到四个工具，状态与检索结果应指向目标项目。只有初始文件的项目，需要用户明确发送 `/modus-init` 创作正文。

各工具的 `root` 默认为当前会话目录；从子目录或多仓工作区调用时，显式传入对应 Modus 根目录。`paths` 和 `changedFiles` 相对该根，插件不向父目录猜测另一个项目。

代码任务收尾时，使用本任务实际修改的路径调用 `modus_knowledge_impact`。`validation` 必填：未验证或验证失败使用 `failed`。确认长期语义变化后加载 `modus-sync-knowledge`，通过原有 CAS 工作流修订并核验；明确要求专项维护时使用 `/modus-update-knowledge`。初始化与重建仍要求用户明确调用。

工具返回 `{ "exitCode": 0, "result": { ... } }`。影响检查的退出码 `1`、核验的退出码 `4` 会与完整报告一同保留，需同时阅读报告与退出码。取消、超时、沙箱失败、截断或非法 JSON 会使工具失败。核验 `clean` 只证明检查覆盖的结构与锚点，不能代替事实回读和代码测试。

## 更新与卸载

以下 `modus` 使用配置中的同一个 CLI；源码安装时替换为其绝对路径。

`modus update` 更新 CLI 与项目受管资产；`modus update --project` 仅使用当前 CLI 更新受管 Skills，并保留用户编辑。profile 中的 npm 插件由 DSH 独立管理。原生工具尚未声明共享 Skill 所需参数时，通过宿主 Shell 使用配置中的同一 CLI 执行对应命令，无需为继续任务先升级插件。

`modus uninstall --project` 按卸载计划移除受管投影和指引区块，保留用户自建 Skill、DSH profile 与长期知识。原生插件独立移除：

```bash
dsh plugin --profile modus remove @modus-ai/modus
```

桌面应用先完全退出，再用安装时的 `DSH_CLI` 执行 `plugin --profile desktop remove @modus-ai/modus`，最后重启。确认不再使用时，可移除 profile 中本插件专属配置。Cordis 会释放插件注册的工具与上下文。

## 排障

| 现象 | 处理 |
| --- | --- |
| 找不到 CLI，或检索与维护使用不同版本 | 把 `executable` 设为包含 DSH 集成的 `.venv/bin/modus` 绝对路径 |
| 插件运行中但找不到知识 | 检查会话目录与 `root`，确认已接入项目并存在知识正文 |
| DSH 版本不兼容 | 使用兼容表中的版本；扩大支持范围前先验证接口与 peer 约束 |
| 配置未生效 | 检查后续配置层是否覆盖；桌面应用完全退出后重启 |
| 本地重装后仍是旧插件 | 新构建使用新版本号；调试时可先移除再安装，pnpm 可能复用同版本缓存 |
| 写入冲突或核验不是 `clean` | 回读冲突文件和 findings，重新评审后使用新的读时摘要；不要覆盖并发修改 |
| DSH 改动卡未列出知识文件 | Shell CLI 写入可能不进入 edit/write 卡，以 CAS 报告、文件差异和核验结果确认 |

开发者可从 [集成设计](architecture.md) 了解模块职责、执行边界和扩展方式；本地构建包与 npm 已发布包的独立验证入口见 [贡献与验证](architecture.md#贡献与验证)。
