"""Interpret user intent and bound workspace scope before retrieval begins."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from ..config import ModusConfig
from ..orchestrator import fallback
from ..paths import ModusPaths
from .settings import RetrievalSettings
from .stages.lexical import tokenize

QueryPurpose = Literal["change"]


@dataclass(frozen=True, slots=True)
class IntentRule:
    """Ordered intent classifier rule.

    Rules are deliberately data rather than branches: precedence is visible,
    multilingual vocabulary is local, and adding an intent does not disturb the
    analysis algorithm.
    """

    name: str
    pattern: re.Pattern[str]


_INTENT_RULES = (
    IntentRule("debug", re.compile(r"(?:错误|异常|故障|失败|报错|bug|error|exception|fail)", re.I)),
    IntentRule(
        "impact",
        re.compile(
            r"(?:影响|依赖|调用链|链路|跨仓|下游|impact|depend|call\s*chain|cross[- ]repo)",
            re.I,
        ),
    ),
    IntentRule("contract", re.compile(r"(?:接口|契约|协议|api|contract|schema|rpc|http|mq)", re.I)),
    IntentRule(
        "design", re.compile(r"(?:设计|方案|架构|规划|design|solution|architecture|plan)", re.I)
    ),
    IntentRule(
        "change",
        re.compile(
            r"(?:新增|增加|补充|优化|修改|调整|实现|删除|重构|add|change|modify|implement|refactor|remove|optimi[sz]e)",
            re.I,
        ),
    ),
)

_RESPONSE_MODE_BY_INTENT = {
    "contract": "contract",
    "design": "solution",
    "change": "solution",
}

_EVIDENCE_NEEDS_BY_INTENT = {
    "debug": ("current-source", "relationship"),
    "impact": ("relationship", "current-source"),
    "contract": ("contract", "current-source"),
    "design": ("business-rule", "relationship", "current-source"),
    "change": ("business-rule", "current-source"),
    "answer": ("routing", "current-source"),
}

_ENTITY_RE = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_.:/-]{2,}|[\u4e00-\u9fff]{2,12})")
_CROSS_MEMBER_RE = re.compile(
    r"(?:跨仓|端到端|全链路|契约|系统间|cross[- ]repo|end[- ]to[- ]end|contract)", re.I
)


# 意图规则按声明次序匹配，多个关键词命中时优先级可见。
# change 用途额外要求规则与当前源码，不覆盖原意图的证据需求。
# 实体去重并限量，保持查询协议有界。
def analyze_query(
    query: str,
    *,
    constraints: list[str] | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    """Convert free text into a stable retrieval intent contract."""

    if purpose not in (None, "change"):
        raise ValueError("purpose 必须为 change")

    intent = next((rule.name for rule in _INTENT_RULES if rule.pattern.search(query)), "answer")
    response_mode = _RESPONSE_MODE_BY_INTENT.get(intent, "answer")

    entities = list(dict.fromkeys(fallback.extract_terms(query)))
    for value in _ENTITY_RE.findall(query):
        normalized = value.casefold()
        if normalized not in entities:
            entities.append(normalized)

    evidence_needs = list(_EVIDENCE_NEEDS_BY_INTENT[intent])
    if purpose == "change" or intent == "change":
        evidence_needs = list(
            dict.fromkeys(
                [
                    *evidence_needs,
                    "business-rule",
                    "domain-knowledge",
                    "engineering-constraint",
                    "current-source",
                ]
            )
        )

    return {
        "intent": intent,
        "purpose": purpose,
        "responseMode": response_mode,
        "entities": entities[:32],
        "constraints": list(constraints or []),
        "evidenceNeeds": evidence_needs,
    }


# 显式路径只在已确认成员中匹配，未知路径保留为范围外提示。
# 自然语言路由使用成员身份与路径，不打开所有仓库正文。
# 无命中时采用有限候选集并标记原因，不声称已确定成员。
# 排序以得分和路径共同确定，预算结果不依赖配置遍历偶然顺序。
# 成员上限控制推断路径，显式选择保留用户给定范围。
def select_workspace_members(
    paths: ModusPaths,
    request: str,
    *,
    explicit_paths: list[str] | None = None,
    max_members: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a deterministic, bounded subset without resolving every repository."""

    config = ModusConfig.read_available(paths)
    maximum = max_members or RetrievalSettings.read(paths).max_members
    requested_paths = list(explicit_paths or [])
    members: list[dict[str, Any]] = list(config.workspace.get("members") or [])

    if requested_paths:
        selected = [
            member
            for member in members
            if any(_paths_overlap(path, str(member["path"])) for path in requested_paths)
        ]
        matched_prefixes = tuple(str(item["path"]) for item in selected)
        out_of_scope = [
            path
            for path in requested_paths
            if not any(_paths_overlap(path, prefix) for prefix in matched_prefixes)
        ]
        return selected, _workspace_route(
            selected,
            rationale="explicit-member-path",
            outOfScopePaths=out_of_scope,
        )

    terms = tokenize(request)
    lowered = request.casefold()
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for member in members:
        member_id = str(member["id"])
        member_path = str(member["path"])
        haystack = " ".join(
            [member_id, member_path, str(member.get("repositoryId", ""))]
        ).casefold()
        exact_terms = {member_id.casefold(), member_path.casefold()}
        score = sum(3 if term in exact_terms else 1 for term in terms if term in haystack)
        if member_id.casefold() in lowered or member_path.casefold() in lowered:
            score += 5
        scored.append((score, member_path, member))

    scored.sort(key=lambda item: (-item[0], item[1]))
    positive = [item for item in scored if item[0] > 0]
    if positive:
        cross_member = bool(_CROSS_MEMBER_RE.search(request))
        selected = [
            item[2] for item in positive[: maximum if cross_member or len(positive) > 1 else 1]
        ]
        rationale = "workspace-cross-member" if len(selected) > 1 else "workspace-member"
    else:
        selected = [item[2] for item in scored[:maximum]]
        rationale = "workspace-unknown-bounded"
    return selected, _workspace_route(selected, rationale=rationale)


# 父子路径按段边界判断，名称前缀相似不表示属于同一成员。
def _paths_overlap(left: str, right: str) -> bool:
    return (
        left == "." or left == right or left.startswith(right + "/") or right.startswith(left + "/")
    )


# 工作区路由先确定成员，领域和模块留给成员知识进一步细化。
# 路由理由随结果输出，便于解释自动选择与显式选择的差异。
def _workspace_route(
    members: list[dict[str, Any]], *, rationale: str, **extra: Any
) -> dict[str, Any]:
    return {
        "kind": "workspace",
        "members": [item["id"] for item in members],
        "domains": [],
        "modules": [],
        "frontend": False,
        "rationale": rationale,
        **extra,
    }


__all__ = ["QueryPurpose", "analyze_query", "select_workspace_members"]
