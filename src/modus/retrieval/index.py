"""Compose discovery, selection, parsing, and lexical indexing stages."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..paths import ModusPaths
from .settings import RetrievalSettings, retrieval_settings
from .stages.documents import _bind_parent_routers, scan_documents
from .stages.lexical import build_lexical_index
from .stages.lexical import tokenize as tokenize
from .stages.ranking import search_index as search_index
from .stages.sections import INDEX_SCHEMA_VERSION as INDEX_SCHEMA_VERSION
from .stages.sections import MAX_DOCUMENT_BYTES as MAX_DOCUMENT_BYTES
from .stages.sections import MAX_INDEX_BYTES as MAX_INDEX_BYTES
from .stages.sections import MAX_SCAN_BYTES as MAX_SCAN_BYTES
from .stages.sections import build_link_index
from .stages.sections import is_rule_evidence as is_rule_evidence
from .stages.sections import markdown_files as markdown_files
from .stages.selection import select_link_targets, select_query_targets

MAX_DISCOVERED_DOCUMENTS = 512

# Transitional private alias for integrations that predate the public export.
_markdown_files = markdown_files
_settings = retrieval_settings


# 各阶段的缺口累积到同一报告，局部成功不消除先前的 partial 状态。
# 链接索引和词法索引都消费同一次文档扫描，避免观察到不同版本。
def scan_index(
    paths: ModusPaths,
    *,
    kind: str,
    query: str = "",
    explicit_paths: Sequence[str] = (),
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    """Build an ephemeral index from the current on-disk knowledge tree.

    No persistent service or stale cache is involved.  Every stage is bounded,
    deterministic, and returns diagnostics in ``scanIssues`` instead of hiding a
    partial result behind an exception.
    """

    discovery_issues: list[dict[str, Any]] = []
    targets = _markdown_files(
        paths, kind, scan_issues=discovery_issues, deadline_monotonic=deadline_monotonic
    )
    available = {paths.relative(target): target for target in targets}
    partial = len(targets) > MAX_DISCOVERED_DOCUMENTS or bool(discovery_issues)
    selection: dict[str, Any] = {"queryScoped": False, "discoveredFiles": len(targets)}
    if query:
        targets, limited_candidates, selection = select_query_targets(
            paths, targets, query, explicit_paths, deadline_monotonic=deadline_monotonic
        )
        partial = partial or limited_candidates
    else:
        targets = targets[:MAX_DISCOVERED_DOCUMENTS]
    document_scan = scan_documents(paths, targets, deadline_monotonic=deadline_monotonic)
    navigation_issues: list[dict[str, Any]] = []
    if query and not document_scan.partial:
        navigation, navigation_partial = select_link_targets(
            document_scan.sections,
            set(available),
            query,
            limit=min(8, RetrievalSettings.read(paths).max_candidates),
            deadline_monotonic=deadline_monotonic,
        )
        selection["navigationTargets"] = navigation
        extra_targets = list(
            dict.fromkeys(
                available[item["path"]]
                for item in navigation
                if item["path"] not in document_scan.input_digests
            )
        )
        if extra_targets:
            extra = scan_documents(
                paths,
                extra_targets,
                deadline_monotonic=deadline_monotonic,
                max_scan_bytes=max(0, MAX_SCAN_BYTES - document_scan.read_bytes),
            )
            # 同一请求共享字节和时间预算；新读取的正文不再次展开链接。
            document_scan.sections.extend(extra.sections)
            document_scan.markdown_links.update(extra.markdown_links)
            document_scan.input_digests.update(extra.input_digests)
            navigation_issues.extend(extra.issues)
            partial = partial or extra.partial
            selection["selectedFiles"] = list(
                dict.fromkeys(
                    [
                        *selection.get("selectedFiles", []),
                        *(paths.relative(p) for p in extra_targets),
                    ]
                )
            )
            selection["omittedFiles"] = len(available) - len(selection["selectedFiles"])
        for target in navigation:
            matched = [
                row
                for row in document_scan.sections
                if row["path"] == target["path"]
                and (not target["fragment"] or target["fragment"] in row.get("anchors", []))
            ]
            if not matched:
                navigation_issues.append(
                    {"type": "knowledge-navigation", "reason": "unresolved-target", **target}
                )
            for row in matched:
                row["navigationScore"] = max(row.get("navigationScore", 0), target["score"])
                row["navigationTargeted"] = row.get("navigationTargeted", False) or bool(
                    target["fragment"]
                )
        if navigation_partial:
            navigation_issues.append({"type": "knowledge-budget", "reason": "navigation-limit"})
        partial = partial or navigation_partial or bool(navigation_issues)
    scan_issues = [
        *discovery_issues,
        *selection.get("scanIssues", []),
        *document_scan.issues,
        *navigation_issues,
    ]
    partial = partial or document_scan.partial
    document_scan.sections.sort(key=lambda item: (item["path"], item["lineStart"], item["id"]))
    _bind_parent_routers(document_scan.sections)
    links = build_link_index(document_scan.sections, document_scan.markdown_links)
    lexical = build_lexical_index(document_scan.sections)
    input_identity = {"kind": kind, "files": document_scan.input_digests}
    payload = {
        "schemaVersion": INDEX_SCHEMA_VERSION,
        "kind": kind,
        "input": input_identity,
        "partial": partial,
        "scanIssues": scan_issues,
        "selection": selection,
        "sections": document_scan.sections,
        "links": links,
        "lexical": lexical,
    }
    payload["status"] = "live"
    return payload


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "MAX_DOCUMENT_BYTES",
    "MAX_INDEX_BYTES",
    "MAX_SCAN_BYTES",
    "is_rule_evidence",
    "markdown_files",
    "scan_index",
    "search_index",
    "tokenize",
]
