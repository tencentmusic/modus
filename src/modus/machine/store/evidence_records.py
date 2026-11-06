"""The sole runtime validator and serializer for authoring evidence records."""

from __future__ import annotations

import hashlib
import json
from typing import cast

from modus.machine.errors import IntegrityError
from modus.machine.store.contracts import (
    SCHEMA_VERSION,
    CoverageGap,
    EffectEvidence,
    EntryEvidence,
    EvidenceRecord,
    JsonObject,
    JsonValue,
    RelationEvidence,
    Resolution,
    ResourceEvidence,
    SourceLayer,
    Witness,
)

_RESOLUTIONS = frozenset({"exact", "candidate", "heuristic", "unresolved"})
_SOURCE_LAYERS = frozenset({"cst", "project-binding", "compiler", "reconciled"})
# 细分类别允许的种类与必需字段集中维护。
# 写入器和读取器共享此表，防止产生只能写出却无法读回的目录。
_DETAIL_CONTRACTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "materialBlock": (frozenset({"resource"}), frozenset({"materialType", "content"})),
    "scopeSummary": (
        frozenset({"resource"}),
        frozenset(
            {
                "candidateCount",
                "actionEntryCount",
                "declarationEntryCount",
                "partitionCount",
                "partitionCandidateCounts",
                "partitionEntryCounts",
                "entryKindCounts",
                "actionEntryKindCounts",
                "entrySignalCounts",
            }
        ),
    ),
    "servicesSummary": (frozenset({"resource"}), frozenset({"boundaryCount"})),
    "candidateSummary": (
        frozenset({"resource"}),
        frozenset(
            {
                "candidateId",
                "partition",
                "structuralBasis",
                "inventory",
                "capabilitySignals",
                "representativeEntries",
                "coverageGapCount",
            }
        ),
    ),
    "candidateMember": (frozenset({"resource"}), frozenset({"candidateId", "path"})),
    "candidateEntry": (
        frozenset({"entry"}),
        frozenset({"entryId", "entryKind", "entryRole"}),
    ),
    "navigationComponent": (frozenset({"resource"}), frozenset({"componentId", "cyclic"})),
    "navigationStep": (
        frozenset({"relation"}),
        frozenset({"sourceSymbol", "targetSymbol", "terminal"}),
    ),
    "candidateCoupling": (frozenset({"relation"}), frozenset({"between", "terminal"})),
    "serviceBoundary": (frozenset({"resource"}), frozenset({"boundaryId", "boundaryKind"})),
    "serviceRelation": (
        frozenset({"relation"}),
        frozenset({"boundaryId", "source", "target", "relation"}),
    ),
    "sourceEntry": (frozenset({"entry"}), frozenset({"entryId", "kind", "symbol"})),
    "sourceRelation": (
        frozenset({"relation"}),
        frozenset({"relation", "source", "target"}),
    ),
    "authoringSignal": (
        frozenset({"entry", "effect", "resource"}),
        frozenset({"evidenceKind", "ruleId", "value"}),
    ),
    "sourceFile": (frozenset({"resource"}), frozenset({"path", "recordCount"})),
}


