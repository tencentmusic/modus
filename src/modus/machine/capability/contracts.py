"""N4 output contract: what can the system do, from trigger to effect?

A :class:`CapabilitySlice` is behaviour evidence -- one public entry walked
forward over resolved relations until it reaches terminal effects -- not a
business conclusion. Actor names and business labels stay empty or
``proposed`` unless directly evidenced; directories never define a
capability.

Identity is a content recipe, not an ordinal: :func:`capability_identity`
hashes the entry signature, authoritative objects and effect signature, so a
capability keeps its id across line drift and in-file moves. Reinit diffing
depends on this recipe.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..receipts import CoverageReceipt
from ..states import Resolution, resolution_floor


class EffectKind(StrEnum):
    """Curated terminal effects: calls that change something outside the walk.

    The categories are the reader's, not a library's: a database write, a
    state transition, a published event, an outbound RPC, a file write, a
    cache mutation. "Any call into a package" is deliberately not an effect.
    """

    DATA_WRITE = "data-write"
    STATE_TRANSITION = "state-transition"
    EVENT_PUBLISH = "event-publish"
    EXTERNAL_CALL = "external-call"
    FILE_WRITE = "file-write"
    CACHE_WRITE = "cache-write"


class PathStatus(StrEnum):
    """Why one walked branch stopped."""

    TERMINATED = "terminated"
    TRUNCATED = "truncated"
    UNRESOLVED = "unresolved"
    CYCLE = "cycle"
    BOUNDARY = "boundary"


@dataclass(frozen=True, slots=True)
class TerminalEffect:
    """One evidenced effect at the end of a walk; never inferred from names."""

    kind: EffectKind
    target: str
    anchor: dict[str, Any] = field(default_factory=dict)
    resolution: Resolution = Resolution.EXACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "target": self.target,
            "anchor": dict(self.anchor),
            "resolution": str(self.resolution),
        }


@dataclass(frozen=True, slots=True)
class PathStep:
    """One hop of a representative path, bound to a resolved entity."""

    entity_id: str
    symbol: str = ""
    anchor: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"entityId": self.entity_id, "symbol": self.symbol, "anchor": dict(self.anchor)}


@dataclass(frozen=True, slots=True)
class RepresentativePath:
    """One contiguous entry-to-effect walk whose edges all exist in N3."""

    steps: tuple[PathStep, ...]
    status: PathStatus
    resolution: Resolution

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "status": str(self.status),
            "resolution": str(self.resolution),
        }


def capability_identity(
    entry_signature: str,
    authoritative_objects: tuple[str, ...],
    effect_signature: tuple[str, ...],
) -> str:
    """Derive the stable capability id from behaviour content, not position.

    Line drift, in-file moves and formatting changes never change the id;
    changing the entry, the authoritative object or the effect set does.
    """
    payload = "\0".join(
        (
            "machine-capability",
            entry_signature,
            "\1".join(sorted(authoritative_objects)),
            "\1".join(sorted(effect_signature)),
        )
    )
    return "cap-" + hashlib.sha256(payload.encode()).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class CapabilitySlice:
    """One entry-driven behaviour slice: trigger, orchestration, effects.

    Invariants enforced at composition time:

    - every representative path is contiguous over N3 relations;
    - ``resolution`` never exceeds the floor of the slice's paths and effects;
    - unterminated branches are counted in ``path_status_counts``, not hidden.
    """

    capability_id: str
    entry_signature: str
    trigger: dict[str, Any]
    entry: dict[str, Any]
    evidence_tier: str = "T3"
    degradation_reasons: tuple[str, ...] = ()
    orchestrators: tuple[str, ...] = ()
    authoritative_objects: tuple[str, ...] = ()
    state_transitions: tuple[dict[str, Any], ...] = ()
    terminal_effects: tuple[TerminalEffect, ...] = ()
    representative_paths: tuple[RepresentativePath, ...] = ()
    shared_dependencies: tuple[str, ...] = ()
    boundary_crossings: tuple[dict[str, Any], ...] = ()
    path_status_counts: dict[str, int] = field(default_factory=dict)
    omitted_counts: dict[str, int] = field(default_factory=dict)
    resolution: Resolution = Resolution.UNRESOLVED
    receipts: tuple[CoverageReceipt, ...] = ()
    expansion_handles: tuple[dict[str, Any], ...] = ()
    # N4 到 N5 的内部关联见证，保留代表路径采样前实际访问的声明。
    # 不作为穷举覆盖证明，也不增加公开能力切片的线协议字段。
    observed_entries: tuple[PathStep, ...] = ()

    def resolution_is_consistent(self) -> bool:
        """Check the monotone-degradation invariant for this slice."""
        members = [path.resolution for path in self.representative_paths]
        members.extend(effect.resolution for effect in self.terminal_effects)
        if not members:
            return self.resolution is Resolution.UNRESOLVED
        return self.resolution == resolution_floor(*members)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recordKind": "capability-slice",
            "capabilityId": self.capability_id,
            "entrySignature": self.entry_signature,
            "trigger": dict(self.trigger),
            "entry": dict(self.entry),
            "evidenceTier": self.evidence_tier,
            "degradationReasons": list(self.degradation_reasons),
            "orchestrators": list(self.orchestrators),
            "authoritativeObjects": list(self.authoritative_objects),
            "stateTransitions": [dict(row) for row in self.state_transitions],
            "terminalEffects": [effect.to_dict() for effect in self.terminal_effects],
            "representativePaths": [path.to_dict() for path in self.representative_paths],
            "sharedDependencies": list(self.shared_dependencies),
            "boundaryCrossings": [dict(row) for row in self.boundary_crossings],
            "pathStatusCounts": dict(self.path_status_counts),
            "omittedCounts": dict(self.omitted_counts),
            "resolution": str(self.resolution),
            "receipts": [receipt.to_dict() for receipt in self.receipts],
            "expansionHandles": [dict(row) for row in self.expansion_handles],
        }


@dataclass(frozen=True, slots=True)
class CapabilityModel:
    """Every slice composed this round, with the seeds that were not covered."""

    slices: tuple[CapabilitySlice, ...]
    seed_count: int = 0
    uncovered_seeds: tuple[str, ...] = ()
    receipts: tuple[CoverageReceipt, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "recordKind": "capability-model",
            "slices": [item.to_dict() for item in self.slices],
            "seedCount": self.seed_count,
            "uncoveredSeeds": list(self.uncovered_seeds),
            "receipts": [receipt.to_dict() for receipt in self.receipts],
        }


__all__ = [
    "CapabilityModel",
    "CapabilitySlice",
    "EffectKind",
    "PathStatus",
    "PathStep",
    "RepresentativePath",
    "TerminalEffect",
    "capability_identity",
]
