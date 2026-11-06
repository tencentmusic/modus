"""通过真实分析包验证上下文的范围、来源、预算与可恢复查询。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from modus.cli import app
from modus.machine import (
    AnalysisOptions,
    ContextRequest,
    ContractError,
    EvidenceQuery,
    PacketBudget,
    PacketScope,
    TaskIntent,
    analyze_repository,
    build_authoring_context,
    open_analysis,
    query_evidence,
)
from modus.machine.packet.context_budget import fit_context_budget
from modus.machine.store.contracts import AnalysisBundle
from modus.paths import ModusPaths


def _bundle(root: Path, *, multiple: bool = False) -> AnalysisBundle:
    # 结构解析使夹具独立于本机 Java 工具链；多步路径用于验证原子裁剪。
    for name in ("Order", "Stock") if multiple else ("Order",):
        (root / f"{name}Controller.java").write_text(
            f"""class {name}Controller {{
 @OpenApiPostMapping(apiName = "Create", apiUrl = "/{name.lower()}")
 public void create() {{ stageA(); }}
 private void stageA() {{ stageB(); }}
 private void stageB() {{ stageC(); }}
 private void stageC() {{ persist(); }}
 private void persist() {{ repository.save(item); }}
}}
""",
            encoding="utf-8",
        )
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    return open_analysis(root, receipt.identity)


def _validate(packet: object) -> None:
    schema = json.loads(
        (
            Path(__file__).parents[2] / "schemas/machine/authoring-context-packet.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(packet)


def test_scope_packet_leads_with_capabilities_and_precise_handles(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    packet = build_authoring_context(bundle, ContextRequest(TaskIntent.SCOPE_DISCOVERY))
    payload = packet.to_dict()

    assert payload["schemaVersion"] == 1
    assert payload["bundleDigest"] == bundle.bundle_digest
    assert payload["baselineDigest"] == bundle.baseline_digest
    assert payload["requestedScope"] == {
        "candidateIds": [],
        "capabilityIds": [],
        "boundaryIds": [],
        "paths": [],
        "symbols": [],
    }
    assert payload["proposals"][0]["disposition"] == "proposed"
    assert payload["capabilities"][0]["capabilityId"].startswith("cap-")
    assert payload["capabilities"][0]["evidenceTiers"] == {"T2": 1}
    assert payload["capabilities"][0]["degradationReasons"] == ["machine.facts.compiler-disabled"]
    assert payload["proposals"][0]["coverageReceipts"][0]["completeness"] == "partial"
    assert payload["representativePaths"][0]["sourceSymbol"] == "OrderController.create"
    assert payload["terminalEffects"][0]["kind"] == "data-write"
    assert any(handle["kind"] == "capability" for handle in payload["expansionHandles"])
    assert "nextCursor" not in json.dumps(payload)
    _validate(payload)
    published = ModusPaths.for_root(tmp_path).analysis_bundles_dir / bundle.bundle_digest
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(published.rglob("*.json"))
    )
    assert str(tmp_path) not in serialized
    assert str(Path.home()) not in serialized


def test_packet_budget_trims_content_and_reports_omissions(tmp_path: Path) -> None:
    budget = PacketBudget(max_items=2, max_bytes=4_096, max_paths_per_capability=1)
    bundle = _bundle(tmp_path)
    discovery = build_authoring_context(bundle, ContextRequest(TaskIntent.SCOPE_DISCOVERY))
    candidate_id = str(discovery.proposals[0]["proposalId"])
    packet = build_authoring_context(
        bundle,
        ContextRequest(
            TaskIntent.MODULE_AUTHORING,
            scope=PacketScope(candidate_ids=(candidate_id,)),
            budget=budget,
        ),
    )
    encoded = json.dumps(
        packet.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()

    assert len(encoded) <= budget.max_bytes
    assert packet.omitted_counts
    assert packet.coverage_receipts[0].completeness == "partial"
    assert packet.coverage_receipts[0].reason_code == "machine.packet.budget-exhausted"
    _validate(packet.to_dict())
    counts = packet.coverage_receipts[0].counts
    assert counts["authoringSignals"] == sum(
        len(row.get("authoringSignals", [])) for row in packet.proposals
    )
    assert counts["navigationSteps"] == len(packet.representative_paths)
    assert counts["evidence"] == len(packet.evidence)
    assert packet.expansion_queries
    assert all("_" not in key for key in packet.omitted_counts)


# 模块创作需要显式范围，缺失选择器不能退化成整个仓库。
def test_module_authoring_rejects_an_unbounded_request() -> None:
    with pytest.raises(ContractError, match="machine.packet.module-scope-required"):
        ContextRequest(TaskIntent.MODULE_AUTHORING)


def test_budget_removes_whole_paths_without_mutating_the_input(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    packet = build_authoring_context(
        bundle,
        ContextRequest(TaskIntent.MODULE_AUTHORING, PacketScope(paths=("OrderController.java",))),
    )
    original = packet.to_dict()
    path_count = len(
        {(row["capabilityId"], row["pathIndex"]) for row in packet.representative_paths}
    )
    assert path_count and len(packet.representative_paths) >= 4

    fitted = fit_context_budget(packet, PacketBudget(max_items=1))

    assert packet.to_dict() == original
    assert not fitted.representative_paths
    assert (
        fitted.omitted_counts["representativePaths"]
        == packet.omitted_counts.get("representativePaths", 0) + path_count
    )
    assert fitted.omitted_counts["navigationSteps"] == len(packet.representative_paths)
    assert fitted.coverage_receipts[0].counts["representativePaths"] == 0
    assert fitted.coverage_receipts[0].counts["navigationSteps"] == 0


def test_module_authoring_packet_keeps_scoped_signals_with_provenance(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    discovery = build_authoring_context(
        bundle,
        ContextRequest(TaskIntent.SCOPE_DISCOVERY),
    )
    candidate_id = str(discovery.proposals[0]["proposalId"])

    packet = build_authoring_context(
        bundle,
        ContextRequest(
            TaskIntent.MODULE_AUTHORING,
            scope=PacketScope(candidate_ids=(candidate_id,)),
        ),
    )
    payload = packet.to_dict()
    proposal = payload["proposals"][0]
    signals = proposal["authoringSignals"]
    kinds = {signal["details"]["evidenceKind"] for signal in signals}

    assert {"external-http", "authoritative-write"} <= kinds
    assert payload["requestedScope"]["candidateIds"] == [candidate_id]
    assert payload["bundleDigest"] == bundle.bundle_digest
    assert payload["representativePaths"]
    assert payload["coverageReceipt"][0]["counts"]["authoringSignals"] == len(signals)
    assert all(signal["resolution"] and signal["sourceLayer"] for signal in signals)
    assert all(signal["witness"]["path"] == "OrderController.java" for signal in signals)
    assert any(handle["kind"] == "path" for handle in payload["expansionHandles"])


def test_module_authoring_can_derive_proposal_from_a_source_path(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    packet = build_authoring_context(
        bundle,
        ContextRequest(
            TaskIntent.MODULE_AUTHORING,
            scope=PacketScope(paths=("OrderController.java",)),
        ),
    )

    assert packet.proposals
    assert packet.proposals[0]["authoringSignals"]
    assert not any(
        ambiguity.get("marker") == "unbound-authoring-signal" for ambiguity in packet.ambiguities
    )


def test_capability_expansion_handle_is_a_direct_module_selector(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    discovery = build_authoring_context(bundle, ContextRequest(TaskIntent.SCOPE_DISCOVERY))
    capability_id = str(discovery.capabilities[0]["capabilityId"])

    packet = build_authoring_context(
        bundle,
        ContextRequest(
            TaskIntent.MODULE_AUTHORING,
            scope=PacketScope(capability_ids=(capability_id,)),
        ),
    )

    assert packet.proposals
    assert packet.proposals[0]["authoringSignals"]
    assert packet.to_dict()["requestedScope"]["capabilityIds"] == [capability_id]


def test_internal_context_cli_returns_packet_without_cursor_protocol(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "internal",
            "init-analysis",
            "context",
            "--root",
            str(tmp_path),
            "--bundle-digest",
            bundle.bundle_digest,
            "--baseline-digest",
            bundle.baseline_digest,
            "--intent",
            "scope-discovery",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["recordKind"] == "authoring-context-packet"
    assert payload["intent"] == "scope-discovery"
    assert "nextCursor" not in payload


def test_internal_context_cli_reports_unbounded_module_authoring_as_contract_error(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "internal",
            "init-analysis",
            "context",
            "--root",
            str(tmp_path),
            "--bundle-digest",
            bundle.bundle_digest,
            "--baseline-digest",
            bundle.baseline_digest,
            "--intent",
            "module-authoring",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "machine.packet.module-scope-required"
    assert payload["error"]["details"]["requiredAnyOf"] == [
        "candidateIds",
        "capabilityIds",
        "paths",
        "symbols",
    ]


@pytest.mark.parametrize("intent", list(TaskIntent))
@pytest.mark.parametrize("selector", ["path", "symbol"])
def test_source_selectors_are_real_queries(
    tmp_path: Path, intent: TaskIntent, selector: str
) -> None:
    bundle = _bundle(tmp_path, multiple=True)
    scope = (
        PacketScope(paths=("OrderController.java",))
        if selector == "path"
        else PacketScope(symbols=("OrderController.create",))
    )
    packet = build_authoring_context(bundle, ContextRequest(intent, scope))
    _validate(packet.to_dict())
    # 本夹具无服务拓扑，空服务包是合法 no-match；其余意图都有真实证据。
    if intent is not TaskIntent.SERVICE_BOUNDARY:
        assert packet.proposals or packet.evidence or packet.terminal_effects
        assert packet.coverage_receipts[0].completeness != "unavailable"
    assert packet.requested_scope == scope
    assert packet.expansion_queries


@pytest.mark.parametrize("intent", list(TaskIntent))
def test_unknown_capability_never_leaks_other_scopes(tmp_path: Path, intent: TaskIntent) -> None:
    bundle = _bundle(tmp_path, multiple=True)
    scope = PacketScope(capability_ids=("cap-missing",))
    packet = build_authoring_context(bundle, ContextRequest(intent, scope))
    assert not packet.proposals and not packet.evidence and not packet.ambiguities
    assert not packet.source_anchors
    assert packet.coverage_receipts[0].completeness == "unavailable"


def test_unmatched_service_symbol_does_not_return_global_summary(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, multiple=True)
    scope = PacketScope(symbols=("MissingService.handle",))
    page = query_evidence(bundle, EvidenceQuery(view="services", symbols=scope.symbols))
    assert not page.items
    packet = build_authoring_context(bundle, ContextRequest(TaskIntent.SERVICE_BOUNDARY, scope))
    assert not packet.proposals and not packet.evidence
    assert packet.coverage_receipts[0].completeness == "unavailable"


@pytest.mark.parametrize(
    "intent", [intent for intent in TaskIntent if intent is not TaskIntent.SERVICE_BOUNDARY]
)
def test_source_drift_survives_context_packaging(tmp_path: Path, intent: TaskIntent) -> None:
    bundle = _bundle(tmp_path, multiple=True)
    source = tmp_path / "OrderController.java"
    source.write_text("// changed\n" + source.read_text())
    packet = build_authoring_context(
        bundle, ContextRequest(intent, PacketScope(paths=(source.name,)))
    )
    assert packet.coverage_gaps
    assert any(
        gap["reasonCode"] == "machine.packet.source-changed-after-analysis"
        for gap in packet.coverage_gaps
    )
    assert packet.coverage_receipts[0].completeness == "partial"
    assert not packet.proposals and not packet.evidence and not packet.representative_paths


def test_audit_keeps_inventory_entries_relations_and_gaps(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, multiple=True)
    packet = build_authoring_context(
        bundle,
        ContextRequest(TaskIntent.COVERAGE_AUDIT, PacketScope(paths=("OrderController.java",))),
    )
    assert {"sourceFile", "sourceEntry", "sourceRelation"} <= {
        row["details"]["recordType"] for row in packet.evidence
    }
    assert packet.coverage_gaps  # 动态 repository 调用未解析，不能被记录类型筛选抹去。
    assert all(
        gap["reasonCode"] != "machine.store.invalid-coverage-reason" for gap in packet.coverage_gaps
    )
    assert packet.coverage_receipts[0].completeness == "partial"
    assert all(row["witness"]["path"] == "OrderController.java" for row in packet.evidence)
    replay = next(row for row in packet.expansion_queries if row["recordTypes"] == ["sourceFile"])
    assert query_evidence(
        bundle,
        EvidenceQuery(
            view=replay["view"],
            paths=tuple(replay["paths"]),
            record_types=tuple(replay["recordTypes"]),
        ),
    ).items


def test_colocated_signals_survive_storage_and_all_authoring_intents(tmp_path: Path) -> None:
    # 一行内的锁、数据保存与消息发送分别影响规则、状态和协作说明。
    # 只按行号和 effect 去重会把前三项压成最后一个 send，且没有缺口提示。
    (tmp_path / "OrderController.java").write_text(
        """class OrderController {
 @OpenApiPostMapping(apiName = "Create", apiUrl = "/orders")
 public void create() { lock(); repository.save(order); publisher.send(event); }
}
""",
        encoding="utf-8",
    )
    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(tmp_path, receipt.identity)
    scope = PacketScope(paths=("OrderController.java",))
    page = query_evidence(
        bundle,
        EvidenceQuery(view="evidence", paths=scope.paths, record_types=("authoringSignal",)),
    )
    expected = {("lock", "lock("), ("authoritative-write", "save"), ("authoritative-write", "send")}
    effects = [row for row in page.items if row.to_dict()["kind"] == "effect"]
    assert {(row.details["evidenceKind"], row.details["value"]) for row in effects} == expected
    assert len({row.record_id for row in effects}) == len(expected)
    for intent in (
        TaskIntent.MODULE_AUTHORING,
        TaskIntent.CONSTRAINT_EXTRACTION,
        TaskIntent.COVERAGE_AUDIT,
    ):
        packet = build_authoring_context(bundle, ContextRequest(intent, scope))
        _validate(packet.to_dict())
        signals = [
            signal
            for proposal in packet.proposals
            for signal in proposal.get("authoringSignals", [])
        ]
        flat_signals = [
            row for row in packet.terminal_effects if row.get("recordType") == "authoringSignal"
        ]
        details = [signal["details"] for signal in signals] + flat_signals
        assert expected <= {(row.get("evidenceKind"), row.get("value")) for row in details}
        delivered_ids = {row["recordId"] for row in (*signals, *flat_signals)}
        assert {row.record_id for row in effects} <= delivered_ids


def test_unbound_configuration_signal_is_included_in_delivery_count(tmp_path: Path) -> None:
    (tmp_path / "settings.py").write_text('import os\nTIMEOUT = os.getenv("TIMEOUT")\n')
    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(tmp_path, receipt.identity)
    packet = build_authoring_context(
        bundle,
        ContextRequest(
            TaskIntent.MODULE_AUTHORING,
            PacketScope(paths=("settings.py",)),
            PacketBudget(low_resolution_quota=0),
        ),
    )
    signals = [
        row["signal"]
        for row in packet.ambiguities
        if row.get("marker") == "unbound-authoring-signal"
    ]
    assert len(signals) == 1 and signals[0]["details"]["evidenceKind"] == "config"
    assert packet.coverage_receipts[0].counts["authoringSignals"] == 1
    assert packet.coverage_receipts[0].completeness == "partial"
    _validate(packet.to_dict())


def test_provenance_and_whole_paths_survive_one_path_quota(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, multiple=True)
    discovery = build_authoring_context(bundle, ContextRequest(TaskIntent.SCOPE_DISCOVERY))
    cap = next(row["capabilityId"] for row in discovery.capabilities)
    packet = build_authoring_context(
        bundle,
        ContextRequest(
            TaskIntent.MODULE_AUTHORING,
            PacketScope(capability_ids=(cap,)),
            PacketBudget(max_paths_per_capability=1),
        ),
    )
    assert len(packet.representative_paths) >= 4
    assert [row["stepIndex"] for row in packet.representative_paths] == list(
        range(len(packet.representative_paths))
    )
    assert packet.representative_paths[-1]["terminal"]
    for row in packet.representative_paths:
        assert row["recordId"] and row["witness"] and row["resolution"] and row["sourceLayer"]
    constraints = build_authoring_context(
        bundle, ContextRequest(TaskIntent.CONSTRAINT_EXTRACTION, PacketScope(capability_ids=(cap,)))
    )
    for row in (
        *constraints.proposals,
        *constraints.terminal_effects,
        *constraints.authoritative_objects,
    ):
        assert row["recordId"] and row["witness"] and row["resolution"] and row["sourceLayer"]


def test_mixed_selector_axes_intersect_and_domain_union_is_explicit(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, multiple=True)
    discovery = build_authoring_context(bundle, ContextRequest(TaskIntent.SCOPE_DISCOVERY))
    candidate = next(
        row["proposalId"]
        for row in discovery.proposals
        if row["capabilityIds"]
        and any(
            entry.get("path") == "OrderController.java" for entry in row["representativeEntries"]
        )
    )
    a = query_evidence(bundle, EvidenceQuery(view="evidence", candidate_ids=(candidate,)))
    b = query_evidence(bundle, EvidenceQuery(view="evidence", paths=("StockController.java",)))
    mixed = query_evidence(
        bundle,
        EvidenceQuery(view="evidence", candidate_ids=(candidate,), paths=("StockController.java",)),
    )
    assert a.items and b.items and not mixed.items
    assert {row.witness.path for row in (*a.items, *b.items) if row.witness} == {
        "OrderController.java",
        "StockController.java",
    }


def test_service_context_keeps_outgoing_incoming_and_projection_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modus.machine.projection import lifecycle

    def topology_fixture(*args: object, **kwargs: object) -> dict[str, object]:
        # 确定的上游拓扑夹具，后续 N5/N6 仍实际发布、认证和查询。
        return {
            "baselineDigest": kwargs["baseline_digest"],
            "nodes": [
                {
                    "id": "order",
                    "kind": "service",
                    "sourceAnchors": [{"path": "OrderController.java"}],
                },
                {
                    "id": "stock",
                    "kind": "service",
                    "sourceAnchors": [{"path": "StockController.java"}],
                },
            ],
            "edges": [
                {
                    "id": "reserve",
                    "source": "order",
                    "target": "stock",
                    "relation": "calls",
                    "resolution": "candidate",
                    "sourceLayer": "reconciled",
                    "witness": {"path": "OrderController.java", "startLine": 3},
                }
            ],
            "coverageGaps": [
                {
                    "reasonCode": "machine.projection.service-relation-without-witness",
                    "relationId": "unknown",
                }
            ],
        }

    monkeypatch.setattr(lifecycle, "project_services", topology_fixture)
    bundle = _bundle(tmp_path, multiple=True)
    for scope in (
        PacketScope(),
        PacketScope(boundary_ids=("order",)),
        PacketScope(boundary_ids=("stock",)),
        PacketScope(paths=("OrderController.java",)),
    ):
        packet = build_authoring_context(bundle, ContextRequest(TaskIntent.SERVICE_BOUNDARY, scope))
        relations = [
            row for row in packet.evidence if row["details"]["recordType"] == "serviceRelation"
        ]
        assert len(relations) == 1
        assert (
            relations[0]["details"]["source"] == "order"
            and relations[0]["details"]["target"] == "stock"
        )
        assert (
            relations[0]["resolution"] == "candidate"
            and relations[0]["witness"]["path"] == "OrderController.java"
        )
        _validate(packet.to_dict())
        if not scope.boundary_ids and not scope.paths:
            assert packet.coverage_gaps and packet.coverage_receipts[0].completeness == "partial"
    (tmp_path / "OrderController.java").write_text("// changed")
    stale = build_authoring_context(
        bundle, ContextRequest(TaskIntent.SERVICE_BOUNDARY, PacketScope(boundary_ids=("stock",)))
    )
    assert stale.coverage_gaps and not stale.evidence


@pytest.mark.parametrize(
    "intent", [item for item in TaskIntent if item is not TaskIntent.SERVICE_BOUNDARY]
)
def test_boundary_filter_rejects_unsupported_intents(intent: TaskIntent) -> None:
    with pytest.raises(ContractError, match="machine.packet.unsupported-boundary-filter"):
        ContextRequest(intent, PacketScope(paths=("orders.py",), boundary_ids=("missing",)))


@pytest.mark.parametrize("view", ["scope", "evidence"])
def test_boundary_filter_rejects_unsupported_views(view: str) -> None:
    with pytest.raises(ContractError, match="machine.packet.unsupported-boundary-filter"):
        EvidenceQuery(view=view, boundary_ids=("missing",))  # type: ignore[arg-type]


def test_same_file_capabilities_keep_their_own_signals_and_unsampled_branches(
    tmp_path: Path,
) -> None:
    source = tmp_path / "OrderController.java"
    source.write_text(
        """class OrderController {
 @OpenApiPostMapping(apiName = "Create", apiUrl = "/create")
 public void create() { a(); b(); c(); d(); e(); }
 @OpenApiDeleteMapping(apiName = "Delete", apiUrl = "/delete")
 public void remove() { repository.delete(item); }
 private void a() { repository.save(a); }
 private void b() { repository.save(b); }
 private void c() { repository.save(c); }
 private void d() { repository.save(d); }
 private void e() { repository.save(e); }
}
""",
        encoding="utf-8",
    )
    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(tmp_path, receipt.identity)
    discovery = build_authoring_context(bundle, ContextRequest(TaskIntent.SCOPE_DISCOVERY))
    for name, allowed, forbidden in (
        ("OrderController.create", {"/create", "save"}, {"/delete", "delete"}),
        ("OrderController.remove", {"/delete", "delete"}, {"/create", "save"}),
    ):
        proposal = next(
            row
            for row in discovery.proposals
            if any(entry["symbol"] == name for entry in row["representativeEntries"])
        )
        packet = build_authoring_context(
            bundle,
            ContextRequest(
                TaskIntent.MODULE_AUTHORING,
                PacketScope(capability_ids=tuple(proposal["capabilityIds"])),
            ),
        )
        signals = [signal for row in packet.proposals for signal in row["authoringSignals"]]
        values = " ".join(str(signal["details"].get("value", "")) for signal in signals)
        assert all(value in values for value in allowed)
        assert all(value not in values for value in forbidden)
        if name.endswith("create"):
            symbols = {signal["witness"]["symbol"] for signal in signals}
            assert {f"OrderController.{method}" for method in "abcde"} <= symbols
        _validate(packet.to_dict())
