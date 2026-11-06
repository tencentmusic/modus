"""Portability preserves mappings even when path normalization creates collisions.

The fixture deliberately includes keys with overlapping portable forms; losing
either value would make the sealed input description incomplete.
"""

from __future__ import annotations

from pathlib import Path

from modus.machine import AnalysisOptions, analyze_repository
from modus.machine.corpus.lifecycle import portable
from modus.machine.store.bundle import _assert_safe_publication
from modus.paths import ModusPaths


def test_portable_normalizes_mapping_keys_and_preserves_collisions(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    paths = ModusPaths.for_root(root)
    first = Path.home() / ".cache/one/settings.xml"
    second = Path.home() / ".cache/two/settings.xml"

    result = portable(
        paths,
        {
            "files": {
                f"external:{first}": {"path": str(first), "digest": "b" * 64},
                f"external:{second}": {"path": str(second), "digest": "a" * 64},
                str(root / "pom.xml"): {"path": str(root / "pom.xml")},
            }
        },
    )

    files = result["files"]
    assert set(files) == {
        "./pom.xml",
        "external:settings.xml#1",
        "external:settings.xml#2",
    }
    assert files["external:settings.xml#1"]["digest"] == "a" * 64
    assert str(root) not in str(result)
    assert str(Path.home()) not in str(result)


def test_portable_embedded_home_paths_pass_publication_without_changing_source_identity(
    tmp_path: Path,
) -> None:
    paths = ModusPaths.for_root(tmp_path)
    source_digest = "a" * 64
    original = {
        "content": f"附件：[{Path.home() / 'Downloads/方案.docx'}]；源码：{tmp_path}/src/A.java",
        "location": {"path": "docs/design.md", "startLine": 3, "endLine": 3},
        "sourceDigest": source_digest,
        "externalPath": str(Path.home() / "Downloads/方案.docx"),
    }

    result = portable(paths, original)

    assert result["content"] == "附件：[<HOME>/Downloads/方案.docx]；源码：./src/A.java"
    assert result["location"] == original["location"]
    assert result["sourceDigest"] == source_digest
    assert result["externalPath"] == "external:方案.docx"
    assert str(Path.home()) in original["content"]
    _assert_safe_publication(paths, result)


def test_material_with_embedded_home_path_can_publish_bundle(tmp_path: Path) -> None:
    material = tmp_path / "design.md"
    original = f"# 设计材料\n\n参考附件：{Path.home() / 'Downloads/方案.docx'}\n"
    material.write_text(original, encoding="utf-8")

    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = tmp_path / "modus/.cache/init-analysis/bundles" / receipt.bundle_digest
    published = b"".join(path.read_bytes() for path in bundle.rglob("*.json"))

    assert str(Path.home()).encode() not in published
    assert b"<HOME>/Downloads/" in published
    assert material.read_text(encoding="utf-8") == original
