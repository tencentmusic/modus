"""Render and reconcile current managed assets, preserving user edits."""

from __future__ import annotations

import errno
import os
import stat
import tempfile
from pathlib import Path
from typing import cast

from .. import __version__, git_hygiene
from ..artifacts_io import atomic_write_text
from ..config import ModusConfig, reconcile_optional_config
from ..legacy_hooks import clean_legacy_hook_config
from ..manifest import (
    ManagedFile,
    ManagedSection,
    Manifest,
    hash_file,
    hash_text,
    serialized_install,
)
from ..paths import ModusPaths
from ..platforms.base import is_executable_asset
from ..platforms.sections import (
    inject_section,
    remove_section,
    section_block,
)
from ..scaffold import scaffold_project
from ..versioning import bump_kind
from .install_state import InstallTransaction, unsafe_target_issue, validate_install_root

__all__ = ["is_project_root", "preview_update", "reconcile_desired_manifest", "run_update"]


# 阻塞报告仍提供完整结果字段，CLI 无需为不同失败原因分叉渲染。
def _blocked(installed: str, kind: str, message: str) -> dict:
    return {
        "status": "blocked",
        "message": message,
        "installedVersion": installed,
        "frameworkVersion": __version__,
        "changeKind": kind,
        "appliedFiles": [],
        "addedFiles": [],
        "removedFiles": [],
        "reinstalledFiles": [],
        "removedDirectories": [],
        "userEditedFiles": [],
        "conflictedFiles": [],
    }


# 受管内容按清单摘要检查，首次种植后归用户的规范文件不参与过期判定。
def _managed_assets_match_manifest(paths: ModusPaths, manifest: Manifest) -> bool:
    """Read-only verification for a genuinely current installed projection."""
    preserved_user_paths = {paths.relative(paths.team_standard)}
    try:
        for entry in manifest.files:
            if entry.path in preserved_user_paths:
                # Seeded once and explicitly user-owned thereafter. Its
                # original manifest hash is an overwrite guard, not a desired
                # content hash, so human edits do not make the framework stale.
                continue
            target = paths.root / entry.path
            if target.is_symlink() or not target.is_file() or hash_file(target) != entry.sha256:
                return False
        for section_entry in manifest.sections:
            target = paths.root / section_entry.path
            if target.is_symlink() or not target.is_file():
                return False
            block = section_block(target, section_entry.marker)
            if block is None or hash_text(block) != section_entry.sha256:
                return False
    except (OSError, UnicodeError, ValueError):
        return False
    return True


# 期望资产在临时根渲染，当前配置读取失败时保留历史项目回退行为。
# 实际写入仍由后续所有权检查和事务负责。
def _render_desired(
    desired_paths: ModusPaths, old: Manifest, installed_paths: ModusPaths
) -> Manifest:
    try:
        installed_config = ModusConfig.read(installed_paths)
        kind = installed_config.kind
        workspace_members = installed_config.workspace["members"] if kind == "workspace" else None
    # NOCA:broad-except(保留历史配置读取失败时的项目模式回退，实际写入仍检查所有权)
    except Exception:
        kind = "project"
        workspace_members = None
    return scaffold_project(
        desired_paths.root,
        old.platforms,
        kind=kind,
        workspace_members=workspace_members,
    )


