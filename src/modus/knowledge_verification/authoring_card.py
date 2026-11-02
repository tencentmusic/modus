"""Typed validation boundary for the resumable knowledge-authoring card.

The card is temporary orchestration state, not authored knowledge. Publication
consumes only its stable ``schemaVersion: 2`` wire contract: exact Module
evidence work, Domain coverage work, and terminal review state. Keeping that
parsing here prevents the publication composer from becoming a second, loosely
typed card schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Final

from ..knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ..paths import ModusPaths
from ..skillmd import split_frontmatter
from .models import VerificationFinding, finding

CARD_DOCUMENT: Final = "modus/.cache/knowledge-authoring/scope-confirmation.md"
AUTHORING_SCHEMA_VERSION: Final = 2

_MODULE_STATUSES: Final = frozenset({"pending", "evidence-ready", "authored", "reviewed"})
_EVIDENCE_STATUSES: Final = frozenset({"pending", "ready", "blocked"})
_EVIDENCE_MODES: Final = frozenset({"machine-context", "source-fallback", "business-material"})
_COVERAGE_STATUSES: Final = frozenset({"pending", "audited", "blocked"})
_COVERAGE_MODES: Final = frozenset({"machine-context", "source-review"})
_EXECUTION_MODES: Final = frozenset({"serial", "domain-parallel"})


# 拒绝非字符串键，避免宽松 YAML 数据在后续协议序列化时改变身份。
def string_mapping(value: object) -> dict[str, object] | None:
    """Return a plain string-keyed view of a mapping, or reject it."""

    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        return None
    return {str(key): item for key, item in value.items()}


# 只读取唯一执行卡，不在多个临时文件之间猜测最新计划。
# 版本不匹配显式要求升级，不能按旧字段默认解释新协议。
# 执行模式和领域映射分别检查，可同时收集可恢复的契约问题。
# 读取受大小和路径边界约束，卡片不是任意文件读取入口。
def load_authoring_plan(
    paths: ModusPaths,
) -> tuple[dict[str, object] | None, list[VerificationFinding]]:
    """Load the unique schema-version-2 execution card and return its Domain plan."""

    try:
        text = read_bound_regular_text(
            paths.root, paths.scope_confirmation_path, max_bytes=2 * 1024 * 1024
        )
    except BoundKnowledgeReadError as exc:
        return None, [
            finding(
                CARD_DOCUMENT,
                "authoring-card-unavailable",
                f"发布需要唯一执行卡： {exc.kind}",
            )
        ]
    frontmatter, _body = split_frontmatter(text)
    modus = string_mapping(frontmatter.get("modus"))
    authoring = string_mapping(modus.get("authoring") if modus is not None else None)
    if authoring is None:
        return None, [
            finding(
                CARD_DOCUMENT,
                "authoring-card-invalid",
                "frontmatter 必须包含 modus.authoring",
            )
        ]
    schema_version = authoring.get("schemaVersion")
    if schema_version != AUTHORING_SCHEMA_VERSION:
        return None, [
            finding(
                CARD_DOCUMENT,
                "authoring-card-upgrade-required",
                f"发布需要创作 schemaVersion： {AUTHORING_SCHEMA_VERSION}; got {schema_version!r}",
            )
        ]
    findings: list[VerificationFinding] = []
    execution_mode = authoring.get("executionMode")
    if execution_mode not in _EXECUTION_MODES:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-execution-mode-invalid",
                "executionMode 必须为 'serial' 或 'domain-parallel'",
            )
        )
    domains = string_mapping(authoring.get("domains"))
    if domains is None or not domains:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-card-invalid",
                "modus.authoring.domains 必须为非空映射",
            )
        )
        return None, findings
    return domains, findings


# 选择器可为单字符串或非空字符串列表，空白值不表示明确范围。
def _non_empty_selector(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _source_selector(value: object, *, machine: bool) -> bool:
    """校验声明的语法和源码边界，不将语法通过解释成查询已执行。"""
    if not _non_empty_selector(value):
        return False
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list):
        return False
    for expression in values:
        for term in str(expression).split(" OR "):
            term = term.strip()
            kind, separator, reference = term.partition(":")
            if separator and kind in {"candidate", "capability", "symbol"}:
                if not reference.strip():
                    return False
                continue
            if separator and kind == "path":
                path = reference.strip()
            elif machine:
                return False
            else:
                path = term
            parts = PurePosixPath(path).parts
            if (
                not parts
                or path.startswith("/")
                or "\\" in path
                or ":" in path
                or ".." in parts
                or parts[:2] in {("modus", "knowledge"), ("modus", ".cache")}
            ):
                return False
    return True


# 模块状态与证据状态分别核验，已写正文不代表证据已就绪。
# requestedScope 必须精确绑定当前领域和模块，避免复用相邻模块回执。
# 选择器记录实际取证范围，不能仅声明使用了机器分析。
# 源码回退和业务材料模式需要原因，降级必须可解释。
# 保留可识别的模块状态，即使其他字段有误仍可继续发布核验。
def verify_module_execution(
    domain: str, module: str, raw: object
) -> tuple[str | None, list[VerificationFinding]]:
    """Validate one resumable Module work item from the schema-version-2 card."""

    plan = string_mapping(raw)
    if plan is None:
        return None, [
            finding(
                CARD_DOCUMENT,
                "authoring-module-invalid",
                f"Module {domain}/{module} plan 必须为映射",
            )
        ]
    findings: list[VerificationFinding] = []
    status = plan.get("status")
    if status not in _MODULE_STATUSES:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-invalid",
                f"Module {domain}/{module} 的状态不受支持：{status!r}",
            )
        )
    evidence = string_mapping(plan.get("evidence"))
    if evidence is None:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-evidence-missing",
                f"Module {domain}/{module} 需要结构化证据记录",
            )
        )
        return status if isinstance(status, str) else None, findings

    evidence_status = evidence.get("status")
    mode = evidence.get("mode")
    expected_scope = f"module:{domain}/{module}"
    if evidence_status not in _EVIDENCE_STATUSES or evidence_status != "ready":
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-evidence-incomplete",
                f"Module {domain}/{module} 的证据必须就绪，实际为 {evidence_status!r}",
            )
        )
    if mode not in _EVIDENCE_MODES:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-evidence-invalid",
                f"Module {domain}/{module} 的证据模式不受支持：{mode!r}",
            )
        )
    if evidence.get("requestedScope") != expected_scope:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-scope-mismatch",
                f"Module {domain}/{module} 的 requestedScope 必须为 {expected_scope!r}",
            )
        )
    if not _non_empty_selector(evidence.get("selector")):
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-selector-missing",
                f"Module {domain}/{module} 需要精确的证据选择器",
            )
        )
    elif mode != "business-material" and not _source_selector(
        evidence.get("selector"), machine=mode == "machine-context"
    ):
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-selector-invalid",
                f"Module {domain}/{module} 需要源码范围的有效 selector",
            )
        )
    reason = evidence.get("reason")
    if mode in {"source-fallback", "business-material"} and (
        not isinstance(reason, str) or not reason.strip()
    ):
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-module-evidence-reason-missing",
                f"Module {domain}/{module} 的证据模式 {mode!r} needs a reason",
            )
        )
    return status if isinstance(status, str) else None, findings


# 领域覆盖审查独立于单模块完成状态，防止遗漏未分配的源码。
# 覆盖必须达到 audited，合法的 pending 状态仍不能发布。
# 源码审查回退保留原因和选择器，便于后续维护者重现边界。
# 返回全部独立发现，避免一次只修一个字段导致反复试错。
def verify_domain_coverage(domain: str, raw: object) -> list[VerificationFinding]:
    """Validate the Domain-level coverage audit recorded by the root author."""

    coverage = string_mapping(raw)
    if coverage is None:
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-coverage-missing",
                f"Domain {domain!r} 需要结构化覆盖审查",
            )
        ]
    findings: list[VerificationFinding] = []
    status = coverage.get("status")
    mode = coverage.get("mode")
    if status not in _COVERAGE_STATUSES or status != "audited":
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-coverage-incomplete",
                f"Domain {domain!r} 的覆盖状态必须已审查，实际为 {status!r}",
            )
        )
    if mode not in _COVERAGE_MODES:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-coverage-invalid",
                f"Domain {domain!r} 的覆盖模式不受支持：{mode!r}",
            )
        )
    if not _non_empty_selector(coverage.get("selector")):
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-coverage-selector-missing",
                f"Domain {domain!r} 需要提供覆盖审查所用的源码选择器",
            )
        )
    elif not _source_selector(coverage.get("selector"), machine=mode == "machine-context"):
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-coverage-selector-invalid",
                f"Domain {domain!r} 不能用生成知识、缓存或无效 selector 证明覆盖",
            )
        )
    reason = coverage.get("reason")
    if mode == "source-review" and (not isinstance(reason, str) or not reason.strip()):
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-coverage-reason-missing",
                f"Domain {domain!r} 回退到源码审查时需要说明原因",
            )
        )
    return findings


__all__ = [
    "AUTHORING_SCHEMA_VERSION",
    "CARD_DOCUMENT",
    "load_authoring_plan",
    "string_mapping",
    "verify_domain_coverage",
    "verify_module_execution",
]
