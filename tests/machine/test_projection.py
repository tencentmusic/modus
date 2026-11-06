"""Authoring proposals preserve evidence ownership under bounded projection.

Fixtures distinguish explicit triggers from structural remainder so sampling
cannot attribute every signal to whichever capability happens to be first.
"""

from __future__ import annotations

from typing import Any, cast

from modus.machine.capability.contracts import CapabilityModel, CapabilitySlice
from modus.machine.projection.contracts import AuthoringProjection, ProjectionIntent
from modus.machine.projection.proposals import build_proposals, capability_first_scope


# 260 个入口刻意跨越两次页上限，覆盖末尾不足一页的余数。
# 候选拆分应完整保留入口身份，不能因分页重复或遗漏。
# needs-split 表示有界调查单元，不能伪称已识别的业务模块。
# 没有能力模型时仍须保留结构剩余项，避免分析空洞。
def test_oversized_remainder_is_split_into_bounded_investigation_units() -> None:
    entries: list[dict[str, Any]] = [
        {
            "entryId": f"entry-{index:04d}",
            "kind": "method",
            "entryRole": "action",
            "sourceRole": "runtime",
            "location": {
                "path": f"src/main/java/example/Service{index // 10}.java",
                "startLine": index + 1,
            },
        }
        for index in range(260)
    ]
    legacy_scope = {
        "candidates": [
            {
                "candidateId": "legacy-super-candidate",
                "partition": "main",
                "buildUnitId": "main",
                "coverageGapCount": 0,
                "files": sorted({entry["location"]["path"] for entry in entries}),
                "entries": entries,
            }
        ],
        "coverage": {},
    }

    result = capability_first_scope(
        legacy_scope,
        CapabilityModel(()),
        AuthoringProjection(ProjectionIntent.SCOPE, "a" * 64),
    )
    candidates = cast(list[dict[str, Any]], result["candidates"])
    published_entries = [
        entry["entryId"] for candidate in candidates for entry in candidate["entries"]
    ]

    assert len(candidates) == 3
    assert max(len(candidate["entries"]) for candidate in candidates) == 128
    assert len(published_entries) == len(set(published_entries)) == 260
    assert {candidate["disposition"] for candidate in candidates} == {"needs-split"}


# 宽范围旧候选的统计不能直接继承给其中一个能力。
# 分别布置入口所属文件与支持文件，要求按真实符号重新归属。
# 夸大的旧总数可揭露整桶复制，单一输入无法发现这类错误。
# 只有 orders 的入口属于该能力，support 的写效果不能被借用。
def test_structural_signal_totals_are_not_smeared_onto_one_capability() -> None:
    entry = {
        "entryId": "entry-orders",
        "kind": "method",
        "entryRole": "action",
        "sourceRole": "runtime",
        "symbol": "OrdersController.create",
        "location": {"path": "src/orders.py", "startLine": 10},
    }
    remainder = {
        "entryId": "entry-support",
        "kind": "method",
        "entryRole": "action",
        "sourceRole": "runtime",
        "symbol": "Support.run",
        "location": {"path": "src/support.py", "startLine": 20},
    }
    capability = CapabilitySlice(
        "cap-orders",
        "POST /orders",
        {"kind": "external-http"},
        entry,
    )
    model = CapabilityModel((capability,), seed_count=1)
    projection = build_proposals(model, baseline_digest="a" * 64)
    legacy_scope = {
        "candidates": [
            {
                "candidateId": "legacy-wide",
                "entries": [entry, remainder],
                "files": ["src/orders.py", "src/support.py"],
                "capabilitySignals": {
                    "entries": {"external-http": 40},
                    "effects": {"authoritative-write": 90},
                    "resources": {},
                    "unboundSignalCount": 0,
                },
            }
        ],
        "coverage": {},
    }

    result = capability_first_scope(
        legacy_scope,
        model,
        projection,
        authoring_records_by_path={
            "src/orders.py": [
                {
                    "kind": "entry",
                    "evidenceKind": "external-http",
                    "symbol": "OrdersController.create",
                    "entryId": "entry-orders",
                }
            ],
            "src/support.py": [
                {
                    "kind": "effect",
                    "evidenceKind": "authoritative-write",
                    "symbol": "Support.run",
                    "entryId": "entry-support",
                }
            ],
        },
    )
    capability_candidate = next(
        candidate for candidate in result["candidates"] if candidate["capabilityIds"]
    )

    assert capability_candidate["capabilitySignals"]["entries"] == {"external-http": 1}
    assert capability_candidate["capabilitySignals"]["effects"] == {}


