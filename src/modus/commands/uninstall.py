"""Plan and apply a manifest-owned project uninstall."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .. import git_hygiene
from ..config import ModusConfig
from ..manifest import ManagedFile, ManagedSection, Manifest, serialized_install
from ..paths import ModusPaths
from ..platforms import get_adapters
from ..platforms.sections import section_block
from .install_state import unsafe_target_issue

__all__ = [
    "KnowledgeDisposition",
    "ProjectUninstallPlan",
    "UninstallPlanChangedError",
    "apply_uninstall",
    "plan_uninstall",
    "run_uninstall",
]


# 预览与应用之间的变化需要重新选择计划，不能沿用旧授权集合。
class UninstallPlanChangedError(RuntimeError):
    """The project changed after preview and must be confirmed again."""


# 持久知识的去留独立于框架卸载，默认策略保留用户内容。
class KnowledgeDisposition(StrEnum):
    """Explicit treatment of the only durable project data."""

    RETAIN = "retain"
    DELETE = "delete"


# 知识路径和处置策略随计划冻结，应用时不重新猜测用户意图。
# 即使项目清单缺失，明确选择的知识处置仍可形成独立清理计划。
@dataclass(frozen=True, slots=True)
class KnowledgePlan:
    """Machine-readable knowledge state bound to an uninstall plan."""

    path: str
    present: bool
    disposition: KnowledgeDisposition

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "present": self.present,
            "disposition": self.disposition.value,
        }


# 预览是不可变值对象，重检可直接比较完整计划。
# 可删除资产与人工检查项分开保存，避免异常路径被顺带清理。
@dataclass(frozen=True, slots=True)
class ProjectUninstallPlan:
    """Immutable preview of one project-root uninstall transaction."""

    root: Path
    installed: bool
    project_kind: str
    framework_version: str | None
    platforms: tuple[str, ...]
    files: tuple[ManagedFile, ...]
    sections: tuple[ManagedSection, ...]
    handled_files: frozenset[str]
    removed_files: tuple[str, ...]
    removed_dirs: tuple[str, ...]
    removed_sections: tuple[str, ...]
    manual_review: tuple[str, ...]
    warnings: tuple[str, ...]
    knowledge: KnowledgePlan

    # 未安装项目仍可能有显式选择删除的知识，因此不能只检查安装标记。
    @property
    def actionable(self) -> bool:
        """Whether applying this plan would remove project-owned content."""

        return self.installed or bool(
            self.removed_files or self.removed_dirs or self.removed_sections
        )

    # 平台适配器需要可变清单；每次构造副本，保持确认计划不可变。
    def removal_manifest(self) -> Manifest:
        """Return a mutable adapter input without weakening plan immutability."""

        return Manifest(
            framework_version=self.framework_version or "unknown",
            platforms=list(self.platforms),
            files=list(self.files),
            sections=list(self.sections),
        )

    # 同一计划生成预览与执行报告，确保两者使用相同路径集合。
    def to_report(self, *, applied: bool = False) -> dict[str, Any]:
        status = "not-installed" if not self.actionable else "uninstalled" if applied else "dry-run"
        return {
            "status": status,
            "applied": bool(applied and self.actionable),
            "root": str(self.root),
            "projectKind": self.project_kind,
            "removedFiles": list(self.removed_files),
            "removedDirs": list(self.removed_dirs),
            "removedSections": list(self.removed_sections),
            "platforms": list(self.platforms),
            "manualReview": list(self.manual_review),
            "warnings": list(self.warnings),
            "knowledge": self.knowledge.to_dict(),
        }


# 损坏配置报告未知类型，不阻止按独立清单检查受管资产。
# 类型探测失败用 unknown 表达，不猜测工作区成员的处置范围。
def _project_kind(paths: ModusPaths) -> str:
    if not paths.config_path.is_file():
        return "project"
    try:
        return ModusConfig.read(paths).kind
    except (OSError, RuntimeError, TypeError, ValueError):
        return "unknown"


# 只使用空目录删除，保留卸载后仍含用户文件的容器。
# 从深层向上处理，父目录仅在子项清理后才有机会为空。
def _prune_empty_dirs(base: Path) -> None:
    """Remove empty projection directories bottom-up, never non-empty ones."""

    if not base.exists():
        return
    for child in sorted(base.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass
    try:
        base.rmdir()
    except OSError:
        pass


# 链接、异常 JSON 和损坏标记进入人工检查列表。
# 共享容器通过结构检查后才交给平台适配器移除受管部分。
def _partition_removals(
    paths: ModusPaths,
    files: list[ManagedFile],
    sections: list[ManagedSection],
) -> tuple[list[ManagedFile], list[ManagedSection], list[str]]:
    """Separate removable assets from malformed shared containers."""

    safe_files: list[ManagedFile] = []
    safe_sections: list[ManagedSection] = []
    manual: list[str] = []
    for entry in files:
        target = paths.root / entry.path
        if target.is_symlink():
            manual.append(entry.path)
            continue
        if not target.exists():
            safe_files.append(entry)
            continue
        if entry.is_hook_config:
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                manual.append(entry.path)
                continue
            if not isinstance(payload, dict):
                manual.append(entry.path)
                continue
        elif not target.is_file():
            manual.append(entry.path)
            continue
        safe_files.append(entry)
    for section_entry in sections:
        target = paths.root / section_entry.path
        if target.is_symlink():
            manual.append(f"{section_entry.path}#{section_entry.marker}")
            continue
        if target.exists() and not target.is_file():
            manual.append(f"{section_entry.path}#{section_entry.marker}")
            continue
        try:
            section_block(target, section_entry.marker)
        except (OSError, UnicodeDecodeError, ValueError):
            manual.append(f"{section_entry.path}#{section_entry.marker}")
            continue
        safe_sections.append(section_entry)
    return safe_files, safe_sections, sorted(set(manual))


# 规划阶段只读，在安装锁内生成一致的资产预览。
# 清单声明仍须经过路径检查，不能直接作为删除权限。
# 知识目录仅在显式删除策略下纳入移除集合。
@serialized_install
def plan_uninstall(
    root: str | Path,
    *,
    knowledge: KnowledgeDisposition = KnowledgeDisposition.RETAIN,
) -> ProjectUninstallPlan:
    """Inspect one root and return an immutable, side-effect-free removal plan."""

    paths = ModusPaths.for_root(root)
    knowledge_path = paths.knowledge_dir.relative_to(paths.root).as_posix()
    knowledge_plan = KnowledgePlan(
        path=knowledge_path,
        present=paths.knowledge_dir.exists() or paths.knowledge_dir.is_symlink(),
        disposition=knowledge,
    )
    project_kind = _project_kind(paths)
    if not paths.manifest_path.is_file():
        cleanup_removed_dirs: tuple[str, ...] = ()
        cleanup_manual_review: tuple[str, ...] = ()
        if knowledge is KnowledgeDisposition.DELETE and knowledge_plan.present:
            issue = unsafe_target_issue(paths.root, paths.knowledge_dir / ".uninstall-check")
            if issue:
                cleanup_manual_review = (knowledge_path,)
            elif paths.knowledge_dir.is_dir():
                cleanup_removed_dirs = (knowledge_path,)
        return ProjectUninstallPlan(
            root=paths.root,
            installed=False,
            project_kind=project_kind,
            framework_version=None,
            platforms=(),
            files=(),
            sections=(),
            handled_files=frozenset(),
            removed_files=(),
            removed_dirs=cleanup_removed_dirs,
            removed_sections=(),
            manual_review=cleanup_manual_review,
            warnings=(),
            knowledge=knowledge_plan,
        )

    manifest = Manifest.read(paths)
    manual_review: list[str] = []
    safe_files: list[ManagedFile] = []
    for entry in manifest.files:
        if unsafe_target_issue(paths.root, paths.root / entry.path):
            manual_review.append(entry.path)
        else:
            safe_files.append(entry)
    safe_sections: list[ManagedSection] = []
    for section_entry in manifest.sections:
        if unsafe_target_issue(paths.root, paths.root / section_entry.path):
            manual_review.append(section_entry.path)
        else:
            safe_sections.append(section_entry)
    files, sections, manual = _partition_removals(paths, safe_files, safe_sections)
    manual_review.extend(manual)
    safe_manifest = Manifest(
        framework_version=manifest.framework_version,
        platforms=list(manifest.platforms),
        files=list(files),
        sections=list(sections),
    )

    # 适配器认领的文件只处理一次，避免通用清理重复修改共享配置。
    handled: set[str] = set()
    removed_files: list[str] = []
    removed_sections: list[str] = []
    for adapter in get_adapters(manifest.platforms):
        projected, marked = adapter.preview_uninstall(safe_manifest)
        handled.update(entry.path for entry in projected)
        removed_files.extend(entry.path for entry in projected)
        removed_sections.extend(f"{entry.path}#{entry.marker}" for entry in marked)
        # 与执行顺序一致，最后一个使用共享区块的平台负责移除它。
        safe_manifest.platforms.remove(adapter.name)

    for entry in files:
        if entry.path in handled or entry.path.startswith("modus/knowledge/"):
            continue
        if entry.path.startswith(".modus/") and (paths.root / entry.path).is_file():
            removed_files.append(entry.path)

    removed_dirs: list[str] = []
    directories = [paths.cache_dir]
    if knowledge is KnowledgeDisposition.DELETE:
        directories.append(paths.knowledge_dir)
    for directory in directories:
        relative = directory.relative_to(paths.root).as_posix()
        if unsafe_target_issue(paths.root, directory / ".uninstall-check"):
            manual_review.append(relative)
        elif directory.is_dir():
            removed_dirs.append(relative)

    for target in (paths.config_path, paths.manifest_path):
        relative = target.relative_to(paths.root).as_posix()
        if unsafe_target_issue(paths.root, target):
            manual_review.append(relative)
        elif target.is_file():
            removed_files.append(relative)

    # 忽略规则也先预览，报告应包含这项可见的项目变更。
    hygiene = git_hygiene.remove_local_state_ignored(paths, apply=False)
    if hygiene.get("changed"):
        removed_sections.append(".gitignore#modus-local-state")

    return ProjectUninstallPlan(
        root=paths.root,
        installed=True,
        project_kind=project_kind,
        framework_version=manifest.framework_version,
        platforms=tuple(manifest.platforms),
        files=tuple(files),
        sections=tuple(sections),
        handled_files=frozenset(handled),
        removed_files=tuple(sorted(set(removed_files))),
        removed_dirs=tuple(sorted(set(removed_dirs))),
        removed_sections=tuple(sorted(set(removed_sections))),
        manual_review=tuple(sorted(set(manual_review))),
        warnings=(),
        knowledge=knowledge_plan,
    )


# 公共入口只传递已确认计划，真正修改由持锁服务统一执行。
def apply_uninstall(plan: ProjectUninstallPlan) -> dict[str, Any]:
    """Revalidate and apply a previously selected uninstall policy."""

    return _apply_uninstall(plan.root, plan)


# 持锁重新生成计划，发现差异立即中止。
# 平台共享文件先由适配器处理，再清理本地受管文件和缓存。
# 目录收尾只剪除空容器，保留非受管内容。
@serialized_install
def _apply_uninstall(
    root: str | Path,
    plan: ProjectUninstallPlan,
) -> dict[str, Any]:
    """Hold the per-root install lock across revalidation and every mutation."""

    current = plan_uninstall(root, knowledge=plan.knowledge.disposition)
    # 比较完整计划而非仅版本号，覆盖预览后的资产与策略变化。
    if current != plan:
        raise UninstallPlanChangedError(
            "预览后项目安装发生变化，未执行卸载。请重新运行命令并检查新预览。"
        )
    if not current.actionable:
        return current.to_report()

    paths = ModusPaths.for_root(current.root)
    if current.installed:
        safe_manifest = current.removal_manifest()
        for adapter in get_adapters(current.platforms):
            adapter.uninstall(paths, safe_manifest)

        for entry in current.files:
            if entry.path in current.handled_files or entry.path.startswith("modus/knowledge/"):
                continue
            if not entry.path.startswith(".modus/"):
                continue
            target = paths.root / entry.path
            if target.is_file() and not target.is_symlink():
                target.unlink()

    # 仅遍历确认计划中的目录，不根据运行时发现扩张删除范围。
    for relative in current.removed_dirs:
        directory = paths.root / relative
        if directory.is_dir() and not directory.is_symlink():
            shutil.rmtree(directory)

    if current.installed:
        for target in (paths.config_path, paths.manifest_path):
            if target.is_file() and not target.is_symlink():
                target.unlink()

        git_hygiene.remove_local_state_ignored(paths, apply=True)
    prune_roots = (
        (
            ".modus",
            "modus",
            ".claude",
            ".cursor",
            ".agents",
            ".codex",
            ".codebuddy",
        )
        if current.installed
        else ("modus",)
    )
    for relative_directory in prune_roots:
        base = paths.root / relative_directory
        if not base.is_symlink():
            _prune_empty_dirs(base)
    return current.to_report(applied=True)


# 兼容入口保留预览默认值，实际执行必须显式启用。
# 旧布尔参数在边界转换为处置枚举，核心流程只处理一种策略表示。
def run_uninstall(
    root: str | Path,
    *,
    keep_knowledge: bool = True,
    apply: bool = False,
) -> dict[str, Any]:
    """Compatibility façade; durable knowledge is retained by default."""

    disposition = KnowledgeDisposition.RETAIN if keep_knowledge else KnowledgeDisposition.DELETE
    plan = plan_uninstall(root, knowledge=disposition)
    return apply_uninstall(plan) if apply else plan.to_report()
