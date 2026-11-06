"""Compose the neutral Modus distribution into a user project.

The scaffold is a small ports-and-adapters boundary:

* :mod:`modus.scaffold.catalog` validates the packaged command and skill source;
* :mod:`modus.scaffold.writer` applies explicit file-ownership policies; and
* this module coordinates project data, host adapters, and re-initialization.

The result is two canonical trees: ``.modus/`` contains the platform-neutral
control plane, while ``modus/`` contains canonical knowledge and disposable
cache state only. Platform adapters then project the neutral surface to each host.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, cast

from .. import __version__
from ..artifacts_io import CorruptArtifactError
from ..config import (
    VALID_PROJECT_KINDS,
    ModusConfig,
    reconcile_optional_config,
)
from ..manifest import Manifest
from ..paths import ModusPaths
from ..platforms import Command, PlatformAdapter, Skill, get_adapters
from ..surface import CORE_SKILLS, EXPLICIT_COMMANDS
from ..versioning import bump_kind
from .catalog import TEMPLATES_DIR, TemplateCatalog
from .writer import AssetOwnership, ScaffoldAsset, ScaffoldWriter

ProjectKind = Literal["project", "workspace"]


class ScaffoldStateError(ValueError):
    """Existing installation state cannot be reconciled safely."""


@dataclass(frozen=True, slots=True)
class ScaffoldRequest:
    """Validated inputs for one deterministic scaffold render."""

    platforms: tuple[str, ...]
    write_manifest: bool = True
    kind: ProjectKind = "project"
    workspace_members: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in VALID_PROJECT_KINDS:
            allowed = ", ".join(sorted(VALID_PROJECT_KINDS))
            raise ValueError(f"kind 可选值为：{allowed}; got {self.kind!r}")


@dataclass(slots=True)
class ProjectScaffolder:
    """Render one request while keeping orchestration separate from I/O policy."""

    paths: ModusPaths
    request: ScaffoldRequest
    catalog: TemplateCatalog = field(default_factory=TemplateCatalog)

    def render(self) -> Manifest:
        """Render or reconcile the requested project scaffold."""

        # Resolve persisted state and adapters before the first write. A current
        # installation renders its desired tree in isolation during reconcile.
        adapters = get_adapters(list(self.request.platforms))
        installed = _read_installed_manifest(self.paths)
        if installed is not None:
            _require_current_framework(installed)
            return _reconcile_current_install(
                self.paths,
                installed,
                request=self.request,
                catalog=self.catalog,
            )

        # The complete packaged distribution is validated before publication.
        commands = self.catalog.load_commands(EXPLICIT_COMMANDS)
        skills = self.catalog.load_skills(CORE_SKILLS)
        neutral_assets = self._neutral_assets(commands, skills)
        knowledge_assets = self._knowledge_assets()

        manifest = Manifest(
            framework_version=__version__,
            platforms=list(self.request.platforms),
        )
        writer = ScaffoldWriter(self.paths, manifest)
        writer.publish_all([*neutral_assets, *knowledge_assets])
        _prepare_data_tree(self.paths, self.request, writer)
        self._project_platforms(adapters, skills, commands, manifest)

        if self.request.write_manifest:
            manifest.write(self.paths)
        return manifest

    def _neutral_assets(
        self,
        commands: list[Command],
        skills: list[Skill],
    ) -> list[ScaffoldAsset]:
        assets = [
            ScaffoldAsset(
                path=self.paths.relative(self.paths.commands_dir / f"{command.name}.md"),
                content=command.body,
                template=f"commands/{command.name}.md",
            )
            for command in commands
        ]
        for skill in skills:
            assets.append(
                ScaffoldAsset(
                    path=self.paths.relative(self.paths.skills_dir / skill.name / "SKILL.md"),
                    content=skill.body,
                    template=f"skills/{skill.name}/SKILL.md",
                )
            )
            assets.extend(
                ScaffoldAsset(
                    path=self.paths.relative(self.paths.skills_dir / skill.name / relative_path),
                    content=content,
                    template=f"skills/{skill.name}/{relative_path}",
                )
                for relative_path, content in sorted(skill.support_files.items())
            )

        return assets

    def _knowledge_assets(self) -> list[ScaffoldAsset]:
        ownership = (
            AssetOwnership.MANAGED if self.request.kind == "workspace" else AssetOwnership.USER_SEED
        )
        return [
            ScaffoldAsset(
                path=self.paths.relative(target),
                content=self.catalog.read(template),
                template=template,
                ownership=ownership,
            )
            for target, template in _knowledge_templates(
                self.paths,
                kind=self.request.kind,
            ).items()
        ]

    def _project_platforms(
        self,
        adapters: list[PlatformAdapter],
        skills: list[Skill],
        commands: list[Command],
        manifest: Manifest,
    ) -> None:
        for adapter in adapters:
            adapter.project(self.paths, skills, commands, manifest)


def templates_dir() -> Path:
    """Return the packaged template root for diagnostics and tooling."""

    return TEMPLATES_DIR


def load_skills() -> list[Skill]:
    """Load the five canonical skills in authoritative presentation order."""

    return TemplateCatalog().load_skills(CORE_SKILLS)


def load_commands() -> list[Command]:
    """Load explicit public commands in authoritative presentation order."""

    return TemplateCatalog().load_commands(EXPLICIT_COMMANDS)


def scaffold_project(
    root: str | Path,
    platforms: list[str],
    *,
    write_manifest: bool = True,
    kind: str | None = None,
    workspace_members: list[dict] | None = None,
) -> Manifest:
    """Render Modus' canonical assets and platform projections into ``root``.

    Repeated calls at the same framework version reconcile through the guarded
    update engine, preserving user-owned knowledge and hand-edited managed
    files. Framework version transitions remain the responsibility of
    ``modus update``.
    """

    paths = ModusPaths.for_root(root)
    request = ScaffoldRequest(
        platforms=tuple(platforms),
        write_manifest=write_manifest,
        kind=_resolve_kind(paths, kind),
        workspace_members=tuple(dict(member) for member in workspace_members or []),
    )
    return ProjectScaffolder(paths, request).render()


def _resolve_kind(paths: ModusPaths, requested: str | None) -> ProjectKind:
    if requested is None:
        try:
            requested = ModusConfig.read(paths).kind
        except (CorruptArtifactError, OSError, TypeError, ValueError):
            requested = "project"
    if requested not in VALID_PROJECT_KINDS:
        allowed = ", ".join(sorted(VALID_PROJECT_KINDS))
        raise ValueError(f"kind 可选值为：{allowed}; got {requested!r}")
    return cast(ProjectKind, requested)


def _read_installed_manifest(paths: ModusPaths) -> Manifest | None:
    if not paths.manifest_path.exists():
        return None
    try:
        return Manifest.read(paths)
    except Exception as exc:  # noqa: BLE001 - fail closed at the persisted-state boundary
        raise ScaffoldStateError(
            f"无法安全合并已有 Modus 安装：{paths.manifest_path}: {exc}"
        ) from exc


def _require_current_framework(manifest: Manifest) -> None:
    change = bump_kind(manifest.framework_version, __version__)
    if change == "downgrade":
        raise ScaffoldStateError(
            f"拒绝使用旧版本 Modus 框架初始化（{__version__}）覆盖已安装版本 {manifest.framework_version}。请使用不低于项目已安装版本的框架。"
        )
    if change != "none":
        raise ScaffoldStateError(
            f"现有 Modus 资产或数据需要受保护的更新流程（已安装 {manifest.framework_version}, current {__version__}）。"
            "请先运行 `modus update`，再运行 `modus init`。"
        )


def _reconcile_current_install(
    paths: ModusPaths,
    installed: Manifest,
    *,
    request: ScaffoldRequest,
    catalog: TemplateCatalog,
) -> Manifest:
    """Re-run init through the ownership-aware manifest diff used by update."""

    with tempfile.TemporaryDirectory(prefix="modus-init-desired.") as scratch:
        desired_paths = ModusPaths.for_root(scratch)
        desired_request = replace(request, write_manifest=False)
        desired = ProjectScaffolder(desired_paths, desired_request, catalog).render()
        # Lazy import keeps scaffold -> update -> scaffold from becoming a
        # module-import cycle while preserving one reconciliation algorithm.
        from ..commands.update import reconcile_desired_manifest

        report = reconcile_desired_manifest(
            paths,
            installed,
            desired_paths,
            desired,
            preserve_existing_paths=(
                frozenset(
                    paths.relative(target)
                    for target in _knowledge_templates(paths, kind=request.kind)
                )
                if request.kind == "project"
                else frozenset()
            ),
            write_manifest=False,
        )
        next_manifest = report.get("_nextManifest")
        if not isinstance(next_manifest, Manifest):
            raise ScaffoldStateError("更新合并未返回下一份清单")

    _prepare_data_tree(paths, request, ScaffoldWriter(paths, next_manifest))

    if request.write_manifest:
        next_manifest.write(paths)
    return next_manifest


def _knowledge_templates(
    paths: ModusPaths,
    *,
    kind: ProjectKind,
) -> dict[Path, str]:
    """Map data destinations to templates and their distinct ownership policy."""

    if kind == "workspace":
        from ..workspace import workspace_seed_files

        return {target: "knowledge/handbook/SKILL.md" for target in workspace_seed_files(paths)}
    return {
        paths.global_standard: "knowledge/constraint/global-standard.md",
        paths.team_standard: "knowledge/constraint/team-standard.md",
    }


def _reconcile_config(paths: ModusPaths, request: ScaffoldRequest) -> None:
    if request.kind == "project":
        reconcile_optional_config(paths)
        return
    reconcile_optional_config(paths, workspace_config=_next_config(paths, request))


def _prepare_data_tree(
    paths: ModusPaths,
    request: ScaffoldRequest,
    writer: ScaffoldWriter,
) -> None:
    """Restore unmanifested data structure, config, and workspace views."""

    if request.kind == "workspace":
        from ..workspace import ensure_workspace_directories

        ensure_workspace_directories(paths)
    else:
        writer.ensure_knowledge_directories()
    _reconcile_config(paths, request)
    if request.kind == "workspace":
        from ..workspace import refresh_generated

        refresh_generated(paths.root)


def _next_config(paths: ModusPaths, request: ScaffoldRequest) -> ModusConfig:
    """Preserve advanced settings while replacing init-owned configuration."""

    try:
        existing = ModusConfig.read(paths)
    except (CorruptArtifactError, OSError, TypeError, ValueError):
        existing = ModusConfig()
    return replace(
        existing,
        kind=request.kind,
        workspace=(
            {**existing.workspace, "members": [dict(m) for m in request.workspace_members]}
            if request.kind == "workspace"
            else {"members": []}
        ),
    )
