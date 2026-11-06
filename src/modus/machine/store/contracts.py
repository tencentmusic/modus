"""Typed boundary for disposable initialization evidence.

Only identities and bounded selections cross this boundary. Storage paths are
private so callers cannot bypass :func:`query_evidence` and load an unbounded bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Final, Literal, TypeAlias

from ..errors import BudgetError, ContractError, validate_code

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

SCHEMA_VERSION: Final = 1
CATALOG_MAX_BYTES: Final = 256 * 1024
CATALOG_MAX_ITEMS: Final = 128

Resolution = Literal["exact", "candidate", "heuristic", "unresolved"]
SourceLayer = Literal["cst", "project-binding", "compiler", "reconciled"]
SelectionView = Literal["scope", "services", "evidence"]
CompilerMode = Literal["auto", "required", "off"]
AnalysisSourceRole = Literal[
    "runtime",
    "test",
    "fixture",
    "generated",
    "configuration",
    "document",
    "opaque",
]


# 路径要求规范的仓库相对 POSIX 表达，不接受隐式归一化。
# 调用方输入错误应被拒绝，而非改写后指向另一个文件。
def _canonical_relative(value: str, *, field_name: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or value != path.as_posix()
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
    ):
        raise ContractError(
            "machine.packet.invalid-relative-path",
            details={"field": field_name},
        )


# 源码摘要将锚点绑定到捕获版本，行号不脱离内容单独成立。
# 起止行可未知，但已知范围必须单调且从一开始。
@dataclass(frozen=True, slots=True)
class Witness:
    """One current-source anchor supporting an evidence record."""

    path: str
    source_digest: str
    symbol: str = ""
    start_line: int | None = None
    end_line: int | None = None

    def __post_init__(self) -> None:
        _canonical_relative(self.path, field_name="witness.path")
        if len(self.source_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_digest
        ):
            raise ContractError("machine.store.invalid-source-digest")
        if self.start_line is not None and self.start_line < 1:
            raise ContractError("machine.store.invalid-source-position")
        if self.end_line is not None and self.end_line < (self.start_line or 1):
            raise ContractError("machine.store.invalid-source-position")

    def to_dict(self) -> JsonObject:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "startLine": self.start_line,
            "endLine": self.end_line,
            "sourceDigest": self.source_digest,
        }


# 正向证据统一携带置信度、来源层与源码见证。
# 具体子类只选择协议种类，公共字段在一个位置序列化。
@dataclass(frozen=True, slots=True)
class EvidenceRecordBase:
    """Fields shared by every positive evidence observation."""

    record_id: str
    candidate_ids: tuple[str, ...]
    resolution: Resolution
    source_layer: SourceLayer
    witness: Witness
    details: JsonObject = field(default_factory=dict)

    def _base_dict(self, kind: str) -> JsonObject:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": kind,
            "recordId": self.record_id,
            "candidateIds": list(self.candidate_ids),
            "resolution": self.resolution,
            "sourceLayer": self.source_layer,
            "witness": self.witness.to_dict(),
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class EntryEvidence(EvidenceRecordBase):
    def to_dict(self) -> JsonObject:
        return self._base_dict("entry")


@dataclass(frozen=True, slots=True)
class RelationEvidence(EvidenceRecordBase):
    def to_dict(self) -> JsonObject:
        return self._base_dict("relation")


@dataclass(frozen=True, slots=True)
class EffectEvidence(EvidenceRecordBase):
    def to_dict(self) -> JsonObject:
        return self._base_dict("effect")


@dataclass(frozen=True, slots=True)
class ResourceEvidence(EvidenceRecordBase):
    def to_dict(self) -> JsonObject:
        return self._base_dict("resource")


# 缺口是证据的一部分，必须能与正常记录一起传递。
# 全局降级允许没有源码位置，但必须使用稳定原因码。
@dataclass(frozen=True, slots=True)
class CoverageGap:
    """A precise absence or degradation, anchored when one is available."""

    record_id: str
    reason_code: str
    candidate_ids: tuple[str, ...] = ()
    witness: Witness | None = None
    details: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_code(self.reason_code)

    def to_dict(self) -> JsonObject:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "coverageGap",
            "recordId": self.record_id,
            "reasonCode": self.reason_code,
            "candidateIds": list(self.candidate_ids),
            "witness": self.witness.to_dict() if self.witness else None,
            "details": self.details,
        }


EvidenceRecord: TypeAlias = (
    EntryEvidence | RelationEvidence | EffectEvidence | ResourceEvidence | CoverageGap
)


# 调度参数控制资源消耗，不能进入业务事实的语义判断。
# 编译器模式则决定是否要求增强能力，需显式校验。
@dataclass(frozen=True, slots=True)
class AnalysisOptions:
    """Semantic analysis choices; scheduling never changes output facts."""

    compiler_mode: CompilerMode = "auto"
    profile: Literal["auto", "low-memory", "balanced", "throughput"] = "auto"
    workers: int | None = None
    memory_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.compiler_mode not in {"auto", "required", "off"}:
            raise ContractError("machine.facts.invalid-compiler-mode")
        if self.workers is not None and self.workers < 1:
            raise ContractError("machine.runtime.invalid-worker-count")
        if self.memory_bytes is not None and self.memory_bytes < 1:
            raise ContractError("machine.runtime.invalid-memory-budget")


# 证据包摘要验证产物，基线摘要验证源码及分析上下文。
# 两者缺一不可，避免拿正确产物回答错误版本的问题。
@dataclass(frozen=True, slots=True)
class AnalysisIdentity:
    """The two commitments required to reopen one published analysis."""

    bundle_digest: str
    baseline_digest: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("bundle_digest", self.bundle_digest),
            ("baseline_digest", self.baseline_digest),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ContractError(
                    "machine.store.invalid-analysis-identity",
                    details={"field": field_name},
                )

    def to_dict(self) -> JsonObject:
        return {
            "bundleDigest": self.bundle_digest,
            "baselineDigest": self.baseline_digest,
        }


# 回执只公开身份与有界摘要，不暴露内部存储目录。
# 调用者据身份重新打开分析，不能绕过查询预算直接读取全集。
@dataclass(frozen=True, slots=True)
class AnalysisReceipt:
    """Identity and bounded summaries for one freshly published analysis."""

    identity: AnalysisIdentity
    coverage: JsonObject
    diagnostics: JsonObject
    timings: JsonObject = field(default_factory=dict)

    @property
    def bundle_digest(self) -> str:
        return self.identity.bundle_digest

    @property
    def baseline_digest(self) -> str:
        return self.identity.baseline_digest

    def to_dict(self) -> JsonObject:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "ok",
            **self.identity.to_dict(),
            "coverage": self.coverage,
            "diagnostics": self.diagnostics,
            "timings": self.timings,
        }


# 路径与内部缓存不参与对象身份比较，身份由两个摘要决定。
# 缓存容器可在不可变句柄内复用，但不能改变封存证据的内容。
@dataclass(frozen=True, slots=True)
class AnalysisBundle:
    """A verified immutable identity with package-private storage handles."""

    identity: AnalysisIdentity
    _root: Path = field(repr=False, compare=False)
    _directory: Path = field(repr=False, compare=False)
    _roots: JsonObject = field(repr=False, compare=False)
    _catalog_cache: dict[str, tuple[tuple[str, JsonObject], ...]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _record_cache: dict[str, tuple[tuple[str, EvidenceRecord], ...]] = field(
        default_factory=dict, repr=False, compare=False
    )

    @property
    def bundle_digest(self) -> str:
        return self.identity.bundle_digest

    @property
    def baseline_digest(self) -> str:
        return self.identity.baseline_digest


# 字节预算包含序列化开销，因此设置可容纳协议封套的最小值。
# 条目预算必须为正，避免产生无法推进的空分页。
@dataclass(frozen=True, slots=True)
class EvidenceBudget:
    max_bytes: int = CATALOG_MAX_BYTES
    max_items: int = CATALOG_MAX_ITEMS

    def __post_init__(self) -> None:
        if self.max_bytes < 1024:
            raise BudgetError("machine.packet.invalid-budget", "max_bytes must be at least 1024")
        if self.max_items < 1:
            raise BudgetError("machine.packet.invalid-budget", "max_items must be positive")


# 筛选描述初始化所需证据，不提供任意图查询或文件读取能力。
# 路径与标识先做契约检查，再交给目录层匹配。
# 游标属于特定查询版本，改变过滤条件需重新开始。
@dataclass(frozen=True, slots=True)
class EvidenceQuery:
    """Purpose-built initialization evidence selection, never a graph query."""

    view: SelectionView
    candidate_ids: tuple[str, ...] = ()
    boundary_ids: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    record_types: tuple[str, ...] = ()
    evidence_kinds: tuple[str, ...] = ()
    budget: EvidenceBudget = EvidenceBudget()
    cursor: str | None = None
    capability_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value in self.paths:
            _canonical_relative(value, field_name="paths")
        if self.boundary_ids and self.view != "services":
            raise ContractError(
                "machine.packet.unsupported-boundary-filter",
                "boundary selectors require services view",
            )
        for name, values in (
            ("candidate_ids", self.candidate_ids),
            ("capability_ids", self.capability_ids),
            ("boundary_ids", self.boundary_ids),
            ("symbols", self.symbols),
            ("record_types", self.record_types),
            ("evidence_kinds", self.evidence_kinds),
        ):
            if any(not value or value != value.strip() for value in values):
                raise ContractError(
                    "machine.packet.invalid-query",
                    details={"field": name},
                )


# 页面同时携带证据与缺口，让调用者知道结果的边界。
# 下一页游标为空才表示本次筛选读取结束。
# 序列化保留基线与证据包身份，便于跨进程校验。
@dataclass(frozen=True, slots=True)
class EvidencePage:
    """One budget-bounded page returned from exactly one verified bundle."""

    bundle_digest: str
    baseline_digest: str
    view: SelectionView
    items: tuple[EvidenceRecord, ...]
    coverage_gaps: tuple[CoverageGap, ...] = ()
    next_cursor: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "bundleDigest": self.bundle_digest,
            "baselineDigest": self.baseline_digest,
            "view": self.view,
            "items": [item.to_dict() for item in self.items],
            "coverageGaps": [item.to_dict() for item in self.coverage_gaps],
            "nextCursor": self.next_cursor,
        }


__all__ = [
    "AnalysisBundle",
    "AnalysisIdentity",
    "AnalysisOptions",
    "AnalysisReceipt",
    "AnalysisSourceRole",
    "CATALOG_MAX_BYTES",
    "CATALOG_MAX_ITEMS",
    "CompilerMode",
    "CoverageGap",
    "EffectEvidence",
    "EntryEvidence",
    "EvidenceBudget",
    "EvidenceRecord",
    "EvidenceQuery",
    "EvidencePage",
    "JsonObject",
    "JsonValue",
    "RelationEvidence",
    "Resolution",
    "ResourceEvidence",
    "SCHEMA_VERSION",
    "SelectionView",
    "SourceLayer",
    "Witness",
]
