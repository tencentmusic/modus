"""Bounded progressive selection of Markdown documents."""

from __future__ import annotations

import math
import posixpath
import re
import time
from collections import Counter, defaultdict
from collections.abc import MutableMapping, Sequence
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from ...knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ...paths import ModusPaths
from ..settings import RetrievalSettings
from .documents import _LABELED_LINK_RE, MAX_DOCUMENT_BYTES, classify_document, strip_fenced_code
from .lexical import tokenize

_MAX_SEARCH_RESULTS = 256


# 只选择已发现的规范知识目标，链接不能扩大扫描边界。
# 词频权重降低常见导航措辞的影响，保留具体概念的区分力。
# 截止时间在读取路由前检查，失败时返回空候选供上层降级。
def _rank_router_links(
    paths: ModusPaths,
    router: Path,
    by_path: dict[str, Path],
    query_terms: list[str],
    *,
    limit: int,
    deadline_monotonic: float | None = None,
) -> list[tuple[str, float]]:
    """Rank canonical links without treating a router as implementation evidence."""
    from ...orchestrator.fallback import extract_terms

    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        return []
    try:
        text = read_bound_regular_text(paths.root, router, max_bytes=MAX_DOCUMENT_BYTES)
    except (BoundKnowledgeReadError, OSError, UnicodeError):
        return []
    query_weights = {
        term: float(len(query_terms) - rank) + min(len(term), 16) * 0.5
        for rank, term in enumerate(query_terms)
    }
    query_set = set(query_terms)
    scores: defaultdict[str, float] = defaultdict(float)
    linked_lines: list[tuple[list[re.Match[str]], set[str]]] = []
    for line in text.splitlines():
        links = list(_LABELED_LINK_RE.finditer(line))
        if not links:
            continue
        line_terms = set(extract_terms(line, limit=64))
        linked_lines.append((links, line_terms))
    document_frequency: Counter[str] = Counter()
    for _links, line_terms in linked_lines:
        document_frequency.update(line_terms & query_set)
    line_count = max(1, len(linked_lines))
    for links, line_terms in linked_lines:
        matched = line_terms & query_set
        # Overlapping n-grams are alternative representations of one phrase,
        # not independent evidence. Count only maximal matches so a generic
        # phrase cannot win merely through its contained bigrams, while
        # separate concepts still reinforce the same navigation row.
        matched = {
            term
            for term in matched
            if not any(term != other and term in other for other in matched)
        }
        if not matched:
            continue
        score = sum(
            query_weights[term] * math.log1p((line_count + 1.0) / (document_frequency[term] + 1.0))
            for term in matched
        )
        for match in links:
            raw = match.group(2).split("#", 1)[0].strip()
            if not raw or raw.startswith(("http://", "https://", "#", "/")):
                continue
            candidate = (router.parent / raw).resolve()
            try:
                candidate.relative_to(paths.knowledge_dir)
                relative = paths.relative(candidate)
            except (ValueError, BoundKnowledgeReadError):
                continue
            if relative in by_path and not candidate.is_symlink():
                scores[relative] = max(scores[relative], score)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]


