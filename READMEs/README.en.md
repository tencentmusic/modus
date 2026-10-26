<div align="center"> <!-- NOCA:LowCommentRatio(读者文档以可见正文承载说明，代码注释率不适用于 Markdown) -->

# Modus

**Take coding beyond code**

Already installed? Run `modus update`

<p>
  <strong>Coding-agent platforms</strong><br />
  <img src="https://img.shields.io/badge/Claude_Code-Supported-D97757" alt="Claude Code Agent Skills" />
  <img src="https://img.shields.io/badge/Codex-Supported-111111" alt="Codex Agent Skills" />
  <img src="https://img.shields.io/badge/Cursor-Supported-111111" alt="Cursor Skills and Rules" />
  <img src="https://img.shields.io/badge/CodeBuddy-Supported-1F6FEB" alt="CodeBuddy Skills and Commands" />
</p>

<p>
  <strong>Language capabilities · compiler and type-system enhancement</strong><br />
  <img src="https://img.shields.io/badge/Python-semantic-3776AB?logo=python&logoColor=white" alt="Python semantic provider" />
  <img src="https://img.shields.io/badge/Java-semantic-ED8B00?logo=openjdk&logoColor=white" alt="Java semantic provider" />
  <img src="https://img.shields.io/badge/Go-semantic-00ADD8?logo=go&logoColor=white" alt="Go semantic provider" />
  <img src="https://img.shields.io/badge/C%2FC%2B%2B-semantic-00599C?logo=cplusplus&logoColor=white" alt="C and C++ semantic provider" />
  <img src="https://img.shields.io/badge/TypeScript-semantic-3178C6?logo=typescript&logoColor=white" alt="TypeScript semantic provider" />
  <br />
  <sub>Structural extraction also covers JavaScript, Kotlin, PHP, C#/.NET, Rust, Astro/Svelte, and more. <a href="#language-capabilities">See the full scope</a></sub>
</p>

