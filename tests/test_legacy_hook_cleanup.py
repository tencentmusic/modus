"""旧 hook 退役通过真实安装、升级、预览和卸载验证所有权与恢复。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from modus import __version__
from modus.activation_guidance import MODUS_ENTRY_HINT
from modus.cli import app
from modus.commands.init_project import run_init
from modus.commands.uninstall import apply_uninstall, plan_uninstall
from modus.commands.update import preview_update, run_update
from modus.legacy_hooks import clean_legacy_hook_config
from modus.manifest import Manifest
from modus.paths import ModusPaths
from modus.platforms import available_platforms, get_adapters
from modus.platforms.sections import inject_section

# 固定旧版磁盘合同，测试不依赖已删除的生成器。
_CONFIGS = {
    ".claude/settings.json": ("hooks/claude-settings.json", "SessionStart"),
    ".codex/hooks.json": ("hooks/codex-hooks.json", "SessionStart"),
    ".agents/hooks.json": ("hooks/codex-hooks.json", "SessionStart"),
    ".cursor/hooks.json": ("hooks/cursor-hooks.json", "sessionStart"),
    ".codebuddy/settings.json": ("hooks/codebuddy-hooks.json", "SessionStart"),
}
_SCRIPTS = [f".modus/hooks/{name}" for name in ("run-hook.cmd", "session-start", "modus-hook.py")]
_COMMAND = {"type": "command", "command": ".modus/hooks/run-hook.cmd runtime --platform codex"}


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _install_legacy(root: Path, version: str = __version__) -> Manifest:
    run_init(root, available_platforms())
    paths = ModusPaths.for_root(root)
    manifest = Manifest.read(paths)
    manifest.framework_version = version
    for relative, (template, event) in _CONFIGS.items():
        config = {"hooks": {event: [_COMMAND]}}
        text = json.dumps(config)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
        manifest.add_file(relative, text, template)
    for relative in _SCRIPTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = "old managed launcher\n"
        target.write_text(text, encoding="utf-8", newline="")
        manifest.add_file(relative, text, f"hooks/{target.name}")
    for section in list(manifest.sections):
        content = "# Modus\nSessionStart injects <MODUS_CONTEXT>.\n"
        block = inject_section(root / section.path, section.marker, content)
        manifest.add_section(section.path, section.marker, block)
    manifest.write(paths)
    return manifest


def test_fresh_install_uses_resident_guidance_without_creating_hooks(tmp_path: Path) -> None:
    run_init(tmp_path, available_platforms())
    assert not (tmp_path / ".modus/hooks").exists()
    assert all(not (tmp_path / relative).exists() for relative in _CONFIGS)
    manifest = Manifest.read(ModusPaths.for_root(tmp_path))
    assert all(not entry.template.startswith("hooks/") for entry in manifest.files)
    for adapter in get_adapters(available_platforms()):
        text = (tmp_path / adapter.layout.instructions.path).read_text(encoding="utf-8")
        assert MODUS_ENTRY_HINT in text
        assert "SessionStart" not in text and "<MODUS_CONTEXT>" not in text


def test_fresh_install_and_update_leave_unmanaged_host_configs_untouched(tmp_path: Path) -> None:
    for relative in _CONFIGS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"{user-owned, even if malformed}")
    before = _snapshot(tmp_path)
    run_init(tmp_path, available_platforms())
    assert run_update(tmp_path)["status"] == "up-to-date"
    apply_uninstall(plan_uninstall(tmp_path))
    assert all(
        (tmp_path / relative).read_bytes() == content for relative, content in before.items()
    )


@pytest.mark.parametrize("version", [__version__, "0.0.4"])
def test_update_retires_legacy_configs_scripts_and_instructions_with_readonly_preview(
    tmp_path: Path, version: str
) -> None:
    _install_legacy(tmp_path, version)
    # 外部配置在安装后添加，不能因整个文件摘要变化而漏掉 Modus 条目。
    target = tmp_path / ".claude/settings.json"
    mixed_commands = [{"command": "team-before"}, _COMMAND, {"command": "team-after"}]
    config = {
        "permissions": {"allow": ["Read"]},
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": mixed_commands,
                },
                {"command": "external", "description": _COMMAND["command"]},
            ],
            "Stop": [{"command": "team-stop"}],
            "UserPromptSubmit": [],
        },
    }
    target.write_text(json.dumps(config), encoding="utf-8")
    before = _snapshot(tmp_path)
    preview = preview_update(tmp_path)
    assert preview["status"] == "updated"
    assert _snapshot(tmp_path) == before

    result = CliRunner().invoke(
        app, ["-C", str(tmp_path), "update", "--project", "--yes", "--json"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["status"] == "updated"
    assert set(report["removedFiles"]) == {*_CONFIGS, *_SCRIPTS}
    assert report["removedFiles"] == preview["removedFiles"]
    assert report["removedDirectories"] == [".modus/hooks"]
    assert not (tmp_path / ".modus/hooks").exists()
    mixed_commands.pop(1)
    assert json.loads(target.read_text(encoding="utf-8")) == config
    assert all(
        not (tmp_path / relative).exists()
        for relative in _CONFIGS
        if relative != ".claude/settings.json"
    )
    manifest = Manifest.read(ModusPaths.for_root(tmp_path))
    assert all(not entry.template.startswith("hooks/") for entry in manifest.files)
    for section in manifest.sections:
        assert "SessionStart" not in (tmp_path / section.path).read_text(encoding="utf-8")
    after = _snapshot(tmp_path)
    assert run_update(tmp_path)["status"] == "up-to-date"
    assert _snapshot(tmp_path) == after


@pytest.mark.parametrize(
    "raw",
    [
        b"{broken",
        b"[]",
        b"\xff",
        b'{"hooks": []}',
        b'{"hooks": {"SessionStart": {}}}',
        b'{"hooks": {"SessionStart": [{"hooks": {}}]}}',
        b'{"hooks": {}, "hooks": {"SessionStart": []}}',
    ],
)
def test_update_preserves_unreadable_legacy_config_and_retries_after_repair(
    tmp_path: Path, raw: bytes
) -> None:
    _install_legacy(tmp_path)
    relative = ".codex/hooks.json"
    target = tmp_path / relative
    target.write_bytes(raw)
    report = run_update(tmp_path)
    assert report["status"] == "partial"
    assert relative in report["userEditedFiles"]
    assert target.read_bytes() == raw
    assert Manifest.read(ModusPaths.for_root(tmp_path)).managed_file(relative) is not None
    target.write_text(json.dumps({"hooks": {"SessionStart": [_COMMAND]}}), encoding="utf-8")
    assert run_update(tmp_path)["status"] == "updated"
    assert not target.exists()


@pytest.mark.parametrize("edit_launcher", [False, True])
def test_update_preserves_edited_launcher_and_untracked_scripts(
    tmp_path: Path, edit_launcher: bool
) -> None:
    _install_legacy(tmp_path)
    launcher = tmp_path / _SCRIPTS[0]
    if edit_launcher:
        launcher.write_bytes(b"user customization")
    foreign = launcher.parent / "team.sh"
    foreign.write_bytes(b"team script")
    preview = preview_update(tmp_path)
    report = run_update(tmp_path)
    assert report["status"] == ("partial" if edit_launcher else "updated")
    assert report["userEditedFiles"] == ([_SCRIPTS[0]] if edit_launcher else [])
    if edit_launcher:
        assert launcher.read_bytes() == b"user customization"
    else:
        assert not launcher.exists()
    assert foreign.read_bytes() == b"team script"
    assert report["removedDirectories"] == preview["removedDirectories"] == []
    assert all(not (tmp_path / relative).exists() for relative in _CONFIGS)


def test_update_rollback_restores_retired_configs_scripts_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modus.commands import update

    _install_legacy(tmp_path)
    before = _snapshot(tmp_path)

    def fail_after_reconciliation(paths: ModusPaths) -> None:
        assert not (paths.root / ".modus/hooks").exists()
        raise OSError("simulated commit failure")

    monkeypatch.setattr(update, "reconcile_optional_config", fail_after_reconciliation)
    with pytest.raises(OSError, match="simulated commit failure"):
        run_update(tmp_path)
    assert _snapshot(tmp_path) == before


def test_legacy_uninstall_removes_only_modus_commands(tmp_path: Path) -> None:
    _install_legacy(tmp_path)
    for relative, (_, event) in _CONFIGS.items():
        config = {
            "custom": True,
            "hooks": {event: [{"matcher": "startup", "hooks": [_COMMAND, {"command": "team"}]}]},
        }
        (tmp_path / relative).write_text(json.dumps(config), encoding="utf-8")
    before = _snapshot(tmp_path)
    plan = plan_uninstall(tmp_path)
    assert _snapshot(tmp_path) == before
    assert set(_CONFIGS) <= set(plan.removed_files)
    assert apply_uninstall(plan)["status"] == "uninstalled"
    for relative, (_, event) in _CONFIGS.items():
        assert json.loads((tmp_path / relative).read_text(encoding="utf-8")) == {
            "custom": True,
            "hooks": {event: [{"matcher": "startup", "hooks": [{"command": "team"}]}]},
        }


@pytest.mark.parametrize("linked_parent", [False, True])
def test_update_refuses_linked_legacy_config(tmp_path: Path, linked_parent: bool) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _install_legacy(project)
    external = tmp_path / "external"
    external.mkdir()
    target = project / ".codex/hooks.json"
    destination = external / "hooks.json"
    target.rename(destination)
    try:
        if linked_parent:
            target.parent.rmdir()
            target.parent.symlink_to(external, target_is_directory=True)
        else:
            target.symlink_to(destination)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")
    before = _snapshot(project)
    external_before = destination.read_bytes()
    assert run_update(project)["status"] == "blocked"
    assert _snapshot(project) == before
    assert destination.read_bytes() == external_before


@pytest.mark.parametrize("version", [1, 2])
def test_cursor_cleanup_only_removes_its_generated_default_version(
    tmp_path: Path, version: int
) -> None:
    target = tmp_path / ".cursor/hooks.json"
    target.parent.mkdir()
    target.write_text(
        json.dumps({"version": version, "hooks": {"sessionStart": [_COMMAND]}}), encoding="utf-8"
    )
    assert clean_legacy_hook_config(target)
    if version == 1:
        assert not target.exists()
    else:
        assert json.loads(target.read_text(encoding="utf-8")) == {"version": 2}


@pytest.mark.parametrize(
    "content", ['{ "version": 1 }\n', '{ "hooks": {"SessionStart": []}, "custom": true }\n']
)
def test_cleanup_without_modus_entries_preserves_exact_bytes(tmp_path: Path, content: str) -> None:
    target = tmp_path / "hooks.json"
    target.write_text(content, encoding="utf-8", newline="")
    assert clean_legacy_hook_config(target)
    assert target.read_bytes() == content.encode()
