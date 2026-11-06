"""Inspect which narrative knowledge may be affected by source changes.

This service is intentionally read-only and independent of initialization analysis:
it combines explicit targets, source-location anchors, and a direct read of
*current* source into review candidates. It never imports or reads an
initialization bundle, so a sync check is exactly as
trustworthy as the source tree the agent already has checked out. The agent
remains responsible for reading current source and for performing any
compare-and-swap knowledge update.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from ..knowledge_identity import KnowledgePathIdentity
from ..knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ..paths import ModusPaths
from ..retrieval.stages.discovery import discover_markdown_files
from ..scope_models import SourceLocation
from ..skillmd import split_frontmatter
from ..source_anchors import check_location, document_locations, source_declarations
from .models import JsonObject
from .path_scope import relative_paths

_MAX_KNOWLEDGE_BYTES = 32 * 1024 * 1024
_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_DELIVERED_DIAGNOSTICS = 32
_VALID_VALIDATION_STATES = frozenset({"passed", "failed"})

__all__ = ["inspect_knowledge_impact", "sync_knowledge"]


@dataclass(frozen=True, slots=True)
class _DocumentImpact:
    """一份知识文档及需要回读的源码关联。"""

    candidate: JsonObject | None
    anchor_reviews: tuple[JsonObject, ...] = ()


# 影响检查只提供候选与证据缺口，失败验证不授权把新行为写成已确认知识。
def inspect_knowledge_impact(
    root: str,
    changed_files: Sequence[str] = (),
    *,
    targets: Sequence[str] = (),
    validation: str = "passed",
    _local: bool = False,
) -> JsonObject:
    """Return a deterministic, read-only knowledge-impact report."""
    if validation not in _VALID_VALIDATION_STATES:
        raise ValueError("validation 必须为 passed 或 failed")

    paths = ModusPaths.for_root(root)
    changed = relative_paths(paths, changed_files)
    selected_targets = relative_paths(paths, targets)
    if not _local:
        workspace_result = _delegate_workspace_if_needed(
            paths,
            changed,
            selected_targets,
            validation=validation,
        )
        if workspace_result is not None:
            return workspace_result

    diagnostics: list[JsonObject] = []
    candidates, anchor_reviews = _candidate_documents(
        paths,
        changed,
        selected_targets,
        diagnostics=diagnostics,
    )
    conflicts = _target_conflicts(paths, candidates)
    skipped: list[JsonObject] = []

    if validation == "failed":
        diagnostics.append(
            {
                "files": changed,
                "kind": "implementation-validation-failed",
                "reason": (
                    "实现验证失败；仍可维护已确立的事实和已记录的失败，但不能将未验证行为作为已确认结果"
                ),
            }
        )
    if changed and not candidates:
        skipped.append(
            {
                "files": changed,
                "reason": "没有可靠的知识目标，助手需先确定业务归属",
            }
        )

    return {
        "status": "partial" if conflicts else "noop",
        "mode": "agent-authored",
        "changedFiles": changed,
        "candidates": candidates,
        "lowConfidenceCandidates": [
            candidate["path"] for candidate in candidates if candidate["confidence"] == "path-only"
        ],
        "anchorReviewCandidates": anchor_reviews,
        "writes": [],
        "skipped": skipped,
        "conflicts": conflicts,
        "diagnostics": diagnostics[:_MAX_DELIVERED_DIAGNOSTICS],
        "diagnosticCount": len(diagnostics),
        "validation": validation,
        "message": (
            "只读影响检查完成。助手需评审需求、差异、测试与当前知识，再直接修订已有语义章节。"
        ),
    }


def sync_knowledge(
    root: str,
    changed_files: Sequence[str] = (),
    *,
    targets: Sequence[str] = (),
    validation: str = "passed",
    _local: bool = False,
) -> JsonObject:
    """Compatibility entry point for the historical knowledge-sync command."""
    return inspect_knowledge_impact(
        root,
        changed_files,
        targets=targets,
        validation=validation,
        _local=_local,
    )


# 工作区分派由专用服务处理，成员调用通过本地标记避免再次递归。
def _delegate_workspace_if_needed(
    paths: ModusPaths,
    changed: list[str],
    targets: list[str],
    *,
    validation: str,
) -> JsonObject | None:
    from ..config import ModusConfig

    try:
        config = ModusConfig.read_available(paths)
    except (OSError, ValueError):
        config = ModusConfig()
    if config.kind != "workspace":
        return None

    from ..workspace import sync_knowledge as sync_workspace

    workspace_sync = cast(Callable[..., JsonObject], sync_workspace)
    return workspace_sync(
        str(paths.root),
        changed,
        targets=targets,
        validation=validation,
    )


# 使用现有知识发现与身份规则；专题与模块共享锚点语义，不新增持久索引。
def _candidate_documents(
    paths: ModusPaths,
    changed: Sequence[str],
    targets: Sequence[str],
    *,
    diagnostics: list[JsonObject],
) -> tuple[list[JsonObject], list[JsonObject]]:
    from .module_meta import load_module

    explicit_targets = set(targets)
    changed_paths = set(changed)
    source_cache: dict[str, list[str] | None] = {}
    declaration_cache: dict[str, list[JsonObject] | None] = {}
    candidates: dict[str, JsonObject] = {}
    anchor_reviews: list[JsonObject] = []
    for path in discover_markdown_files(paths, "project", scan_issues=diagnostics):
        document = paths.relative(path)
        identity = KnowledgePathIdentity.classify(paths, document)
        if identity is None:
            continue
        try:
            if identity.module is not None and identity.domain is not None:
                # 保留模块的物理身份检查，文件头不能改写业务归属。
                load_module(paths, identity.domain, identity.module, diagnostics=diagnostics)
            text = read_bound_regular_text(paths.root, path, max_bytes=_MAX_KNOWLEDGE_BYTES)
        except (BoundKnowledgeReadError, OSError, ValueError) as exc:
            diagnostics.append(
                {"path": document, "kind": "knowledge-unavailable", "reason": str(exc)}
            )
            continue
        locations, issues = document_locations(paths, path, text)
        diagnostics.extend(issues)
        frontmatter, _ = split_frontmatter(text)
        anchors = frontmatter.get("anchors")
        support_paths = anchors.get("paths", []) if isinstance(anchors, dict) else []
        if not isinstance(support_paths, list) or any(
            not isinstance(item, str) for item in support_paths
        ):
            diagnostics.append(
                {
                    "path": document,
                    "kind": "anchor_metadata_invalid",
                    "reason": "anchors.paths 必须为路径列表",
                }
            )
            support_paths = []
        impact = _document_impact(
            paths,
            document,
            str(identity.scope_ref.value) if identity.module and identity.scope_ref else None,
            locations,
            support_paths,
            changed_paths=changed_paths,
            explicit_targets=explicit_targets,
            source_cache=source_cache,
            declaration_cache=declaration_cache,
        )
        if impact.candidate is not None:
            candidates[document] = impact.candidate
            anchor_reviews.extend(impact.anchor_reviews)

    for target in targets:
        candidates.setdefault(target, _explicit_candidate(target))
    return [candidates[key] for key in sorted(candidates)], anchor_reviews


def _document_impact(
    paths: ModusPaths,
    document: str,
    module_id: str | None,
    locations: Sequence[SourceLocation],
    support_paths: Sequence[str],
    *,
    changed_paths: set[str],
    explicit_targets: set[str],
    source_cache: dict[str, list[str] | None],
    declaration_cache: dict[str, list[JsonObject] | None],
) -> _DocumentImpact:
    location_paths = {location.path for location in locations} & changed_paths
    file_paths = set(support_paths) & changed_paths
    explicitly_selected = document in explicit_targets
    if not explicitly_selected and not location_paths and not file_paths:
        return _DocumentImpact(candidate=None)

    reviews: list[JsonObject] = []
    for location in locations:
        if location.path not in changed_paths and not explicitly_selected:
            continue
        if location.path not in source_cache:
            source_cache[location.path] = _read_source_lines(paths, location.path)
        lines = source_cache[location.path]
        if lines is None:
            review: JsonObject = {
                "disposition": "anchor-symbol-missing",
                "detail": "源码缺失或不可读，需核对当前路径",
            }
        else:
            if location.path not in declaration_cache:
                declaration_cache[location.path] = source_declarations(location.path, lines)
            check = check_location(location, declaration_cache[location.path])
            if check.finding == "current":
                continue
            review = {
                "disposition": check.finding.replace("_", "-")
                if check.finding.startswith("anchor_")
                else "anchor-" + check.finding.replace("_", "-"),
                "detail": check.detail,
            }
            if check.start_line is not None:
                review["actualLine"] = check.start_line
            if check.candidate_lines:
                review["candidateLines"] = list(check.candidate_lines[:10])
        reviews.append({"path": location.path, "anchorSymbol": location.symbol, **review})

    reasons: list[str] = []
    if location_paths:
        reasons.append("source-location-path")
    if file_paths:
        reasons.append("source-path")
    if reviews:
        reasons.append("source-location-symbol")
    if explicitly_selected:
        reasons.append("explicit-target")
    return _DocumentImpact(
        candidate={
            "path": document,
            "moduleId": module_id,
            "confidence": "explicit"
            if explicitly_selected
            else "symbol"
            if reviews
            else "path-only",
            "reasons": reasons,
            "matchedSourcePaths": sorted(location_paths | file_paths),
            "matchedSymbols": reviews,
        },
        anchor_reviews=tuple(
            {
                "moduleId": module_id,
                "document": document,
                **review,
                "reason": "源码关联需要回读；核对当前声明、正文及文件头后再判断同步完成",
            }
            for review in reviews
        ),
    )


# 统一读取边界和大小上限，单次检查共享源码缓存。
def _read_source_lines(paths: ModusPaths, relative_path: str) -> list[str] | None:
    try:
        return read_bound_regular_text(
            paths.root, paths.root / relative_path, max_bytes=_MAX_SOURCE_BYTES
        ).splitlines()
    except (BoundKnowledgeReadError, OSError, ValueError):
        return None


# 候选目标不可读或缺失时报告冲突，不能悄悄创建替代文档。
def _target_conflicts(paths: ModusPaths, candidates: Sequence[JsonObject]) -> list[JsonObject]:
    conflicts: list[JsonObject] = []
    for candidate in candidates:
        target = str(candidate["path"])
        try:
            text = _read(paths, target)
        except (BoundKnowledgeReadError, OSError, ValueError) as exc:
            conflicts.append({"path": target, "reason": str(exc)})
            continue
        if text is None:
            conflicts.append({"path": target, "reason": "知识目标缺失"})
    return conflicts


# 缺失与其他读取故障分开处理，保留错误语义供上层展示。
def _read(paths: ModusPaths, relative: str) -> str | None:
    try:
        return read_bound_regular_text(
            paths.root,
            paths.root / relative,
            max_bytes=_MAX_KNOWLEDGE_BYTES,
        )
    except BoundKnowledgeReadError as exc:
        if exc.kind == "missing":
            return None
        raise


# 显式目标代表用户选择，不推断额外的源码匹配证据。
def _explicit_candidate(target: str) -> JsonObject:
    return {
        "path": target,
        "moduleId": None,
        "confidence": "explicit",
        "reasons": ["explicit-target"],
        "matchedSourcePaths": [],
        "matchedSymbols": [],
    }