[![PyPI](https://img.shields.io/pypi/v/openmodus?label=PyPI&color=3775A9)](https://pypi.org/project/openmodus/)
![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.14-3776AB?logo=python&logoColor=white)
<!-- NOCA:AllFileLicenseCheck(项目许可声明与根目录协议及包元数据一致) -->
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)

[简体中文](../README.md) · [**English**](README.en.md)

</div>

---

[Core features](#core-features) · [Quick start](#quick-start) · [Why Modus](#why-modus) · [Technical principles](#technical-principles) · [User guide](#user-guide) · [Contributing](#development-and-contribution)

**New to a project and changing a critical flow? Where are the rules and code, and how will you verify the result?**

Modus organizes source and business material into verifiable project knowledge. It helps coding agents read source, business material, and team constraints together, record business scenarios, design tradeoffs, and change boundaries as verifiable Markdown in the repository, then use that knowledge progressively during later coding tasks and update it when needed.

> The open-source release currently covers Modus's project knowledge base. Its broader AI workflow solution is also evolving, and we will share updates as it develops.

---

<!--
Keep product claims aligned with the executable command surface.
-->

## Core features

Modus treats project knowledge as a maintainable engineering asset: local analysis provides leads, agents and people confirm business meaning, Markdown carries durable conclusions, and everyday tasks use and revise them as needed.

<!--
The evidence map describes observations, not completed business authoring.
-->

### Build a project map from evidence

During initialization, local analysis extracts bounded evidence from source, build context, and available toolchains to locate entry points, relationships, and key behavior. The agent then rereads source, tests, configuration, and business material to confirm system architecture, domain boundaries, and real scenarios, recording its conclusions in the system overview, Domain, Module, and topic documents.

<!--
Context budgets and explicit degradation qualify every completeness claim.
-->

### Assemble task context progressively

When development, debugging, or review requires project facts, the agent moves from the system overview into relevant Domains, Modules, and scenarios, reads team constraints as needed, and checks current source. Retrieval organizes knowledge and implementation excerpts around the question and makes evidence gaps explicit. Everyday use reads repository Markdown and current source directly without rerunning initialization analysis.

<!--
The review workflow uses Markdown and version control, without a separate knowledge service.
-->

### Bring knowledge into code review

Durable knowledge lives as Markdown beside code. Stable Domain and Module identities, knowledge links, and structured source anchors form a traceable path. Human-maintained business knowledge and team constraints have clear ownership; integrity checks cover structure, links, and anchors, giving knowledge changes a clear review boundary.

<!--
Preserve the distinction between durable meaning and transient implementation details.
-->

### Maintain knowledge as durable meaning changes

After a code change, the agent checks whether responsibilities, contracts, rules, state, dependencies, resources, or source anchors changed durably. If so, it revises the affected prose where the fact is defined and updates related navigation and references. New business material and local facts can also be incorporated through targeted updates.

## Quick start

Install the CLI from source, connect a target repository, then have your agent author its first project knowledge from evidence. The CLI handles host integration; reviewed Markdown is the durable result kept in the repository.

<!--
Keep installation examples aligned with distribution metadata and the command name.
-->

### 1. Install the CLI

From the Modus source repository root (containing `pyproject.toml`), install the CLI with [`uv`](https://docs.astral.sh/uv/) (Python 3.11–3.14 required):

```bash
uv tool install .
```

You can also install the published package from PyPI with `uv tool install openmodus`. When developing Modus, `uv tool install --editable .` makes source changes take effect directly. The installed command is `modus` in either case. See [Installation and connection options](#installation-and-connection-options) for other methods and index configuration.

<!--
Installation owns framework assets; user-authored knowledge has a separate owner.
-->

### 2. Connect a project

Enter the repository where you want to use Modus:

```bash
cd path/to/your-project
modus init
```

In an interactive terminal, select Claude Code, Codex, Cursor, or CodeBuddy. The CLI installs platform-neutral Skills and commands into the project, projects them through the selected host adapter, and records ownership of managed files. See [Installation and connection options](#installation-and-connection-options) for scripted and multi-platform setup and installation checks.

<!--
Document initialization and ongoing maintenance as separate entry points.
-->

### 3. Author project knowledge

Open the project in your selected coding agent and invoke this workflow in the conversation:

```text
/modus-init
```

This is the knowledge-authoring workflow, distinct from the `modus init` Shell command. The agent uses local analysis to locate leads, checks current source, tests, configuration, and any business material you provide, then authors knowledge after the project boundaries are confirmed. If a host exposes Skills by name instead of slash commands, ask it to “use modus-init to initialize knowledge for this project.”

When the workflow finishes, `.modus/` holds platform-neutral integration assets, `modus/knowledge/` holds Markdown knowledge reviewed alongside code, and `modus/.cache/` holds disposable initialization evidence. Everyday tasks read the relevant knowledge and current source without rerunning initialization analysis. See the [User guide](#user-guide) for first-run review and later maintenance.

## Why Modus

<!--
Capability tables must retain unsupported-provider and degraded-mode limits.
-->

### What you get

When taking over a project, finding a code entry point is only the start. You also need to know why a rule exists, what counts as completion, how failures are recovered, and which boundaries a change must preserve. Modus keeps durable conclusions verified against source and available business material in the repository, so later tasks can build on that understanding while checking it against current source.

| What you need | What Modus changes |
| --- | --- |
| Take over a project | Follow the system overview through Domains and Modules to relevant scenarios, responsibilities, key decisions, and verification entry points. Later tasks can follow the same route instead of rediscovering it. |
| Decide how to change it | Read business rules, interface contracts, state and failure recovery, and team constraints around the task, then check current source to confirm the change site and impact. |
| Review conclusions | Review repository Markdown alongside code diffs. Links and source anchors help trace conclusions; mechanical checks validate paths, links, and anchors. |
| Maintain knowledge | First decide whether a code change affects durable meaning. If it does, revise the original definition and related references instead of appending notes for every edit. |

The knowledge is readable, editable, and removable Markdown in the repository. Initialization analysis produces bounded local evidence for the current authoring run; ordinary tasks use current source and reviewed prose directly, without a remote knowledge service, vector database, or persistent source graph.

### Platforms and languages

Modus supports Python 3.11–3.14, and the installed command is `modus`. The supported hosts and language evidence levels are listed below.

<!--
Maintain platform claims alongside installed-artifact acceptance checks.
-->

#### Coding-agent platforms

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-Agent_Skills-D97757" alt="Claude Code Agent Skills" />
  <img src="https://img.shields.io/badge/Codex-Agent_Skills-111111" alt="Codex Agent Skills" />
  <img src="https://img.shields.io/badge/Cursor-Skills_%26_Rules-111111" alt="Cursor Skills and Rules" />
  <img src="https://img.shields.io/badge/CodeBuddy-Skills_%26_Commands-1F6FEB" alt="CodeBuddy Skills and Commands" />
</p>

Each adapter declares its Skill directory, resident instructions, and Hook layout. The shared installer owns deterministic writes, the ownership manifest, upgrade reconciliation, and safe uninstall behavior.

<!--
Language recognition, structural extraction and compiler evidence have distinct precision.
-->

#### Language capabilities

Evidence depth is explicit. Recognizing a file extension is never presented as complete semantic support.

**Compiler or type-system enhancement**

<p align="center">
  <img src="https://img.shields.io/badge/Python-semantic-3776AB?logo=python&logoColor=white" alt="Python semantic provider" />
  <img src="https://img.shields.io/badge/Java-semantic-ED8B00?logo=openjdk&logoColor=white" alt="Java semantic provider" />
  <img src="https://img.shields.io/badge/Go-semantic-00ADD8?logo=go&logoColor=white" alt="Go semantic provider" />
  <img src="https://img.shields.io/badge/C%2FC%2B%2B-semantic-00599C?logo=cplusplus&logoColor=white" alt="C and C++ semantic provider" />
  <img src="https://img.shields.io/badge/TypeScript-semantic-3178C6?logo=typescript&logoColor=white" alt="TypeScript semantic provider" />
</p>

Python, Java, Go, C/C++, and TypeScript can add local compiler or type-checker observations to structural evidence. An unavailable toolchain lowers only the affected evidence; it does not block the whole project.

**Dedicated structural extraction**

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

Objective-C, Objective-C++, and Swift have dedicated structural extraction, including OC selectors/categories/protocols, Swift extensions and argument labels, and content-based `.h` dispatch. Objective-C++ combines separate OC and C++ observations with explicit partial coverage. Kotlin adds packages, imports, extension functions, and Compose trailing closures; C++ adds namespaces, header declarations, and template calls. Ordinary source retrieval also includes `.m`, `.mm`, `.hh`, and `.hxx`.

These observations are not Xcode, Swift, or Kotlin compiler semantics. They do not automatically resolve every build variant, macro expansion, or IDL/JNI bridge. Native and Kotlin evidence guides direct agents to verify generated origins, registrations, Action/State flows, and client lifecycles; missing relations remain candidate or unresolved evidence.

Other registered source, template, configuration, data-definition, and document formats still enter a bounded generic-evidence path. Modus preserves coverage gaps instead of interpreting a missing provider as proof that the repository has no business behavior.

### Why choose Modus

Coding agents can quickly find files and explain local implementation. Keeping that understanding useful across people and tasks raises three problems:

1. **Discoveries are hard to reuse.** Entry points, call relationships, rules, and verification paths are derived in one session and reconstructed in the next.
2. **Structure alone cannot explain the business.** Imports, call edges, and directory clusters point to relevant code; business boundaries, design rationale, and recovery policies require judgment grounded in source, tests, and material.
3. **Knowledge drifts as code changes.** Documents without ownership, traceability, and a maintenance trigger can still look credible after implementation changes.

Modus addresses these problems through an inspectable knowledge-production and maintenance path:

- **Separate evidence from judgment.** Local analysis identifies entry points and relationships, marking confidence and gaps. Agents and people record conclusions only after checking current source, tests, configuration, and available material. Gaps remain explicit rather than being filled by guesswork.
- **Organize knowledge around stable boundaries.** The system overview provides navigation, Domains define business capability boundaries, Modules explain scenarios and responsibilities, and topic documents hold the primary definitions of interfaces, objects, rules, state, dependencies, and infrastructure. Human-maintained business knowledge and team constraints have clear ownership.
- **Keep authoring cost out of everyday use.** The init/reinit graph and evidence bundle serve the current authoring run. Later tasks progressively read reviewed Markdown and current source; retrieval also reports coverage gaps.
- **Maintain knowledge in the engineering workflow.** After a change, check whether durable responsibilities, contracts, rules, or source anchors changed. Revise only affected definitions, using link and anchor checks to preserve traceability.

## Technical principles

### From evidence to knowledge

Modus keeps one-off machine analysis separate from durable knowledge. `init/reinit` builds verifiable code evidence for the current authoring run; agents and people interpret that evidence together with business material and current source. Ordinary tasks consume reviewed Markdown and return to the implementation whenever a conclusion must be verified.

```text
[One-off evidence production: init / reinit]
  source + build files + tests/configuration
    → Source Snapshot (freeze this run's repository inputs)
    → CST / structural IR / project binding
    → optional compiler and type-system observations
    → temporary evidence graph → explicit semantic reconciliation
    → bounded views of entries, relations, effects, and resources
    → deterministic, bounded JSON bundle ───────────────┐
                                                        │
[Knowledge authoring]                                  ▼
  business material + team constraints ─→ agent + human judgment ← current source
                                                        │
                                                        ▼
                                      reviewable, traceable Markdown knowledge
                                                        │
[Continuous use and maintenance]                        │
  ordinary task ─→ progressive routing and retrieval ───┤→ act after source check
  code change ─→ durable-knowledge impact decision ─→ minimal revision if needed
```

These are three decoupled phases. Evidence production runs only during `init/reinit`; authoring never promotes a machine relationship directly into a business conclusion; continuous use and maintenance neither rebuild initialization analysis nor create documentation churn for every code edit.

The full lifecycle deliberately protects three boundaries:

- **Evidence guides; it does not decide.** `exact`, `candidate`, `heuristic`, and `unresolved` remain distinct. Conflicts become diagnostics, and an agent must reread source, tests, configuration, or supplied material before stating a conclusion.
- **Analysis state is not the durable product.** The temporary graph is released after projection, and the JSON bundle lives in disposable cache for the current authoring run only. Ordinary tasks never read it; only reviewed Markdown becomes lasting knowledge.
- **Current source remains authoritative.** Snapshot drift or an integrity failure stops the current analysis, while a local parser or provider gap lowers only the affected evidence. Ordinary use and incremental maintenance read prose together with current source instead of silently falling back to an old conclusion.

Consider a project where an order callback's retry behavior needs changing. Within the analyzed coverage, initialization evidence can point to the callback entry point, state writes, and relevant source. The author must still reread implementation, tests, and available business agreements to decide what a duplicate notification should return. Once confirmed, idempotency conditions, failure recovery, and verification entry points belong in the Module and the rule and state topics according to their responsibilities. A later developer follows the Domain and Module to those conclusions, checks current source, and makes the change. If the retry contract or state transitions change, they revise the primary definitions and references in place; an internal refactor needs no added knowledge.

<!--
Translation must preserve stable identities and protocol field names.
-->

### Knowledge model

After setup, `.modus/` holds the host control plane, `modus/knowledge/` holds durable knowledge, and `modus/.cache/` holds disposable analysis state. The knowledge model is not a document tree grouped by file type. It combines four task-oriented views. They are perspectives for reading and modeling a project, not physical layers that every repository must reproduce.

| View | Question it answers | Primary carriers |
| --- | --- | --- |
| Business | Why is a change needed, and where do its concepts, scenarios, and experience belong? | Domain routing plus concepts, scenarios, and experience under `business/` |
| Architecture | What are the capability boundaries, and how do runtime units and modules collaborate? | The root overview, Domain boundaries, state, and downstream handoffs |
| System | How does one capability work, and how do contracts, objects, rules, and resources produce its result? | Module scenario guides and the six reusable topic documents |
| Engineering constraints | What must not change casually, and how is a change proved safe? | `constraint/`, rule and infrastructure topics, and Module implementation and verification entry points |

```text
modus/knowledge/
├── architecture-overview.md          project, runtime layers, capability relations, navigation
├── constraint/
│   ├── global-standard.md             global constraints
│   └── team-standard.md               architecture, change, and verification standards
└── domain/<domain>/
    ├── SKILL.md                       Domain routing and capability overview
    └── references/
        ├── modules/<module>.md        responsibilities, scenarios, tradeoffs, verification
        ├── api.md                     contract overview and stable navigation
        ├── api/                       optional semantic groups, never one shard per contract
        ├── object.md                  object overview and stable navigation
        ├── object/                    optional semantic groups, never one shard per DTO/class
        ├── rule.md                    rules, constraints, exceptions, and evidence
        ├── state_machine.md           state, flows, failures, and recovery
        ├── downstream.md              dependencies, events, and system handoffs
        ├── infrastructure.md          storage, configuration, processes, runtime resources
        └── business/                  human-owned business knowledge
            ├── index.md               business-knowledge entry point
            ├── meta/                  terminology, concepts, objects, measures, rules
            ├── experience/            decisions, practice, retrospectives, applicability
            └── scenario/              actors, flows, outcomes, and exceptional scenarios
```

Each carrier has a stable responsibility. A Domain is a capability and ownership boundary whose `SKILL.md` provides routing. A Module organizes the causal story around responsibilities and real scenarios. The six topic documents own the complete definitions of reusable facts, while the root overview connects system-wide capabilities and runtime architecture. Frontends, backends, CLIs, libraries, workers, data jobs, infrastructure, and plugins share this contract while expanding only the capability blocks that actually exist.

**Structure routes; prose explains.** Stable identities, source anchors, and precise links let an agent move progressively from the root overview into a Domain, Module, and relevant topics. Markdown explains business outcomes, decisions, completion boundaries, failure and recovery, and design tradeoffs. Method-level source evidence belongs only in Modules and topics; the root overview and Domain remain stable routers. One document owns the full definition of a fact; the rest link to it, so the entire knowledge base never has to be loaded at once.

Everyday retrieval builds a temporary index from current Markdown. It first follows links from the root overview, Domains, and Modules to select documents to read, then combines structural signals with BM25 term matching to rank results. Inferred routes adjust relevance without excluding other potentially relevant Modules. Matched sections are reassembled as complete entries so conditions, exceptions, and recovery notes stay together. Current source and team constraints share the same time and output budget. Results identify missing evidence types and where to continue reading after a truncated entry, helping the developer decide what to check rather than treating retrieval as proof.

Modus favors knowledge that is **highly reusable, high risk, or hard to infer** instead of generating a summary for every function. Public contracts, core objects, state transitions, downstream handoffs, compatibility boundaries, and verification standards merit durable treatment; routine implementation detail that is cheap to recover stays in source. `business/` and `constraint/` are human-owned by default, so automation cannot overwrite organizational knowledge with scan output. Changes to generated knowledge are guarded by read-time hashes and checked for path identity, link, and anchor integrity.

<!--
Architecture diagrams follow real dependencies, ownership and failure semantics.
-->

### Code architecture

Modus follows the boundaries it advocates: the entry surface stays narrow, application orchestration is separate from retrieval algorithms, declarative adapters contain host differences, and durable knowledge uses a different directory and write contract from disposable analysis state.

| Subsystem | Responsibility and boundary |
| --- | --- |
| `modus.machine` | The machine layer: freezes inputs, observes facts, resolves relationships, and publishes an immutable, bounded evidence bundle for the current init/reinit run along the N1–N6 lifecycle (corpus → facts → resolution → capability → projection → packet). |
| `modus.orchestrator` | Composes preflight, task context, and knowledge-impact candidates without owning retrieval algorithms or knowledge writes. |
| `modus.retrieval` | Progressively selects prose, current source, and constraints under one time and output budget, reporting partial results explicitly. |
| `modus.platforms` / `modus.hooks` | Projects canonical Skills into four hosts while isolating host directories, resident instructions, and session Hooks. |
| `modus.scaffold` | Packages neutral templates and owns deterministic project installation, upgrade reconciliation, ownership records, and safe uninstall. |
| `knowledge_verification` / `knowledge_write_session` | Separate mechanical integrity checks, human ownership, compare-and-swap writes, and atomic publication. |

The machine layer moves in one direction: frozen inputs, fact observation, relationship resolution, capability composition, authoring projection, and evidence packaging. Projection and packaging consume prior results rather than observing source again to invent missing facts. If an optional compiler or local parser fails, available leads remain, with their affected scope marked. Projected capability boundaries and behavior paths are candidates for the author to verify, not business conclusions.

An evidence bundle is published only after full validation. If source changes during analysis or evidence integrity fails, this run's machine output cannot be treated as verified fact. A failed build does not replace an existing complete bundle, and the current authoring run does not pass off that older bundle as current evidence. Knowledge prose is written under ownership and read-time content protection, then checked for structure, links, and source anchors. This gives local evidence gaps, whole-run analysis failure, and prose write conflicts distinct handling boundaries while letting developers return to current source and available material.

## User guide

The [Quick start](#quick-start) gives the shortest path. This section adds connection checks, workflow selection, and everyday maintenance. `modus` in a terminal manages installation and status; `/modus-*` in an agent authors and revises knowledge.

### Installation and connection options

The public PyPI distribution is named `openmodus`; no private index is required. You can also use `pipx install openmodus`. If your custom index does not proxy public PyPI, run `uv tool install --default-index https://pypi.org/simple openmodus`.

`modus init` selects a host in an interactive terminal. For scripts or noninteractive terminals, specify one with `modus init --platform codex`, repeat `--platform` for several hosts, or use `modus init --all-platforms`. A first noninteractive run without a platform selection connects all supported hosts. The same neutral Skill contracts are projected into each selected host.

After connecting, run `modus status` in the target repository. The output `Installation: installed` means the project assets are in place. The CLI places starter files in `modus/knowledge/`, but you still need `/modus-init` in an agent to author the prose. The knowledge document count reported by `status` includes starter files and does not by itself show that authoring is complete.

<!--
Keep command examples synchronized with registered options and exit behavior.
-->

### CLI commands

The CLI installs, maintains, and inspects Modus. Run `modus help` for the complete surface in the installed version.

| Command | Purpose |
| --- | --- |
| `modus init` | Install neutral project assets and project them into the selected coding-agent hosts. |
| `modus update` | Update the local CLI and reconcile Modus-managed Skills and Hooks in the current project. |
| `modus help` | Show CLI commands, explicit knowledge workflows, and automatic knowledge capabilities. |
| `modus uninstall` | Show a plan, then remove the current project's managed assets and the personal CLI after interactive confirmation by default; authored knowledge is retained. |
| `modus status` | Read installation, version, and authored-knowledge status without reading initialization caches. |

Useful read-only checks and operation previews:

```bash
modus status
modus status --json
modus help /modus-init
modus update --dry-run
modus uninstall --dry-run
modus uninstall --project --delete-knowledge --dry-run
modus uninstall --person --dry-run
```

`modus update` updates both the local CLI and managed assets in the current project by default. Use `--project` to update only the project or `--person` to update only the local CLI. `modus uninstall` similarly targets the current project and personal CLI by default. If the current directory has no project-level installation, it skips that scope and continues with the personal CLI. Use `--project` or `--person` to select one scope; `--all` remains a compatibility alias for the bare command. Project knowledge is retained unless `--delete-knowledge` is specified. Both update and uninstall support `--dry-run` to preview the plan.

### Explicit knowledge workflows

Use these entry points in an AI coding environment, not in a Shell.

| Workflow | When to use it |
| --- | --- |
| `/modus-init` | Create complete project knowledge from current code, build context, and material; automatically behaves as reinit when a formal Scope exists. |
| `/modus-reinit` | Reuse stable Domain and Module identities while fully reviewing and reorganizing existing prose. |
| `/modus-update-knowledge` | Update knowledge affected by explicit material or local facts without rerunning repository-wide analysis. |

On the first `/modus-init` run, you can give the agent known project boundaries, business material, and team constraints. The agent first organizes the Domain and Module scope for confirmation, then rereads source domain by domain and writes the prose. Afterward, start at `modus/knowledge/architecture-overview.md`, follow a Domain's `SKILL.md` into a relevant Module, and check that one real scenario's rules, failure recovery, and verification entry points are grounded in current source. Review the new prose as you would code.

For existing knowledge, use `/modus-reinit` when overall boundaries change or a full review is needed. To incorporate specific new material or local facts, use `/modus-update-knowledge` and provide the material path and affected scope. Ordinary coding tasks do not need these authoring workflows rerun.

### Automatic knowledge capabilities

- `using-modus` progressively loads knowledge only when a task needs project facts, then decides whether a modifying task caused durable knowledge impact.
- `modus-sync-knowledge` performs the smallest in-place, verifiable prose revision only after a positive impact decision.

These are agent lifecycle capabilities, not extra workflows that users must remember and invoke on every task.

In everyday use, give the agent a concrete task, such as “Check the order callback's duplicate-notification and retry rules, find the implementation and verification entry points, and fix the confirmed issue.” The agent reads relevant knowledge through the overview, Domain, and Module as needed, then checks current source. It revises the corresponding prose before delivery only if the change affects a durable contract, rule, state, or source anchor. You can also follow links from `architecture-overview.md` yourself; if documentation and implementation disagree, use current source to verify the fact and update the knowledge accordingly.

<!--
Reproducible local checks do not imply that every supported platform was exercised.
-->

## Development and contribution

The CLI, maintainer guides, and newly authored knowledge default to Simplified Chinese. Commands, options, paths, and machine-readable fields remain stable. Users can explicitly request another language for authored prose.

Start with the [architecture reading guide](../ARCHITECTURE.md) for the dependency map and design boundaries, then [CONTRIBUTING.md](../CONTRIBUTING.md) for conventions and release checks.

Modus supports Python 3.11–3.14. Local development and CI use the same locked dependencies and quality gates:

```bash
uv sync --locked --extra test
uv run --locked --extra test pytest
uv run --locked --extra test ruff check .
uv run --locked --extra test ruff format --check .
uv run --locked --extra test mypy
./scripts/wheel-smoke.sh
```

When contributing, treat the CLI, Skills, schemas, and Markdown contracts as public interfaces. Behavioral changes should include focused tests, language-provider gaps must degrade explicitly, and host adapters must preserve shared ownership and uninstall semantics. Architecture-boundary tests prevent ordinary runtime code from depending on disposable initialization analysis and ensure release artifacts do not reintroduce legacy graph databases or removed commands.

### License

<!-- NOCA:AllFileLicenseCheck(项目许可声明与根目录协议及包元数据一致) -->
Modus is available under the [MIT License](../LICENSE).
