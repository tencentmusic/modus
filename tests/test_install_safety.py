"""Ownership, concurrency, and path safety at installation boundaries."""

from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from _support.markdown import assert_local_markdown_links_resolve
from modus import __version__
from modus.cli import app
from modus.commands.init_project import InitConflictError, run_init, run_workspace_init
from modus.commands.uninstall import (
    UninstallPlanChangedError,
    apply_uninstall,
    plan_uninstall,
)
from modus.commands.update import preview_update, run_update
from modus.manifest import Manifest
from modus.paths import ModusPaths
from modus.platforms import available_platforms


# 清单外的空文件仍可能属于用户，不能因为没有内容就接管。
# 预览比较完整字节快照，证明检查阶段没有写入。
# 执行阶段保留冲突与用户编辑，同时将部分完成显式反映到报告。
def test_update_preserves_user_edits_and_untracked_collision(tmp_path: Path) -> None:
    run_init(tmp_path, ["codex"])
    paths = ModusPaths.for_root(tmp_path)
    edited = tmp_path / ".agents/skills/modus-init/SKILL.md"
    edited.write_text("my instructions")
    missing = tmp_path / ".modus/skills/using-modus/SKILL.md"
    manifest = Manifest.read(paths)
    manifest.files = [
        item for item in manifest.files if item.path != missing.relative_to(tmp_path).as_posix()
    ]
    manifest.write(paths)
    missing.write_text("")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    preview = preview_update(tmp_path)
    assert preview["status"] == "partial"
    assert before == {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }
    result = run_update(tmp_path)
    assert result["status"] == "partial"
    assert missing.relative_to(tmp_path).as_posix() in result["conflictedFiles"]
    assert edited.relative_to(tmp_path).as_posix() in result["userEditedFiles"]
    assert missing.read_bytes() == b""
    assert edited.read_text(encoding="utf-8") == "my instructions"


@pytest.mark.parametrize("kind", ["project", "workspace"])
@pytest.mark.parametrize("installed_version", [__version__, "0.0.4"])
def test_update_delivers_workflow_changes_to_every_host_and_retains_user_edits(
    tmp_path: Path, kind: str, installed_version: str
) -> None:
    """旧安装与同版本更新均传播全部宿主资产，保留人工内容和成员仓库。"""
    members = [tmp_path / name for name in ("orders", "payments")]
    if kind == "workspace":
        for member in members:
            member.mkdir()
            subprocess.run(["git", "init", "-q", str(member)], check=True)
            (member / "source.txt").write_bytes(b"member-owned\n")
        run_workspace_init(tmp_path, list(available_platforms()), ["orders", "payments"])
    else:
        run_init(tmp_path, list(available_platforms()))
    member_before = {
        p.relative_to(tmp_path): p.read_bytes()
        for member in members
        for p in member.rglob("*")
        if p.is_file()
    }
    paths = ModusPaths.for_root(tmp_path)
    config_before = paths.config_path.read_bytes() if paths.config_path.exists() else None
    manifest = Manifest.read(paths)
    manifest.framework_version = installed_version
    workflow_files = [
        entry for entry in manifest.files if entry.template.startswith(("skills/", "commands/"))
    ]
    expected = {entry.path: (tmp_path / entry.path).read_bytes() for entry in workflow_files}
    added = {
        entry.path
        for entry in workflow_files
        if entry.template.endswith("/authoring/incremental.md")
    }
    assert added
    for entry in workflow_files:
        target = tmp_path / entry.path
        if entry.path in added:
            target.unlink()
        else:
            old_text = "# Previous installed workflow\n"
            target.write_text(old_text, encoding="utf-8", newline="")
            manifest.add_file(entry.path, old_text, entry.template)
    manifest.files = [entry for entry in manifest.files if entry.path not in added]
    manifest.write(paths)

    edited = ".agents/skills/modus-reinit/SKILL.md"
    (tmp_path / edited).write_bytes(b"# User-owned workflow\n")
    paths.constraint_dir.mkdir(parents=True, exist_ok=True)
    paths.team_standard.write_bytes(b"# Human team policy\n")
    topic = paths.constraint_dir / "team-standard/concurrency.md"
    topic.parent.mkdir()
    topic.write_bytes(b"# Human task policy\n")
    card = paths.scope_confirmation_path
    card.parent.mkdir(parents=True, exist_ok=True)
    card_content = (
        b"---\nmodus:\n  authoring:\n    schemaVersion: 2\n    executionMode: serial\n"
        b"    domains:\n      orders:\n        status: pending\n---\n"
        b"# Unfinished scope\nPreserve authorization, progress, and unresolved questions.\n"
    )
    card.write_bytes(card_content)

    run = CliRunner().invoke(app, ["-C", str(tmp_path), "update", "--project", "--yes", "--json"])
    assert run.exit_code == 0, run.output
    result = json.loads(run.stdout)

    assert result["status"] == "partial"
    assert result["userEditedFiles"] == [edited]
    assert added <= set(result["addedFiles"])
    for relative, content in expected.items():
        actual = (tmp_path / relative).read_bytes()
        assert actual == (b"# User-owned workflow\n" if relative == edited else content), relative
        assert_local_markdown_links_resolve(tmp_path / relative, root=tmp_path)
    assert paths.team_standard.read_bytes() == b"# Human team policy\n"
    assert topic.read_bytes() == b"# Human task policy\n"
    assert card.read_bytes() == card_content
    config_after = paths.config_path.read_bytes() if paths.config_path.exists() else None
    assert config_after == config_before
    assert {
        p.relative_to(tmp_path): p.read_bytes()
        for member in members
        for p in member.rglob("*")
        if p.is_file()
    } == member_before

    retry = run_update(tmp_path)
    assert retry["status"] == "partial"
    assert retry["userEditedFiles"] == [edited]
    assert retry["appliedFiles"] == retry["addedFiles"] == []
    assert card.read_bytes() == card_content


