"""Bounded, content-addressed range catalogs used by every bundle namespace."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from modus.artifacts_io import atomic_write_text
from modus.knowledge_reader import read_bound_regular_bytes
from modus.machine.errors import IntegrityError
from modus.machine.progress import ProgressReporter
from modus.machine.store.contracts import (
    CATALOG_MAX_BYTES,
    CATALOG_MAX_ITEMS,
    SCHEMA_VERSION,
    JsonObject,
)


def _compact_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


# 所有摘要使用相同 JSON 编码和结尾换行，写入与验证必须一致。
# 排序键消除对象构造顺序对内容身份的影响。
def canonical_bytes(value: object) -> bytes:
    return _compact_bytes(value) + b"\n"


def content_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


# 目录引用只能使用规范相对路径，不允许读取包根外的文件。
# 拒绝而非修正不规范路径，避免同一路径出现多种身份表达。
def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value != path.as_posix()
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
    ):
        raise IntegrityError("machine.store.catalog-path")
    return path


# 父节点同时承诺子节点内容、键范围和记录数量。
# 读取时逐层核对这些值，不能只验证 JSON 文件摘要。
@dataclass(frozen=True, slots=True)
class CatalogReference:
    first_key: str
    last_key: str
    record_count: int
    path: str
    digest: str
    node_type: str

    def to_dict(self) -> JsonObject:
        return {
            "firstKey": self.first_key,
            "lastKey": self.last_key,
            "recordCount": self.record_count,
            "path": self.path,
            "digest": self.digest,
            "nodeType": self.node_type,
        }


# 逻辑排序键与物理存储路径分离，打包布局可独立优化。
@dataclass(frozen=True, slots=True)
class CatalogRecord:
    key: str
    value: JsonObject
    relative_path: str


# 按最终序列化字节数检查上限，Unicode 字符数不能代替字节数。
# 原子写入避免中途失败留下半个 JSON 文件。
# 返回的引用摘要来自真正写出的字节，不能基于另一种编码计算。
def _write_bounded(directory: Path, relative: str, value: JsonObject) -> CatalogReference:
    path = _safe_relative(relative)
    encoded = canonical_bytes(value)
    if len(encoded) > CATALOG_MAX_BYTES:
        raise IntegrityError("machine.store.catalog-byte-budget")
    destination = directory.joinpath(*path.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, encoded.decode())
    first_key = str(value.get("firstKey") or value.get("key") or "")
    last_key = str(value.get("lastKey") or value.get("key") or "")
    record_count = value.get("recordCount", 1)
    node_type = str(value.get("nodeType") or "")
    if not isinstance(record_count, int) or isinstance(record_count, bool):
        raise IntegrityError("machine.store.catalog-record-count")
    return CatalogReference(
        first_key,
        last_key,
        record_count,
        path.as_posix(),
        content_digest(encoded),
        node_type,
    )


# 索引节点也受条目预算约束，目录规模通过增加树高扩展。
# 空索引使用空键范围，仍是可验证的完整目录。
# 分支只描述子页面的范围与承诺，数据正文保留在叶级页面。
def _branch_payload(
    catalog: str,
    node_type: str,
    references: list[CatalogReference],
    *,
    metadata: JsonObject | None = None,
) -> JsonObject:
    if len(references) > CATALOG_MAX_ITEMS:
        raise IntegrityError("machine.store.catalog-item-budget")
    payload: JsonObject = {
        "schemaVersion": SCHEMA_VERSION,
        "catalog": catalog,
        "nodeType": node_type,
        "firstKey": references[0].first_key if references else "",
        "lastKey": references[-1].last_key if references else "",
        "recordCount": sum(item.record_count for item in references),
        "entries": [item.to_dict() for item in references],
    }
    if metadata:
        payload["metadata"] = metadata
    return payload


# 全局键排序保证页面与树结构可重复；相同观察幂等，不同内容拒绝。
# 打包记录和单条文件共享引用协议，读取端无需猜测布局。
# 数据页与索引页都经过统一的字节预算检查。
def write_catalog(
    directory: Path,
    *,
    catalog: str,
    index_path: str,
    records: Iterable[CatalogRecord],
    metadata: JsonObject | None = None,
    pack_records: bool = False,
    progress: ProgressReporter | None = None,
) -> CatalogReference:
    """Write sorted records plus a bounded multi-level range index.

    Packed catalogs deliberately ignore source-directory ownership: globally
    sorted keys produce dense, deterministic pages and make prefix reads cheap.
    ``relative_path`` remains part of the input contract for unpacked catalogs.
    """

    unique: dict[str, CatalogRecord] = {}
    for item in records:
        previous = unique.get(item.key)
        if previous is not None and (
            previous.relative_path != item.relative_path
            or canonical_bytes(previous.value) != canonical_bytes(item.value)
        ):
            raise IntegrityError(
                "machine.store.catalog-duplicate-key",
                details={"catalog": catalog, "keyDigest": content_digest(item.key.encode())},
            )
        unique[item.key] = item
    normalized = sorted(unique.values(), key=lambda item: item.key)
    references: list[CatalogReference] = []
    if pack_records:
        page: list[CatalogRecord] = []
        page_rows_bytes = 0

        # 估算包括空封套、行内容及逗号，避免只统计业务字段漏算开销。
        # 首尾键随拟加入记录变化，因此封套也需重新计算。
        def page_size(owned: list[CatalogRecord], rows_bytes: int) -> int:
            envelope: JsonObject = {
                "schemaVersion": SCHEMA_VERSION,
                "catalog": catalog,
                "nodeType": "data",
                "firstKey": owned[0].key,
                "lastKey": owned[-1].key,
                "recordCount": len(owned),
                "records": [],
            }
            return len(canonical_bytes(envelope)) + rows_bytes + max(0, len(owned) - 1)

        # 页面名称取内容摘要，相同输入生成相同物理引用。
        # 记录顺序在上层固定，页面内部不再次排序或改变语义。
        def finish_page(owned: list[CatalogRecord]) -> None:
            finished: JsonObject = {
                "schemaVersion": SCHEMA_VERSION,
                "catalog": catalog,
                "nodeType": "data",
                "firstKey": owned[0].key,
                "lastKey": owned[-1].key,
                "recordCount": len(owned),
                "records": [{"key": record.key, "value": record.value} for record in owned],
            }
            digest = content_digest(canonical_bytes(finished))
            base = PurePosixPath(index_path).parent
            references.append(
                _write_bounded(
                    directory,
                    (base / "_data" / f"{digest}.json").as_posix(),
                    finished,
                )
            )

        total = len(normalized)
        for completed, item in enumerate(normalized, start=1):
            proposed = [*page, item]
            row_size = len(_compact_bytes({"key": item.key, "value": item.value}))
            proposed_rows_bytes = page_rows_bytes + row_size
            if (
                len(proposed) > CATALOG_MAX_ITEMS
                or page_size(proposed, proposed_rows_bytes) > CATALOG_MAX_BYTES
            ):
                # 单条记录本身超限时明确失败，不能输出永远读不出的页面。
                # 已有页面先封存，再单独校验新页首条的大小。
                if not page:
                    raise IntegrityError("machine.store.catalog-record-byte-budget")
                finish_page(page)
                page = [item]
                page_rows_bytes = row_size
                if page_size(page, page_rows_bytes) > CATALOG_MAX_BYTES:
                    raise IntegrityError("machine.store.catalog-record-byte-budget")
            else:
                page = proposed
                page_rows_bytes = proposed_rows_bytes
            if (
                progress is not None
                and progress.emits_updates
                and (completed % 1024 == 0 or completed == total)
            ):
                progress.advance(
                    completed,
                    total,
                    unit="records",
                    force=completed == total,
                )
        if page:
            finish_page(page)
        if any(
            left.last_key >= right.first_key
            for left, right in zip(references, references[1:], strict=False)
        ):
            raise IntegrityError("machine.store.catalog-overlapping-pages")
    else:
        total = len(normalized)
        for completed, item in enumerate(normalized, start=1):
            document: JsonObject = {
                "schemaVersion": SCHEMA_VERSION,
                "catalog": catalog,
                "nodeType": "record",
                "key": item.key,
                "recordCount": 1,
                "value": item.value,
            }
            references.append(_write_bounded(directory, item.relative_path, document))
            if (
                progress is not None
                and progress.emits_updates
                and (completed % 1024 == 0 or completed == total)
            ):
                progress.advance(
                    completed,
                    total,
                    unit="records",
                    force=completed == total,
                )

    # 自底向上分层构造范围索引，每层引用数量都有上限。
    # 根节点路径固定，内部节点使用内容地址，便于验证完整引用链。
    page_level = 0
    while len(references) > CATALOG_MAX_ITEMS:
        next_level: list[CatalogReference] = []
        for offset in range(0, len(references), CATALOG_MAX_ITEMS):
            chunk = references[offset : offset + CATALOG_MAX_ITEMS]
            branch = _branch_payload(catalog, "leaf" if page_level == 0 else "branch", chunk)
            digest = content_digest(canonical_bytes(branch))
            base = PurePosixPath(index_path).parent
            relative = (base / "_catalog" / f"{digest}.json").as_posix()
            next_level.append(_write_bounded(directory, relative, branch))
        references = next_level
        page_level += 1
    root = _branch_payload(catalog, "index", references, metadata=metadata)
    return _write_bounded(directory, index_path, root)


def _object(value: object, *, code: str) -> JsonObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise IntegrityError(code)
    return cast(JsonObject, value)


# 先按上限读取并校验摘要，之后才解释 JSON。
# 受限常规文件读取同时保护目录边界与链接风险。
# 损坏与格式错误有不同错误码，便于定位存储失效原因。
def load_document(directory: Path, relative: str, *, expected_digest: str) -> JsonObject:
    path = _safe_relative(relative)
    try:
        raw = read_bound_regular_bytes(
            directory, directory.joinpath(*path.parts), max_bytes=CATALOG_MAX_BYTES
        )
    except (OSError, ValueError) as exc:
        raise IntegrityError("machine.store.catalog-read") from exc
    if content_digest(raw) != expected_digest:
        raise IntegrityError("machine.store.catalog-digest")
    try:
        return _object(json.loads(raw), code="machine.store.catalog-json")
    except json.JSONDecodeError as exc:
        raise IntegrityError("machine.store.catalog-json") from exc


# 页内键必须严格递增，首尾声明与真实内容一致。
# 记录数量核对实际列表长度，防止分页跳过被错误计数的条目。
# 页面声明范围必须覆盖其实际有序键，范围索引才能安全裁剪查询。
def _validate_data_document(value: Mapping[str, Any], count: int) -> None:
    """Check sorted record keys and the declared range of a packed data node."""
    if set(value) != {
        "schemaVersion",
        "catalog",
        "nodeType",
        "firstKey",
        "lastKey",
        "recordCount",
        "records",
    }:
        raise IntegrityError("machine.store.catalog-data-fields")
    records = value.get("records")
    if not isinstance(records, list) or not records or len(records) > CATALOG_MAX_ITEMS:
        raise IntegrityError("machine.store.catalog-data-records")
    previous = ""
    for raw in records:
        row = _object(raw, code="machine.store.catalog-data-record")
        if set(row) != {"key", "value"}:
            raise IntegrityError("machine.store.catalog-data-record-fields")
        key = row["key"]
        if (
            not isinstance(key, str)
            or not key
            or previous
            and key <= previous
            or not isinstance(row["value"], dict)
        ):
            raise IntegrityError("machine.store.catalog-data-record-value")
        previous = key
    if (
        count != len(records)
        or value.get("firstKey") != records[0]["key"]
        or value.get("lastKey") != records[-1]["key"]
    ):
        raise IntegrityError("machine.store.catalog-data-range")
    return


# 单条布局仍需闭合字段契约，不能伪装成含任意子引用的分支。
# 溢出记录只有一个逻辑键，不能伪装为可继续遍历的索引节点。
def _validate_record_document(value: Mapping[str, Any], count: int) -> None:
    """An overflow record is a single key/value envelope, never a branch."""
    if set(value) != {
        "schemaVersion",
        "catalog",
        "nodeType",
        "key",
        "recordCount",
        "value",
    }:
        raise IntegrityError("machine.store.catalog-record-fields")
    if not isinstance(value.get("key"), str) or not isinstance(value.get("value"), dict):
        raise IntegrityError("machine.store.catalog-record")
    if count != 1:
        raise IntegrityError("machine.store.catalog-record-count")
    return


# 目录名与模式版本先校验，避免在错误命名空间解释有效 JSON。
# 引用区间不能重叠，子项数量之和必须匹配父节点。
# 布尔值不接受为整数计数，防止宽松 Python 类型关系穿透协议。
# 只有根索引允许元数据，内部节点保持最小封套。
def validate_document(value: Mapping[str, Any], *, expected_catalog: str) -> None:
    """Validate the catalog envelope before interpreting its type-specific closed shape."""

    if value.get("schemaVersion") != SCHEMA_VERSION or value.get("catalog") != expected_catalog:
        raise IntegrityError("machine.store.catalog-envelope")
    node_type = value.get("nodeType")
    count = value.get("recordCount")
    if node_type not in {"index", "branch", "leaf", "data", "record"}:
        raise IntegrityError("machine.store.catalog-node-type")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise IntegrityError("machine.store.catalog-count")
    if node_type == "record":
        _validate_record_document(value, count)
        return
    if node_type == "data":
        _validate_data_document(value, count)
        return
    entries = _catalog_branch_entries(value, node_type)
    total = 0
    previous = ""
    for raw in entries:
        last, item_count = _validate_catalog_reference(raw, previous)
        previous = last
        total += item_count
    if total != count:
        raise IntegrityError("machine.store.catalog-count-mismatch")
    first_key = str(value.get("firstKey") or "")
    last_key = str(value.get("lastKey") or "")
    if entries and (first_key != entries[0]["firstKey"] or last_key != entries[-1]["lastKey"]):
        raise IntegrityError("machine.store.catalog-range")
    if not entries and (first_key or last_key):
        raise IntegrityError("machine.store.catalog-empty-range")


def _catalog_branch_entries(value: Mapping[str, Any], node_type: str) -> list[Any]:
    """分支封套只允许索引节点携带元数据，条目数上限先于逐项验证。"""
    allowed = {
        "schemaVersion",
        "catalog",
        "nodeType",
        "firstKey",
        "lastKey",
        "recordCount",
        "entries",
    }
    if node_type == "index":
        if "metadata" in value:
            allowed.add("metadata")
            if not isinstance(value["metadata"], dict):
                raise IntegrityError("machine.store.catalog-metadata")
    if set(value) != allowed:
        raise IntegrityError("machine.store.catalog-branch-fields")
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) > CATALOG_MAX_ITEMS:
        raise IntegrityError("machine.store.catalog-entries")
    return entries


def _validate_catalog_reference(raw: object, previous: str) -> tuple[str, int]:
    """引用范围必须严格递增；安全路径检查在字段与值验证后进行。"""
    row = _object(raw, code="machine.store.catalog-reference")
    if set(row) != {
        "firstKey",
        "lastKey",
        "recordCount",
        "path",
        "digest",
        "nodeType",
    }:
        raise IntegrityError("machine.store.catalog-reference-fields")
    first = row["firstKey"]
    last = row["lastKey"]
    item_count = row["recordCount"]
    if (
        not isinstance(first, str)
        or not isinstance(last, str)
        or first > last
        or previous
        and first <= previous
        or not isinstance(item_count, int)
        or isinstance(item_count, bool)
        or item_count < 1
        or not isinstance(row["digest"], str)
        or len(row["digest"]) != 64
        or any(character not in "0123456789abcdef" for character in row["digest"])
        or not isinstance(row["path"], str)
        or not isinstance(row["nodeType"], str)
    ):
        raise IntegrityError("machine.store.catalog-reference-value")
    _safe_relative(row["path"])
    return last, item_count


# 完整验证同时收集可达路径，供发布阶段发现多余或缺失文件。
# 重复引用直接失败，也阻止恶意目录形成循环。
# 父子节点的种类、范围与数量逐层核对，摘要正确也不能绕过。
# 关闭记录收集只减少返回内存，仍验证所有可达节点。
def walk_catalog(
    directory: Path,
    *,
    root_path: str,
    root_digest: str,
    expected_catalog: str,
    include_records: bool = True,
    on_progress: Callable[[int], None] | None = None,
) -> tuple[list[tuple[str, JsonObject]], set[str]]:
    """Validate a catalog tree and return sorted record values and reachable paths."""

    pending: list[tuple[str, str, str, str | None, str | None, int | None]] = [
        (root_path, root_digest, "index", None, None, None)
    ]
    records: list[tuple[str, JsonObject]] = []
    visited: set[str] = set()
    while pending:
        relative, digest, expected_node, expected_first, expected_last, expected_count = (
            pending.pop()
        )
        if relative in visited:
            raise IntegrityError("machine.store.catalog-duplicate-reference")
        value = load_document(directory, relative, expected_digest=digest)
        validate_document(value, expected_catalog=expected_catalog)
        if value["nodeType"] != expected_node:
            raise IntegrityError("machine.store.catalog-reference-node")
        current_first = str(value.get("firstKey") or value.get("key") or "")
        current_last = str(value.get("lastKey") or value.get("key") or "")
        if expected_first is not None and (
            current_first != expected_first
            or current_last != expected_last
            or value.get("recordCount") != expected_count
        ):
            raise IntegrityError("machine.store.catalog-reference-range")
        visited.add(relative)
        if on_progress is not None and len(visited) % 128 == 0:
            on_progress(len(visited))
        if value["nodeType"] == "record":
            if include_records:
                records.append((cast(str, value["key"]), cast(JsonObject, value["value"])))
            continue
        if value["nodeType"] == "data":
            if include_records:
                records.extend(
                    (cast(str, row["key"]), cast(JsonObject, row["value"]))
                    for row in cast(list[JsonObject], value["records"])
                )
            continue
        entries = cast(list[JsonObject], value["entries"])
        for row in reversed(entries):
            pending.append(
                (
                    cast(str, row["path"]),
                    cast(str, row["digest"]),
                    cast(str, row["nodeType"]),
                    cast(str, row["firstKey"]),
                    cast(str, row["lastKey"]),
                    cast(int, row["recordCount"]),
                )
            )
    records.sort(key=lambda item: item[0])
    if on_progress is not None:
        on_progress(len(visited))
    return records, visited


# 区间采用左闭右开语义，空边界表示向该方向无限延伸。
def read_catalog_range(
    directory: Path,
    *,
    root_path: str,
    root_digest: str,
    expected_catalog: str,
    start_key: str = "",
    end_key: str = "",
) -> tuple[list[tuple[str, JsonObject]], set[str]]:
    """Read and verify only catalog pages intersecting ``[start_key, end_key)``.

    Empty bounds mean unbounded. Index nodes are always authenticated from the
    root; data pages outside the requested range are never opened.
    """

    return read_catalog_ranges(
        directory,
        root_path=root_path,
        root_digest=root_digest,
        expected_catalog=expected_catalog,
        ranges=((start_key, end_key),),
    )


# 先合并重叠区间，一次索引遍历服务多个过滤范围。
# 二分查找只决定哪些页需要读，每个读到的页仍完整验证。
# 范围之外的数据页不打开，让大目录查询成本随选择范围缩小。
# 返回结果统一按键排序，不受栈遍历或区间输入顺序影响。
def read_catalog_ranges(
    directory: Path,
    *,
    root_path: str,
    root_digest: str,
    expected_catalog: str,
    ranges: Iterable[tuple[str, str]],
) -> tuple[list[tuple[str, JsonObject]], set[str]]:
    """Read a union of authenticated key ranges with one index traversal."""

    # 空或反向的有限区间没有记录，过滤后不应触发无界读取。
    # 重复区间去重，防止同一证据被重复交付。
    raw_ranges = tuple(
        sorted({(start, end) for start, end in ranges if not (end and start and end <= start)})
    )
    if not raw_ranges:
        return [], set()
    merged: list[tuple[str, str]] = []
    for start, end in raw_ranges:
        if not merged or (merged[-1][1] and start > merged[-1][1]):
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (
            previous_start,
            "" if not previous_end or not end else max(previous_end, end),
        )
    # 合并后的区间互不重叠，可用起点数组做二分判断。
    # 页面范围的末端是包含关系，而查询末端仍为开区间。
    starts = [start for start, _end in merged]

    def intersects(first: str, last: str) -> bool:
        index = bisect_right(starts, last) - 1
        return index >= 0 and (not merged[index][1] or first < merged[index][1])

    def includes(key: str) -> bool:
        index = bisect_right(starts, key) - 1
        return index >= 0 and (not merged[index][1] or key < merged[index][1])

    pending: list[tuple[str, str, str, str | None, str | None, int | None]] = [
        (root_path, root_digest, "index", None, None, None)
    ]
    records: list[tuple[str, JsonObject]] = []
    visited: set[str] = set()
    while pending:
        relative, digest, expected_node, expected_first, expected_last, expected_count = (
            pending.pop()
        )
        if relative in visited:
            raise IntegrityError("machine.store.catalog-duplicate-reference")
        value = load_document(directory, relative, expected_digest=digest)
        validate_document(value, expected_catalog=expected_catalog)
        if value["nodeType"] != expected_node:
            raise IntegrityError("machine.store.catalog-reference-node")
        current_first = str(value.get("firstKey") or value.get("key") or "")
        current_last = str(value.get("lastKey") or value.get("key") or "")
        if expected_first is not None and (
            current_first != expected_first
            or current_last != expected_last
            or value.get("recordCount") != expected_count
        ):
            raise IntegrityError("machine.store.catalog-reference-range")
        visited.add(relative)
        if value["nodeType"] == "record":
            key = cast(str, value["key"])
            if includes(key):
                records.append((key, cast(JsonObject, value["value"])))
            continue
        if value["nodeType"] == "data":
            records.extend(
                (cast(str, row["key"]), cast(JsonObject, row["value"]))
                for row in cast(list[JsonObject], value["records"])
                if includes(cast(str, row["key"]))
            )
            continue
        entries = cast(list[JsonObject], value["entries"])
        for row in reversed(entries):
            first = cast(str, row["firstKey"])
            last = cast(str, row["lastKey"])
            if not intersects(first, last):
                continue
            pending.append(
                (
                    cast(str, row["path"]),
                    cast(str, row["digest"]),
                    cast(str, row["nodeType"]),
                    first,
                    last,
                    cast(int, row["recordCount"]),
                )
            )
    records.sort(key=lambda item: item[0])
    return records, visited


__all__ = [
    "CatalogRecord",
    "CatalogReference",
    "canonical_bytes",
    "content_digest",
    "load_document",
    "read_catalog_range",
    "read_catalog_ranges",
    "validate_document",
    "walk_catalog",
    "write_catalog",
]
