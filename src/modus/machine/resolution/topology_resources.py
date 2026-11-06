"""Lift resolved calls into component, RPC and resource occurrences.

This phase consumes reconciled compiler facts and source value summaries. It
retains evidence tiers and unresolved names instead of inventing deployment
bindings. The single-file value cache follows the existing call-site ordering.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from modus.machine.facts.semantic_ir import SemanticEdge, SemanticFacts, SemanticNode, stable_id
from modus.machine.facts.value_summary import SourceValueIndex, ValueSummary, read_value_index
from modus.machine.resolution.topology_records import (
    _occurrence_edge,
    _semantic_edge_attributes,
    _topology_node,
)
from modus.machine.resolution.topology_rules import (
    _BUILTIN_RESOURCE_CATEGORIES,
    _annotations,
    _builtin_classifications,
    _capped_resolution,
    _Classification,
    _dubbo_contract,
    _endpoint_contract,
    _grpc_contract,
    _is_dubbo_service,
    _is_grpc_service,
    _mq_contract,
    _resolve_owner,
    _select_deployable,
)
from modus.paths import ModusPaths

_RPC_INJECTION_MARKERS = ("Reference", "DubboReference", "FeignClient", "GrpcClient")
# Substrings of a lowered target qualified name that mark an RPC client call.
_RPC_TARGET_MARKERS = ("dubbo", "grpc", "feignclient", "httpclient")
_STATE_OPERATIONS = re.compile(r"(set|change|update|transition).*(status|state)|markAs", re.I)


# 只缓存最近文件的值索引，避免分析大仓库时长期持有全部源码解析状态。
class _ValueIndexCache:
    """Single-slot cache of the value index for the last-seen source file.

    Callers iterate calls in call-site file order, so keeping exactly one
    parsed index alive covers all lookups without retaining source text.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._file = ""
        self._index: SourceValueIndex | None = None

    def for_file(self, file: str) -> SourceValueIndex | None:
        """Return the index for `file`, re-reading only when the file changes."""
        if file != self._file:
            self._file = file
            self._index = read_value_index(self._root, file)
        return self._index


# 调用方优先归属组件，再回退到可确定的部署或构建单元。
def _caller_topology_id(
    caller_node: SemanticNode,
    caller_owner: str | None,
    deployables: Mapping[str, list[dict[str, Any]]],
) -> str:
    """Component ID when owned, else the caller's deployable or build-unit node ID."""
    if caller_owner is not None:
        return caller_owner
    source_file = caller_node.source_anchors[0].file if caller_node.source_anchors else ""
    caller_deployable = _select_deployable(
        deployables.get(caller_node.build_unit_id, []),
        source_file,
    )
    if caller_deployable:
        return str(caller_deployable["id"])
    return f"build-unit:{caller_node.build_unit_id}"


