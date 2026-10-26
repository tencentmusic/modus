"""Deterministic source-role and primary build-unit classification."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

from modus.machine.languages import capability_for
from modus.machine.store.contracts import AnalysisSourceRole

_CONFIG_NAMES = frozenset(
    {
        "dockerfile",
        "makefile",
        "cmakelists.txt",
        "pyproject.toml",
        "package.json",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "podfile",
        "podfile.lock",
        "package.swift",
        "package.resolved",
        "go.mod",
        "cargo.toml",
    }
)
_CONFIG_SUFFIXES = frozenset(
    {
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".properties",
        ".json",
        ".pbxproj",
        ".xcconfig",
        ".xcscheme",
        ".xcworkspacedata",
        ".podspec",
        ".modulemap",
    }
)
_GENERATED_PARTS = frozenset(
    {"dist", "build", "target", "generated", "gen", "vendor", "node_modules"}
)
_FIXTURE_PARTS = frozenset(
    {"fixture", "fixtures", "sample", "samples", "example", "examples", "testdata"}
)
_TEST_PARTS = frozenset(
    {
        "test",
        "tests",
        "__tests__",
        "spec",
        "specs",
        "commontest",
        "androidtest",
        "androidunittest",
        "androidinstrumentedtest",
        "iostest",
        "iosarm64test",
        "iossimulatorarm64test",
        "iosx64test",
        "jvmtest",
        "desktoptest",
    }
)


# 分类顺序有意固定：文档、生成文件、夹具、测试先于普通运行源码。
# 路径角色决定后续提案如何使用证据，不改变文件本身的内容身份。
# 无专用提取器时标记 opaque，避免把通用文本片段当作运行代码。
# 匹配使用大小写折叠，但输出路径仍保留原始规范形式。
def source_role(path: str) -> AnalysisSourceRole:
    candidate = PurePosixPath(path)
    folded = tuple(part.casefold() for part in candidate.parts)
    name = candidate.name.casefold()
    if capability_for(path).role == "document":
        return "document"
    if any(part in _GENERATED_PARTS for part in folded) or any(
        token in name for token in (".generated.", ".gen.", "_generated.")
    ):
        return "generated"
    if any(part in _FIXTURE_PARTS for part in folded):
        return "fixture"
    if (
        any(part in _TEST_PARTS for part in folded)
        or name.startswith("test_")
        or any(token in name for token in ("_test.", ".test.", ".spec."))
    ):
        return "test"
    if name in _CONFIG_NAMES or candidate.suffix.casefold() in _CONFIG_SUFFIXES:
        return "configuration"
    if capability_for(path).extractor == "extract_generic_text":
        return "opaque"
    return "runtime"


# 同一源码可属于多个编译变体，完整成员关系不能因选择 primary 丢失。
# 主单元优先选择根更深的匹配，再以 ID 打破平局，保证确定性。
# 没有编译单元时生成结构归属，不伪造编译器覆盖。
# 所有路径先排序去重，返回结果不依赖输入容器的遍历顺序。
# 主单元只用于组织展示，不能据此排除其他上下文中的有效观察。
def build_unit_memberships(
    source_paths: Iterable[str],
    units: Iterable[Mapping[str, Any]],
) -> dict[str, tuple[tuple[str, ...], str]]:
    """Return all memberships and one stable primary unit per source path."""

    prepared: list[tuple[str, str, tuple[str, ...]]] = []
    for raw in units:
        unit_id = str(raw.get("id") or "")
        root = str(raw.get("root") or ".").strip("/")
        files = tuple(
            str(value) for value in raw.get("files", ()) if isinstance(value, str) and value
        )
        if unit_id:
            prepared.append((unit_id, root or ".", files))
    result: dict[str, tuple[tuple[str, ...], str]] = {}
    for path in sorted(set(source_paths)):
        matches = [(unit_id, root) for unit_id, root, files in prepared if path in files]
        memberships = tuple(sorted(unit_id for unit_id, _ in matches))
        if matches:
            primary = min(
                matches,
                key=lambda item: (
                    -len(PurePosixPath(item[1]).parts) if item[1] != "." else 0,
                    item[0],
                ),
            )[0]
        else:
            parts = PurePosixPath(path).parts
            structural_root = parts[0] if len(parts) > 1 else "."
            primary = f"structural:{structural_root}"
            memberships = (primary,)
        result[path] = (memberships, primary)
    return result


__all__ = ["build_unit_memberships", "source_role"]
