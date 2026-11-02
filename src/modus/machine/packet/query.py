"""Budgeted query execution over one authenticated analysis bundle."""

from __future__ import annotations

import hashlib

from modus.knowledge_reader import read_bound_regular_bytes
from modus.machine.errors import BudgetError, InvariantError
from modus.machine.store.bundle import canonical_bytes, load_catalog_range, load_catalog_ranges
from modus.machine.store.contracts import (
    SCHEMA_VERSION,
    AnalysisBundle,
    CoverageGap,
    EvidencePage,
    EvidenceQuery,
    EvidenceRecord,
    JsonObject,
)
from modus.machine.store.evidence_records import gap_record, parse_record, stable_record_id

from .cursor import decode_cursor, encode_cursor


def _details(record: EvidenceRecord) -> JsonObject:
    return record.details


# 候选过滤按集合交集判断，一条证据可同时支撑多个候选。
def _candidate_match(record: EvidenceRecord, candidate_ids: set[str]) -> bool:
    return not candidate_ids or bool(candidate_ids.intersection(record.candidate_ids))


# 兼容单能力和多能力关联字段，空过滤条件不额外缩小结果集。
def _capability_match(record: EvidenceRecord, capability_ids: set[str]) -> bool:
    if not capability_ids:
        return True
    details = _details(record)
    values = {str(details.get("capabilityId") or "")}
    declared = details.get("capabilityIds")
    if isinstance(declared, list):
        values.update(str(value) for value in declared)
    return bool(capability_ids.intersection(values))


# 能力句柄先通过候选摘要解析，不把外部 ID 当作物理目录。
# 只读取摘要键范围，避免为路由加载全部证据。
def _candidate_ids_for_capabilities(bundle: AnalysisBundle, capability_ids: set[str]) -> set[str]:
    """Resolve public capability handles through bounded scope summaries."""

    if not capability_ids:
        return set()
    summaries = _parse_unique([_prefix_records(bundle, "scope", "!summary:")])
    return {
        str(record.details.get("candidateId") or "")
        for _key, record in summaries
        if _capability_match(record, capability_ids)
        and str(record.details.get("candidateId") or "")
    }


# 优先使用源码见证路径，缺口没有见证时读取其说明路径。
# 前缀按目录边界匹配，避免相似文件名扩大范围。
def _path_match(record: EvidenceRecord, paths: set[str]) -> bool:
    if not paths:
        return True
    witness = record.witness
    if witness is None:
        value = str(record.details.get("path") or "")
    else:
        value = witness.path
    return any(value == path or value.startswith(path.rstrip("/") + "/") for path in paths)


# 符号搜索同时覆盖见证、签名与关系端点，匹配不改变证据精度。
def _symbol_match(record: EvidenceRecord, symbols: set[str]) -> bool:
    if not symbols:
        return True
    witness = record.witness
    values = [witness.symbol if witness else ""]
    values.extend(
        str(record.details.get(key) or "")
        for key in ("symbol", "signature", "source", "target", "entryId")
    )
    return any(symbol in value for symbol in symbols for value in values if value)


# 服务边界既可作为所属边界，也可作为关系端点被查询。
def _boundary_match(record: EvidenceRecord, boundary_ids: set[str]) -> bool:
    if not boundary_ids:
        return True
    details = _details(record)
    values = {
        str(details.get("boundaryId") or ""),
        str(details.get("source") or ""),
        str(details.get("target") or ""),
    }
    return bool(boundary_ids.intersection(values))


# 记录类别与证据类别分别过滤，同时给定时取交集。
def _record_kind_match(
    record: EvidenceRecord, record_types: set[str], evidence_kinds: set[str]
) -> bool:
    # 缺口属于所选源码范围，不因只取某一正向记录类别而消失。
    if isinstance(record, CoverageGap):
        return True
    details = record.details
    return (not record_types or str(details.get("recordType") or "") in record_types) and (
        not evidence_kinds or str(details.get("evidenceKind") or "") in evidence_kinds
    )


