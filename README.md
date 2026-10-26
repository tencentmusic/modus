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
  <br />
  <sub>结构提取还覆盖 JavaScript、Kotlin、PHP、C#/.NET、Rust、Astro/Svelte 等。<a href="#语言能力">查看完整范围</a></sub>
</p>

[![PyPI](https://img.shields.io/pypi/v/openmodus?label=PyPI&color=3775A9)](https://pypi.org/project/openmodus/)
![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.14-3776AB?logo=python&logoColor=white)
<!-- NOCA:AllFileLicenseCheck(项目许可声明与根目录协议及包元数据一致) -->
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[**简体中文**](README.md) · [English](READMEs/README.en.md)

</div>

---

[核心功能](#核心功能) · [快速开始](#快速开始) · [为什么需要 Modus](#为什么需要-modus) · [技术原理](#技术原理) · [使用手册](#使用手册) · [开发与贡献](#开发与贡献)

**接手陌生项目，要改关键流程：规则在哪、代码在哪、如何验证？**

Modus 将源码与业务材料梳理成可核验的项目知识库，让 Coding Agent 联读源码、业务材料与团队约束，把业务场景、设计取舍和变更边界写成仓库内可核验的 Markdown 知识，并在后续编码中渐进使用、随变更修订。

> 目前开源的是 Modus 的项目知识库部分；配套的 AI 工作流开源方案也在持续完善，后续会更新进展。

---

<!--
产品价值与命令能力对应，维护宣传语时核对当前可执行入口。
-->

## 核心功能

Modus 把项目知识作为可维护的工程资产：本地分析提供线索，Agent 与人确认业务含义，Markdown 承载长期结论，日常任务按需使用并随变更修订。

<!--
证据地图说明观察能力，不代表机器已经完成业务知识创作。
-->

### 从证据建立项目地图

初始化时，本地分析从源码、构建上下文和可用工具链提取有界证据，帮助定位入口、关系与关键行为。Agent 再回读源码、测试、配置和业务材料，确认系统架构、领域边界与真实场景，将判断写入系统概览、领域、模块及专题文档。

<!--
上下文预算与降级共同约束检索结果，完整性描述必须保留这一前提。
-->

### 为任务渐进装配上下文

开发、排障或评审需要项目事实时，Agent 从系统概览进入相关领域、模块与场景，按需联读团队约束，并回到当前源码核验。检索按问题组织知识和实现片段，明确标示证据缺口；日常使用直接读取仓库中的 Markdown 与当前源码，无需重跑初始化分析。

<!--
评审链路依赖普通Markdown与版本控制，不能暗示独立的远端知识服务。
-->

### 让知识进入代码评审链路

长期知识以 Markdown 与代码同仓保存。稳定的领域与模块身份、知识链接和结构化源码锚点形成追溯路径；人工维护的业务知识与团队约束有明确所有权，完整性检查负责结构、链接和锚点，让知识变更具有清晰的评审边界。

<!--
维护触发点是长期语义变化，临时实现细节不应沉淀为团队规则。
-->

### 随长期语义变化精确维护

代码变更后，Agent 根据本次修改判断职责、契约、规则、状态、依赖、资源或源码锚点是否发生长期变化；确有影响时，在原定义处修订受影响正文并同步相关导航与引用。新增业务材料和局部事实也可以定向更新，使知识随项目演进而保持可用。

## 快速开始

从源码安装 CLI，接入目标仓库，再由 Agent 基于项目证据创建第一份知识。CLI 负责平台接入；经确认的 Markdown 才是留在仓库中的长期产物。

<!--
安装示例与分发包元数据同步；命令名和Python包名具有不同职责。
-->

### 1. 安装 CLI

在 Modus 源码仓库根目录（包含 `pyproject.toml`），使用 [`uv`](https://docs.astral.sh/uv/) 安装 CLI（需要 Python 3.11–3.14）：

```bash
uv tool install .
```

也可以从 PyPI 安装发布包：`uv tool install openmodus`。参与 Modus 开发时，使用 `uv tool install --editable .` 可让源码修改直接生效。无论安装来源，命令都是 `modus`。其他安装方式与索引配置见[安装与接入选项](#安装与接入选项)。

<!--
接入过程仅写入框架拥有的资产，用户正文的保护边界保持可见。
-->

### 2. 接入项目

进入要使用 Modus 的项目仓库：

```bash
cd path/to/your-project
modus init
```

在交互式终端中选择 Claude Code、Codex、Cursor 或 CodeBuddy。CLI 将平台中立的 Skill 与命令安装到项目，再通过对应适配器接入所选平台，并记录受管文件的所有权。脚本接入、多平台接入和安装状态检查见[安装与接入选项](#安装与接入选项)。

<!--
知识创作入口与后续维护入口分开说明，避免将重建作为日常前置。
-->

### 3. 创建项目知识

在所选 Coding Agent 中打开该项目，在对话中运行：

```text
/modus-init
```

这是知识创作工作流，与 Shell 中的 `modus init` 不同。Agent 会使用本地分析定位线索，回读当前源码、测试、配置和你提供的业务材料，并在确认项目边界后撰写知识。若平台以 Skill 名称而非斜杠命令呈现能力，直接要求它“使用 modus-init 初始化当前项目知识”即可。

完成后，`.modus/` 保存平台中立的接入资产，`modus/knowledge/` 保存与代码一起评审的 Markdown 知识，`modus/.cache/` 保存可丢弃的初始化证据。日常任务按需读取知识与当前源码，无需重跑初始化分析。首次创作的验收与后续维护见[使用手册](#使用手册)。

## 为什么需要 Modus

<!--
能力表描述项目已实现的范围，缺失提供方与降级应如实表述。
-->

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

<!--
平台支持列表与安装验收一起维护，不能以模板存在代替平台验证。
-->

#### Coding Agent 平台

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-Agent_Skills-D97757" alt="Claude Code Agent Skills" />
  <img src="https://img.shields.io/badge/Codex-Agent_Skills-111111" alt="Codex Agent Skills" />
  <img src="https://img.shields.io/badge/Cursor-Skills_%26_Rules-111111" alt="Cursor Skills and Rules" />
  <img src="https://img.shields.io/badge/CodeBuddy-Skills_%26_Commands-1F6FEB" alt="CodeBuddy Skills and Commands" />
</p>

每个适配器声明自己的 Skill 目录、常驻说明和 Hook 布局；共享安装器负责确定性写入、所有权清单、升级合并与安全卸载。

<!--
语言识别、结构解析和编译器证据是不同能力，不合并为统一精度承诺。
-->

#### 语言能力

不同语言的证据深度明确分层，不以“识别文件后缀”冒充完整语义支持。

**编译器或类型系统增强**

<p align="center">
  <img src="https://img.shields.io/badge/Python-semantic-3776AB?logo=python&logoColor=white" alt="Python semantic provider" />
  <img src="https://img.shields.io/badge/Java-semantic-ED8B00?logo=openjdk&logoColor=white" alt="Java semantic provider" />
  <img src="https://img.shields.io/badge/Go-semantic-00ADD8?logo=go&logoColor=white" alt="Go semantic provider" />
  <img src="https://img.shields.io/badge/C%2FC%2B%2B-semantic-00599C?logo=cplusplus&logoColor=white" alt="C and C++ semantic provider" />
  <img src="https://img.shields.io/badge/TypeScript-semantic-3178C6?logo=typescript&logoColor=white" alt="TypeScript semantic provider" />
</p>

Python、Java、Go、C/C++ 和 TypeScript 可以在结构证据之上使用本地编译器或类型检查器观察；工具链不可用时只降低对应证据，不阻塞整个项目。

**专门结构提取**

<p align="center">
  <img src="https://img.shields.io/badge/JavaScript%20%2F%20TypeScript-structure-F7DF1E?logo=javascript&logoColor=111111" alt="JavaScript and TypeScript" />
  <img src="https://img.shields.io/badge/Java-structure-ED8B00?logo=openjdk&logoColor=white" alt="Java" />
  <img src="https://img.shields.io/badge/Kotlin-structure-7F52FF?logo=kotlin&logoColor=white" alt="Kotlin" />
  <img src="https://img.shields.io/badge/Python-structure-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Go-structure-00ADD8?logo=go&logoColor=white" alt="Go" />
  <img src="https://img.shields.io/badge/PHP-structure-777BB4?logo=php&logoColor=white" alt="PHP" />
  <img src="https://img.shields.io/badge/C%2FC%2B%2B-structure-00599C?logo=cplusplus&logoColor=white" alt="C and C++" />
  <img src="https://img.shields.io/badge/C%23%20%2F%20.NET-structure-512BD4?logo=dotnet&logoColor=white" alt="C sharp and .NET" />
  <img src="https://img.shields.io/badge/Rust-structure-000000?logo=rust&logoColor=white" alt="Rust" />
  <img src="https://img.shields.io/badge/Astro%20%2F%20Svelte-template-FF5D01?logo=astro&logoColor=white" alt="Astro and Svelte templates" />
</p>

Objective-C、Objective-C++ 和 Swift 提供专门结构提取：保留 OC selector/category/protocol、Swift 扩展与参数标签，并按内容区分 `.h`。Objective-C++ 分别恢复 OC 与 C++ 结构，明确标为部分覆盖；Kotlin 补充包、导入、扩展函数与 Compose 尾随闭包，C++ 补充命名空间、头文件声明与模板调用。日常检索也覆盖 `.m`、`.mm`、`.hh`、`.hxx`。

这些结构证据不等于 Xcode/Swift/Kotlin 编译语义；不自动解析全部构建变体、宏展开或 IDL/JNI 跨语言桥接。原生和 Kotlin 取证适配会指导 Agent 核对生成来源、注册、Action/State 与端侧生命周期，缺失关系保留为候选或未解析。

其余已登记的源码、模板、配置、数据定义和文档格式仍会进入有界通用证据流程。Modus 会如实保留覆盖缺口，而不会因为某个 Provider 缺失就断言仓库没有业务行为。

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

### 从证据到知识

Modus 把一次性机器分析与长期知识明确分开：`init/reinit` 负责为本轮创作建立可核验的代码证据，Agent 和人负责把证据、业务材料与当前源码共同解释成知识；普通任务直接消费已评审的 Markdown，并在需要时回到当前实现核验。

```text
[一次性证据生产：init / reinit]
  源码 + 构建文件 + 测试/配置
    → Source Snapshot（冻结本轮仓库输入）
    → CST / 结构 IR / 项目绑定
    → 可选编译器与类型语义观察
    → 临时证据图 → 显式语义协调
    → 入口、关系、效果与资源的有界证据视图
    → 确定性、有界 JSON 证据包 ─────────────┐
                                             │
[知识创作]                                   ▼
  业务材料 + 团队约束 ─────────→ Agent + 人工判断 ← 回读当前源码
                                             │
                                             ▼
                               可评审、可追溯的 Markdown 知识
                                             │
[持续使用与维护]                             │
  日常任务 ─→ 渐进路由与检索 ────────────────┤→ 回读当前源码后行动
  代码变更 ─→ 长期知识影响判断 ─→ 有影响时最小修订
```

这里包含三个彼此解耦的阶段。证据生产只在 `init/reinit` 中运行；知识创作不会把机器关系直接改写成业务结论；持续使用与维护既不重建初始化分析，也不会因为每次代码编辑而制造文档噪声。

整条链路刻意维护三条边界：

- **证据负责导航，不负责裁决。** `exact`、`candidate`、`heuristic` 与 `unresolved` 保持可区分；冲突进入 diagnostics，Agent 必须回读源码、测试、配置或材料后才能陈述结论。
- **分析状态不是长期产品。** 临时图在投影后释放，JSON bundle 位于可丢弃缓存中并只服务当前创作会话；普通任务明确不读取它，只有经评审的 Markdown 进入长期知识。
- **当前源码始终权威。** 快照漂移或完整性错误会终止本轮分析，局部解析器或 Provider 缺口只降低受影响证据；普通使用和增量维护始终联合读取正文与当前源码，不会静默回退到旧结论。

以一个需要修改订单回调重试行为的项目为例：在覆盖范围内，初始化证据可指向回调入口、状态写入及相关源码，但“重复通知应返回什么”仍需作者回读实现、测试和可用的业务约定。确认后，幂等条件、失败恢复和验证入口按各自职责写入 Module 与规则、状态专题。下一位开发者沿 Domain、Module 找到这些结论，核对当前源码后动手；若改动改变了重试契约或状态迁移，就原位修订相应主定义和引用，内部重构则无需增加知识。

<!--
知识模型区分稳定身份与展示名称，翻译不能改变协议键。
-->

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

日常检索从当前 Markdown 临时建立索引，优先沿根概览、Domain 与 Module 链接选择待读取的文档，再结合结构信号与 BM25 词项匹配排序；推断出的路由用于调整相关性，不直接排除其他可能相关的模块。命中的小节会按完整条目重组，让条件、异常与恢复说明一起进入上下文；当前源码和团队约束共享同一时间与输出预算。结果会标出未找到的证据类型，并为截断的条目给出继续阅读的范围，供开发者判断还需回读什么，而非把“检索到”当作“已经证实”。

Modus 优先显式化**高复用、高风险、高隐性**的知识，而不是为每个函数生成摘要。公开契约、核心对象、状态流转、下游交接、兼容红线和验证标准值得长期维护；从当前代码即可低成本读出的普通实现细节仍留在源码中。`business/` 与 `constraint/` 默认受人工所有权保护，自动流程不会用扫描结果覆盖组织经验；生成知识的变更使用读时哈希保护，并接受路径身份、链接与锚点完整性核验。

<!--
架构解释围绕输入、所有权与失败语义，图示跟随真实依赖方向。
-->

### 代码架构

Modus 自身也遵守它倡导的边界：入口层保持窄，应用编排与检索算法分离，平台差异通过声明式适配器收口，长期知识与一次性分析状态拥有不同的目录和写入合同。

| 子系统 | 职责与边界 |
| --- | --- |
| `modus.machine` | 机器层：按 N1–N6 生命周期（corpus→facts→resolution→capability→projection→packet）冻结输入、观察事实、解析关系，并为当前 init/reinit 发布不可变、有界的证据包。 |
| `modus.orchestrator` | 组合预检、任务上下文与知识影响候选；不拥有检索算法或知识写入。 |
| `modus.retrieval` | 在统一时间与输出预算下渐进选择正文、当前源码和约束，并显式报告部分结果。 |
| `modus.platforms` / `modus.hooks` | 把中立 Skill 投影到四个平台，隔离宿主目录、说明文件与会话 Hook 差异。 |
| `modus.scaffold` | 打包中立模板，执行确定性项目安装、升级协调、所有权记录与安全卸载。 |
| `knowledge_verification` / `knowledge_write_session` | 分离机械完整性核验、人工所有权、比较并交换写入和原子发布。 |

机器层按冻结输入、事实观察、关系解析、能力组合、创作投影和证据打包单向推进。投影与打包阶段只消费前序结果，不重新观察源码来补造事实；可选编译器或局部解析失败时，保留仍可用的线索，并标明受影响范围。投影给出的能力边界和行为路径只是作者继续核验的候选，不能直接充当业务结论。

证据包只有在完整校验后才会发布。若源码在分析期间变化，或证据完整性校验失败，本轮机器结果就不能当作已核验的事实；失败构建不会替换已有完整包，本轮创作也不会用旧包冒充当前证据。知识正文则按所有权和读时内容保护写入，完成后检查结构、链接与源码锚点。这样，局部证据缺口、整轮分析失败和正文写入冲突各有明确处理边界，开发者仍能回到当前源码与可用材料继续工作。

## 使用手册

[快速开始](#快速开始)给出最短路径；这里补充接入检查、工作流选择与日常维护。终端里的 `modus` 管理安装与状态；Agent 里的 `/modus-*` 创作和修订知识。

### 安装与接入选项

公网 PyPI 发行包名是 `openmodus`，安装不需要私有软件源。也可以用 `pipx install openmodus`；如果本机自定义索引不代理公网 PyPI，可以运行 `uv tool install --default-index https://pypi.org/simple openmodus`。

`modus init` 在交互式终端中选择平台；脚本或非交互终端中可显式指定，例如 `modus init --platform codex`，需要多个平台时重复 `--platform`，或用 `modus init --all-platforms`。未指定平台的首次非交互运行会接入全部支持的平台。同一份中立 Skill 合同会投影到所选平台。

接入后在目标仓库运行 `modus status`：显示 `Installation: installed`（已安装）表示项目资产已就位。CLI 会在 `modus/knowledge/` 放置初始文件，仍需在 Agent 中运行 `/modus-init` 创作正文；`status` 的知识文档数也会计入初始文件，不能单独作为创作完成的依据。

<!--
命令手册与CLI注册同步，示例保留真实参数与退出语义。
-->

### CLI 命令

CLI 用于安装、维护和检查 Modus。运行 `modus help` 可以查看当前版本的完整入口。

| 命令 | 用途 |
| --- | --- |
| `modus init` | 为当前项目安装中立资产，并投影到选择的 Coding Agent 平台。 |
| `modus update` | 更新本机 CLI，并协调当前项目中由 Modus 管理的 Skill 与 Hook。 |
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

### 自动知识能力

- `using-modus`：只在任务需要当前项目事实时渐进加载知识，并在修改任务交付前判断是否产生长期知识影响。
- `modus-sync-knowledge`：只在正向影响判定后执行最小、原位、可验证的正文修订。

它们属于 Agent 生命周期，不是要求用户额外记忆或逐次执行的工作流。

日常使用时，直接向 Agent 提出具体任务，例如“检查订单回调的重复通知与重试规则，找到实现和验证入口，并修复已确认的问题”。Agent 按需沿概览、Domain 和 Module 读取相关知识，再用当前源码核验；若本次修改改变了长期契约、规则、状态或源码锚点，交付前才修订对应正文。你也可以从 `architecture-overview.md` 沿链接手动阅读，遇到文档与实现不一致时以当前源码为准，再定向修订知识。

<!--
开发步骤应能由新环境复现，本地通过不等于全部平台已经验证。
-->

## 开发与贡献

先阅读[架构导览](ARCHITECTURE.md)了解依赖方向与设计边界，再按[贡献指南](CONTRIBUTING.md)运行检查。CLI 帮助、交互提示、诊断、开发文档及新创作知识默认使用简体中文。命令名、参数、路径和 JSON 字段保持稳定，便于脚本与工具集成。

Modus 支持 Python 3.11–3.14。开发环境和 CI 使用同一组锁定依赖与质量门禁：

```bash
uv sync --locked --extra test
uv run --locked --extra test pytest
uv run --locked --extra test ruff check .
uv run --locked --extra test ruff format --check .
uv run --locked --extra test mypy
./scripts/wheel-smoke.sh
```

贡献代码时，请把 CLI、Skill、Schema 和 Markdown 合同视为公开接口：行为变更应带有聚焦测试，语言 Provider 缺口应保持可解释降级，平台适配不得绕过统一所有权和卸载语义。架构边界测试会阻止普通运行时依赖一次性初始化分析，并核对发布制品不重新引入旧图数据库或废弃命令。

### License

<!-- NOCA:AllFileLicenseCheck(项目许可声明与根目录协议及包元数据一致) -->
Modus 使用 [MIT License](LICENSE)。
