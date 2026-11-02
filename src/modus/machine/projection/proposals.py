"""Capability-first authoring proposals and their bounded scope projection.

Capabilities are the unit of aggregation. Communities and directories enrich
the structural basis only; uncovered declarations remain an explicit, lower-
priority remainder rather than being silently absorbed into a giant candidate.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from ..capability.contracts import CapabilityModel, CapabilitySlice
from .contracts import AuthoringProjection, ProjectionIntent, Proposal, ProposalDisposition
from .scope_profiles import StructuralBasis, build_candidate_profile

_SPLIT_CAPABILITIES = 32
_SPLIT_ENTRIES = 128


# 提议身份绑定排序后的能力集合，输入枚举顺序不改变同一分组身份。
def _identity(kind: str, values: Sequence[str]) -> str:
    payload = "\0".join((kind, *sorted(values)))
    return kind + "-" + hashlib.sha256(payload.encode()).hexdigest()[:24]


# 入口、代表路径和终态效果共同决定支撑文件集合。
# 空路径过滤后排序，保留稳定且可追溯的成员列表。
def _capability_files(capability: CapabilitySlice) -> tuple[str, ...]:
    paths = {
        str((capability.entry.get("location") or {}).get("path") or ""),
        *(
            str(step.anchor.get("path") or step.anchor.get("file") or "")
            for path in capability.representative_paths
            for step in path.steps
        ),
        *(
            str(effect.anchor.get("path") or effect.anchor.get("file") or "")
            for effect in capability.terminal_effects
        ),
    }
    return tuple(sorted(path for path in paths if path))


# 仅共享权威对象的能力才合并，目录接近不构成业务聚合依据。
# 并查集选择稳定根，使等价连接顺序产生相同分组。
# 超大组标记 needs-split，不能当作已确认的巨大模块。
# 代表入口限量但扩展句柄保留完整能力集合。
# 公开触发入口优先，纯导出与结构声明维持较低阅读优先级。
def build_proposals(model: CapabilityModel, *, baseline_digest: str) -> AuthoringProjection:
    """Group capabilities only when they share an authoritative object."""
    groups = _group_authoritative_capabilities(model)
    proposals = []
    for capabilities in groups.values():
        capability_ids = tuple(sorted(item.capability_id for item in capabilities))
        entries = tuple(dict(item.entry) for item in capabilities)
        authorities = tuple(
            sorted({value for item in capabilities for value in item.authoritative_objects})
        )
        effects = tuple(
            effect.to_dict() for item in capabilities for effect in item.terminal_effects
        )
        disposition = (
            ProposalDisposition.NEEDS_SPLIT
            if len(capability_ids) > _SPLIT_CAPABILITIES or len(entries) > _SPLIT_ENTRIES
            else ProposalDisposition.PROPOSED
        )
        proposal_id = _identity("proposal", capability_ids)
        proposals.append(
            Proposal(
                proposal_id=proposal_id,
                kind="module-candidate",
                capability_ids=capability_ids,
                disposition=disposition,
                representative_entries=entries[:6],
                authoritative_objects=authorities,
                terminal_effects=effects,
                supporting_signals={
                    "entryKinds": dict(
                        sorted(
                            Counter(
                                str(item.trigger.get("kind") or "unknown") for item in capabilities
                            ).items()
                        )
                    ),
                    "files": sorted(
                        {path for item in capabilities for path in _capability_files(item)}
                    ),
                    "evidenceTiers": dict(
                        sorted(Counter(item.evidence_tier for item in capabilities).items())
                    ),
                    "degradationReasons": sorted(
                        {reason for item in capabilities for reason in item.degradation_reasons}
                    ),
                },
                omitted_counts={"representativeEntries": max(0, len(entries) - 6)},
                expansion_handles=tuple(
                    {"kind": "capability", "reference": identity} for identity in capability_ids
                ),
            )
        )
    # 入口种类优先级来自可观察的外部触发，不使用推测的业务重要性。
    # 行为证据和拆分状态作为次级排序，稳定 ID 负责最后消歧。
    explicit_entries = {"external-http", "external-rpc", "mq", "job", "cli"}

    def priority(proposal: Proposal) -> tuple[int, int, int, str]:
        entry_kinds = set(proposal.supporting_signals.get("entryKinds") or {})
        entry_rank = (
            0
            if entry_kinds.intersection(explicit_entries)
            else 1
            if "declared-entry" in entry_kinds
            else 2
        )
        behavior_rank = 0 if proposal.authoritative_objects or proposal.terminal_effects else 1
        split_rank = int(proposal.disposition is ProposalDisposition.NEEDS_SPLIT)
        return entry_rank, behavior_rank, split_rank, proposal.proposal_id

    return AuthoringProjection(
        ProjectionIntent.SCOPE,
        baseline_digest,
        tuple(sorted(proposals, key=priority)),
        receipts=model.receipts,
        omitted_counts={"uncoveredSeeds": len(model.uncovered_seeds)},
    )


def _group_authoritative_capabilities(model: CapabilityModel) -> dict[str, list[CapabilitySlice]]:
    """共享权威对象才建立连通分组，稳定身份决定合并方向。"""
    slices = {item.capability_id: item for item in model.slices}
    parent = {identity: identity for identity in slices}

    def find(identity: str) -> str:
        while parent[identity] != identity:
            parent[identity] = parent[parent[identity]]
            identity = parent[identity]
        return identity

    def union(left: str, right: str) -> None:
        first, second = find(left), find(right)
        if first != second:
            parent[max(first, second)] = min(first, second)

    by_object: defaultdict[str, list[str]] = defaultdict(list)
    for capability in model.slices:
        for authority in capability.authoritative_objects:
            by_object[authority].append(capability.capability_id)
    for identities in by_object.values():
        for identity in identities[1:]:
            union(identities[0], identity)
    groups: defaultdict[str, list[CapabilitySlice]] = defaultdict(list)
    for capability in model.slices:
        groups[find(capability.capability_id)].append(capability)
    return groups


# 从能力已有触发与效果构造统计信号，不重新识别源码规则。
def _signal_rows(capabilities: Sequence[CapabilitySlice]) -> list[dict[str, Any]]:
    rows = []
    for capability in capabilities:
        rows.append(
            {
                "kind": "entry",
                "evidenceKind": str(capability.trigger.get("kind") or "entry"),
            }
        )
        rows.extend(
            {"kind": "effect", "evidenceKind": str(effect.kind)}
            for effect in capability.terminal_effects
        )
        rows.extend(
            {"kind": "resource", "evidenceKind": "authoritative-object"}
            for _value in capability.authoritative_objects
        )
    return rows


# 转换保留全部能力入口，代表样本交由统一画像策略选择。
# 候选文件角色用于区分运行与支持材料。
# 完整度缺口来自能力收据，不能因候选已形成而清零。
def _candidate_from_proposal(
    proposal: Proposal,
    capabilities: Mapping[str, CapabilitySlice],
    source_roles: Mapping[str, str],
) -> dict[str, Any]:
    grouped = [capabilities[identity] for identity in proposal.capability_ids]
    entries_by_id: dict[str, dict[str, Any]] = {}
    for capability in grouped:
        entry = dict(capability.entry)
        entry["entryRole"] = "action"
        entry["entryCandidate"] = True
        identity = str(entry.get("entryId") or capability.capability_id)
        entries_by_id[identity] = entry
    entries = sorted(
        entries_by_id.values(),
        key=lambda entry: (
            str((entry.get("location") or {}).get("path") or ""),
            int((entry.get("location") or {}).get("startLine") or 0),
            str(entry.get("symbol") or ""),
        ),
    )
    files = sorted({path for capability in grouped for path in _capability_files(capability)})
    directories = tuple(sorted({str(PurePosixPath(path).parent) for path in files})[:16])
    roles = Counter(source_roles.get(path, "runtime") for path in files)
    profile = build_candidate_profile(
        structural_basis=StructuralBasis("directory", None, directories),
        entries=entries,
        runtime_file_count=roles["runtime"],
        support_file_count=sum(value for key, value in roles.items() if key != "runtime"),
        authoring_records=_signal_rows(grouped),
        unbound_signal_count=0,
    )
    gaps = sum(
        receipt.completeness != "complete"
        for capability in grouped
        for receipt in capability.receipts
    )
    return {
        "candidateId": proposal.proposal_id,
        "partition": "capability-model",
        "buildUnitId": "capability-model",
        **profile.to_dict(),
        "coverageGapCount": gaps,
        "files": files,
        "entries": entries,
        "capabilityIds": list(proposal.capability_ids),
        "disposition": str(proposal.disposition),
        "authoritativeObjects": list(proposal.authoritative_objects),
        "terminalEffects": [dict(row) for row in proposal.terminal_effects],
        "evidenceTiers": dict(proposal.supporting_signals.get("evidenceTiers") or {}),
        "degradationReasons": list(proposal.supporting_signals.get("degradationReasons") or []),
        "coverageReceipts": [
            receipt.to_dict() for capability in grouped for receipt in capability.receipts
        ],
        "omittedCounts": dict(proposal.omitted_counts),
    }


# 未被能力覆盖的声明仍需要作者阅读，明确保留为 remainder。
# 按完整目录路径分组并分块，防止结构社区重新形成巨型候选。
# 无法精确归属的旧聚合信号只保留一次，不能复制到每个分块。
# 分块身份包含条目集合，成员变化可以被后续比较识别。
# 尚不能形成能力提议的结构材料继续保留，避免分析缺口被分组过程隐藏。
def _remainder_candidates(
    raw: Mapping[str, Any],
    covered_entries: set[str],
    *,
    preserve_aggregate_signals: bool,
    source_roles: Mapping[str, str],
) -> list[dict[str, Any]]:
    entries = [
        dict(entry)
        for entry in raw.get("entries", [])
        if isinstance(entry, Mapping) and str(entry.get("entryId") or "") not in covered_entries
    ]
    if not entries:
        return []

    # A structural community can cover an entire monorepo area. Preserve it as
    # auxiliary evidence, but never re-create the old multi-thousand-entry
    # super-candidate. Directory-local chunks are deterministic investigation
    # units and remain explicitly marked when a directory needed chunking.
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        location = entry.get("location") or {}
        path = str(location.get("path") or entry.get("sourceFile") or "")
        grouped[str(PurePosixPath(path).parent) if path else "."].append(entry)

    results: list[dict[str, Any]] = []
    raw_identity = str(raw.get("candidateId") or "")
    for directory, directory_entries in sorted(grouped.items()):
        ordered = sorted(
            directory_entries,
            key=lambda entry: (
                str((entry.get("location") or {}).get("path") or ""),
                int((entry.get("location") or {}).get("startLine") or 0),
                str(entry.get("entryId") or ""),
            ),
        )
        chunks = [
            ordered[index : index + _SPLIT_ENTRIES]
            for index in range(0, len(ordered), _SPLIT_ENTRIES)
        ]
        for chunk_index, chunk in enumerate(chunks):
            files = sorted(
                {
                    str((entry.get("location") or {}).get("path") or "")
                    for entry in chunk
                    if str((entry.get("location") or {}).get("path") or "")
                }
            ) or [str(value) for value in raw.get("files", []) if value]
            roles = Counter(source_roles.get(path, "runtime") for path in files)
            profile = build_candidate_profile(
                structural_basis=StructuralBasis("directory", None, (directory,)),
                entries=chunk,
                runtime_file_count=roles["runtime"],
                support_file_count=sum(value for key, value in roles.items() if key != "runtime"),
                authoring_records=(),
                unbound_signal_count=0,
            )
            profile_fields = profile.to_dict()
            # The legacy candidate only exposes aggregate signal counts, so a
            # split cannot attribute them to an individual chunk. Retain the
            # aggregate exactly once instead of dropping or multiplying it.
            if (
                preserve_aggregate_signals
                and not results
                and isinstance(raw.get("capabilitySignals"), Mapping)
            ):
                profile_fields["capabilitySignals"] = dict(raw["capabilitySignals"])
            identity = _identity(
                "remainder",
                [
                    raw_identity,
                    directory,
                    str(chunk_index),
                    *(str(row.get("entryId") or "") for row in chunk),
                ],
            )
            results.append(
                {
                    "candidateId": identity,
                    "partition": str(raw.get("partition") or raw.get("buildUnitId") or "remainder"),
                    "buildUnitId": str(raw.get("buildUnitId") or "remainder"),
                    **profile_fields,
                    "coverageGapCount": int(raw.get("coverageGapCount") or 0),
                    "files": files,
                    "entries": chunk,
                    "capabilityIds": [],
                    "disposition": str(
                        ProposalDisposition.NEEDS_SPLIT
                        if len(chunks) > 1
                        else ProposalDisposition.REMAINDER
                    ),
                    "authoritativeObjects": [],
                    "terminalEffects": [],
                    "evidenceTiers": {},
                    "degradationReasons": [],
                    "coverageReceipts": [],
                    "omittedCounts": (
                        {"siblingRemainderChunks": len(chunks) - 1} if len(chunks) > 1 else {}
                    ),
                }
            )
    return results


# 使用已有符号和签名作为归属线索，不通过模糊子串猜测拥有者。
def _entry_owner_keys(entry: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        str(entry.get(name) or "")
        for name in ("symbol", "displayName", "declarationName", "signature")
        if entry.get(name)
    )


# 优先精确拥有者，只有文件唯一候选时才允许文件级回退。
# 歧义归属计入缺口，不能把同一规则复制为每个候选的已知事实。
# 新信号计数与已有摘要取较大值，避免重复输入造成双倍统计。
def _merge_authoring_records(
    candidates: list[dict[str, Any]],
    records_by_path: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    """Attach rule signals only to one evidenced owner; ambiguous rows stay gaps."""

    owners: defaultdict[tuple[str, str], set[int]] = defaultdict(set)
    candidates_by_file: defaultdict[str, set[int]] = defaultdict(set)
    for index, candidate in enumerate(candidates):
        for entry in candidate.get("entries", []):
            if not isinstance(entry, Mapping):
                continue
            location = entry.get("location") or {}
            path = str(location.get("path") or entry.get("sourceFile") or "")
            if not path:
                continue
            candidates_by_file[path].add(index)
            for owner in _entry_owner_keys(entry):
                owners[path, owner].add(index)

    assigned: defaultdict[int, dict[str, Counter[str]]] = defaultdict(
        lambda: {"entry": Counter(), "effect": Counter(), "resource": Counter()}
    )
    unbound: Counter[int] = Counter()
    for path, records in sorted(records_by_path.items()):
        file_candidates = candidates_by_file.get(path, set())
        for record in records:
            owner = str(record.get("symbol") or "")
            exact = owners.get((path, owner), set()) if owner else set()
            targets = exact if len(exact) == 1 else file_candidates if not exact else exact
            if len(targets) != 1:
                for index in targets:
                    unbound[index] += 1
                continue
            kind = str(record.get("kind") or "")
            evidence_kind = str(record.get("evidenceKind") or "")
            if kind in {"entry", "effect", "resource"} and evidence_kind:
                assigned[next(iter(targets))][kind][evidence_kind] += 1

    axis_names = {"entry": "entries", "effect": "effects", "resource": "resources"}
    for index, candidate in enumerate(candidates):
        signals = candidate.get("capabilitySignals")
        if not isinstance(signals, dict):
            continue
        for kind, counts in assigned[index].items():
            axis = signals.setdefault(axis_names[kind], {})
            for name, count in counts.items():
                axis[name] = max(int(axis.get(name) or 0), count)
        signals["unboundSignalCount"] = int(signals.get("unboundSignalCount") or 0) + unbound[index]


# 能力候选与剩余结构材料共存，覆盖不到的声明不会消失。
# 旧跨候选耦合不能沿用新的候选身份，因此清空后由能力导航提供关系。
# 原覆盖信息保留，同时补充能力种子、提议与剩余候选规模。
# 未覆盖种子或需要拆分的提议使整体状态保持 partial。
def capability_first_scope(
    legacy_scope: Mapping[str, Any],
    model: CapabilityModel,
    projection: AuthoringProjection,
    *,
    authoring_records_by_path: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    source_roles: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Replace structural primacy with capability proposals plus remainder."""
    capabilities = {item.capability_id: item for item in model.slices}
    roles = source_roles or {}
    primary = [
        _candidate_from_proposal(proposal, capabilities, roles) for proposal in projection.proposals
    ]
    legacy_candidates = [
        raw for raw in legacy_scope.get("candidates", []) if isinstance(raw, Mapping)
    ]
    # 只排除已经进入能力模型的入口，不能按文件整体排除剩余声明。
    # 同一文件可能同时支撑主要提议和待调查材料。
    covered_entries = {
        str(item.entry.get("entryId") or "") for item in model.slices if item.entry.get("entryId")
    }
    remainders = []
    for raw in legacy_candidates:
        remainders.extend(
            _remainder_candidates(
                raw,
                covered_entries,
                preserve_aggregate_signals=authoring_records_by_path is None,
                source_roles=roles,
            )
        )
    # 主要提议先交付，结构剩余保持较低优先级。
    # 有逐条规则记录时重新归属，避免沿用无法解释的旧聚合。
    candidates = [*primary, *remainders]
    if authoring_records_by_path is not None:
        _merge_authoring_records(candidates, authoring_records_by_path)
    result = dict(legacy_scope)
    result.update(
        candidates=candidates,
        crossCandidateCoupling=[],
        proposals=projection.to_dict(),
        capabilities=[item.to_dict() for item in model.slices],
        coverage={
            **dict(legacy_scope.get("coverage") or {}),
            "capabilities": len(model.slices),
            "capabilitySeeds": model.seed_count,
            "capabilityProposals": len(primary),
            "remainderCandidates": len(remainders),
            "entries": sum(len(item["entries"]) for item in candidates),
        },
        status="partial"
        if model.uncovered_seeds or any(item["disposition"] == "needs-split" for item in candidates)
        else "ready"
        if candidates
        else "empty",
    )
    return result


