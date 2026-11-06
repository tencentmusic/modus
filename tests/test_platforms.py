"""Architecture and safety contracts for the host projection boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from modus.manifest import hash_file
from modus.platforms import (
    BUILTIN_REGISTRY,
    PlatformRegistry,
    ProjectionConfigurationError,
    Skill,
    UnknownPlatformError,
    available_platforms,
    get_adapters,
)
from modus.platforms.claude import ClaudeAdapter
from modus.platforms.codex import CodexAdapter
from modus.platforms.sections import SectionIntegrityError, inject_section, remove_section
from modus.scaffold import TemplateCatalog, scaffold_project
from modus.skillmd import split_frontmatter
from modus.surface import CORE_SKILLS


# 注册表统一安装平台词汇；Codex 与 DSH 共用指令区块，技能目录独立。
def test_builtin_registry_covers_platforms_and_separates_skill_roots() -> None:
    expected = ["claude", "codebuddy", "codex", "cursor", "dsh"]
    assert sorted(BUILTIN_REGISTRY.names) == available_platforms() == expected
    adapters = get_adapters(expected)
    assert [adapter.name for adapter in adapters] == expected
    assert len({adapter.layout.skills_root for adapter in adapters}) == len(adapters)
    assert (
        get_adapters(["codex"])[0].layout.instructions
        == get_adapters(["dsh"])[0].layout.instructions
    )


# 自定义注册表应拥有独立目录，不向内置全局状态追加类型。
# 未知平台错误携带可用列表，让 CLI 能提供具体恢复建议。
def test_registry_is_extensible_without_mutating_the_builtin_catalog() -> None:
    class ExampleAdapter(CodexAdapter):
        name = "example"

    registry = PlatformRegistry([ExampleAdapter])
    assert [adapter.name for adapter in registry.create(["example"])] == ["example"]
    assert "example" not in BUILTIN_REGISTRY.names

    with pytest.raises(UnknownPlatformError) as error:
        registry.create(["missing"])
    assert error.value.unknown == ("missing",)
    assert error.value.available == ("example",)


# 构造后修改调用者字典，验证模型保存快照而非共享可变引用。
# 路径穿越在投影模型边界拒绝，不能留给最终写文件时处理。
def test_projection_models_reject_path_traversal_and_snapshot_support_files() -> None:
    source = {"references/context.md": "context"}
    skill = Skill("example-skill", "Example", "# Example", source)
    source["references/context.md"] = "mutated"
    assert skill.support_files["references/context.md"] == "context"

    with pytest.raises(ProjectionConfigurationError, match="项目相对"):
        Skill("example-skill", "Example", "# Example", {"../outside.md": "unsafe"})


# 共享指令文件中只有成对标记的片段属于 Modus。
# 先验证重复更新与删除可逆，再验证不完整标记不会触发猜测性修复。
def test_section_editor_preserves_foreign_text_and_fails_closed_on_bad_markers(
    tmp_path: Path,
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# Team rules\n", encoding="utf-8")
    inject_section(target, "example-section", "Modus rules")
    inject_section(target, "example-section", "Updated rules")
    assert target.read_text(encoding="utf-8").count("MODUS:BEGIN example-section") == 1

    remove_section(target, "example-section")
    assert target.read_text(encoding="utf-8") == "# Team rules\n"

    target.write_text("<!-- MODUS:BEGIN example-section -->\n", encoding="utf-8")
    with pytest.raises(SectionIntegrityError, match="不完整或重复"):
        inject_section(target, "example-section", "must not be appended")
    assert target.read_text(encoding="utf-8") == "<!-- MODUS:BEGIN example-section -->\n"


def test_installed_skills_keep_host_invocation_policy_and_manifest_hashes(tmp_path: Path) -> None:
    expected = {
        "using-modus": (False, False),
        "modus-init": (True, True),
        "modus-reinit": (True, True),
        "modus-update-knowledge": (True, False),
        "modus-sync-knowledge": (False, False),
    }
    manifest = scaffold_project(tmp_path, available_platforms())
    projected: dict[str, bytes] = {}
    for skill in TemplateCatalog().load_skills(CORE_SKILLS):
        relative = f".claude/skills/{skill.name}/SKILL.md"
        target = tmp_path / relative
        metadata, body = split_frontmatter(target.read_text(encoding="utf-8"))
        assert metadata["user-invocable"] is expected[skill.name][0]
        assert metadata["disable-model-invocation"] is expected[skill.name][1]
        assert body == split_frontmatter(skill.body)[1]
        managed = manifest.managed_file(relative)
        assert managed is not None and managed.sha256 == hash_file(target)
        projected[relative] = target.read_bytes()
        for root in (".modus", ".agents", ".cursor", ".codebuddy"):
            neutral = tmp_path / root / "skills" / skill.name / "SKILL.md"
            assert neutral.read_text(encoding="utf-8") == skill.body

    second = scaffold_project(tmp_path, available_platforms())
    assert second.to_dict() == manifest.to_dict()
    assert {path: (tmp_path / path).read_bytes() for path in projected} == projected


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("existing_key", ["user-invocable", "disable-model-invocation"])
def test_claude_metadata_preserves_explicit_keys_nested_values_and_body(
    newline: str, existing_key: str
) -> None:
    body = "\n# 示例\n\n```yaml\nuser-invocable: false\n---\n```\n\n".replace("\n", newline)
    header = (
        "---\nname: example\n"
        f"'{existing_key}': false\n"
        "description: |\n  保留多行内容\n  第二行\n"
        "metadata:\n  user-invocable: false\n  disable-model-invocation: false\n---\n"
    ).replace("\n", newline)
    adapter = ClaudeAdapter()
    result = adapter._post_process_skill_md(
        header + body, model_invocable=False, user_invocable=True
    )
    metadata, rendered_body = split_frontmatter(result)
    assert metadata[existing_key] is False
    other_key = "disable-model-invocation" if existing_key == "user-invocable" else "user-invocable"
    assert metadata[other_key] is True
    assert metadata["metadata"] == {
        "user-invocable": False,
        "disable-model-invocation": False,
    }
    assert metadata["description"] == "保留多行内容\n第二行\n"
    assert rendered_body == body
    assert result.startswith(f"---{newline}")
    if newline == "\r\n":
        assert "\n" not in result.replace("\r\n", "")
    assert adapter._post_process_skill_md(result) == result


@pytest.mark.parametrize(
    "content",
    [
        "# 正文\n---\n示例\n---\n",
        "---\nname: missing-end\n",
        "---\nname: [broken\n---\n正文\n",
        "---\n- not-a-mapping\n---\n正文\n",
        "---\nname: wrong-fence\n---suffix\n正文\n",
        "---\nname: example\nmetadata: &loop [*loop]\n---\n正文\n",
    ],
)
def test_claude_metadata_leaves_unparseable_input_unchanged(content: str) -> None:
    assert ClaudeAdapter()._post_process_skill_md(content) == content