# 逻辑键前缀转换为有界区间，实际页面读取仍验证内容摘要。
def _prefix_records(
    bundle: AnalysisBundle, catalog: str, prefix: str
) -> tuple[tuple[str, JsonObject], ...]:
    return load_catalog_range(
        bundle,
        catalog,
        start_key=prefix,
        end_key=prefix + "\U0010ffff",
    )


# 多个前缀一起读取，游标之前的整个区间可以跳过。
# 剩余区间从游标键开始，最终严格大于关系在分页层执行。
def _prefixes_records(
    bundle: AnalysisBundle,
    catalog: str,
    prefixes: list[str],
    *,
    after_key: str = "",
) -> tuple[tuple[str, JsonObject], ...]:
    ranges = []
    for prefix in sorted(set(prefixes)):
        end = prefix + "\U0010ffff"
        if after_key and after_key >= end:
            continue
        ranges.append((max(prefix, after_key), end))
    return load_catalog_ranges(
        bundle,
        catalog,
        ranges=tuple(ranges),
    )


# 范围可能重叠，先按目录键去重再解析，避免重复占用页面预算。
def _parse_unique(
    ranges: list[tuple[tuple[str, JsonObject], ...]],
) -> list[tuple[str, EvidenceRecord]]:
    values = {key: value for records in ranges for key, value in records}
    return [(key, parse_record(value)) for key, value in sorted(values.items())]


# 全局摘要优先使用已有证据锚点，无证据时才从快照寻找源码身份。
# 摘要同样需要可验证见证，不能仅因它是导航记录而省略来源。
def _summary_witness(bundle: AnalysisBundle, records: list[EvidenceRecord]) -> JsonObject | None:
    for record in records:
        if record.witness is not None:
            return record.witness.to_dict()
    for _key, value in _prefix_records(bundle, "snapshot", "source:"):
        if value.get("recordType") == "source":
            path, digest = value.get("path"), value.get("sha256")
            if isinstance(path, str) and isinstance(digest, str):
                return {
                    "path": path,
                    "symbol": "",
                    "startLine": None,
                    "endLine": None,
                    "sourceDigest": digest,
                }
    return None


# 没有源码见证时返回覆盖缺口，不制造正向摘要证据。
# 摘要身份绑定基线，不能跨版本复用统计结论。
def _global_summary(
    bundle: AnalysisBundle,
    *,
    record_type: str,
    count_name: str,
    count: int,
    records: list[EvidenceRecord],
    extra_details: JsonObject | None = None,
) -> EvidenceRecord:
    witness = _summary_witness(bundle, records)
    if witness is None:
        reason = {
            "scopeSummary": "machine.packet.scope-summary-empty",
            "servicesSummary": "machine.packet.services-summary-empty",
        }.get(record_type, "machine.packet.summary-empty")
        return gap_record(reason, details={count_name: count})
    return parse_record(
        {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "resource",
            "recordId": stable_record_id("resource", record_type, bundle.baseline_digest),
            "candidateIds": [],
            "resolution": "heuristic",
            "sourceLayer": "cst",
            "witness": witness,
            "details": {
                "recordType": record_type,
                count_name: count,
                **(extra_details or {}),
            },
        }
    )