# RPC 分类保留其依据与契约，精确方法绑定不自动证明远程调用性质。
def _maybe_lift_rpc_invocation(
    call: SemanticEdge,
    caller_node: SemanticNode,
    target_node: SemanticNode,
    target_owner_semantic: str,
    source_topology: str,
    lowered_target: str,
    target_annotation_items: tuple[str, ...],
    target_owner_annotation_items: tuple[str, ...],
    receiver_injection: SemanticEdge | None,
    receiver_binding: str,
    nodes: dict[str, dict[str, Any]],
    raw_occurrence_edges: list[dict[str, Any]],
) -> None:
    """Emit an rpc-service node plus invokes occurrence when the call is an RPC.

    A verified receiver injection or RPC markers on the target select the
    contract scheme (gRPC/HTTP/Dubbo); non-RPC calls are left untouched.
    """
    target_text = target_node.qualified_name
    target_annotations = " ".join(target_annotation_items)
    target_owner_annotations = " ".join(target_owner_annotation_items)
    rpc_injection_verified = bool(
        receiver_injection
        and any(
            marker in " ".join(receiver_injection.evidence) for marker in _RPC_INJECTION_MARKERS
        )
    )
    if not (
        rpc_injection_verified
        or any(marker in lowered_target for marker in _RPC_TARGET_MARKERS)
        or "FeignClient" in target_owner_annotations
        or "Mapping" in target_annotations
    ):
        return
    rpc_annotations = " ".join(receiver_injection.evidence) if receiver_injection else ""
    contract_key = (
        _grpc_contract(target_text)
        if "grpc" in lowered_target or "grpc" in target_owner_annotations.lower()
        else _endpoint_contract(
            target_node,
            target_annotations,
            target_owner_annotations,
            owner_is_dubbo=_is_dubbo_service(target_owner_annotation_items),
            owner_is_grpc=_is_grpc_service(target_owner_annotation_items),
            method_is_grpc=_is_grpc_service(target_annotation_items),
        )
        if "http" in lowered_target
        or "feign" in lowered_target
        or "FeignClient" in target_owner_annotations
        or "Mapping" in target_annotations
        else _dubbo_contract(target_text, rpc_annotations)
    )
    resource_id = stable_id(
        "rpc-service",
        getattr(caller_node, "analysis_context_id", ""),
        caller_node.build_unit_id,
        receiver_binding or caller_node.id,
        target_owner_semantic or target_text,
    )
    nodes.setdefault(
        resource_id,
        _topology_node(
            node_id=resource_id,
            kind="rpc-service",
            qualified_name=target_owner_semantic.removeprefix(f"{target_node.language}:")
            or target_text,
            build_unit_id=caller_node.build_unit_id,
            language=target_node.language,
            source_anchors=(call.call_site.to_dict(),) if call.call_site else (),
            attributes={
                "sourceBasis": "relation",
                "contractKey": contract_key,
                "external": not bool(target_node.source_anchors),
            },
        ),
    )
    rpc_tier = "annotation-verified" if rpc_injection_verified else "keyword-heuristic"
    raw_occurrence_edges.append(
        _occurrence_edge(
            source=source_topology,
            target=resource_id,
            relation="invokes",
            resolution=_capped_resolution(call.resolution, rpc_tier),
            operation=call.operation,
            contract_key=contract_key,
            evidence=(*call.evidence, "RPC client/framework rule"),
            call_site=call.call_site.to_dict() if call.call_site else None,
            provenance=call.provenance.to_dict() if call.provenance else {},
            attributes=_semantic_edge_attributes(
                call,
                functionEdgeId=call.id,
                classificationEvidence=rpc_tier,
            ),
        )
    )


# 资源身份与调用见证分别生成，多个调用可指向同一资源而保持独立来源。
def _emit_resource_occurrences(
    classifications: Sequence[_Classification],
    call: SemanticEdge,
    caller_node: SemanticNode,
    source_topology: str,
    receiver_binding: str,
    summary: ValueSummary,
    nodes: dict[str, dict[str, Any]],
    raw_occurrence_edges: list[dict[str, Any]],
) -> None:
    """Materialize one resource node and occurrence edge per classification row.

    `summary` must be the final per-call value summary: it caps resolution to
    candidate for dynamic or multi-valued names and is recorded verbatim.
    """
    for kind, relation, resource_name, framework, tier, resolved_from in classifications:
        contract_key = (
            _mq_contract(framework, resource_name)
            if kind == "topic" and not resource_name.startswith("dynamic-")
            else ""
        )
        namespace = stable_id(
            "resource-namespace",
            getattr(caller_node, "analysis_context_id", ""),
            caller_node.build_unit_id,
            str(call.attributes.get("resourceBindingId") or receiver_binding or caller_node.id),
        )
        resource_id = stable_id(kind, namespace, framework, resource_name)
        nodes.setdefault(
            resource_id,
            _topology_node(
                node_id=resource_id,
                kind=kind,
                qualified_name=resource_name,
                build_unit_id=caller_node.build_unit_id,
                source_anchors=(call.call_site.to_dict(),) if call.call_site else (),
                attributes={
                    "sourceBasis": "relation",
                    "framework": framework,
                    "dynamic": resource_name.startswith("dynamic-"),
                    "namespaceId": namespace,
                    **({"contractKey": contract_key} if contract_key else {}),
                },
                provenance=call.provenance.to_dict() if call.provenance else {},
            ),
        )
        base_resolution = (
            call.resolution
            if not resource_name.startswith("dynamic-") and len(summary.values) <= 1
            else "candidate"
        )
        raw_occurrence_edges.append(
            _occurrence_edge(
                source=source_topology,
                target=resource_id,
                relation=relation,
                resolution=_capped_resolution(base_resolution, tier),
                operation=call.operation,
                contract_key=contract_key,
                evidence=(*call.evidence, f"{framework} framework rule"),
                call_site=call.call_site.to_dict() if call.call_site else None,
                provenance=call.provenance.to_dict() if call.provenance else {},
                attributes=_semantic_edge_attributes(
                    call,
                    functionEdgeId=call.id,
                    classificationEvidence=tier,
                    nameResolvedFrom=resolved_from,
                    valueSummary=summary.to_dict(),
                    sourceSymbolId=call.source,
                    effect="unknown-effect" if relation == "uses" else relation,
                ),
            )
        )