# 清单摘要表示框架拥有的基线，用户编辑不能被重新认领为可覆盖内容。
# 普通文件和标记区块分别协调；旧 Hook 仅按签名撤销。
# 可延迟清单落盘，让外层事务统一控制提交标记。
def reconcile_desired_manifest(
    paths: ModusPaths,
    old: Manifest,
    desired_paths: ModusPaths,
    desired: Manifest,
    *,
    preserve_existing_paths: frozenset[str] = frozenset(),
    write_manifest: bool = True,
) -> dict:
    """Reconcile current managed assets by hash; preserve knowledge and user edits."""
    applied: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    removed_directories: list[str] = []
    user_edited: list[str] = []
    conflicted: list[str] = []

    next_manifest = Manifest(
        framework_version=__version__,
        platforms=desired.platforms,
    )

    old_files = {f.path: f for f in old.files}
    desired_files = {f.path: f for f in desired.files}
    desired_section_paths = {s.path for s in desired.sections}
    for rel, desired_file in sorted(desired_files.items()):
        old_file = old_files.get(rel)
        source = desired_paths.root / rel
        target = paths.root / rel

        if rel in preserve_existing_paths and target.is_file():
            # These files are seeded once and then user-owned.  Hashing the
            # current target here would launder a hand edit into the managed
            # baseline: a later update would see the matching hash and overwrite
            # the user's content.  Retain the prior ownership hash, or use the
            # rendered template hash when repairing an untracked seed.
            next_manifest.files.append(old_file or desired_file)
            continue

        desired_content = source.read_text(encoding="utf-8")
        action = _apply_file(
            target, desired_content, old_file, desired_file, rel, user_edited, conflicted
        )
        if action == "skipped":
            if old_file is not None:
                next_manifest.files.append(old_file)
            continue
        if action == "conflict":
            continue
        if action == "added":
            added.append(rel)
        elif action == "applied":
            applied.append(rel)
        next_manifest.files.append(_entry_for(target, rel, desired_file.template))

    for rel, old_file in sorted(old_files.items()):
        if rel in desired_files:
            continue
        if rel in desired_section_paths:
            continue
        target = paths.root / rel
        if rel.startswith("modus/") and target.exists():
            # Project knowledge is durable. A managed removal may already have
            # removed a source path, but user-owned data is never retired merely
            # because a future renderer stopped tracking it.
            next_manifest.files.append(old_file)
            continue
        action = _remove_unused_managed_file(target, old_file, rel, user_edited)
        if action == "removed":
            removed.append(rel)
        elif action == "skipped":
            next_manifest.files.append(old_file)

    # 旧启动器按清单摘要退役后只移除空容器，保留用户追加的脚本。
    if any(rel.startswith(".modus/hooks/") for rel in old_files):
        hooks_directory = paths.root / ".modus/hooks"
        if hooks_directory.is_dir() and not hooks_directory.is_symlink():
            try:
                hooks_directory.rmdir()
            except OSError as exc:
                if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                    raise
            else:
                removed_directories.append(".modus/hooks")

    _apply_sections(
        paths, old, old_files, desired_paths, desired, next_manifest, applied, added, user_edited
    )

    if write_manifest:
        next_manifest.write(paths)
    report: dict = {
        "appliedFiles": sorted(set(applied)),
        "addedFiles": sorted(set(added)),
        "removedFiles": sorted(set(removed)),
        "removedDirectories": removed_directories,
        "userEditedFiles": sorted(set(user_edited)),
        "conflictedFiles": sorted(set(conflicted)),
    }
    if not write_manifest:
        report["_nextManifest"] = next_manifest
    return report


# 三方比较使用旧基线、当前内容和新模板；当前偏离旧基线时保留用户编辑。
# 没有旧所有权记录的已有文件视为冲突，不因内容相似而接管。
def _apply_file(
    target: Path,
    desired_content: str,
    old_file: ManagedFile | None,
    desired_file: ManagedFile,
    rel: str,
    user_edited: list[str],
    conflicted: list[str],
) -> str:
    if old_file is None:
        if target.exists():
            conflicted.append(rel)
            return "conflict"
        _write_text(target, desired_content, rel)
        return "added"

    if not target.exists():
        _write_text(target, desired_content, rel)
        return "added"

    current_hash = hash_file(target)
    if current_hash == desired_file.sha256:
        return "unchanged"
    if current_hash != old_file.sha256:
        user_edited.append(rel)
        return "skipped"

    _write_text(target, desired_content, rel)
    return "applied"


# 退休资产仍需匹配旧摘要；用户改动的文件继续保留。
# Hook 容器按受管条目撤销，不删除整个共享配置。
def _remove_unused_managed_file(
    target: Path,
    old_file: ManagedFile,
    rel: str,
    user_edited: list[str],
) -> str:
    if not target.exists():
        return "removed"
    if old_file.is_legacy_hook_config:
        if not clean_legacy_hook_config(target):
            user_edited.append(rel)
            return "skipped"
        return "removed"
    if hash_file(target) != old_file.sha256:
        user_edited.append(rel)
        return "skipped"
    target.unlink()
    return "removed"


