"""Deterministic structural/lexical ranking and parent-router inclusion."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .documents import canonical_json, matches_knowledge_need
from .lexical import BM25Query, tokenize


def rank_source_locations(
    records: list[dict[str, Any]], query: str
) -> list[tuple[dict[str, Any], Any]]:
    """优先问题匹配及命中正文提及的声明，文件头顺序不代表相关性。"""
    query_terms = tokenize(query)
    ranked: list[tuple[tuple[int, int, int, int], dict[str, Any], Any]] = []
    for record in records:
        heading = str(record.get("heading") or "")
        text = str(record.get("text") or "")
        heading_relevance = sum(term in heading.casefold() for term in query_terms)
        locations = record.get("sourceLocations") or []
        for raw in locations if isinstance(locations, list) else [locations]:
            score = (0, 0, 0, 0)
            if isinstance(raw, dict):
                symbol = str(raw.get("symbol") or "")
                identity = (symbol + " " + str(raw.get("path") or "")).casefold()
                # 小节可能只写类名（如任务入口），不一定重复 execute 等方法名。
                names = [
                    name for name in re.split(r"[.#]|::", symbol.split("(", 1)[0])[-2:] if name
                ]
                pattern = rf"(?<![\w$])(?:{'|'.join(re.escape(name) for name in names)})(?![\w$])"
                in_heading = int(bool(names and re.search(pattern, heading)))
                in_text = int(bool(names and re.search(pattern, text)))
                score = (
                    sum(term in identity for term in query_terms),
                    heading_relevance if in_heading or in_text else 0,
                    in_heading,
                    in_text,
                )
            ranked.append((score, record, raw))
    # 同分保留文档检索顺序；这里只给读取优先级，不声称小节与锚点精确绑定。
    return [
        (record, raw) for _, record, raw in sorted(ranked, key=lambda row: row[0], reverse=True)
    ]


# 显式范围是过滤边界，推断领域和模块只影响排序。
# 成员边界仍需保留，不能因推断路由而跨到未选仓库。
def route_allows(record: dict[str, Any], route: dict[str, Any] | None) -> bool:
    """Return whether an explicit route permits a section to participate."""

    if record.get("status") in {"deprecated"}:
        return False
    route = route or {}
    scope = record.get("scope") or {}
    members = set(route.get("members") or [])
    domains = set(route.get("domains") or [])
    modules = set(route.get("modules") or [])
    if members and scope.get("memberId") and scope.get("memberId") not in members:
        return False
    inferred = bool(route.get("inferred"))
    if not inferred and domains and scope.get("domain") and scope.get("domain") not in domains:
        return False
    return _module_route_allows(scope, modules, inferred)


def _module_route_allows(scope: dict[str, Any], modules: set[str], inferred: bool) -> bool:
    """显式模块路由同时接受短名称和领域限定名称，推断路由不作硬过滤。"""
    qualified_module = "/".join(item for item in (scope.get("domain"), scope.get("module")) if item)
    if (
        not inferred
        and modules
        and scope.get("module")
        and scope.get("module") not in modules
        and qualified_module not in modules
    ):
        return False
    return True


# 结构命中与 BM25 各自排序，再用倒数排名融合不同分数量纲。
# 需求加分与当前状态加分保留为独立信号，便于解释结果。
# 同分时按路径和行号排序，预算输出保持可重复。
# 精确命中的 L2 正文会补上父导航，避免片段脱离所属模块。
def search_index(
    index: dict[str, Any],
    query: str,
    *,
    route: dict[str, Any] | None = None,
    limit: int = 24,
    evidence_needs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fuse structural, lexical, link and optional semantic rankings with RRF."""
    records = [item for item in index.get("sections") or [] if route_allows(item, route)]
    query_tokens = tokenize(query)
    query_low = query.casefold()
    structural: list[tuple[float, str]] = []
    lexical: list[tuple[float, str]] = []
    exact_l2: set[str] = set()
    bm25 = BM25Query(index, query_tokens)
    for record in records:
        path = record["path"].casefold()
        heading = " / ".join(record.get("headingPath") or [record["heading"]]).casefold()
        frontmatter = canonical_json(record.get("frontmatter") or {}).casefold()
        exact = sum(
            1 for token in query_tokens if token in path or token in heading or token in frontmatter
        )
        phrase = 2 if query_low and (query_low in heading or query_low in path) else 0
        scope_bonus = sum(
            1
            for value in (record.get("scope") or {}).values()
            if value and str(value).casefold() in query_low
        )
        route_scope = record.get("scope") or {}
        route_bonus = 0
        if route:
            locations = record.get("sourceLocations") or []
            if isinstance(locations, list) and any(
                isinstance(location, dict)
                and isinstance(location.get("path"), str)
                and any(
                    location["path"] == prefix
                    or location["path"].startswith(prefix.rstrip("/") + "/")
                    for prefix in route.get("paths") or []
                    if not prefix.startswith(("modus/", ".modus/"))
                )
                for location in locations
            ):
                route_bonus += 5
            if route_scope.get("memberId") in set(route.get("members") or []):
                route_bonus += 3
            if route_scope.get("domain") in set(route.get("domains") or []):
                route_bonus += 3
            qualified_module = "/".join(
                item for item in (route_scope.get("domain"), route_scope.get("module")) if item
            )
            route_modules = set(route.get("modules") or [])
            if route_scope.get("module") in route_modules or qualified_module in route_modules:
                route_bonus += 4
        structural.append((float(exact * 3 + phrase + scope_bonus + route_bonus), record["id"]))
        if record.get("loadLevel") == "L2" and (exact or phrase):
            exact_l2.add(record["id"])
        lexical.append((bm25.score(record), record["id"]))
    rankings: list[list[str]] = [
        [
            item[1]
            for item in sorted(structural, key=lambda item: (-item[0], item[1]))
            if item[0] > 0
        ],
        [item[1] for item in sorted(lexical, key=lambda item: (-item[0], item[1])) if item[0] > 0],
    ]
    rrf: defaultdict[str, float] = defaultdict(float)
    signals: defaultdict[str, dict[str, float]] = defaultdict(dict)
    for channel, ranking in zip(("structural", "lexical"), rankings, strict=False):
        for rank, evidence_id in enumerate(ranking, start=1):
            contribution = 1.0 / (60.0 + rank)
            rrf[evidence_id] += contribution
            signals[evidence_id][channel] = round(contribution, 8)
    by_id = {item["id"]: item for item in records}
    # 场景链接可连接不同词汇；片段精确命中保留独立信号，不升级规则权威。
    for record in records:
        if record.get("navigationScore"):
            # 整篇文件链接只给弱提示，不能让无关小节压过精确正文命中。
            contribution = 1.0 / 61 if record.get("navigationTargeted") else 0.002
            rrf[record["id"]] += contribution
            signals[record["id"]]["navigationLink"] = contribution
    need_types = {
        "relationship": {"workspace-generated", "project-generated", "project-module"},
        "contract": {"workspace-generated", "project-generated", "project-module"},
        "routing": {"workspace-router", "project-domain"},
    }
    for evidence_id in rrf:
        record = by_id[evidence_id]
        matched_needs = sum(
            1
            for need in evidence_needs or []
            if (
                matches_knowledge_need(need, record)
                or record.get("sourceType") in need_types.get(need, set())
            )
        )
        if matched_needs:
            contribution = 0.002 * matched_needs
            rrf[evidence_id] += contribution
            signals[evidence_id]["evidenceNeed"] = round(contribution, 8)
        if record.get("status") == "current":
            rrf[evidence_id] += 0.001
            signals[evidence_id]["currentFact"] = 0.001
    ranked: list[dict[str, Any]] = []
    for evidence_id, score in sorted(
        rrf.items(),
        key=lambda item: (-item[1], by_id[item[0]]["path"], by_id[item[0]]["lineStart"]),
    ):
        item = dict(by_id[evidence_id])
        item["score"] = round(score, 8)
        item["scoreSignals"] = signals[evidence_id]
        ranked.append(item)
        if len(ranked) >= limit:
            break
    return _with_parent_routers(index, ranked, exact_l2=exact_l2, limit=limit, route=route)


