"""Language-neutral, source-bound evidence for capability discovery.

This is an observation adapter, not a Domain/Module classifier. Structural
references remain candidates even when a parser successfully extracted them.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from modus.machine.corpus.source_snapshot import SourceSnapshot
from modus.machine.facts import structural
from modus.machine.facts.language_capabilities import (
    LanguageCapability,
    capability_for,
    structural_extractors,
)

_DECLARATION_RELATIONS = {"contains", "method", "defines", "declares", "function", "exports"}
_NON_ENTRY_KINDS = {
    "file",
    "reference",
    "type",
    "class",
    "interface",
    "enum",
    "namespace",
    "package",
    "module",
    "field",
    "property",
    "variable",
    "parameter",
    "configuration",
    "data-definition",
    "document",
}
# Capability roles that override the heuristic node kind (except for file nodes).
_ROLE_OVERRIDE_KINDS = {"configuration", "data-definition", "document"}
# Lines scanned above a Java declaration when the extractor supplied no annotations.
_JAVA_ANNOTATION_LOOKBACK = 25
# Truncated sha256 hex length shared by entry and observation identities.
_IDENTITY_HEX_LENGTH = 32


# 兼容提取器的行号表示，只接受正行号，未知位置保持为空。
def _line(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("startLine", value.get("line"))
    match = re.fullmatch(r"L?(\d+)(?::\d+)?(?:-\d+(?::\d+)?)?", str(value or ""))
    return int(match[1]) if match and int(match[1]) > 0 else None


# 入口是图节点的视图身份，不在此处再次解析或合并符号。
def entry_identity(node_id: str) -> str:
    """A view identity of the bound node, never another symbol resolver."""
    return "entry:" + hashlib.sha256(node_id.encode()).hexdigest()[:_IDENTITY_HEX_LENGTH]


# 优先使用显式调用位置或源码范围，再兼容旧字符串位置。
# 有同文件字节偏移时从 UTF-8 内容校准行列，避免字符编码造成偏移。
def source_location(relative: str, row: dict, content: str | None = None) -> dict:
    anchor = row.get("call_site") or row.get("callSite") or row.get("location") or {}
    ranges = row.get("source_ranges") or row.get("source_anchors") or row.get("sourceAnchors")
    if not anchor and ranges:
        anchor = ranges[0]
    start = _line(anchor) or _line(row.get("source_location"))
    column = anchor.get("column", anchor.get("startColumn")) if anchor else None
    if column is None:
        match = re.match(r"L?\d+:(\d+)", str(row.get("source_location") or ""))
        column = int(match[1]) if match else None
    result = {
        "path": anchor.get("file", anchor.get("path", relative)) or relative,
        "startLine": start,
        "startColumn": column,
        "endLine": anchor.get("endLine", row.get("source_end_line", start)),
        "endColumn": anchor.get("endColumn"),
        "startByte": anchor.get("startByte"),
        "endByte": anchor.get("endByte"),
        "columnEncoding": anchor.get("columnEncoding", anchor.get("coordinateEncoding", "unknown")),
        "precision": "range" if start and column else "line" if start else "unknown",
    }
    _apply_byte_location(result, anchor, relative, content)
    return result


def _apply_byte_location(result: dict, anchor: dict, relative: str, content: str | None) -> None:
    """只有同一源文件中的有效字节范围才能覆盖观察到的行列。"""
    offset = anchor.get("startByte")
    if content is not None and result["path"] == relative and isinstance(offset, int):
        raw = content.encode("utf-8")
        end = anchor.get("endByte", offset)
        if 0 <= offset <= end <= len(raw):
            result.update(
                startLine=raw.count(b"\n", 0, offset) + 1,
                startColumn=offset - raw.rfind(b"\n", 0, offset),
                endLine=raw.count(b"\n", 0, end) + 1,
                endColumn=end - raw.rfind(b"\n", 0, end),
                precision="range",
                coordinateEncoding="utf-8-byte-column",
            )


# 保留提供者原始字段，同时补充统一的位置表示。
# 没有原始位置且缺少行号时不生成虚假的调用锚点。
def canonical_call_site(location: dict, row: dict) -> dict:
    original = dict(row.get("call_site") or row.get("callSite") or {})
    if not original and location["startLine"] is None:
        return {}
    return {
        **original,
        "file": location["path"],
        "line": location["startLine"],
        "column": location["startColumn"],
        "endLine": location["endLine"],
        "endColumn": location["endColumn"],
        "coordinateEncoding": location.get("coordinateEncoding", "provider"),
    }


# 声明展示只扫描有限行和字符，避免多行签名把整个函数体带入证据。
def _declaration(lines: list[str], start: int) -> tuple[str, int]:
    selected: list[str] = []
    for index in range(start - 1, min(len(lines), start + 11)):
        text = lines[index].strip()
        selected.append(text)
        if any(char in text for char in "{;") or text.endswith(":") or len(selected) >= 12:
            break
        if index + 1 < len(lines) and not text and selected:
            break
    return " ".join(selected)[:1200], start + len(selected) - 1


# 只收集紧邻声明的有界注释，跨过装饰器但不跨过其他源码语句。
def _leading_comment(lines: list[str], start: int) -> str:
    selected: list[str] = []
    for line in reversed(lines[max(0, start - 17) : start - 1]):
        text = line.strip()
        if not text and not selected:
            continue
        if text.startswith(("//", "/*", "*", "#", "--", "!", "///", "<!--")):
            selected.append(text)
        elif text.startswith(("@", "[")):
            continue
        else:
            break
    return "\n".join(reversed(selected))[:1600]


# 声明增强只能通过显式节点身份连接，名称相似不能证明同一声明。
def _index_nodes(extraction: dict) -> dict[str, dict]:
    """Key extracted nodes by id, overlaying declarations joined by explicit identity."""
    nodes = {str(node["id"]): node for node in extraction.get("nodes", []) if node.get("id")}
    # Declaration enrichment may join only an explicit identity. Matching names
    # and overlapping lines here would create a second, conflicting reconciler.
    for declaration in extraction.get("declarations", []):
        nid = str(declaration.get("graph_node_id") or declaration.get("id") or "")
        if nid:
            nodes[nid] = {**nodes.get(nid, {}), **declaration, "id": nid}
    return nodes


# 所有者来自已有声明关系，不根据路径或命名猜测业务归属。
def _declaration_parents(extraction: dict) -> dict[str, tuple[str, str]]:
    """Map each declared child node id to its (owner node id, declaration relation)."""
    parents: dict[str, tuple[str, str]] = {}
    for edge in extraction.get("edges", []):
        if edge.get("relation") in _DECLARATION_RELATIONS:
            parents[str(edge.get("target"))] = (str(edge.get("source")), edge.get("relation"))
    return parents


# 显式节点种类优先；配置和文档能力可覆盖结构启发式分类。
def _entry_kind(
    node: dict,
    label: str,
    relative: str,
    parent: str,
    relation: str,
    capability: LanguageCapability,
) -> str:
    """Classify one node: explicit kind wins, then structural heuristics, then role override."""
    kind = str(node.get("kind") or node.get("type") or "")
    if label == Path(relative).name:
        kind = "file"
    elif not kind:
        kind = (
            "method"
            if relation == "method"
            else "function"
            if "(" in label and parent
            else "type"
            if parent
            else "reference"
        )
    if capability.role in _ROLE_OVERRIDE_KINDS:
        kind = capability.role if kind != "file" else kind
    return kind


# 提供者签名优先于源码展示片段，同时将展示结束行限制在当前文件内。
def _entry_signature(node: dict, lines: list[str], start: int) -> tuple[str, int]:
    """Return (signature text, display end line), preferring provider-supplied values."""
    signature, end = _declaration(lines, start)
    if node.get("signature"):
        signature = str(node["signature"])
        end = min(len(lines), max(start, int(node.get("source_end_line") or start)))
    return signature, end


# 保留提供者限定名；缺失时结合文件、所有者和参数生成回退表示。
def _entry_symbol(
    node: dict, relative: str, owner: str, name: str, kind: str, signature: str
) -> str:
    """Derive a stable symbol id; synthesized ones embed the normalized parameter list."""
    symbol = str(node.get("qualified_name") or node.get("symbol") or "")
    if not symbol:
        symbol = f"{relative}#{owner + '.' if owner else ''}{name}"
        if kind in {"method", "function"}:
            parameters = re.search(r"\b" + re.escape(name) + r"\s*(\([^)]*\))", signature)
            if parameters:
                symbol += " ".join(parameters.group(1).split())
    return symbol


# 回看范围有限，且不跨越包含类型边界，防止类注解泄漏给方法。
def _java_annotation_fallback(lines: list[str], start: int, *, declaration_kind: str) -> list[str]:
    """Scan annotations without crossing the containing Java type boundary."""
    prefix: list[str] = []
    for text in reversed(lines[max(0, start - _JAVA_ANNOTATION_LOOKBACK) : start]):
        stripped = text.strip()
        type_declaration = re.search(r"\b(?:class|interface|enum|record)\s+\w+", text)
        if type_declaration and declaration_kind not in {"type", "class", "interface", "enum"}:
            break
        if stripped.endswith((";", "}")) or (
            stripped.endswith("{") and not stripped.startswith("@")
        ):
            break
        prefix.append(text)
    return re.findall(r"@[\w.]+(?:\([^@]*?\))?", "\n".join(reversed(prefix)), re.S)


# 语义注解优先；只有 Java 且缺少注解时才启用文本回退。
def _entry_annotations(
    node: dict, capability: LanguageCapability, lines: list[str], start: int
) -> list[Any]:
    """Collect declared annotations as a list, scanning Java source text when absent."""
    semantic_attrs = node.get("semantic_attributes") or {}
    annotations = semantic_attrs.get("annotations", node.get("annotations", []))
    annotations = [annotations] if isinstance(annotations, str) else list(annotations or [])
    if capability.language == "java" and not annotations:
        annotations = _java_annotation_fallback(
            lines, start, declaration_kind=str(node.get("kind") or "")
        )
    return annotations


# 已声明契约与 Java 注解契约汇总，声明信息不等于部署验证结果。
def _entry_contracts(
    node: dict, capability: LanguageCapability, annotations: list[Any], symbol: str, kind: str
) -> tuple[list[dict], str | None, str | None]:
    """Return (declared contracts incl. any HTTP route, api display name, route identity)."""
    api: str | None = ""
    route: str | None = ""
    if capability.language == "java":
        from modus.machine.facts.source_contracts import _annotations, _http_contract

        api, route = _http_contract(
            _annotations({"annotations": annotations}), symbol=symbol, kind=kind
        )
    contracts = list(node.get("contracts") or [])
    if route:
        contracts.append(
            {
                "kind": "http",
                "identity": route,
                "direction": "provides",
                "resolution": "declared",
            }
        )
    return contracts, api, route


# 不可定位节点转为覆盖缺口，避免产出无法回查的入口记录。
# 源码摘要绑定本次内容，展示范围与提供者精确范围保留来源区别。
# 入口候选只表达可调查性，不自动升级为领域或模块。
def _collect_entries(
    relative: str,
    content: str,
    lines: list[str],
    capability: LanguageCapability,
    extraction: dict,
    nodes: dict[str, dict],
    parents: dict[str, tuple[str, str]],
    digest: str,
) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Build one entry record per locatable node.

    Returns (records, gaps for unlocatable nodes, node id -> entry id mapping);
    records preserve node iteration order and never invent owners or symbols.
    """
    records: list[dict] = []
    gaps: list[dict] = []
    ids: dict[str, str] = {}
    for nid, node in nodes.items():
        label = str(node.get("label") or nid)
        location = source_location(relative, node, content)
        start = location["startLine"]
        if start is None or start > len(lines):
            gaps.append(
                {
                    "path": relative,
                    "nodeId": nid,
                    "reasonCode": "machine.facts.declaration-location-unavailable",
                }
            )
            continue
        parent, relation = parents.get(nid, ("", ""))
        kind = _entry_kind(node, label, relative, parent, relation, capability)
        signature, end = _entry_signature(node, lines, start)
        parent_label = str(nodes.get(parent, {}).get("label") or "")
        name = label.removeprefix(".").removesuffix("()")
        owner = str(
            node.get("owner")
            or (parent_label if parent_label and parent_label != Path(relative).name else "")
        )
        symbol = _entry_symbol(node, relative, owner, name, kind, signature)
        entry_id = entry_identity(nid)
        ids[nid] = entry_id
        annotations = _entry_annotations(node, capability, lines, start)
        comment = str(
            node.get("doc_comment") or node.get("comment") or _leading_comment(lines, start)
        )
        from modus.machine.facts.search_metadata import source_vocabulary

        vocabulary, _ = source_vocabulary(
            {**node, "language": capability.language, "annotations": annotations, "kind": kind}
        )
        contracts, api, route = _entry_contracts(node, capability, annotations, symbol, kind)
        # 契约身份加入检索词汇，使入口可以按路由或接口被定位。
        vocabulary.extend(item["identity"] for item in contracts)
        records.append(
            {
                "entryId": entry_id,
                "graphNodeId": nid,
                "analysisContextId": node.get("analysis_context_id", node.get("context_id", "")),
                "correspondences": list(node.get("correspondences") or []),
                "symbol": symbol,
                "language": capability.language,
                "symbolId": node.get("symbol_id") or node.get("semantic_id") or symbol,
                "kind": kind,
                "declarationName": name.rsplit(".", 1)[-1].rsplit("::", 1)[-1],
                "sourceRole": capability.role,
                "signature": signature,
                "displayName": str(api or node.get("display_name") or node.get("api") or label),
                "route": route
                or next((item["identity"] for item in contracts if item["kind"] == "http"), ""),
                "searchLabels": vocabulary,
                "contracts": contracts,
                "decorators": node.get("decorators", []),
                "comment": comment,
                "annotations": annotations,
                "location": {
                    **location,
                    "symbol": symbol,
                    "endLine": end,
                    "rangeOrigin": "provider" if node.get("source_end_line") else "source-display",
                },
                "sourceDigest": digest,
                # 文件、类型及数据字段保留证据，但不作为默认业务入口候选。
                "entryCandidate": kind not in _NON_ENTRY_KINDS,
                "provenance": {
                    "kind": "current-source",
                    "extractor": capability.extractor,
                    "semantic": node.get("semantic_provenance") or {},
                },
                "analysisCompleteness": node.get("analysis_completeness")
                or node.get(
                    "analysisCompleteness", extraction.get("analysisCompleteness", "structural")
                ),
            }
        )
    return records, gaps, ids