# 标记区块独立比较摘要，区块外正文不属于框架更新范围。
# 用户移除或编辑过的旧区块保留其旧所有权基线，避免下次更新强制覆盖。
def _apply_sections(
    paths: ModusPaths,
    old: Manifest,
    old_files: dict[str, ManagedFile],
    desired_paths: ModusPaths,
    desired: Manifest,
    next_manifest: Manifest,
    applied: list[str],
    added: list[str],
    user_edited: list[str],
) -> None:
    old_sections = {(s.path, s.marker): s for s in old.sections}
    desired_sections = {(s.path, s.marker): s for s in desired.sections}

    for key, desired_section in sorted(desired_sections.items()):
        rel, marker = key
        old_section = old_sections.get(key)
        desired_block = section_block(desired_paths.root / rel, marker)
        target = paths.root / rel
        current_block = section_block(target, marker) if target.exists() else None
        if current_block is None:
            if old_section is not None and target.exists():
                user_edited.append(rel)
                next_manifest.sections.append(old_section)
                continue
            source = desired_paths.root / rel
            old_file = old_files.get(rel)
            if source.exists() and (
                not target.exists()
                or (
                    old_file is not None
                    and target.exists()
                    and hash_file(target) == old_file.sha256
                )
            ):
                action = "applied" if target.exists() else "added"
                _write_text(target, source.read_text(encoding="utf-8"), rel)
                if action == "applied":
                    applied.append(rel)
                else:
                    added.append(rel)
            else:
                inject_section(target, marker, _section_content(cast(str, desired_block)))
                added.append(rel)
            next_manifest.sections.append(_section_entry(target, rel, marker))
            continue
        if old_section is None:
            user_edited.append(rel)
            continue
        current_hash = hash_text(current_block)
        if current_hash == desired_section.sha256:
            next_manifest.sections.append(ManagedSection(rel, marker, current_hash))
            continue
        if old_section is not None and current_hash != old_section.sha256:
            user_edited.append(rel)
            next_manifest.sections.append(old_section)
            continue
        inject_section(target, marker, _section_content(cast(str, desired_block)))
        applied.append(rel)
        next_manifest.sections.append(_section_entry(target, rel, marker))

    for key, old_section in sorted(old_sections.items()):
        if key in desired_sections:
            continue
        rel, marker = key
        target = paths.root / rel
        current_block = section_block(target, marker) if target.exists() else None
        if current_block is None:
            continue
        if hash_text(current_block) != old_section.sha256:
            user_edited.append(rel)
            next_manifest.sections.append(old_section)
            continue
        remove_section(target, marker)
        applied.append(rel)


# 去除边界标记后交给统一注入器，避免嵌套生成重复标记。
def _section_content(block: str) -> str:
    lines = block.splitlines()
    if len(lines) <= 2:
        return ""
    return "\n".join(lines[1:-1])


# 摘要只覆盖受管区块，其他正文变化不会使框架区块误报过期。
def _section_entry(path: Path, rel: str, marker: str) -> ManagedSection:
    block = section_block(path, marker)
    return ManagedSection(rel, marker, hash_text(block or ""))


# 写入完成后读取实际文件摘要，清单记录落盘内容而非预期中间值。
def _entry_for(path: Path, rel: str, template: str) -> ManagedFile:
    return ManagedFile(rel, hash_file(path), template)


# 原子替换内容后仅为可执行资产补执行位，保留其他权限位。
def _write_text(path: Path, content: str, rel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, content)
    if is_executable_asset(rel):
        mode = os.stat(path).st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# 根据结构化结果生成说明，统计与机器可读报告使用同一数据源。
def _message(status: str, installed: str, framework: str, kind: str, result: dict) -> str:
    if status == "up-to-date":
        return f"已安装 {installed}，框架 {framework}（更新类型：{kind}）；无变更"
    if status == "updated":
        changed = (
            len(result["appliedFiles"]) + len(result["addedFiles"]) + len(result["removedFiles"])
        )
        return f"已更新 {installed} → {framework}（{changed} 个文件，更新类型：{kind}）"
    return (
        f"更新 {installed} → {framework} 部分完成；"
        f"已跳过 {len(result['userEditedFiles'])} 个用户修改文件与 "
        f"{len(result['conflictedFiles'])} 个冲突文件"
    )


# 这里仅探测安装标记是否存在，清单完整性由真正维护入口验证。
def is_project_root(root: str | Path) -> bool:
    return ModusPaths.for_root(root).manifest_path.is_file()


