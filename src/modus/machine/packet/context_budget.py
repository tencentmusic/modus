"""N6 交付预算：完整路径作为裁剪单位，回执只描述实际交付。

查询保留证据身份与缺口；本模块只负责最终封套的条目、字节和遗漏计数。
展开查询属于固定封套，缺口最后裁剪，无法容纳封套时明确失败。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

from ..errors import BudgetError
from ..states import Completeness
from ..store.catalog import canonical_bytes
from .contracts import AuthoringContextPacket, PacketBudget

# 按交付优先级裁剪；外部计数使用 JSON 字段名，不泄漏 Python 属性名。
_TRIM_ORDER = {
    "ambiguities": "ambiguities",
    "representative_paths": "representativePaths",
    "terminal_effects": "terminalEffects",
    "authoritative_objects": "authoritativeObjects",
    "capabilities": "capabilities",
    "proposals": "proposals",
    "evidence": "evidence",
    "source_anchors": "sourceAnchors",
    "expansion_handles": "expansionHandles",
    "coverage_gaps": "coverageGaps",
}


def fit_context_budget(
    packet: AuthoringContextPacket,
    budget: PacketBudget,
) -> AuthoringContextPacket:
    """以最终交付重新计数；导航路径整体裁剪，缺口最后裁剪且保留原因。"""
    omitted = Counter(packet.omitted_counts)
    values: dict[str, list[Any]] = {name: list(getattr(packet, name)) for name in _TRIM_ORDER}
    values["proposals"] = [
        {**row, "authoringSignals": list(row["authoringSignals"])}
        if "authoringSignals" in row
        else dict(row)
        for row in packet.proposals
    ]

    def snapshot() -> AuthoringContextPacket:
        result = replace(
            packet,
            proposals=tuple(values["proposals"]),
            capabilities=tuple(values["capabilities"]),
            representative_paths=tuple(values["representative_paths"]),
            terminal_effects=tuple(values["terminal_effects"]),
            authoritative_objects=tuple(values["authoritative_objects"]),
            ambiguities=tuple(values["ambiguities"]),
            evidence=tuple(values["evidence"]),
            source_anchors=tuple(values["source_anchors"]),
            expansion_handles=tuple(values["expansion_handles"]),
            coverage_gaps=tuple(values["coverage_gaps"]),
            omitted_counts=dict(sorted(omitted.items())),
        )
        original = packet.coverage_receipts[0]
        counts = {
            "proposals": len(result.proposals),
            "capabilities": len(result.capabilities),
            "representativePaths": len(
                {
                    (row.get("capabilityId"), row.get("pathIndex"))
                    for row in result.representative_paths
                }
            ),
            "navigationSteps": len(result.representative_paths),
            "authoringSignals": sum(
                len(row.get("authoringSignals") or []) for row in result.proposals
            )
            + sum(
                row.get("marker") == "unbound-authoring-signal"
                and isinstance(row.get("signal"), dict)
                for row in result.ambiguities
            )
            + sum(
                row.get("recordType") == "authoringSignal"
                for row in (
                    *result.proposals,
                    *result.authoritative_objects,
                    *result.terminal_effects,
                )
            ),
            "evidence": len(result.evidence),
            "coverageGaps": len(result.coverage_gaps),
        }
        reason = original.reason_code
        if omitted and reason != "machine.packet.coverage-gaps":
            reason = "machine.packet.budget-exhausted"
        receipt = replace(
            original,
            counts=counts,
            reason_code=reason,
            completeness=Completeness.PARTIAL if omitted else original.completeness,
        )
        return replace(result, coverage_receipts=(receipt,))

    def item_count() -> int:
        return sum(
            len(values[name])
            for name in _TRIM_ORDER
            if name not in {"source_anchors", "expansion_handles", "coverage_gaps"}
        ) + sum(len(row.get("authoringSignals") or []) for row in values["proposals"])

    result = snapshot()
    while (
        len(canonical_bytes(result.to_dict())) > budget.max_bytes or item_count() > budget.max_items
    ):
        for row in reversed(values["proposals"]):
            if row.get("authoringSignals"):
                row["authoringSignals"].pop()
                omitted["authoringSignals"] += 1
                break
        else:
            for name, count_key in _TRIM_ORDER.items():
                if not values[name]:
                    continue
                row = values[name].pop()
                if name == "representative_paths":
                    key = (row.get("capabilityId"), row.get("pathIndex"))
                    kept = [
                        other
                        for other in values[name]
                        if (other.get("capabilityId"), other.get("pathIndex")) != key
                    ]
                    omitted["navigationSteps"] += 1 + len(values[name]) - len(kept)
                    values[name] = kept
                omitted[count_key] += 1
                break
            else:
                raise BudgetError("machine.packet.fixed-envelope-exceeds-budget")
        result = snapshot()
    return result