# 对外触发比普通导出更适合作为创作入口。
# 将普通导出放在输入首位，证明输出优先级不依赖插入顺序。
# 这里保护排序策略，不要求为未观察到的副作用补造证据。
# 相同策略应适用于后续新增的显式触发类型。
def test_proposals_prioritize_explicit_triggers_over_public_exports() -> None:
    exported = CapabilitySlice(
        "cap-exported",
        "Library.call",
        {"kind": "public-export"},
        {"entryId": "entry-exported"},
    )
    endpoint = CapabilitySlice(
        "cap-endpoint",
        "POST /orders",
        {"kind": "external-http"},
        {"entryId": "entry-endpoint"},
    )

    projection = build_proposals(
        CapabilityModel((exported, endpoint), seed_count=2),
        baseline_digest="a" * 64,
    )

    assert projection.proposals[0].capability_ids == ("cap-endpoint",)


def test_shared_declaration_keeps_both_capability_owners() -> None:
    from modus.machine.capability.contracts import PathStep
    from modus.machine.projection.memberships import entry_memberships

    shared = PathStep("shared", "Shared.run", {"path": "shared.py"})
    slices = tuple(
        CapabilitySlice(f"cap-{name}", name, {}, {"entryId": name}, observed_entries=(shared,))
        for name in ("orders", "payments")
    )
    model = CapabilityModel(slices)
    projection = build_proposals(model, baseline_digest="a" * 64)
    scope = capability_first_scope({"candidates": []}, model, projection)
    memberships = entry_memberships(scope["candidates"], model)
    assert memberships["shared"].capability_ids == ("cap-orders", "cap-payments")
    assert len(memberships["shared"].candidate_ids) == 2


def test_signal_outside_or_between_ambiguous_declarations_stays_unbound() -> None:
    from modus.config import AuthoringRule, RuleEmit, RuleMatch
    from modus.machine.facts.rule_signals import project_authoring_records

    entries = [
        {"entryId": name, "symbol": name, "location": {"startLine": 2, "endLine": 2}}
        for name in ("first", "second")
    ]
    rows = project_authoring_records(
        "sample.py",
        "save()\nsave()\nsave()\n",
        (
            AuthoringRule(
                "test.write", RuleMatch(r"save"), RuleEmit("effect", "authoritative-write")
            ),
        ),
        entries=entries,
    )
    assert len(rows) == 3
    assert all("entryId" not in row and "symbol" not in row for row in rows)


def test_signals_bind_corresponding_declarations_but_preserve_context_ambiguity() -> None:
    from modus.config import AuthoringRule, RuleEmit, RuleMatch
    from modus.machine.facts.rule_signals import project_authoring_records

    syntax = {
        "entryId": "syntax-entry",
        "graphNodeId": "syntax",
        "symbol": "Service.save",
        "location": {"startLine": 1, "endLine": 1},
    }
    semantic = {
        **syntax,
        "entryId": "compiler-entry",
        "graphNodeId": "compiler",
        "analysisContextId": "main",
        "symbolId": "Service#save()",
        "correspondences": [{"role": "declaration", "syntaxGraphNodeId": "syntax"}],
    }
    rules = (
        AuthoringRule("test.write", RuleMatch("save"), RuleEmit("effect", "authoritative-write")),
    )

    def signals(entries):
        return project_authoring_records("Service.java", "save()", rules, entries=entries)

    assert signals([syntax, semantic])[0]["entryId"] == "syntax-entry"
    assert signals([semantic, syntax])[0]["entryId"] == "syntax-entry"
    # 同声明的不同构建上下文、重载冲突、未确认对应不能随意挑一项。
    for extra in (
        {**semantic, "entryId": "other", "analysisContextId": "test"},
        {**semantic, "entryId": "other", "symbolId": "Service#save(int)"},
        {**semantic, "entryId": "other", "correspondences": []},
    ):
        assert "entryId" not in signals([syntax, semantic, extra])[0]