# 仅投影声明入口，供不需要关系图的初始化范围识别复用。
def project_entries(relative: str, content: str, extraction: dict) -> dict[str, Any]:
    """Project only declaration entries for initialization scope evidence."""
    capability = capability_for(Path(relative))
    nodes = _index_nodes(extraction)
    entries, gaps, _ids = _collect_entries(
        relative,
        content,
        content.splitlines(),
        capability,
        extraction,
        nodes,
        _declaration_parents(extraction),
        hashlib.sha256(content.encode()).hexdigest(),
    )
    return {"entries": entries, "gaps": gaps}


# 回退观察身份包含位置和来源，防止不同提供者的证据相互覆盖。
def _observation_identity(
    source: str, target: str, edge: dict, location: dict, provenance: dict
) -> str:
    """Deterministic fallback observation id hashing the edge tuple with sorted JSON keys."""
    import json

    return (
        "observation:"
        + hashlib.sha256(
            json.dumps(
                [source, target, edge.get("relation"), location, provenance], sort_keys=True
            ).encode()
        ).hexdigest()[:_IDENTITY_HEX_LENGTH]
    )


# 只交付来源入口存在的关系，目标则可保留外部或未解析引用。
# 声明精度、分派精度与分析完整性分开保存，供下游保守消费。
def _collect_relations(
    relative: str,
    content: str,
    capability: LanguageCapability,
    extraction: dict,
    nodes: dict[str, dict],
    ids: dict[str, str],
) -> list[dict]:
    """Normalize extractor edges whose source node produced an entry record."""
    relations: list[dict] = []
    for edge in extraction.get("edges", []):
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source not in ids:
            continue
        target_reference = dict(edge.get("target_reference") or {})
        target_reference.setdefault("kind", "graph-node")
        target_reference.setdefault("id", target)
        target_reference.setdefault("entryId", entry_identity(target))
        target_reference.setdefault(
            "anchors", edge.get("target_anchors", edge.get("targetAnchors", []))
        )
        target_reference.setdefault("sourceDigests", edge.get("target_source_digests", {}))
        location = source_location(relative, edge, content)
        provenance = (
            edge.get("semantic_provenance")
            or edge.get("provenance")
            or {"extractor": capability.extractor}
        )
        observation = edge.get("semantic_edge_id") or edge.get("id")
        if not observation:
            observation = _observation_identity(source, target, edge, location, provenance)
        relations.append(
            {
                "id": observation,
                "source": ids[source],
                "target": entry_identity(target),
                "sourceReference": {"kind": "graph-node", "id": source, "entryId": ids[source]},
                "targetReference": target_reference,
                "targetSymbol": str(
                    edge.get("target_symbol")
                    or nodes.get(target, {}).get("qualified_name")
                    or nodes.get(target, {}).get("label")
                    or target
                ),
                "targetAnchors": target_reference["anchors"],
                "relation": str(edge.get("relation") or "references"),
                "resolution": edge.get("resolution")
                or ("exact" if edge.get("relation") in _DECLARATION_RELATIONS else "candidate"),
                "bindingKind": edge.get("binding_kind", edge.get("bindingKind", "structural")),
                "declarationResolution": edge.get(
                    "declaration_resolution", edge.get("declarationResolution")
                ),
                "dispatchResolution": edge.get(
                    "dispatch_resolution", edge.get("dispatchResolution")
                ),
                "resolvedBy": edge.get("resolvedBy", "structural"),
                "contextId": edge.get(
                    "context_id",
                    edge.get(
                        "analysisContextId",
                        provenance.get("contextId", provenance.get("contextDigest", "")),
                    ),
                ),
                "contractKey": edge.get("contract_key", edge.get("contractKey")),
                "analysisCompleteness": edge.get(
                    "analysis_completeness", edge.get("analysisCompleteness", "structural")
                ),
                "provenance": provenance,
                "evidence": list(edge.get("evidence") or []),
                "support": list(edge.get("support") or edge.get("supportIds") or []),
                "callSite": canonical_call_site(location, edge),
                "location": location,
            }
        )
    return relations


