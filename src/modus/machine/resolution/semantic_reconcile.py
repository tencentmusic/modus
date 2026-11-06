"""Contextual compiler observations and non-destructive syntax correspondence.

Compiler symbols, syntax occurrences and runtime dispatch are different things.
This pass records their correspondence without rewriting source facts or turning
an uncertain correspondence into a semantic identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import networkx as nx

from modus.machine.corpus.source_coordinates import SourceCoordinates
from modus.machine.errors import ContractError, ProviderError
from modus.machine.facts.compiler.merge import _merge_facts
from modus.machine.facts.semantic_ir import SemanticFacts, SemanticNode, canonical_json, stable_id
from modus.machine.resolution.evidence_graph import (
    EVIDENCE_GRAPH_SCHEMA_VERSION,
    iter_keyed_edges,
    validate_evidence_graph,
)


# 必需语义模式下保留独立提供者错误，调用方可据此阻止发布。
class SemanticReconcileError(ProviderError):
    """A requested semantic observation cannot be published with its identity intact."""


# 记录语义观察与语法节点的对应关系，不合并两者身份。
# 候选和多锚点对应同时保存，单个成功匹配不能掩盖其他歧义。
@dataclass(frozen=True)
class NodeBinding:
    semantic_id: str
    graph_node_id: str
    method: str
    source_file: str = ""
    reason_code: str = ""
    analysis_context_id: str = ""
    candidates: tuple[str, ...] = ()
    correspondences: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "semanticId": self.semantic_id,
            "graphNodeId": self.graph_node_id,
            "method": self.method,
            "sourceFile": self.source_file,
            "reasonCode": self.reason_code,
            "contextId": self.analysis_context_id,
            "analysisContextId": self.analysis_context_id,
            "candidates": list(self.candidates),
            "correspondences": list(self.correspondences),
        }


# 被拒绝的边仍保留事实 ID 和原因，便于回查提供者输出。
@dataclass(frozen=True)
class RejectedSemanticEdge:
    edge_id: str
    reason_code: str

    def to_dict(self) -> dict[str, str]:
        return {"edgeId": self.edge_id, "reasonCode": self.reason_code}


# 图、对应关系与统计作为同一结果交付，摘要绑定本次协调策略。
@dataclass
class SemanticReconcileResult:
    graph: nx.MultiDiGraph[str] = field(repr=False)
    facts: SemanticFacts
    bindings: tuple[NodeBinding, ...]
    rejected_edges: tuple[RejectedSemanticEdge, ...]
    conflicts: tuple[dict[str, Any], ...]
    stats: dict[str, int]
    input_digests: dict[str, str]
    digest: str
    report_path: str = ""

    # 详细报告保留处置与覆盖回执，支持解释为什么某条语义边没有发布。
    def report(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "evidenceGraphSchemaVersion": EVIDENCE_GRAPH_SCHEMA_VERSION,
            "digest": self.digest,
            "bindings": [row.to_dict() for row in self.bindings],
            "conflicts": list(self.conflicts),
            "rejectedEdges": [row.to_dict() for row in self.rejected_edges],
            "inputDigests": dict(self.input_digests),
            "stats": dict(self.stats),
            "dispositions": [row.to_dict() for row in self.facts.dispositions],
            "coverageReceipts": [row.to_dict() for row in self.facts.coverage_receipts],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.stats,
            "digest": self.digest,
            **({"report": self.report_path} if self.report_path else {}),
        }


# 规范 JSON 保证摘要与映射插入顺序无关。
def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


# 仓库内绝对路径规范为相对路径，外部符号仍保留其外部位置。
def _path(value: object, root: Path) -> str:
    if not value:
        return ""
    path = Path(str(value))
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            return path.as_posix()
    return path.as_posix().removeprefix("./")


# 名称只用于筛选兼容声明，最终对应仍要求符号或位置证据。
def _simple_name(node: SemanticNode) -> str:
    # Use the provider's explicit identifier where available. Identifiers retain
    # case, Unicode and punctuation; a lossy search key is never an identity key.
    explicit = node.attributes.get("name")
    if explicit:
        return str(explicit)
    name = node.qualified_name.split("#")[-1].split("(")[0]
    return name.rsplit("::", 1)[-1].rsplit(".", 1)[-1]


# 优先转换为字节范围，统一不同编译器的列编码。
# 无法转换时保留坐标编码标签，防止直接比较不可比的列号。
def _span(
    value: Mapping[str, Any], root: Path, coordinates: SourceCoordinates
) -> tuple[object, ...]:
    relative = _path(value.get("file"), root)
    location = {
        "path": relative,
        "startLine": value.get("line"),
        "startColumn": value.get("column", 1),
        "endLine": value.get("endLine", value.get("line")),
        "endColumn": value.get("endColumn", value.get("column", 1) + 1),
        "columnEncoding": value.get("columnEncoding", "unknown"),
    }
    span = coordinates.span(location)
    if span:
        return ("bytes", *span)
    # Legacy observations can still agree in their declared coordinate system.
    # Different encodings are never compared as raw column numbers.
    return (
        "coordinates",
        relative,
        value.get("columnEncoding", "unknown"),
        value.get("line"),
        value.get("column", 1),
        value.get("endLine"),
        value.get("endColumn"),
    )


# 起点回退只用于缺少完整范围的对应，不扩大为整行匹配。
def _point(span: tuple[object, ...]) -> tuple[object, ...]:
    return span[:-1] if span[0] == "bytes" else span[:5]


# 优先消费完整范围；兼容旧节点时仍保留列号和编码信息。
def _node_points(
    data: Mapping[str, Any], root: Path, coordinates: SourceCoordinates
) -> set[tuple[object, ...]]:
    ranges = data.get("source_ranges", ())
    if ranges:
        return {_point(_span(row, root, coordinates)) for row in ranges if isinstance(row, Mapping)}
    match = re.fullmatch(r"L(\d+):(\d+)", str(data.get("source_location") or ""))
    if not match:
        return set()
    return {
        _point(
            _span(
                {
                    "file": data.get("source_file"),
                    "line": int(match[1]),
                    "column": int(match[2]),
                    "columnEncoding": data.get("columnEncoding", "unknown"),
                },
                root,
                coordinates,
            )
        )
    }


# 对应前检查语言、种类、名称及已知签名，排除明显不兼容的声明。
# Java CST 的所有者不含包名；允许编译器补全包名前缀，仍须匹配精确源码位置。
def _compatible(data: Mapping[str, Any], semantic: SemanticNode) -> bool:
    kind = str(data.get("kind") or data.get("node_type") or "")
    if kind and kind != semantic.kind and {kind, semantic.kind} != {"function", "method"}:
        return False
    if data.get("language") and data["language"] != semantic.language:
        return False
    if str(data.get("label") or "") != _simple_name(semantic):
        return False
    for key in ("owner", "signature"):
        structural = data.get(key)
        compiled = semantic.attributes.get(key)
        if structural and compiled and structural != compiled:
            if (
                key == "owner"
                and semantic.language == "java"
                and str(compiled).endswith("." + str(structural))
            ):
                continue
            return False
    return True


# 按稳定符号、完整范围、精确起点逐级尝试对应。
# 合成声明只建立来源联系，不声称它与语法声明具有同一身份。
# 多个合法声明锚点可共存；多义匹配单独进入候选集合。
def _correspondences(
    graph: nx.MultiDiGraph[str],
    semantic: SemanticNode,
    root: Path,
    by_file: Mapping[str, list[str]],
    by_symbol: Mapping[str, set[str]],
    coordinates: SourceCoordinates,
    by_name: Mapping[tuple[str, str], list[str]],
) -> tuple[tuple[dict[str, str], ...], tuple[str, ...], str]:
    rows: list[dict[str, str]] = []
    candidates: set[str] = set()
    reason = (
        "machine.resolution.no-source-anchor"
        if not semantic.source_anchors
        else "machine.resolution.no-exact-identity"
    )
    synthetic = "#<init>" in semantic.qualified_name or semantic.attributes.get("synthetic") is True
    for anchor in semantic.source_anchors:
        file_nodes = by_file.get(_path(anchor.file, root), ())
        compatible = [
            nid
            for nid in by_name.get((_path(anchor.file, root), _simple_name(semantic)), ())
            if _compatible(graph.nodes[nid], semantic)
        ]
        semantic_span = _span(anchor.to_dict(), root, coordinates)
        symbol = semantic.symbol_id or semantic.id
        matches = [nid for nid in compatible if nid in by_symbol.get(symbol, ())]
        method = "stable-symbol"
        if not matches:
            matches = [
                nid
                for nid in compatible
                if any(
                    _span(row, root, coordinates) == semantic_span
                    for row in graph.nodes[nid].get("source_ranges", ())
                    if isinstance(row, Mapping)
                )
            ]
            method = "full-range"
        if not matches:
            # Without a declared range, require the column too. A line plus a
            # similar name cannot distinguish multiple declarations.
            matches = [
                nid
                for nid in compatible
                if _point(semantic_span) in _node_points(graph.nodes[nid], root, coordinates)
            ]
            method = "file-position-symbol-kind"
        if synthetic:
            matches = [
                nid
                for nid in file_nodes
                if _point(semantic_span) in _node_points(graph.nodes[nid], root, coordinates)
            ]
            method = "synthetic-origin"
        if len(matches) == 1:
            rows.append(
                {
                    "syntaxGraphNodeId": matches[0],
                    "method": method,
                    "role": "origin" if synthetic else "declaration",
                }
            )
            reason = ""
        elif matches:
            candidates.update(matches)
            reason = "machine.resolution.ambiguous-correspondence"
    # Multiple anchors are legal declaration/definition occurrences. Ambiguity
    # at any anchor is retained separately and cannot be hidden by a good match.
    unique = {canonical_json(row): row for row in rows}
    return tuple(unique[key] for key in sorted(unique)), tuple(sorted(candidates)), reason


# 语义节点保留分析上下文、来源和完整性，供下游按可信度消费。
def _semantic_attributes(node: SemanticNode) -> dict[str, Any]:
    anchor = node.source_anchors[0] if node.source_anchors else None
    provenance = node.provenance.to_dict() if node.provenance else {}
    return {
        "label": _simple_name(node),
        "source_file": anchor.file if anchor else "",
        "source_location": f"L{anchor.line}:{anchor.column}" if anchor else "",
        "source_ranges": [row.to_dict() for row in node.source_anchors],
        "file_type": "code" if anchor else "concept",
        "kind": node.kind,
        "language": node.language,
        "qualified_name": node.qualified_name,
        "semantic_id": node.id,
        "symbol_id": node.symbol_id or node.id,
        "build_unit_id": node.build_unit_id,
        "deployable_id": node.deployable_id,
        "analysis_context_id": node.analysis_context_id,
        "context_id": node.analysis_context_id,
        "analysis_completeness": node.analysis_completeness,
        "semantic_attributes": dict(node.attributes),
        "semantic_provenance": provenance,
        "provenance": provenance,
        "_origin": "compiler",
        "external": not bool(anchor),
    }


# 输入摘要覆盖所有证据属性，防止只比较标签而漏掉绑定变化。
def _structural_digest(graph: nx.MultiDiGraph[str]) -> str:
    # Include all evidence attributes, not just presentation labels and line
    # numbers. JSON conversion admits Path-valued extraction metadata.
    payload = {
        "nodes": sorted(
            ((str(nid), data) for nid, data in graph.nodes(data=True)), key=lambda row: row[0]
        ),
        "edges": sorted(
            ((str(a), str(b), key, data) for a, b, key, data in iter_keyed_edges(graph)),
            key=lambda row: row[:3],
        ),
    }
    return _digest(json.loads(json.dumps(payload, default=str, sort_keys=True)))


# 语义观察以新节点加入图，保留原始结构事实。
# 同一上下文中的冲突对称处理，不用排序先后决定赢家。
# 声明精度与运行时分派精度分别存储，避免精确声明被当作确定执行。
def reconcile_graph(
    graph: nx.Graph[str],
    facts: SemanticFacts,
    root: Path,
    *,
    mode: str = "auto",
    copy_graph: bool = True,
) -> SemanticReconcileResult:
    if mode not in {"auto", "required", "off"}:
        raise ContractError("machine.resolution.invalid-reconcile-mode")
    validate_evidence_graph(graph)
    working = cast("nx.MultiDiGraph[str]", graph.copy() if copy_graph else graph)
    # 先归一化提供者记录，再建立索引和对应关系，确保后续使用同一事实集合。
    normalized = _merge_facts((facts,))
    inputs = {
        "structuralGraph": _structural_digest(working),
        "semanticFacts": _digest(normalized.to_dict()),
        "correspondencePolicy": "contextual-occurrences",
    }
    by_file: dict[str, list[str]] = defaultdict(list)
    by_symbol: dict[str, set[str]] = defaultdict(set)
    by_name: dict[tuple[str, str], list[str]] = defaultdict(list)
    coordinates = SourceCoordinates(root)
    for nid, data in working.nodes(data=True):
        by_file[_path(data.get("source_file"), root)].append(nid)
        by_name[(_path(data.get("source_file"), root), str(data.get("label") or ""))].append(nid)
        symbol = data.get("symbol_id") or data.get("symbolId")
        if symbol:
            by_symbol[str(symbol)].add(nid)
    # 一次生成所有候选，随后统一检测竞争声明，避免边遍历边认领。
    proposals = {
        node.id: _correspondences(working, node, root, by_file, by_symbol, coordinates, by_name)
        for node in normalized.nodes
    }
    # Symmetric conflict handling: never let sorted ID order select a winner.
    claims: dict[tuple[str, str], list[SemanticNode]] = defaultdict(list)
    for node in normalized.nodes:
        for row in proposals[node.id][0]:
            if row["role"] == "declaration":
                claims[(node.analysis_context_id, row["syntaxGraphNodeId"])].append(node)
    ambiguous = {
        key
        for key, values in claims.items()
        if len({node.symbol_id or node.id for node in values}) > 1
    }
    bindings: list[NodeBinding] = []
    conflicts: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    for node in sorted(normalized.nodes, key=lambda row: row.id):
        rows, candidates, reason = proposals[node.id]
        displaced = tuple(
            row["syntaxGraphNodeId"]
            for row in rows
            if (node.analysis_context_id, row["syntaxGraphNodeId"]) in ambiguous
        )
        # 同上下文多个语义身份竞争同一声明时，原对应退回候选而非保留首个。
        if displaced:
            rows = tuple(row for row in rows if row["syntaxGraphNodeId"] not in displaced)
            candidates = tuple(sorted(set((*candidates, *displaced))))
            reason = "machine.resolution.conflicting-symbol-correspondence"
        # 节点身份包含分析上下文，同一符号在不同构建配置中保持独立。
        identity = stable_id("compiler-observation", node.analysis_context_id, node.id)
        salt = 0
        # 已有图发生身份碰撞时使用确定递增盐值，不覆盖原节点。
        while identity in working:
            salt += 1
            identity = stable_id("compiler-observation", node.analysis_context_id, node.id, salt)
        ids[node.id] = identity
        attrs = _semantic_attributes(node)
        attrs.update(
            graph_node_id=identity,
            correspondences=list(rows),
            correspondence_candidates=list(candidates),
        )
        working.add_node(identity, **attrs)
        # 没有语法对应的编译器观察仍独立保留，便于表示外部与合成符号。
        method = "multi-anchor" if len(rows) > 1 else rows[0]["method"] if rows else "standalone"
        bindings.append(
            NodeBinding(
                node.id,
                identity,
                method,
                node.source_anchors[0].file if node.source_anchors else "",
                reason,
                node.analysis_context_id,
                candidates,
                rows,
            )
        )
        if candidates:
            conflicts.append(
                {
                    "semanticId": node.id,
                    "contextId": node.analysis_context_id,
                    "reasonCode": reason,
                    "candidates": list(candidates),
                }
            )
    # 拒收边进入报告，不能通过不发布它们让统计看似全部成功。
    rejected = tuple(
        RejectedSemanticEdge(row.record_id, row.reason_code)
        for row in normalized.dispositions
        if row.record_kind == "edge" and row.status in {"rejected", "conflict"}
    )
    # 每条语义边保留独立键，平行调用与反向调用不会被简单图折叠。
    for edge in normalized.edges:
        anchor = edge.call_site.to_dict() if edge.call_site else {}
        provenance = edge.provenance.to_dict() if edge.provenance else {}
        working.add_edge(
            ids[edge.source],
            ids[edge.target],
            key=f"compiler:{edge.id}",
            relation=edge.relation,
            resolution=edge.declaration_precision,
            declaration_resolution=edge.declaration_precision,
            dispatch_resolution=edge.dispatch_precision,
            confidence=edge.declaration_precision.upper(),
            binding_kind=edge.to_dict()["bindingKind"],
            bindingKind=edge.to_dict()["bindingKind"],
            resolvedBy="compiler",
            analysis_completeness=edge.analysis_completeness,
            analysis_context_id=edge.analysis_context_id,
            context_id=edge.analysis_context_id,
            operation=edge.operation,
            dispatch=edge.dispatch,
            contract_key=edge.contract_key,
            source_file=edge.call_site.file if edge.call_site else "",
            source_location=f"L{edge.call_site.line}:{edge.call_site.column}"
            if edge.call_site
            else "",
            call_site=anchor,
            callSite=anchor,
            evidence=list(edge.evidence),
            semantic_edge_id=edge.id,
            semantic_attributes=dict(edge.attributes),
            semantic_provenance=provenance,
            provenance=provenance,
        )
    # 必需模式拒绝包含冲突或拒收事实的结果，自动模式仍可提供部分证据。
    if mode == "required" and any(
        row.status in {"conflict", "rejected"} for row in normalized.dispositions
    ):
        raise SemanticReconcileError("machine.resolution.required-reconciliation-failed")
    validate_evidence_graph(working)
    duplicates = sum(
        row.record_kind == "edge" and row.status == "duplicate" for row in normalized.dispositions
    )
    # 统计按端点对计数，但不改变图中逐次调用的证据粒度。
    pairs = Counter((ids[row.source], ids[row.target]) for row in normalized.edges)
    # 对应方法分布单独统计，便于识别匹配策略退化。
    methods = Counter(row.method for row in bindings)
    stats = {
        "inputSemanticEdges": len(normalized.edges) + len(rejected) + duplicates,
        "retainedSemanticEdges": len(normalized.edges),
        "rejectedSemanticEdges": len(rejected),
        "duplicateSemanticEdges": duplicates,
        "addedEdges": len(normalized.edges),
        "enrichedNodes": 0,
        "correspondingNodes": sum(bool(row.correspondences) for row in bindings),
        "addedNodes": len(bindings),
        "externalNodes": sum(not row.source_file for row in bindings),
        "removedHeuristicEdges": 0,
        "parallelOccurrences": sum(max(0, count - 1) for count in pairs.values()),
        "selfOccurrences": sum(count for (a, b), count in pairs.items() if a == b),
        "reversePairs": sum(a < b and (b, a) in pairs for a, b in pairs),
        "bindingConflicts": len(conflicts),
        "danglingEdges": 0,
        "edgeKeyCollisions": 0,
        **{f"binding{key.title().replace('-', '')}": value for key, value in methods.items()},
    }
    # 报告摘要在加入自身摘要前计算，避免循环定义。
    unsigned = {
        "schemaVersion": 1,
        "bindings": [row.to_dict() for row in bindings],
        "conflicts": conflicts,
        "rejectedEdges": [row.to_dict() for row in rejected],
        "inputDigests": inputs,
        "stats": stats,
        "dispositions": [row.to_dict() for row in normalized.dispositions],
    }
    digest = _digest(unsigned)
    # 图元数据携带协调摘要，后续产物可以绑定同一分析结果。
    working.graph.update(
        evidenceGraphSchemaVersion=EVIDENCE_GRAPH_SCHEMA_VERSION,
        semanticReconcileDigest=digest,
    )
    return SemanticReconcileResult(
        working, normalized, tuple(bindings), rejected, tuple(conflicts), stats, inputs, digest
    )


__all__ = [
    "NodeBinding",
    "RejectedSemanticEdge",
    "SemanticReconcileError",
    "SemanticReconcileResult",
    "reconcile_graph",
]
