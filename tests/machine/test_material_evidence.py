"""材料和对象声明通过真实 N1～N6 发布，保持来源、顺序与未知语义。"""

from pathlib import Path
from typing import Any, cast

import pytest

from modus.machine import (
    AnalysisOptions,
    EvidenceQuery,
    analyze_repository,
    open_analysis,
    query_evidence,
)
from modus.machine.capability import compose
from modus.machine.corpus import freeze
from modus.machine.facts import observe
from modus.machine.projection.lifecycle import project
from modus.machine.resolution import resolve


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_material_blocks_preserve_text_order_and_explicit_associations(
    tmp_path: Path, newline: str
) -> None:
    content = "# Request\n`Dto.enabled` 可省略，不能解释为 false。\n\n| 字段 | 单位 |\n| --- | --- |\n| amount | 分 |\n\n```java\nBoolean enabled;\n```\n"
    # 材料保留原始换行；夹具明确落盘字节，不能依赖宿主的文本换行转换。
    content = content.replace("\n", newline)
    (tmp_path / "guide.md").write_bytes(content.encode("utf-8"))
    (tmp_path / "Dto.java").write_text("class Dto { Boolean enabled; }", encoding="utf-8")
    (tmp_path / "manual.pdf").write_bytes(b"%PDF\0unsupported")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/ignored.js").write_text("bad", encoding="utf-8")
    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(tmp_path, receipt.identity)
    page = query_evidence(
        bundle, EvidenceQuery(view="evidence", paths=("guide.md",), record_types=("materialBlock",))
    )
    blocks = sorted(page.items, key=lambda row: cast(int, row.details["blockIndex"]))
    assert "".join(str(row.details["content"]) for row in blocks) == content
    assert {row.details["materialType"] for row in blocks} == {"heading", "text", "table", "code"}
    assert all(
        row.witness and row.witness.path == "guide.md" and row.witness.start_line for row in blocks
    )
    mentions = [
        item
        for row in blocks
        for item in cast(list[dict[str, Any]], row.details.get("associations", []))
    ]
    assert any(item["mention"] == "Dto.enabled" and item["entryIds"] for item in mentions)
    gaps = query_evidence(
        bundle, EvidenceQuery(view="evidence", record_types=("coverageGap",))
    ).coverage_gaps
    dispositions = {
        row.details.get("path"): row.details
        for row in gaps
        if row.reason_code == "machine.corpus.input-not-admitted"
    }
    assert dispositions["manual.pdf"]["reason"] == "unsupported-binary"
    assert dispositions["node_modules"]["scope"] == "directory"
    assert "node_modules/ignored.js" not in dispositions


def test_declared_members_are_not_runtime_defaults_and_projection_is_pure(tmp_path: Path) -> None:
    (tmp_path / "Dto.java").write_text(
        'class Dto { @JsonProperty("enabled") @Nullable Boolean optional; boolean flag = false; int scalar, array[][]; int[] matrix[]; enum Status { NEW(0), DONE(1); Status(int code){} } }',
        encoding="utf-8",
    )
    (tmp_path / "types.ts").write_text(
        "interface Payload { enabled?: boolean; amount: number; }", encoding="utf-8"
    )
    (tmp_path / "dto.py").write_text(
        "class Request:\n    enabled: bool | None = None\n    amount: int\n", encoding="utf-8"
    )
    corpus = freeze(tmp_path, compiler_mode="off")
    with corpus.activate():
        observed = observe(corpus)
        # N3 不再执行规则正则；N2 的原始记录先保留，绑定不修改原观察。
        import copy

        observations = copy.deepcopy(observed.rule_observations)
        resolved = resolve(observed)
        before = copy.deepcopy(resolved.source_evidence)
        projection = project(resolved, compose(resolved))
    assert resolved.source_evidence == before
    assert observed.rule_observations == observations
    rows = {
        row["symbol"]: row
        for packet in projection.evidence_packets.values()
        for row in packet["entries"]
        if row.get("objectFacts")
    }
    optional = next(row["objectFacts"] for key, row in rows.items() if key.endswith("Dto.optional"))
    assert optional["declaredType"] == "Boolean"
    assert optional["hasInitializer"] is False
    assert optional["serializationName"] == "enabled"
    assert optional["nullableEvidence"] == ["@Nullable"]
    flag = next(row["objectFacts"] for key, row in rows.items() if key.endswith("Dto.flag"))
    assert flag["declaredType"] == "boolean" and flag["initializer"] == "false"
    for name, expected in (("scalar", "int"), ("array", "int[][]"), ("matrix", "int[][]")):
        facts = next(row["objectFacts"] for key, row in rows.items() if key.endswith("Dto." + name))
        assert facts["declaredType"] == expected
    member = next(row for key, row in rows.items() if key.endswith("Status.NEW"))
    assert member["kind"] == "enum-member" and member["objectFacts"]["initializer"] == "(0)"
    typescript = next(
        row["objectFacts"] for key, row in rows.items() if key.endswith("Payload.enabled")
    )
    assert typescript["declaredType"] == "boolean" and typescript["optionalMember"] is True
    python = next(
        row["objectFacts"] for key, row in rows.items() if key.endswith("Request.enabled")
    )
    assert python["declaredType"] == "bool | None" and python["initializer"] == "None"


def test_member_annotations_exclude_strings_comments_and_unrelated_arguments(
    tmp_path: Path,
) -> None:
    (tmp_path / "Dto.java").write_text(
        """class Dto {
    @com.example.Nullable @JsonProperty(value = "enabled") Boolean enabled;
    String text = "@NotNull";
    /* @Nullable @JsonProperty("wrong") */ Boolean comment;
    @Notice("@NonNull") Boolean unrelated;
    @SerializedName(value = "external", alternate = {"legacy"}) String named;
}""",
        encoding="utf-8",
    )
    corpus = freeze(tmp_path, compiler_mode="off")
    with corpus.activate():
        resolved = resolve(observe(corpus))
    fields = {
        row["declarationName"]: row["objectFacts"]
        for packet in resolved.source_evidence.packets.values()
        for row in packet["entries"]
        if row.get("objectFacts")
    }
    assert fields["enabled"]["nullableEvidence"] == ["@com.example.Nullable"]
    assert fields["enabled"]["serializationName"] == "enabled"
    assert fields["named"]["serializationName"] == "external"
    for name in ("text", "comment", "unrelated"):
        assert fields[name]["nullableEvidence"] == []
        assert fields[name]["serializationName"] == ""


def test_native_signature_truncation_is_visible_in_published_evidence(tmp_path: Path) -> None:
    signature = "void accept(" + ", ".join(f"String value{index}" for index in range(100)) + ")"
    (tmp_path / "Long.java").write_text("class Long { " + signature + " {} }", encoding="utf-8")
    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    page = query_evidence(
        open_analysis(tmp_path, receipt.identity),
        EvidenceQuery(view="evidence", paths=("Long.java",), record_types=("sourceEntry",)),
    )
    entry = next(row for row in page.items if row.details.get("symbol") == "Long.accept")
    assert entry.details["signature"] == signature[:1000]
    assert entry.details["signatureOmittedCharacters"] == len(signature) - 1000
