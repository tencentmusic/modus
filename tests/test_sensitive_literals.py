"""Synthetic secrets verify detection, redaction and safe failure reporting.

The literals below are intentionally artificial regression inputs. Assertions
require diagnostics and published projections to withhold their original values.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _support.sensitive_samples import SYNTHETIC_JWT, synthetic_source_assignment
from modus.machine import AnalysisOptions, analyze_repository
from modus.machine.corpus.source_snapshot import SourceSnapshot
from modus.machine.errors import IntegrityError
from modus.machine.facts.native_parser import parser_for
from modus.machine.store.bundle import _assert_safe_publication
from modus.paths import ModusPaths
from modus.sensitive_literals import (
    contains_sensitive_literal,
    redact_sensitive_text,
    sensitive_literal_findings,
)


# 标识符和调用表达式不是凭据；检测目标是实际字面量。
def test_code_variable_assignment_is_not_mistaken_for_a_literal() -> None:
    assert not contains_sensitive_literal("token = resolvedTokenValue")
    assert not contains_sensitive_literal("accountId = request.getAccountId()")
    assert contains_sensitive_literal(synthetic_source_assignment())


# 报告只保留类别和 JSON 指针，防止诊断成为第二条泄漏通道。
def test_redaction_and_findings_never_return_the_original_literal() -> None:
    identity = "12345678901234567" + "8"
    redacted, kinds = redact_sensitive_text(f"customer identity: {identity}")
    assert identity not in redacted
    assert kinds == ("identity-number",)

    findings = sensitive_literal_findings({"evidence": {"comment": identity}})
    assert [(item.kind, item.pointer) for item in findings] == [
        ("identity-number", "/evidence/comment")
    ]


# 进度回调只接收计数，不能将被扫描内容带出检测边界。
def test_sensitive_scan_progress_exposes_counts_but_never_values() -> None:
    inspected: list[int] = []
    secret = SYNTHETIC_JWT

    findings = sensitive_literal_findings(
        {"evidence": [{"value": "safe"}, {"value": secret}]},
        on_progress=inspected.append,
    )

    assert findings
    assert inspected and inspected[-1] > 0
    assert all(isinstance(value, int) for value in inspected)


def test_repeated_text_is_reported_at_every_location_and_mutations_are_rechecked() -> None:
    payload = [{"value": SYNTHETIC_JWT}, {"value": SYNTHETIC_JWT}]
    findings = sensitive_literal_findings(payload)
    assert [(item.kind, item.pointer) for item in findings] == [
        ("jwt", "/0/value"),
        ("jwt", "/1/value"),
    ]
    payload[0]["value"] = "safe"
    assert [item.pointer for item in sensitive_literal_findings(payload)] == ["/1/value"]
    # 超过短文本缓存边界仍完整检查，不能因长度而跳过秘密。
    assert sensitive_literal_findings("x" * 5000 + " " + SYNTHETIC_JWT)[0].kind == "jwt"


# 人工构造的 JWT 形状用于触发规则；它没有真实签名或账户。
# 异常应指出定位坐标，同时隐藏原始值。
def test_publication_failure_reports_only_safe_coordinates(tmp_path: Path) -> None:
    token = SYNTHETIC_JWT
    with pytest.raises(IntegrityError) as caught:
        _assert_safe_publication(
            ModusPaths.for_root(tmp_path),
            {"scope": {"signature": token}},
        )
    assert caught.value.code == "machine.store.sensitive-publication"
    message = str(caught.value)
    assert "jwt@/scope/signature" in message
    assert token not in message


# 本机路径同样不能进入可分享产物，错误信息也不得回显它。
def test_nonportable_publication_reports_only_safe_coordinates(tmp_path: Path) -> None:
    checkout_path = str(tmp_path / "source.java")
    with pytest.raises(IntegrityError) as caught:
        _assert_safe_publication(
            ModusPaths.for_root(tmp_path),
            {"scope": {"source": checkout_path}},
        )
    assert caught.value.code == "machine.store.nonportable-publication"
    message = str(caught.value)
    assert "/scope/source" in message
    assert checkout_path not in message


# 保留引用关系即可完成绑定分析，无需复制敏感的右值文本。
def test_structural_local_binding_does_not_retain_rhs_literal(tmp_path: Path) -> None:
    identity = "12345678901234567" + "8"
    source = tmp_path / "Example.java"
    facts = parser_for("java")(
        SourceSnapshot(
            source,
            "class Example { void run() { "
            f'String identity = "{identity}"; '
            "Object alias = service; } }",
        )
    )
    bindings = {row["name"]: row for scope in facts["scopes"] for row in scope.get("bindings", [])}

    assert bindings["identity"] == {"name": "identity", "kind": "local"}
    assert bindings["alias"]["target_name"] == "service"


# 端到端检查已发布字节，避免只检查中间对象而漏掉另一份序列化。
# 允许有标记的脱敏证据继续发布，保留可用的其余分析结果。
def test_machine_projection_redacts_source_literals_instead_of_losing_bundle(
    tmp_path: Path,
) -> None:
    identity = "12345678901234567" + "8"
    source = tmp_path / "Example.java"
    source.write_text(
        "class Example {\n"
        f'  @OpenApiPostMapping(apiName = "{identity}", apiUrl = "/orders")\n'
        "  public void run() {}\n"
        "}\n",
        encoding="utf-8",
    )

    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = tmp_path / "modus/.cache/init-analysis/bundles" / receipt.bundle_digest
    published = b"".join(path.read_bytes() for path in bundle.rglob("*.json"))

    assert identity.encode() not in published
    assert b"[redacted:identity-number]" in published
    assert b"machine.projection.sensitive-literal-redacted" in published