# 首跳来自系统概览，第二跳只允许领域路由继续授权导航。
# 直接指向模块的链接已是终点，不再从模块任意扩展范围。
def _progressive_router_targets(
    paths: ModusPaths,
    by_path: dict[str, Path],
    query_terms: list[str],
    *,
    limit: int,
    deadline_monotonic: float | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Follow root router -> Domain -> Module before scanning leaf prose."""
    overview = "modus/knowledge/architecture-overview.md"
    if overview not in by_path:
        return {}, []
    selected: dict[str, float] = {overview: 1000.0}
    trail = [overview]
    first_hop = _rank_router_links(
        paths,
        by_path[overview],
        by_path,
        query_terms,
        limit=min(8, limit),
        deadline_monotonic=deadline_monotonic,
    )
    for relative, score in first_hop:
        selected[relative] = max(selected.get(relative, 0.0), 700.0 + score)
        trail.append(relative)
    # Only route documents can authorize the second progressive hop. A root
    # link straight to a Module is already a useful terminal selection.
    domain_hops = [item for item in first_hop if item[0].endswith("/SKILL.md")][:4]
    for relative, _score in domain_hops:
        for child, child_score in _rank_router_links(
            paths,
            by_path[relative],
            by_path,
            query_terms,
            limit=4,
            deadline_monotonic=deadline_monotonic,
        ):
            selected[child] = max(selected.get(child, 0.0), 500.0 + child_score)
            trail.append(child)
    return selected, list(dict.fromkeys(trail))


# 显式定位跳过自动路由，保留用户指定目标的优先级。
# 父导航与领域规则作为正文配额之外的必要解释材料。
# 扫描超时、截断和候选超限均标记 partial，不能假装检索完整。
def select_query_targets(
    paths: ModusPaths,
    targets: list[Path],
    query: str,
    explicit_paths: Sequence[str] = (),
    *,
    deadline_monotonic: float | None = None,
) -> tuple[list[Path], bool, dict[str, Any]]:
    """Route canonically, then parse only relevant bodies and navigation."""
    from ...orchestrator.fallback import extract_terms, has_explicit_locator, search_docs

    limit = max(1, RetrievalSettings.read(paths).max_candidates)
    route_terms = extract_terms(query, limit=64)
    # 已知源码路径可命中正文的结构化锚点，不需要常驻源码到领域反向索引。
    source_terms = [
        path
        for path in explicit_paths
        if path != "." and not path.startswith(("modus/", ".modus/"))
    ][:16]
    by_path = {paths.relative(path): path for path in targets}
    direct_target = bool(explicit_paths) or has_explicit_locator(query)
    if direct_target:
        router_scores: dict[str, float] = {}
        router_trail: list[str] = []
    else:
        router_scores, router_trail = _progressive_router_targets(
            paths, by_path, route_terms, limit=limit, deadline_monotonic=deadline_monotonic
        )
    hits = search_docs(
        paths.root,
        query,
        doc_targets=targets,
        max_results=_MAX_SEARCH_RESULTS,
        timeout_seconds=1.0,
        terms=list(dict.fromkeys([*source_terms, *route_terms])),
        deadline_monotonic=deadline_monotonic,
    )
    scores = cast(MutableMapping[str, float], Counter(hit["file"] for hit in hits.hits))
    for relative, score in router_scores.items():
        scores[relative] += score
    for relative in by_path:
        scores[relative] += sum(
            (len(route_terms) - rank) / max(1, len(route_terms))
            for rank, term in enumerate(route_terms)
            if term in relative.casefold()
        )
        if any(relative == p or relative.startswith(p.rstrip("/") + "/") for p in explicit_paths):
            scores[relative] += 1000
    ranked = sorted((p for p in by_path if scores[p] > 0), key=lambda p: (-scores[p], p))
    chosen = set(ranked[:limit])
    domains = {p.split("/")[3] for p in chosen if p.startswith("modus/knowledge/domain/")}
    # Parent navigation and related domain rules are supplemental to the body quota.
    for relative in by_path:
        if any(
            relative
            in {
                f"modus/knowledge/domain/{domain}/SKILL.md",
                f"modus/knowledge/domain/{domain}/references/rule.md",
            }
            for domain in domains
        ):
            chosen.add(relative)
    # Unmatched project declarations remain candidates for semantic applicability,
    # never automatically established rules. Reading two small entry files does not
    # require them to exist, and a direct query can reach any other constraint.
    constraints = sorted(p for p in by_path if p.startswith("modus/knowledge/constraint/"))
    chosen.update(constraints[:2])
    if not ranked:
        routers = [
            path
            for path in by_path
            if classify_document(path)[0] in {"project-router", "workspace-router"}
        ]
        chosen.update(routers[:2])
    selected = sorted(chosen, key=lambda p: (-scores[p], p))
    partial = len(ranked) > limit or len(hits.hits) >= _MAX_SEARCH_RESULTS or hits.timed_out
    return (
        [by_path[p] for p in selected],
        partial,
        {
            "queryScoped": True,
            "discoveredFiles": len(targets),
            "candidateFiles": len(ranked),
            "selectedFiles": selected,
            "routerTrail": router_trail,
            "directTarget": direct_target,
            "querySignalCount": len(route_terms),
            "omittedFiles": len(targets) - len(selected),
            "scanIssues": hits.issues,
        },
    )


# Compatibility with the original internal stage name.
_query_targets = select_query_targets


def select_link_targets(
    records: list[dict[str, Any]],
    available_paths: set[str],
    query: str,
    *,
    limit: int,
    deadline_monotonic: float | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """从已读且命中的正文单跳展开链接，保留片段，不递归遍历知识树。"""
    terms = set(tokenize(query))
    matches: dict[tuple[str, str], dict[str, Any]] = {}
    exhausted = False
    for record in records:
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            exhausted = True
            break
        if record.get("status") != "current":
            continue
        # 不用全局祖先标题触发所有导航行；领域名称命中不等于每个专题都相关。
        headings = set(tokenize(record["heading"])) if record.get("headingLevel", 1) > 1 else set()
        for offset, line in enumerate(
            strip_fenced_code(str(record.get("text") or "")).splitlines()
        ):
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                exhausted = True
                break
            links = list(_LABELED_LINK_RE.finditer(line))
            if not links:
                continue
            overlap = terms & (headings | set(tokenize(line)))
            if not overlap:
                continue
            for match in links:
                raw = unquote(match[2].strip())
                # 只使用已安全发现的知识坐标；不 resolve 链接路径，避免经符号链接改道。
                if "\\" in raw or "\x00" in raw:
                    continue
                try:
                    link = urlsplit(raw)
                except ValueError:
                    continue
                if link.scheme or link.netloc or link.path.startswith("/") or link.query:
                    continue
                relative = (
                    posixpath.normpath(posixpath.join(posixpath.dirname(record["path"]), link.path))
                    if link.path
                    else record["path"]
                )
                if relative not in available_paths:
                    continue
                key = (relative, link.fragment.casefold())
                score = len(overlap)
                if key not in matches or score > matches[key]["score"]:
                    matches[key] = {
                        "path": relative,
                        "fragment": key[1],
                        "score": score,
                        "fromPath": record["path"],
                        "fromLine": record["lineStart"] + offset,
                    }
    ranked = sorted(
        matches.values(), key=lambda item: (-item["score"], item["path"], item["fragment"])
    )
    return ranked[:limit], exhausted or len(ranked) > limit


__all__ = ["select_link_targets", "select_query_targets"]