# 视图决定目录选择和默认深度，细节筛选不会直接暴露存储路径。
# 候选与能力同时指定时取交集，不能把两个范围相加。
# 默认 scope 只返回概要；指定候选才展开成员和入口。
# 所有记录最终经过统一类型过滤与稳定键排序。
def _selection_records(
    bundle: AnalysisBundle, request: EvidenceQuery, *, after_key: str = ""
) -> list[tuple[str, EvidenceRecord]]:
    requested_candidates = set(request.candidate_ids)
    capabilities = set(request.capability_ids)
    capability_candidates = _candidate_ids_for_capabilities(bundle, capabilities)
    candidates = (
        requested_candidates.intersection(capability_candidates)
        if requested_candidates and capabilities
        else requested_candidates or capability_candidates
    )
    # 显式能力没有归属或与候选不相交时，所有视图都必须保持空集。
    if capabilities and not candidates:
        return []
    boundaries = set(request.boundary_ids)
    paths = set(request.paths)
    symbols = set(request.symbols)
    record_types = set(request.record_types)
    evidence_kinds = set(request.evidence_kinds)
    selected: list[tuple[str, EvidenceRecord]] = []
    if request.view == "scope":
        if paths or symbols:
            # 源码选择器通过已发布的记录找归属，不只匹配摘要的代表锚点。
            matches = _selection_records(
                bundle,
                EvidenceQuery(
                    view="evidence",
                    candidate_ids=request.candidate_ids,
                    capability_ids=request.capability_ids,
                    paths=request.paths,
                    symbols=request.symbols,
                ),
            )
            source_candidates = {
                candidate_id for _, record in matches for candidate_id in record.candidate_ids
            }
            candidates = (
                candidates.intersection(source_candidates) if candidates else source_candidates
            )
            if not candidates:
                return []
        summaries = _parse_unique([_prefix_records(bundle, "scope", "!summary:")])
        if requested_candidates or capabilities or paths or symbols:
            if not candidates:
                return []
            details = [
                _prefixes_records(
                    bundle,
                    "scope",
                    [f"candidate:{candidate_id}:" for candidate_id in candidates],
                )
            ]
            parsed = [*summaries, *_parse_unique(details)]
            selected = [
                (key, record)
                for key, record in parsed
                if _candidate_match(record, candidates)
                and _capability_match(record, capabilities)
                and (
                    record.details.get("recordType") == "candidateSummary"
                    or (_path_match(record, paths) and _symbol_match(record, symbols))
                )
            ]
        else:
            selected.extend(summaries)
            # 范围摘要区分动作与声明，类型数量不能冒充可执行能力数量。
            # 分区统计和入口类型分布从同一批候选摘要汇总。
            action_entry_count = 0
            declaration_entry_count = 0
            partition_candidate_counts: dict[str, int] = {}
            partition_entry_counts: dict[str, int] = {}
            entry_kind_counts: dict[str, int] = {}
            action_entry_kind_counts: dict[str, int] = {}
            entry_signal_counts: dict[str, int] = {}
            for _key, summary in summaries:
                partition = str(summary.details.get("partition") or "unassigned")
                partition_candidate_counts[partition] = (
                    partition_candidate_counts.get(partition, 0) + 1
                )
                inventory = summary.details.get("inventory")
                if not isinstance(inventory, dict):
                    continue
                action = inventory.get("actionEntryCount")
                declaration = inventory.get("declarationEntryCount")
                if isinstance(action, int) and not isinstance(action, bool):
                    action_entry_count += action
                if isinstance(declaration, int) and not isinstance(declaration, bool):
                    declaration_entry_count += declaration
                candidate_entry_count = sum(
                    value
                    for value in (action, declaration)
                    if isinstance(value, int) and not isinstance(value, bool)
                )
                partition_entry_counts[partition] = (
                    partition_entry_counts.get(partition, 0) + candidate_entry_count
                )
                kinds = inventory.get("entryKindCounts")
                if isinstance(kinds, dict):
                    for name, count_value in kinds.items():
                        if isinstance(count_value, int) and not isinstance(count_value, bool):
                            key = str(name)
                            entry_kind_counts[key] = entry_kind_counts.get(key, 0) + count_value
                action_kinds = inventory.get("actionEntryKindCounts")
                if isinstance(action_kinds, dict):
                    for name, count_value in action_kinds.items():
                        if isinstance(count_value, int) and not isinstance(count_value, bool):
                            key = str(name)
                            action_entry_kind_counts[key] = (
                                action_entry_kind_counts.get(key, 0) + count_value
                            )
                capability = summary.details.get("capabilitySignals")
                capability = capability if isinstance(capability, dict) else {}
                signals = capability.get("entries")
                if isinstance(signals, dict):
                    for name, count_value in signals.items():
                        if isinstance(count_value, int) and not isinstance(count_value, bool):
                            key = str(name)
                            entry_signal_counts[key] = entry_signal_counts.get(key, 0) + count_value
            selected.append(
                (
                    "!scope:summary",
                    _global_summary(
                        bundle,
                        record_type="scopeSummary",
                        count_name="candidateCount",
                        count=len(summaries),
                        records=[record for _, record in summaries],
                        extra_details={
                            "actionEntryCount": action_entry_count,
                            "declarationEntryCount": declaration_entry_count,
                            "partitionCount": len(partition_candidate_counts),
                            "partitionCandidateCounts": dict(
                                sorted(partition_candidate_counts.items())
                            ),
                            "partitionEntryCounts": dict(sorted(partition_entry_counts.items())),
                            "entryKindCounts": dict(sorted(entry_kind_counts.items())),
                            "actionEntryKindCounts": dict(sorted(action_entry_kind_counts.items())),
                            "entrySignalCounts": dict(sorted(entry_signal_counts.items())),
                        },
                    ),
                )
            )
    elif request.view == "services":
        # 边按发起方存储；只读被查询边界的前缀会漏掉指向它的入边。
        service_ranges = [load_catalog_range(bundle, "services")]
        parsed = _parse_unique(service_ranges)
        selected = [
            (key, record)
            for key, record in parsed
            if _boundary_match(record, boundaries)
            and _candidate_match(record, candidates)
            and _path_match(record, paths)
            and _symbol_match(record, symbols)
            and (
                bool(boundaries or candidates or paths or symbols)
                or "serviceRelation" in record_types
                or record.details.get("recordType") == "serviceBoundary"
                or isinstance(record, CoverageGap)
            )
        ]
        # 无过滤的服务首屏只展示边界概要，关系细节留待指定范围读取。
        # 全局服务计数对应实际返回的边界集合。
        if not (boundaries or candidates or paths or symbols):
            selected.append(
                (
                    "!services:summary",
                    _global_summary(
                        bundle,
                        record_type="servicesSummary",
                        count_name="boundaryCount",
                        count=sum(
                            record.details.get("recordType") == "serviceBoundary"
                            for _, record in selected
                        ),
                        records=[record for _, record in selected],
                    ),
                )
            )
    else:
        # 候选筛选先展开成员路径，缩小证据目录实际读取范围。
        # 显式路径存在时优先使用它，避免候选成员自动扩大读取量。
        evidence_paths = set(paths)
        if candidates and not evidence_paths:
            member_ranges = [
                _prefixes_records(
                    bundle,
                    "scope",
                    [f"candidate:{candidate_id}:member:" for candidate_id in candidates],
                )
            ]
            for _key, value in _parse_unique(member_ranges):
                path = value.details.get("path")
                if isinstance(path, str) and path:
                    evidence_paths.add(path)
        evidence_ranges = (
            [
                _prefixes_records(
                    bundle,
                    "evidence",
                    [f"file:{path}" for path in evidence_paths],
                    after_key=after_key,
                )
            ]
            if evidence_paths
            else [load_catalog_range(bundle, "evidence", start_key=after_key)]
        )
        parsed = _parse_unique(evidence_ranges)
        selected = [
            (key, record)
            for key, record in parsed
            if _candidate_match(record, candidates)
            and _path_match(record, paths)
            and _symbol_match(record, symbols)
        ]
    return sorted(
        (
            (key, record)
            for key, record in selected
            if _record_kind_match(record, record_types, evidence_kinds)
        ),
        key=lambda item: item[0],
    )