# 首次安装同样遵守所有权边界，不能将空文件视为可用路径。
# 拒绝冲突后不应留下管理目录，便于用户安全重试。
def test_fresh_install_preserves_unmanaged_empty_skill(tmp_path: Path) -> None:
    file = tmp_path / ".agents/skills/modus-init/SKILL.md"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"")
    with pytest.raises(InitConflictError):
        run_init(tmp_path, ["codex"])
    assert file.read_bytes() == b""
    assert not (tmp_path / ".modus").exists()


# 预览不是永久删除授权；执行前必须重新确认安装快照。
# 删除一个已预览文件模拟漂移，清单仍在证明没有开始清理。
def test_uninstall_rejects_a_project_that_changes_after_preview(tmp_path: Path) -> None:
    run_init(tmp_path, ["codex"])
    plan = plan_uninstall(tmp_path)
    neutral = next(
        tmp_path / entry.path
        for entry in plan.files
        if entry.path.startswith(".modus/") and (tmp_path / entry.path).is_file()
    )
    neutral.unlink()

    with pytest.raises(UninstallPlanChangedError, match="预览后项目安装发生变化"):
        apply_uninstall(plan)

    assert ModusPaths.for_root(tmp_path).manifest_path.is_file()


# 共享配置损坏时无法辨认所有权，只能进入人工复核。
# 软链本身和目标都必须保留，不能顺着受管路径删除外部内容。
def test_uninstall_preserves_corrupt_shared_config_and_symlink_targets(
    tmp_path: Path,
) -> None:
    run_init(tmp_path, ["codex"])
    hook = tmp_path / ".codex/hooks.json"
    hook.parent.mkdir()
    hook.write_bytes(b"{broken")
    paths = ModusPaths.for_root(tmp_path)
    manifest = Manifest.read(paths)
    manifest.add_file(".codex/hooks.json", "{broken", "hooks/codex-hooks.json")
    manifest.write(paths)
    managed = tmp_path / ".agents/skills/modus-init/SKILL.md"
    external = tmp_path / "external-skill.md"
    external.write_text("external\n", encoding="utf-8")
    managed.unlink()
    try:
        managed.symlink_to(external)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")

    plan = plan_uninstall(tmp_path)
    report = plan.to_report()
    assert ".codex/hooks.json" in report["manualReview"]
    assert ".agents/skills/modus-init/SKILL.md" in report["manualReview"]

    applied = apply_uninstall(plan)
    assert applied["status"] == "uninstalled"
    assert hook.read_bytes() == b"{broken"
    assert managed.is_symlink()
    assert external.read_text(encoding="utf-8") == "external\n"


# 并发结束后核对实际字节与清单摘要，覆盖锁之外的发布一致性。
# 不规定哪个安装先完成，只要求最终产物自洽。
def test_concurrent_installers_serialize_without_corruption(tmp_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_init(tmp_path, ["codex"]), range(2)))
    assert len(results) == 2
    paths = ModusPaths.for_root(tmp_path)
    manifest = Manifest.read(paths)
    assert all(
        hashlib.sha256((tmp_path / item.path).read_bytes()).hexdigest() == item.sha256
        for item in manifest.files
    )


# 清单是持久化输入，反序列化也需重做路径校验。
# 先创建合法安装再篡改单个字段，定位到越界路径这一失败原因。
def test_manifest_rejects_unsafe_managed_paths(tmp_path: Path) -> None:
    run_init(tmp_path, ["codex"])
    paths = ModusPaths.for_root(tmp_path)
    data = Manifest.read(paths).to_dict()
    data["files"][0]["path"] = "../escape"
    with pytest.raises(ValueError, match="受管路径"):
        Manifest.from_dict(data)
