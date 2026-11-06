"""Catalog validation, bounded reads, and bundle commitments."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from modus.machine.errors import BudgetError, ContractError, IntegrityError
from modus.machine.store import bundle as bundle_store
from modus.machine.store import catalog
from modus.machine.store.bundle_catalogs import service_catalog
from modus.machine.store.catalog import CatalogRecord
from modus.machine.store.contracts import (
    CATALOG_MAX_BYTES,
    CATALOG_MAX_ITEMS,
    AnalysisIdentity,
    AnalysisOptions,
    EvidenceBudget,
    EvidenceQuery,
    JsonObject,
    Witness,
)
from modus.paths import ModusPaths


# 断言稳定原因码，避免多个校验分支都抛异常却检查错了边界。
# 展示文本可以改进，消费者依赖的错误分类不能漂移。
# 所有存储校验都应在可信读取边界失败，不能继续发布部分认证的内容。
# 共同断言保持错误码精确，方便新增损坏场景复用。
def _assert_integrity(
    code: str, function: Callable[..., object], *args: object, **kwargs: object
) -> None:
    with pytest.raises(IntegrityError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code


# 最小单记录信封作为合法基线，坏输入只修改一个目标字段。
def _record_document() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "catalog": "evidence",
        "nodeType": "record",
        "key": "a",
        "recordCount": 1,
        "value": {},
    }


def test_service_catalog_preserves_diagnostic_identity_and_real_sources(tmp_path: Path) -> None:
    diagnostics = [
        {
            "code": "machine.facts.unresolved",
            "provider": "java",
            "buildUnitId": f"unit-{index}",
            "subject": f"symbol-{index}",
        }
        for index in range(140)
    ]
    reference = service_catalog(
        tmp_path,
        {
            "nodes": [
                {"id": "unknown", "kind": "repository", "qualifiedName": "acme.Project"},
                {
                    "id": "declared",
                    "kind": "component",
                    "qualifiedName": "acme.Service",
                    "displayName": "合同服务",
                    "sourceAnchors": [{"file": "Service.java", "line": 3}],
                },
                {
                    "id": "dynamic",
                    "kind": "table",
                    "qualifiedName": "dynamic-table",
                    "sourceAnchors": [{"file": "Service.java", "line": 7}],
                    "attributes": {"dynamic": True, "sourceBasis": "relation"},
                },
                {
                    "id": "configured",
                    "kind": "service",
                    "qualifiedName": "declared-service",
                    "sourceAnchors": [{"file": "service.yaml", "line": 2}],
                },
            ],
            "edges": [
                {
                    "id": "derived",
                    "from": "declared",
                    "to": "dynamic",
                    "relation": "writes",
                    "callSite": {"file": "Service.java", "line": 7},
                },
            ],
            "coverageGaps": [*diagnostics, diagnostics[0]],
        },
        {
            "sources": [
                {"path": ".cursorrules", "sha256": "a" * 64},
                {"path": "Service.java", "sha256": "b" * 64},
                {"path": "service.yaml", "sha256": "c" * 64, "role": "configuration"},
            ]
        },
    )
    records, _ = catalog.walk_catalog(
        tmp_path,
        root_path=reference.path,
        root_digest=reference.digest,
        expected_catalog="services",
    )
    values = [cast(dict[str, Any], value) for _, value in records]
    gaps = [value for value in values if value.get("reasonCode") == "machine.facts.unresolved"]
    assert len(gaps) == len({value["recordId"] for value in gaps}) == 140
    assert {value["details"]["buildUnitId"] for value in gaps} == {f"unit-{i}" for i in range(140)}
    boundaries = {
        value["details"].get("boundaryId"): value
        for value in values
        if value["details"].get("recordType") == "serviceBoundary"
    }
    assert boundaries["unknown"]["witness"] is None
    assert boundaries["unknown"]["kind"] == "coverageGap"
    assert boundaries["declared"]["details"]["name"] == "acme.Service"
    assert boundaries["declared"]["details"]["displayName"] == "合同服务"
    assert boundaries["dynamic"]["details"]["resourceNature"] == "dynamic-reference"
    assert boundaries["dynamic"]["details"]["sourceBasis"] == "relation"
    assert boundaries["configured"]["details"]["sourceBasis"] == "configuration"
    assert boundaries["configured"]["witness"]["path"] == "service.yaml"
    assert all(
        value["witness"]["path"] in {"Service.java", "service.yaml"}
        for value in values
        if value["witness"]
    )
    relation = next(
        value for value in values if value["details"].get("recordType") == "serviceRelation"
    )
    assert relation["witness"]["startLine"] == 7


# 两条有序记录同时提供非空键范围和计数，便于单点篡改。
def _data_document() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "catalog": "evidence",
        "nodeType": "data",
        "firstKey": "a",
        "lastKey": "b",
        "recordCount": 2,
        "records": [{"key": "a", "value": {}}, {"key": "b", "value": {}}],
    }


# 索引见证包含子页摘要与类型，树完整性不能只依赖文件存在。
# 夹具保留 metadata 字段，覆盖可选扩展与固定信封的区别。
def _index_document() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "catalog": "evidence",
        "nodeType": "index",
        "firstKey": "a",
        "lastKey": "b",
        "recordCount": 2,
        "entries": [
            {
                "firstKey": "a",
                "lastKey": "b",
                "recordCount": 2,
                "path": "evidence/data.json",
                "digest": "a" * 64,
                "nodeType": "data",
            }
        ],
        "metadata": {},
    }


# 每项参数都对应一个独立协议不变量，防止宽泛异常掩盖漏检。
# 布尔值虽然是 Python 整数子类，也不能作为记录计数。
# 未知字段被拒绝，防止不同版本对同一信封作不一致解释。
# 键范围、记录顺序与总数必须一致，否则分页跳转不可信。
# 空树需要空范围，不能保留指向不存在数据的边界键。
@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({**_record_document(), "schemaVersion": 2}, "machine.store.catalog-envelope"),
        ({**_record_document(), "nodeType": "unknown"}, "machine.store.catalog-node-type"),
        ({**_record_document(), "recordCount": True}, "machine.store.catalog-count"),
        ({**_record_document(), "extra": 1}, "machine.store.catalog-record-fields"),
        ({**_record_document(), "key": 1}, "machine.store.catalog-record"),
        ({**_record_document(), "recordCount": 2}, "machine.store.catalog-record-count"),
        ({**_data_document(), "extra": 1}, "machine.store.catalog-data-fields"),
        ({**_data_document(), "records": []}, "machine.store.catalog-data-records"),
        ({**_data_document(), "records": ["bad"]}, "machine.store.catalog-data-record"),
        (
            {**_data_document(), "records": [{"key": "a", "value": {}, "extra": 1}]},
            "machine.store.catalog-data-record-fields",
        ),
        (
            {
                **_data_document(),
                "records": [{"key": "b", "value": {}}, {"key": "a", "value": {}}],
            },
            "machine.store.catalog-data-record-value",
        ),
        ({**_data_document(), "firstKey": "z"}, "machine.store.catalog-data-range"),
        ({**_index_document(), "metadata": []}, "machine.store.catalog-metadata"),
        ({**_index_document(), "extra": 1}, "machine.store.catalog-branch-fields"),
        ({**_index_document(), "entries": "bad"}, "machine.store.catalog-entries"),
        (
            {
                **_index_document(),
                "entries": [{**_index_document()["entries"][0], "extra": 1}],
            },
            "machine.store.catalog-reference-fields",
        ),
        (
            {
                **_index_document(),
                "entries": [{**_index_document()["entries"][0], "digest": "bad"}],
            },
            "machine.store.catalog-reference-value",
        ),
        ({**_index_document(), "recordCount": 3}, "machine.store.catalog-count-mismatch"),
        ({**_index_document(), "firstKey": "z"}, "machine.store.catalog-range"),
        (
            {
                **_index_document(),
                "firstKey": "a",
                "lastKey": "b",
                "recordCount": 0,
                "entries": [],
            },
            "machine.store.catalog-empty-range",
        ),
    ],
)
def test_catalog_document_validation_rejects_each_invalid_shape(
    document: dict[str, Any], code: str
) -> None:
    _assert_integrity(code, catalog.validate_document, document, expected_catalog="evidence")


# 140 条记录跨越数据页，使全量遍历和范围读取可比较。
# 仅验证节点时仍遍历同一承诺树，但不物化全部记录。
# 重叠范围应去重，半开区间的右端点不应额外出现。
# 比较访问页集合证明范围裁剪实际减少读取，而非事后过滤。
# 反向区间是空选择，不应退化成全目录读取。
def test_catalog_write_walk_and_disjoint_range_reads(tmp_path: Path) -> None:
    records = [
        CatalogRecord(f"key:{index:03d}", {"index": index}, f"records/{index:03d}.json")
        for index in range(140)
    ]
    root = catalog.write_catalog(
        tmp_path,
        catalog="evidence",
        index_path="evidence/index.json",
        records=records,
        metadata={"baselineDigest": "a" * 64},
        pack_records=True,
    )

    walked, visited = catalog.walk_catalog(
        tmp_path,
        root_path=root.path,
        root_digest=root.digest,
        expected_catalog="evidence",
    )
    assert len(walked) == 140
    assert root.path in visited
    no_records, same_pages = catalog.walk_catalog(
        tmp_path,
        root_path=root.path,
        root_digest=root.digest,
        expected_catalog="evidence",
        include_records=False,
    )
    assert no_records == []
    assert same_pages == visited

    selected, selected_pages = catalog.read_catalog_ranges(
        tmp_path,
        root_path=root.path,
        root_digest=root.digest,
        expected_catalog="evidence",
        ranges=(("key:005", "key:010"), ("key:008", "key:012")),
    )
    assert [key for key, _value in selected] == [
        *(f"key:{index:03d}" for index in range(5, 12)),
    ]
    assert selected_pages < visited
    assert catalog.read_catalog_ranges(
        tmp_path,
        root_path=root.path,
        root_digest=root.digest,
        expected_catalog="evidence",
        ranges=(("z", "a"),),
    ) == ([], set())


# 逐记录存储与打包页共享相同目录语义，两条路径都需覆盖。
# 完全重复观察可幂等写入，同键异内容必须拒绝。
# 越界、缺失、坏 JSON 和摘要失配是不同失败原因。
# 坏 JSON 使用其真实摘要，确保失败进入解析校验而非先被摘要拦截。
# 错误分类帮助维护者分辨损坏、漂移与无效请求。
def test_unpacked_catalog_and_load_failures_are_explicit(tmp_path: Path) -> None:
    records = [
        CatalogRecord("a", {"value": 1}, "records/a.json"),
        CatalogRecord("b", {"value": 2}, "records/b.json"),
    ]
    root = catalog.write_catalog(
        tmp_path,
        catalog="scope",
        index_path="scope/index.json",
        records=records,
    )
    walked, _visited = catalog.walk_catalog(
        tmp_path,
        root_path=root.path,
        root_digest=root.digest,
        expected_catalog="scope",
    )
    assert [key for key, _value in walked] == ["a", "b"]

    repeated = catalog.write_catalog(
        tmp_path,
        catalog="scope",
        index_path="repeated/index.json",
        records=(records[0], records[0]),
    )
    assert repeated.record_count == 1
    _assert_integrity(
        "machine.store.catalog-duplicate-key",
        catalog.write_catalog,
        tmp_path,
        catalog="scope",
        index_path="duplicate/index.json",
        records=(records[0], CatalogRecord("a", {"value": 2}, "records/a.json")),
    )
    _assert_integrity(
        "machine.store.catalog-path",
        catalog.load_document,
        tmp_path,
        "../escape.json",
        expected_digest="0" * 64,
    )
    _assert_integrity(
        "machine.store.catalog-read",
        catalog.load_document,
        tmp_path,
        "missing.json",
        expected_digest="0" * 64,
    )

    invalid_json = b"not json\n"
    (tmp_path / "invalid.json").write_bytes(invalid_json)
    _assert_integrity(
        "machine.store.catalog-json",
        catalog.load_document,
        tmp_path,
        "invalid.json",
        expected_digest=catalog.content_digest(invalid_json),
    )
    _assert_integrity(
        "machine.store.catalog-digest",
        catalog.load_document,
        tmp_path,
        root.path,
        expected_digest="0" * 64,
    )


# 单个记录过大不能靠分页解决，应在发布前明确拒绝。
# 路径、摘要和行号在公共值对象边界统一约束。
# 编译模式、worker 数和内存预算同样属于调用契约。
# 条目与字节预算无效时使用 BudgetError，区别于形状错误。
# 不让非法值进入存储后才由难以定位的 I/O 异常暴露。
def test_catalog_and_public_contract_budgets_fail_closed(tmp_path: Path) -> None:
    oversized = CatalogRecord(
        "large",
        {"payload": "x" * (300 * 1024)},
        "large.json",
    )
    _assert_integrity(
        "machine.store.catalog-record-byte-budget",
        catalog.write_catalog,
        tmp_path,
        catalog="evidence",
        index_path="evidence/index.json",
        records=(oversized,),
        pack_records=True,
    )

    for factory in (
        lambda: Witness("../outside", "a" * 64),
        lambda: Witness("source.py", "bad"),
        lambda: Witness("source.py", "a" * 64, start_line=0),
        lambda: Witness("source.py", "a" * 64, start_line=2, end_line=1),
        lambda: AnalysisOptions(compiler_mode="unknown"),  # type: ignore[arg-type]
        lambda: AnalysisOptions(workers=0),
        lambda: AnalysisOptions(memory_bytes=0),
        lambda: AnalysisIdentity("bad", "a" * 64),
        lambda: EvidenceQuery("evidence", paths=("../outside",)),
        lambda: EvidenceQuery("evidence", candidate_ids=(" ",)),
    ):
        with pytest.raises(ContractError):
            factory()
    for budget_factory in (
        lambda: EvidenceBudget(max_bytes=1),
        lambda: EvidenceBudget(max_items=0),
    ):
        with pytest.raises(BudgetError):
            budget_factory()


# 页预算包含 JSON 信封开销，不能只检查记录值大小。
# 分支扇出上限保证索引层同样有界，避免大树根节点膨胀。
# 计数类型先验证，使后续算术不会接受字符串或其他隐式转换。
# 这里直接覆盖写出边界，补充公共 API 的预算约束。
def test_catalog_writer_enforces_envelope_and_fanout_budgets(tmp_path: Path) -> None:
    _assert_integrity(
        "machine.store.catalog-byte-budget",
        catalog._write_bounded,
        tmp_path,
        "oversized.json",
        {"payload": "x" * CATALOG_MAX_BYTES},
    )
    _assert_integrity(
        "machine.store.catalog-record-count",
        catalog._write_bounded,
        tmp_path,
        "invalid-count.json",
        {"recordCount": "one"},
    )
    reference = catalog.CatalogReference("a", "a", 1, "a.json", "a" * 64, "record")
    _assert_integrity(
        "machine.store.catalog-item-budget",
        catalog._branch_payload,
        "evidence",
        "index",
        [reference] * (CATALOG_MAX_ITEMS + 1),
    )


# 四个目录根和诊断摘要共同构成 bundle 承诺，不能遗漏诊断文件。
def _manifest_roots(*, diagnostics_digest: str = "a" * 64) -> JsonObject:
    return {
        **{
            name: {"path": f"{name}/index.json", "digest": "a" * 64}
            for name in ("snapshot", "scope", "services", "evidence")
        },
        "diagnostics": {"path": "diagnostics.json", "digest": diagnostics_digest},
    }


# 空目录仍有合法信封与身份，不等同于目录缺失。
# 可选基线元数据用于精确模拟跨基线引用。
def _empty_index(catalog_name: str, *, baseline_digest: str | None = None) -> JsonObject:
    value: JsonObject = {
        "schemaVersion": 1,
        "catalog": catalog_name,
        "nodeType": "index",
        "firstKey": "",
        "lastKey": "",
        "recordCount": 0,
        "entries": [],
    }
    if baseline_digest is not None:
        value["metadata"] = {"baselineDigest": baseline_digest}
    return value


# 根必须是索引节点，合法记录页也不能替代目录根。
# 各根绑定同一 baseline，防止混合不同分析时刻的产物。
# 通过替换加载器隔离结构承诺校验，避免文件编码差异干扰。
# 两个故障分别检查，证明类型正确并不足以证明基线一致。
def test_root_commitments_reject_node_and_baseline_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _manifest_roots()
    manifest = {"baselineDigest": "a" * 64, "roots": roots}

    def record_root(_directory: Path, _relative: str, *, expected_digest: str) -> JsonObject:
        del expected_digest
        return {**_record_document(), "catalog": "snapshot"}

    monkeypatch.setattr(bundle_store, "load_document", record_root)
    _assert_integrity(
        "machine.store.catalog-reference-node",
        bundle_store._verify_root_commitments,
        tmp_path,
        manifest,
    )

    def stale_root(_directory: Path, relative: str, *, expected_digest: str) -> JsonObject:
        del expected_digest
        return _empty_index(relative.split("/", 1)[0], baseline_digest="b" * 64)

    monkeypatch.setattr(bundle_store, "load_document", stale_root)
    _assert_integrity(
        "machine.store.snapshot-baseline-mismatch",
        bundle_store._verify_root_commitments,
        tmp_path,
        manifest,
    )


# 即使根逐项通过验证，组合后的 bundle 摘要仍须重新认证。
# 伪造清单中的摘要不能成为自身有效性的证明。
# 此测试隔离组合身份边界，真实页面读取由其他场景覆盖。
def test_open_bundle_authenticates_the_composed_bundle_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = AnalysisIdentity("a" * 64, "b" * 64)
    roots = _manifest_roots()
    manifest: JsonObject = {
        "schemaVersion": 1,
        "bundleDigest": identity.bundle_digest,
        "baselineDigest": identity.baseline_digest,
        "implementationDigest": "c" * 64,
        "roots": roots,
        "state": "complete",
    }
    monkeypatch.setattr(bundle_store, "_load_manifest", lambda *_args: manifest)
    monkeypatch.setattr(bundle_store, "_verify_root_commitments", lambda *_args: roots)
    _assert_integrity(
        "machine.store.bundle-digest",
        bundle_store.open_bundle,
        ModusPaths.for_root(tmp_path),
        identity,
    )


def test_projection_preserves_full_occurrence_and_context_identity() -> None:
    from modus.machine.store.bundle_catalogs import _evidence_record

    raw: dict[str, Any] = {
        "source": "caller",
        "target": "callee",
        "relation": "calls",
        "contextId": "main",
        "location": {
            "path": "a.java",
            "startLine": 2,
            "startColumn": 1,
            "endLine": 2,
            "endColumn": 12,
        },
    }

    def project(row):
        return _evidence_record(
            raw=row, path="a.java", source_digest="a" * 64, candidate_ids=(), kind="relation"
        )

    first = project(raw)
    longer = project({**raw, "location": {**raw["location"], "endColumn": 20}})
    other_context = project({**raw, "contextId": "test"})
    assert len({first["recordId"], longer["recordId"], other_context["recordId"]}) == 3
    assert project(raw) == first


def test_material_candidate_fanout_is_bounded_without_mutating_observations() -> None:
    from modus.machine.store.bundle import canonical_bytes
    from modus.machine.store.bundle_catalogs import _evidence_record

    identities = [f"entry:{index:032x}" for index in range(10_000)]
    raw: dict[str, Any] = {
        "materialType": "text",
        "content": "调用 `save`。",
        "associations": [
            {"mention": "save", "entryIds": identities, "basis": "explicit-identifier"}
        ],
        "location": {"startLine": 1, "endLine": 1},
    }
    record = _evidence_record(
        raw=raw, path="guide.md", source_digest="a" * 64, candidate_ids=(), kind="resource"
    )
    association = cast(dict[str, Any], record["details"])["associations"][0]
    assert association["entryIds"] == identities[:32]
    assert association["entryIdsOmittedCount"] == len(identities) - 32
    assert len(canonical_bytes(record)) < EvidenceBudget().max_bytes
    assert raw["associations"][0]["entryIds"] == identities


def test_gap_identity_preserves_nested_source_ranges() -> None:
    from modus.machine.store.bundle_catalogs import _coverage_gap
    from modus.machine.store.evidence_records import gap_record

    witnesses = [Witness("a.java", "a" * 64, "caller", 3, end) for end in (3, 8)]
    records = [gap_record("machine.facts.unresolved", witness=w) for w in witnesses]
    assert records[0].record_id != records[1].record_id
    assert gap_record("machine.facts.unresolved", witness=witnesses[0]) == records[0]
    locations = [
        {"startLine": 3, "startColumn": 1, "endLine": 3, "endColumn": column} for column in (12, 20)
    ]
    projected = [
        _coverage_gap(
            {"reasonCode": "machine.facts.unresolved", "location": location},
            path="a.java",
            source_digest="a" * 64,
            candidate_ids=(),
        )
        for location in locations
    ]
    assert projected[0]["recordId"] != projected[1]["recordId"]
    details = projected[1]["details"]
    assert isinstance(details, dict)
    assert details["location"] == locations[1]