# 未绑定原始调用仍保留名称和位置，缺少目标不是删除观察的理由。
def _raw_call_relations(
    relative: str, content: str, extraction: dict, ids: dict[str, str]
) -> list[dict]:
    """Emit unresolved call observations for raw calls whose caller produced an entry."""
    relations: list[dict] = []
    for call in extraction.get("raw_calls", []):
        if str(call.get("caller_nid")) in ids:
            relations.append(
                {
                    "source": ids[str(call["caller_nid"])],
                    "target": "unresolved:" + str(call.get("callee") or ""),
                    "sourceReference": {
                        "kind": "graph-node",
                        "id": str(call["caller_nid"]),
                        "entryId": ids[str(call["caller_nid"])],
                    },
                    "targetReference": {
                        "kind": "unresolved-name",
                        "name": str(call.get("callee") or ""),
                    },
                    "targetSymbol": str(call.get("callee") or ""),
                    "relation": "calls",
                    "resolution": "unresolved",
                    "bindingKind": "structural",
                    "location": source_location(relative, call, content),
                    "callSite": canonical_call_site(source_location(relative, call, content), call),
                    "resolvedBy": "unresolved",
                }
            )
    return relations


# 提取失败、部分解析和主动排除分别记录，空结果不能掩盖覆盖问题。
def _extend_extraction_gaps(
    gaps: list[dict], relative: str, extraction: dict, records: list[dict], relations: list[dict]
) -> None:
    """Append extractor-level gaps (errors, diagnostics, partial parses, skips) in order."""
    if extraction.get("error"):
        gaps.append({"path": relative, "reasonCode": "machine.facts.extraction-failed"})
    for diagnostic in extraction.get("diagnostics", []):
        gaps.append(
            {
                "path": relative,
                "reasonCode": str(diagnostic.get("code") or "machine.facts.extraction-diagnostic"),
            }
        )
    if extraction.get("analysisCompleteness") == "partial" or any(
        row["analysisCompleteness"] in {"partial", "fallback"}
        for row in [*records, *relations]
        if "analysisCompleteness" in row
    ):
        gaps.append({"path": relative, "reasonCode": "machine.facts.partial-parse"})
    if extraction.get("skipped"):
        gaps.append(
            {
                "path": relative,
                "reasonCode": "machine.facts.extraction-skipped",
                "disposition": "excluded",
            }
        )


