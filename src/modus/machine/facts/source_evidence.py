"""Typed source evidence assembled from frozen observations.

N2 owns source decoding, entry detection, and authoring-rule observation. The
resolved N3 graph may strengthen relation bindings, but downstream projection
stages consume this result and never reopen source files or call parser helpers.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modus.paths import ModusPaths

from ..corpus.input_snapshot import InputSnapshot
from ..corpus.source_roles import source_role
from ..languages import CapabilityTier
from ..states import Completeness
from ..store.contracts import SCHEMA_VERSION
from .compiler.models import CompilerSemanticResult
from .entry_observation import entry_identity, normalize_extraction, source_location
from .language_capabilities import capability_for
from .rule_signals import bind_authoring_records

_RESOLUTIONS = frozenset({"exact", "candidate", "heuristic", "unresolved"})


# 投影层读取冻结后的证据包，不再重新打开源码。
# 索引、正文包与覆盖缺口分开传递，支持按需读取和完整性展示。
@dataclass(frozen=True, slots=True)
class SourceEvidence:
    """Bounded, source-backed records safe for N4/N5 consumption."""

    index: dict[str, Any]
    packets: dict[str, dict[str, Any]]
    coverage_gaps: tuple[dict[str, Any], ...]
    source_digests: dict[str, str]
    source_roles: dict[str, str]


# 图中的绝对路径只允许归属当前仓库；外部路径不能冒充本地证据。
def _relative(paths: ModusPaths, value: object) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        try:
            return path.relative_to(paths.root).as_posix()
        except ValueError:
            return ""
    return path.as_posix()


# 统一不同提供者的来源字段，保留编译器与结构提取的能力差异。
def _source_layer(row: Mapping[str, Any]) -> str:
    origin = " ".join(
        str(row.get(key) or "")
        for key in ("source_layer", "sourceLayer", "resolvedBy", "binding_kind", "_origin")
    ).lower()
    if "reconcil" in origin:
        return "reconciled"
    if "compiler" in origin or "semantic" in origin:
        return "compiler"
    if "bind" in origin or "import" in origin:
        return "project-binding"
    return "cst"


# 缺少显式解析等级时保守降级，目标存在本身不足以证明精确绑定。
def _resolution(row: Mapping[str, Any]) -> str:
    value = str(row.get("resolution") or "")
    if value in _RESOLUTIONS:
        return value
    if row.get("candidateCount") or row.get("candidates"):
        return "candidate"
    if row.get("target") or row.get("targetReference"):
        return "heuristic"
    return "unresolved"


# 每条关系附带源码摘要和位置，使消费者能够验证其对应的源码版本。
# 非法行号留空，避免把布尔值解释为行号。
def _witness(relative: str, row: Mapping[str, Any], source_digest: str) -> dict[str, Any]:
    location = row.get("callSite") or row.get("location") or {}
    if not isinstance(location, Mapping):
        location = {}
    start = location.get("startLine", location.get("line", row.get("line")))
    end = location.get("endLine", start)
    return {
        "path": str(location.get("path") or location.get("file") or relative),
        "symbol": str(row.get("symbol") or row.get("sourceSymbol") or ""),
        "startLine": start if isinstance(start, int) and not isinstance(start, bool) else None,
        "endLine": end if isinstance(end, int) and not isinstance(end, bool) else None,
        "sourceDigest": source_digest,
    }


# 语言支持语义分析不等于本次分析已获得完整语义证据。
# 能力等级依据实际编译器回执决定，缺失或部分覆盖需要显式降级。
# 完整语义等级要求当前文件的编译器回执全部完整，不能用其他文件的成功替代。
def _observed_tier(compiler: CompilerSemanticResult, relative: str) -> tuple[CapabilityTier, str]:
    capability = capability_for(relative)
    if capability.tier is not CapabilityTier.SEMANTIC:
        return capability.tier, capability.degradation_reason
    fallback = (
        CapabilityTier.GENERIC
        if capability.extractor == "extract_generic_text"
        else CapabilityTier.STRUCTURAL
    )
    if compiler.mode == "off":
        return fallback, "machine.facts.compiler-disabled"
    receipts = [
        receipt
        for receipt in compiler.coverage_receipts
        if receipt.source_file == relative and receipt.phase == "compiler"
    ]
    if receipts and all(receipt.completeness is Completeness.COMPLETE for receipt in receipts):
        return CapabilityTier.SEMANTIC, ""
    if any(receipt.completeness is Completeness.PARTIAL for receipt in receipts):
        return fallback, "machine.facts.compiler-evidence-partial"
    return fallback, "machine.facts.compiler-provider-unavailable"


# 从冻结快照和已解析图构建统一包，避免跨阶段重复观察源码。
# 节点决定文件归属，关系同时保存目标锚点和目标源码摘要。
# 逐文件失败转成覆盖缺口，其他文件的证据仍然可用。
def observe_source_evidence(
    paths: ModusPaths,
    graph: Any,
    snapshot: InputSnapshot,
    compiler: CompilerSemanticResult,
    *,
    baseline_digest: str,
    rule_observations: Mapping[str, list[dict[str, Any]]],
    materials: Mapping[str, list[dict[str, Any]]] | None = None,
) -> SourceEvidence:
    """Observe source-backed entries and resolved relations exactly once."""
    files: defaultdict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"nodes": [], "edges": []}
    )
    # 节点归属表同时用于边的来源检查和本地目标判定。
    node_files: dict[object, str] = {}
    for node, attrs in graph.nodes(data=True):
        relative = _relative(paths, attrs.get("source_file"))
        if relative not in snapshot.files or capability_for(Path(relative)).role == "document":
            continue
        files[relative]["nodes"].append({**attrs, "id": str(node)})
        node_files[node] = relative

    for source, target, _key, attrs in graph.edges(keys=True, data=True):
        relative = node_files.get(source, "")
        if not relative:
            continue
        target_attrs = graph.nodes[target]
        target_path = node_files.get(target, "")
        target_location = source_location(target_path, target_attrs)
        target_anchors = list(
            target_attrs.get("source_ranges") or target_attrs.get("source_anchors") or []
        )
        # 旧图没有显式范围时，使用已有源码位置补充最小目标锚点。
        if not target_anchors and target_path and target_location.get("startLine"):
            target_anchors = [target_location]
        files[relative]["edges"].append(
            {
                **attrs,
                "source": str(source),
                "target": str(target),
                "target_reference": {
                    "kind": "graph-node" if target_path else "external-symbol",
                    "id": str(target),
                    "entryId": entry_identity(str(target)),
                    "anchors": target_anchors,
                    "sourceDigests": (
                        {target_path: snapshot.files[target_path].digest} if target_path else {}
                    ),
                },
                "target_symbol": target_attrs.get("qualified_name")
                or target_attrs.get("label")
                or str(target),
            }
        )

    packets: dict[str, dict[str, Any]] = {}
    index_rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    roles: dict[str, str] = {}
    for relative, frozen in sorted(snapshot.files.items()):
        capability = capability_for(Path(relative))
        # 文档由知识通道处理，不混入源码语义观察。
        if capability.role == "document" and relative not in (materials or {}):
            continue
        roles[relative] = source_role(relative)
        try:
            content = frozen.read_text()
            evidence = (
                {"entries": [], "relations": [], "gaps": []}
                if relative in (materials or {})
                else normalize_extraction(relative, content, files[relative])
            )
            evidence_tier, degradation_reason = _observed_tier(compiler, relative)
            entries = []
            for entry in evidence.get("entries", []):
                row = dict(entry)
                row["witness"] = {
                    "path": relative,
                    "symbol": str(row.get("symbol") or ""),
                    "signature": str(row.get("signature") or ""),
                    "startLine": (row.get("location") or {}).get("startLine"),
                    "endLine": (row.get("location") or {}).get("endLine"),
                    "sourceDigest": frozen.digest,
                }
                row.update(
                    sourceRole=roles[relative],
                    resolution=str(row.get("resolution") or "exact"),
                    sourceLayer=str(row.get("sourceLayer") or "cst"),
                    evidenceTier=str(evidence_tier),
                    compilerProvider=capability.compiler_provider,
                    frameworkAdapters=list(capability.framework_adapters),
                    entryDetectors=list(capability.entry_detectors),
                    degradationReason=degradation_reason,
                )
                entries.append(row)
            # 归一化关系等级和替代项后，投影层无需理解各提取器的私有字段。
            relations = []
            for relation in evidence.get("relations", []):
                row = dict(relation)
                row.update(
                    resolution=_resolution(row),
                    sourceLayer=_source_layer(row),
                    witness=_witness(relative, row, frozen.digest),
                    alternatives=list(row.get("candidates") or []),
                    reason=str(row.get("reason_code") or row.get("reason") or ""),
                    contextId=str(row.get("analysis_context_id") or row.get("context_id") or ""),
                )
                relations.append(row)
            # 复制缺口记录，避免后续增加文件路径时修改提取器结果。
            packet_gaps = [dict(item) for item in evidence.get("gaps", [])]
            packet: dict[str, Any] = {
                "schemaVersion": SCHEMA_VERSION,
                "path": relative,
                "sourceDigest": frozen.digest,
                "baselineDigest": baseline_digest,
                "entries": entries,
                "relations": relations,
                "authoringRecords": [dict(row) for row in materials[relative]]
                if materials and relative in materials
                else bind_authoring_records(rule_observations.get(relative, []), entries),
                "coverageGaps": packet_gaps,
            }
            # 包键基于路径摘要，文件内容变化由独立的源码摘要表达。
            key = hashlib.sha256(relative.encode()).hexdigest()
            packets[key] = packet
            # 轻量索引只收集检索符号，完整关系留在文件证据包中。
            symbols = sorted(
                {
                    str(value)
                    for entry in entries
                    for value in (
                        entry.get("symbol"),
                        entry.get("signature"),
                        entry.get("displayName"),
                    )
                    if value
                }
            )
            index_rows.append(
                {
                    "path": relative,
                    "pathDigest": key,
                    "sourceDigest": frozen.digest,
                    "symbols": symbols,
                    "entryKinds": sorted({str(row.get("kind") or "") for row in entries}),
                    "entries": len(entries),
                    "relations": len(relations),
                }
            )
            gaps.extend({"path": relative, **row} for row in packet_gaps)
        # 隔离单文件观察故障，诊断只暴露异常类型而不复制可能敏感的内容。
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            gaps.append(
                {
                    "path": relative,
                    "reasonCode": "machine.facts.source-observation-failed",
                    "summary": type(exc).__name__,
                }
            )
    # 只关联材料中明确写出的标识；同名声明保留全部候选，不写入代码社区图。
    declarations: defaultdict[str, set[str]] = defaultdict(set)
    for packet in packets.values():
        for entry in packet["entries"]:
            for name in (entry.get("symbol"), entry.get("declarationName")):
                if name:
                    declarations[str(name)].add(str(entry["entryId"]))
    for packet in packets.values():
        for row in packet["authoringRecords"]:
            if row.get("materialType"):
                row["associations"] = [
                    {
                        "mention": name,
                        "entryIds": sorted(declarations[name]),
                        "basis": "explicit-identifier",
                    }
                    for name in row.get("mentions", [])
                    if name in declarations
                ]
    # 索引与包共享基线摘要，使读取方可拒绝混用不同分析批次。
    index = {
        "schemaVersion": SCHEMA_VERSION,
        "baselineDigest": baseline_digest,
        "files": index_rows,
    }
    return SourceEvidence(index, packets, tuple(gaps), snapshot.hashes, roles)


__all__ = ["SourceEvidence", "observe_source_evidence"]
