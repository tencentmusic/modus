"""Traverse normalized evidence under hard capability budgets."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from typing import Any

from ..languages import CapabilityTier
from ..receipts import CoverageReceipt
from ..resolution.contracts import TraversalBudget
from ..states import (
    Completeness,
    ExecutionStatus,
    Resolution,
    completeness_floor,
    resolution_floor,
)
from .composition_model import RESOLUTION_ORDER as _RESOLUTION_ORDER
from .composition_model import Edge as _Edge
from .composition_model import Seed as _Seed
from .contracts import (
    CapabilitySlice,
    PathStatus,
    PathStep,
    RepresentativePath,
    TerminalEffect,
    capability_identity,
)


# 路径步骤只引用已有入口及位置，缺失标签回退到稳定身份。
# 展示名称的变化不会影响图中的连接关系。
def _step(entry_id: str, entries: Mapping[str, Mapping[str, Any]]) -> PathStep:
    entry = entries.get(entry_id, {})
    return PathStep(
        entry_id,
        str(entry.get("symbol") or entry.get("displayName") or entry_id),
        dict(entry.get("location") or {}),
    )


# 从单个已确认种子出发，在节点、边、深度和路径预算内遍历。
# 路径置信度取沿途证据的下界，弱边不能因连接强入口而升级。
# 终止、未解析、循环与预算截断分别计数，避免把停止都当作成功。
def compose_seed(
    seed: _Seed,
    entries: Mapping[str, Mapping[str, Any]],
    adjacency: Mapping[str, tuple[_Edge, ...]],
    effects: Mapping[str, tuple[TerminalEffect, ...]],
    resources: Mapping[str, tuple[str, ...]],
    transitions: Mapping[str, tuple[dict[str, Any], ...]],
    budget: TraversalBudget,
) -> CapabilitySlice:
    pending: deque[tuple[str, tuple[str, ...], Resolution]] = deque(
        [(seed.entry_id, (seed.entry_id,), seed.resolution)]
    )
    path_candidates: list[tuple[RepresentativePath, TerminalEffect | None]] = []
    status_counts: Counter[str] = Counter()
    terminal_effects: list[TerminalEffect] = []
    visited_nodes: set[str] = set()
    edge_count = 0
    omitted: Counter[str] = Counter()
    while pending and len(path_candidates) < budget.max_paths:
        current, identities, path_resolution = pending.popleft()
        visited_nodes.add(current)
        current_effects = effects.get(current, ())
        # 副作用节点构成当前路径的终点，不继续穿透至更远的调用。
        # 同一节点可具有多个效果，均保留用于能力摘要。
        if current_effects:
            for effect in current_effects:
                resolution = resolution_floor(path_resolution, effect.resolution)
                candidate = RepresentativePath(
                    tuple(_step(identity, entries) for identity in identities),
                    PathStatus.TERMINATED,
                    resolution,
                )
                path_candidates.append((candidate, effect))
                terminal_effects.append(effect)
                status_counts[str(PathStatus.TERMINATED)] += 1
            continue
        outgoing = adjacency.get(current, ())
        # 预算到达时保留已走过的路径及截断状态。
        # 遗漏计数表达尚未展开的分支，不能解释成不存在其他行为。
        if len(identities) >= budget.max_depth or len(visited_nodes) >= budget.max_nodes:
            path_candidates.append(
                (
                    RepresentativePath(
                        tuple(_step(identity, entries) for identity in identities),
                        PathStatus.TRUNCATED,
                        path_resolution,
                    ),
                    None,
                )
            )
            status_counts[str(PathStatus.TRUNCATED)] += 1
            omitted["budgetBranches"] += max(1, len(outgoing))
            continue
        # 没有可遍历边也没有终态效果时，记录为未解析终点。
        # 这是证据边界，不是证明该函数没有副作用。
        if not outgoing:
            path_candidates.append(
                (
                    RepresentativePath(
                        tuple(_step(identity, entries) for identity in identities),
                        PathStatus.UNRESOLVED,
                        path_resolution,
                    ),
                    None,
                )
            )
            status_counts[str(PathStatus.UNRESOLVED)] += 1
            continue
        for edge in outgoing:
            edge_count += 1
            if edge_count > budget.max_edges:
                omitted["budgetEdges"] += 1
                status_counts[str(PathStatus.TRUNCATED)] += 1
                continue
            next_resolution = resolution_floor(path_resolution, edge.resolution)
            # 循环检测以当前路径为单位，不禁止其他分支再次到达相同节点。
            # 循环闭合节点保留在路径中，读者可以看到回边。
            if edge.target in identities:
                path_candidates.append(
                    (
                        RepresentativePath(
                            tuple(
                                _step(identity, entries) for identity in (*identities, edge.target)
                            ),
                            PathStatus.CYCLE,
                            next_resolution,
                        ),
                        None,
                    )
                )
                status_counts[str(PathStatus.CYCLE)] += 1
                continue
            pending.append((edge.target, (*identities, edge.target), next_resolution))
    # 路径预算用尽后队列中的工作计入遗漏。
    # 这些未展开分支也会降低完整度，不能被代表路径筛选隐藏。
    if pending:
        omitted["budgetPaths"] += len(pending)
        status_counts[str(PathStatus.TRUNCATED)] += len(pending)
    # 优先选择达到终态的路径，再比较置信度、长度与稳定身份。
    # 排序与进程调度无关，相同输入可生成相同的解释顺序。
    path_candidates.sort(
        key=lambda item: (
            item[0].status is not PathStatus.TERMINATED,
            _RESOLUTION_ORDER[item[0].resolution],
            len(item[0].steps),
            tuple(step.entity_id for step in item[0].steps),
        )
    )
    # 代表路径最多三条，先覆盖不同的效果种类与目标。
    # 不足时再补充其他路径，避免多个同效路径挤占解释空间。
    representatives: list[RepresentativePath] = []
    represented_effects: set[tuple[str, str]] = set()
    for representative, represented_effect in path_candidates:
        effect_key = (
            (str(represented_effect.kind), represented_effect.target)
            if represented_effect
            else ("", "")
        )
        if represented_effect is not None and effect_key in represented_effects:
            continue
        representatives.append(representative)
        represented_effects.add(effect_key)
        if len(representatives) >= 3:
            break
    if len(representatives) < 3:
        for representative, _effect in path_candidates:
            if representative not in representatives:
                representatives.append(representative)
            if len(representatives) >= 3:
                break
    # 效果按种类、目标和锚点去重，保留不同源码位置的同类写入。
    # 总体置信度还需考虑效果本身，而非只看路径边。
    effect_by_key = {
        (str(effect.kind), effect.target, repr(sorted(effect.anchor.items()))): effect
        for effect in terminal_effects
    }
    unique_effects = tuple(effect_by_key[key] for key in sorted(effect_by_key))
    all_resolutions = [path.resolution for path in representatives]
    all_resolutions.extend(effect.resolution for effect in unique_effects)
    slice_resolution = (
        resolution_floor(*all_resolutions) if all_resolutions else Resolution.UNRESOLVED
    )
    authoritative = sorted(
        {
            value
            for identity in {step.entity_id for path in representatives for step in path.steps}
            for value in resources.get(identity, ())
        }
    )
    state_transitions = tuple(
        row
        for identity in {step.entity_id for path in representatives for step in path.steps}
        for row in transitions.get(identity, ())
    )
    # 找到终态效果也不必然完整：预算遗漏必须显式降低完整度。
    # 再与入口证据层级取下界，通用解析不能产出语义级完整声明。
    traversal_completeness = (
        Completeness.COMPLETE
        if unique_effects and not omitted and not status_counts[str(PathStatus.TRUNCATED)]
        else Completeness.PARTIAL
        if path_candidates
        else Completeness.UNAVAILABLE
    )
    entry = dict(entries.get(seed.entry_id, {}))
    evidence_tier = str(entry.get("evidenceTier") or CapabilityTier.GENERIC)
    tier_completeness = {
        str(CapabilityTier.SEMANTIC): Completeness.COMPLETE,
        str(CapabilityTier.STRUCTURAL): Completeness.PARTIAL,
        str(CapabilityTier.GENERIC): Completeness.FALLBACK,
    }.get(evidence_tier, Completeness.FALLBACK)
    completeness = completeness_floor(traversal_completeness, tier_completeness)
    degradation_reason = str(entry.get("degradationReason") or "")
    reason = (
        ""
        if completeness is Completeness.COMPLETE
        else "machine.capability.traversal-truncated"
        if omitted or status_counts[str(PathStatus.TRUNCATED)]
        else degradation_reason
        if degradation_reason
        else "machine.capability.terminal-effect-unresolved"
    )
    # 收据保存遍历计数与降级原因，便于下游解释能力缺口。
    # 能力身份依赖触发签名、权威对象与效果，展示路径不参与身份。
    receipt = CoverageReceipt(
        "capability-composer",
        "entry",
        seed.entry_id,
        ExecutionStatus.ANALYZED,
        completeness,
        reason,
        {
            "visitedNodes": len(visited_nodes),
            "visitedEdges": min(edge_count, budget.max_edges),
            "terminalEffects": len(unique_effects),
        },
    )
    capability_id = capability_identity(
        seed.signature,
        tuple(authoritative),
        tuple(f"{effect.kind}:{effect.target}" for effect in unique_effects),
    )
    # 入口和终态之间的中间步骤构成编排者列表。
    # 顺序去重保留代表路径中的阅读次序，不添加未遍历的符号。
    orchestrators = tuple(
        dict.fromkeys(
            step.symbol for path in representatives for step in path.steps[1:-1] if step.symbol
        )
    )
    return CapabilitySlice(
        capability_id=capability_id,
        entry_signature=seed.signature,
        trigger=seed.trigger,
        entry=entry,
        observed_entries=tuple(_step(identity, entries) for identity in sorted(visited_nodes)),
        evidence_tier=evidence_tier,
        degradation_reasons=(degradation_reason,) if degradation_reason else (),
        orchestrators=orchestrators,
        authoritative_objects=tuple(authoritative),
        state_transitions=state_transitions,
        terminal_effects=unique_effects,
        representative_paths=tuple(representatives),
        path_status_counts=dict(sorted(status_counts.items())),
        omitted_counts=dict(sorted(omitted.items())),
        resolution=slice_resolution,
        receipts=(receipt,),
        expansion_handles=(
            {"kind": "symbol", "reference": str(entry.get("symbol") or seed.entry_id)},
        ),
    )


__all__ = ["compose_seed"]
