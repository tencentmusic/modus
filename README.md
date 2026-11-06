<div align="center">

# Modus

**让 Coding 不止于 Code**

已安装？运行 `modus update`。

<p>
  <strong>Coding Agent 平台</strong><br />
  <img src="https://img.shields.io/badge/Claude_Code-Supported-D97757" alt="Claude Code Agent Skills" />
  <img src="https://img.shields.io/badge/Codex-Supported-111111" alt="Codex Agent Skills" />
  <img src="https://img.shields.io/badge/Cursor-Supported-111111" alt="Cursor Skills and Rules" />
  <img src="https://img.shields.io/badge/CodeBuddy-Supported-1F6FEB" alt="CodeBuddy Skills and Commands" />
</p>

<p>
  <strong>语言能力 · 编译器 / 类型系统增强</strong><br />
  <img src="https://img.shields.io/badge/Python-semantic-3776AB?logo=python&logoColor=white" alt="Python semantic provider" />
  <img src="https://img.shields.io/badge/Java-semantic-ED8B00?logo=openjdk&logoColor=white" alt="Java semantic provider" />
  <img src="https://img.shields.io/badge/Go-semantic-00ADD8?logo=go&logoColor=white" alt="Go semantic provider" />
  <img src="https://img.shields.io/badge/C%2FC%2B%2B-semantic-00599C?logo=cplusplus&logoColor=white" alt="C and C++ semantic provider" />
  <img src="https://img.shields.io/badge/TypeScript-semantic-3178C6?logo=typescript&logoColor=white" alt="TypeScript semantic provider" />
</p>

<p>
  <strong>语言能力 · 专用结构解析</strong><br />
  <img src="https://img.shields.io/badge/JavaScript-structure-F7DF1E?logo=javascript&logoColor=111111" alt="JavaScript structural parsing" />
  <img src="https://img.shields.io/badge/Kotlin-structure-7F52FF?logo=kotlin&logoColor=white" alt="Kotlin structural parsing" />
  <img src="https://img.shields.io/badge/Swift-structure-F05138?logo=swift&logoColor=white" alt="Swift structural parsing" />
  <img src="https://img.shields.io/badge/Objective--C-structure-438EFF" alt="Objective-C structural parsing" />
  <img src="https://img.shields.io/badge/C%2B%2B-structure-00599C?logo=cplusplus&logoColor=white" alt="C++ structural parsing" />
  <br />
  <sub>结构提取还覆盖 PHP、C#/.NET、Rust、Astro/Svelte 等。<a href="#语言能力">查看完整范围</a></sub>
</p>

