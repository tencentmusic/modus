"""N5 统一把声明身份映射到候选与能力；文件邻近性不产生声明归属。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..capability.contracts import CapabilityModel


@dataclass(frozen=True, slots=True)
class EntryMembership:
    candidate_ids: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()


def entry_memberships(
    candidates: Sequence[Mapping[str, Any]], model: CapabilityModel
) -> dict[str, EntryMembership]:
    """共享声明可支撑多个能力；只使用实际遍历和候选声明身份。"""
    candidates_by_entry: dict[str, set[str]] = defaultdict(set)
    capabilities_by_entry: dict[str, set[str]] = defaultdict(set)
    proposal_by_capability = {
        str(capability): str(candidate["candidateId"])
        for candidate in candidates
        for capability in candidate.get("capabilityIds", [])
    }
    for candidate in candidates:
        for entry in candidate.get("entries", []):
            identity = str(entry.get("entryId") or "")
            if identity:
                candidates_by_entry[identity].add(str(candidate["candidateId"]))
    for capability in model.slices:
        proposal = proposal_by_capability.get(capability.capability_id)
        if proposal is None:
            continue
        identities = {str(capability.entry.get("entryId") or "")}
        identities.update(step.entity_id for step in capability.observed_entries)
        # 兼容没有内部遍历见证的调用方；代表路径仅提供正向关联，不证明完整。
        identities.update(
            step.entity_id for path in capability.representative_paths for step in path.steps
        )
        for identity in identities - {""}:
            candidates_by_entry[identity].add(proposal)
            capabilities_by_entry[identity].add(capability.capability_id)
    return {
        identity: EntryMembership(
            tuple(sorted(owners)), tuple(sorted(capabilities_by_entry[identity]))
        )
        for identity, owners in candidates_by_entry.items()
    }
