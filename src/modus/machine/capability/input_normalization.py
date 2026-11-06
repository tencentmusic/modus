"""Normalize N3 observations into typed capability-composition inputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from ..facts.entry_observation import declaration_aliases, entry_identity
from ..resolution.lifecycle import ResolvedProgram
from ..states import Resolution
from .composition_model import (
    RESOLUTION_ORDER as _RESOLUTION_ORDER,
)
from .composition_model import (
    Edge as _Edge,
)
from .composition_model import (
    Seed as _Seed,
)
from .composition_model import (
    resolution as _resolution,
)
from .contracts import EffectKind, TerminalEffect

_TRAVERSABLE_RELATIONS = frozenset(
    {"calls", "references", "invokes", "dispatches", "enters", "handles"}
)
_ENTRY_SIGNAL_KINDS = frozenset(
    {"external-http", "external-rpc", "mq", "job", "cli", "public-export"}
)


# 输入只来自已解析的证据包，不重读源码或重新运行识别器。
# 复制记录字典，后续规范化不会修改解析阶段保留的原始观察。
# 缺少身份的入口不能加入关联索引。
# 阶段边界复用冻结证据，后续能力组合不应获得新的磁盘读取权威。
def _observations(
    resolved: ResolvedProgram,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the N3 source-evidence contract without reopening source files."""
    entries: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    for packet in resolved.source_evidence.packets.values():
        for raw in packet.get("entries", []):
            if not isinstance(raw, Mapping):
                continue
            entry = dict(raw)
            entry_id = str(entry.get("entryId") or "")
            if entry_id:
                entries[entry_id] = entry
        relations.extend(
            dict(row) for row in packet.get("relations", []) if isinstance(row, Mapping)
        )
        signals.extend(
            dict(row) for row in packet.get("authoringRecords", []) if isinstance(row, Mapping)
        )
    return entries, relations, signals


# 终态效果的分类只解释已有证据，不通过名称推导任意副作用。
# 发布类写入和普通数据写入分开，以便能力摘要描述外部影响。
# 缓存读取不算写效果；状态、锁和事务保留为状态转换。
def _effect_kind(signal: Mapping[str, Any]) -> EffectKind | None:
    evidence = str(signal.get("evidenceKind") or "")
    value = str(signal.get("value") or "").casefold()
    if evidence == "authoritative-write":
        if any(word in value for word in ("publish", "produce", "emit", "send")):
            return EffectKind.EVENT_PUBLISH
        return EffectKind.DATA_WRITE
    if evidence in {"state", "transaction", "lock", "idempotency"}:
        return EffectKind.STATE_TRANSITION
    if evidence == "cache" and any(word in value for word in ("set", "put", "evict")):
        return EffectKind.CACHE_WRITE
    return None


# 兼容声明位置与调用点两种来源，返回独立的位置字典。
# 位置缺失时保留空锚点，不伪造源码行号。
def _anchor(row: Mapping[str, Any]) -> dict[str, Any]:
    location = row.get("location") or row.get("callSite") or {}
    return dict(location) if isinstance(location, Mapping) else {}


