"""Modus structural pipeline: cache file syntax, then bind project observations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from modus.machine.corpus.source_snapshot import SourceSnapshot
from modus.machine.facts import native_parser
from modus.machine.facts.contracts import StructuralExtractor
from modus.machine.facts.extraction_cache import (
    extract_files,
    extraction_context,
    read_source_bytes,
)
from modus.machine.facts.native_binding import bind_files
from modus.machine.facts.native_parser import parser_for
from modus.machine.store.ids import make_id

# These module-level names are the extractor targets referenced by
# language-registry.json; capability_for(path).extractor resolves against
# this namespace, so removing or renaming one silently downgrades that
# language to generic-text evidence.
REFERENCE_CONTEXTS = native_parser.REFERENCE_CONTEXTS
extract_markdown = native_parser.extract_markdown
extract_python = parser_for("python")
extract_js = parser_for("javascript")
extract_java = parser_for("java")
extract_go = parser_for("go")
extract_c = parser_for("c")
extract_cpp = parser_for("cpp")
extract_header = parser_for("c")
extract_objc = parser_for("objective-c")
extract_objcpp = parser_for("objective-cpp")
extract_swift = parser_for("swift")
extract_csharp = parser_for("csharp")
extract_kotlin = parser_for("kotlin")
extract_php = parser_for("php")
extract_rust = parser_for("rust")
extract_svelte = parser_for("javascript")
extract_astro = parser_for("typescript")
extract_blade = parser_for("php")


def _get_extractor(path: Path) -> StructuralExtractor:
    from modus.machine.facts.extension_registry import builtin_extensions
    from modus.machine.facts.language_capabilities import capability_for

    registry = builtin_extensions()
    name = capability_for(path).extractor
    return registry.structural_extractors[name].implementation


# 文本回退也使用仓库相对身份，避免不同 checkout 的绝对路径进入图键。
def _normalize_fallback(facts: dict[str, Any], relative: str) -> dict[str, Any]:
    """Adapt text-only parsers to the same file-local boundary."""
    if facts.get("path"):
        return facts
    remap = {
        node["id"]: make_id(relative, node.get("kind", "text"), str(index))
        for index, node in enumerate(facts.get("nodes", ()))
    }
    for node in facts.get("nodes", ()):
        node["id"] = remap[node["id"]]
        node["source_file"] = relative
    for edge in facts.get("edges", ()):
        edge["source"] = remap.get(edge["source"], edge["source"])
        edge["target"] = remap.get(edge["target"], edge["target"])
        edge["source_file"] = relative
    facts["path"] = relative
    return facts


# 框架增强复制节点和边后再加工，文件局部缓存不混入项目绑定结果。
@extraction_context
def extract(
    paths: list[Path],
    cache_root: Path | None = None,
) -> dict[str, Any]:
    """Parse frozen files and recompute project binding as one full derivation.

    Native parsing is file-local. Framework observations are projected after
    parsing because project manifests are binding inputs, not parser inputs.
    """
    from modus.machine.facts.extension_registry import builtin_extensions
    from modus.machine.facts.language_capabilities import capability_for
    from modus.machine.facts.native_parser import PARSER_CONTRACT_VERSION
    from modus.machine.store.fingerprint import extraction_projection_digest

    root = Path(cache_root).resolve() if cache_root else Path.cwd()
    parsed = extract_files(paths, root, _get_extractor)
    projections = {}
    enriched = []
    for path, raw_facts in zip(paths, parsed, strict=True):
        relative = path.relative_to(root).as_posix()
        facts = _normalize_fallback(cast(dict[str, Any], raw_facts), relative)
        projections[relative] = extraction_projection_digest(facts)
        capability = capability_for(path)
        if capability.framework_adapters:
            view = {
                **facts,
                "nodes": [dict(row) for row in facts.get("nodes", ())],
                "edges": [dict(row) for row in facts.get("edges", ())],
            }
            snapshot = SourceSnapshot(path, read_source_bytes(path).decode("utf-8"))
            try:
                invoked: set[int] = set()
                for name in capability.framework_adapters:
                    resolver = builtin_extensions().boundary_resolvers[name].implementation
                    if id(resolver) in invoked:
                        continue
                    invoked.add(id(resolver))
                    view = resolver(snapshot, view)
            except (ImportError, ValueError, RuntimeError) as exc:
                view.setdefault("diagnostics", []).append(
                    {
                        "code": "machine.facts.boundary-observation-partial",
                        "path": relative,
                        "message": type(exc).__name__,
                    }
                )
            enriched.append(view)
        else:
            enriched.append(facts)
    result = bind_files(enriched, root)
    result.update(
        fileFacts=parsed,
        projections=projections,
        parserContract=PARSER_CONTRACT_VERSION,
        input_tokens=0,
        output_tokens=0,
    )
    return result
