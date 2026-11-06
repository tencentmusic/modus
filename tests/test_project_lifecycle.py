"""Public CLI, installation, and project-read lifecycle contracts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from modus import __version__, git_hygiene
from modus.cli import app
from modus.cli_commands import uninstall as uninstall_cli
from modus.cli_commands import update as update_cli
from modus.commands import self_update
from modus.commands import status as status_cmd
from modus.commands.init_project import InitFailedError, run_init
from modus.manifest import Manifest
from modus.orchestrator import context_resolver
from modus.paths import ModusPaths
from modus.platforms.codex import CodexAdapter
from modus.surface import CORE_SKILLS

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


# 每个测试复制独立源码项目，安装副作用不污染公共夹具。
@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURES / "simple_service", root)
    return root


# 仅补齐已确认域的必要元数据，使只读检索使用正式知识入口。
# 已确认状态是检索前提，不通过执行创作工作流引入无关副作用。
def _confirm_order_domain(paths: ModusPaths) -> None:
    target = paths.domain_skill("order")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nname: order\nstatus: confirmed\naliases: [order, approve]\nanchors:\n"
        "  paths: [order/order_service.py, order/order_repo.py]\n---\n# Order\n"
    )


# 快照覆盖实际文件字节，Git 索引由专门断言保护。
# 忽略 .git 内部变化，避免无关 Git 元数据使业务断言不稳定。
def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


# 公开命令和版本来自运行中的 CLI，而非静态文档清单。
# 保护初次安装后用户真正可发现的入口。
def test_cli_exposes_the_supported_entrypoints() -> None:
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    for command in ("help", "init", "status", "update", "uninstall"):
        assert command in help_result.output

    version_result = runner.invoke(app, ["--version"])
    assert version_result.exit_code == 0
    assert __version__ in version_result.output


# 状态查询在未安装且含空格中文的目录中也应保持只读。
# 人类文本与 JSON 返回同一服务结果，防止展示分支语义分叉。
# 前后快照将“报告成功”和“无副作用”作为两个独立条件。
def test_status_reports_install_state_without_writing(project: Path) -> None:
    root = project.parent / "项目 status"
    project.rename(root)
    before = _tree_snapshot(root)

    human = runner.invoke(app, ["-C", str(root), "status"])
    machine = runner.invoke(app, ["-C", str(root), "status", "--json"])

    assert human.exit_code == machine.exit_code == 0
    assert "未安装" in human.output
    assert json.loads(machine.output) == status_cmd.project_status(str(root))
    assert _tree_snapshot(root) == before


# 各平台共享权威技能，但分别产出各宿主原生入口。
# 用户自建命令不属于 Modus 清单，重复安装必须保留。
# 比较整个树验证幂等，而非只核对受管文件数量。
# 安装报告与清单一致，消费者无需自行重新统计。
def test_init_projects_the_core_surface_and_is_idempotent(project: Path) -> None:
    platforms = ["claude", "codex", "cursor", "codebuddy", "dsh"]
    first = run_init(project, platforms)
    paths = ModusPaths.for_root(project)
    manifest = Manifest.read(paths)

    assert first["managedFiles"] == len(manifest.files)
    assert manifest.platforms == platforms
    assert {path.name for path in paths.skills_dir.iterdir() if path.is_dir()} == set(CORE_SKILLS)
    for projected in ("AGENTS.md", "CLAUDE.md", ".cursor/rules/modus.mdc", "CODEBUDDY.md"):
        assert (project / projected).is_file()

    user_file = project / ".codebuddy/commands/team-check.md"
    user_file.write_text("Team-owned command\n", encoding="utf-8")
    before = _tree_snapshot(project)
    second = run_init(project, platforms)

    assert second["managedFiles"] == first["managedFiles"]
    assert _tree_snapshot(project) == before
    assert user_file.read_text(encoding="utf-8") == "Team-owned command\n"


# 冲突在首个写入之前发现，错误要指出具体路径和恢复动作。
# 通过 CLI 验证退出码，服务异常本身不足以证明用户体验。
# 已有文件由用户所有，不能通过初始化自动接管。
def test_fresh_init_conflict_is_actionable_and_writes_nothing(project: Path) -> None:
    conflict = project / ".agents/skills/modus-init/SKILL.md"
    conflict.parent.mkdir(parents=True)
    conflict.write_text("user-owned skill\n", encoding="utf-8")
    before = _tree_snapshot(project)

    result = runner.invoke(app, ["-C", str(project), "init", "--all-platforms"])

    assert result.exit_code == 2
    assert "未写入任何文件" in result.output
    assert ".agents/skills/modus-init/SKILL.md" in result.output
    assert "移走或修复冲突文件" in result.output
    assert _tree_snapshot(project) == before


# 父目录软链会改变所有写入目标，必须在预检时拒绝。
# 同时检查项目和外部目标，覆盖隐蔽的越界写入。
# 平台不支持软链时明确跳过该场景，不将环境限制当产品失败。
def test_fresh_init_rejects_symlink_without_side_effects(
    project: Path,
    tmp_path: Path,
) -> None:
    external = tmp_path / "external-agents"
    external.mkdir()
    try:
        (project / ".agents").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")
    symlink_before = _tree_snapshot(project)
    unsafe = runner.invoke(
        app,
        ["-C", str(project), "init", "--platform", "codex"],
    )
    assert unsafe.exit_code == 2
    assert "符号链接" in unsafe.output
    assert not list(external.rglob("*"))
    assert _tree_snapshot(project) == symlink_before


# 默认保留知识体现作者所有权；只有显式参数改变删除计划。
# 项目卸载和个人 CLI 卸载是不同范围，报告不能混入后者。
# JSON 计划保留路径、存在性与处置，便于调用者审查后执行。
def test_uninstall_default_retains_knowledge_and_explicit_flag_plans_deletion(
    tmp_path: Path,
) -> None:
    run_init(tmp_path, ["codex"])

    retained = runner.invoke(
        app,
        ["-C", str(tmp_path), "uninstall", "--project", "--dry-run"],
    )
    deleted = runner.invoke(
        app,
        [
            "-C",
            str(tmp_path),
            "uninstall",
            "--project",
            "--delete-knowledge",
            "--dry-run",
            "--json",
        ],
    )

    assert retained.exit_code == deleted.exit_code == 0
    assert "保留 modus/knowledge" in retained.output
    assert "--delete-knowledge" in retained.output
    assert "Plan 产物" not in retained.output
    assert self_update.PACKAGE_NAME not in retained.output
    payload = json.loads(deleted.stdout)
    project_result = payload["project"]
    assert project_result["knowledge"] == {
        "path": "modus/knowledge",
        "present": True,
        "disposition": "delete",
    }
    assert "modus/knowledge" in project_result["removedDirs"]


# 自动化环境缺少确认机会，必须明确选择预览或授权执行。
# 替换个人更新预览以隔离网络和包管理器，不改变项目维护验证。
# 失败后树保持不变，防止先写入再发现缺少确认。
def test_non_interactive_maintenance_requires_dry_run_or_yes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_init(tmp_path, ["codex"])
    before = _tree_snapshot(tmp_path)
    monkeypatch.setattr(update_cli, "is_interactive", lambda: False)
    monkeypatch.setattr(uninstall_cli, "is_interactive", lambda: False)
    monkeypatch.setattr(
        self_update,
        "preview_self_update",
        lambda **_: {
            "status": "dry-run",
            "applied": False,
            "command": ["uv", "tool", "upgrade", "openmodus"],
        },
    )

    uninstall_result = runner.invoke(
        app,
        ["-C", str(tmp_path), "uninstall", "--project"],
    )
    update_result = runner.invoke(
        app,
        ["update", "--root", str(tmp_path)],
    )

    assert uninstall_result.exit_code == update_result.exit_code == 2
    assert "--dry-run" in uninstall_result.stderr
    assert "--yes" in update_result.stderr
    assert _tree_snapshot(tmp_path) == before


# 分别在平台投影、Git 清理和清单发布阶段注入失败。
# 预置已索引缓存文件，使回滚必须恢复索引而非只重建工作树。
# 比较原始 stage 输出，覆盖 mode、摘要与路径的精确恢复。
# 平台替身仅在目标项目失败，避免破坏用于回滚的独立渲染。
# 完成回滚的报告必须由完整文件快照与索引共同证明。
@pytest.mark.parametrize("failure_stage", ("platform", "git", "manifest"))
def test_init_failure_restores_files_gitignore_and_exact_index(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    tracked_cache = project / "modus/.cache/preexisting.txt"
    tracked_cache.parent.mkdir(parents=True)
    tracked_cache.write_text("keep indexed\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(project), "add", "modus/.cache/preexisting.txt"],
        check=True,
    )
    before_tree = _tree_snapshot(project)
    before_index = subprocess.run(
        ["git", "-C", str(project), "ls-files", "--stage", "-z"],
        check=True,
        capture_output=True,
    ).stdout

    if failure_stage == "platform":
        original = CodexAdapter.project

        def fail_platform(self, paths, *args, **kwargs):
            if paths.root == project.resolve():
                raise OSError("platform projection failed")
            return original(self, paths, *args, **kwargs)

        monkeypatch.setattr(CodexAdapter, "project", fail_platform)
    elif failure_stage == "git":
        monkeypatch.setattr(
            git_hygiene,
            "untrack_local_state",
            lambda _paths: {"status": "blocked", "message": "git hygiene failed"},
        )
    else:
        original_write = Manifest.write

        def fail_manifest(self, paths):
            if paths.root == project.resolve():
                raise OSError("manifest failed")
            return original_write(self, paths)

        monkeypatch.setattr(Manifest, "write", fail_manifest)

    with pytest.raises(InitFailedError, match="已完成回滚"):
        run_init(project, ["codex"])

    after_index = subprocess.run(
        ["git", "-C", str(project), "ls-files", "--stage", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    assert _tree_snapshot(project) == before_tree
    assert after_index == before_index


# 只读检索不得创建缓存目录，也不能消费一次性状态。
# 分别比较文件和目录，空目录副作用不会被字节快照漏过。
def test_initialized_project_read_context_creates_and_consumes_nothing(project: Path) -> None:
    run_init(project, ["codex"])
    paths = ModusPaths.for_root(project)
    _confirm_order_domain(paths)
    before_files = _tree_snapshot(project)
    before_dirs = sorted(
        path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_dir()
    )

    result = context_resolver.resolve_context(
        str(project),
        "read the order approval implementation",
        scope="project-read",
        explicit_paths=["order/order_service.py"],
    )

    after_dirs = sorted(
        path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_dir()
    )
    assert result["scope"] == "project-read"
    assert result["sourceFiles"]
    assert _tree_snapshot(project) == before_files
    assert after_dirs == before_dirs


# 同进程重复检索可能命中内存缓存，仍须确认当前源码摘要。
# 只改源码注释就应改变文件身份，避免缓存把新字节当成旧证据。
def test_project_read_memory_cache_revalidates_current_source(project: Path) -> None:
    run_init(project, ["codex"])
    paths = ModusPaths.for_root(project)
    _confirm_order_domain(paths)
    source = project / "order/order_service.py"
    kwargs: dict = {
        "scope": "project-read",
        "explicit_paths": ["order/order_service.py"],
    }

    first = context_resolver.resolve_context(str(project), "order approval", **kwargs)
    source.write_text(source.read_text(encoding="utf-8") + "\n# changed now\n", encoding="utf-8")
    second = context_resolver.resolve_context(str(project), "order approval", **kwargs)

    first_source = next(
        item
        for item in first["evidence"]
        if item.get("sourceType") == "current-source"
        and item.get("path") == "order/order_service.py"
    )
    second_source = next(
        item
        for item in second["evidence"]
        if item.get("sourceType") == "current-source"
        and item.get("path") == "order/order_service.py"
    )
    assert first_source["digest"] != second_source["digest"]