# 把多种观察格式收敛为种子、邻接、效果、资源和状态转换。
# 只有运行时代码可成为入口，测试与示例不能抬高能力覆盖率。
# 所有跨图引用统一使用 entry_identity，避免符号 ID 与入口 ID 混用。
# 集合与排序消除重复边，并使下游预算遍历具有可重复的次序。
def collect_inputs(
    resolved: ResolvedProgram,
) -> tuple[
    dict[str, dict[str, Any]],
    tuple[_Seed, ...],
    dict[str, tuple[_Edge, ...]],
    dict[str, tuple[TerminalEffect, ...]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[dict[str, Any], ...]],
]:
    entries, relations, signals = _observations(resolved)
    aliases = declaration_aliases(list(entries.values()))

    def canonical(identity: str) -> str:
        return aliases.get(identity, identity)

    def executable(identity: str) -> bool:
        entry = entries.get(identity, {})
        return entry.get("sourceRole") == "runtime" and entry.get("kind") in {
            "function",
            "method",
            "constructor",
            "handler",
        }

    seeds: dict[str, _Seed] = {}
    effects: defaultdict[str, list[TerminalEffect]] = defaultdict(list)
    resources: defaultdict[str, list[str]] = defaultdict(list)
    transitions: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        entry_id = canonical(str(signal.get("entryId") or ""))
        if entry_id not in entries or str(entries[entry_id].get("sourceRole") or "") != "runtime":
            continue
        evidence_kind = str(signal.get("evidenceKind") or "")
        if (
            str(signal.get("kind") or "") == "entry"
            and evidence_kind in _ENTRY_SIGNAL_KINDS
            and executable(entry_id)
        ):
            signature = str(
                signal.get("value")
                or signal.get("contract")
                or entries[entry_id].get("symbol")
                or entry_id
            )
            seeds.setdefault(
                entry_id,
                _Seed(
                    entry_id,
                    signature,
                    {
                        "kind": evidence_kind,
                        "contract": str(signal.get("contract") or ""),
                        "value": str(signal.get("value") or ""),
                        "anchor": _anchor(signal),
                    },
                    _resolution(signal.get("resolution"), Resolution.HEURISTIC),
                ),
            )
        effect_kind = _effect_kind(signal)
        if effect_kind is not None:
            effect = TerminalEffect(
                effect_kind,
                str(signal.get("contract") or signal.get("value") or evidence_kind),
                _anchor(signal),
                _resolution(signal.get("resolution"), Resolution.HEURISTIC),
            )
            if effect not in effects[entry_id]:
                effects[entry_id].append(effect)
            if effect_kind is EffectKind.STATE_TRANSITION:
                transitions[entry_id].append(
                    {
                        "kind": evidence_kind,
                        "value": str(signal.get("value") or ""),
                        "anchor": _anchor(signal),
                    }
                )
        elif str(signal.get("kind") or "") == "resource":
            resources[entry_id].append(
                str(signal.get("contract") or signal.get("value") or evidence_kind)
            )
    # 声明入口补足规则观察；setdefault 保留先前更具体的触发信息。
    # 方法图身份与源证据中的入口身份必须先归一再匹配。
    # 存在图记录并不保证存在可用源码入口。
    method_graph = resolved.topology.get("methodGraph") or {}
    method_entries = method_graph.get("entries", []) if isinstance(method_graph, Mapping) else []
    for row in method_entries:
        if not isinstance(row, Mapping):
            continue
        entry_id = canonical(entry_identity(str(row.get("symbolId") or "")))
        entry = entries.get(entry_id)
        if entry is None or not executable(entry_id):
            continue
        signature = str(entry.get("signature") or entry.get("symbol") or entry_id)
        seeds.setdefault(
            entry_id,
            _Seed(
                entry_id,
                signature,
                {"kind": "declared-entry", "entryId": str(row.get("entryId") or "")},
                Resolution.EXACT,
            ),
        )
    # 导出函数是另一类入口来源，但导出字段或类型本身不是执行入口。
    # 要求已有 runtime 函数/方法记录，避免仅凭可见性创造能力。
    for graph_id, attrs in resolved.graph.nodes(data=True):
        if not attrs.get("exported"):
            continue
        identity = canonical(entry_identity(str(graph_id)))
        entry = entries.get(identity)
        if (
            entry is not None
            and str(entry.get("sourceRole") or "") == "runtime"
            and str(entry.get("kind") or "") in {"function", "method"}
        ):
            seeds.setdefault(
                identity,
                _Seed(
                    identity,
                    str(entry.get("signature") or entry.get("symbol") or identity),
                    {"kind": "public-export", "anchor": dict(entry.get("location") or {})},
                    Resolution.EXACT,
                ),
            )
    # 遍历仅接受明确列出的关系类型，资源关联不会自动变成调用边。
    # 目标必须能在入口表中展开；未知目标留待其他证据表达。
    adjacency: defaultdict[str, list[_Edge]] = defaultdict(list)
    for row in relations:
        relation = str(row.get("relation") or "")
        if relation not in _TRAVERSABLE_RELATIONS:
            continue
        source = canonical(str(row.get("source") or ""))
        target = canonical(str(row.get("target") or ""))
        if source and target and target in entries:
            adjacency[source].append(
                _Edge(target, relation, _resolution(row.get("resolution"), Resolution.CANDIDATE))
            )
    method_nodes = {
        str(row.get("id") or ""): row
        for row in (method_graph.get("nodes", []) if isinstance(method_graph, Mapping) else [])
        if isinstance(row, Mapping)
    }
    for row in method_graph.get("edges", []) if isinstance(method_graph, Mapping) else []:
        if not isinstance(row, Mapping):
            continue
        source = canonical(entry_identity(str(row.get("from") or "")))
        target_id = str(row.get("to") or "")
        target = canonical(entry_identity(target_id))
        relation = str(row.get("relation") or "")
        resolution = _resolution(row.get("resolution"), Resolution.CANDIDATE)
        if relation in _TRAVERSABLE_RELATIONS and source in entries and target in entries:
            adjacency[source].append(_Edge(target, relation, resolution))
        if relation not in {"writes", "invalidates", "publishes", "invokes"}:
            continue
        # 方法图的外部调用和资源写入转成终态效果。
        # 缺少目标详细属性时仍保留目标身份，便于追溯尚未解析的边界。
        target_node = method_nodes.get(target_id, {})
        target_kind = str(target_node.get("kind") or "")
        effect_kind = (
            EffectKind.EVENT_PUBLISH
            if relation == "publishes"
            else EffectKind.EXTERNAL_CALL
            if relation == "invokes"
            else EffectKind.CACHE_WRITE
            if relation == "invalidates" or target_kind == "cache"
            else EffectKind.FILE_WRITE
            if target_kind == "file"
            else EffectKind.DATA_WRITE
        )
        target_name = str(target_node.get("qualifiedName") or target_node.get("name") or target_id)
        effects[source].append(TerminalEffect(effect_kind, target_name, _anchor(row), resolution))
        if target_name:
            resources[source].append(target_name)
    # 较高置信度的边优先进入有限遍历预算。
    # 最终资源名排序去重，能力身份不依赖上游记录顺序。
    # 效果与状态转换仍保留各自锚点，不合并不同位置的观察。
    normalized_adjacency = {
        source: tuple(
            sorted(
                set(edges),
                key=lambda edge: (
                    _RESOLUTION_ORDER[edge.resolution],
                    edge.relation,
                    edge.target,
                ),
            )
        )
        for source, edges in adjacency.items()
    }
    return (
        entries,
        tuple(sorted(seeds.values(), key=lambda seed: (seed.signature, seed.entry_id))),
        normalized_adjacency,
        {key: tuple(value) for key, value in effects.items()},
        {key: tuple(sorted(set(value))) for key, value in resources.items()},
        {key: tuple(value) for key, value in transitions.items()},
    )


__all__ = ["collect_inputs"]
