"""移动端语言注册、混编、发现与降级的集成契约。"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from modus.machine.corpus.source_roles import source_role
from modus.machine.corpus.source_snapshot import SourceSnapshot
from modus.machine.facts import native_parser
from modus.machine.facts.extraction_cache import _parse_one
from modus.machine.facts.structural import _get_extractor, extract
from modus.machine.languages import CapabilityTier, capability_for, validate_language_registry
from modus.orchestrator.search_policy import iter_source_files
from modus.source_listing import list_source_paths


@pytest.mark.parametrize(
    ("suffix", "language"),
    [(".m", "objective-c"), (".mm", "objective-cpp"), (".swift", "swift"), (".kt", "kotlin")],
)
def test_mobile_registry_has_structural_implementations(suffix: str, language: str) -> None:
    validate_language_registry()
    capability = capability_for("View" + suffix)
    assert capability.language == language
    assert capability.tier == CapabilityTier.STRUCTURAL
    assert capability.extractor != "extract_generic_text"
    assert not capability.compiler_provider


@pytest.mark.parametrize(
    ("source", "language"),
    [
        ("int run(void);", "c"),
        ("namespace UI { class View { public: void run(); }; }", "cpp"),
        ("@interface View : NSObject\n- (void)run;\n@end", "objective-c"),
        ("@protocol Bindable\n- (void)bind;\n@end", "objective-c"),
        ("@class View;\n@protocol Delegate;", "objective-c"),
        ("#import <Foundation/Foundation.h>\ntypedef void(^Done)(int value);", "objective-c"),
        ("namespace UI { class Model {}; }\n@interface View : NSObject\n@end", "objective-cpp"),
        (
            '/* @interface Fake : NSObject */\nconst char *s = "@protocol Fake";\nint run(void);',
            "c",
        ),
    ],
)
def test_header_dispatch_uses_syntax_not_comment_keywords(
    tmp_path: Path, source: str, language: str
) -> None:
    facts = native_parser.parse_file(SourceSnapshot(tmp_path / "View.h", source))
    assert facts["language"] == language
    assert not any(item["name"] == "Fake" for item in facts["declarations"])


def test_objcpp_retains_both_languages_and_original_coordinates(tmp_path: Path) -> None:
    source = """#import "View.h"
namespace Shared { void Run() {} }
@implementation View
- (void)confirm {
    // 中文不能改变字节锚点
    Shared::Run();
    [self refresh];
}
- (void)refresh {}
@end
"""
    facts = native_parser.parse_file(SourceSnapshot(tmp_path / "View.mm", source))
    assert facts["analysisCompleteness"] == "partial"
    assert any(
        row["code"] == "machine.facts.objcpp-structural-partial" for row in facts["diagnostics"]
    )
    assert any(row["qualified_name"] == "Shared.Run" for row in facts["declarations"])
    method = next(row for row in facts["declarations"] if row["name"] == "confirm")
    native = next(row for row in facts["references"] if row["name"] == "Shared.Run")
    assert native["caller_nid"] == method["id"]
    assert native["line"] == 6
    start, end = native["call_site"]["startByte"], native["call_site"]["endByte"]
    assert source.encode()[start:end] == b"Shared::Run()"
    assert any(row["name"] == "self.refresh" for row in facts["references"])
    assert not any(row["name"] == "f" for row in facts["declarations"])


def test_mobile_discovery_agrees_with_ordinary_retrieval(tmp_path: Path) -> None:
    names = ["View.m", "View.mm", "View.h", "Model.hh", "Model.hxx", "View.swift", "View.kt"]
    for name in names:
        (tmp_path / name).write_text("// source\n", encoding="utf-8")
    assert set(list_source_paths(tmp_path)) == set(names)
    assert {path.name for path in iter_source_files(tmp_path)} == set(names)


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("App/View.swift", "runtime"),
        ("App/View.m", "runtime"),
        ("App/View.mm", "runtime"),
        ("src/commonTest/kotlin/ViewTest.kt", "test"),
        ("src/androidInstrumentedTest/kotlin/ViewTest.kt", "test"),
        ("settings.gradle.kts", "configuration"),
        ("Package.swift", "configuration"),
        ("App.xcodeproj/project.pbxproj", "configuration"),
        ("Config/Debug.xcconfig", "configuration"),
        ("App.podspec", "configuration"),
        ("include/gen/Model.swift", "generated"),
        ("LocalPods/Feature/View.m", "runtime"),
    ],
)
def test_mobile_source_roles(path: str, role: str) -> None:
    assert source_role(path) == role


@pytest.mark.parametrize("suffix", [".m", ".swift"])
def test_missing_mobile_grammar_preserves_text_and_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
) -> None:
    original = importlib.import_module

    def unavailable(name: str, package: str | None = None) -> Any:
        if name in {"tree_sitter_objc", "tree_sitter_swift"}:
            raise ImportError("grammar unavailable")
        return original(name, package)

    monkeypatch.setattr(importlib, "import_module", unavailable)
    facts = _parse_one(tmp_path / ("View" + suffix), b"// retained source\n", _get_extractor)
    assert facts["nodes"]
    assert any(row["code"] == "machine.facts.parser-unavailable" for row in facts["diagnostics"])


def test_mixed_project_structural_extraction_has_no_generic_mobile_fallback(tmp_path: Path) -> None:
    sources = {
        "View.h": "@interface View : NSObject\n- (void)refresh;\n@end",
        "View.m": '#import "View.h"\n@implementation View\n- (void)refresh {}\n@end',
        "View.swift": "class Screen { func refresh() {} }",
        "View.kt": "package sample\nclass Screen { fun refresh() {} }",
        "model.hpp": "namespace Shared { class Model { public: void refresh(); }; }",
    }
    paths = []
    for name, content in sources.items():
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path)
    assert len(result["fileFacts"]) == len(sources)
    for facts in result["fileFacts"]:
        assert facts["declarations"], facts["path"]
        assert not any(row.get("kind") == "source-text" for row in facts["nodes"])
    assert any(edge["relation"] == "imports" for edge in result["edges"])

    from modus.machine import (
        AnalysisOptions,
        EvidenceQuery,
        analyze_repository,
        open_analysis,
        query_evidence,
    )

    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(tmp_path, receipt.identity)
    assert query_evidence(bundle, EvidenceQuery(view="scope")).items
    repeated = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    assert repeated.identity == receipt.identity
