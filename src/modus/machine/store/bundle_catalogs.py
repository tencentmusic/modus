"""Build immutable bundle catalogs from typed lifecycle projections.

Catalog construction is pure with respect to repository state: callers provide
all source identities and projection records explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from modus.machine.errors import validate_code
from modus.machine.progress import ProgressReporter
from modus.machine.store.catalog import (
    CatalogRecord,
    CatalogReference,
    canonical_bytes,
    content_digest,
    write_catalog,
)
from modus.machine.store.catalog_building import (
    _as_objects,
    _as_strings,
    _digest_path,
    _line,
    _positive_record,
    _source_digests,
    _witness,
)
from modus.machine.store.contracts import JsonObject
from modus.machine.store.evidence_records import gap_record, parse_record
from modus.machine.store.scope_catalog import scope_catalog


# 源码快照目录保存输入身份与构建归属，支持重现分析上下文。
# 文件摘要记录和构建单元成员记录分开，避免单条摘要无限膨胀。
# 物理文件名由逻辑身份散列生成，路径文本仍保留在内容中。
# 分析配置只公开摘要，目录读取不需要重新运行配置解析。
# 所有输入来自封存快照，打包过程中不重新扫描文件系统。
def snapshot_catalog(
    directory: Path,
    snapshot: Mapping[str, Any],
    *,
    progress: ProgressReporter | None = None,
) -> CatalogReference:
    records: list[CatalogRecord] = []
    for row in _as_objects(snapshot.get("sources")):
        path = str(row.get("path") or "")
        if not path:
            continue
        key = f"source:{path}"
        records.append(
            CatalogRecord(
                key,
                {
                    **{
                        name: cast(Any, value)
                        for name, value in row.items()
                        if name != "buildUnitIds"
                    },
                    "recordType": "source",
                    "buildUnitMembershipCount": len(_as_strings(row.get("buildUnitIds"))),
                },
                f"snapshot/sources/{_digest_path(path)}.json",
            )
        )
    # 构建单元摘要剥离完整文件列表，成员以独立记录延迟读取。
    # 源码记录仅保留归属数量，避免在两个位置重复持久化大型列表。
    build_context = snapshot.get("buildContext")
    units = _as_objects(build_context.get("units")) if isinstance(build_context, Mapping) else []
    for row in units:
        unit_id = str(row.get("id") or "")
        if not unit_id:
            continue
        unit_digest = _digest_path(unit_id)
        files = _as_strings(row.get("files"))
        summary = {key: cast(Any, value) for key, value in row.items() if key != "files"}
        records.append(
            CatalogRecord(
                f"unit:{unit_id}:summary",
                {**summary, "recordType": "buildUnit", "sourceCount": len(files)},
                f"snapshot/build-units/{unit_digest}/summary.json",
            )
        )
        for path in files:
            records.append(
                CatalogRecord(
                    f"unit:{unit_id}:source:{path}",
                    {
                        "recordType": "buildUnitSource",
                        "buildUnitId": unit_id,
                        "path": path,
                    },
                    f"snapshot/build-units/{unit_digest}/sources/{_digest_path(path)}.json",
                )
            )
    # 基线同时包含源码与分析环境的承诺。
    # 配置摘要使用规范 JSON，键顺序不同不会造成无意义的身份变化。
    analysis_config = cast(JsonObject, snapshot.get("analysisConfig") or {})
    metadata: JsonObject = {
        "corpusDigest": str(snapshot.get("corpusDigest") or ""),
        "analysisContextDigest": str(snapshot.get("analysisContextDigest") or ""),
        "baselineDigest": str(snapshot.get("baselineDigest") or ""),
        "sourceCount": len(_as_objects(snapshot.get("sources"))),
        "buildUnitCount": len(units),
        "repository": cast(Any, snapshot.get("repository") or {}),
        "analysisConfigDigest": content_digest(canonical_bytes(analysis_config)),
    }
    return write_catalog(
        directory,
        catalog="snapshot",
        index_path="snapshot/index.json",
        records=records,
        metadata=metadata,
        pack_records=True,
        progress=progress,
    )


# 服务视图由已解析拓扑投影而来，不在存储层发现新边界。
# 边界记录与关系记录分别编码，保持各自的置信度和源码锚点。
# 节点可用名称回退到稳定身份，但必须有可用的源码路径。
# 服务关系优先归到已收集的来源边界，否则使用目标边界。
# 目录级计数描述实际收集的边界集合，不以原始节点数代替。
def service_catalog(
    directory: Path,
    services: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    progress: ProgressReporter | None = None,
) -> CatalogReference:
    digests = _source_digests(snapshot)
    records: list[CatalogRecord] = []
    nodes = _as_objects(services.get("nodes"))
    boundary_ids: set[str] = set()
    default_path = next(iter(digests), "")
    for row in nodes:
        boundary_id = str(row.get("boundaryId") or row.get("id") or row.get("name") or "")
        if not boundary_id or not default_path:
            continue
        boundary_ids.add(boundary_id)
        anchors = _as_objects(row.get("sourceAnchors") or row.get("anchors"))
        anchor = anchors[0] if anchors else {}
        path = str(anchor.get("path") or anchor.get("file") or default_path)
        value = _positive_record(
            "resource",
            identity=("service-boundary", boundary_id),
            candidate_ids=_as_strings(row.get("candidateIds")),
            resolution=str(row.get("resolution") or "heuristic"),
            source_layer=str(row.get("sourceLayer") or "cst"),
            witness=_witness(
                path=path,
                source_digest=str(anchor.get("sourceDigest") or digests.get(path, "0" * 64)),
                symbol=str(row.get("symbol") or row.get("name") or ""),
                start_line=_line(anchor.get("startLine") or anchor.get("line")),
                end_line=_line(anchor.get("endLine") or anchor.get("line")),
            ),
            details={
                "recordType": "serviceBoundary",
                "boundaryId": boundary_id,
                "boundaryKind": str(row.get("kind") or ""),
                "name": str(row.get("name") or row.get("label") or ""),
            },
        )
        records.append(
            CatalogRecord(
                f"boundary:{boundary_id}:summary",
                value,
                f"services/boundaries/{_digest_path(boundary_id)}/summary.json",
            )
        )
    # 关系可能拥有自己的调用见证，不能直接借用节点的行号。
    # 未解析关系仍保留为 unresolved，便于展示边界处的证据缺口。
    for row in _as_objects(services.get("edges")):
        source = str(row.get("source") or row.get("from") or "")
        target = str(row.get("target") or row.get("to") or "")
        boundary_id = source if source in boundary_ids else target
        witness: Mapping[str, Any] = (
            cast(Mapping[str, Any], row["witness"])
            if isinstance(row.get("witness"), Mapping)
            else {}
        )
        path = str(witness.get("path") or default_path)
        if not boundary_id or not path:
            continue
        value = _positive_record(
            "relation",
            identity=("service-relation", row.get("id"), source, target, row.get("relation")),
            candidate_ids=_as_strings(row.get("candidateIds")),
            resolution=str(row.get("resolution") or "unresolved"),
            source_layer=str(row.get("sourceLayer") or "cst"),
            witness=_witness(
                path=path,
                source_digest=str(witness.get("sourceDigest") or digests.get(path, "0" * 64)),
                symbol=str(witness.get("symbol") or ""),
                start_line=_line(witness.get("startLine")),
                end_line=_line(witness.get("endLine")),
            ),
            details={
                "recordType": "serviceRelation",
                "boundaryId": boundary_id,
                "source": source,
                "target": target,
                "relation": str(row.get("relation") or ""),
            },
        )
        record_id = str(value["recordId"])
        records.append(
            CatalogRecord(
                f"boundary:{boundary_id}:relation:{record_id}",
                value,
                f"services/boundaries/{_digest_path(boundary_id)}/records/{_digest_path(record_id)}.json",
            )
        )
    # 没有可发布关系也可能是投影缺口，不能把诊断丢成“没有依赖”。
    for row in _as_objects(services.get("coverageGaps")):
        reason = str(row.get("reasonCode") or row.get("code") or "machine.projection.service-gap")
        try:
            validate_code(reason)
        except ValueError:
            reason = "machine.projection.service-gap"
        value = gap_record(
            reason,
            details={
                key: cast(Any, row[key])
                for key in ("path", "symbol", "source", "target", "boundaryId", "relationId")
                if key in row
            },
        ).to_dict()
        record_id = str(value["recordId"])
        records.append(
            CatalogRecord(
                f"!gap:{record_id}", value, f"services/gaps/{_digest_path(record_id)}.json"
            )
        )
    return write_catalog(
        directory,
        catalog="services",
        index_path="services/index.json",
        records=records,
        metadata={
            "baselineDigest": str(services.get("baselineDigest") or ""),
            "boundaryCount": len(boundary_ids),
        },
        pack_records=True,
        progress=progress,
    )


# 原始提供者记录转换为公开证据协议时，只保留声明的细节字段。
# 入口、关系与规则信号使用不同字段表，避免泄露内部实现对象。
# 列表细节限量保留，确保单条证据能够进入有界目录。
# 锚点依次兼容 witness、location 与行号，但源码摘要由调用方绑定。
# 身份由路径、原始身份、关系类型及位置共同确定。
# 最终仍通过公共记录校验器，存储不能产生无效协议。
def _evidence_record(
    *,
    raw: Mapping[str, Any],
    path: str,
    source_digest: str,
    candidate_ids: tuple[str, ...],
    kind: str,
) -> JsonObject:
    witness_raw: Mapping[str, Any] = (
        cast(Mapping[str, Any], raw["witness"]) if isinstance(raw.get("witness"), Mapping) else {}
    )
    location: Mapping[str, Any] = (
        cast(Mapping[str, Any], raw["location"]) if isinstance(raw.get("location"), Mapping) else {}
    )
    symbol = str(
        witness_raw.get("symbol")
        or raw.get("symbol")
        or raw.get("sourceSymbol")
        or raw.get("displayName")
        or ""
    )
    detail_names: tuple[str, ...]
    if raw.get("ruleId") or raw.get("evidenceKind"):
        detail_names = (
            "evidenceKind",
            "ruleId",
            "value",
            "contract",
            "observation",
            "displayName",
            "symbol",
            "signature",
        )
        record_type = "authoringSignal"
    elif kind == "entry":
        detail_names = (
            "entryId",
            "kind",
            "language",
            "symbol",
            "signature",
            "displayName",
            "route",
            "contracts",
            "annotations",
            "analysisCompleteness",
        )
        record_type = "sourceEntry"
    else:
        detail_names = (
            "relation",
            "source",
            "target",
            "targetSymbol",
            "sourceReference",
            "targetReference",
            "bindingKind",
            "resolvedBy",
            "reason",
            "contextId",
            "alternatives",
            "analysisCompleteness",
        )
        record_type = "sourceRelation"
    # 空值不进入细节；读取者以记录种类解释字段缺省。
    # 列表裁剪只影响公开细节，不改变原始证据包。
    keep: JsonObject = {"recordType": record_type}
    for name in detail_names:
        value = raw.get(name)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            value = value[:32]
        keep[name] = cast(Any, value)
    identity: tuple[object, ...] = (
        path,
        raw.get("entryId") or raw.get("id") or raw.get("source"),
        raw.get("target"),
        raw.get("kind") or raw.get("relation"),
        location.get("startLine") or witness_raw.get("startLine"),
    )
    if record_type == "authoringSignal":
        # 同一行可同时加锁、保存数据和发送消息。规则及命中值也是信号身份，
        # 不能让文件级去重静默覆盖这些不同事实；普通入口/关系身份保持不变。
        identity += (
            symbol,
            raw.get("ruleId"),
            raw.get("evidenceKind"),
            raw.get("contract"),
            raw.get("value"),
            raw.get("observation"),
        )
    return _positive_record(
        kind,
        identity=identity,
        candidate_ids=candidate_ids,
        resolution=str(raw.get("resolution") or ("exact" if kind == "entry" else "unresolved")),
        source_layer=str(raw.get("sourceLayer") or "cst"),
        witness=_witness(
            path=path,
            source_digest=source_digest,
            symbol=symbol,
            start_line=_line(
                witness_raw.get("startLine") or location.get("startLine") or raw.get("line")
            ),
            end_line=_line(witness_raw.get("endLine") or location.get("endLine")),
        ),
        details=keep,
    )


# 缺口保留原因与可用位置，没有行号时不制造虚假锚点。
# 不合法的上游原因码替换为明确的契约错误原因。
# 保留摘要与处置状态，供读者理解降级的实际影响。
# 缺口采用自己的记录种类，不混入正向证据精度字段。
def _coverage_gap(
    raw: Mapping[str, Any],
    *,
    path: str,
    source_digest: str,
    candidate_ids: tuple[str, ...],
) -> JsonObject:
    reason = str(
        raw.get("reasonCode") or raw.get("reason") or "machine.store.unspecified-coverage-gap"
    )
    try:
        validate_code(reason)
    except ValueError:
        reason = "machine.store.invalid-coverage-reason"
    location: Mapping[str, Any] = (
        cast(Mapping[str, Any], raw["location"]) if isinstance(raw.get("location"), Mapping) else {}
    )
    details: JsonObject = {"path": path}
    for name in ("summary", "disposition", "nodeId", "symbol", "resolution"):
        value = raw.get(name)
        if value not in (None, ""):
            details[name] = cast(Any, value)
    witness = None
    start_line = _line(location.get("startLine") or raw.get("line"))
    if start_line is not None:
        from modus.machine.store.contracts import Witness

        witness = Witness(
            path,
            source_digest,
            str(location.get("symbol") or raw.get("symbol") or ""),
            start_line,
            _line(location.get("endLine")),
        )
    return gap_record(
        reason,
        candidate_ids=candidate_ids,
        witness=witness,
        details=details,
    ).to_dict()


# 文件证据包按稳定路径摘要次序展开，再按记录身份去重。
# 源码条目、关系、规则信号和覆盖缺口使用同一目录通道。
# 文件摘要独立存在，即使没有可用细节也能表达文件级库存。
# 候选关联取自证据索引，存储层不重新划分作用域。
# 写入采用统一打包格式，读取方无需了解各提供者原始结构。
def evidence_catalog(
    directory: Path,
    evidence_index: Mapping[str, Any],
    evidence_packets: Mapping[str, Mapping[str, Any]],
    *,
    progress: ProgressReporter | None = None,
) -> CatalogReference:
    records: list[CatalogRecord] = []
    # 路径摘要连接文件包与范围索引，避免用展示名称作关联键。
    # 缺少索引行时保留空候选关联，文件证据仍可被路径查询读取。
    index_rows = {
        str(row.get("pathDigest") or ""): row
        for row in _as_objects(evidence_index.get("files"))
        if row.get("pathDigest")
    }
    packet_total = len(evidence_packets)

    # 进度按批次节流，最后一个文件强制上报。
    # 回调不影响记录内容或目录摘要，可在无终端环境中关闭。
    def report_packet(completed: int) -> None:
        if (
            progress is not None
            and progress.emits_updates
            and (completed % 64 == 0 or completed == packet_total)
        ):
            progress.advance(
                completed,
                packet_total,
                unit="files",
                force=completed == packet_total,
            )

    for completed, (path_digest, packet) in enumerate(
        sorted(evidence_packets.items()),
        start=1,
    ):
        path = str(packet.get("path") or "")
        source_digest = str(packet.get("sourceDigest") or "")
        if not path or len(source_digest) != 64:
            report_packet(completed)
            continue
        index_row = index_rows.get(path_digest, {})
        candidate_ids = _as_strings(index_row.get("candidateIds"))
        projected: list[JsonObject] = []
        # 源码入口与关系分别转换，不能因共享字段而混淆记录种类。
        # 每条正向记录都绑定当前文件摘要。
        projected.extend(
            _evidence_record(
                raw=row,
                path=path,
                source_digest=source_digest,
                candidate_ids=candidate_ids,
                kind="entry",
            )
            for row in _as_objects(packet.get("entries"))
        )
        projected.extend(
            _evidence_record(
                raw=row,
                path=path,
                source_digest=source_digest,
                candidate_ids=candidate_ids,
                kind="relation",
            )
            for row in _as_objects(packet.get("relations"))
        )
        projected.extend(
            _evidence_record(
                raw=row,
                path=path,
                source_digest=source_digest,
                candidate_ids=candidate_ids,
                kind=str(row.get("kind") or "effect"),
            )
            for row in _as_objects(packet.get("authoringRecords"))
            if str(row.get("kind") or "") in {"entry", "effect", "resource"}
        )
        # 降级与缺口随同文件证据发布，不能在打包时丢弃。
        # 消费者无需读取内部诊断文件即可发现取证不足。
        for raw in _as_objects(packet.get("coverageGaps")):
            projected.append(
                _coverage_gap(
                    raw,
                    path=path,
                    source_digest=source_digest,
                    candidate_ids=candidate_ids,
                )
            )
        # 去重后再计数，摘要反映实际可读取记录而非原始重复观察。
        # 逐条验证让无效提供者输出在发布边界失败。
        projected = list({str(value["recordId"]): value for value in projected}.values())
        for value in projected:
            parse_record(value)
            record_id = str(value["recordId"])
            records.append(
                CatalogRecord(
                    f"file:{path}:{record_id}",
                    value,
                    f"evidence/files/{path_digest}/records/{_digest_path(record_id)}.json",
                )
            )
        # 文件摘要保留入口、关系与交付记录三种数量。
        # 交付记录还包括规则与缺口，因此不等于前两项之和。
        file_summary = _positive_record(
            "resource",
            identity=("source-file", path),
            candidate_ids=candidate_ids,
            resolution="exact",
            source_layer="cst",
            witness=_witness(path=path, source_digest=source_digest),
            details={
                "recordType": "sourceFile",
                "path": path,
                "entryCount": len(_as_objects(packet.get("entries"))),
                "relationCount": len(_as_objects(packet.get("relations"))),
                "recordCount": len(projected),
            },
        )
        records.append(
            CatalogRecord(
                f"file:{path}:summary",
                file_summary,
                f"evidence/files/{path_digest}/summary.json",
            )
        )
        report_packet(completed)
    # 空库存也需要完成进度事件，避免调用方一直等待首个文件。
    # 转换与物理写入分为不同阶段，便于定位大仓库耗时。
    if progress is not None:
        if packet_total == 0:
            progress.advance(0, 0, unit="files", force=True)
        progress.transition("package.catalog.evidence-write")
    return write_catalog(
        directory,
        # 目录元数据保留基线与文件规模，查询时可核对分析归属。
        # 打包参数只影响布局，不改变单条证据的公开 JSON 形状。
        catalog="evidence",
        index_path="evidence/index.json",
        records=records,
        metadata={
            "baselineDigest": str(evidence_index.get("baselineDigest") or ""),
            "fileCount": len(evidence_packets),
        },
        pack_records=True,
        progress=progress,
    )


__all__ = ["evidence_catalog", "scope_catalog", "service_catalog", "snapshot_catalog"]
