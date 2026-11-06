"""Canonical project knowledge, installation and initialization-analysis paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# Platform projection trees. These hold Modus-projected skill bundles, command
# surfaces, and host configuration (NOT user source code), so every code-scanning or
# evidence-searching surface must exclude them the same way it excludes the
# ``modus/`` / ``.modus/`` output trees. Centralised here so initialization
# analysis, the ripgrep fallback (``orchestrator/fallback.py``), and
# any future scanner share one authoritative list and never drift apart.
# Roots that contain projected Agent Skill bundles.  Keep this separate from
# ``PLATFORM_OUTPUT_DIRS`` also excludes host configuration and legacy assets
# under ``.codex``; those are never project implementation evidence.
PLATFORM_SKILL_DIRS: Final[tuple[str, ...]] = (
    ".claude",
    ".agents",
    ".cursor",
    ".codebuddy",
    ".dsh",
)

# Project-root directories reserved for host configuration and projections. Source and
# knowledge scanners must ignore all of them so Modus
# never learns from its own projections.
PLATFORM_OUTPUT_DIRS: Final[tuple[str, ...]] = (*PLATFORM_SKILL_DIRS, ".codex")

PROJECT_OUTPUT_DIRS: Final = PLATFORM_OUTPUT_DIRS

# Project-root markdown files Modus injects/owns a managed section in (Claude's
# ``CLAUDE.md``, Codex's ``AGENTS.md``, CodeBuddy's ``CODEBUDDY.md``). They live at
# the project root (not under a ``PLATFORM_OUTPUT_DIRS`` tree) and carry Modus's
# own ``<!-- MODUS:BEGIN ... -->`` context, so any code/evidence scanner must treat
# them as Modus output -- never as project source. Centralised here so the
# ripgrep fallback (``orchestrator/fallback.py``) and any future scanner share one
# authoritative list. (Cursor's ``.cursor/rules/modus.mdc`` already sits under a
# ``PLATFORM_OUTPUT_DIRS`` tree, so it needs no separate entry.)
MANAGED_ROOT_FILES: Final[tuple[str, ...]] = ("CLAUDE.md", "AGENTS.md", "CODEBUDDY.md")

DOMAIN_GENERATED_REFERENCE_KINDS: Final[tuple[str, ...]] = (
    "api",
    "downstream",
    "infrastructure",
    "object",
    "rule",
    "state_machine",
)

BUSINESS_REFERENCE_KINDS: Final[tuple[str, ...]] = ("meta", "experience", "scenario")

WORKSPACE_GENERATED_MAP_NAMES: Final[tuple[str, ...]] = (
    "member-map",
    "system-map",
    "capability-map",
    "service-map",
    "feature-map",
    "contract-map",
    "object-map",
    "infrastructure-map",
    "delivery-map",
    "fact-status",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_path_segment(value: str, *, kind: str) -> str:
    """Validate one user-facing identity before placing it in a governed path."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or ":" in value
        or any(ch.isspace() or ord(ch) < 32 for ch in value)
    ):
        raise ValueError(f"{kind} 必须为单个非空规范路径片段，实际为 {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class ModusPaths:
    """Resolve all Modus paths relative to a project root.

    Two top-level trees are produced inside a user project:

    * ``.modus/``  -- control plane (config + commands + skills + manifest)
    * ``modus/``   -- authored knowledge and disposable analysis cache
    """

    root: Path

    @classmethod
    def for_root(cls, root: str | Path) -> ModusPaths:
        """Create a canonical path namespace rooted at ``root``."""

        return cls(Path(root).resolve())

    # --- .modus/ : neutral authoritative source -----------------------------
    @property
    def modus_dir(self) -> Path:
        return self.root / ".modus"

    @property
    def commands_dir(self) -> Path:
        return self.modus_dir / "commands"

    @property
    def skills_dir(self) -> Path:
        return self.modus_dir / "skills"

    @property
    def manifest_path(self) -> Path:
        return self.modus_dir / "manifest.json"

    # --- modus/ : project data ---------------------------------------------
    @property
    def data_dir(self) -> Path:
        return self.root / "modus"

    @property
    def config_path(self) -> Path:
        return self.modus_dir / "config.yaml"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge"

    @property
    def workspace_handbook_dir(self) -> Path:
        """Workspace-level progressive router; legal only for kind=workspace."""
        return self.knowledge_dir / "handbook"

    @property
    def workspace_handbook_skill(self) -> Path:
        return self.workspace_handbook_dir / "SKILL.md"

    @property
    def workspace_business_dir(self) -> Path:
        return self.workspace_handbook_dir / "references" / "business"

    @property
    def workspace_generated_dir(self) -> Path:
        return self.workspace_handbook_dir / "references" / "generated"

    @property
    def workspace_members_dir(self) -> Path:
        return self.workspace_generated_dir / "members"

    def workspace_member_doc(self, member_id: str) -> Path:
        member_id = _canonical_path_segment(member_id, kind="工作区成员")
        return self.workspace_members_dir / f"{member_id}.md"

    def workspace_generated_map(self, name: str) -> Path:
        if name not in WORKSPACE_GENERATED_MAP_NAMES:
            raise ValueError(f"未知的工作区生成地图： {name!r}")
        return self.workspace_generated_dir / f"{name}.md"

    @property
    def architecture_overview(self) -> Path:
        """Rebuildable system relationship overview."""
        return self.knowledge_dir / "architecture-overview.md"

    @property
    def constraint_dir(self) -> Path:
        return self.knowledge_dir / "constraint"

    @property
    def global_standard(self) -> Path:
        return self.constraint_dir / "global-standard.md"

    @property
    def team_standard(self) -> Path:
        return self.constraint_dir / "team-standard.md"

    @property
    def domain_dir(self) -> Path:
        return self.knowledge_dir / "domain"

    def domain(self, name: str) -> Path:
        """Directory for one knowledge domain (e.g. ``knowledge/domain/order``)."""
        name = _canonical_path_segment(name, kind="domain")
        return self.domain_dir / name

    def domain_references(self, domain: str) -> Path:
        return self.domain(domain) / "references"

    def domain_business_dir(self, domain: str) -> Path:
        """Human-owned business knowledge for one canonical Domain."""
        return self.domain_references(domain) / "business"

    def domain_business_index(self, domain: str, category: str | None = None) -> Path:
        """One required Domain business index, never a project-root business path."""
        directory = self.domain_business_dir(domain)
        if category is None:
            return directory / "index.md"
        if category not in BUSINESS_REFERENCE_KINDS:
            raise ValueError(f"未知的业务引用分类： {category!r}")
        return directory / category / "index.md"

    def modules_dir(self, domain: str) -> Path:
        """Directory containing flat machine-owned Module documents for one Domain."""
        domain = _canonical_path_segment(domain, kind="domain")
        return self.domain_references(domain) / "modules"

    def module(self, domain: str, module: str) -> Path:
        """Canonical flat Module document (``references/modules/<module>.md``)."""
        domain = _canonical_path_segment(domain, kind="domain")
        module = _canonical_path_segment(module, kind="module")
        return self.modules_dir(domain) / f"{module}.md"

    def domain_skill(self, name: str) -> Path:
        """Generated routing entry point for a business domain (``SKILL.md``).

        Its YAML frontmatter carries Domain metadata that drives routing, while
        durable human knowledge stays under ``references/business``. The file is
        machine-owned and may be completely regenerated by ``modus-init``.
        """
        return self.domain(name) / "SKILL.md"

    # --- caches and state (git-ignored in user projects) -------------------
    @property
    def cache_dir(self) -> Path:
        return self.data_dir / ".cache"

    @property
    def knowledge_authoring_dir(self) -> Path:
        """Disposable init/reinit plan and progress state."""
        return self.cache_dir / "knowledge-authoring"

    @property
    def scope_confirmation_path(self) -> Path:
        return self.knowledge_authoring_dir / "scope-confirmation.md"

    @property
    def init_analysis_dir(self) -> Path:
        """Disposable JSON evidence created only for init/reinit authoring."""
        return self.cache_dir / "init-analysis"

    @property
    def analysis_bundles_dir(self) -> Path:
        return self.init_analysis_dir / "bundles"

    @property
    def analysis_extraction_cache_dir(self) -> Path:
        return self.init_analysis_dir / "extraction-cache"

    @property
    def compiler_cache_dir(self) -> Path:
        """Rebuildable compiler observations used only during init analysis."""
        return self.analysis_extraction_cache_dir / "compiler"

    @property
    def knowledge_locks_dir(self) -> Path:
        """Disposable locks for writes to the persistent knowledge tree."""
        return self.cache_dir / "locks" / "knowledge"

    def knowledge_document_lock(self, target: str | Path) -> Path:
        """Return the cache-resident lock mirroring one knowledge document path."""
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            relative = candidate.relative_to(self.knowledge_dir)
        except ValueError as exc:
            raise ValueError(f"知识锁目标位于知识目录之外： {candidate}") from exc
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError(f"知识锁目标不规范： {candidate}")
        mirrored = self.knowledge_locks_dir / relative
        return mirrored.with_suffix(mirrored.suffix + ".lock")

    @property
    def init_analysis_lock(self) -> Path:
        """Serialize complete initialization analysis builds."""
        return self.init_analysis_dir / ".build.lock"

    def relative(self, path: Path) -> str:
        """Return ``path`` as a POSIX string relative to the project root."""
        return path.resolve().relative_to(self.root).as_posix()


__all__ = [
    "BUSINESS_REFERENCE_KINDS",
    "DOMAIN_GENERATED_REFERENCE_KINDS",
    "MANAGED_ROOT_FILES",
    "ModusPaths",
    "PLATFORM_OUTPUT_DIRS",
    "PLATFORM_SKILL_DIRS",
    "PROJECT_OUTPUT_DIRS",
    "WORKSPACE_GENERATED_MAP_NAMES",
]
