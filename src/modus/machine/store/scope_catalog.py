"""Serialize scope candidates, their members and coupling into one catalog.

Candidate ordering, summary keys and witness digests are persisted contracts.
Inventory consistency is checked before publication so a rendered scope cannot
claim entries or representative evidence absent from its input projection.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from modus.machine.errors import IntegrityError
from modus.machine.progress import ProgressReporter
from modus.machine.store.catalog import (
    CatalogRecord,
    CatalogReference,
    write_catalog,
)
from modus.machine.store.catalog_building import (
    _as_objects,
    _as_strings,
    _digest_path,
    _integer,
    _line,
    _positive_record,
    _source_digests,
    _witness,
)
from modus.machine.store.contracts import JsonObject


# 范围目录持久化候选的结构依据、成员、入口与导航关系。
# 这里只消费既有投影和源码摘要，不在写盘阶段再读取仓库。
# 候选排序进入目录键，是后续预算分页的稳定阅读顺序。
# 写入前核对库存计数与代表条目，拒绝摘要和实际材料相互矛盾。
# 物理文件名使用身份摘要，逻辑键仍保留可读的候选和路径。
# 最终采用打包记录，降低大项目小文件数量而保留单条证据协议。
def scope_catalog(
    directory: Path,
    scope: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    progress: ProgressReporter | None = None,
) -> CatalogReference:
    digests = _source_digests(snapshot)
    records: list[CatalogRecord] = []
    candidates = _as_objects(scope.get("candidates"))
    for candidate_rank, candidate in enumerate(candidates):
        candidate_id = str(candidate.get("candidateId") or "")
        if not candidate_id:
            continue
        # 候选逻辑身份单独转为安全路径片段，避免把原始 ID 直接用作文件名。
        candidate_digest = _digest_path(candidate_id)
        files = _as_strings(candidate.get("files"))
        entries = _as_objects(candidate.get("entries"))
        representative_source = _as_objects(candidate.get("representativeEntries"))
        inventory_value = candidate.get("inventory")
        structural_basis_value = candidate.get("structuralBasis")
        capability_signals_value = candidate.get("capabilitySignals")
        if not all(
            isinstance(value, Mapping)
            for value in (inventory_value, structural_basis_value, capability_signals_value)
        ):
            raise IntegrityError("machine.store.scope-profile")
        # 运行时形状检查先于类型收窄，不能仅依赖静态断言接受外部投影。
        inventory = cast(Mapping[str, Any], inventory_value)
        structural_basis = cast(Mapping[str, Any], structural_basis_value)
        capability_signals = cast(Mapping[str, Any], capability_signals_value)
        # 代表入口必须是完整入口清单的子集，不能由展示阶段凭空生成。
        # 动作与声明的计数分别核对，防止类型声明抬高可执行入口数量。
        # 入口类型分布也需一致，避免摘要字段与明细来自不同投影。
        entry_ids = {str(entry.get("entryId") or "") for entry in entries}
        representative_ids = {str(entry.get("entryId") or "") for entry in representative_source}
        if (
            len(representative_source) > 6
            or not representative_ids.issubset(entry_ids)
            or _integer(inventory.get("actionEntryCount"))
            != sum(entry.get("entryRole") == "action" for entry in entries)
            or _integer(inventory.get("declarationEntryCount"))
            != sum(entry.get("entryRole") == "declaration" for entry in entries)
            or _integer(inventory.get("representativeEntryCount")) != len(representative_source)
            or inventory.get("entryKindCounts")
            != dict(
                sorted(Counter(str(entry.get("kind") or "unknown") for entry in entries).items())
            )
            or inventory.get("actionEntryKindCounts")
            != dict(
                sorted(
                    Counter(
                        str(entry.get("kind") or "unknown")
                        for entry in entries
                        if entry.get("entryRole") == "action"
                    ).items()
                )
            )
        ):
            raise IntegrityError("machine.store.scope-inventory")
        # 候选摘要需要源码见证，优先使用该候选的首个文件。
        # 完全没有可用源码路径时跳过，不能构造无路径的正向证据。
        anchor_path = files[0] if files else next(iter(digests), "")
        if not anchor_path:
            continue
        anchor = _witness(path=anchor_path, source_digest=digests.get(anchor_path, "0" * 64))
        # 代表入口保留签名、路由和契约，让首屏具备解释价值。
        # 位置与摘要按同一路径取值，不能混用不同文件的来源身份。
        # 缺失展示字段允许回退，但原有解析精度仍随记录保留。
        representative_entries: list[JsonObject] = []
        for entry in representative_source:
            representative_location = (
                cast(Mapping[str, Any], entry["location"])
                if isinstance(entry.get("location"), Mapping)
                else {}
            )
            representative_entries.append(
                {
                    "entryId": str(entry.get("entryId") or ""),
                    "entryKind": str(entry.get("kind") or ""),
                    "entryRole": str(entry.get("entryRole") or ""),
                    "displayName": str(entry.get("displayName") or ""),
                    "symbol": str(entry.get("symbol") or ""),
                    "signature": str(entry.get("signature") or ""),
                    "route": cast(Any, entry.get("route") or ""),
                    "contracts": cast(Any, entry.get("contracts") or []),
                    "annotations": cast(Any, entry.get("annotations") or []),
                    "path": str(
                        representative_location.get("path")
                        or entry.get("sourceFile")
                        or anchor_path
                    ),
                    "startLine": _line(representative_location.get("startLine")),
                    "endLine": _line(representative_location.get("endLine")),
                    "sourceDigest": str(
                        entry.get("sourceDigest")
                        or digests.get(
                            str(
                                representative_location.get("path")
                                or entry.get("sourceFile")
                                or anchor_path
                            ),
                            "0" * 64,
                        )
                    ),
                    "resolution": str(entry.get("resolution") or "heuristic"),
                    "sourceLayer": str(entry.get("sourceLayer") or "cst"),
                }
            )
        # 候选划分属于启发式投影，摘要不能宣称业务边界已被精确证明。
        # 遗漏计数、证据层级与降级原因必须一起持久化。
        # 下游创作可据此决定哪些结论需要返回源码核验。
        summary = _positive_record(
            "resource",
            identity=("candidate-summary", candidate_id),
            candidate_ids=(candidate_id,),
            resolution="heuristic",
            source_layer="cst",
            witness=anchor,
            details={
                "recordType": "candidateSummary",
                "candidateId": candidate_id,
                "partition": str(candidate.get("partition") or candidate.get("buildUnitId") or ""),
                "structuralBasis": cast(Any, structural_basis),
                "inventory": cast(Any, inventory),
                "capabilitySignals": cast(Any, capability_signals),
                "representativeEntries": cast(Any, representative_entries),
                "coverageGapCount": _integer(candidate.get("coverageGapCount")),
                "capabilityIds": cast(Any, candidate.get("capabilityIds") or []),
                "disposition": str(candidate.get("disposition") or "remainder"),
                "authoritativeObjects": cast(Any, candidate.get("authoritativeObjects") or []),
                "terminalEffects": cast(Any, candidate.get("terminalEffects") or []),
                "evidenceTiers": cast(Any, candidate.get("evidenceTiers") or {}),
                "degradationReasons": cast(Any, candidate.get("degradationReasons") or []),
                "coverageReceipts": cast(Any, candidate.get("coverageReceipts") or []),
                "omittedCounts": cast(Any, candidate.get("omittedCounts") or {}),
            },
        )
        records.append(
            CatalogRecord(
                f"!summary:{candidate_rank:08d}:{candidate_id}",
                summary,
                f"scope/candidates/{candidate_digest}/summary.json",
            )
        )
        # 成员关系表达文件归属事实，与候选业务含义的置信度不同。
        # 每个成员独立成记录，便于分页按路径筛选。
        for path in files:
            member = _positive_record(
                "resource",
                identity=("candidate-member", candidate_id, path),
                candidate_ids=(candidate_id,),
                resolution="exact",
                source_layer="cst",
                witness=_witness(path=path, source_digest=digests.get(path, "0" * 64)),
                details={
                    "recordType": "candidateMember",
                    "candidateId": candidate_id,
                    "path": path,
                },
            )
            record_id = str(member["recordId"])
            records.append(
                CatalogRecord(
                    f"candidate:{candidate_id}:member:{path}",
                    member,
                    f"scope/candidates/{candidate_digest}/records/{_digest_path(record_id)}.json",
                )
            )
        # 完整入口不受代表入口数量限制，后续查询仍可继续读取。
        # 入口身份包含候选与路径，避免不同候选的相同符号冲突。
        for entry in entries:
            location: Mapping[str, Any] = (
                cast(Mapping[str, Any], entry["location"])
                if isinstance(entry.get("location"), Mapping)
                else {}
            )
            path = str(location.get("path") or entry.get("sourceFile") or anchor_path)
            symbol = str(entry.get("symbol") or entry.get("displayName") or "")
            value = _positive_record(
                "entry",
                identity=("candidate-entry", candidate_id, entry.get("entryId"), path),
                candidate_ids=(candidate_id,),
                resolution=str(entry.get("resolution") or "heuristic"),
                source_layer=str(entry.get("sourceLayer") or "cst"),
                witness=_witness(
                    path=path,
                    source_digest=digests.get(path, "0" * 64),
                    symbol=symbol,
                    start_line=_line(location.get("startLine")),
                    end_line=_line(location.get("endLine")),
                ),
                details={
                    "recordType": "candidateEntry",
                    "entryId": str(entry.get("entryId") or ""),
                    "entryKind": str(entry.get("kind") or ""),
                    "entryRole": str(entry.get("entryRole") or ""),
                    "displayName": str(entry.get("displayName") or ""),
                    "symbol": str(entry.get("symbol") or ""),
                    "signature": str(entry.get("signature") or ""),
                    "route": cast(Any, entry.get("route") or ""),
                    "contracts": cast(Any, entry.get("contracts") or []),
                    "annotations": cast(Any, entry.get("annotations") or []),
                    "graphCenter": bool(entry.get("graphCenter")),
                },
            )
            record_id = str(value["recordId"])
            records.append(
                CatalogRecord(
                    f"candidate:{candidate_id}:entry:{record_id}",
                    value,
                    f"scope/candidates/{candidate_digest}/records/{_digest_path(record_id)}.json",
                )
            )
    # 导航投影可从多个连接产生相同记录，持久化前按身份去重。
    # 没有候选或有效源码摘要的导航不能成为公开正向证据。
    navigation_ids: set[str] = set()
    for navigation in _as_objects(scope.get("navigationRecords")):
        candidate_ids = _as_strings(navigation.get("candidateIds"))
        path = str(navigation.get("path") or "")
        source_digest = str(navigation.get("sourceDigest") or digests.get(path, ""))
        if not candidate_ids or not path or len(source_digest) != 64:
            continue
        # 循环分量属于资源，跨分量步骤属于关系。
        # 公共 witness 字段从细节中移出，防止同一位置有两份不一致副本。
        record_type = str(navigation.get("recordType") or "")
        value = _positive_record(
            "resource" if record_type == "navigationComponent" else "relation",
            identity=(
                record_type,
                *candidate_ids,
                navigation.get("componentId"),
                navigation.get("sourceComponentId"),
                navigation.get("targetComponentId"),
                navigation.get("sourceSymbol"),
                navigation.get("targetSymbol"),
                navigation.get("capabilityId"),
                navigation.get("pathIndex"),
                navigation.get("stepIndex"),
            ),
            candidate_ids=candidate_ids,
            resolution=str(navigation.get("resolution") or "exact"),
            source_layer="reconciled",
            witness=_witness(
                path=path,
                source_digest=source_digest,
                symbol=str(navigation.get("symbol") or ""),
                start_line=_line(navigation.get("startLine")),
            ),
            details={
                key: cast(Any, item)
                for key, item in navigation.items()
                if key
                not in {
                    "candidateIds",
                    "path",
                    "sourceDigest",
                    "symbol",
                    "startLine",
                    "resolution",
                }
            },
        )
        record_id = str(value["recordId"])
        if record_id in navigation_ids:
            continue
        navigation_ids.add(record_id)
        records.append(
            CatalogRecord(
                f"candidate:{candidate_ids[0]}:navigation:{record_id}",
                value,
                "scope/candidates/"
                f"{_digest_path(candidate_ids[0])}/records/{_digest_path(record_id)}.json",
            )
        )
    # 耦合只接受明确的候选对，不能从不完整列表猜测另一侧。
    # 连接作为终止边持久化，提示阅读者已到达候选边界。
    for coupling in _as_objects(scope.get("crossCandidateCoupling")):
        between = _as_strings(coupling.get("between"))
        if len(between) != 2:
            continue
        anchor_candidate = next(
            (row for row in candidates if row.get("candidateId") == between[0]), {}
        )
        path = next(iter(_as_strings(anchor_candidate.get("files"))), next(iter(digests), ""))
        if not path:
            continue
        value = _positive_record(
            "relation",
            identity=("candidate-coupling", *between, coupling.get("relation")),
            candidate_ids=between,
            resolution="exact",
            source_layer="reconciled",
            witness=_witness(path=path, source_digest=digests.get(path, "0" * 64)),
            details={
                "recordType": "candidateCoupling",
                "between": list(between),
                "relation": str(coupling.get("relation") or ""),
                "edgeCount": _integer(coupling.get("edges")),
                "terminal": True,
            },
        )
        record_id = str(value["recordId"])
        records.append(
            CatalogRecord(
                f"candidate:{between[0]}:coupling:{between[1]}:{record_id}",
                value,
                f"scope/candidates/{_digest_path(between[0])}/records/{_digest_path(record_id)}.json",
            )
        )
    # 目录元数据保存基线与覆盖说明，供打开目录时核对归属。
    # 进度回调传给统一写入器，不参与记录身份或排序。
    metadata: JsonObject = {
        "baselineDigest": str(scope.get("baselineDigest") or ""),
        "status": str(scope.get("status") or "empty"),
        "candidateCount": len(candidates),
        "coverage": cast(Any, scope.get("coverage") or {}),
        "notice": str(scope.get("notice") or ""),
    }
    return write_catalog(
        directory,
        catalog="scope",
        index_path="scope/index.json",
        records=records,
        metadata=metadata,
        pack_records=True,
        progress=progress,
    )


__all__ = ["scope_catalog"]
