"""N6 output contract: the least an author needs to see for one task.

A packet serves exactly one task intent, is consumable in one response by
default, and proves its own coverage: what is included, what was omitted and
why, and precisely where to expand. Exhausting pagination is never a
precondition for the consumer to finish its task.

"Bounded" means four budgets at once: items, bytes, representative paths per
capability, and a quota for low-resolution or repeated information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from ..errors import BudgetError, ContractError
from ..receipts import CoverageReceipt

AUTHORING_CONTEXT_SCHEMA_VERSION: Final = 1


class TaskIntent(StrEnum):
    """The authoring tasks a packet can serve; one packet, one intent."""

    SCOPE_DISCOVERY = "scope-discovery"
    MODULE_AUTHORING = "module-authoring"
    CONSTRAINT_EXTRACTION = "constraint-extraction"
    SERVICE_BOUNDARY = "service-boundary"
    REINIT_DIFF = "reinit-diff"
    COVERAGE_AUDIT = "coverage-audit"


class HandleKind(StrEnum):
    """What a precise expansion handle points at."""

    CANDIDATE = "candidate"
    CAPABILITY = "capability"
    PATH = "path"
    SYMBOL = "symbol"
    SOURCE_ANCHOR = "source-anchor"
    BOUNDARY = "boundary"


@dataclass(frozen=True, slots=True)
class ExpansionHandle:
    """One precise, optional follow-up -- never an obligation to exhaust."""

    kind: HandleKind
    reference: str
    hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": str(self.kind), "reference": self.reference, "hint": self.hint}


@dataclass(frozen=True, slots=True)
class PacketBudget:
    """The four simultaneous bounds of one packet."""

    max_items: int = 128
    max_bytes: int = 256 * 1024
    max_paths_per_capability: int = 3
    low_resolution_quota: int = 16

    def __post_init__(self) -> None:
        if self.max_items < 1 or self.max_paths_per_capability < 1:
            raise ContractError(
                "machine.packet.invalid-budget", "item and path budgets must be positive"
            )
        if self.max_bytes < 1024:
            raise BudgetError("machine.packet.invalid-budget", "byte budget must be at least 1024")
        if self.low_resolution_quota < 0:
            raise BudgetError(
                "machine.packet.invalid-budget", "low-resolution quota must not be negative"
            )


@dataclass(frozen=True, slots=True)
class PacketScope:
    """Optional exact narrowing for one intent packet."""

    candidate_ids: tuple[str, ...] = ()
    boundary_ids: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, values in (
            ("candidate_ids", self.candidate_ids),
            ("capability_ids", self.capability_ids),
            ("boundary_ids", self.boundary_ids),
            ("paths", self.paths),
            ("symbols", self.symbols),
        ):
            if any(not value or value != value.strip() for value in values):
                raise BudgetError("machine.packet.invalid-scope", f"{name} contains a blank value")

    @property
    def has_module_selector(self) -> bool:
        """Whether the scope identifies concrete source-backed Module work.

        A service boundary is useful for boundary review, but it is not a
        substitute for selecting the capability, path, or symbol whose method
        bodies must be read before a Module is authored.
        """

        return bool(self.candidate_ids or self.capability_ids or self.paths or self.symbols)

    def to_dict(self) -> dict[str, list[str]]:
        """Serialize the exact caller scope for receipts and resumable plans."""

        return {
            "candidateIds": list(self.candidate_ids),
            "capabilityIds": list(self.capability_ids),
            "boundaryIds": list(self.boundary_ids),
            "paths": list(self.paths),
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """One complete authoring-context request.

    Keeping intent, narrowing and budgets in one value prevents positional
    argument drift at the public boundary and makes requests straightforward
    to log, test and evolve.
    """

    intent: TaskIntent
    scope: PacketScope = PacketScope()
    budget: PacketBudget = PacketBudget()

    def __post_init__(self) -> None:
        if self.intent is TaskIntent.MODULE_AUTHORING and not self.scope.has_module_selector:
            raise ContractError(
                "machine.packet.module-scope-required",
                "module-authoring requires at least one candidate, capability, path, or symbol selector",
                details={
                    "requiredAnyOf": [
                        "candidateIds",
                        "capabilityIds",
                        "paths",
                        "symbols",
                    ]
                },
            )


@dataclass(frozen=True, slots=True)
class AuthoringContextPacket:
    """The machine layer's final product for one authoring task.

    Every conclusion inside traces back to N3/N4/N5 records; low-confidence
    material carries an explicit marker plus a handle instead of pretending
    to be comprehensive.
    """

    intent: TaskIntent
    bundle_digest: str
    baseline_digest: str
    requested_scope: PacketScope = PacketScope()
    proposals: tuple[dict[str, Any], ...] = ()
    capabilities: tuple[dict[str, Any], ...] = ()
    representative_paths: tuple[dict[str, Any], ...] = ()
    authoritative_objects: tuple[dict[str, Any], ...] = ()
    terminal_effects: tuple[dict[str, Any], ...] = ()
    ambiguities: tuple[dict[str, Any], ...] = ()
    coverage_receipts: tuple[CoverageReceipt, ...] = ()
    source_anchors: tuple[dict[str, Any], ...] = ()
    expansion_handles: tuple[ExpansionHandle, ...] = ()
    omitted_counts: dict[str, int] = field(default_factory=dict)
    # 保留库存/关系原记录、真实缺口和可重放的公开查询。
    evidence: tuple[dict[str, Any], ...] = ()
    coverage_gaps: tuple[dict[str, Any], ...] = ()
    expansion_queries: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": AUTHORING_CONTEXT_SCHEMA_VERSION,
            "recordKind": "authoring-context-packet",
            "intent": str(self.intent),
            "bundleDigest": self.bundle_digest,
            "baselineDigest": self.baseline_digest,
            "requestedScope": self.requested_scope.to_dict(),
            "proposals": [dict(row) for row in self.proposals],
            "capabilities": [dict(row) for row in self.capabilities],
            "representativePaths": [dict(row) for row in self.representative_paths],
            "authoritativeObjects": [dict(row) for row in self.authoritative_objects],
            "terminalEffects": [dict(row) for row in self.terminal_effects],
            "ambiguities": [dict(row) for row in self.ambiguities],
            "coverageReceipt": [receipt.to_dict() for receipt in self.coverage_receipts],
            "sourceAnchors": [dict(row) for row in self.source_anchors],
            "expansionHandles": [handle.to_dict() for handle in self.expansion_handles],
            "omittedCounts": dict(self.omitted_counts),
            "evidence": [dict(row) for row in self.evidence],
            "coverageGaps": [dict(row) for row in self.coverage_gaps],
            "expansionQueries": [dict(row) for row in self.expansion_queries],
        }


__all__ = [
    "AUTHORING_CONTEXT_SCHEMA_VERSION",
    "AuthoringContextPacket",
    "ContextRequest",
    "ExpansionHandle",
    "HandleKind",
    "PacketBudget",
    "PacketScope",
    "TaskIntent",
]
