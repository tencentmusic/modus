"""Focused regression tests for the repository's public-release gate."""

import stat
import tarfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from release_smoke.archive import extract_wheel, inspect_artifact
from release_smoke.cli import main
from release_smoke.contracts import (
    SDIST_EXCLUSIONS,
    SDIST_ROOT_BOUNDARY,
    SDIST_WORKFLOW_ROOT,
    WHEEL_WORKFLOW_ROOT,
    ArchitectureBoundary,
    ArtifactInventory,
    ArtifactKind,
    ReleaseCheckError,
)
from release_smoke.verification import verify_artifact

PUBLIC_SOURCE_DOCS = (
    "AGENTS.md",
    "skills/modus-development/SKILL.md",
    "docs/skill-authoring.md",
    "docs/knowledge-lifecycle-boundary.md",
    "docs/authoring-contract.md",
)


# wheel 与源码包路径不同，架构见证需显式转换。
# 生成到包内的 schema 不应被当成源码目录中的原文件要求。
def test_source_boundary_maps_package_files_and_omits_generated_resources() -> None:
    boundary = ArchitectureBoundary(
        "example",
        frozenset(
            {
                "modus/runtime.py",
                "modus/_bundled/schemas/generated.yaml",
            }
        ),
    )

    assert boundary.as_source_boundary().members == frozenset({"src/modus/runtime.py"})


# 失败诊断应指出缺失职责，不能只报告压缩包可以打开。
def test_verifier_names_the_missing_architecture_boundary(tmp_path: Path) -> None:
    artifact = tmp_path / "empty.whl"
    artifact.touch()
    inventory = ArtifactInventory(
        path=artifact,
        kind=ArtifactKind.WHEEL,
        members=frozenset(),
        workflow_root=WHEEL_WORKFLOW_ROOT,
    )

    with pytest.raises(ReleaseCheckError, match="public command surface"):
        verify_artifact(inventory)


# 逐个删除公开契约文档，证明每份都属于源码分发的必要内容。
# 其余见证保持有效，避免错误来自不相关的缺失项。
@pytest.mark.parametrize("document", PUBLIC_SOURCE_DOCS)
def test_source_distribution_requires_each_public_contract_document(
    tmp_path: Path, document: str
) -> None:
    artifact = tmp_path / "incomplete.tar.gz"
    artifact.touch()
    inventory = ArtifactInventory(
        path=artifact,
        kind=ArtifactKind.SDIST,
        members=SDIST_ROOT_BOUNDARY.members - {document},
        workflow_root=SDIST_WORKFLOW_ROOT,
    )

    with pytest.raises(ReleaseCheckError, match="source project"):
        verify_artifact(inventory)


# 必须文件也要通过排除策略，防止正反规则互相矛盾。
@pytest.mark.parametrize("document", PUBLIC_SOURCE_DOCS)
def test_public_contract_documents_are_allowed_in_source_distributions(document: str) -> None:
    assert not SDIST_EXCLUSIONS.excludes(document)


# 恶意归档路径在写出前拒绝；检查外部文件不存在以验证副作用。
def test_wheel_extraction_rejects_parent_path_traversal(tmp_path: Path) -> None:
    wheel = tmp_path / "unsafe.whl"
    destination = tmp_path / "package"
    with ZipFile(wheel, mode="w") as archive:
        archive.writestr("../escaped.py", "raise RuntimeError")

    with pytest.raises(ReleaseCheckError, match="不安全、加密或链接路径"):
        extract_wheel(wheel, destination)

    assert not (tmp_path / "escaped.py").exists()


# 重复路径会使检查器与解包器选择不同内容，必须拒绝整个归档。
# 压缩库警告是构造夹具的预期结果，不代表验证已经完成。
def test_wheel_inspection_rejects_duplicate_member_paths(tmp_path: Path) -> None:
    wheel = tmp_path / "duplicate.whl"
    with ZipFile(wheel, mode="w") as archive:
        archive.writestr("modus/__init__.py", "")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("modus/__init__.py", "")

    with pytest.raises(ReleaseCheckError, match="重复归档路径"):
        inspect_artifact(wheel)


# ZIP 权限位也可声明软链，不能仅以文件后缀判断安全性。
# 目标文本不含越界内容，确保拒绝原因是链接类型本身。
def test_wheel_extraction_rejects_symbolic_links(tmp_path: Path) -> None:
    wheel = tmp_path / "linked.whl"
    link = ZipInfo("modus/linked.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(wheel, mode="w") as archive:
        archive.writestr(link, "target.py")

    with pytest.raises(ReleaseCheckError, match="不安全、加密或链接路径"):
        extract_wheel(wheel, tmp_path / "package")


# 源码归档只接受目录与普通文件，拒绝软链等具有额外语义的成员。
# 构造合法根目录，隔离到成员类型这一校验边界。
def test_sdist_inspection_rejects_non_regular_members(tmp_path: Path) -> None:
    sdist = tmp_path / "linked.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        root = tarfile.TarInfo("openmodus-1.0")
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        link = tarfile.TarInfo("openmodus-1.0/linked.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "target.py"
        archive.addfile(link, BytesIO())

    with pytest.raises(ReleaseCheckError, match="不安全或非常规路径"):
        inspect_artifact(sdist)


# CLI 将契约异常转为非零退出码，并将可操作诊断写入 stderr。
# 输出断言保护维护者入口，而非底层异常的堆栈格式。
def test_cli_turns_an_unsupported_artifact_into_an_actionable_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact = tmp_path / "release.zip"
    artifact.touch()

    assert main([str(artifact)]) == 1
    assert "[失败] 不支持的产物：'release.zip'" in capsys.readouterr().err
