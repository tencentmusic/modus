"""Bind multi-producer observations into one resolved program model.

N3 owns identity reconciliation, typed relations and topology quarantine. It
does not cluster business capabilities or publish the underlying graph.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

from ..corpus.source_roles import build_unit_memberships
from ..errors import safe_error_summary
from ..facts.lifecycle import ObservedProgramFacts
from ..facts.semantic_ir import SemanticFacts
from ..facts.source_evidence import SourceEvidence, observe_source_evidence
from ..states import Completeness, ExecutionStatus
from .evidence_graph import build_evidence_graph
from .reference_outcomes import reconcile_reference_outcomes
from .semantic_reconcile import SemanticReconcileResult, reconcile_graph
from .topology import build_topology
from .view_quarantine import quarantine_topology

GraphBuilder = Callable[..., "nx.MultiDiGraph[str]"]


# N3 统一持有解析后的图；后续能力与投影阶段消费这份结果。
# 诊断输入与阶段摘要保留来源，便于解释局部降级。
# 构建单元归属与业务候选划分分离，避免混淆两种边界。
@dataclass(frozen=True, slots=True)
class ResolvedProgram:
    """The sole authoritative N3 graph plus its bounded derived topology."""

    baseline_digest: str
    repository_root: Path
    graph: nx.MultiDiGraph[str]
    reconciliation: SemanticReconcileResult
    topology: dict[str, Any]
    quarantine: dict[str, Any]
    reference_outcomes: dict[str, Any]
    source_evidence: SourceEvidence
    build_unit_assignments: dict[str, tuple[tuple[str, ...], str]]
    diagnostic_inputs: dict[str, Any]
    stage_summary: dict[str, dict[str, Any]]


# 结构图先建立，再尝试补充编译器身份与关系。
# 调和失败会重建结构图，避免使用可能已经部分修改的对象。
# 拓扑拥有独立的隔离与降级边界，不拖垮可用源码证据。
# 阶段状态如实记录失败，回退结果不能声称语义分析完整。
def resolve(
    observed: ObservedProgramFacts,
    *,
    graph_builder: GraphBuilder = build_evidence_graph,
) -> ResolvedProgram:
    """Resolve identities and relations, degrading only the affected view."""
    corpus = observed.corpus
    graph = graph_builder(observed.extraction, root=corpus.paths.root)
    try:
        reconciliation = reconcile_graph(
            graph,
            observed.compiler.facts,
            corpus.paths.root,
            mode=observed.compiler.mode,
            copy_graph=False,
        )
        graph = reconciliation.graph
        reconcile_stage = {
            "status": str(ExecutionStatus.ANALYZED),
            "completeness": str(Completeness.COMPLETE),
            "bindings": len(reconciliation.bindings),
            "conflicts": len(reconciliation.conflicts),
        }
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        graph = graph_builder(observed.extraction, root=corpus.paths.root)
        reconciliation = reconcile_graph(
            graph,
            SemanticFacts(),
            corpus.paths.root,
            mode="off",
            copy_graph=False,
        )
        graph = reconciliation.graph
        reconcile_stage = {
            "status": str(ExecutionStatus.FAILED),
            "completeness": str(Completeness.UNAVAILABLE),
            "reasonCode": "machine.resolution.reconciliation-unavailable",
            "summary": safe_error_summary(exc),
            "bindings": 0,
            "conflicts": 0,
        }
    try:
        proposed = build_topology(
            corpus.paths,
            corpus.config,
            observed.compiler,
            reconcile=reconciliation,
        )
        topology, quarantine = quarantine_topology(
            proposed,
            graph,
            sources=corpus.snapshot.files,
            analysis_inputs=corpus.snapshot.analysis_inputs(),
        )
        topology_stage = {
            "status": str(ExecutionStatus.ANALYZED),
            "completeness": str(
                Completeness.COMPLETE
                if quarantine.get("status", "complete") == "complete"
                else Completeness.PARTIAL
            ),
            "retained": quarantine.get("retained", {}),
        }
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        summary = safe_error_summary(exc)
        topology = {
            "nodes": [],
            "edges": [],
            "diagnostics": [
                {"reasonCode": "machine.resolution.topology-unavailable", "summary": summary}
            ],
        }
        quarantine = {
            "status": "unavailable",
            "reasonCode": "machine.resolution.topology-unavailable",
        }
        topology_stage = {
            "status": str(ExecutionStatus.FAILED),
            "completeness": str(Completeness.UNAVAILABLE),
            "reasonCode": "machine.resolution.topology-unavailable",
            "summary": summary,
        }
    # 引用结果与源码证据绑定同一封存基线。
    # 后续查询能够据此拒绝跨分析版本混用的证据。
    baseline_digest = observed.sealed_corpus.baseline.digests.baseline_digest
    references = reconcile_reference_outcomes(
        observed.extraction,
        graph,
        baseline_digest=baseline_digest,
        root=corpus.paths.root,
    )
    source_evidence = observe_source_evidence(
        corpus.paths,
        graph,
        corpus.snapshot,
        observed.compiler,
        baseline_digest=baseline_digest,
        rule_observations=observed.rule_observations,
        materials=observed.materials,
    )
    # 构建归属由捕获的编译上下文推导，不重新探测磁盘。
    # 一个文件可能属于多个构建单元，因此保留完整归属集合。
    # 返回阶段摘要时叠加已有阶段，维持整条流水线的可追溯性。
    compiler_context = observed.compiler_snapshot.get("buildContext", {})
    build_units = compiler_context.get("units", []) if isinstance(compiler_context, dict) else []
    unit_assignments = build_unit_memberships(source_evidence.source_digests, build_units)
    stages = {
        "resolvedGraph": {
            **reconcile_stage,
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
        },
        "topology": topology_stage,
    }
    return ResolvedProgram(
        baseline_digest,
        corpus.paths.root,
        graph,
        reconciliation,
        topology,
        quarantine,
        references,
        source_evidence,
        unit_assignments,
        {
            "extraction": observed.extraction,
            "compiler": observed.compiler_snapshot,
            "authoringRuleDiagnostics": tuple(observed.authoring_rules.diagnostics),
        },
        {**observed.stage_summary, **stages},
    )


__all__ = ["ResolvedProgram", "resolve"]