# 只投影代表路径，避免把完整图作为创作材料公开。
# 单步骤路径仍可表达终态效果或未解析终点。
# 每条导航带能力与候选身份，调用方可以按实际决策继续展开。
# 源码摘要按路径绑定，展示符号变化不改变引用文件版本。
# 导航只展示代表路径，完整关系由后续证据查询按需展开。
def capability_navigation(
    model: CapabilityModel,
    proposal_by_capability: Mapping[str, str],
    source_digests: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Project only representative paths, never every graph edge."""
    records = []
    for capability in model.slices:
        candidate_id = proposal_by_capability.get(capability.capability_id, "")
        if not candidate_id:
            continue
        for path_index, path in enumerate(capability.representative_paths):
            steps = path.steps
            pairs: list[tuple[Any, Any | None]] = list(zip(steps, steps[1:], strict=False))
            fallback_target = "unresolved-effect"
            if not pairs and steps:
                fallback_target = (
                    capability.terminal_effects[0].target
                    if capability.terminal_effects
                    else fallback_target
                )
                pairs = [(steps[0], None)]
            for edge_index, (source, target_step) in enumerate(pairs):
                relative = str(source.anchor.get("path") or source.anchor.get("file") or "")
                target_symbol = target_step.symbol if target_step is not None else fallback_target
                records.append(
                    {
                        "recordType": "navigationStep",
                        "candidateIds": [candidate_id],
                        "capabilityId": capability.capability_id,
                        "pathIndex": path_index,
                        "stepIndex": edge_index,
                        "sourceSymbol": source.symbol,
                        "targetSymbol": target_symbol,
                        "resolution": str(path.resolution),
                        "terminal": edge_index == len(pairs) - 1,
                        "path": relative,
                        "symbol": source.symbol,
                        "startLine": source.anchor.get("startLine") or source.anchor.get("line"),
                        "sourceDigest": source_digests.get(relative, ""),
                    }
                )
    return records


__all__ = [
    "build_proposals",
    "capability_first_scope",
    "capability_navigation",
]
