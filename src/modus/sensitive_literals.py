"""Small, deterministic guard against persisting obvious sensitive literals."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass
from functools import lru_cache
from typing import Final


@dataclass(frozen=True, slots=True)
class SensitiveLiteralFinding:
    """A safe diagnostic coordinate; the matched source text is never retained."""

    kind: str
    pointer: str


@dataclass(frozen=True, slots=True)
class _SensitiveLiteralRule:
    kind: str
    pattern: re.Pattern[str]


_RULES: Final = (
    _SensitiveLiteralRule("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    _SensitiveLiteralRule("prefixed-api-key", re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b")),
    _SensitiveLiteralRule("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    _SensitiveLiteralRule("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    _SensitiveLiteralRule(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    _SensitiveLiteralRule(
        "phone-number", re.compile(r"(?<![A-Za-z0-9])1[3-9]\d{9}(?![A-Za-z0-9])")
    ),
    _SensitiveLiteralRule(
        "identity-number", re.compile(r"(?<![A-Za-z0-9])\d{17}[\dXx](?![A-Za-z0-9])")
    ),
    _SensitiveLiteralRule(
        "quoted-identity-assignment",
        re.compile(
            r"(?i)\b(?:account|account_?id|customer_?id|identity|identity_?id)\s*"
            r"[:=]\s*['\"][A-Za-z0-9][A-Za-z0-9._:-]{5,}['\"]"
        ),
    ),
    _SensitiveLiteralRule(
        "quoted-credential-assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|token|api[-_]?key|secret|client[-_]?secret|"
            r"access[-_]?token|refresh[-_]?token|account(?:_?id)?|customer_?id|"
            r"identity(?:_?id)?)\b\s*[:=]\s*(['\"])[^'\"\r\n]{8,}\1"
        ),
    ),
    _SensitiveLiteralRule(
        "unquoted-config-secret",
        re.compile(
            r"(?im)^\s*(?:password|passwd|token|api[-_]?key|secret|client[-_]?secret|"
            r"access[-_]?token|refresh[-_]?token)\s*[:=]\s*"
            r"(?=[A-Za-z0-9._~+/=-]{12,}\s*$)(?=[^\r\n]*[0-9.~+/=-])"
            r"[A-Za-z0-9._~+/=-]{12,}\s*$"
        ),
    ),
    _SensitiveLiteralRule(
        "literal-sql",
        re.compile(
            r"(?is)\b(?:select\s+.+?\s+from|insert\s+into|update\s+\w+\s+set|"
            r"delete\s+from)\b.{0,500}?(?:'[^']*'|\"[^\"]*\")"
        ),
    ),
)

# Kept private for small internal diagnostics and compatibility with existing callers.
_PATTERNS: Final = tuple(rule.pattern for rule in _RULES)
_PROGRESS_STRIDE: Final = 4096


# 映射键和值都参与检查，敏感内容不能通过放入键名绕过检测。
def _children(value: object) -> tuple[object, ...] | None:
    if isinstance(value, Mapping):
        return tuple(item for pair in value.items() for item in pair)
    if isinstance(value, (Sequence, Set)) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return None


# 以对象身份阻止循环容器重复遍历，调用方尚未通过 schema 校验也可安全检查。
def contains_sensitive_literal(value: object) -> bool:
    """Return true for credential, identity, phone, or literal-SQL payloads.

    The walk is cycle-safe because this helper is also used defensively on
    caller-owned values before their surrounding schema has necessarily run.
    """
    stack = [value]
    visited: set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, str) and any(pattern.search(current) for pattern in _PATTERNS):
            return True
        children = _children(current)
        if children is None:
            continue
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)
        stack.extend(children)
    return False


# 替换文本保留命中类别，诊断仍可解释而无需返回原字面量。
def redact_sensitive_text(value: str) -> tuple[str, tuple[str, ...]]:
    """Redact prohibited spans while preserving the surrounding evidence shape."""

    redacted = value
    kinds: list[str] = []
    for rule in _RULES:
        redacted, count = rule.pattern.subn(f"[redacted:{rule.kind}]", redacted)
        if count:
            kinds.append(rule.kind)
    return redacted, tuple(kinds)


# 可疑键名统一隐藏，诊断路径本身不能成为敏感信息泄漏渠道。
def _pointer_segment(value: object) -> str:
    text = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", text) or contains_sensitive_literal(text):
        return "<key>"
    return text.replace("~", "~0").replace("/", "~1")


# 数量上限只限制交付的发现，进度回调仅接收检查数量而不接收原始值。
def sensitive_literal_findings(
    value: object,
    *,
    limit: int = 16,
    on_progress: Callable[[int], None] | None = None,
) -> tuple[SensitiveLiteralFinding, ...]:
    """Locate prohibited text without returning or embedding the matched literal.

    ``on_progress`` observes traversal volume only. It never receives inspected
    values, preserving the same safe diagnostic boundary as the findings.
    """

    if limit < 1:
        return ()

    # 同次发布中的协议键和短文本大量重复；缓存只复用字符串匹配，
    # 每个出现位置仍遍历并报告。长源码不驻留，缓存随本次检查释放。
    @lru_cache(maxsize=2048)
    def short_text_kinds(text: str) -> tuple[str, ...]:
        return tuple(rule.kind for rule in _RULES if rule.pattern.search(text))

    @lru_cache(maxsize=256)
    def short_key_segment(text: str) -> str:
        return _pointer_segment(text)

    pending: list[tuple[str, object]] = [("", value)]
    visited: set[int] = set()
    findings: list[SensitiveLiteralFinding] = []
    inspected = 0
    while pending and len(findings) < limit:
        pointer, current = pending.pop()
        inspected += 1
        if on_progress is not None and inspected % _PROGRESS_STRIDE == 0:
            on_progress(inspected)
        if isinstance(current, str):
            kinds = (
                short_text_kinds(current)
                if len(current) <= 4096
                else tuple(rule.kind for rule in _RULES if rule.pattern.search(current))
            )
            for kind in kinds:
                findings.append(SensitiveLiteralFinding(kind, pointer or "/"))
                if len(findings) >= limit:
                    break
            continue
        identity = id(current)
        if identity in visited:
            continue
        if isinstance(current, Mapping):
            visited.add(identity)
            for key, item in reversed(tuple(current.items())):
                text = str(key)
                segment = short_key_segment(text) if len(text) <= 80 else _pointer_segment(text)
                pending.append((f"{pointer}/{segment}", item))
                pending.append((f"{pointer}/<key>", key))
        elif isinstance(current, (Sequence, Set)) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            visited.add(identity)
            for index, item in reversed(tuple(enumerate(current))):
                pending.append((f"{pointer}/{index}", item))
    if on_progress is not None:
        on_progress(inspected)
    return tuple(findings)


__all__ = [
    "SensitiveLiteralFinding",
    "contains_sensitive_literal",
    "redact_sensitive_text",
    "sensitive_literal_findings",
]
