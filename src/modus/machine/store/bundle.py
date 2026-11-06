"""Atomic publication and complete verification of bounded evidence catalogs."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeGuard, cast

from modus.artifacts_io import atomic_write_text
from modus.knowledge_reader import read_bound_regular_bytes
from modus.machine.errors import IntegrityError
from modus.machine.progress import ProgressReporter
from modus.machine.store.bundle_catalogs import (
    evidence_catalog as _evidence_catalog,
)
from modus.machine.store.bundle_catalogs import (
    scope_catalog as _scope_catalog,
)
from modus.machine.store.bundle_catalogs import (
    service_catalog as _service_catalog,
)
from modus.machine.store.bundle_catalogs import (
    snapshot_catalog as _snapshot_catalog,
)
from modus.machine.store.catalog import (
    CatalogReference,
    canonical_bytes,
    content_digest,
    load_document,
    read_catalog_range,
    read_catalog_ranges,
    validate_document,
    walk_catalog,
)
from modus.machine.store.contracts import (
    CATALOG_MAX_BYTES,
    SCHEMA_VERSION,
    AnalysisBundle,
    AnalysisIdentity,
    AnalysisReceipt,
    JsonObject,
)
from modus.machine.store.evidence_records import parse_record
from modus.paths import ModusPaths
from modus.sensitive_literals import sensitive_literal_findings

_MAX_MANIFEST_BYTES = 64 * 1024
_ROOT_NAMES = ("snapshot", "scope", "services", "evidence", "diagnostics")


# 摘要必须为完整小写十六进制值，不能把任意目录名当作分析身份。
# 摘要格式检查先于身份比较，非法字符串不能成为目录承诺。
def _is_digest(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _as_objects(value: object) -> list[JsonObject]:
    return (
        [cast(JsonObject, row) for row in value if isinstance(row, dict)]
        if isinstance(value, list)
        else []
    )


# 协议计数排除布尔值，避免 Python 数值继承关系绕过类型约束。
def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


# 诊断同样是受限发布产物，不能因非主证据而绕过字节上限。
# 写入字节与根引用使用同一规范编码。
def _write_diagnostics(directory: Path, diagnostics: Mapping[str, Any]) -> CatalogReference:
    value: JsonObject = {
        "schemaVersion": SCHEMA_VERSION,
        **{
            str(key): cast(Any, item) for key, item in diagnostics.items() if key != "schemaVersion"
        },
    }
    encoded = canonical_bytes(value)
    if len(encoded) > CATALOG_MAX_BYTES:
        raise IntegrityError("machine.store.diagnostics-byte-budget")
    path = directory / "diagnostics.json"
    atomic_write_text(path, encoded.decode())
    return CatalogReference("", "", 1, "diagnostics.json", content_digest(encoded), "diagnostics")


# 包身份绑定基线、实现与全部根目录承诺。
# 任一视图变化都会改变包摘要，避免混合新旧分析结果。
# 根名称按固定契约取值，不依赖字典插入顺序。
def _bundle_state_digest(
    *,
    baseline_digest: str,
    implementation_digest: str,
    roots: Mapping[str, Mapping[str, Any]],
) -> str:
    return content_digest(
        canonical_bytes(
            {
                "schemaVersion": SCHEMA_VERSION,
                "baselineDigest": baseline_digest,
                "implementationDigest": implementation_digest,
                "roots": {name: roots[name] for name in _ROOT_NAMES},
            }
        )
    )


# 安全检查发生在任何证据写盘之前，失败不留下待公开材料。
# 同时检查键和值，敏感字面量可能藏在映射键中。
# 诊断只报告种类和数据坐标，不回显原始敏感内容。
# 本机仓库根和用户目录不应进入可移植证据。
# 坐标中的异常键以占位符替代，避免错误消息再次泄露值。
# 发现数量有上限，使拒绝报告本身也保持有界。
def _assert_safe_publication(
    paths: ModusPaths,
    values: Mapping[str, object],
    *,
    progress: ProgressReporter | None = None,
) -> None:
    """Reject host identity and high-confidence secrets before writing a bundle."""
    on_sensitive_progress = None
    if progress is not None:
        progress.transition("package.safety.sensitive-literals")
        if progress.emits_updates:

            def report_sensitive_progress(inspected: int) -> None:
                progress.advance(inspected, unit="values")

            on_sensitive_progress = report_sensitive_progress
    findings = sensitive_literal_findings(
        values,
        limit=8,
        on_progress=on_sensitive_progress,
    )
    if findings:
        coordinates = ", ".join(f"{item.kind}@{item.pointer}" for item in findings)
        raise IntegrityError(
            "machine.store.sensitive-publication",
            "published evidence contains a prohibited sensitive literal: " + coordinates,
        )
    forbidden = {str(paths.root), str(Path.home())}
    pending: list[tuple[str, object]] = [("", values)]
    path_findings: list[str] = []
    inspected = 0
    if progress is not None:
        progress.transition("package.safety.portability")
    while pending and len(path_findings) < 8:
        pointer, value = pending.pop()
        inspected += 1
        if progress is not None and inspected % 4096 == 0:
            progress.advance(inspected, unit="values")
        if isinstance(value, Mapping):
            for key, item in reversed(tuple(value.items())):
                raw_segment = str(key)
                segment = (
                    raw_segment
                    if 0 < len(raw_segment) <= 80
                    and all(character.isalnum() or character in "_.-" for character in raw_segment)
                    else "<key>"
                )
                pending.append((f"{pointer}/{segment}", item))
                pending.append((f"{pointer}/<key>", key))
        elif isinstance(value, (list, tuple, set, frozenset)):
            for index, item in reversed(tuple(enumerate(value))):
                pending.append((f"{pointer}/{index}", item))
        elif isinstance(value, str) and any(
            marker and marker != "/" and marker in value for marker in forbidden
        ):
            path_findings.append(pointer or "/")
    if path_findings:
        raise IntegrityError(
            "machine.store.nonportable-publication",
            "published evidence contains a checkout or home path: " + ", ".join(path_findings),
        )
    if progress is not None:
        progress.advance(inspected, unit="values", force=True)


# 先在临时目录构造全部视图，通过完整验证后原子发布。
# 内容地址决定最终目录，相同结果可复用已有完整产物。
# 已有目录也需重新验证，不能因名称相同就信任磁盘内容。
# 只有新包可用之后才清理旧包，防止构建失败清空可用分析。
# 写入边界限于临时分析数据，不修改 Git 状态或长期知识。
# 回执仅返回身份与摘要，查询必须通过公开读取契约。
def publish_bundle(
    paths: ModusPaths,
    *,
    baseline_digest: str,
    implementation_digest: str,
    snapshot: Mapping[str, Any],
    scope: Mapping[str, Any],
    services: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    evidence_index: Mapping[str, Any],
    evidence_packets: Mapping[str, Mapping[str, Any]],
    progress: ProgressReporter | None = None,
) -> AnalysisReceipt:
    """Publish one complete content-addressed bundle without touching Git state."""

    _assert_safe_publication(
        paths,
        {
            "snapshot": snapshot,
            "scope": scope,
            "services": services,
            "diagnostics": diagnostics,
            "evidenceIndex": evidence_index,
            "evidencePackets": evidence_packets,
        },
        progress=progress,
    )
    paths.analysis_bundles_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".build-", dir=paths.init_analysis_dir) as temporary:
        candidate = Path(temporary) / "bundle"
        candidate.mkdir()
        references: dict[str, CatalogReference] = {}
        if progress is not None:
            progress.transition("package.catalog.snapshot")
        references["snapshot"] = _snapshot_catalog(candidate, snapshot, progress=progress)
        if progress is not None:
            progress.transition("package.catalog.scope")
        references["scope"] = _scope_catalog(candidate, scope, snapshot, progress=progress)
        if progress is not None:
            progress.transition("package.catalog.services")
        references["services"] = _service_catalog(
            candidate,
            services,
            snapshot,
            progress=progress,
        )
        if progress is not None:
            progress.transition("package.catalog.evidence-project")
        references["evidence"] = _evidence_catalog(
            candidate,
            evidence_index,
            evidence_packets,
            progress=progress,
        )
        if progress is not None:
            progress.transition("package.catalog.diagnostics")
        references["diagnostics"] = _write_diagnostics(candidate, diagnostics)
        # 每个根引用只保留路径与内容摘要，组成可验证的承诺树。
        # 展示计数与诊断摘要不替代这些内容承诺。
        roots: JsonObject = {
            name: {"path": ref.path, "digest": ref.digest} for name, ref in references.items()
        }
        bundle_digest = _bundle_state_digest(
            baseline_digest=baseline_digest,
            implementation_digest=implementation_digest,
            roots=cast(Mapping[str, Mapping[str, Any]], roots),
        )
        coverage: JsonObject = {
            "sourceFiles": len(_as_objects(snapshot.get("sources"))),
            "evidenceFiles": len(evidence_packets),
            "scopeCandidates": len(_as_objects(scope.get("candidates"))),
            "serviceNodes": len(_as_objects(services.get("nodes"))),
            "serviceEdges": len(_as_objects(services.get("edges"))),
        }
        diagnostic_summary: JsonObject = {
            "status": str(diagnostics.get("status") or "complete"),
            "groups": _integer(diagnostics.get("groupCount")),
            "total": _integer(diagnostics.get("totalCount")),
        }
        # 完成清单只在所有目录构造完成后写出。
        # 发布前仍需递归校验，state 字段本身不是成功证明。
        manifest: JsonObject = {
            "schemaVersion": SCHEMA_VERSION,
            "bundleDigest": bundle_digest,
            "baselineDigest": baseline_digest,
            "implementationDigest": implementation_digest,
            "roots": roots,
            "state": "complete",
        }
        atomic_write_text(candidate / "manifest.json", canonical_bytes(manifest).decode())
        if progress is not None:
            progress.transition("package.verify-bundle")
        _verify_directory(candidate, manifest, progress=progress)
        destination = paths.analysis_bundles_dir / bundle_digest
        if destination.exists():
            if progress is not None:
                progress.transition("package.verify-existing-bundle")
            open_bundle(paths, AnalysisIdentity(bundle_digest, baseline_digest))
            _verify_directory(
                destination,
                _load_manifest(paths, destination),
                progress=progress,
            )
        else:
            if progress is not None:
                progress.transition("package.publish")
            os.replace(candidate, destination)
        if progress is not None and destination.exists():
            progress.transition("package.prune")
        _prune_other_bundles(paths, keep=bundle_digest)
    return AnalysisReceipt(
        AnalysisIdentity(bundle_digest, baseline_digest),
        coverage,
        diagnostic_summary,
    )


# 只清理专用证据包目录的其他子目录，保留刚发布的身份。
# 调用发生在新包验证成功之后，清理不参与包内容摘要。
def _prune_other_bundles(paths: ModusPaths, *, keep: str) -> None:
    for child in paths.analysis_bundles_dir.iterdir():
        if child.name != keep and child.is_dir() and child.parent == paths.analysis_bundles_dir:
            shutil.rmtree(child)


# 清单有独立的小尺寸上限，打开分析不需要先读取全部证据。
# 受限读取拒绝越界或非常规文件，JSON 形状随后单独校验。
def _load_manifest(paths: ModusPaths, directory: Path) -> JsonObject:
    try:
        raw = read_bound_regular_bytes(
            paths.root, directory / "manifest.json", max_bytes=_MAX_MANIFEST_BYTES
        )
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntegrityError("machine.store.manifest-json") from exc
    if not isinstance(value, dict):
        raise IntegrityError("machine.store.manifest-object")
    return cast(JsonObject, value)


# 每个命名空间根都有固定路径，清单不能重定向到任意包内文件。
# 引用只包含路径与摘要，未知字段也视作契约不一致。
# 目录根引用集中解码，后续范围查询依赖同一认证入口。
def _root_reference(roots: Mapping[str, Any], name: str) -> tuple[str, str]:
    value = roots.get(name)
    if not isinstance(value, Mapping) or set(value) != {"path", "digest"}:
        raise IntegrityError("machine.store.manifest-root")
    path, digest = value["path"], value["digest"]
    if not isinstance(path, str) or not _is_digest(digest):
        raise IntegrityError("machine.store.manifest-root-value")
    expected_path = "diagnostics.json" if name == "diagnostics" else f"{name}/index.json"
    if path != expected_path:
        raise IntegrityError("machine.store.manifest-root-path")
    return path, digest


# 诊断必须绑定同一基线，不能附带另一轮分析的失败统计。
# 分组种类、样本形状与总数量逐项核对。
# 样本最多三条，摘要计数仍保留该组真实规模。
# 缺失行号允许表达全局问题，非法行号不能强转。
# 状态只接受 complete/partial，新增状态需显式扩展契约。
# 诊断同样属于包契约，不能因为不含正向证据而跳过形状验证。
def _validate_diagnostics(value: object, *, baseline_digest: str) -> None:
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion",
        "baselineDigest",
        "status",
        "stages",
        "groups",
        "groupCount",
        "totalCount",
        "coverage",
    }:
        raise IntegrityError("machine.store.diagnostics-schema")
    groups = value.get("groups")
    if (
        value.get("schemaVersion") != SCHEMA_VERSION
        or value.get("baselineDigest") != baseline_digest
        or value.get("status") not in {"complete", "partial"}
        or not isinstance(value.get("stages"), dict)
        or not isinstance(value.get("coverage"), dict)
        or not isinstance(groups, list)
    ):
        raise IntegrityError("machine.store.diagnostics-schema")
    total = 0
    for raw in groups:
        count = _validate_diagnostic_group(raw)
        total += count
    if value.get("groupCount") != len(groups) or value.get("totalCount") != total:
        raise IntegrityError("machine.store.diagnostics-count")


def _validate_diagnostic_group(raw: object) -> int:
    """组内验证先于总数核对，首个错误仍由原有诊断码表示。"""
    if not isinstance(raw, dict) or set(raw) != {
        "stage",
        "language",
        "reasonCode",
        "resolution",
        "count",
        "samples",
    }:
        raise IntegrityError("machine.store.diagnostics-group")
    count, samples = raw.get("count"), raw.get("samples")
    if (
        not all(
            isinstance(raw.get(name), str) and raw.get(name)
            for name in (
                "stage",
                "language",
                "reasonCode",
                "resolution",
            )
        )
        or raw.get("resolution") not in {"exact", "candidate", "heuristic", "unresolved"}
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
        or not isinstance(samples, list)
        or len(samples) > 3
    ):
        raise IntegrityError("machine.store.diagnostics-group-value")
    for sample in samples:
        _validate_diagnostic_sample(sample)
    return count


def _validate_diagnostic_sample(sample: object) -> None:
    """逐项验证来源锚点，保留字段错误与值错误的诊断区别。"""
    if not isinstance(sample, dict) or set(sample) != {
        "path",
        "symbol",
        "startLine",
    }:
        raise IntegrityError("machine.store.diagnostics-sample")
    start_line = sample.get("startLine")
    if (
        not isinstance(sample.get("path"), str)
        or not sample["path"]
        or not isinstance(sample.get("symbol"), str)
        or start_line is not None
        and (not isinstance(start_line, int) or isinstance(start_line, bool) or start_line < 1)
    ):
        raise IntegrityError("machine.store.diagnostics-sample-value")


# 发布前走完所有目录与记录，校验内容协议及记录身份唯一性。
# 快照记录使用输入身份契约，其他视图使用公共证据记录契约。
# 可达文件集合必须等于实际文件集合，拒绝夹带未引用产物。
# 诊断单独验证摘要和基线，不能被视图验证遗漏。
# 进度合并各目录页数，回调不会改变验证结论。
def _verify_directory(
    directory: Path,
    manifest: Mapping[str, Any],
    *,
    progress: ProgressReporter | None = None,
) -> tuple[JsonObject, dict[str, tuple[tuple[str, JsonObject], ...]]]:
    roots = manifest.get("roots")
    if not isinstance(roots, Mapping) or set(roots) != set(_ROOT_NAMES):
        raise IntegrityError("machine.store.manifest-roots")
    reachable = {"manifest.json"}
    catalogs: dict[str, tuple[tuple[str, JsonObject], ...]] = {}
    verified_pages = 0
    for name in ("snapshot", "scope", "services", "evidence"):
        path, digest = _root_reference(roots, name)
        on_catalog_progress = None
        if progress is not None and progress.emits_updates:
            base = verified_pages

            def report_catalog_progress(completed: int, *, _base: int = base) -> None:
                progress.advance(_base + completed, unit="pages")

            on_catalog_progress = report_catalog_progress
        if on_catalog_progress is None:
            records, visited = walk_catalog(
                directory,
                root_path=path,
                root_digest=digest,
                expected_catalog=name,
            )
        else:
            records, visited = walk_catalog(
                directory,
                root_path=path,
                root_digest=digest,
                expected_catalog=name,
                on_progress=on_catalog_progress,
            )
        verified_pages += len(visited)
        if progress is not None:
            progress.advance(verified_pages, unit="pages", force=True)
        record_ids: set[str] = set()
        for _key, value in records:
            if name == "snapshot" and value.get("kind") == "coverageGap":
                parse_record(value)
            elif name == "snapshot":
                record_type = value.get("recordType")
                if record_type not in {"source", "buildUnit", "buildUnitSource"}:
                    raise IntegrityError("machine.store.snapshot-record-kind")
                if record_type == "source" and (
                    not isinstance(value.get("path"), str) or not _is_digest(value.get("sha256"))
                ):
                    raise IntegrityError("machine.store.snapshot-source-record")
            else:
                record = parse_record(value)
                if record.record_id in record_ids:
                    raise IntegrityError(f"machine.store.{name}-duplicate-record-id")
                record_ids.add(record.record_id)
        catalogs[name] = tuple(records)
        reachable.update(visited)
    path, digest = _root_reference(roots, "diagnostics")
    raw = read_bound_regular_bytes(directory, directory / path, max_bytes=CATALOG_MAX_BYTES)
    if content_digest(raw) != digest:
        raise IntegrityError("machine.store.diagnostics-digest")
    try:
        diagnostic_value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntegrityError("machine.store.diagnostics-json") from exc
    _validate_diagnostics(
        diagnostic_value,
        baseline_digest=str(manifest.get("baselineDigest") or ""),
    )
    reachable.add(path)
    # 未被根引用覆盖的文件也会使验证失败。
    # 这样公开包不会携带旧构建残留或未核验的旁路数据。
    actual = {
        child.relative_to(directory).as_posix() for child in directory.rglob("*") if child.is_file()
    }
    if actual != reachable:
        raise IntegrityError("machine.store.bundle-file-set")
    return cast(JsonObject, roots), catalogs


# 打开时只验证根承诺，叶页在实际查询时按需验证。
# 这种分工保证快速打开，同时不信任未经核验的读取页面。
# 各根元数据中的基线必须一致，防止跨版本拼接。
def _verify_root_commitments(directory: Path, manifest: Mapping[str, Any]) -> JsonObject:
    """Authenticate the manifest and catalog roots without walking leaf pages."""

    roots = manifest.get("roots")
    if not isinstance(roots, Mapping) or set(roots) != set(_ROOT_NAMES):
        raise IntegrityError("machine.store.manifest-roots")
    snapshot_digest = str(manifest.get("baselineDigest") or "")
    for name in ("snapshot", "scope", "services", "evidence"):
        path, digest = _root_reference(roots, name)
        value = load_document(directory, path, expected_digest=digest)
        validate_document(value, expected_catalog=name)
        if value.get("nodeType") != "index":
            raise IntegrityError("machine.store.catalog-reference-node")
        metadata = value.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("baselineDigest") != snapshot_digest:
            raise IntegrityError(f"machine.store.{name}-baseline-mismatch")
    path, digest = _root_reference(roots, "diagnostics")
    raw = read_bound_regular_bytes(directory, directory / path, max_bytes=CATALOG_MAX_BYTES)
    if content_digest(raw) != digest:
        raise IntegrityError("machine.store.diagnostics-digest")
    try:
        diagnostics = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntegrityError("machine.store.diagnostics-json") from exc
    _validate_diagnostics(diagnostics, baseline_digest=snapshot_digest)
    return cast(JsonObject, roots)


# 清单只有 complete 状态可打开，临时构建不能被查询。
# 同时验证用户请求身份、清单身份与重算的包摘要。
# 实现摘要是包承诺的一部分，即使源码基线相同也不能忽略。
# 返回私有存储句柄，调用者仍需经过受预算约束的查询层。
def open_bundle(paths: ModusPaths, identity: AnalysisIdentity) -> AnalysisBundle:
    """Open a bundle after authenticating its identity and Merkle roots.

    Publication performs a full recursive validation. Selection subsequently
    authenticates only the index and data pages it actually reads.
    """

    bundle_digest = identity.bundle_digest
    baseline_digest = identity.baseline_digest
    if not _is_digest(bundle_digest):
        raise IntegrityError("machine.store.invalid-bundle-digest")
    if not _is_digest(baseline_digest):
        raise IntegrityError("machine.store.invalid-baseline-digest")
    directory = paths.analysis_bundles_dir / bundle_digest
    manifest = _load_manifest(paths, directory)
    if (
        set(manifest)
        != {
            "schemaVersion",
            "bundleDigest",
            "baselineDigest",
            "implementationDigest",
            "roots",
            "state",
        }
        or manifest.get("schemaVersion") != SCHEMA_VERSION
    ):
        raise IntegrityError("machine.store.manifest-schema")
    if manifest.get("state") != "complete" or manifest.get("bundleDigest") != bundle_digest:
        raise IntegrityError("machine.store.manifest-identity")
    if manifest.get("baselineDigest") != baseline_digest:
        raise IntegrityError("machine.store.baseline-mismatch")
    implementation_digest = manifest.get("implementationDigest")
    if not _is_digest(implementation_digest):
        raise IntegrityError("machine.store.manifest-implementation-digest")
    roots = _verify_root_commitments(directory, manifest)
    actual_bundle = _bundle_state_digest(
        baseline_digest=baseline_digest,
        implementation_digest=implementation_digest,
        roots=cast(Mapping[str, Mapping[str, Any]], roots),
    )
    if actual_bundle != bundle_digest:
        raise IntegrityError("machine.store.bundle-digest")
    return AnalysisBundle(
        identity=identity,
        _root=paths.root,
        _directory=directory,
        _roots=roots,
    )


# 仅允许公开定义的四种目录名称，诊断使用单独读取路径。
# 局部读取仍从可信根开始验证，不直接打开推测的数据页路径。
def load_catalog_range(
    bundle: AnalysisBundle,
    name: str,
    *,
    start_key: str = "",
    end_key: str = "",
) -> tuple[tuple[str, JsonObject], ...]:
    """Load an authenticated key range without traversing unrelated data pages."""

    if name not in {"snapshot", "scope", "services", "evidence"}:
        raise IntegrityError("machine.store.unknown-catalog")
    roots = cast(Mapping[str, Any], bundle._roots)
    path, digest = _root_reference(roots, name)
    records, _ = read_catalog_range(
        bundle._directory,
        root_path=path,
        root_digest=digest,
        expected_catalog=name,
        start_key=start_key,
        end_key=end_key,
    )
    return tuple(records)


# 多个筛选区间共享一次根遍历，减少重复索引读取。
# 空区间集合交由目录层处理，不隐式扩大成全量目录。
def load_catalog_ranges(
    bundle: AnalysisBundle,
    name: str,
    *,
    ranges: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, JsonObject], ...]:
    """Load multiple authenticated key ranges with one shared index traversal."""

    if name not in {"snapshot", "scope", "services", "evidence"}:
        raise IntegrityError("machine.store.unknown-catalog")
    roots = cast(Mapping[str, Any], bundle._roots)
    path, digest = _root_reference(roots, name)
    records, _ = read_catalog_ranges(
        bundle._directory,
        root_path=path,
        root_digest=digest,
        expected_catalog=name,
        ranges=ranges,
    )
    return tuple(records)


# 全量读取结果按包句柄缓存，同一分析内避免反复验证整棵树。
# 缓存键只需目录名，因为句柄已绑定不可变的包身份。
# 此函数是内部存储能力，公共调用者应优先使用有界证据查询。
def load_catalog(bundle: AnalysisBundle, name: str) -> tuple[tuple[str, JsonObject], ...]:
    if name not in {"snapshot", "scope", "services", "evidence"}:
        raise IntegrityError("machine.store.unknown-catalog")
    cached = bundle._catalog_cache.get(name)
    if cached is not None:
        return cached
    roots = cast(Mapping[str, Any], bundle._roots)
    path, digest = _root_reference(roots, name)
    records, _ = walk_catalog(
        bundle._directory,
        root_path=path,
        root_digest=digest,
        expected_catalog=name,
    )
    result = tuple(records)
    bundle._catalog_cache[name] = result
    return result


__all__ = [
    "canonical_bytes",
    "load_catalog",
    "load_catalog_range",
    "load_catalog_ranges",
    "open_bundle",
    "publish_bundle",
]
