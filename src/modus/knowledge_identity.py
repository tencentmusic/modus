"""Canonical structural identities for human-tree Modus knowledge paths."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

from .paths import ModusPaths
from .scope_models import ScopeRef

OwnershipPlane: TypeAlias = Literal["human", "business", "machine", "mixed"]
PathKind: TypeAlias = Literal[
    "workspace-handbook-skill",
    "workspace-business-reference",
    "workspace-generated-reference",
    "architecture-overview",
    "constraint",
    "domain-scope-skill",
    "module-scope-skill",
    "domain-business-reference",
    "domain-generated-reference",
]

_KNOWLEDGE_PREFIX: Final = ("modus", "knowledge")
_DOMAIN_GENERATED_FILES: Final = frozenset(
    {
        "api.md",
        "downstream.md",
        "infrastructure.md",
        "object.md",
        "rule.md",
        "state_machine.md",
    }
)


# 路径字符串保留原分段再校验，不能先规范化而掩盖上级跳转。
def _canonical_relative_parts(target: str | Path) -> tuple[str, ...] | None:
    """Parse a canonical project-relative POSIX path without touching disk."""

    try:
        raw = str(target)
    except (TypeError, ValueError):
        return None
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or "\\" in raw or "\x00" in raw:
        return None
    parts = tuple(raw.split("/"))
    return None if any(not part or part in {".", ".."} for part in parts) else parts


# 缺失后缀允许新建目标，但任何已存在的软链或特殊文件都拒绝接管。
# 分类时的检查不是写入锁，实际变更仍需重新绑定描述符。
def _existing_path_chain_is_safe(root: Path, parts: tuple[str, ...]) -> bool:
    """Reject links and non-directory ancestors while allowing absent suffixes."""

    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError:
            return False
        if stat.S_ISLNK(mode):
            return False
        final = index == len(parts) - 1
        if (final and not stat.S_ISREG(mode)) or (not final and not stat.S_ISDIR(mode)):
            return False
    try:
        current.resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _target_parts(paths: ModusPaths, target: str | Path) -> tuple[str, ...] | None:
    """Return safe, canonical project-relative parts without following links."""
    parts = _canonical_relative_parts(target)
    if parts is None:
        return None
    root = paths.root.resolve()
    return parts if _existing_path_chain_is_safe(root, parts) else None


def _is_team_standard_tail(tail: tuple[str, ...]) -> bool:
    # 新内容推荐一级专题；已有嵌套专题仍属于同一人工命名空间。
    return tail == ("constraint", "team-standard.md") or (
        len(tail) >= 3 and tail[:2] == ("constraint", "team-standard") and tail[-1].endswith(".md")
    )


def is_team_standard_path(target: str | Path) -> bool:
    """识别入口及任意深度的 Markdown 专题，不检查磁盘或授予写入权限。"""
    parts = _canonical_relative_parts(target)
    return (
        parts is not None and parts[:2] == _KNOWLEDGE_PREFIX and _is_team_standard_tail(parts[2:])
    )


def _scope(domain: str, module: str | None) -> ScopeRef | None:
    try:
        return (
            ScopeRef.for_domain(domain) if module is None else ScopeRef.for_module(domain, module)
        )
    except ValueError:
        return None


# 目录布局决定结构身份，ownership_plane 则决定维护权限。
# 两者分开，避免“位于知识树”被误解为“允许自动覆盖”。
@dataclass(frozen=True, slots=True)
class KnowledgePathIdentity:
    """Typed ownership identity for one canonical knowledge entry point."""

    path_kind: PathKind
    scope_ref: ScopeRef | None
    domain: str | None
    module: str | None
    ownership_plane: OwnershipPlane

    # 工作区手册中的人工业务材料与生成导航有不同所有权。
    # 开关由项目种类决定，不让普通项目意外识别工作区专属表面。
    @classmethod
    def _workspace_identity(
        cls,
        tail: tuple[str, ...],
        *,
        enabled: bool,
    ) -> KnowledgePathIdentity | None:
        if not enabled:
            return None
        if tail == ("handbook", "SKILL.md"):
            return cls("workspace-handbook-skill", None, None, None, "machine")
        if (
            len(tail) >= 4
            and tail[:3] == ("handbook", "references", "business")
            and tail[-1].endswith(".md")
        ):
            return cls("workspace-business-reference", None, None, None, "business")
        if (
            len(tail) in {4, 5}
            and tail[:3] == ("handbook", "references", "generated")
            and tail[-1].endswith(".md")
        ):
            return cls("workspace-generated-reference", None, None, None, "machine")
        return None

    @classmethod
    def _root_identity(cls, tail: tuple[str, ...]) -> KnowledgePathIdentity | None:
        if tail == ("architecture-overview.md",):
            return cls("architecture-overview", None, None, None, "machine")
        if tail == ("constraint", "global-standard.md") or _is_team_standard_tail(tail):
            return cls("constraint", None, None, None, "human")
        return None

    # 只有已知生成文档和分片目录获得机器所有权，未知文件保持未分类。
    @classmethod
    def _domain_identity(cls, tail: tuple[str, ...]) -> KnowledgePathIdentity | None:
        if len(tail) < 3 or tail[0] != "domain":
            return None
        domain = tail[1]
        if len(tail) == 3 and tail[2] == "SKILL.md":
            return cls._scoped("domain-scope-skill", domain, None, "machine")
        if len(tail) == 5 and tail[2:4] == ("references", "modules"):
            module_file = tail[4]
            if module_file.endswith(".md"):
                return cls._scoped("module-scope-skill", domain, module_file[:-3], "machine")
        if len(tail) >= 5 and tail[2:4] == ("references", "business") and tail[-1].endswith(".md"):
            return cls._scoped("domain-business-reference", domain, None, "business")
        if len(tail) == 4 and tail[2] == "references" and tail[3] in _DOMAIN_GENERATED_FILES:
            return cls._scoped("domain-generated-reference", domain, None, "machine")
        if (
            len(tail) == 5
            and tail[2] == "references"
            and tail[3] in {"api", "object"}
            and tail[4].endswith(".md")
        ):
            return cls._scoped("domain-generated-reference", domain, None, "machine")
        return None

    # 域与模块名通过公共 ScopeRef 校验，分类器不复制另一套 ID 规则。
    @classmethod
    def _scoped(
        cls,
        path_kind: PathKind,
        domain: str,
        module: str | None,
        ownership_plane: OwnershipPlane,
    ) -> KnowledgePathIdentity | None:
        scope_ref = _scope(domain, module)
        if scope_ref is None:
            return None
        return cls(path_kind, scope_ref, domain, module, ownership_plane)

    # 文件系统安全与布局识别都通过后才返回身份，形似合法路径并不充分。
    # 无配置时允许识别保留的工作区知识，配置损坏时不猜测工作区种类。
    @classmethod
    def classify(cls, paths: ModusPaths, target: str | Path) -> KnowledgePathIdentity | None:
        """Classify one exact project-relative human-tree knowledge entry.

        Absolute and non-canonical inputs are intentionally unmanaged. Existing
        filesystem entries add a second safety gate: no symlink or special file
        may acquire knowledge ownership through a path-shaped name.
        """
        parts = _target_parts(paths, target)
        if parts is None:
            return None
        if parts[:2] != _KNOWLEDGE_PREFIX:
            return None

        tail = parts[2:]
        workspace_unconfigured = not paths.config_path.exists()
        workspace_kind = False
        if paths.config_path.is_file():
            try:
                from .config import ModusConfig

                workspace_kind = ModusConfig.read(paths).kind == "workspace"
            except (OSError, ValueError):
                workspace_kind = False
        workspace_surface = workspace_kind or workspace_unconfigured
        workspace = cls._workspace_identity(tail, enabled=workspace_surface)
        return workspace or cls._root_identity(tail) or cls._domain_identity(tail)


__all__ = ["KnowledgePathIdentity", "OwnershipPlane", "PathKind", "is_team_standard_path"]
