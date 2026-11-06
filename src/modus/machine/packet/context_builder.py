"""按创作意图组织已认证证据，交给预算边界统一裁剪。

先选摘要，再读取当前范围的规则信号和完整代表路径。每次查询同时保留
来源、缺口与可重放过滤条件，不自动穷尽分页，也不暴露底层图。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

from ..receipts import CoverageReceipt
from ..states import Completeness, ExecutionStatus
from ..store.contracts import (
    AnalysisBundle,
    EvidenceBudget,
    EvidencePage,
    EvidenceQuery,
    EvidenceRecord,
    SelectionView,
)
from .context_budget import fit_context_budget
from .contracts import (
    AuthoringContextPacket,
    ContextRequest,
    ExpansionHandle,
    HandleKind,
    PacketBudget,
    PacketScope,
    TaskIntent,
)
from .query import query_evidence


# 切换意图只改变视图和记录类别，不能扩大调用方范围。
def _intent_request(
    intent: TaskIntent,
    scope: PacketScope,
    budget: PacketBudget,
) -> EvidenceQuery:
    if intent is TaskIntent.SERVICE_BOUNDARY:
        view: SelectionView = "services"
        record_types: tuple[str, ...] = ("serviceBoundary", "servicesSummary", "serviceRelation")
    elif intent is TaskIntent.CONSTRAINT_EXTRACTION:
        view = "evidence"
        record_types = ("authoringSignal",)
    elif intent is TaskIntent.COVERAGE_AUDIT:
        view = "evidence"
        record_types = ()
    else:
        view = "scope"
        record_types = ("scopeSummary", "candidateSummary")
    return EvidenceQuery(
        view=view,
        candidate_ids=scope.candidate_ids,
        capability_ids=scope.capability_ids,
        boundary_ids=scope.boundary_ids,
        paths=scope.paths,
        symbols=scope.symbols,
        record_types=record_types,
        budget=EvidenceBudget(
            max_items=budget.max_items,
            max_bytes=budget.max_bytes,
        ),
    )


# 候选携带库存和降级依据；规则信号稍后挂到所属候选。
def _candidate_row(details: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposalId": str(details.get("candidateId") or ""),
        "disposition": str(details.get("disposition") or "remainder"),
        "partition": str(details.get("partition") or ""),
        "capabilityIds": list(details.get("capabilityIds") or []),
        "structuralBasis": dict(details.get("structuralBasis") or {}),
        "inventory": dict(details.get("inventory") or {}),
        "capabilitySignals": dict(details.get("capabilitySignals") or {}),
        "representativeEntries": list(details.get("representativeEntries") or []),
        "authoritativeObjects": list(details.get("authoritativeObjects") or []),
        "terminalEffects": list(details.get("terminalEffects") or []),
        "evidenceTiers": dict(details.get("evidenceTiers") or {}),
        "degradationReasons": list(details.get("degradationReasons") or []),
        "coverageReceipts": list(details.get("coverageReceipts") or []),
        "coverageGapCount": int(details.get("coverageGapCount") or 0),
        "omittedCounts": dict(details.get("omittedCounts") or {}),
        "authoringSignals": [],
    }


def _flat_record(record: EvidenceRecord) -> dict[str, Any]:
    """摘要保留既有细节位置，同时携带原记录的身份、精度和源码见证。"""
    payload = record.to_dict()
    return {
        **record.details,
        **{
            key: payload[key]
            for key in ("recordId", "kind", "candidateIds", "resolution", "sourceLayer", "witness")
        },
    }


@dataclass(slots=True)
class _ContextBuilder:
    """单次请求的组装状态；查询账本与最终交付共享同一范围和遗漏口径。"""

    bundle: AnalysisBundle
    request: ContextRequest
    proposals: list[dict[str, Any]] = field(default_factory=list)
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    paths: list[dict[str, Any]] = field(default_factory=list)
    authorities: list[dict[str, Any]] = field(default_factory=list)
    effects: list[dict[str, Any]] = field(default_factory=list)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    anchors: list[dict[str, Any]] = field(default_factory=list)
    handles: list[ExpansionHandle] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    queries: list[dict[str, Any]] = field(default_factory=list)
    omitted: Counter[str] = field(default_factory=Counter)
    low_resolution_count: int = 0

    def select(self, query: EvidenceQuery, page_kind: str) -> EvidencePage:
        # 记录初始过滤条件；续页由公开 select 返回的 cursor 驱动。
        descriptor = {
            "view": query.view,
            "candidateIds": list(query.candidate_ids),
            "capabilityIds": list(query.capability_ids),
            "boundaryIds": list(query.boundary_ids),
            "paths": list(query.paths),
            "symbols": list(query.symbols),
            "recordTypes": list(query.record_types),
            "evidenceKinds": list(query.evidence_kinds),
        }
        if descriptor not in self.queries:
            self.queries.append(descriptor)
        page = query_evidence(self.bundle, query)
        for gap in page.coverage_gaps:
            payload = gap.to_dict()
            if payload not in self.gaps:
                self.gaps.append(payload)
        if page.next_cursor:
            self.omitted[page_kind] += 1
        return page

    def add_handle(self, kind: HandleKind, reference: str, hint: str) -> None:
        if reference and not any(
            handle.kind == kind and handle.reference == reference for handle in self.handles
        ):
            self.handles.append(ExpansionHandle(kind, reference, hint))

    def add_anchor(self, witness: dict[str, Any]) -> None:
        path = str(witness.get("path") or "")
        if not path:
            return
        if witness not in self.anchors:
            self.anchors.append(witness)
        self.add_handle(HandleKind.PATH, path, "回读当前源码并核对结论。")
        if witness.get("symbol"):
            self.add_handle(HandleKind.SYMBOL, str(witness["symbol"]), "按符号核对具体行为。")

    def add_candidate(self, details: dict[str, Any]) -> None:
        row = _candidate_row(details)
        candidate_id = row["proposalId"]
        is_low = (
            row["disposition"] != "proposed"
            or bool(row["coverageGapCount"])
            or any(receipt.get("completeness") != "complete" for receipt in row["coverageReceipts"])
        )
        # 被配额排除的候选仍有展开入口，低精度不能伪装成明确提议。
        self.add_handle(HandleKind.CANDIDATE, candidate_id, "按候选展开未交付或低精度证据。")
        if is_low and self.low_resolution_count >= self.request.budget.low_resolution_quota:
            self.omitted["lowResolutionProposals"] += 1
            return
        self.low_resolution_count += int(is_low)
        self.proposals.append(row)
        for capability_id in row["capabilityIds"]:
            self.capabilities.append(
                {
                    "capabilityId": capability_id,
                    "proposalId": candidate_id,
                    "evidenceTiers": dict(row["evidenceTiers"]),
                    "degradationReasons": list(row["degradationReasons"]),
                }
            )
            self.add_handle(HandleKind.CAPABILITY, capability_id, "展开能力的代表路径。")
        self.authorities.extend(
            {"proposalId": candidate_id, "identity": value} for value in row["authoritativeObjects"]
        )
        self.effects.extend(
            {"proposalId": candidate_id, **dict(value)}
            for value in row["terminalEffects"]
            if isinstance(value, dict)
        )
        for entry in row["representativeEntries"]:
            if isinstance(entry, dict):
                self.add_anchor(
                    {
                        key: entry.get(key)
                        for key in ("path", "startLine", "endLine", "sourceDigest", "symbol")
                    }
                )
        if is_low:
            self.ambiguities.append(
                {
                    "proposalId": candidate_id,
                    "marker": "low-confidence-or-incomplete",
                    "disposition": row["disposition"],
                    "coverageGapCount": row["coverageGapCount"],
                }
            )

    def add_record(self, record: EvidenceRecord) -> None:
        record_type = record.details.get("recordType")
        if record_type == "candidateSummary":
            self.add_candidate(dict(record.details))
        elif record_type in {"serviceBoundary", "servicesSummary"}:
            self.proposals.append(_flat_record(record))
            self.add_handle(
                HandleKind.BOUNDARY,
                str(record.details.get("boundaryId") or ""),
                "用 service-boundary 或 select --view services 双向核对边界。",
            )
        elif record_type == "authoringSignal":
            row = _flat_record(record)
            target = (
                self.effects
                if row["kind"] == "effect"
                else self.authorities
                if row["kind"] == "resource"
                else self.proposals
            )
            target.append(row)
        else:
            # 库存、入口、关系和导航摘要保持原记录形状，便于按身份回查。
            self.evidence.append(dict(record.to_dict()))
        if record.witness is not None:
            self.add_anchor(record.witness.to_dict())

    def add_module_signals(self, query: EvidenceQuery) -> None:
        signals = self.select(
            replace(query, view="evidence", record_types=("authoringSignal",)),
            "authoringSignalPages",
        )
        proposals = {row["proposalId"]: row for row in self.proposals if row.get("proposalId")}
        for record in signals.items:
            row = dict(record.to_dict())
            matched = False
            for candidate_id in record.candidate_ids:
                if candidate_id in proposals:
                    proposals[candidate_id]["authoringSignals"].append(row)
                    matched = True
            if record.witness is not None:
                self.add_anchor(record.witness.to_dict())
            # 未归属信号不能丢弃，也不能挂到相邻候选上。
            if not matched:
                self.ambiguities.append(
                    {
                        "marker": "unbound-authoring-signal",
                        "candidateIds": list(record.candidate_ids),
                        "signal": row,
                    }
                )
        if not signals.items and (query.paths or query.symbols):
            declarations = self.select(
                replace(query, view="evidence", record_types=("sourceEntry", "sourceFile")),
                "declarationPages",
            )
            for record in declarations.items:
                self.add_record(record)

    def add_paths(self, query: EvidenceQuery) -> None:
        candidate_ids = tuple(row["proposalId"] for row in self.proposals if row.get("proposalId"))
        if not candidate_ids:
            return
        # 路径解释已选候选的完整链路；原始源码选择器仍保留在 requestedScope。
        page = self.select(
            replace(
                query,
                candidate_ids=candidate_ids,
                paths=(),
                symbols=(),
                record_types=("navigationStep",),
            ),
            "pathSelectionPages",
        )
        groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for record in page.items:
            row = _flat_record(record)
            groups[(str(row.get("capabilityId") or ""), int(row.get("pathIndex") or 0))].append(row)
        per_capability: Counter[str] = Counter()
        for (capability_id, _), rows in sorted(groups.items()):
            rows.sort(key=lambda row: int(row.get("stepIndex", -1)))
            # 页可能在任一步截断；必须从首步连续抵达终点才交付整条路径。
            # 旧记录没有步骤序号时同样无法证明连续性，保留展开入口。
            complete = [row.get("stepIndex") for row in rows] == list(range(len(rows))) and rows[
                -1
            ]["terminal"]
            if (
                not complete
                or per_capability[capability_id] >= self.request.budget.max_paths_per_capability
            ):
                self.omitted["representativePaths"] += 1
                continue
            per_capability[capability_id] += 1
            self.paths.extend(rows)
            for row in rows:
                self.add_anchor(row["witness"])

    def build(self) -> AuthoringContextPacket:
        query = _intent_request(self.request.intent, self.request.scope, self.request.budget)
        if self.request.intent is TaskIntent.COVERAGE_AUDIT:
            inventory = self.select(replace(query, record_types=("sourceFile",)), "inventoryPages")
            for record in inventory.items:
                self.add_record(record)
            query = replace(
                query, record_types=("sourceEntry", "sourceRelation", "authoringSignal")
            )
        selection = self.select(query, "selectionPages")
        for record in selection.items:
            self.add_record(record)
        if self.request.intent is TaskIntent.MODULE_AUTHORING:
            self.add_module_signals(query)
        if query.view == "scope":
            self.add_paths(query)
            # 已知候选总量与查询页截断分别记录，页数不冒充记录数量。
            for record in selection.items:
                if record.details.get("recordType") == "scopeSummary":
                    candidate_count = record.details.get("candidateCount")
                    if not isinstance(candidate_count, int):
                        continue
                    missing = candidate_count - len(self.proposals)
                    if missing > 0:
                        self.omitted["proposals"] += missing

        if self.gaps:
            reason = "machine.packet.coverage-gaps"
        elif self.omitted:
            reason = "machine.packet.budget-exhausted"
        elif self.ambiguities:
            reason = "machine.packet.low-confidence-evidence"
        elif not any(
            (
                self.proposals,
                self.capabilities,
                self.paths,
                self.authorities,
                self.effects,
                self.evidence,
            )
        ):
            reason = "machine.packet.no-matching-evidence"
        else:
            reason = ""
        completeness = (
            Completeness.UNAVAILABLE
            if reason == "machine.packet.no-matching-evidence"
            else Completeness.PARTIAL
            if reason
            else Completeness.COMPLETE
        )
        receipt = CoverageReceipt(
            "context-builder",
            "intent",
            str(self.request.intent),
            ExecutionStatus.ANALYZED,
            completeness,
            reason,
        )
        packet = AuthoringContextPacket(
            intent=self.request.intent,
            bundle_digest=self.bundle.bundle_digest,
            baseline_digest=self.bundle.baseline_digest,
            requested_scope=self.request.scope,
            proposals=tuple(self.proposals),
            capabilities=tuple(self.capabilities),
            representative_paths=tuple(self.paths),
            authoritative_objects=tuple(self.authorities),
            terminal_effects=tuple(self.effects),
            ambiguities=tuple(self.ambiguities),
            coverage_receipts=(receipt,),
            source_anchors=tuple(self.anchors),
            expansion_handles=tuple(self.handles),
            omitted_counts=dict(self.omitted),
            evidence=tuple(self.evidence),
            coverage_gaps=tuple(self.gaps),
            expansion_queries=tuple(self.queries),
        )
        # 计数唯一归属预算边界：子查询各自合规，不代表最终封套合规。
        return fit_context_budget(packet, self.request.budget)


def package_context(bundle: AnalysisBundle, request: ContextRequest) -> AuthoringContextPacket:
    """组装一个意图的首屏；分页是补证入口，不是创作完成条件。"""
    return _ContextBuilder(bundle, request).build()


__all__ = ["package_context"]