# 入口检测器在统一观察边界运行，按实现身份去重防止别名重复调用。
# 声明、关系和缺口共享同一内容摘要与能力配置。
def normalize_extraction(relative: str, content: str, extraction: dict) -> dict:
    """Normalize the actual structural/compiled nodes without guessing owners."""
    capability = capability_for(relative)
    if capability is None:
        return {
            "entries": [],
            "relations": [],
            "gaps": [
                {
                    "path": relative,
                    "reasonCode": "machine.facts.no-structural-extractor",
                }
            ],
            "status": "partial",
        }
    lines = content.splitlines()
    from modus.machine.facts.extension_registry import builtin_extensions

    invoked: set[int] = set()
    for name in capability.entry_detectors:
        detector = builtin_extensions().entry_detectors[name].implementation
        if id(detector) in invoked:
            continue
        # 记录实际函数身份，多个注册名指向同一检测器时只执行一次。
        invoked.add(id(detector))
        extraction = detector(relative, content, capability.language, extraction)
    digest = hashlib.sha256(content.encode()).hexdigest()
    nodes = _index_nodes(extraction)
    parents = _declaration_parents(extraction)
    records, gaps, ids = _collect_entries(
        relative, content, lines, capability, extraction, nodes, parents, digest
    )
    relations = _collect_relations(relative, content, capability, extraction, nodes, ids)
    # 结构化关系之外补齐未解析调用，保留后续调查需要的缺口。
    relations.extend(_raw_call_relations(relative, content, extraction, ids))
    _extend_extraction_gaps(gaps, relative, extraction, records, relations)
    return {
        "entries": sorted(records, key=lambda row: (row["location"]["startLine"], row["symbol"])),
        "relations": relations,
        "gaps": gaps,
        "status": "partial" if gaps else "ready",
    }


