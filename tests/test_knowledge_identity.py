"""路径识别、人工所有权与布局核验共享同一 Team Standard 命名空间。"""

from pathlib import Path

import pytest

from modus.knowledge_identity import KnowledgePathIdentity, is_team_standard_path
from modus.knowledge_verification.structure import verify_canonical_paths
from modus.paths import ModusPaths


@pytest.mark.parametrize(
    "relative",
    [
        "modus/knowledge/constraint/team-standard.md",
        "modus/knowledge/constraint/team-standard/database.md",
        "modus/knowledge/constraint/team-standard/legacy/database.md",
    ],
)
def test_team_standard_namespace_has_one_human_identity(tmp_path: Path, relative: str) -> None:
    paths = ModusPaths.for_root(tmp_path)
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text("# 团队规范\n", encoding="utf-8")

    assert is_team_standard_path(relative)
    identity = KnowledgePathIdentity.classify(paths, relative)
    assert identity is not None
    assert identity.path_kind == "constraint"
    assert identity.ownership_plane == "human"
    assert verify_canonical_paths(paths, (target,)) == []


@pytest.mark.parametrize(
    "relative",
    [
        "modus/knowledge/constraint/global-standard.md",
        "modus/knowledge/constraint/team-standard-extra.md",
        "modus/knowledge/constraint/team-standard-extra/database.md",
        "modus/knowledge/constraint/team-standard",
        "modus/knowledge/constraint/team-standard/database.txt",
        "other/modus/knowledge/constraint/team-standard.md",
        "/modus/knowledge/constraint/team-standard.md",
        "modus/knowledge/constraint/team-standard/../database.md",
        "modus/knowledge/constraint/team-standard//database.md",
        "modus/knowledge/constraint/team-standard/./database.md",
        "modus\\knowledge\\constraint\\team-standard.md",
    ],
)
def test_team_standard_namespace_does_not_capture_other_paths(relative: str) -> None:
    assert not is_team_standard_path(relative)


def test_lexical_membership_does_not_grant_filesystem_ownership(tmp_path: Path) -> None:
    paths = ModusPaths.for_root(tmp_path)
    relative = "modus/knowledge/constraint/team-standard/database.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    external = tmp_path / "external.md"
    external.write_text("# 人工文档\n", encoding="utf-8")
    target.symlink_to(external)

    assert is_team_standard_path(relative)
    assert KnowledgePathIdentity.classify(paths, relative) is None