# 先验证版本策略和全部目标路径，再建立覆盖新旧资产的事务快照。
# 所有普通异常都必须触发回滚，随后重新抛出保留原始失败。
# 可选配置协调成功后最后写清单，避免半完成更新被标成成功。
@serialized_install
def run_update(root: str | Path, accept_major: bool = False, allow_downgrade: bool = False) -> dict:
    """Reconcile the installed projection with the current framework version.

    Runs inside an :class:`~modus.commands.install_state.InstallTransaction`:
    any exception rolls every touched file back to its pre-update bytes.
    Major upgrades and downgrades stay blocked until explicitly accepted.
    """
    paths = validate_install_root(root)
    if not paths.manifest_path.is_file():
        return {
            "status": "error",
            "message": "项目尚未初始化（缺少 .modus/manifest.json）",
        }
    old = Manifest.read(paths)
    kind = bump_kind(old.framework_version, __version__)
    if kind == "major" and not accept_major:
        return _blocked(old.framework_version, kind, "安装包主版本更新需要 --accept-major")
    if kind == "downgrade" and not allow_downgrade:
        return _blocked(old.framework_version, kind, "安装包降级需要 --allow-downgrade")
    with tempfile.TemporaryDirectory(prefix="modus-update-desired.") as scratch:
        desired_paths = ModusPaths.for_root(scratch)
        desired = _render_desired(desired_paths, old, paths)
        relative = _manifest_paths(old) | _manifest_paths(desired)
        targets = [paths.root / rel for rel in sorted(relative)] + [
            paths.manifest_path,
            paths.config_path,
        ]
        issues = list(filter(None, (unsafe_target_issue(paths.root, target) for target in targets)))
        if issues:
            return _blocked(old.framework_version, kind, "; ".join(issues))
        transaction = InstallTransaction(
            paths, targets, git_hygiene.snapshot_local_state_index(paths)
        )
        try:
            result = reconcile_desired_manifest(
                paths,
                old,
                desired_paths,
                desired,
                preserve_existing_paths=frozenset(
                    rel for rel in relative if rel.startswith("modus/knowledge/")
                ),
                write_manifest=False,
            )
            reconcile_optional_config(paths)
            result.pop("_nextManifest").write(paths)
        # NOCA:broad-except(更新事务发生任何普通异常都必须回滚，随后重新抛出原始异常)
        except Exception:
            transaction.rollback()
            raise
    blocked = bool(result["userEditedFiles"] or result["conflictedFiles"])
    changed = bool(
        result["appliedFiles"]
        or result["addedFiles"]
        or result["removedFiles"]
        or result["removedDirectories"]
    )
    status = "partial" if blocked else "updated" if changed else "up-to-date"
    return {
        "status": status,
        "message": _message(status, old.framework_version, __version__, kind, result),
        "installedVersion": old.framework_version,
        "frameworkVersion": __version__,
        "changeKind": kind,
        "platforms": desired.platforms,
        **result,
    }


# 真实项目仅用于受约束读取，更新逻辑在临时副本中完整运行。
# 新模板涉及的已有路径也进入副本，预览能够发现潜在冲突。
def preview_update(
    root: str | Path, accept_major: bool = False, allow_downgrade: bool = False
) -> dict:
    """Dry-run :func:`run_update` against a scratch copy of the managed paths.

    Only manifest-tracked files are copied out, so the real project is never
    written; the returned report is the genuine update result marked ``dryRun``.
    """
    from ..knowledge_reader import read_bound_regular_bytes

    paths = ModusPaths.for_root(root)
    if not paths.manifest_path.is_file():
        return {
            "status": "error",
            "message": "项目尚未初始化（缺少 .modus/manifest.json）",
        }
    manifest = Manifest.read(paths)
    with tempfile.TemporaryDirectory(prefix="modus-update-preview.") as scratch:
        target = Path(scratch)
        rels = _manifest_paths(manifest)
        rels.update((paths.relative(paths.manifest_path), paths.relative(paths.config_path)))
        with tempfile.TemporaryDirectory(prefix="modus-preview-desired.") as desired_root:
            desired = _render_desired(ModusPaths.for_root(desired_root), manifest, paths)
            rels.update(_manifest_paths(desired))
        for rel in sorted(rels):
            source = paths.root / rel
            if source.is_file():
                raw = read_bound_regular_bytes(paths.root, source, max_bytes=16 * 1024 * 1024)
                destination = target / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
        # 目录退役预览只记录非受管子项的存在，不读取或复制用户脚本。
        legacy_directory = paths.root / ".modus/hooks"
        if any(entry.path.startswith(".modus/hooks/") for entry in manifest.files):
            if legacy_directory.is_dir() and not legacy_directory.is_symlink():
                preview_directory = target / ".modus/hooks"
                preview_directory.mkdir(parents=True, exist_ok=True)
                if any(paths.relative(child) not in rels for child in legacy_directory.iterdir()):
                    tempfile.mkdtemp(prefix="unmanaged-", dir=preview_directory)
        result = run_update(target, accept_major=accept_major, allow_downgrade=allow_downgrade)
    result["dryRun"] = True
    result["message"] = "[dry-run] " + result.get("message", "")
    return result


# 文件与区块共享路径集合，同一共享容器只需要一次事务快照。
def _manifest_paths(manifest: Manifest) -> set[str]:
    """Project the two ownership records onto their shared path identity."""
    return {entry.path for entry in manifest.files} | {entry.path for entry in manifest.sections}
