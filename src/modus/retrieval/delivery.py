"""Assemble, measure, and render the evidence that crosses the API boundary."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .stages.documents import matches_knowledge_need

_SOURCE_EVIDENCE_TYPES = frozenset(
    {"current-source", "test-source", "config-source", "contract-source"}
)
_RELATIONSHIP_EVIDENCE_TYPES = frozenset(
    {"workspace-generated", "project-generated", "project-module", "contract-source"}
)
_TRUNCATION_MARKER = "\n[… 运行时上下文已按固定规则截断 …]\n"


# 证据身份在所有优先池之间共享，避免重复占用交付配额。
# 轮转会消费传入的列表；调用者应为需要复用的候选池提供副本。
@dataclass(slots=True)
class EvidenceCollector:
    """Collect unique evidence fairly across ordered priority pools.

    One pass takes at most one item from each pool. This preserves source,
    constraint, and narrative diversity without encoding incomparable score
    scales into a fragile global weight.
    """

    limit: int
    items: list[dict[str, Any]] = field(default_factory=list)
    _identities: set[str] = field(default_factory=set, init=False, repr=False)

    def add(self, item: dict[str, Any]) -> bool:
        identity = str(item["id"])
        if len(self.items) >= self.limit or identity in self._identities:
            return False
        self.items.append(item)
        self._identities.add(identity)
        return True

    def drain_round_robin(self, pools: Iterable[list[dict[str, Any]]]) -> None:
        queues = list(pools)
        while len(self.items) < self.limit and any(queues):
            for queue in queues:
                if queue and len(self.items) < self.limit:
                    self.add(queue.pop(0))

    @property
    def identities(self) -> frozenset[str]:
        return frozenset(self._identities)


# 只有 current 证据可覆盖需求，计划与假设不能冒充已验证材料。
# 需求与来源类型的映射集中在此，便于交付裁剪后重新计算。
def evidence_matches_need(need: str, item: dict[str, Any]) -> bool:
    """Return whether one current evidence item can cover a requested need."""

    if item.get("status") != "current":
        return False
    source_type = str(item.get("sourceType") or "")
    if need == "current-source":
        return source_type in _SOURCE_EVIDENCE_TYPES
    if need in {"business-rule", "domain-knowledge", "engineering-constraint"}:
        return matches_knowledge_need(need, item)
    if need in {"relationship", "contract"}:
        return source_type in _RELATIONSHIP_EVIDENCE_TYPES
    if need == "routing":
        return source_type.startswith(("project-", "workspace-"))
    return False


# 这里衡量检索材料是否到场，不判断答案正确与否。
# 候选是否尚存由上游传入，不能由当前交付批次的大小推断。
def measure_coverage(
    needs: Iterable[str],
    evidence: list[dict[str, Any]],
    *,
    candidates_remain: bool,
) -> dict[str, Any]:
    """Describe evidence-type coverage without claiming factual validation."""

    items: list[dict[str, Any]] = []
    counts: defaultdict[str, int] = defaultdict(int)
    for need in needs:
        matched = [item["id"] for item in evidence if evidence_matches_need(need, item)]
        if matched:
            status = "covered"
        elif any(item.get("status") in {"planned", "hypothesis"} for item in evidence):
            status = "partial"
        else:
            status = "missing"
        counts[status] += 1
        items.append({"need": need, "status": status, "evidenceIds": matched})
    counts.setdefault("conflict", 0)
    counts.setdefault("out-of-scope", 0)
    return {
        "items": items,
        "semantics": "retrieval-hint-only",
        "note": ("匹配到证据类型不代表事实完整、正确，也不构成修改代码的授权。"),
        "summary": dict(sorted(counts.items())),
        "complete": bool(items) and all(item["status"] == "covered" for item in items),
        "candidatesRemain": candidates_remain,
    }


# 围栏长度随摘录中的反引号调整，保持原始文本的引用边界。
# 字符预算包括截断提示；极小预算也不会返回超限的提示语。
def render_context(
    base_markdown: str,
    evidence: list[dict[str, Any]],
    coverage: dict[str, Any],
    maximum: int,
) -> str:
    """Render a deterministic Markdown evidence batch within ``maximum`` chars."""

    lines = [
        base_markdown.rstrip(),
        "",
        "## 本轮运行证据",
        "",
        "覆盖情况仅描述已检索的证据类型，不验证答案，也不证明完整性。",
        "",
    ]
    for item in evidence:
        location = item["path"]
        if item.get("lineStart"):
            location += f":{item['lineStart']}"
        label = f"{item.get('layer', 'evidence')}/{item['sourceType']}/{item['status']}"
        lines.append(f"- `{location}` — {label}")
        excerpt = item.get("excerpt")
        if excerpt:
            fence = "`" * max(
                4, max((len(match[0]) + 1 for match in re.finditer(r"`+", excerpt)), default=4)
            )
            lines.extend(["", fence + "text", str(excerpt), fence, ""])
        target = item.get("readTarget")
        if target and item.get("truncated"):
            lines.append(
                f"  继续阅读 `{target['path']}:{target['lineStart']}-{target['lineEnd']}` 查看完整条目。"
            )
    missing = [item["need"] for item in coverage["items"] if item["status"] != "covered"]
    if missing:
        lines.extend(["", "## 证据缺口", "", *[f"- `{item}`" for item in missing]])
    rendered = "\n".join(lines).rstrip() + "\n"
    if len(rendered) <= maximum:
        return rendered
    if maximum <= len(_TRUNCATION_MARKER):
        return _TRUNCATION_MARKER[: max(0, maximum)]
    return rendered[: maximum - len(_TRUNCATION_MARKER)].rstrip() + _TRUNCATION_MARKER


# 裁剪证据后同时重建覆盖度、继续阅读提示和渲染文本。
# 按尾部逐项缩减，保留上游排序确定的最高优先级。
# 额外覆盖项仍需保留，例如范围限制不能随材料裁剪消失。
def limit_result(
    result: dict[str, Any],
    *,
    evidence_limit: int | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """Keep evidence, coverage, continuation, and rendering mutually consistent."""

    original = result["evidence"]
    maximum = (
        max_chars
        if max_chars is not None
        else int(result.get("retrieval", {}).get("budget", {}).get("maxContextChars", 12_000))
    )
    evidence = original[: max(1, evidence_limit)] if evidence_limit is not None else list(original)
    needs = result["query"]["evidenceNeeds"]
    extras = [item for item in result["coverage"]["items"] if item["need"] not in needs]

    while True:
        trimmed = len(evidence) < len(original)
        coverage = measure_coverage(
            needs,
            evidence,
            candidates_remain=trimmed or result["coverage"]["candidatesRemain"],
        )
        coverage["items"].extend(extras)
        if trimmed:
            coverage["items"].append(
                {"need": "delivery-budget", "status": "partial", "evidenceIds": []}
            )
        coverage["complete"] = bool(coverage["items"]) and all(
            item["status"] == "covered" for item in coverage["items"]
        )
        counts = Counter(item["status"] for item in coverage["items"])
        coverage["summary"] = {"conflict": 0, "out-of-scope": 0, **dict(counts)}
        rendered = render_context("", evidence, coverage, maximum)
        if _TRUNCATION_MARKER.strip() not in rendered or not evidence:
            break
        evidence.pop()

    result.update(evidence=evidence, coverage=coverage, contextMarkdown=rendered)
    result["retrieval"]["deliveredEvidenceCount"] = len(evidence)
    if trimmed:
        result["retrieval"].update(stage="progressive", stopReason="delivery-budget")
        result["continuation"].update(available=True, reason="delivery-budget")
    _merge_read_targets(result, original, evidence)
    return result


# 被截去的证据仍可通过原始行范围继续阅读。
# 按路径和起止行去重，避免相同条目耗尽后续阅读窗口。
def _merge_read_targets(
    result: dict[str, Any],
    original: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> None:
    read_targets = [
        item["readTarget"]
        for item in original
        if item.get("readTarget") and (item.get("truncated") or item not in evidence)
    ]
    read_targets.extend(result.get("continuation", {}).get("readTargets", []))
    result["continuation"]["readTargets"] = list(
        {(item["path"], item["lineStart"], item["lineEnd"]): item for item in read_targets}.values()
    )[:24]
    if result["continuation"]["readTargets"]:
        result["continuation"]["available"] = True
        if result["continuation"].get("reason") == "retrieval-needs-matched":
            result["continuation"]["reason"] = "entry-continuation"


__all__ = [
    "EvidenceCollector",
    "evidence_matches_need",
    "limit_result",
    "measure_coverage",
    "render_context",
]