# 父路由只为解释正文，不算另一条独立命中。
# 父子使用同一排名，极小限制下允许一对完整返回。
# 去重按证据 ID 处理，多个子项不会反复交付同一个父导航。
def _with_parent_routers(
    index: dict[str, Any],
    ranked: list[dict[str, Any]],
    *,
    exact_l2: set[str],
    limit: int,
    route: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Keep a precise L2 result interpretable by pairing its L1 router.

    Parent routers are navigation, not a second evidence hit.  They therefore
    share the child's rank and may add one record beyond a tiny caller limit;
    this preserves the required L1 -> L2 progressive-loading contract.
    """
    all_records = {
        item["id"]: item for item in index.get("sections") or [] if route_allows(item, route)
    }
    result: list[dict[str, Any]] = []
    emitted: set[str] = set()
    for child in ranked:
        parent_id = child.get("parentRouter") if child.get("id") in exact_l2 else None
        if parent_id and parent_id not in emitted and parent_id in all_records:
            parent = dict(all_records[parent_id])
            parent["score"] = child.get("score", 0.0)
            parent["scoreSignals"] = {"parentRouter": 1.0}
            result.append(parent)
            emitted.add(parent_id)
        if child["id"] not in emitted:
            result.append(child)
            emitted.add(child["id"])
        if len(result) >= limit and not (
            child.get("id") in exact_l2 and parent_id and len(result) == 1
        ):
            break
    return result


# Compatibility with the original internal predicate name.
_allowed = route_allows

__all__ = ["route_allows", "search_index"]
