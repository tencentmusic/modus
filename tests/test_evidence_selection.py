"""Bounded evidence selection, drift detection, and continuation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from _support.analysis import bundle_path, sample_project
from modus.machine import (
    AnalysisOptions,
    EvidenceBudget,
    EvidenceQuery,
    analyze_repository,
    open_analysis,
    query_evidence,
)
from modus.machine.store.bundle import canonical_bytes


def test_many_diagnostics_leave_room_for_evidence_and_are_fully_pageable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modus.machine.store.bundle as storage
    from modus.machine.store.bundle_catalogs import service_catalog

    original = service_catalog

    def with_diagnostics(directory, services, snapshot, **kwargs):
        return original(
            directory,
            {
                **services,
                "coverageGaps": [
                    *services.get("coverageGaps", []),
                    *(
                        {
                            "code": "machine.facts.unresolved",
                            "provider": "java",
                            "buildUnitId": f"unit-{index}",
                            "subject": f"method-{index}",
                        }
                        for index in range(600)
                    ),
                ],
            },
            snapshot,
            **kwargs,
        )

    monkeypatch.setattr(storage, "_service_catalog", with_diagnostics)
    root = sample_project(tmp_path)
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(root, receipt.identity)
    first = query_evidence(bundle, EvidenceQuery(view="services"))
    assert first.items
    summary = next(
        gap
        for gap in first.coverage_gaps
        if gap.reason_code == "machine.packet.coverage-gap-summary"
    )
    details = cast(dict[str, Any], summary.details)
    assert details["totalCount"] >= 600
    assert details["reasonCounts"]["machine.facts.unresolved"] == 600
    assert details["expansionQuery"]["recordTypes"] == ["coverageGap"]
    seen: set[str] = set()
    cursors: set[str] = set()
    cursor = None
    while True:
        page = query_evidence(
            bundle,
            EvidenceQuery(
                view="services",
                record_types=("coverageGap",),
                cursor=cursor,
                budget=EvidenceBudget(max_bytes=16 * 1024, max_items=23),
            ),
        )
        assert not page.items
        assert len(canonical_bytes(page.to_dict())) <= 16 * 1024
        assert len(page.coverage_gaps) <= 23
        for gap in page.coverage_gaps:
            assert gap.record_id not in seen
            seen.add(gap.record_id)
        cursor = page.next_cursor
        if cursor is None:
            break
        assert page.coverage_gaps and cursor not in cursors
        cursors.add(cursor)
    assert len(seen) >= 600


# 构造足够多的源码强制形成多页，避免单页夹具无法观察惰性读取。
# 打开 bundle 仅校验根承诺，选取具体证据才读取对应数据页。
# 统计实际加载路径而非耗时，使性能边界可确定地验证。
# 多个不相交范围共享一次根读取，防止按范围重复全树扫描。
# 故意损坏无关页，证明范围查询不会无意读取全部数据。
# 被访问页面仍由加载器校验摘要，惰性不代表放松完整性检查。
def test_open_authenticates_roots_without_reading_unrelated_data_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import modus.machine.store.catalog as catalog

    root = tmp_path / "project"
    root.mkdir()
    for index in range(180):
        (root / f"service_{index:03d}.py").write_text(
            f"def operation_{index}():\n    return {index}\n", encoding="utf-8"
        )
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    data_pages = list(bundle_path(root, receipt.bundle_digest).glob("evidence/_data/*.json"))
    assert 1 < len(data_pages) < 180

    opened: list[str] = []
    original = catalog.load_document

    def count_load(directory: Path, relative: str, *, expected_digest: str):
        opened.append(relative)
        return original(directory, relative, expected_digest=expected_digest)

    monkeypatch.setattr(catalog, "load_document", count_load)
    bundle = open_analysis(root, receipt.identity)
    assert not any("/_data/" in path for path in opened)
    query_evidence(bundle, EvidenceQuery(view="evidence", paths=("service_000.py",)))
    touched_data_pages = {path for path in opened if "/_data/" in path}
    assert touched_data_pages
    assert len(touched_data_pages) < len(data_pages)

    from modus.machine.store.bundle import load_catalog_ranges

    opened.clear()
    load_catalog_ranges(
        bundle,
        "evidence",
        ranges=(
            ("file:service_000.py", "file:service_000.py\U0010ffff"),
            ("file:service_179.py", "file:service_179.py\U0010ffff"),
        ),
    )
    assert opened.count("evidence/index.json") == 1
    untouched = next(
        path
        for path in data_pages
        if path.relative_to(bundle._directory).as_posix() not in touched_data_pages
    )
    untouched.write_bytes(canonical_bytes({"schemaVersion": 1, "tampered": True}))
    reopened = open_analysis(root, receipt.identity)
    assert query_evidence(reopened, EvidenceQuery(view="evidence", paths=("service_000.py",))).items


# 翻页期间源码可能变化，游标不能承诺当前文件仍等于冻结版本。
# 变化的证据转换为覆盖缺口，避免将旧内容冒充当前事实。
# 检查每个缺口的稳定原因码，使消费者可要求重新分析。
# 保留分页流程，验证重检发生在第二次选择而非仅打开 bundle 时。
def test_selection_rechecks_source_drift_between_pages(tmp_path: Path) -> None:
    root = sample_project(tmp_path)
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(root, receipt.identity)
    first = query_evidence(
        bundle,
        EvidenceQuery(view="evidence", budget=EvidenceBudget(max_items=1)),
    )
    assert first.next_cursor
    (root / "orders.py").write_text("# changed between pages\n", encoding="utf-8")
    second = query_evidence(
        bundle,
        EvidenceQuery(
            view="evidence",
            budget=EvidenceBudget(max_items=4),
            cursor=first.next_cursor,
        ),
    )
    assert second.coverage_gaps
    assert any(
        gap.reason_code == "machine.packet.source-changed-after-analysis"
        or cast(dict[str, Any], gap.details.get("reasonCounts", {})).get(
            "machine.packet.source-changed-after-analysis", 0
        )
        for gap in second.coverage_gaps
    )
    assert {gap.reason_code for gap in second.coverage_gaps} <= {
        "machine.packet.source-changed-after-analysis",
        "machine.corpus.input-not-admitted",
        "machine.packet.coverage-gap-summary",
    }


# 条目数与字节数是两个同时生效的预算，任何一项都不能超限。
# 完整遍历游标后核对记录身份，覆盖分页边界的丢失和重复。
# 覆盖缺口同样占用记录预算，不应成为无限大小的旁路。
# 先要求有结果，防止全部过滤掉的空实现通过唯一性断言。
# 使用规范序列化字节作为线协议预算依据。
def test_selection_pages_complete_records_without_loss_or_duplicates(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "many.py").write_text(
        "\n\n".join(f"def operation_{index}():\n    return {index}" for index in range(20)),
        encoding="utf-8",
    )
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(root, receipt.identity)

    cursor: str | None = None
    seen: list[str] = []
    while True:
        result = query_evidence(
            bundle,
            EvidenceQuery(
                view="evidence",
                budget=EvidenceBudget(max_bytes=16 * 1024, max_items=3),
                cursor=cursor,
            ),
        )
        payload = canonical_bytes(result.to_dict())
        records = (*result.items, *result.coverage_gaps)
        assert len(payload) <= 16 * 1024
        assert len(records) <= 3
        seen.extend(item.record_id for item in records)
        cursor = result.next_cursor
        if cursor is None:
            break

    assert seen
    assert len(seen) == len(set(seen))


# 游标绑定选择语义，不绑定显示预算，因此下一页可更改页大小。
# 路径与证据类型改变会选择另一集合，必须拒绝旧游标。
# 先成功续读再检查失败，避免一个总是报错的实现通过测试。
# 失配错误码保护调用者明确重启查询的能力。
# 两个不同过滤轴都受保护，避免只把 view 名称放入游标摘要。
def test_cursor_is_bound_to_query_and_page_size_may_change(tmp_path: Path) -> None:
    root = sample_project(tmp_path)
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(root, receipt.identity)
    first = query_evidence(
        bundle,
        EvidenceQuery(
            view="evidence",
            budget=EvidenceBudget(max_bytes=32 * 1024, max_items=1),
        ),
    )
    assert first.next_cursor
    second = query_evidence(
        bundle,
        EvidenceQuery(
            view="evidence",
            budget=EvidenceBudget(max_bytes=64 * 1024, max_items=4),
            cursor=first.next_cursor,
        ),
    )
    assert second.items or second.coverage_gaps
    with pytest.raises(ValueError, match="cursor-query-mismatch"):
        query_evidence(
            bundle,
            EvidenceQuery(
                view="evidence",
                paths=("orders.py",),
                cursor=first.next_cursor,
            ),
        )
    with pytest.raises(ValueError, match="cursor-query-mismatch"):
        query_evidence(
            bundle,
            EvidenceQuery(
                view="evidence",
                evidence_kinds=("transaction",),
                cursor=first.next_cursor,
            ),
        )


# 默认范围视图只返回摘要，详细成员需要显式候选选择。
# 全局分区统计应与入口角色统计守恒，不按页内抽样推断总数。
# 代表入口有固定上限，保证首屏可读且不携带全量源码。
# 代表项同时包含位置、摘要、精度与来源，让读者判断证据强度。
# 候选摘要保留结构依据和缺口信息，避免只给一个不透明分数。
# 定向查询再出现 candidateMember，保护摘要与详情的责任边界。
def test_scope_summary_expands_only_for_an_explicit_candidate(tmp_path: Path) -> None:
    root = sample_project(tmp_path)
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(root, receipt.identity)
    summary = query_evidence(bundle, EvidenceQuery(view="scope"))
    record_types = {str(item.details.get("recordType")) for item in summary.items}
    assert record_types <= {"scopeSummary", "candidateSummary"}
    global_summary = next(
        item for item in summary.items if item.details.get("recordType") == "scopeSummary"
    )
    assert global_summary.details["partitionCount"] == len(
        cast(dict[str, int], global_summary.details["partitionCandidateCounts"])
    )
    assert sum(cast(dict[str, int], global_summary.details["partitionEntryCounts"]).values()) == (
        cast(int, global_summary.details["actionEntryCount"])
        + cast(int, global_summary.details["declarationEntryCount"])
    )
    assert cast(dict[str, int], global_summary.details["entryKindCounts"])
    action_kinds = cast(dict[str, int], global_summary.details["actionEntryKindCounts"])
    assert action_kinds
    assert sum(action_kinds.values()) == global_summary.details["actionEntryCount"]
    assert isinstance(global_summary.details["entrySignalCounts"], dict)
    candidate = next(
        str(item.details["candidateId"])
        for item in summary.items
        if item.details.get("recordType") == "candidateSummary"
    )
    candidate_summary = next(
        item for item in summary.items if item.details.get("recordType") == "candidateSummary"
    )
    assert {
        "structuralBasis",
        "inventory",
        "capabilitySignals",
        "representativeEntries",
        "coverageGapCount",
    } <= set(candidate_summary.details)
    representative_entries = candidate_summary.details["representativeEntries"]
    assert isinstance(representative_entries, list) and 0 < len(representative_entries) <= 6
    representative = representative_entries[0]
    assert isinstance(representative, dict)
    assert {
        "displayName",
        "symbol",
        "signature",
        "route",
        "contracts",
        "path",
        "sourceDigest",
        "resolution",
        "sourceLayer",
    } <= set(representative)
    detail = query_evidence(bundle, EvidenceQuery(view="scope", candidate_ids=(candidate,)))
    assert any(item.details.get("recordType") == "candidateMember" for item in detail.items)


# 一个 Java 夹具同时包含入口、事务、缓存、存储、状态和消息信号。
# 同文件不等于同所有者，每条信号仍要携带真实符号见证。
# 过滤使用稳定 evidenceKind，不能依赖人类展示名称。
# 关闭编译器测试结构观察可独立提供的有界信号。
# 类别集合断言验证覆盖，所有见证断言验证归属完整性。
# 不要求推断不存在的运行时调用结果，避免提高证据精度。
def test_authoring_signals_are_filterable_and_bound_to_real_owner_symbols(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    source = root / "src/main/java/example/OrderController.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
package example;

@Table(name = "orders")
class OrderController {
    enum OrderStatus { CREATED, PAID }

    @OpenApiPostMapping(apiName = "创建订单", apiUrl = "/orders")
    @Transactional
    public OrderDto create(OrderRequest request) {
        cache.put(request.id(), request);
        repository.save(request);
        return new OrderDto();
    }

    @KafkaListener(topic = "orders.created")
    public void consume(OrderEvent event) {}
}
""".lstrip(),
        encoding="utf-8",
    )
    receipt = analyze_repository(root, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(root, receipt.identity)
    result = query_evidence(
        bundle,
        EvidenceQuery(
            view="evidence",
            paths=("src/main/java/example/OrderController.java",),
            record_types=("authoringSignal",),
            evidence_kinds=(
                "external-http",
                "transaction",
                "authoritative-write",
                "cache",
                "table",
                "state",
                "mq",
                "topic",
            ),
        ),
    )
    kinds = {str(item.details.get("evidenceKind")) for item in result.items}
    assert {
        "external-http",
        "transaction",
        "authoritative-write",
        "cache",
        "table",
        "state",
        "mq",
        "topic",
    } <= kinds
    assert all(item.witness and item.witness.symbol for item in result.items)
