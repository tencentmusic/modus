"""`modus init`: transactional project installation and platform projection."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .. import __version__, git_hygiene
from ..config import ModusConfig
from ..manifest import Manifest, serialized_install
from ..paths import ModusPaths
from ..platforms.sections import section_markers
from ..scaffold import scaffold_project
from ..versioning import bump_kind
from .install_state import (
    InitConflictError,
    InitFailedError,
    InitRollbackError,
    InstallTransaction,
    unsafe_target_issue,
    validate_install_root,
)

__all__ = [
    "InitConflictError",
    "InitFailedError",
    "InitRollbackError",
    "run_init",
    "run_workspace_init",
]


# 共享文本只能合并没有同名标记的区域。
# 重复、缺失或倒置标记都视为冲突，避免覆盖不明确的所有权。
def _section_conflict(target: Path, marker: str) -> str | None:
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"{target.name} 无法安全合并为 UTF-8 文本： {exc}"
    begin, end = section_markers(marker)
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 and end_count == 0:
        return None
    if begin_count != 1 or end_count != 1 or text.index(begin) >= text.index(end):
        return f"{target.name} 存在不完整或重复的 Modus 标记"
    return f"{target.name} 存在同名标记的非受管区块"


# 先收集全部冲突，再决定是否写入，避免安装一半才发现阻塞。
# 种子规范允许复用；其他已有非受管文件不得被初始化覆盖。
# 孤立配置读取失败也必须阻止写入，故在此边界汇总任意解析异常。
def _fresh_install_conflicts(paths: ModusPaths, desired: Manifest) -> list[str]:
    conflicts: list[str] = []
    seed_paths = {
        paths.relative(paths.global_standard),
        paths.relative(paths.team_standard),
    }
    section_paths = {entry.path for entry in desired.sections}
    for entry in desired.files:
        target = paths.root / entry.path
        issue = unsafe_target_issue(paths.root, target)
        if issue:
            conflicts.append(issue)
            continue
        if not target.exists() or entry.path in seed_paths:
            continue
        if entry.path in section_paths:
            continue
        conflicts.append(f"{entry.path}：该路径已存在非受管文件")

    for section_entry in desired.sections:
        target = paths.root / section_entry.path
        issue = unsafe_target_issue(paths.root, target)
        if issue:
            conflicts.append(issue)
            continue
        if target.exists():
            issue = _section_conflict(target, section_entry.marker)
            if issue:
                conflicts.append(f"{section_entry.path}: {issue}")

    if paths.config_path.exists():
        issue = unsafe_target_issue(paths.root, paths.config_path)
        if issue:
            conflicts.append(issue)
        else:
            try:
                ModusConfig.read(paths)
            # NOCA:broad-except(已有配置读取失败必须阻止覆盖，并报告原始冲突原因)
            except Exception as exc:  # invalid orphan config must never be overwritten
                conflicts.append(f".modus/config.yaml：无法安全复用已有配置： {exc}")
    return sorted(set(conflicts))


# 回滚集合同时覆盖新旧清单中的路径，防止重新初始化遗漏旧资产。
# 工作区导航和 Git 忽略规则也纳入事务快照。
# 去重保留顺序，使快照和回滚处理具有稳定次序。
def _planned_targets(
    paths: ModusPaths,
    desired: Manifest,
    previous: Manifest | None,
    hygiene_preflight: dict,
    *,
    kind: str = "project",
    workspace_members: list[dict] | None = None,
) -> list[Path]:
    relative_paths = {
        *(entry.path for entry in desired.files),
        *(entry.path for entry in desired.sections),
    }
    if previous is not None:
        relative_paths.update(entry.path for entry in previous.files)
        relative_paths.update(entry.path for entry in previous.sections)
    targets = [paths.root / rel for rel in sorted(relative_paths)]
    targets.extend((paths.config_path, paths.manifest_path))
    if kind == "workspace":
        from ..workspace import MAP_NAMES

        targets.extend(
            (
                paths.root / ".gitignore",
                *(paths.workspace_generated_map(name) for name in MAP_NAMES),
                *(
                    paths.workspace_member_doc(member["repositoryId"])
                    for member in (workspace_members or [])
                ),
            )
        )
    else:
        targets.append(paths.domain_dir / ".gitkeep")
    if hygiene_preflight.get("status") != "not_git_repo":
        targets.append(Path(hygiene_preflight["gitRoot"]) / ".gitignore")
    return list(dict.fromkeys(targets))


# 已有安装只能同版本重新投影；升级必须经过更新服务。
# 清单是所有权依据，读取异常不能降级为全新安装。
def _load_previous_manifest(paths: ModusPaths) -> Manifest | None:
    if not paths.manifest_path.exists():
        return None
    if paths.manifest_path.is_symlink() or not paths.manifest_path.is_file():
        raise InitConflictError([".modus/manifest.json：清单必须是常规文件"])
    try:
        manifest = Manifest.read(paths)
    # NOCA:broad-except(已有清单是所有权依据，任何读取故障都阻止初始化并保留异常链)
    except Exception as exc:
        raise InitConflictError([f".modus/manifest.json：无法读取已有清单： {exc}"]) from exc
    kind = bump_kind(manifest.framework_version, __version__)
    if kind == "downgrade":
        raise InitConflictError(
            [
                f"项目由更新版本的 Modus 初始化：已安装={manifest.framework_version}, current={__version__}"
            ]
        )
    if kind != "none":
        raise InitConflictError(
            [f"现有资产需通过受保护的更新流程升级：框架={manifest.framework_version}"],
        )
    return manifest


# 先在临时目录构造期望资产，预检成功才触碰真实项目。
# 事务快照覆盖文件和 Git 索引，失败时恢复原始状态。
# 清单最后写入，作为安装完成的持久标记。
# 外层捕获所有普通异常是回滚边界，回滚失败则保留独立错误类型。
@serialized_install
def run_init(
    root: str | Path,
    platforms: list[str],
    *,
    kind: str = "project",
    workspace_members: list[dict] | None = None,
) -> dict:
    """Install Modus into ``root`` as one all-or-nothing transaction.

    Conflicts are collected up front and abort before the first write; any
    failure mid-install rolls every touched path back to its prior bytes and
    raises :class:`InitFailedError`. The manifest is written last, so its
    presence is the durable commit marker for a completed install.
    """
    paths = validate_install_root(root)
    if kind not in {"project", "workspace"}:
        raise ValueError(f"未知的 Modus 类型： {kind!r}")
    if kind == "workspace" and len(workspace_members or []) < 2:
        raise ValueError("工作区初始化需要至少两个已确认成员")
    if kind == "project" and workspace_members:
        raise ValueError("项目初始化不能接收工作区成员")
    previous = _load_previous_manifest(paths)

    with tempfile.TemporaryDirectory(prefix="modus-init-desired.") as scratch:
        desired = scaffold_project(
            scratch,
            platforms,
            kind=kind,
            workspace_members=workspace_members,
        )
        # 首次安装额外检查非受管资产冲突，已有安装交由清单约束。
        if previous is None:
            conflicts = _fresh_install_conflicts(paths, desired)
            if conflicts:
                raise InitConflictError(conflicts)

        # 忽略规则不可安全写入时提前退出，避免生成会被意外提交的本地状态。
        hygiene_preflight = git_hygiene.preflight_local_state_hygiene(paths)
        if hygiene_preflight.get("status") == "blocked":
            raise InitConflictError(
                [
                    "无法更新 .gitignore，未写入任何文件： "
                    f"{hygiene_preflight.get('message', '无法安全写入忽略规则')}"
                ]
            )

        targets = _planned_targets(
            paths,
            desired,
            previous,
            hygiene_preflight,
            kind=kind,
            workspace_members=workspace_members,
        )
        unsafe = [
            issue
            for target in targets
            if target.is_relative_to(paths.root)
            for issue in [unsafe_target_issue(paths.root, target)]
            if issue
        ]
        if unsafe:
            raise InitConflictError(sorted(set(unsafe)))
        # 索引快照必须在首次真实写入前取得，才能恢复原有暂存状态。
        index_snapshot = git_hygiene.snapshot_local_state_index(paths)
        transaction = InstallTransaction(paths, targets, index_snapshot)

        try:
            manifest = scaffold_project(
                paths.root,
                platforms,
                write_manifest=False,
                kind=kind,
                workspace_members=workspace_members,
            )
            hygiene = (
                git_hygiene.ensure_workspace_local_state_ignored(paths)
                if kind == "workspace"
                else git_hygiene.untrack_local_state(paths)
            )
            if hygiene.get("status") == "blocked":
                raise OSError(hygiene.get("message") or "无法更新 .gitignore 以排除本地缓存目录")
            # The manifest is the commit marker and is always written last.
            manifest.write(paths)
        # NOCA:broad-except(所有安装故障都必须触发回滚，成功恢复后才报告初始化失败)
        except Exception as exc:
            try:
                transaction.rollback()
            except InitRollbackError:
                raise
            # 只有回滚正常结束才报告已恢复，回滚异常不能被此消息掩盖。
            raise InitFailedError(f"Modus 初始化失败，已完成回滚： {exc}") from exc

    return {
        "root": str(paths.root),
        "platforms": platforms,
        "managedFiles": len(manifest.files),
        "managedSections": len(manifest.sections),
        "manifest": paths.relative(paths.manifest_path),
        "gitHygiene": hygiene,
        "kind": kind,
        "knowledgeMode": "canonical" if kind == "project" else "workspace",
        **(
            {"members": [member["id"] for member in workspace_members or []]}
            if kind == "workspace"
            else {}
        ),
    }


# 先确认并规范成员，再安装工作区自身资产。
# 成员结果只是只读引用状态，不隐式初始化任何成员。
def run_workspace_init(
    root: str | Path,
    platforms: list[str],
    member_paths: list[str],
) -> dict:
    """Initialize only the workspace root and reference every member read-only."""
    from ..workspace import inspect_workspace_knowledge, normalize_members

    paths = validate_install_root(root)
    members = normalize_members(paths.root, member_paths)
    workspace_result = run_init(
        paths.root,
        platforms,
        kind="workspace",
        workspace_members=members,
    )
    inventory = inspect_workspace_knowledge(paths.root)
    # 以规范成员 ID 关联盘点结果，避免依赖遍历顺序。
    observations = {item["id"]: item for item in inventory["members"]}
    member_results = [
        {
            "root": str(paths.root / member["path"]),
            "kind": "project",
            "status": "referenced",
            "readOnly": True,
            "memberId": member["id"],
            "installed": observations[member["id"]]["installed"],
            "knowledgeState": observations[member["id"]]["knowledge"]["state"],
        }
        for member in members
    ]
    return {
        **workspace_result,
        "memberResults": member_results,
        "workspace": str(paths.root),
        "knowledgeInventory": inventory,
    }