# 交付前重新核验当前源码摘要，过期证据转为显式缺口。
# 同一页面内按路径缓存摘要，避免每条记录都重复读取文件。
# 读取失败与内容变化都不能继续作为当前源码证据返回。
# 查询交付前核对当前记录，避免把失效证据表示为本轮正向结果。
def _current_record(
    bundle: AnalysisBundle,
    record: EvidenceRecord,
    source_digest_cache: dict[str, str | None],
) -> EvidenceRecord:
    witness = record.witness
    if witness is None:
        return record
    current_digest = source_digest_cache.get(witness.path)
    if witness.path not in source_digest_cache:
        path = bundle._root / witness.path
        try:
            raw = read_bound_regular_bytes(bundle._root, path, max_bytes=2 * 1024 * 1024)
            current_digest = hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError):
            current_digest = None
        source_digest_cache[witness.path] = current_digest
    if current_digest == witness.source_digest:
        return record
    return gap_record(
        "machine.packet.source-changed-after-analysis",
        candidate_ids=record.candidate_ids,
        details={"path": witness.path, "staleRecordId": record.record_id},
    )


# 正向材料与覆盖缺口分别序列化，但共享同一个分析身份和游标。
def _make_selection(
    bundle: AnalysisBundle,
    request: EvidenceQuery,
    records: list[tuple[str, EvidenceRecord]],
    *,
    next_cursor: str | None,
) -> EvidencePage:
    positives = tuple(record for _, record in records if not isinstance(record, CoverageGap))
    gaps = tuple(record for _, record in records if isinstance(record, CoverageGap))
    return EvidencePage(
        bundle.bundle_digest,
        bundle.baseline_digest,
        request.view,
        positives,
        gaps,
        next_cursor,
    )


