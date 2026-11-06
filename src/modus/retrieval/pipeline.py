"""Orchestrate routing, evidence assembly, and bounded context delivery."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from ..knowledge_identity import KnowledgePathIdentity
from ..knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ..orchestrator import fallback
from ..orchestrator.search_policy import redact_secrets
from ..paths import ModusPaths
from ..scope_models import SourceLocation
from ..source_anchors import check_location, source_declarations
from .budget import RetrievalBudget
from .delivery import EvidenceCollector, limit_result
from .delivery import evidence_matches_need as _need_matches
from .delivery import measure_coverage as _coverage
from .delivery import render_context as _render_context
from .index import is_rule_evidence, scan_index, search_index, tokenize
from .query import analyze_query
from .routing import infer_knowledge_route as _infer_knowledge_route
from .routing import route_records as _route_records
from .settings import RetrievalSettings, retrieval_settings
from .stages.ranking import rank_source_locations

_NON_SOURCE_PREFIXES = ("modus/knowledge/", "modus/.cache/", ".modus/")


def _settings(paths: ModusPaths) -> dict:
    return retrieval_settings(paths)


# 源码范围按完整路径段匹配，不能用字符串前缀扩大到相似目录。
# 源码范围判断独立于排序得分，相关性不能越过明确选择的范围。
def _source_in_scope(relative: str, prefixes) -> bool:
    return not prefixes or any(
        p == "." or relative == p or relative.startswith(p.rstrip("/") + "/") for p in prefixes
    )


# 正文摘录、来源元数据与源码位置分别设预览上限。
# 被裁剪的元数据保留独立读取目标，避免静默丢失可追溯信息。
# 文档权威性沿用摄取结果，不能在交付时升级为当前实现。
# 摘要描述原始章节，摘录截断不产生新的事实身份。
def _knowledge_ref(record: dict) -> dict:
    excerpt = str(record.get("text") or "")[:1200]
    if len(str(record.get("text") or "")) > len(excerpt):
        excerpt = excerpt.rstrip() + "\n[… truncated …]"
    raw_locations = record.get("sourceLocations") or []
    locations = raw_locations if isinstance(raw_locations, list) else []
    location_preview = _source_location_preview(locations)
    provenance = {"origin": "document", **record.get("provenance", {})}
    metadata_target = {
        "path": record["path"],
        "lineStart": 1,
        "lineEnd": max(1, int(record.get("frontmatterLineEnd") or record["lineStart"])),
    }
    provenance_preview: dict = {}
    for key, value in provenance.items():
        candidate = {**provenance_preview, key: value}
        if len(json.dumps(candidate, ensure_ascii=False)) <= 2000:
            provenance_preview = candidate
    return {
        "id": record["id"],
        "sourceType": record["sourceType"],
        "layer": record.get("layer", "narrative"),
        "loadLevel": record.get("loadLevel"),
        "facet": record.get("facet"),
        "sectionRole": record.get("sectionRole"),
        "itemIds": list(record.get("itemIds") or [])[:16],
        "itemIdsTotal": len(record.get("itemIds") or []),
        "parentRouter": record.get("parentRouter"),
        "authority": record["authority"],
        "sourceLocations": location_preview,
        "sourceLocationsTotal": len(locations),
        "sourceLocationsTruncated": len(location_preview) < len(locations),
        "sourceLocationsReadTarget": metadata_target,
        "provenance": provenance_preview,
        "provenanceTruncated": len(provenance_preview) != len(provenance),
        "provenanceReadTarget": metadata_target,
        "status": record["status"],
        "scope": record.get("scope") or {},
        "path": record["path"],
        "heading": str(record["heading"])[:300],
        "headingPath": [
            str(value)[:300] for value in (record.get("headingPath") or [record["heading"]])[:6]
        ],
        "entryRange": record.get("entryRange")
        or {"lineStart": record["lineStart"], "lineEnd": record["lineEnd"]},
        "readTarget": record.get("readTarget")
        or {"path": record["path"], "lineStart": record["lineStart"], "lineEnd": record["lineEnd"]},
        "truncated": len(str(record.get("text") or "")) > 1200,
        "lineStart": record["lineStart"],
        "lineEnd": record["lineEnd"],
        "symbol": None,
        "digest": record["digest"],
        "scoreSignals": record.get("scoreSignals") or {},
        "excerpt": excerpt,
    }


def _source_location_preview(locations: list) -> list[dict]:
    """预览只携带有界的标量锚点，完整来源仍通过原文读取目标访问。"""
    location_preview = [
        {
            key: location[key]
            for key in ("path", "symbol", "startLine", "endLine")
            if key in location and isinstance(location[key], (str, int, float, bool))
        }
        for location in locations[:8]
        if isinstance(location, dict)
        and all(
            not isinstance(location.get(key), str) or len(location[key]) <= 512
            for key in ("path", "symbol", "startLine", "endLine")
        )
    ]
    return location_preview


# 排序使用小章节，交付重组为包含条件与失败路径的逻辑条目。
# 只有相同范围和状态的片段可合并，退役片段不进入当前证据。
# 组合正文重新计算内容摘要，保留参与章节的身份以支持去重。
# 排名使用小节，交付恢复逻辑条目，避免只给结论而漏掉条件与失败路径。
def _entry_refs(index: dict, candidates: list[dict]) -> list[dict]:
    """Reunite a ranked entry's explanation, conditions and failure paths.

    Ranking uses small sections; delivery uses logical entries. Long entries
    carry their full read range instead of implying the excerpt is complete.
    """
    by_path: defaultdict[str, list[dict]] = defaultdict(list)
    for section in index.get("sections") or []:
        by_path[section["path"]].append(section)
    seen: set[tuple[str, int, int]] = set()
    result: list[dict] = []
    for candidate in candidates:
        if candidate.get("status") == "deprecated":
            continue
        entry = candidate.get("entryRange") or {
            "lineStart": candidate["lineStart"],
            "lineEnd": candidate["lineEnd"],
        }
        key = (candidate["path"], entry["lineStart"], entry["lineEnd"])
        if key in seen:
            continue
        seen.add(key)
        parts = sorted(
            (
                section
                for section in by_path[key[0]]
                if section.get("entryRange") == entry
                and section.get("status") == candidate.get("status")
            ),
            key=lambda section: section["lineStart"],
        )
        record = dict(candidate)
        # 不同池或命中小节共享条目首段身份，避免残缺片段抢先去重或同条目重复占额。
        if parts:
            record.update(
                id=parts[0]["id"],
                heading=parts[0]["heading"],
                headingPath=parts[0]["headingPath"],
            )
        record.update(
            lineStart=key[1],
            lineEnd=key[2],
            text="\n\n".join(section["text"] for section in parts),
            sectionIds=[section["id"] for section in parts],
        )
        record["digest"] = hashlib.sha256(record["text"].encode("utf-8")).hexdigest()
        ref = _knowledge_ref(record)
        ref["sectionIds"] = record["sectionIds"][:32]
        ref["sectionIdsTotal"] = len(record["sectionIds"])
        result.append(ref)
    return result


# 测试、配置和契约材料分别标识，不能把所有源码都当作运行时实现。
# 证据类型按来源标注，消费者可区分源码与知识正文。
def _source_type(path: str) -> str:
    lowered = path.casefold()
    if "/test" in f"/{lowered}" or Path(lowered).name.startswith("test_"):
        return "test-source"
    if Path(lowered).suffix in {".yaml", ".yml", ".json", ".toml", ".ini", ".conf"}:
        return "config-source"
    if any(marker in lowered for marker in ("openapi", "swagger", "schema", "proto")):
        return "contract-source"
    return "current-source"


# 当前源码必须重新受限读取，历史知识引用不能直接冒充实时证据。
# 摘录围绕命中行取有限上下文，身份仍绑定完整文件摘要。
# 敏感值在离开进程前脱敏，二进制内容不进入文本摘录。
def _source_ref(paths: ModusPaths, relative: str, query: str, hits: list[dict]) -> dict | None:
    # Explicit paths still retain their knowledge provenance. They enter via
    # _knowledge_ref, not as proof of current implementation (including seeds).
    if (
        relative.startswith(("modus/knowledge/", "modus/.cache/", ".modus/"))
        or KnowledgePathIdentity.classify(paths, relative) is not None
    ):
        return None
    target = paths.root / relative
    try:
        raw = read_bound_regular_text(paths.root, target, max_bytes=8 * 1024 * 1024)
    except (BoundKnowledgeReadError, OSError):
        return None
    if "\x00" in raw:
        return None
    lines = raw.splitlines()
    hit_lines = [
        int(item["line"]) for item in hits if item.get("file") == relative and item.get("line")
    ]
    if hit_lines:
        start = max(1, min(hit_lines) - 2)
    else:
        query_terms = tokenize(query)
        match_index = next(
            (
                index
                for index, line in enumerate(lines)
                if any(term in line.casefold() for term in query_terms)
            ),
            0,
        )
        start = max(1, match_index + 1 - 2)
    end = min(len(lines), start + 19)
    excerpt = redact_secrets("\n".join(lines[start - 1 : end]))
    identity = f"{relative}:{start}:{end}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"
    return {
        "id": "ev-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        "layer": "source",
        "sourceType": _source_type(relative),
        "authority": "current-implementation",
        "status": "current",
        "provenance": {},
        "scope": {},
        "path": relative,
        "heading": None,
        "lineStart": start,
        "lineEnd": end,
        "symbol": None,
        "digest": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "scoreSignals": {"liveSource": 1.0},
        "excerpt": excerpt[:1200],
        "truncated": len(excerpt) > 1200,
        "readTarget": {"path": relative, "lineStart": start, "lineEnd": end},
    }


# 源码读取共享本轮截止时间，到期后返回已有材料。
# 结果数量限制在此执行，避免上游宽搜索直接扩大交付体积。
# 源码回退与知识检索共享预算，降级检索不获得额外无限时间。
def _live_source_refs(
    paths: ModusPaths, base: dict, query: str, *, limit: int, budget: RetrievalBudget | None = None
) -> list[dict]:
    raw_evidence = list(base.get("routeEvidence") or base.get("evidence") or [])
    hits = [item for item in raw_evidence if item.get("type") == "ripgrep"]
    result: list[dict] = []
    for relative in base.get("sourceFiles") or []:
        if budget is not None and budget.exhausted:
            break
        ref = _source_ref(paths, str(relative), query, hits)
        if ref is not None:
            result.append(ref)
        if len(result) >= limit:
            break
    return result


# 项目、领域和模块规则分层选择，避免单一层级占满规则配额。
# 未匹配请求的项目约束保留为候选，不能自动宣称适用。
# 显式路径可支持规则适用，但不改变规则本身的状态与权威性。
# 项目、领域与模块约束分别选取，局部命中不能遮蔽更广范围的规则。
def _applicable_constraints(
    index: dict, route: dict, query: str, *, candidates: bool = False
) -> list[dict]:
    """Select current rules independently at project, Domain and Module levels."""
    domains = set(route.get("domains") or [])
    modules = set(route.get("modules") or [])
    query_terms = set(tokenize(query))
    tiers: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for item in index.get("sections") or []:
        if not is_rule_evidence(item):
            continue
        scope = item.get("scope") or {}
        domain = str(scope.get("domain") or "")
        module = str(scope.get("module") or "")
        qualified = f"{domain}/{module}" if domain and module else ""
        source_type = item.get("sourceType")
        if source_type == "project-constraint":
            tier = "project"
        elif item.get("facet") == "rule" and domain in domains and not module:
            tier = f"domain:{domain}"
        elif item.get("facet") == "rule" and qualified in modules:
            tier = f"module:{qualified}"
        else:
            continue
        overlap = len(query_terms & set(tokenize(f"{item['heading']}\n{item['text']}")))
        overlap += int(item.get("navigationScore") or 0)
        explicit = any(
            item["path"] == p or item["path"].startswith(p.rstrip("/") + "/")
            for p in route.get("paths") or []
        )
        tiers[tier].append((float(overlap) + float(explicit), item))

    selected: list[dict] = []
    tier_limits = {"project": 2}
    for tier in sorted(tiers, key=lambda value: (value != "project", value)):
        limit = tier_limits.get(tier, 1)
        ranked = sorted(
            tiers[tier],
            key=lambda value: (-value[0], value[1]["path"], value[1]["lineStart"]),
        )

        def entry_key(item: dict) -> tuple:
            entry = item.get("entryRange") or item
            return item["path"], entry["lineStart"], entry["lineEnd"]

        # 在截断元数据前判断整个条目，长条目的末尾命中也不能丢失。
        matched_entries = {entry_key(item) for score, item in ranked if score > 0}
        chosen: list[dict] = []
        seen: set[tuple] = set()
        for _score, item in ranked:
            key = entry_key(item)
            uncertain = tier == "project" and key not in matched_entries
            if uncertain == candidates and key not in seen:
                chosen.append(item)
                seen.add(key)
                if len(chosen) == limit:
                    break
        selected.extend(_entry_refs(index, chosen))
    return selected


# 知识锚点需在当前文件重新验证范围与符号，不能只相信旧行号。
# 显式源码范围继续约束锚点，引用不能越过用户选择边界。
# 无效锚点保留缺口，同时可按符号做有限词法回退。
# 同一失败符号只搜索一次，避免多个陈旧引用放大检索成本。
# 回退结果附上不同信号，读者可识别它不是原锚点的直接验证。
def _anchored_source_refs(
    paths: ModusPaths,
    records: list[dict],
    query: str,
    *,
    limit: int,
    explicit_paths: list[str] | None = None,
    budget: RetrievalBudget | None = None,
) -> tuple[list[dict], list[dict]]:
    """核验相关文档的当前声明；漂移定向重定位，缺口显式交付。"""
    result: list[dict] = []
    gaps: list[dict] = []
    seen: set[tuple[str, str, int, int]] = set()
    searched_symbols: set[str] = set()
    source_cache: dict[str, tuple[str, list[str], list[dict] | None]] = {}
    for record, raw in rank_source_locations(records, query):
        if budget is not None and budget.exhausted:
            gaps.append({"type": "source-budget", "reason": "anchor-deadline"})
            return result, gaps
        try:
            if not isinstance(raw, dict):
                raise ValueError("源码位置必须为映射")
            relative = str(raw["path"])
            if relative.startswith(_NON_SOURCE_PREFIXES):
                raise ValueError("锚点未指向当前项目源码")
            if explicit_paths and not _source_in_scope(relative, explicit_paths):
                continue
            location = SourceLocation.from_dict(raw)
            symbol = location.symbol
            identity = (
                relative,
                symbol,
                location.start_line,
                location.end_line or location.start_line,
            )
            if identity in seen:
                continue
            seen.add(identity)
            if relative not in source_cache:
                text = read_bound_regular_text(
                    paths.root, paths.root / relative, max_bytes=8 * 1024 * 1024
                )
                lines = text.splitlines()
                source_cache[relative] = (text, lines, source_declarations(relative, lines))
            text, lines, declarations = source_cache[relative]
            check = check_location(location, declarations)
            if budget is not None and budget.exhausted:
                gaps.append({"type": "source-budget", "reason": "anchor-deadline"})
                return result, gaps
            if check.finding not in {"current", "line_drift"}:
                raise ValueError(f"{check.finding}: {check.detail}")
            assert check.start_line is not None and check.end_line is not None
            start, end = check.start_line, check.end_line
            if check.finding == "line_drift":
                gaps.append(
                    {
                        "type": "source-anchor",
                        "path": relative,
                        "symbol": symbol,
                        "reason": "line_drift",
                        "claimedLine": location.start_line,
                        "actualLine": start,
                    }
                )
            excerpt_text = "\n".join(lines[start - 1 : end])
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            excerpt = redact_secrets(excerpt_text)
            result.append(
                {
                    "id": "ev-"
                    + hashlib.sha256(
                        f"anchor:{relative}:{symbol}:{start}:{end}:{digest}".encode()
                    ).hexdigest()[:20],
                    "sourceType": _source_type(relative),
                    "layer": "source",
                    "authority": "current-implementation",
                    "status": "current",
                    "scope": dict(record.get("scope") or {}),
                    "path": relative,
                    "heading": None,
                    "lineStart": start,
                    "lineEnd": end,
                    "symbol": symbol,
                    "digest": digest,
                    "scoreSignals": {"sourceLocation": 1.0},
                    "excerpt": excerpt[:1200],
                    "truncated": len(excerpt) > 1200,
                    "readTarget": {"path": relative, "lineStart": start, "lineEnd": end},
                }
            )
            if len(result) >= limit:
                return result, gaps
        except (KeyError, TypeError, BoundKnowledgeReadError, OSError, ValueError) as exc:
            relative = str(raw.get("path") or "") if isinstance(raw, dict) else ""
            symbol = str(raw.get("symbol") or "") if isinstance(raw, dict) else ""
            gaps.append(
                {
                    "type": "source-anchor",
                    "path": relative,
                    "symbol": symbol,
                    "reason": str(exc),
                }
            )
            if symbol and symbol not in searched_symbols:
                searched_symbols.add(symbol)
                terminal = re.split(r"[.#]|::", symbol.split("(", 1)[0])[-1]
                term = terminal or symbol
                found = fallback.search(
                    paths.root,
                    term or query,
                    max_results=2,
                    path_prefixes=explicit_paths or (),
                    deadline_monotonic=budget.deadline if budget else None,
                )
                gaps.extend(dict(issue) for issue in found.issues)
                for fallback_path in found.files:
                    ref = _source_ref(
                        paths,
                        fallback_path,
                        term or query,
                        [dict(hit) for hit in found.hits],
                    )
                    if ref is not None and ref["id"] not in {item["id"] for item in result}:
                        ref["scoreSignals"] = {"invalidAnchorRipgrepFallback": 1.0}
                        result.append(ref)
                    if len(result) >= limit:
                        return result, gaps
    return result, gaps


# 统一编排路由、源码核验、规则选择与交付预算。
# 所有阶段共享同一时间预算，不能通过创建子阶段重新获得全额时间。
# 先广泛召回知识路由，再使用推断范围重排材料。
# 交付顺序轮转不同证据池，避免大量正文挤掉源码或规则。
# 覆盖度表示证据类型是否到场，不证明答案完整或正确。
def finish_context(
    paths: ModusPaths,
    base: dict,
    *,
    kind: str,
    query_text: str,
    route: dict,
    index: dict,
    additional_evidence: list[dict] | None = None,
    purpose: str | None = None,
    started_monotonic: float | None = None,
    budget: RetrievalBudget | None = None,
) -> dict:
    settings = RetrievalSettings.read(paths)
    if budget is None:
        started = started_monotonic if started_monotonic is not None else time.monotonic()
        budget = RetrievalBudget(
            started,
            started + settings.cold_budget_ms / 1000,
            settings.max_context_chars,
        )
    query = analyze_query(
        query_text,
        constraints=list(base.get("sourceFiles") or []),
        purpose=purpose,
    )
    initial_route = {**route, "domains": [], "modules": []}
    initial_candidates = search_index(
        index,
        query_text,
        route=initial_route,
        limit=settings.max_candidates,
        evidence_needs=query["evidenceNeeds"],
    )
    route = _infer_knowledge_route(index, initial_candidates, query_text, route)
    candidates = search_index(
        index,
        query_text,
        route=route,
        limit=settings.max_candidates,
        evidence_needs=query["evidenceNeeds"],
    )
    body_limit = settings.max_body_sections
    knowledge = _entry_refs(index, candidates)
    domain_routes = [_knowledge_ref(item) for item in _route_records(index, route, kind="domain")]
    module_route_records = _route_records(index, route, kind="module")
    module_routes = [_knowledge_ref(item) for item in module_route_records]
    applicable_constraints = _applicable_constraints(index, route, query_text)
    # 规则候选单独返回，交付者可做语义适用性判断。
    # 不能因为项目存在约束文档就把每条约束标记为本次已适用。
    constraint_candidates = _applicable_constraints(index, route, query_text, candidates=True)
    explicit_scope = list(route.get("paths") or [])
    source_scope = [p for p in explicit_scope if not p.startswith(_NON_SOURCE_PREFIXES)]
    # A knowledge-only explicit selection does not authorize a repository-wide
    # source search. Its citations remain visible for a subsequent targeted read.
    allow_source = kind == "project" and (not explicit_scope or bool(source_scope))
    anchored, anchor_gaps = (
        _anchored_source_refs(
            paths,
            [*candidates, *module_route_records],
            query_text,
            limit=body_limit,
            explicit_paths=source_scope,
            budget=budget,
        )
        if allow_source
        else ([], [])
    )
    # Direct source paths are already bounded. Otherwise source search is the
    # recovery step after narrative routing and source-location verification.
    base = dict(base)
    if (
        allow_source
        and not anchored
        and not base.get("sourceFiles")
        and not budget.exhausted
        and base.get("sourceSearchEnabled", True)
    ):
        found = fallback.search(
            paths.root,
            query_text,
            max_results=20,
            path_prefixes=source_scope,
            deadline_monotonic=budget.deadline,
        )
        base["sourceFiles"] = found.files
        base["routeEvidence"] = [
            *base.get("routeEvidence", []),
            *({"type": "ripgrep", **hit} for hit in found.hits),
        ]
        anchor_gaps.extend(dict(issue) for issue in found.issues)
    live = _live_source_refs(paths, base, query_text, limit=body_limit, budget=budget)
    # 领域导航使用更短摘录，保留位置说明而节省正文配额。
    # 导航的附加名额不应挤掉核心源码与规则材料。
    routing_evidence: list[dict] = []
    for ref in domain_routes:
        routing_evidence.append({**ref, "excerpt": ref["excerpt"][:300], "loadLevel": "L1"})
    collector = EvidenceCollector(limit=body_limit + len(routing_evidence))
    for ref in routing_evidence:
        collector.add(ref)
    rules = [
        *applicable_constraints,
        *[item for item in additional_evidence or [] if _need_matches("business-rule", item)],
    ]
    needs_rules = bool({"business-rule", "engineering-constraint"} & set(query["evidenceNeeds"]))
    domain_pool = [*rules, *knowledge] if needs_rules else knowledge
    pools = [
        [*anchored, *live],
        [item for item in rules if needs_rules and item.get("sourceType") == "project-constraint"],
        [item for item in domain_pool if _need_matches("domain-knowledge", item)],
        [*knowledge, *module_routes],
        list(additional_evidence or []),
    ]
    collector.drain_round_robin(pools)
    evidence = collector.items
    # A logical entry is one delivery unit, regardless of how many headings or
    # how many siblings share its file.
    # 逻辑条目包含多个章节 ID，覆盖计算需把这些章节一起视为已交付。
    # 否则同一条目会被错误报告为仍有未返回候选。
    delivered_ids = {
        identity for item in evidence for identity in [item["id"], *item.get("sectionIds", [])]
    }
    unreturned = {item["id"] for item in candidates} - delivered_ids
    coverage = _coverage(
        query["evidenceNeeds"],
        evidence,
        candidates_remain=bool(unreturned) or bool(index.get("partial")),
    )
    # 扫描损坏和锚点失效都属于取证完整性问题。
    # 已有可用证据继续返回，但整体 complete 必须降为 false。
    grounding_gaps = [*list(index.get("scanIssues") or []), *anchor_gaps]
    if index.get("partial"):
        grounding_gaps.append({"type": "knowledge-budget", "selection": index.get("selection", {})})
    if grounding_gaps:
        coverage["items"].append(
            {
                "need": "grounding-integrity",
                "status": "partial",
                "evidenceIds": [],
                "gaps": grounding_gaps,
            }
        )
        coverage["summary"]["partial"] = coverage["summary"].get("partial", 0) + 1
        coverage["complete"] = False
    # 范围外请求明确列出，不能以当前范围的成功检索掩盖未满足部分。
    # 这些路径仅用于报告，不触发额外读取。
    if route.get("outOfScopePaths"):
        coverage["items"].append(
            {
                "need": "scope-boundary",
                "status": "out-of-scope",
                "evidenceIds": [],
                "paths": list(route["outOfScopePaths"]),
            }
        )
        coverage["summary"]["out-of-scope"] = len(route["outOfScopePaths"])
        coverage["complete"] = False
    # 时间预算采用协作式截止检查，结果如实标记耗尽。
    # 较早阶段已耗尽的状态需要继承，不能被后续快速阶段清除。
    elapsed_ms = budget.elapsed_ms
    budget_exhausted = bool(
        budget.exhausted or (base.get("freshness") or {}).get("budgetExhausted")
    )
    if budget_exhausted:
        coverage["items"].append({"need": "runtime-budget", "status": "partial", "evidenceIds": []})
        coverage["summary"]["partial"] = coverage["summary"].get("partial", 0) + 1
        coverage["complete"] = False
    # 继续读取理由区分预算耗尽、候选剩余和材料缺口。
    # 正文过长时保留完整条目阅读范围，避免摘录被误认为全文。
    continuation = {
        "available": not coverage["complete"]
        and (coverage["candidatesRemain"] or bool(route.get("members"))),
        "reason": (
            "budget-exhausted"
            if budget_exhausted
            else "retrieval-needs-matched"
            if coverage["complete"]
            else ("more-candidates" if coverage["candidatesRemain"] else "evidence-gap")
        ),
        "readTargets": [
            item["readTarget"]
            for item in [*knowledge, *applicable_constraints]
            if item.get("readTarget")
            and (item.get("truncated") or item["id"] not in {ref["id"] for ref in evidence})
        ],
    }
    # 路由证据与最终交付证据分开保存，便于复核选择依据。
    # 基础结果先复制，避免组装阶段改变调用方持有的外层对象。
    raw_route_evidence = list(base.get("routeEvidence") or base.get("evidence") or [])
    result = dict(base)
    result.update(
        {
            "schemaVersion": 1,
            "query": query,
            "route": route,
            "applicableConstraints": applicable_constraints,
            "constraintCandidates": constraint_candidates,
            "groundingGaps": grounding_gaps,
            "retrieval": {
                "stage": (
                    "degraded"
                    if budget_exhausted
                    else ("retrieved" if coverage["complete"] else "progressive")
                ),
                "semantics": "retrieval-hint-only",
                "candidateCount": len(candidates),
                "deliveredEvidenceCount": len(evidence),
                "elapsedMs": elapsed_ms,
                "budget": {
                    "maxContextChars": budget.max_chars,
                    "maxRuntimeMs": budget.duration_ms,
                    "deadlineMode": "cooperative",
                    "maxCandidates": settings.max_candidates,
                    "maxBodySections": body_limit,
                },
                "stopReason": continuation["reason"],
                "indexStatus": index.get("status"),
            },
            "routeEvidence": raw_route_evidence,
            "evidence": evidence,
            "coverage": coverage,
            "continuation": continuation,
        }
    )
    result["freshness"] = {
        **dict(base.get("freshness") or {}),
        "retrievalIndexStatus": index.get("status"),
    }
    # 公开文件清单由实际证据与路由依据合并而来。
    # 按首次出现去重，保留阅读优先级。
    result["knowledgeFiles"] = list(
        dict.fromkeys(
            [
                *[
                    str(item["path"])
                    for item in [*evidence, *applicable_constraints]
                    if item.get("path")
                    and str(item.get("sourceType") or "").startswith(("project-", "workspace-"))
                ],
                *[
                    str(item["path"])
                    for item in route.get("rationaleDetails") or []
                    if item.get("path")
                ],
            ]
        )
    )
    # 源码清单排除 Modus 自有知识与缓存，保持材料来源清晰。
    # 通过锚点核验的源码即使未进入本轮摘录也保留为后续定位入口。
    result["sourceFiles"] = list(
        dict.fromkeys(
            [
                *[
                    str(item)
                    for item in base.get("sourceFiles") or []
                    if not str(item).startswith(("modus/knowledge/", "modus/.cache/", ".modus/"))
                ],
                *[
                    str(item["path"])
                    for item in [*evidence, *anchored]
                    if item.get("path")
                    and item.get("sourceType")
                    in {"current-source", "test-source", "config-source", "contract-source"}
                ],
            ]
        )
    )
    result["materialFiles"] = []
    result["freshness"]["knowledgeSelection"] = index.get("selection", {})
    if budget_exhausted:
        result["freshness"]["mode"] = "degraded"
        result["freshness"]["budgetExhausted"] = True
    result["contextMarkdown"] = _render_context(
        str(base.get("contextMarkdown") or ""),
        evidence,
        coverage,
        budget.max_chars,
    )
    # 最终再按真实渲染长度裁剪，并同步更新覆盖度和继续阅读提示。
    # 这一步保证 JSON 证据与用户看到的上下文不会互相矛盾。
    limit_result(result, max_chars=budget.max_chars)
    return result


# 成员证据深拷贝后映射到工作区坐标，原成员结果保持可复用。
# 正文路径、来源位置和继续阅读目标必须同步转换。
# 证据 ID 加入成员身份，避免两个仓库相同相对路径发生碰撞。
# 工作区聚合复用当前预算，不为每个成员重置总交付上限。
def enrich_workspace_result(
    root: str | Path,
    request: str,
    base: dict,
    *,
    route: dict,
    purpose: str | None = None,
    budget: RetrievalBudget | None = None,
) -> dict:
    paths = ModusPaths.for_root(root)
    settings = RetrievalSettings.read(paths)
    if budget is None:
        budget = RetrievalBudget.start(
            settings.cold_budget_ms,
            settings.max_context_chars,
        )
    index = scan_index(paths, kind="workspace", query=request, deadline_monotonic=budget.deadline)
    member_evidence: list[dict] = []
    for item in base.get("memberContexts") or []:
        child = item.get("context") or {}
        for ref in child.get("evidence") or []:
            if not isinstance(ref, dict) or not ref.get("id"):
                continue
            copied = deepcopy(ref)
            if copied.get("path"):
                copied["path"] = (Path(item["memberPath"]) / copied["path"]).as_posix()
            for target_key in ("readTarget", "sourceLocationsReadTarget", "provenanceReadTarget"):
                if copied.get(target_key, {}).get("path"):
                    copied[target_key]["path"] = (
                        Path(item["memberPath"]) / copied[target_key]["path"]
                    ).as_posix()
            for location in copied.get("sourceLocations") or []:
                if location.get("path"):
                    location["path"] = (Path(item["memberPath"]) / location["path"]).as_posix()
            for endpoint in (
                (copied.get("relation") or {}).get("source"),
                (copied.get("relation") or {}).get("target"),
            ):
                if endpoint and endpoint.get("file"):
                    endpoint["file"] = (Path(item["memberPath"]) / endpoint["file"]).as_posix()
            # 路径重映射之后再建立工作区证据身份。
            # 成员来源同时写入 scope，便于跨仓库结果过滤与解释。
            # 源证据摘要保持原值，前缀映射并未改变文件内容。
            copied["id"] = (
                "ev-"
                + hashlib.sha256(f"{item.get('memberId')}:{ref['id']}".encode()).hexdigest()[:20]
            )
            copied["scope"] = {**dict(copied.get("scope") or {}), "memberId": item.get("memberId")}
            member_evidence.append(copied)
    return finish_context(
        paths,
        base,
        kind="workspace",
        query_text=request,
        route=route,
        index=index,
        additional_evidence=member_evidence,
        purpose=purpose,
        budget=budget,
    )


# Compatibility for internal integrations using the former helper name.
_finish = finish_context
