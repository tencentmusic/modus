"""知识发布边界：所有权决定可写范围，文档锁与 CAS 保护观察版本。"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from enum import Enum
from pathlib import Path
from typing import Final, Self

from .artifacts_io import (
    atomic_write_text,
    required_reentrant_file_lock,
)
from .atomic_writes import (
    _assert_atomic_write_parent_binding,
    _assert_portable_atomic_parent,
    _is_link_or_reparse,
    _portable_parent_snapshot,
)
from .knowledge_reader import (
    BoundKnowledgeReadError,
    _supports_bound_reads,
    read_bound_regular_text,
)
from .paths import ModusPaths

_CAS_UNSET: Final = object()


class KnowledgeWriteSessionError(RuntimeError):
    """写入或退役未满足路径、所有权、锁或 CAS 条件。"""


class TeamStandardWriteMode(Enum):
    """将兼容协议的两个权限字段收敛为互斥模式，不从文件状态推导授权。"""

    PROTECTED = "protected"
    INITIALIZE = "initialize"
    MAINTAIN = "maintain"

    @classmethod
    def from_flags(cls, *, initialize: object, maintain: object) -> Self:
        """批量预检与直接写入共用此边界；无效权限在任何副作用前失败。"""
        if not isinstance(maintain, bool):
            raise ValueError("allowTeamStandard 必须为布尔值")
        if not isinstance(initialize, bool):
            raise ValueError("initializeTeamStandard 必须为布尔值")
        if initialize and maintain:
            raise ValueError("首次填充与人工维护不能同时启用；请选择一种 team-standard 写入方式")
        if initialize:
            return cls.INITIALIZE
        if maintain:
            return cls.MAINTAIN
        return cls.PROTECTED


def _read_existing(paths: ModusPaths, target: Path) -> tuple[str, str | None]:
    try:
        text = read_bound_regular_text(paths.root, target)
    except BoundKnowledgeReadError as exc:
        if exc.kind == "missing":
            return "", None
        raise KnowledgeWriteSessionError(f"知识树读取目标不安全： {target}: {exc}") from exc
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


# None 表示预期目标不存在；它与内部“未指定条件”哨兵具有不同语义。
def _assert_cas(target: Path, current_hash: str | None, expected_hash: str | None | object) -> None:
    if expected_hash is _CAS_UNSET:
        return
    if current_hash != expected_hash:
        raise KnowledgeWriteSessionError(
            f"知识树内容哈希不匹配：{target}：预期 {expected_hash}，实际 {current_hash}"
        )


def _is_team_standard_seed(text: str) -> bool:
    """只接受精确的随包种子；清单收录的人工内容不因此获得种子身份。"""
    from .knowledge_seeds import is_constraint_seed

    return is_constraint_seed("modus/knowledge/constraint/team-standard.md", text)


def write_document(
    paths: ModusPaths,
    target: str,
    text: str,
    *,
    expected_hash: str | None,
    allow_human: bool = False,
    initialize_team_standard: bool = False,
    allow_team_standard: bool = False,
) -> Path:
    """按所有权与读时摘要写入；元数据和缓存均不授予修改权限。

    首次 init 作者通过更新入口显式选择 initialize_team_standard，只能填充
    缺失文件或精确种子。后续人工正文维护使用独立授权，普通 reinit/update/
    sync 工作流不自动启用任一种权限。锁内复查种子与摘要，防止调查后的人工作品被覆盖。
    """
    from .knowledge_identity import _target_parts

    team_standard_mode = TeamStandardWriteMode.from_flags(
        initialize=initialize_team_standard, maintain=allow_team_standard
    )
    parts = _target_parts(paths, target)
    if parts is None or parts[:2] != ("modus", "knowledge") or not target.endswith(".md"):
        raise KnowledgeWriteSessionError(f"知识目标不安全： {target}")
    human = (
        parts[2:3] == ("constraint",)
        or target.endswith("/module-map.md")
        or ("references" in parts and "business" in parts)
    )
    if human and not allow_human:
        raise KnowledgeWriteSessionError(f"自动同步不能修改人工知识： {target}")
    destination = paths.root / target
    with required_reentrant_file_lock(paths.knowledge_document_lock(destination)):
        existing, digest = _read_existing(paths, destination)
        _assert_cas(destination, digest, expected_hash)
        needs_write = digest is None or existing != text
        if parts[2:] == ("constraint", "team-standard.md") and needs_write:
            if team_standard_mode is TeamStandardWriteMode.PROTECTED:
                raise KnowledgeWriteSessionError(
                    "team-standard.md 仅在首次初始化时生成；后续修改需要用户明确要求维护"
                )
            if (
                team_standard_mode is TeamStandardWriteMode.INITIALIZE
                and digest is not None
                and not _is_team_standard_seed(existing)
            ):
                raise KnowledgeWriteSessionError(
                    "team-standard.md 已包含保留内容；首次初始化不能覆盖它"
                )
        if needs_write:
            atomic_write_text(destination, text)
    return destination


_DELETABLE_KINDS: Final = frozenset(
    {
        "module-scope-skill",
        "domain-generated-reference",
        "domain-scope-skill",
        "workspace-generated-reference",
    }
)
_DELETE_MAX_BYTES: Final = 32 * 1024 * 1024


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _open_delete_parent(parent: Path) -> int:
    """Bind existing ancestors; deleting never creates a missing directory."""
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NONBLOCK")
        or os.unlink not in os.supports_dir_fd
    ):
        raise KnowledgeWriteSessionError("当前平台不支持安全删除知识")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(parent.anchor, flags)
    try:
        for part in parent.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        _assert_atomic_write_parent_binding(parent, descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _hash_delete_candidate(
    descriptor: int,
    destination: Path,
) -> tuple[os.stat_result, str]:
    """Hash one bound regular file and prove it stayed stable while read."""

    observed = os.fstat(descriptor)
    if not stat.S_ISREG(observed.st_mode):
        raise KnowledgeWriteSessionError(f"删除目标不是常规文件： {destination}")
    if observed.st_size > _DELETE_MAX_BYTES:
        raise KnowledgeWriteSessionError(f"删除目标超过字节预算： {destination}")
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(descriptor, 64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > _DELETE_MAX_BYTES:
            raise KnowledgeWriteSessionError(f"删除目标增长并超过字节预算： {destination}")
        digest.update(chunk)
    if _file_identity(observed) != _file_identity(os.fstat(descriptor)):
        raise KnowledgeWriteSessionError(f"删除目标在读取过程中发生变化： {destination}")
    return observed, digest.hexdigest()


def _unlink_verified_candidate(
    parent_fd: int | None,
    destination: Path,
    observed: os.stat_result,
    *,
    parent_snapshot: tuple[tuple[int, int], ...] | None = None,
) -> None:
    """Rebind the candidate by name immediately before unlinking it."""

    if parent_fd is None:
        _assert_portable_atomic_parent(destination.parent, parent_snapshot)
        named = destination.lstat()
    else:
        _assert_atomic_write_parent_binding(destination.parent, parent_fd)
        named = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        _is_link_or_reparse(named)
        or not stat.S_ISREG(named.st_mode)
        or _file_identity(named) != _file_identity(observed)
    ):
        raise KnowledgeWriteSessionError(f"删除目标在移除前发生变化： {destination}")
    if parent_fd is None:
        destination.unlink()
        return
    os.unlink(destination.name, dir_fd=parent_fd)
    try:
        os.fsync(parent_fd)
    except OSError:
        pass  # Match atomic writes' best-effort directory durability.


def _delete_portable_regular_file(destination: Path, expected_hash: str) -> bool:
    """在文档锁内用路径快照与原始字节摘要核验退役目标。

    Windows 删除前必须先关闭读取句柄；关闭后再次核对路径身份，
    发现目标被替换时保留新文件，与 POSIX 的比较后删除边界一致。
    """
    destination = Path(os.path.abspath(destination))
    try:
        parents = _portable_parent_snapshot(destination.parent)
        named = destination.lstat()
        if _is_link_or_reparse(named) or not stat.S_ISREG(named.st_mode):
            raise KnowledgeWriteSessionError(f"删除目标不是常规文件： {destination}")
        descriptor = os.open(
            destination,
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOINHERIT", 0),
        )
    except FileNotFoundError:
        return False
    try:
        observed, digest = _hash_delete_candidate(descriptor, destination)
        # Windows 的 stat 与 fstat 对 ctime 的含义可能不同（CPython #157671）。
        # 跨 API 只比较共有身份；读取期间仍比较完整 fstat，移除前比较完整 lstat。
        if _file_identity(named)[:4] != _file_identity(observed)[:4]:
            raise KnowledgeWriteSessionError(f"删除目标在打开时发生变化： {destination}")
    finally:
        os.close(descriptor)
    _assert_cas(destination, digest, expected_hash)
    _unlink_verified_candidate(None, destination, named, parent_snapshot=parents)
    return True


def _delete_bound_regular_file(destination: Path, expected_hash: str) -> bool:
    """Compare and unlink under one bound parent and the caller's document lock.

    Cooperative Modus writers are serialized. Rechecking the named inode and
    its content metadata detects external replacements observed before unlink;
    POSIX does not provide an atomic compare-and-unlink against external editors.
    """
    if not _supports_bound_reads() or os.unlink not in os.supports_dir_fd:
        return _delete_portable_regular_file(destination, expected_hash)
    try:
        parent_fd = _open_delete_parent(destination.parent)
    except FileNotFoundError:
        return False
    file_fd: int | None = None
    try:
        try:
            file_fd = os.open(
                destination.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return False
        observed, digest = _hash_delete_candidate(file_fd, destination)
        _assert_cas(destination, digest, expected_hash)
        _unlink_verified_candidate(parent_fd, destination, observed)
        return True
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


# 删除与写入共享文档锁；内容摘要匹配之外，还需证明路径类别允许退役。
def delete_document(paths: ModusPaths, target: str, *, expected_hash: str) -> bool:
    """Delete one explicitly retired generated document; retain human material."""
    from .knowledge_identity import KnowledgePathIdentity

    if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
        raise KnowledgeWriteSessionError("删除需要读取时记录的 SHA-256 内容摘要")
    identity = KnowledgePathIdentity.classify(paths, target)
    if identity is None or identity.path_kind not in _DELETABLE_KINDS:
        raise KnowledgeWriteSessionError(f"删除目标不是生成知识： {target}")
    destination = paths.root / target
    with required_reentrant_file_lock(paths.knowledge_document_lock(destination)):
        # Recheck ownership/path shape after acquiring the shared writer lock.
        identity = KnowledgePathIdentity.classify(paths, target)
        if identity is None or identity.path_kind not in _DELETABLE_KINDS:
            raise KnowledgeWriteSessionError(f"删除目标不是生成知识： {target}")
        return _delete_bound_regular_file(destination, expected_hash)


__all__ = [
    "KnowledgeWriteSessionError",
    "TeamStandardWriteMode",
    "delete_document",
    "write_document",
]