# 游标先验证查询归属，再从其后开始交付，避免跨筛选条件续读。
# 数量预算只计算正向证据，缺口仍受完整响应字节预算限制。
# 每次尝试加入条目都计算包含游标的最终封套大小。
# 首条过大与缺口前缀过大分别报错，不能返回无法推进的空页。
# 最终再次核验预算不变量，防止游标变化导致响应超限。
def query_evidence(bundle: AnalysisBundle, query: EvidenceQuery) -> EvidencePage:
    """Return one stable page with at least one positive item or true exhaustion.

    ``max_items`` limits positive evidence. Coverage gaps are diagnostic and do
    not consume that quota, while the complete response remains bounded by
    ``max_bytes``. This lets selection scan a run of gaps or non-matches until
    the next positive record instead of emitting an empty ``items`` page with a
    continuation cursor.
    """

    request = query
    after_key = decode_cursor(bundle, request)
    matching = [
        (key, record)
        for key, record in _selection_records(bundle, request, after_key=after_key)
        if key > after_key
    ]
    page: list[tuple[str, EvidenceRecord]] = []
    positive_count = 0
    # 源码核验缓存限定在一次查询中，下次读取仍可发现新漂移。
    # None 表示本轮已尝试但不可读，不能与未检查混淆。
    source_digest_cache: dict[str, str | None] = {}
    for index, (key, record) in enumerate(matching):
        if positive_count >= request.budget.max_items:
            break
        item = (key, _current_record(bundle, record, source_digest_cache))
        has_more = index < len(matching) - 1
        cursor = encode_cursor(bundle, request, after_key=item[0]) if has_more else None
        proposed = _make_selection(bundle, request, [*page, item], next_cursor=cursor)
        if len(canonical_bytes(proposed.to_dict())) > request.budget.max_bytes:
            if not page:
                raise BudgetError("machine.packet.selection-record-exceeds-budget")
            if positive_count == 0:
                raise BudgetError("machine.packet.selection-gap-prefix-exceeds-budget")
            break
        page.append(item)
        if not isinstance(item[1], CoverageGap):
            positive_count += 1
    # 游标推进到最后实际交付的键，不能跳过因预算未加入的记录。
    # 缺口同样是已消费记录，下一页无需重复报告。
    # 真正耗尽时不再返回游标，区别于预算截断。
    consumed = len(page)
    next_cursor = (
        encode_cursor(bundle, request, after_key=page[-1][0])
        if page and consumed < len(matching)
        else None
    )
    result = _make_selection(bundle, request, page, next_cursor=next_cursor)
    if len(canonical_bytes(result.to_dict())) > request.budget.max_bytes:
        raise InvariantError("machine.packet.selection-budget-invariant")
    return result


__all__ = ["query_evidence"]