# 调用提升复用分类策略和静态值摘要，分类置信度限制最终关系等级。
def _lift_calls(
    paths: ModusPaths,
    facts: SemanticFacts,
    semantic_nodes: Mapping[str, SemanticNode],
    type_lookup: Mapping[tuple[str, str, str], str],
    component_ids: Mapping[str, str],
    deployables: Mapping[str, list[dict[str, Any]]],
    injection_edges: Mapping[str, SemanticEdge],
    nodes: dict[str, dict[str, Any]],
    raw_occurrence_edges: list[dict[str, Any]],
) -> None:
    """Project each calls edge onto component, RPC and resource occurrences.

    Mutates `nodes` and `raw_occurrence_edges` in place. Calls are ordered by
    file, so one syntax index suffices for all resource observations without
    retaining a repository of source strings or ASTs.
    """
    value_cache = _ValueIndexCache(paths.root)
    for call in sorted(
        facts.edges, key=lambda item: (item.call_site.file if item.call_site else "", item.id)
    ):
        if call.relation != "calls":
            continue
        caller_node = semantic_nodes.get(call.source)
        target_node = semantic_nodes.get(call.target)
        if caller_node is None or target_node is None:
            continue
        caller_owner = component_ids.get(_resolve_owner(caller_node, type_lookup))
        target_owner_semantic = _resolve_owner(target_node, type_lookup)
        target_owner = component_ids.get(target_owner_semantic)
        if caller_owner and target_owner and caller_owner != target_owner:
            raw_occurrence_edges.append(
                _occurrence_edge(
                    source=caller_owner,
                    target=target_owner,
                    relation="calls",
                    resolution=call.resolution,
                    operation=call.operation,
                    evidence=call.evidence,
                    call_site=call.call_site.to_dict() if call.call_site else None,
                    provenance=call.provenance.to_dict() if call.provenance else {},
                    attributes=_semantic_edge_attributes(call, functionEdgeId=call.id),
                )
            )

        target_text = target_node.qualified_name
        lower = target_text.lower()
        summary = ValueSummary(reason="no-call-site")
        if call.call_site and any(
            category.matched_framework(lower) for category in _BUILTIN_RESOURCE_CATEGORIES
        ):
            value_index = value_cache.for_file(call.call_site.file)
            if value_index is not None:
                summary = value_index.argument(
                    line=call.call_site.line,
                    column=call.call_site.column,
                    operation=call.operation,
                    column_encoding=call.call_site.column_encoding,
                )
        source_topology = _caller_topology_id(caller_node, caller_owner, deployables)

        target_annotation_items = _annotations(target_node)
        target_owner_annotation_items = (
            _annotations(semantic_nodes[target_owner_semantic])
            if target_owner_semantic in semantic_nodes
            else ()
        )
        # A type-level injection elsewhere does not bind this receiver. Only a
        # provider-proved receiver binding may upgrade this particular call.
        receiver_binding = str(call.attributes.get("receiverBindingId") or "")
        receiver_injection = injection_edges.get(receiver_binding)
        _maybe_lift_rpc_invocation(
            call,
            caller_node,
            target_node,
            target_owner_semantic,
            source_topology,
            lower,
            target_annotation_items,
            target_owner_annotation_items,
            receiver_injection,
            receiver_binding,
            nodes,
            raw_occurrence_edges,
        )
        classifications = _builtin_classifications(
            call, caller_node, target_annotation_items, lower, summary
        )
        if _STATE_OPERATIONS.search(call.operation):
            classifications.append(
                (
                    "state-machine",
                    "transitions_to",
                    target_owner_semantic or target_text,
                    "state",
                    "keyword-heuristic",
                    "operation-name",
                )
            )
        _emit_resource_occurrences(
            classifications,
            call,
            caller_node,
            source_topology,
            receiver_binding,
            summary,
            nodes,
            raw_occurrence_edges,
        )
