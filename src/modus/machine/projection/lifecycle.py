"""Project resolved evidence into bounded authoring views.

N5 owns aggregation and proposal-shaped views. Structural communities remain
an auxiliary signal; this stage never turns directory layout into authored
business truth and never publishes the raw resolved graph.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..capability.lifecycle import ComposedCapabilities
from ..errors import safe_error_summary, validate_code
from ..resolution.lifecycle import ResolvedProgram
from ..states import Completeness, ExecutionStatus
from .community_signal import GraphEngine
from .contracts import AuthoringProjection
from .memberships import EntryMembership, entry_memberships
from .proposals import build_proposals, capability_first_scope, capability_navigation
from .publication import sanitize_publication
from .scope_candidates import project_scope_candidates
from .views import project_diagnostics, project_services


# 投影产物共享同一基线，打包阶段不再读取解析图补数据。
# 作用域、服务、诊断和文件证据各有独立视图与用途。
@dataclass(frozen=True, slots=True)
class ProjectionProducts:
    """All bounded views ready for N6 packaging."""

    baseline_digest: str
    scope: dict[str, Any]
    services: dict[str, Any]
    diagnostics: dict[str, Any]
    evidence_index: dict[str, Any]
    evidence_packets: dict[str, dict[str, Any]]
    authoring_projection: AuthoringProjection
    stage_summary: dict[str, Any]


# 同一文件可支撑多个能力候选，归属保持列表而非单值覆盖。
# 候选索引与文件证据索引同步更新，保证两种查询方向一致。
# 成员关系附着到已有候选，保留能力与结构投影之间的可追溯连接。
def _attach_candidate_memberships(
    scope: dict[str, Any], evidence_index: dict[str, Any]
) -> dict[str, list[str]]:
    candidate_index: dict[str, list[str]] = {}
    memberships: dict[str, list[str]] = {}
    for raw in scope.get("candidates", []):
        if not isinstance(raw, Mapping):
            continue
        candidate_id = str(raw.get("candidateId") or "")
        files = [str(value) for value in raw.get("files", []) if value]
        if candidate_id:
            candidate_index[candidate_id] = files
            for relative in files:
                memberships.setdefault(relative, []).append(candidate_id)
    evidence_index["candidates"] = dict(sorted(candidate_index.items()))
    for row in evidence_index.get("files", []):
        if isinstance(row, dict):
            row["candidateIds"] = sorted(memberships.get(str(row.get("path") or ""), []))
    return memberships


def _reference_reason(value: object) -> str:
    """上游短原因不是无效存储记录；规范化后仍能解释未解析边界。"""
    reason = str(value or "unresolved")
    if len(reason) > 120:
        return "machine.resolution.reference-unresolved"
    try:
        return validate_code(
            reason
            if reason.startswith("machine.")
            else "machine.resolution." + f"reference-{reason}"
        )
    except ValueError:
        return "machine.resolution.reference-unresolved"


# 社区划分仅提供结构线索，失败后仍可使用能力与目录证据。
# 能力提议优先于结构候选，未覆盖声明保留为明确的剩余材料。
# 未解析引用与规则缺口回写文件证据，使局部查询也能看到降级。
# 所有公开视图统一脱敏，脱敏本身也必须成为覆盖缺口。
# 阶段摘要与内容视图分开，便于定位失败而不暴露原始图。
def project(
    resolved: ResolvedProgram,
    capabilities: ComposedCapabilities,
    *,
    community_engine: GraphEngine | None = None,
) -> ProjectionProducts:
    """Build bounded scope, service, evidence and diagnostic projections."""
    baseline_digest = resolved.baseline_digest
    engine = community_engine or GraphEngine()
    try:
        communities = engine.partition_scope(resolved.graph)
        scope_stage = {
            "status": str(ExecutionStatus.ANALYZED),
            "completeness": str(Completeness.COMPLETE),
            "groups": len(communities),
        }
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        communities = {}
        scope_stage = {
            "status": str(ExecutionStatus.FAILED),
            "completeness": str(Completeness.FALLBACK),
            "reasonCode": "machine.projection.community-unavailable",
            "summary": safe_error_summary(exc),
        }
    # N5 添加归属和预算说明，不能反写 N3 的冻结观察。
    evidence_index = {
        **resolved.source_evidence.index,
        "files": [
            dict(row)
            for row in resolved.source_evidence.index.get("files", [])
            if isinstance(row, Mapping)
        ],
    }
    evidence_packets = {
        key: {
            **packet,
            **{
                name: [dict(row) for row in packet.get(name, []) if isinstance(row, Mapping)]
                for name in ("entries", "relations", "authoringRecords", "coverageGaps")
            },
        }
        for key, packet in resolved.source_evidence.packets.items()
    }
    seed_inventory = {row["entryId"]: row for row in capabilities.model.seed_inventory}
    evidence_gaps = [dict(item) for item in resolved.source_evidence.coverage_gaps]
    evidence_gaps.extend(
        dict(item)
        for item in resolved.diagnostic_inputs.get("authoringRuleDiagnostics", ())
        if isinstance(item, Mapping)
    )
    authoring_records_by_path = {
        str(packet.get("path") or ""): [
            row for row in packet.get("authoringRecords", []) if isinstance(row, Mapping)
        ]
        for packet in evidence_packets.values()
    }
    scope = project_scope_candidates(
        resolved.repository_root,
        resolved.graph,
        communities=communities,
        source_digests=resolved.source_evidence.source_digests,
        source_roles=resolved.source_evidence.source_roles,
        baseline_digest=baseline_digest,
        build_unit_assignments=resolved.build_unit_assignments,
        projected_entries_by_path={
            str(packet.get("path") or ""): [
                row for row in packet.get("entries", []) if isinstance(row, Mapping)
            ]
            for packet in evidence_packets.values()
        },
        authoring_records_by_path=authoring_records_by_path,
        coverage_gaps_by_path={
            str(packet.get("path") or ""): [
                row for row in packet.get("coverageGaps", []) if isinstance(row, Mapping)
            ]
            for packet in evidence_packets.values()
        },
    )
    authoring_projection = build_proposals(
        capabilities.model,
        baseline_digest=baseline_digest,
    )
    scope = capability_first_scope(
        scope,
        capabilities.model,
        authoring_projection,
        authoring_records_by_path=authoring_records_by_path,
        source_roles=resolved.source_evidence.source_roles,
    )
    # 代表路径按能力所属提议投影，不发布全部原始调用边。
    # 这保持导航可解释且有界，避免大图直接进入创作上下文。
    proposal_by_capability = {
        capability_id: proposal.proposal_id
        for proposal in authoring_projection.proposals
        for capability_id in proposal.capability_ids
    }
    scope["navigationRecords"] = capability_navigation(
        capabilities.model,
        proposal_by_capability,
        resolved.source_evidence.source_digests,
    )
    memberships = _attach_candidate_memberships(scope, evidence_index)
    by_entry = entry_memberships(scope["candidates"], capabilities.model)
    # 文件库存保留文件级关联；细节使用声明/关系来源的精确身份。
    # 无归属记录保留文件相关提示，不能挂进某个提案的已绑定信号。
    for packet in evidence_packets.values():
        related = sorted(memberships.get(str(packet.get("path") or ""), []))
        for kind in ("entries", "relations", "authoringRecords"):
            for row in packet.get(kind, []):
                identity = str(row.get("source" if kind == "relations" else "entryId") or "")
                binding = by_entry.get(identity, EntryMembership())
                if kind == "entries" and identity in seed_inventory:
                    row["capabilitySeed"] = dict(seed_inventory[identity])
                row["candidateIds"] = list(binding.candidate_ids)
                row["capabilityIds"] = list(binding.capability_ids)
                if not binding.candidate_ids:
                    row["relatedCandidateIds"] = related

    services = project_services(
        resolved.topology,
        baseline_digest=baseline_digest,
        source_digests=resolved.source_evidence.source_digests,
    )
    # 服务节点通过锚点路径关联候选，不能仅凭服务名称匹配。
    # 节点可跨多个文件，因此合并全部已知候选归属。
    for row in services.get("nodes", []):
        if not isinstance(row, dict):
            continue
        anchors = row.get("sourceAnchors") or row.get("anchors") or []
        paths = {
            str(anchor.get("path") or anchor.get("file") or "")
            for anchor in anchors
            if isinstance(anchor, Mapping)
        }
        row["candidateIds"] = sorted(
            {candidate_id for relative in paths for candidate_id in memberships.get(relative, [])}
        )
    for row in services.get("edges", []):
        if not isinstance(row, dict):
            continue
        witness = row.get("witness") or {}
        relative = str(witness.get("path") or "") if isinstance(witness, Mapping) else ""
        row["candidateIds"] = sorted(memberships.get(relative, []))
    packets_by_path = {
        str(packet.get("path") or ""): packet for packet in evidence_packets.values()
    }
    # 引用未解析情况归到调用者文件，便于作者就地核验。
    # 没有对应文件包时不制造新的源码身份。
    for raw in resolved.reference_outcomes.get("refs", []):
        if not isinstance(raw, Mapping):
            continue
        target = packets_by_path.get(str(raw.get("callerFile") or ""))
        if target is None:
            continue
        target.setdefault("coverageGaps", []).append(
            {
                "reasonCode": _reference_reason(raw.get("reason")),
                "symbol": str(raw.get("name") or ""),
                "location": dict(raw.get("location") or {}),
                "resolution": "unresolved",
            }
        )
    for gap in evidence_gaps:
        target = packets_by_path.get(str(gap.get("path") or ""))
        if target is not None and gap not in target.setdefault("coverageGaps", []):
            target.setdefault("coverageGaps", []).append(dict(gap))
    stages = {
        **resolved.stage_summary,
        "capability": dict(capabilities.stage_summary),
        "projection": scope_stage,
    }
    diagnostics = project_diagnostics(
        baseline_digest=baseline_digest,
        stages=stages,
        extraction=resolved.diagnostic_inputs.get("extraction", {}),
        compiler=resolved.diagnostic_inputs.get("compiler", {}),
        reconcile=resolved.reconciliation.report(),
        unresolved=resolved.reference_outcomes,
        evidence_gaps=evidence_gaps,
    )
    # 每种投影视图独立处理后汇总脱敏计数。
    # 不能只清理正文而让同样的敏感值残留在索引或诊断中。
    redactions: Counter[str] = Counter()
    scope, counts = sanitize_publication(scope)
    redactions.update(counts)
    services, counts = sanitize_publication(services)
    redactions.update(counts)
    diagnostics, counts = sanitize_publication(diagnostics)
    redactions.update(counts)
    evidence_index, counts = sanitize_publication(evidence_index)
    redactions.update(counts)
    sanitized_packets: dict[str, dict[str, Any]] = {}
    for digest, packet in evidence_packets.items():
        sanitized, counts = sanitize_publication(packet)
        if counts:
            sanitized.setdefault("coverageGaps", []).append(
                {
                    "reasonCode": "machine.projection.sensitive-literal-redacted",
                    "count": sum(counts.values()),
                    "kinds": dict(sorted(counts.items())),
                    "resolution": "unresolved",
                }
            )
        redactions.update(counts)
        sanitized_packets[digest] = sanitized
    evidence_packets = sanitized_packets
    # 发生脱敏后整体诊断标记为部分完整。
    # 报告只包含种类与数量，不重新输出被移除的原值。
    # 诊断分组排序与总数同步更新，保持存储校验契约。
    if redactions:
        redaction_count = sum(redactions.values())
        scope.setdefault("coverage", {})["redactedSensitiveLiterals"] = redaction_count
        diagnostics["status"] = "partial"
        diagnostics.setdefault("groups", []).append(
            {
                "stage": "projection",
                "language": "mixed",
                "reasonCode": "machine.projection.sensitive-literal-redacted",
                "resolution": "unresolved",
                "count": redaction_count,
                "samples": [],
            }
        )
        diagnostics["groups"] = sorted(
            diagnostics["groups"],
            key=lambda row: (
                str(row.get("stage") or ""),
                str(row.get("language") or ""),
                str(row.get("reasonCode") or ""),
                str(row.get("resolution") or ""),
            ),
        )
        diagnostics["groupCount"] = len(diagnostics["groups"])
        diagnostics["totalCount"] = int(diagnostics.get("totalCount") or 0) + redaction_count
        projection_stage = diagnostics.setdefault("stages", {}).setdefault("projection", {})
        projection_stage["redactedSensitiveLiterals"] = redaction_count
    return ProjectionProducts(
        baseline_digest,
        scope,
        services,
        diagnostics,
        evidence_index,
        evidence_packets,
        authoring_projection,
        scope_stage,
    )


__all__ = ["ProjectionProducts", "project"]