# 从内存快照提取，避免分析时再次读取变化中的磁盘源码。
# 单文件解析器异常降级为证据缺口，不能中断其他文件的观察。
def extract_source_entries(root: Path, relative: str, content: str) -> dict:
    capability = capability_for(relative)
    if capability is None:
        return normalize_extraction(relative, content, {})
    if capability.extractor == "source-text":
        raw: dict = {
            "nodes": [
                {
                    "id": relative,
                    "label": relative,
                    "kind": "configuration",
                    "source_location": "L1",
                }
            ],
            "edges": [],
        }
    else:
        try:
            extract = structural
            parser = structural_extractors().get(
                Path(relative).suffix
            ) or structural_extractors().get(Path(relative).suffix.lower())
            if relative.endswith(".blade.php"):
                parser = extract.extract_blade
            if parser is None:
                from modus.machine.facts.generic import extract_generic_text

                parser = extract_generic_text
            # 解析器接收被冻结的内容视图，文件路径仅提供身份和语言上下文。
            raw = parser(SourceSnapshot(root / relative, content))
        # NOCA:broad-except(隔离第三方解析器故障，保留异常类型与证据缺口并继续其他文件)
        except Exception as exc:
            # Deliberate isolation downgrade: a parser crash in one file must not
            # sink the whole build; it degrades to an error-gap evidence packet.
            raw = {"nodes": [], "edges": [], "error": f"{type(exc).__name__}: {exc}"}
    return normalize_extraction(relative, content, raw)