# 稳定身份只依赖种类与显式身份材料，不依赖写盘位置。
# 规范 JSON 消除字典顺序差异，Unicode 文本保留原值。
# 摘要前缀同时表达记录种类，读取时可检测种类不一致。
def stable_record_id(kind: str, *identity: object) -> str:
    payload = json.dumps(
        [kind, *identity], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return f"{kind}.{hashlib.sha256(payload.encode()).hexdigest()[:32]}"


# 边界校验拒绝隐式类型转换，非字符串键不能进入公开 JSON 对象。
def _object(value: object, *, name: str) -> JsonObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise IntegrityError("machine.store.invalid-record-field", details={"field": name})
    return cast(JsonObject, value)


# 身份集合要求非空字符串且无重复，避免过滤与计数产生歧义。
# 保留声明顺序供稳定序列化使用。
def _strings(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise IntegrityError("machine.store.invalid-record-field", details={"field": name})
    if len(value) != len(set(value)):
        raise IntegrityError("machine.store.invalid-record-field", details={"field": name})
    return tuple(value)


# recordType 决定可用的证据大类与必需字段。
# 新增细分类别需在此注册，不能只靠写入方自声明。
# 允许细节扩展字段，但不允许缺失现有必需字段。
def _validate_details(kind: str, details: JsonObject) -> None:
    record_type = details.get("recordType")
    if not isinstance(record_type, str) or record_type not in _DETAIL_CONTRACTS:
        raise IntegrityError("machine.store.record-details-type")
    kinds, required = _DETAIL_CONTRACTS[record_type]
    if kind not in kinds or not required.issubset(details):
        raise IntegrityError("machine.store.record-details-contract")


# 行号允许未知值；布尔值和非正整数不能被强转成源码位置。
def _line(value: object, *, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise IntegrityError("machine.store.invalid-record-field", details={"field": name})
    return value


# 锚点字段使用闭合契约，未知字段不能悄然跨越存储边界。
# 类型检查后交给 Witness 核验路径、摘要及行号范围。
# 缺少源码身份不能构造看似有效的正向证据。
def parse_witness(value: object) -> Witness:
    row = _object(value, name="witness")
    allowed = {"path", "symbol", "startLine", "endLine", "sourceDigest"}
    if set(row) != allowed:
        raise IntegrityError("machine.store.record-witness-fields")
    path = row["path"]
    source_digest = row["sourceDigest"]
    symbol = row["symbol"]
    if (
        not isinstance(path, str)
        or not isinstance(source_digest, str)
        or not isinstance(symbol, str)
    ):
        raise IntegrityError("machine.store.record-witness-types")
    return Witness(
        path=path,
        symbol=symbol,
        start_line=_line(row["startLine"], name="start-line"),
        end_line=_line(row["endLine"], name="end-line"),
        source_digest=source_digest,
    )


# 先识别版本和种类，再按各类精确字段集合验证。
# 覆盖缺口有独立协议，不具备正向证据的置信度与来源字段。
# 缺口可无锚点，正向观察必须拥有可验证的 witness。
# recordId 前缀必须与种类一致，避免同一标识被解释成不同对象。
# 精度和来源均为封闭枚举，未知值不能默认为 exact。
# 最终构造类型化记录，后续读取不再反复猜测原始字典形状。
def parse_record(value: object) -> EvidenceRecord:
    """Validate one complete discriminated record without coercing bad fields."""

    row = _object(value, name="object")
    if row.get("schemaVersion") != SCHEMA_VERSION:
        raise IntegrityError("machine.store.record-schema")
    kind = row.get("kind")
    record_id = row.get("recordId")
    if not isinstance(kind, str) or not isinstance(record_id, str) or not record_id:
        raise IntegrityError("machine.store.record-identity")
    candidate_ids = _strings(row.get("candidateIds"), name="candidate-ids")
    details = _object(row.get("details"), name="details")
    if kind == "coverageGap":
        allowed = {
            "schemaVersion",
            "kind",
            "recordId",
            "reasonCode",
            "candidateIds",
            "witness",
            "details",
        }
        if (
            set(row) != allowed
            or not isinstance(row.get("reasonCode"), str)
            or not row["reasonCode"]
            or not record_id.startswith("gap.")
        ):
            raise IntegrityError("machine.store.coverage-gap-fields")
        witness = None if row["witness"] is None else parse_witness(row["witness"])
        return CoverageGap(
            record_id,
            str(row["reasonCode"]),
            candidate_ids,
            witness,
            details,
        )
    allowed = {
        "schemaVersion",
        "kind",
        "recordId",
        "candidateIds",
        "resolution",
        "sourceLayer",
        "witness",
        "details",
    }
    if kind not in {"entry", "relation", "effect", "resource"} or set(row) != allowed:
        raise IntegrityError("machine.store.record-kind-or-fields")
    if not record_id.startswith(kind + "."):
        raise IntegrityError("machine.store.record-id-kind")
    resolution = row.get("resolution")
    source_layer = row.get("sourceLayer")
    if resolution not in _RESOLUTIONS or source_layer not in _SOURCE_LAYERS:
        raise IntegrityError("machine.store.record-precision")
    _validate_details(kind, details)
    arguments = (
        record_id,
        candidate_ids,
        cast(Resolution, resolution),
        cast(SourceLayer, source_layer),
        parse_witness(row["witness"]),
        details,
    )
    if kind == "entry":
        return EntryEvidence(*arguments)
    if kind == "relation":
        return RelationEvidence(*arguments)
    if kind == "effect":
        return EffectEvidence(*arguments)
    return ResourceEvidence(*arguments)


# 缺口身份包含原因、候选与具体位置，相邻源码的同类缺口可区分。
# 额外细节也参与身份，改变降级事实会产生新的记录标识。
# 没有锚点时仍可表达全局不可用，不伪造文件位置。
# 返回类型化值，统一由公共序列化协议输出。
def gap_record(
    reason_code: str,
    *,
    candidate_ids: tuple[str, ...] = (),
    witness: Witness | None = None,
    details: JsonObject | None = None,
) -> CoverageGap:
    gap_details = details or {}
    identity: list[JsonValue] = [reason_code, *candidate_ids]
    if witness:
        identity.extend([witness.path, witness.start_line, witness.end_line, witness.symbol])
    identity.append(gap_details)
    return CoverageGap(
        stable_record_id("gap", *identity),
        reason_code,
        candidate_ids,
        witness,
        gap_details,
    )


__all__ = ["gap_record", "parse_record", "parse_witness", "stable_record_id"]