[![PyPI](https://img.shields.io/pypi/v/openmodus?label=PyPI&color=3775A9)](https://pypi.org/project/openmodus/)
![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.14-3776AB?logo=python&logoColor=white)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[**简体中文**](README.md) · [English](READMEs/README.en.md)

</div>

---

[核心功能](#核心功能) · [快速开始](#快速开始) · [为什么需要 Modus](#为什么需要-modus) · [技术原理](#技术原理) · [使用手册](#使用手册) · [开发与贡献](#开发与贡献)

**接手陌生项目，要改一条业务规则，如何找到负责它的代码和验证它的测试？**

Modus 为 Coding Agent 建立可追溯的项目知识库。本地分析把入口、调用和状态写入定位到源码。Agent 沿这些线索核对实现、测试、业务材料与团队约束，把规则成立的条件、失败后的恢复方式和验证入口写进仓库里的 Markdown。下一次改动时，开发者和 Agent 都能从同一条规则回到当前实现。

> 目前开源的是 Modus 的项目知识库部分；配套的 AI 工作流开源方案也在持续完善，后续会更新进展。

---

## 核心功能

Modus 把项目知识作为可维护的工程资产：本地分析提供线索，Agent 与人确认业务含义，Markdown 承载长期结论，日常任务按需使用并随变更修订。

### 从证据建立项目地图

初始化时，本地分析从源码、构建上下文和可用工具链提取有界证据，帮助定位入口、关系与关键行为。Agent 再回读源码、测试、配置和业务材料，确认系统架构、领域边界与真实场景，将判断写入系统概览、领域、模块及专题文档。

### 为任务渐进装配上下文

开发、排障或评审需要项目事实时，Agent 从系统概览进入相关领域、模块与场景，按需联读团队约束，并回到当前源码核验。检索按问题组织知识和实现片段，明确标示证据缺口；日常使用直接读取仓库中的 Markdown 与当前源码，无需重跑初始化分析。

### 让知识进入代码评审链路

长期知识以 Markdown 与代码同仓保存。稳定的领域与模块身份、知识链接和结构化源码锚点形成追溯路径；人工维护的业务知识与团队约束有明确所有权，完整性检查负责结构、链接和锚点，让知识变更具有清晰的评审边界。

### 随长期语义变化精确维护

代码变更后，Agent 根据本次修改判断职责、契约、规则、状态、依赖、资源或源码锚点是否发生长期变化；确有影响时，在原定义处修订受影响正文并同步相关导航与引用。新增业务材料和局部事实也可以定向更新，使知识随项目演进而保持可用。

## 快速开始

从源码安装 CLI，接入目标仓库，再由 Agent 基于项目证据创建第一份知识。CLI 负责平台接入；经确认的 Markdown 才是留在仓库中的长期产物。

### 1. 安装 CLI

在 Modus 源码仓库根目录（包含 `pyproject.toml`），使用 [`uv`](https://docs.astral.sh/uv/) 安装 CLI（需要 Python 3.11–3.14）：

```bash
uv tool install .
```

也可以从 PyPI 安装发布包：`uv tool install openmodus`。参与 Modus 开发时，使用 `uv tool install --editable .` 可让源码修改直接生效。无论安装来源，命令都是 `modus`。其他安装方式与索引配置见[安装与接入选项](#安装与接入选项)。

### 2. 接入项目

进入要使用 Modus 的项目仓库：

```bash
cd path/to/your-project
modus init
```

在交互式终端中选择 Claude Code、Codex、Cursor、CodeBuddy 或 DeepSeek Harness（预览）。CLI 将平台中立的 Skill 与命令安装到项目，再通过对应适配器接入所选平台，并记录受管文件的所有权。脚本接入、多平台接入和安装状态检查见[安装与接入选项](#安装与接入选项)。

### 3. 创建项目知识

在所选 Coding Agent 中打开该项目，在对话中运行：

```text
/modus-init
```

这是知识创作工作流，与 Shell 中的 `modus init` 不同。Agent 会使用本地分析定位线索，回读当前源码、测试、配置和你提供的业务材料，并在确认项目边界后撰写知识。若平台以 Skill 名称而非斜杠命令呈现能力，直接要求它“使用 modus-init 初始化当前项目知识”即可。

完成后，`.modus/` 保存平台中立的接入资产，`modus/knowledge/` 保存与代码一起评审的 Markdown 知识，`modus/.cache/` 保存可丢弃的初始化证据。日常任务按需读取知识与当前源码，无需重跑初始化分析。首次创作的验收与后续维护见[使用手册](#使用手册)。

## 为什么需要 Modus

### 你会得到什么

接手一个项目时，找到代码入口只是开始：还需要弄清规则为何存在、什么结果算完成、失败后如何恢复，以及改动要守住哪些边界。Modus 把经源码和可用业务材料核验的长期结论留在仓库，让后续任务从已有理解出发，并继续以当前源码核对实现。

| 你关心的事 | Modus 带来的变化 |
| --- | --- |
| 接手项目 | 从系统概览沿 Domain、Module 进入相关场景，找到职责、关键判定和验证入口；下一轮任务可以沿同一路径继续，减少重复摸索。 |
| 判断怎么改 | 围绕当前任务联读业务规则、接口契约、状态与失败恢复、团队约束，再回到当前源码确认修改点和影响面。 |
| 评审结论 | 知识以仓库内的 Markdown 呈现，可随代码 diff 一起评审；链接和源码锚点帮助追溯，机械核验检查路径、链接与锚点。 |
| 长期维护 | 代码变化后先判断长期语义是否受影响；需要更新时在原定义处修订并同步引用，避免为每次编辑追加一段很快过时的说明。 |

这份知识是仓库内可读、可改、可删除的 Markdown。初始化分析在本地生成本轮创作需要的有界证据；普通任务直接使用当前源码和已经审阅的正文，不依赖远程知识服务、向量数据库或持久化源码图。

### 支持的平台与语言

Modus 需要 Python 3.11–3.14，安装后的命令是 `modus`。下面按平台与语言列出可用范围。

#### Coding Agent 平台

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-Agent_Skills-D97757" alt="Claude Code Agent Skills" />
  <img src="https://img.shields.io/badge/Codex-Agent_Skills-111111" alt="Codex Agent Skills" />
  <img src="https://img.shields.io/badge/Cursor-Skills_%26_Rules-111111" alt="Cursor Skills and Rules" />
  <img src="https://img.shields.io/badge/CodeBuddy-Skills_%26_Commands-1F6FEB" alt="CodeBuddy Skills and Commands" />
</p>

每个适配器声明自己的 Skill 目录与常驻说明；共享安装器负责确定性写入、所有权清单、升级合并与安全卸载。Modus 通过常驻说明与 Skills 按需提供项目指引，不安装会话启动 hook。

旧项目执行 `modus update --project` 时，会按安装清单移除 Modus 的 hook 条目和未被用户修改的启动脚本，保留其他工具的命令与用户配置。损坏的配置会保留并报告，修复后可再次更新。

#### 语言能力

当前源码分别记录文件是否纳入分析、语法结构能提取到什么，以及本地工具链能进一步绑定哪些符号。

**编译器或类型系统增强**

<p align="center">
  <img src="https://img.shields.io/badge/Python-semantic-3776AB?logo=python&logoColor=white" alt="Python semantic provider" />
  <img src="https://img.shields.io/badge/Java-semantic-ED8B00?logo=openjdk&logoColor=white" alt="Java semantic provider" />
  <img src="https://img.shields.io/badge/Go-semantic-00ADD8?logo=go&logoColor=white" alt="Go semantic provider" />
  <img src="https://img.shields.io/badge/C%2FC%2B%2B-semantic-00599C?logo=cplusplus&logoColor=white" alt="C and C++ semantic provider" />
  <img src="https://img.shields.io/badge/TypeScript-semantic-3178C6?logo=typescript&logoColor=white" alt="TypeScript semantic provider" />
</p>

Python、Java、Go、C/C++ 和 TypeScript 可在结构解析的基础上补充本地编译器或类型检查器的观察。自动模式下，可选工具链缺失会留下对应的覆盖缺口。显式要求编译语义时，必需的提供方失败会中止本轮分析。

例如，Java 的结构解析可以定位一行方法调用。项目构建上下文和本地 JDK 可用时，Modus 还会通过 `javac` 查询该调用绑定的方法声明，保留调用位置和目标身份。[Java 编译器适配实现](src/modus/machine/facts/provider_assets/ModusJavaAnalyzer.java)

**专门结构提取**

<p align="center">
  <img src="https://img.shields.io/badge/JavaScript%20%2F%20TypeScript-structure-F7DF1E?logo=javascript&logoColor=111111" alt="JavaScript and TypeScript" />
  <img src="https://img.shields.io/badge/Java-structure-ED8B00?logo=openjdk&logoColor=white" alt="Java" />
  <img src="https://img.shields.io/badge/Kotlin-structure-7F52FF?logo=kotlin&logoColor=white" alt="Kotlin" />
  <img src="https://img.shields.io/badge/Swift-structure-F05138?logo=swift&logoColor=white" alt="Swift" />
  <img src="https://img.shields.io/badge/Objective--C-structure-438EFF" alt="Objective-C" />
  <img src="https://img.shields.io/badge/Python-structure-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Go-structure-00ADD8?logo=go&logoColor=white" alt="Go" />
  <img src="https://img.shields.io/badge/PHP-structure-777BB4?logo=php&logoColor=white" alt="PHP" />
  <img src="https://img.shields.io/badge/C%2FC%2B%2B-structure-00599C?logo=cplusplus&logoColor=white" alt="C and C++" />
  <img src="https://img.shields.io/badge/C%23%20%2F%20.NET-structure-512BD4?logo=dotnet&logoColor=white" alt="C sharp and .NET" />
  <img src="https://img.shields.io/badge/Rust-structure-000000?logo=rust&logoColor=white" alt="Rust" />
  <img src="https://img.shields.io/badge/Astro%20%2F%20Svelte-template-FF5D01?logo=astro&logoColor=white" alt="Astro and Svelte templates" />
</p>

| 语言或格式 | 能从源码提取的结构 |
| --- | --- |
| Java | 提取类、接口、字段、方法及调用位置。从语法节点读取参数类型和数组维度，也能记录显式的可空注解与序列化字段名。 |
| Python | 提取类、函数、导入别名和作用域，记录函数体中的调用位置。 |
| JavaScript、TypeScript（含 JSX、TSX） | 识别导入、导出、函数和调用点。TypeScript 还可记录显式声明的类型成员及其可选性。 |
| Go | 记录包、导入路径及别名、函数声明和调用，包括通过导入别名发起的调用。 |
| C | 提取函数定义、调用与 `#include`，保留它们的源码位置。 |
| C++ | 保留命名空间，区分方法原型与定义，提取模板接收者上的调用。未展开的注册宏会留下覆盖缺口。 |
| C#（.NET） | 提取 `.cs` 文件中的类型、方法声明和方法体内的调用。 |
| PHP | 提取类和方法的名称、签名、所属作用域与源码位置。 |
| Rust | 提取结构体、函数、`use` 导入及调用，保留泛型调用中的显式类型参数。 |
| Kotlin | 提取包、别名导入、扩展函数的接收者以及 Compose DSL 中的调用。跨 source set 存在多个目标时保留候选。 |
| Swift | 保留参数标签和扩展的归属，区分同名重载的声明。 |
| Objective-C | 识别多段 selector、category、类方法与实例方法，记录消息发送的位置。 |
| Objective-C++ | 在混编文件中分别提取 Objective-C 消息和 C++ 调用，沿用原文件字节坐标，标明部分覆盖。 |
| Vue、Svelte、Astro | 提取组件内的 JavaScript 或 TypeScript 脚本，也读取 Astro 的前置脚本区，保留脚本在原组件中的位置。 |
| Markdown（含 MDX、QMD） | 从 Markdown 标题提取文档章节和所在行，供材料定位。 |

`.h` 依据冻结源码中的语法区分 C、C++、Objective-C 和 Objective-C++。对于 `.mm` 文件，Modus 可提取两种语言的结构，并标明混编解析的覆盖范围。普通源码导航和检索也识别 `.m`、`.mm`、`.hh` 和 `.hxx`。成员调用的实际目标仍可能依赖类型推断或运行时派发，这类关系保留候选或缺口。[语言访问器回归用例](tests/machine/test_mobile_adapters.py)

其余已登记的源码、模板、配置、数据定义和文档格式仍会进入有界通用证据流程。Modus 会如实保留覆盖缺口，而不会因为某个 Provider 缺失就断言仓库没有业务行为。[语言与后缀注册表](src/modus/machine/language-registry.json)

### 为什么选择 Modus

Coding Agent 可以快速搜索文件、解释局部实现。让这份理解在多人、多次任务之间持续可用，还要处理三个问题：

1. **发现难以复用。** 入口、调用关系、规则和验证方式在一次会话中被推导，下一次又要从头查起。
2. **结构无法独自解释业务。** import、调用边和目录聚类能指向相关代码；业务边界、设计动机和恢复策略还需要结合源码、测试与材料判断。
3. **知识会随代码失真。** 缺少所有权、追溯线索和维护时机的文档，可能在实现变化后仍显得可信。

Modus 将这些问题落实为一条可检查的知识生产与维护链路：

- **证据与判断分层。** 本地分析提供入口、关系和标明确定性与缺口的线索；Agent 与人结合当前源码、测试、配置及可用材料核验后，才把判断写入正文。证据缺口会显式保留，不由推测填平。
- **按稳定边界组织知识。** 系统概览负责导航，Domain 定义业务能力边界，Module 讲清场景与职责，专题文件保存接口、对象、规则、状态、依赖和基础设施的主定义；人工维护的业务知识与团队约束有明确所有权。
- **创作成本不转嫁给日常使用。** init/reinit 的分析图和证据包用于当轮创作；后续任务按问题渐进读取已审阅的 Markdown 与当前源码，检索结果也保留覆盖缺口。
- **维护落在原有工程流程里。** 修改后判断职责、契约、规则等长期事实或源码锚点是否改变；有影响才做定向修订，并用链接与锚点检查守住可追溯性。

## 技术原理

<a id="从证据到知识"></a>

### N/K/C 三层如何协作

```text
项目源码、构建配置、可用工具链
  ↓
N · 机器举证     冻结输入，解析关系，从公开入口追到可观察的效果
  ↓ 本轮证据包，附源码位置、解析精度和覆盖缺口
K · 知识创作     Agent 回读源码、测试和业务材料，与人确认领域边界
  ↓ 经评审的 Markdown，与项目代码一起版本管理
C · 日常使用     按任务联读知识、团队约束和当前源码，执行并验收
  └─ 改动影响长期事实时，修订原定义及其引用
```

以一个订单系统为例，**回调接口返回“已受理”，订单状态就一定已经提交了吗？** 在 `/modus-init` 或 `/modus-reinit` 中，N 定位值得查的调用与写入，K 查明哪一步才算完成。下次有人修改重试策略时，C 使用已评审的结论和当前实现，直接从这个问题继续。

#### N · 从源码到证据包

| 阶段 | 交给下一步的证据 |
| --- | --- |
| N1 源码基线 | 冻结本轮输入的字节，区分实现、测试、配置等来源。文件内容与分析环境共同确定基线，排除或无法读取的输入也有记录。 |
| N2 程序事实 | 语言访问器从冻结输入提取声明、作用域和引用，框架观察器定位入口，可用的编译器或类型检查器补充绑定。事实带来源和坐标。 |
| N3 关系解析 | 按声明身份、所有者与源码位置协调结构和编译器观察，构建带类型的有向多重图。关系保留 `exact`、`candidate`、`heuristic` 或 `unresolved` 的解析精度。 |
| N4 能力组合 | 从 HTTP、消息、任务等公开入口沿有依据的关系做有界广度优先遍历，交付到达状态写入、消息发送等效果的代表路径，分别记录循环、未解析终点和预算截断。 |
| N5 创作投影 | 依据入口到效果的能力和权威对象提出范围候选，用结构社区辅助判断哪些文件值得一起读，并标出需要拆分或尚未归属的部分。 |
| N6 证据打包 | 复核基线与完整性后原子发布 JSON 证据包。按能力、路径或符号查询时，创作上下文携带 `baselineDigest` 与 `bundleDigest`，同时标明预算内交付了什么、省略了多少、从哪里继续查。输入漂移或校验失败会阻止本轮发布。 |

投影与打包只消费前序分析结果。作者收到范围建议时，可以展开它所引用的观察，核对来源和精度。[六阶段管线](src/modus/machine/pipeline.py) · [证据包与查询契约](src/modus/machine/packet/README.md)

**为什么在 Tree-sitter 之上写语言访问器？** Tree-sitter 从源码生成具体语法树（CST）。Modus 的访问器从语言特有的节点提取声明、作用域和调用位置。解析 Objective-C++ 时，Modus 用等长字节遮罩处理 Objective-C 语法，让 C++ 调用仍能按原始坐标定位到 `.mm` 源文件。访问器实现或语法包版本变化时，缓存中的旧观察随之失效。[Tree-sitter](https://tree-sitter.github.io/tree-sitter/) · [解析实现](src/modus/machine/facts/native_parser.py) · [混编坐标测试](tests/machine/test_mobile_integration.py)

**为什么证据图要保留平行边？** 同一个回调函数可能在两个分支调用同一写入方法。审查重试行为时，要能查清每次调用来自哪一行。N3 采用 NetworkX 的 `MultiDiGraph` 表示方向和平行边，由 Modus 为证据边分配稳定身份、记录来源与调用位置，并判断哪些目标可以绑定。N4 沿有向边追到效果时，一条路径的解析精度取沿途最弱证据。即使入口已精确绑定，只要中间一步是候选，整条路径就仍需核对。[证据图与边身份](src/modus/machine/resolution/evidence_graph.py) · [能力遍历](src/modus/machine/capability/traversal.py)

**为什么社区发现要换一张图？** 为了判断哪些文件值得一起读，N5 只选同一分析上下文内已精确绑定的本地调用和导入，投影成无向文件图。两个文件之间即使有二十处调用，也只计一条依赖。Modus 在各连通分量内分别运行 NetworkX 的 Louvain 算法，按模块度寻找联系紧密的文件组。各分量独立划分，加入无关代码不会打乱已有分组。固定节点与边的顺序和随机种子，使同一输入的划分可复现。[Louvain 原论文](https://arxiv.org/abs/0803.0476) · [Modus 的社区划分](src/modus/machine/projection/community_signal.py)

节点、边或层数预算限制了划分时，Modus 记录受影响的范围。社区只作为结构线索，作者结合入口、写入和业务材料提出 Domain/Module 边界，在 K1 与用户确认。

#### K · 从证据到可评审的知识

| 阶段 | 作者交付什么 |
| --- | --- |
| K1 范围建模 | 结合机器候选、现有知识和用户材料，与用户确认本轮覆盖的 Domain、Module 及其稳定身份。 |
| K2 创作计划 | 确定每项事实由哪篇文档完整定义、哪些页面引用它，以及哪些跨域交接需要双方核对。 |
| K3 证据闭环 | 按场景回读实现、测试、配置与业务材料，记录触发条件、关键判断、可见结果和失败恢复。证据不足时写明待查问题。 |
| K4 领域成稿 | 用 Module 讲清完整场景，把接口、对象、规则、状态、下游依赖和基础设施的细节放进各自的专题，逐篇对照来源验收。 |
| K5 项目约束 | 从源码、测试、CI 和团队材料中核实工程要求，说明适用范围、强制检查与例外，尊重已有人工规范的所有权。 |
| K6 系统概览与发布 | 核对跨域交接双方的最终描述，依据已成稿的领域知识和项目约束编写系统概览。作者回读正文，发布核验检查路径、身份、链接与源码锚点。 |

**订单回调的“已受理”能证明什么？** 作者先查哪条分支返回这个响应，再找真正提交订单状态的事务或下游消费者，最后核对重复通知和失败恢复的测试。如果只能证实请求已受理，正文就只写到受理，把完成信号留作具体待查项。

**证据变化时从哪里继续？** 创作按领域推进。K4 写到某个状态转换却找不到依据，就回到 K3 补查，再修订受影响的主定义。本轮检查点保留已确认的范围和进度，中断后可从最早未完成的工作继续。[六阶段创作契约](docs/authoring-contract.md)

#### C · 在下一次改动中使用和维护知识

| 阶段 | 当前任务得到什么 |
| --- | --- |
| C1 任务定界 | 明确要回答的问题或要改变的行为，以及哪些未知会影响结果。 |
| C2 联合定位 | 找到相关规则的主定义、适用的团队约束、实现入口和验证位置。 |
| C3 证据收敛 | 回读当前源码和已定位材料，核实规则成立的条件与例外，区分已证实的事实和仍会影响决定的缺口。 |
| C4 产出决策 | 确定本次改变和保留哪些行为、选择依据是什么，以及怎样验收。 |
| C5 执行与验收 | 落实决定，把实际结果逐项与预期核对，标明已验证的范围和仍未完成的验证。 |
| C6 知识留存判断 | 根据实际差异和验收结果，判断哪些长期事实或源码锚点受影响，需要时转入定向维护。 |

**怎样找到这次改动真正需要的规则？** 日常任务直接读取当前 Markdown 与源码，初始化证据包仅服务当轮创作。知识检索把标题、路径等结构信号与 BM25 词项匹配分别排序，再用倒数排名融合（RRF）合并。命中的规则连同适用条件、例外和恢复说明一起交付，截断处给出续读位置。已有证据足以支持决定时，Agent 可以直接进入 C4。[检索排序实现](src/modus/retrieval/stages/ranking.py)

**修改重试策略后，哪些知识要跟着改？** 以订单回调为例，Agent 先核对重复通知的返回值和订单状态的实际变化。若返回契约改变，就修订原规则及其引用。若只重构了函数内部，规则和源码锚点仍准确，核对后即可结束。[日常任务的阶段与停止条件](src/modus/scaffold/templates/skills/using-modus/references/consumption.md)

### 知识模型

完成项目知识创作后，`.modus/` 保存平台控制面，`modus/knowledge/` 保存长期知识，`modus/.cache/` 保存可丢弃的分析状态。Modus 的知识模型不是一棵按文件类型堆积的文档树，而是围绕研发任务组织的四种可组合视角。它们是阅读和建模视角，不是要求每个项目复制同一种技术分层。

| 视角 | 回答的问题 | 主要载体 |
| --- | --- | --- |
| 业务 | 为什么要改，业务概念、场景与历史经验落在哪里？ | Domain 路由与 `business/` 中的概念、场景、历史实践 |
| 架构 | 能力边界是什么，运行单元和模块之间如何协作？ | 根概览、Domain 边界、状态与下游交接 |
| 系统 | 一个能力内部如何工作，接口、对象、规则和资源如何共同形成结果？ | Module 场景手册与六类专题事实 |
| 工程约束 | 哪些内容不能随意改变，修改后如何证明安全？ | `constraint/`、规则与基础设施专题、Module 的实现与验证入口 |

```text
modus/knowledge/
├── architecture-overview.md          项目总览、运行分层、能力协作、导航与排障入口
├── constraint/
│   ├── global-standard.md             全局约束
│   └── team-standard.md               团队架构、变更与验证标准
└── domain/<domain>/
    ├── SKILL.md                       Domain 路由与能力全景
    └── references/
        ├── modules/<module>.md        职责、场景、设计取舍与实现验证
        ├── api.md                     契约总览与稳定导航
        ├── api/                       可选的契约语义分组；不按单接口分片
        ├── object.md                  对象总览与稳定导航
        ├── object/                    可选的对象语义分组；不按单 DTO/类分片
        ├── rule.md                    规则、约束、例外与依据
        ├── state_machine.md           状态、链路、失败与恢复
        ├── downstream.md              依赖、事件与系统交接
        ├── infrastructure.md          存储、配置、进程与运行资源
        └── business/                  团队人工维护的业务知识
            ├── index.md               业务知识入口
            ├── meta/                  术语、概念、对象、口径与规则
            ├── experience/            历史决策、实践、复盘与适用条件
            └── scenario/              参与者、流程、结果与异常场景
```

这些载体各自承担稳定职责：Domain 是能力和所有权边界，`SKILL.md` 负责路由；Module 围绕职责与真实场景组织因果主线；六类专题保存可复用事实的唯一完整定义；根概览连接全局能力与运行架构。前端、后端、CLI、库、Worker、数据任务、基础设施和插件共享这份合同，但只展开真实存在的能力块。

**结构负责路由，正文负责解释。** 稳定身份、源码锚点和精确链接帮助 Agent 渐进地从根概览进入 Domain、Module 与相关专题；Markdown 正文解释业务结果、关键判定、完成边界、失败恢复和设计取舍。方法级源码证据只进入 Module 与专题，根概览和 Domain 保持为稳定路由；一个事实只在一处完整定义，其他位置通过链接复用，避免把整个知识库一次性塞入上下文。

日常检索按请求从当前 Markdown 临时建立索引。推断出的 Domain 与 Module 影响排序，其他模块仍可命中。正文、源码与团队约束共用时间和输出预算，结果标明哪些证据类型仍然缺失。[检索管线](src/modus/retrieval/README.md)

Modus 优先显式化**高复用、高风险、高隐性**的知识，而不是为每个函数生成摘要。公开契约、核心对象、状态流转、下游交接、兼容红线和验证标准值得长期维护；从当前代码即可低成本读出的普通实现细节仍留在源码中。`business/` 与 `constraint/` 默认受人工所有权保护，自动流程不会用扫描结果覆盖组织经验；生成知识的变更使用读时哈希保护，并接受路径身份、链接与锚点完整性核验。

### 代码架构

Modus 自身也遵守它倡导的边界：入口层保持窄，应用编排与检索算法分离，平台差异通过声明式适配器收口，长期知识与一次性分析状态拥有不同的目录和写入合同。

| 子系统 | 职责与边界 |
| --- | --- |
| `modus.machine` | 机器层：按 N1–N6 生命周期（corpus→facts→resolution→capability→projection→packet）冻结输入、观察事实、解析关系，并为当前 init/reinit 发布不可变、有界的证据包。 |
| `modus.orchestrator` | 组合预检、任务上下文与知识影响候选；不拥有检索算法或知识写入。 |
| `modus.retrieval` | 在统一时间与输出预算下渐进选择正文、当前源码和约束，并显式报告部分结果。 |
| `modus.platforms` | 把中立 Skill 投影到五个平台，隔离宿主目录、常驻说明与调用权限差异。 |
| `modus.scaffold` | 打包中立模板，执行确定性项目安装、升级协调、所有权记录与安全卸载。 |
| `knowledge_verification` / `knowledge_write_session` | 分离机械完整性核验、人工所有权、比较并交换写入和原子发布。 |

初始化分析与知识写入各有发布边界。机器层验证新证据包之后才替换当前包。失败时已有完整包仍然保留，创作端依据本轮身份判断证据是否可用。[分析层的失败与发布](src/modus/machine/README.md#失败与发布)

知识写入则逐文件核对所有权和读取时的内容哈希。如果有人在作者准备修改后编辑了同一文档，写入会报告冲突，让作者基于最新正文重新判断。通过核对的文件才原子替换，写完再检查知识链接和源码锚点。[知识写入会话](src/modus/knowledge_write_session.py)

## 使用手册

[快速开始](#快速开始)给出最短路径；这里补充接入检查、工作流选择与日常维护。终端里的 `modus` 管理安装与状态；Agent 里的 `/modus-*` 创作和修订知识。

### 安装与接入选项

公网 PyPI 发行包名是 `openmodus`，安装不需要私有软件源。也可以用 `pipx install openmodus`；如果本机自定义索引不代理公网 PyPI，可以运行 `uv tool install --default-index https://pypi.org/simple openmodus`。

`modus init` 在交互式终端中选择平台；脚本或非交互终端中可显式指定，例如 `modus init --platform codex`，需要多个平台时重复 `--platform`，或用 `modus init --all-platforms`。未指定平台的首次非交互运行会接入全部支持的平台。同一份中立 Skill 合同会投影到所选平台。

DeepSeek Harness（预览）使用 `modus init --platform dsh` 接入项目工作流；原生插件 `@modus-ai/modus` 额外提供上下文检索、知识状态、影响检查和核验工具。Python CLI 当前需从包含 DSH 集成的源码安装，原生插件可从 npm 安装；兼容 DSH `0.2.1-rc.3` / `0.2.2-alpha.2`。参见 [DSH 安装与使用](integrations/dsh/README.md)、[集成设计](integrations/dsh/architecture.md)。

接入后在目标仓库运行 `modus status`：显示 `Installation: installed`（已安装）表示项目资产已就位。CLI 会在 `modus/knowledge/` 放置初始文件，仍需在 Agent 中运行 `/modus-init` 创作正文；`status` 的知识文档数也会计入初始文件，不能单独作为创作完成的依据。

### CLI 命令

CLI 用于安装、维护和检查 Modus。运行 `modus help` 可以查看当前版本的完整入口。

| 命令 | 用途 |
| --- | --- |
| `modus init` | 为当前项目安装中立资产，并投影到选择的 Coding Agent 平台。 |
| `modus update` | 更新本机 CLI，并协调当前项目中由 Modus 管理的 Skills 与常驻说明。 |
| `modus help` | 查看 CLI、主动知识工作流和自动知识能力。 |
| `modus uninstall` | 默认展示计划，经交互确认后卸载当前项目资产与个人 CLI；正文知识默认保留。 |
| `modus status` | 只读查看安装、版本与正文知识状态，不读取初始化分析缓存。 |

常用的只读检查与操作预览：

```bash
modus status
modus status --json
modus help /modus-init
modus update --dry-run
modus uninstall --dry-run
modus uninstall --project --delete-knowledge --dry-run
modus uninstall --person --dry-run
```

`modus update` 默认同时升级本机 CLI 并协调当前项目的托管资产；只更新项目时用 `--project`，只更新本机 CLI 时用 `--person`。`modus uninstall` 默认同时处理当前项目与个人 CLI；当前目录没有项目级安装时会跳过项目级，继续卸载个人 CLI。卸载同样可用 `--project` 或 `--person` 限定范围，`--all` 是裸命令的兼容别名。项目正文知识默认保留；只有显式加上 `--delete-knowledge` 才会一并删除。更新和卸载都可先用 `--dry-run` 查看计划。

### 主动知识工作流

这些入口在 AI 编程平台中使用，不要在 Shell 中执行。

| 工作流 | 使用时机 |
| --- | --- |
| `/modus-init` | 从当前代码、构建上下文和材料创建完整项目知识；已有正式 Scope 时自动按 reinit 处理。 |
| `/modus-reinit` | 复用稳定 Domain/Module 身份，全量复核并重新整理已有正文。 |
| `/modus-update-knowledge` | 针对明确材料或局部事实，更新受影响知识而不重跑全仓分析。 |

首次运行 `/modus-init` 时，可向 Agent 提供已知的项目边界、业务材料和团队约束。Agent 会先整理 Domain/Module 范围供确认，再逐域回读源码并写入正文。完成后从 `modus/knowledge/architecture-overview.md` 沿 Domain 的 `SKILL.md` 进入相关 Module，抽查一个真实场景的规则、失败恢复与验证入口是否能在当前源码中找到依据，并像审阅代码一样审阅新增正文。

已有知识时，涉及整体边界或需要全量复核可运行 `/modus-reinit`；有明确的新材料或局部事实要纳入知识时，运行 `/modus-update-knowledge` 并给出材料路径及受影响范围。普通编码任务不需要重新执行这些创作工作流。

升级 CLI 后，运行 `modus update --project` 将最新命令、技能和共享参考同步到已接入项目；只读预览可加 `--dry-run`。这一步保留正文知识和用户修改过的接入文件，报告中的冲突需要单独处理。随后使用知识工作流时，才会按其范围复核或修订正文。

完整创作按 K1–K6 推进：范围与材料 → 主定义计划 → 证据闭环 → 领域/模块成稿 → 项目约束 → 系统概览与发布。团队规范在领域事实闭合后独立提炼，系统概览再引用两者的最终结果。已有人工规范始终受保护；首次填充只替换缺失内容或未改动的框架种子。阶段分工与验收见[创作契约](docs/authoring-contract.md)。

增量更新与自动同步复用同一套正文和发布规则，从实际变化追踪场景、主定义、消费者、跨端实现与相关导航，并修复受影响场景内已证实的历史错漏。既有模块内自动维护；真实结构变化沿用授权或在当前任务中合并确认，确认后继续，无需另跑维护命令。工程机制变化会核对团队规范，但只有明确委托时才修改规范。

流程复用当前任务证据，不读取初始化证据包、不增加执行卡或持久待办、不依赖宿主专用步骤。正文已准确时跳写，影响未明时继续定向调查；能够解决的冲突在当前任务处理，确需用户决定、外部证据或工具恢复时明确报告知识未完成。该机制不保证发现从未触及的历史盲区，也不提供脱离会话上下文的自动恢复。

工作区成员的发布核验使用 `modus knowledge verify --publication --member <member-id> --root <workspace-root> --json`，从唯一根卡选择已配置成员计划，并在该成员仓库内核验。

### 自动知识能力

- `using-modus`：只在任务需要当前项目事实时渐进加载知识，并在修改任务交付前判断是否产生长期知识影响。
- `modus-sync-knowledge`：对已知或待查明的长期影响定向调查，完成最小、原位、可验证的正文修订。

它们属于 Agent 生命周期，不是要求用户额外记忆或逐次执行的工作流。

日常使用时，直接向 Agent 提出具体任务，例如“检查订单回调的重复通知与重试规则，找到实现和验证入口，并修复已确认的问题”。Agent 按需沿概览、Domain 和 Module 读取相关知识，再用当前源码核验；若本次修改改变了长期契约、规则、状态或源码锚点，交付前才修订对应正文。你也可以从 `architecture-overview.md` 沿链接手动阅读，遇到文档与实现不一致时以当前源码为准，再定向修订知识。

## 开发与贡献

先阅读[架构导览](ARCHITECTURE.md)了解依赖方向与设计边界，再按[贡献指南](CONTRIBUTING.md)运行检查。CLI 帮助、交互提示、诊断、开发文档及新创作知识默认使用简体中文。命令名、参数、路径和 JSON 字段保持稳定，便于脚本与工具集成。

使用 Agent 开发时，从 [AGENTS.md](AGENTS.md) 进入，按 [modus-development](skills/modus-development/SKILL.md) 定位实现。代码设计规范由贡献指南维护；工作流 Markdown 的划分、撰写和行为验收见 [Skill 编写规范](docs/skill-authoring.md)。

Modus 支持 Python 3.11–3.14。开发环境和 CI 使用同一组锁定依赖：

```bash
uv sync --locked --extra test
uv run --locked --extra test pytest -q
```

提交前的静态、类型和分发检查统一见 [完整验证命令](CONTRIBUTING.md#本地开发)。

贡献代码时，请把 CLI、Skill、Schema 和 Markdown 合同视为公开接口：行为变更应带有聚焦测试，语言 Provider 缺口应保持可解释降级，平台适配不得绕过统一所有权和卸载语义。架构边界测试会阻止普通运行时依赖一次性初始化分析，并核对发布制品不重新引入旧图数据库或废弃命令。

### License

Modus 使用 [MIT License](LICENSE)。
