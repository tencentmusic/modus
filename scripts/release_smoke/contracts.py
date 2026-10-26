"""Declarative policy for Modus release artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ReleaseCheckError(RuntimeError):
    """A release contract failed with a message intended for maintainers."""


class ArtifactKind(StrEnum):
    """Distribution formats understood by the release gate."""

    WHEEL = "wheel"
    SDIST = "source distribution"


# 归档读取器负责路径安全与格式解析，核验器只消费规范化清单。
# 成员集合不包含格式特有的包根，因此 wheel 与源码包可共享规则。
@dataclass(frozen=True, slots=True)
class ArtifactInventory:
    """Normalized contents and optional metadata for one release artifact."""

    path: Path
    kind: ArtifactKind
    members: frozenset[str]
    workflow_root: str
    metadata: str | None = None
    entry_points: str | None = None


# 只有所有静态发布契约通过后才创建成功结果。
@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    """Successful archive verification, independent of terminal rendering."""

    path: Path
    member_count: int
    size_bytes: int
    workflow_count: int


# 运行时计数来自实际加载的安装包，而非仓库源码目录。
@dataclass(frozen=True, slots=True)
class RuntimeVerification:
    """Successful installed-wheel verification and its public surface counts."""

    workflow_count: int
    platform_count: int


# 边界清单选择各能力的必要文件，不枚举全部内部实现。
# 内部重构可增减文件，但不能让发布产物丢失整项能力。
@dataclass(frozen=True, slots=True)
class ArchitectureBoundary:
    """Files that prove one architectural capability reached the artifact."""

    name: str
    members: frozenset[str]

    # 源码包从 src 布局读取模块；构建生成的资源另有源码来源。
    # 因此不能简单要求源码包拥有 wheel 的全部生成路径。
    def as_source_boundary(self) -> ArchitectureBoundary:
        """Map package members to source, omitting generated wheel resources."""

        return ArchitectureBoundary(
            name=self.name,
            members=frozenset(
                f"src/{member}"
                for member in self.members
                if not member.startswith("modus/_bundled/")
            ),
        )


# 前缀、片段与后缀各表达一种排除范围，调用方无需组合正则。
# 策略只判定归档成员，不接触实际文件系统。
@dataclass(frozen=True, slots=True)
class ExclusionPolicy:
    """Path patterns that must never cross a public archive boundary."""

    prefixes: tuple[str, ...] = ()
    fragments: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()

    def excludes(self, member: str) -> bool:
        return (
            member.startswith(self.prefixes)
            or any(fragment in member for fragment in self.fragments)
            or member.endswith(self.suffixes)
        )


# 公开工作流和平台集合属于发布契约，新增入口需同步验收。
# 元数据断言同时保护包名、许可证声明和最低 Python 版本。
WORKFLOW_NAMES = frozenset(
    {
        "using-modus",
        "modus-init",
        "modus-reinit",
        "modus-update-knowledge",
        "modus-sync-knowledge",
    }
)
COMMAND_NAMES = frozenset({"init", "reinit", "update-knowledge"})
PLATFORM_NAMES = frozenset({"claude", "codebuddy", "codex", "cursor"})
WHEEL_METADATA_HEADERS = (
    ("Description-Content-Type", "text/markdown"),
    ("License-Expression", "MIT"),
    ("Name", "openmodus"),
    ("Requires-Python", ">=3.11"),
)
CONSOLE_SCRIPT = ("modus", "modus.cli:main")
FORBIDDEN_DEPENDENCIES = frozenset({"tomli"})


def _boundary(name: str, *members: str) -> ArchitectureBoundary:
    return ArchitectureBoundary(name, frozenset(members))


# Each group is a small set of architectural witnesses, not an exhaustive file
# manifest. A failure therefore identifies the capability missing from a build
# while ordinary internal refactors remain cheap to review.
PACKAGE_BOUNDARIES = (
    _boundary(
        "public command surface",
        "modus/__init__.py",
        "modus/__main__.py",
        "modus/cli.py",
        "modus/cli_commands/initialize.py",
        "modus/cli_commands/analysis.py",
        "modus/cli_commands/common.py",
        "modus/cli_commands/presentation.py",
        "modus/cli_commands/analysis_display.py",
        "modus/display_labels.py",
        "modus/platforms/display.py",
        "modus/commands/install_state.py",
    ),
    _boundary(
        "knowledge orchestration",
        "modus/hooks/bootstrap.py",
        "modus/knowledge_update.py",
        "modus/orchestrator/context_resolver.py",
        "modus/paths.py",
        "modus/knowledge_write_session.py",
    ),
    _boundary(
        "machine lifecycle",
        "modus/machine/api.py",
        "modus/machine/errors.py",
        "modus/machine/pipeline.py",
        "modus/machine/corpus/contracts.py",
        "modus/machine/corpus/lifecycle.py",
        "modus/machine/facts/contracts.py",
        "modus/machine/facts/lifecycle.py",
        "modus/machine/resolution/contracts.py",
        "modus/machine/resolution/lifecycle.py",
        "modus/machine/resolution/method_graph.py",
        "modus/machine/resolution/topology_validation.py",
        "modus/machine/capability/contracts.py",
        "modus/machine/capability/composition_model.py",
        "modus/machine/capability/lifecycle.py",
        "modus/machine/capability/traversal.py",
        "modus/machine/projection/contracts.py",
        "modus/machine/projection/lifecycle.py",
        "modus/machine/packet/contracts.py",
        "modus/machine/packet/lifecycle.py",
        "modus/machine/store/bundle.py",
        "modus/machine/store/bundle_catalogs.py",
        "modus/machine/store/catalog.py",
    ),
    _boundary(
        "machine extension registry and providers",
        "modus/machine/facts/compiler/process.py",
        "modus/machine/facts/build_contracts.py",
        "modus/machine/facts/build_support.py",
        "modus/machine/facts/build_resolvers/cpp_resolver.py",
        "modus/machine/facts/build_resolvers/go_resolver.py",
        "modus/machine/facts/build_resolvers/java_resolver.py",
        "modus/machine/facts/build_resolvers/python_resolver.py",
        "modus/machine/facts/build_resolvers/typescript_resolver.py",
        "modus/machine/facts/extension_registry.py",
        "modus/machine/facts/native_objc.py",
        "modus/machine/facts/native_swift.py",
        "modus/machine/facts/native_cpp.py",
        "modus/machine/facts/native_kotlin.py",
        "modus/machine/facts/frontend.py",
        "modus/machine/facts/frontend_frameworks.py",
        "modus/machine/facts/frontend_routes.py",
        "modus/machine/facts/provider_assets/ModusJavaAnalyzer.java",
        "modus/machine/facts/provider_assets/modus_go_analyzer.go",
        "modus/machine/facts/provider_assets/modus_typescript_analyzer.cjs",
        "modus/machine/facts/semantic_providers.py",
    ),
    _boundary(
        "retrieval pipeline",
        "modus/retrieval/pipeline.py",
        "modus/retrieval/runtime.py",
        "modus/retrieval/stages/lexical.py",
        "modus/retrieval/stages/selection.py",
    ),
    _boundary(
        "scaffolding and resources",
        "modus/_bundled/schemas/module-meta.schema.yaml",
        "modus/_bundled/schemas/machine/analysis-receipt.schema.json",
        "modus/_bundled/schemas/machine/authoring-context-packet.schema.json",
        "modus/_bundled/schemas/machine/capability-slice.schema.json",
        "modus/_bundled/schemas/machine/evidence-page.schema.json",
        "modus/machine/language-registry.json",
        "modus/py.typed",
        "modus/scaffold/README.md",
        "modus/scaffold/catalog.py",
        "modus/scaffold/project.py",
        "modus/scaffold/templates/README.md",
        "modus/scaffold/writer.py",
    ),
)

# 源码包应保留贡献、架构、测试与构建入口，支持接手维护。
# 这些文件不需要进入运行时 wheel。
SDIST_ROOT_BOUNDARY = _boundary(
    "source project",
    "LICENSE",
    "README.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "tests/test_documented_cli.py",
    "scripts/package_smoke.py",
    "READMEs/README.en.md",
    "docs/knowledge-lifecycle-boundary.md",
    "docs/authoring-contract.md",
    "pyproject.toml",
    "schemas/module-meta.schema.yaml",
    "uv.lock",
)
SDIST_PACKAGE_BOUNDARIES = tuple(boundary.as_source_boundary() for boundary in PACKAGE_BOUNDARIES)

WHEEL_WORKFLOW_ROOT = "modus/scaffold/templates/skills/"
SDIST_WORKFLOW_ROOT = "src/modus/scaffold/templates/skills/"

SDIST_EXCLUSIONS = ExclusionPolicy(
    prefixes=("exports/", "third_party/"),
)
# 退役接口不能因构建目录残留重新进入公开产物。
# 公共排除策略同时应用于两种发行格式。
PUBLIC_ARCHIVE_EXCLUSIONS = ExclusionPolicy(
    prefixes=("third_party/", "modus/licenses/", "src/modus/licenses/"),
    fragments=(
        "dashboard",
        "/planflow/",
        "/scaffold/templates/commands/plan.md",
        "/scaffold/templates/skills/modus-plan/",
        "/practice/",
        "/vendor/",
        "/modus/graph/",
        "/commands/graph_",
        "/init_analysis/build_progress.py",
        "/init_analysis/contract_links.py",
        "/init_analysis/diff.py",
        "/init_analysis/graph_model.py",
        "/init_analysis/incremental.py",
        "/init_analysis/outputs.py",
        "/init_analysis/query/",
    ),
    suffixes=(
        "frontend_knowledge.py",
        "machine_store.py",
        "migrations.py",
        "project_profile.py",
        "protocols.py",
        "scope_store.py",
        "staleness.py",
    ),
)
