"""DSH 投影复用安装事务与知识边界，并可和 Codex 共存。"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from modus.cli import app
from modus.commands.init_project import InitConflictError, run_init
from modus.commands.uninstall import apply_uninstall, plan_uninstall
from modus.commands.update import run_update
from modus.manifest import Manifest, hash_file
from modus.paths import PLATFORM_OUTPUT_DIRS, ModusPaths
from modus.platforms import get_adapters
from modus.scaffold import TemplateCatalog
from modus.skillmd import split_frontmatter
from modus.surface import CORE_SKILLS, EXPLICIT_SKILLS, MODEL_INVOCABLE_SKILLS


def test_dsh_cli_install_and_update_preserve_invocation_policy(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["-C", str(tmp_path), "init", "--platform", "dsh"])
    assert result.exit_code == 0, result.output
    assert "AGENTS.md" in result.output
    manifest = Manifest.read(ModusPaths.for_root(tmp_path))
    assert manifest.platforms == ["dsh"]
    assert ".dsh" in PLATFORM_OUTPUT_DIRS
    assert not (tmp_path / ".dsh/settings.json").exists()
    for skill in TemplateCatalog().load_skills(CORE_SKILLS):
        relative = f".dsh/skills/{skill.name}/SKILL.md"
        target = tmp_path / relative
        metadata, body = split_frontmatter(target.read_text(encoding="utf-8"))
        assert metadata["user-invocable"] == (skill.name in EXPLICIT_SKILLS)
        assert metadata["disable-model-invocation"] == (skill.name not in MODEL_INVOCABLE_SKILLS)
        assert body == split_frontmatter(skill.body)[1]
        entry = manifest.managed_file(relative)
        assert entry is not None and entry.sha256 == hash_file(target)
        for support in skill.support_files:
            assert (target.parent / support).is_file()
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    run_init(tmp_path, ["dsh"])
    assert {p: p.read_bytes() for p in before} == before
    assert run_update(tmp_path)["status"] == "up-to-date"


def test_dsh_coexists_with_codex_and_uninstall_retains_user_assets(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Team rules\n", encoding="utf-8")
    run_init(tmp_path, ["codex", "dsh"])
    paths = ModusPaths.for_root(tmp_path)
    manifest = Manifest.read(paths)
    assert [s.marker for s in manifest.sections if s.path == "AGENTS.md"] == ["modus"]
    shared_instructions = agents.read_bytes()
    get_adapters(["dsh"])[0].uninstall(paths, manifest)
    assert agents.read_bytes() == shared_instructions
    assert manifest.platforms == ["codex"]
    assert (tmp_path / ".agents/skills/using-modus/SKILL.md").exists()
    manifest.write(paths)
    run_init(tmp_path, ["codex", "dsh"])
    personal = tmp_path / ".dsh/skills/team/SKILL.md"
    personal.parent.mkdir(parents=True)
    personal.write_text("Team skill\n", encoding="utf-8")
    profile = tmp_path / ".dsh/cordis.patch.yml"
    profile.write_text("[]\n", encoding="utf-8")
    knowledge = paths.knowledge_dir / "team-note.md"
    knowledge.write_text("Business knowledge\n", encoding="utf-8")
    edited = tmp_path / ".dsh/skills/modus-init/SKILL.md"
    edited.write_text("My workflow\n", encoding="utf-8")
    update = run_update(tmp_path)
    assert edited.relative_to(tmp_path).as_posix() in update["userEditedFiles"]
    assert edited.read_text(encoding="utf-8") == "My workflow\n"
    plan = plan_uninstall(tmp_path)
    assert plan.removed_sections.count("AGENTS.md#modus") == 1
    apply_uninstall(plan)
    assert agents.read_text(encoding="utf-8") == "# Team rules\n"
    assert personal.read_text(encoding="utf-8") == "Team skill\n"
    assert not edited.exists()  # 显式卸载按现有契约移除受管投影。
    assert profile.read_text(encoding="utf-8") == "[]\n"
    assert knowledge.read_text(encoding="utf-8") == "Business knowledge\n"


@pytest.mark.parametrize("platforms", [["codex", "dsh"], ["dsh", "codex"]])
def test_shared_instructions_survive_until_the_last_adapter_is_uninstalled(
    tmp_path: Path, platforms: list[str]
) -> None:
    run_init(tmp_path, platforms)
    paths = ModusPaths.for_root(tmp_path)
    manifest = Manifest.read(paths)
    agents = tmp_path / "AGENTS.md"
    before = agents.read_bytes()
    assert before.count(b"<!-- MODUS:BEGIN ") == 1
    first, last = get_adapters(platforms)

    assert not first.preview_uninstall(manifest)[1]
    first.uninstall(paths, manifest)
    assert agents.read_bytes() == before
    assert manifest.platforms == [last.name]
    assert (tmp_path / last.layout.skills_root / "using-modus/SKILL.md").is_file()
    assert not (tmp_path / first.layout.skills_root / "using-modus/SKILL.md").exists()

    assert last.preview_uninstall(manifest)[1] == manifest.sections
    last.uninstall(paths, manifest)
    assert not agents.exists()
    assert manifest.platforms == []
    assert manifest.sections == []


@pytest.mark.parametrize("remaining", ["codex", "dsh"])
@pytest.mark.parametrize("edited", [False, True])
def test_shared_instructions_are_preserved_across_platform_changes_and_updates(
    tmp_path: Path, remaining: str, edited: bool
) -> None:
    run_init(tmp_path, [remaining])
    paths = ModusPaths.for_root(tmp_path)
    agents = tmp_path / "AGENTS.md"
    original_sections = Manifest.read(paths).sections
    if edited:
        agents.write_text(
            agents.read_text(encoding="utf-8").replace("## Modus", "## Team Modus"),
            encoding="utf-8",
        )
    before = agents.read_bytes()

    for platforms in (["codex", "dsh"], [remaining]):
        run_init(tmp_path, platforms)
        manifest = Manifest.read(paths)
        assert manifest.platforms == platforms
        assert manifest.sections == original_sections
        assert agents.read_bytes() == before
        update = run_update(tmp_path)
        assert update["status"] == ("partial" if edited else "up-to-date")
        assert update["userEditedFiles"] == (["AGENTS.md"] if edited else [])
        assert agents.read_bytes() == before


def test_dsh_unmanaged_skill_collision_fails_before_install(tmp_path: Path) -> None:
    target = tmp_path / ".dsh/skills/using-modus/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("user-owned", encoding="utf-8")
    with pytest.raises(InitConflictError):
        run_init(tmp_path, ["dsh"])
    assert target.read_text(encoding="utf-8") == "user-owned"
    assert not (tmp_path / ".modus").exists()
