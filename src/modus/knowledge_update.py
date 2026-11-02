"""显式知识更新：整批预检、逐文件 CAS 与可恢复的部分成功报告。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from .knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from .knowledge_write_session import TeamStandardWriteMode, delete_document, write_document
from .paths import ModusPaths

_DigestMap: TypeAlias = Mapping[str, str | None]
_Outcome: TypeAlias = Literal["written", "unchanged", "deleted", "absent", "conflict"]


def _valid_digest(value: object) -> bool:
    return (
        value is None or isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    )


def _validate_knowledge_target(target: str) -> None:
    parts = target.split("/")
    if (
        parts[:2] != ["modus", "knowledge"]
        or any(part in {"", ".", ".."} for part in parts)
        or "\\" in target
        or "\x00" in target
        or not target.endswith(".md")
    ):
        raise ValueError(f"知识路径不安全： {target}")


# null 表示预期不存在，摘要字符串表示观察版本，不能混为可选无条件写入。
def _validated_hashes(expected_hashes: object) -> _DigestMap:
    if expected_hashes is None:
        return {}
    if not isinstance(expected_hashes, Mapping) or not all(
        isinstance(key, str) and _valid_digest(value) for key, value in expected_hashes.items()
    ):
        raise ValueError("expectedHashes 必须将路径映射到 SHA-256 摘要或 null")
    return expected_hashes


# 每个文档有独立结果，冲突上下文只与失败项对应。
# 批量报告不宣称事务性回滚，已完成写入会明确保留。
@dataclass(slots=True)
class _UpdateLedger:
    """按文档保存独立结果，保留部分成功与冲突的边界。"""

    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)
    conflicts: list[dict[str, str]] = field(default_factory=list)

    def record(self, outcome: _Outcome, target: str, conflict: dict[str, str] | None) -> None:
        if outcome == "conflict":
            if conflict is None:
                raise AssertionError("冲突结果需要诊断上下文")
            self.conflicts.append(conflict)
            return
        if conflict is not None:
            raise AssertionError("成功结果不能包含冲突上下文")
        buckets = {
            "written": self.written,
            "unchanged": self.unchanged,
            "deleted": self.deleted,
            "absent": self.absent,
        }
        buckets[outcome].append(target)


# 相同内容先返回 unchanged，使失败后的原请求可安全重试。
# 已有不同内容若没有观察摘要，先返回冲突而非自动接管。
# 真正写入仍在文档锁内重新校验，预读只用于决定报告。
def _write_one(
    paths: ModusPaths,
    target: str,
    content: str,
    hashes: _DigestMap,
    *,
    allow_team_standard: bool,
    initialize_team_standard: bool,
) -> tuple[_Outcome, dict[str, str] | None]:
    try:
        try:
            before = read_bound_regular_text(
                paths.root, paths.root / target, max_bytes=8 * 1024 * 1024
            )
        except BoundKnowledgeReadError as exc:
            if exc.kind != "missing":
                raise
            before = None
        if before == content:
            return "unchanged", None
        if before is not None and target not in hashes:
            return "conflict", {
                "path": target,
                "operation": "write",
                "reason": "已有文档需要读取时记录的内容摘要",
                "digest": hashlib.sha256(before.encode()).hexdigest(),
            }
        write_document(
            paths,
            target,
            content,
            expected_hash=hashes.get(target),
            allow_human=True,
            allow_team_standard=allow_team_standard,
            initialize_team_standard=initialize_team_standard,
        )
        return "written", None
    except (OSError, ValueError, RuntimeError) as exc:
        return "conflict", {"path": target, "operation": "write", "reason": str(exc)}


# 已不存在是幂等成功分支，不应因重复退役变成错误。
def _delete_one(
    paths: ModusPaths,
    target: str,
    hashes: _DigestMap,
) -> tuple[_Outcome, dict[str, str] | None]:
    try:
        digest = hashes[target]
        if not isinstance(digest, str):  # Guaranteed by ``validate_update_input``.
            raise ValueError(f"删除需要读取时记录的内容摘要： {target}")
        deleted = delete_document(paths, target, expected_hash=digest)
        return ("deleted" if deleted else "absent"), None
    except (OSError, ValueError, RuntimeError) as exc:
        return "conflict", {"path": target, "operation": "delete", "reason": str(exc)}


# 整批形状在首个副作用前验证，类型错误不能造成半份请求已落地。
# 删除只允许逐个明确路径，通配符无法表达用户实际观察的版本。
def validate_update_input(
    documents: object,
    expected_hashes: object,
    deletions: object,
    allow_team_standard: object,
    initialize_team_standard: object = False,
) -> None:
    """在首个写入前检查整批形状；执行期冲突仍按文档报告。"""
    if not isinstance(documents, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in documents.items()
    ):
        raise ValueError("documents 必须将 Markdown 路径映射到完整正文")
    hashes = _validated_hashes(expected_hashes)
    if (
        not isinstance(deletions, Sequence)
        or isinstance(deletions, (str, bytes))
        or not all(isinstance(target, str) for target in deletions)
    ):
        raise ValueError("deletions 必须为单个 Markdown 路径组成的列表")
    TeamStandardWriteMode.from_flags(
        initialize=initialize_team_standard, maintain=allow_team_standard
    )
    if len(set(deletions)) != len(deletions):
        raise ValueError("deletions 不能包含重复路径")
    if set(documents) & set(deletions):
        raise ValueError("同一请求不能同时写入和删除同一文档")
    for target in [*documents, *deletions]:
        _validate_knowledge_target(target)
    for target in deletions:
        if any(character in target for character in "*?[]"):
            raise ValueError(f"删除需要单个路径，不能使用匹配模式： {target}")
        if not isinstance(hashes.get(target), str):
            raise ValueError(f"删除需要读取时记录的内容摘要： {target}")


# 写入有冲突时延迟全部退役，确保旧内容在替代失败后仍可访问。
# 不同文档的已完成写入不回滚，partial 报告是调用者重试的依据。
def update_knowledge(
    root: str,
    documents: Mapping[str, str],
    *,
    expected_hashes: Mapping[str, str | None] | None = None,
    deletions: Sequence[str] = (),
    allow_team_standard: bool = False,
    initialize_team_standard: bool = False,
) -> dict[str, Any]:
    """写入调用方已完成的 Markdown，仅改变本次明确选中的文档。

    已有正文使用创作时观察的摘要，新文件以 None 表达预期不存在。
    退役必须提供原摘要，且只在本批写入全部成功后执行。独立文件已完成的
    写入不回滚；调用方根据逐项结果回读冲突，不能把 partial 当作整批失败。

    首次填充与人工维护分别授权：initialize_team_standard 仅允许缺失或
    精确框架种子，allow_team_standard 允许明确委托的既有正文修订。
    两者互斥，均不跳过文档锁内的所有权和内容摘要检查。
    """
    validate_update_input(
        documents, expected_hashes, deletions, allow_team_standard, initialize_team_standard
    )
    paths = ModusPaths.for_root(root)
    hashes = expected_hashes or {}
    ledger = _UpdateLedger()
    for target, content in documents.items():
        outcome, conflict = _write_one(
            paths,
            target,
            content,
            hashes,
            allow_team_standard=allow_team_standard,
            initialize_team_standard=initialize_team_standard,
        )
        ledger.record(outcome, target, conflict)
    deferred = list(deletions) if ledger.conflicts else []
    if not deferred:
        for target in deletions:
            outcome, conflict = _delete_one(paths, target, hashes)
            ledger.record(outcome, target, conflict)
    return {
        "status": (
            "partial"
            if ledger.conflicts
            else "completed"
            if ledger.written or ledger.deleted
            else "noop"
        ),
        "writes": ledger.written,
        "unchanged": ledger.unchanged,
        "deleted": ledger.deleted,
        "alreadyAbsent": ledger.absent,
        "deferredDeletions": deferred,
        "conflicts": ledger.conflicts,
    }


__all__ = ["update_knowledge", "validate_update_input"]
