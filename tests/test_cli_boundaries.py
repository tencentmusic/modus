"""Terminal isolation, optional analysis dependencies, and bounded input failures."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from _support.paths import REPO_ROOT
from modus.cli import app


# 普通命令在分析依赖完全不可导入时仍应运行。
# 同时保护第三方 Click 命令，防止中文帮助适配修改全局行为。
# 独立进程还能检测 pytest 共享模块缓存掩盖的导入副作用。
def test_ordinary_cli_is_isolated_from_analysis_and_unrelated_click_commands(
    tmp_path: Path,
) -> None:
    # A fresh interpreter detects import-time side effects hidden by pytest's
    # shared module cache, and simulates an installation missing analysis extras.
    program = """
import importlib
import importlib.abc
import sys

import click
from typer.testing import CliRunner

class NoAnalysisImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'modus.machine' or fullname.split('.')[0] in {'networkx', 'tree_sitter'}:
            raise ModuleNotFoundError('analysis dependency unavailable', name=fullname)
        return None

sys.meta_path.insert(0, NoAnalysisImports())
original_help = click.Command.get_help_option
import modus.cli
importlib.reload(modus.cli)
assert click.Command.get_help_option is original_help
unrelated = click.Command('unrelated')
option = unrelated.get_help_option(click.Context(unrelated))
assert option is not None and not option.hidden

runner = CliRunner()
for arguments in ([], ['--help'], ['help'], ['status', '--json'],
                  ['context', 'resolve', 'helper', '--scope', 'project-read']):
    result = runner.invoke(modus.cli.app, arguments)
    assert result.exit_code == 0, (arguments, result.output, result.exception)
assert 'modus.machine' not in sys.modules
"""
    # 子进程明确从当前源码导入，避免误用机器上的另一份安装。
    environment = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    # NOCA:dangerous-subprocess-use-audit(当前解释器仅执行本测试定义的静态程序，不拼接外部输入)
    result = subprocess.run(
        [sys.executable, "-c", program],
        shell=False,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # 普通帮助和读取命令应保持空工作区，不隐式初始化项目。
    assert list(tmp_path.iterdir()) == []


# 输入读取被拒绝时，CLI 返回稳定错误码与错误流消息。
# 禁止泄露 traceback，且不能因失败读取创建其他项目文件。
# 故障只注入目标输入，其他路径继续使用真实文件操作。
def test_knowledge_update_reports_an_unreadable_input_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = tmp_path / "update.json"
    payload.write_text('{"documents": {}}', encoding="utf-8")
    original_open = Path.open

    def deny_payload(path: Path, *args, **kwargs):
        if path == payload:
            raise PermissionError("input access denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_payload)
    result = CliRunner().invoke(
        app, ["-C", str(tmp_path), "knowledge", "update", "--input", str(payload)]
    )

    assert result.exit_code == 3
    assert result.stdout == ""
    assert "input access denied" in result.stderr
    assert "Traceback" not in result.output
    assert list(tmp_path.iterdir()) == [payload]


# 模拟 stat 之后输入增长，验证实际 read 仍受字节上限约束。
# 仅检查初始文件大小不足以保护这一竞态。
# 记录每次读取大小，确保实现没有先无界读入再截断。
def test_knowledge_update_bounds_the_read_when_input_grows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = tmp_path / "update.json"
    payload.write_text('{"documents": {}}', encoding="utf-8")
    limit = 16 * 1024 * 1024
    # 读取轨迹用于证明资源上限作用于 I/O 边界，而非仅作用于输出。
    read_sizes: list[int | None] = []

    class GrowingInput(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            read_sizes.append(size)
            return super().read(size)

    original_open = Path.open

    def growing_payload(path: Path, *args, **kwargs):
        if path == payload:
            return GrowingInput(b" " * (limit + 2))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", growing_payload)
    result = CliRunner().invoke(
        app, ["-C", str(tmp_path), "knowledge", "update", "--input", str(payload)]
    )

    assert result.exit_code == 2
    assert "16 MiB" in result.output
    assert read_sizes and all(size is not None and 0 < size <= limit + 1 for size in read_sizes)
    assert list(tmp_path.iterdir()) == [payload]


# 预览成功后执行写入失败，覆盖确认与修改之间的错误边界。
# 文本与 JSON 两种模式都应保留失败信息及稳定退出码。
# 比较所有文件字节，确认终端错误适配没有留下半完成修改。
@pytest.mark.parametrize("json_output", (False, True))
def test_project_update_failure_keeps_the_cli_error_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, json_output: bool
) -> None:
    import json

    from modus.commands import update
    from modus.commands.init_project import run_init

    run_init(tmp_path, ["codex"])
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(
        update,
        "preview_update",
        lambda *args, **kwargs: {"status": "pending", "installedVersion": "0.0.2"},
    )

    def deny_write(*args, **kwargs):
        raise PermissionError("project write denied")

    monkeypatch.setattr(update, "run_update", deny_write)
    arguments = ["-C", str(tmp_path), "update", "--project", "--yes"]
    if json_output:
        arguments.append("--json")
    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 1
    assert "project write denied" in result.output
    assert "Traceback" not in result.output
    if json_output:
        payload = json.loads(result.stdout)
        assert payload["status"] == "error"
        assert payload["applied"] is False
        assert payload["scope"] == "project"
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_anchor_routing_without_parser_reports_gap_and_keeps_current_source_hint(
    tmp_path: Path,
) -> None:
    """普通检索在声明解析器不可用时仍可定位，但不能声称锚点已核验。"""
    source = tmp_path / "Runner.java"
    source.write_text("class Runner { void run() {} }\n", encoding="utf-8")
    document = tmp_path / "modus/knowledge/domain/core/references/api.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        "---\nanchors:\n  locations:\n    - path: Runner.java\n      symbol: Runner.run\n      startLine: 1\n---\n# 运行\nRunner.run 执行任务。\n",
        encoding="utf-8",
    )
    original = document.read_bytes()
    program = """
import importlib.abc
import json
import sys
from typer.testing import CliRunner
class NoParser(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'modus.machine' or fullname.split('.')[0] in {'networkx', 'tree_sitter'}:
            raise ModuleNotFoundError('parser unavailable', name=fullname)
sys.meta_path.insert(0, NoParser())
from modus.cli import app
result = CliRunner().invoke(app, ['context', 'resolve', 'Runner.run', '--scope', 'project-read'])
assert result.exit_code == 0, (result.output, result.exception)
context = json.loads(result.output)
assert any('anchor_verification_unavailable' in gap.get('reason', '') for gap in context['groundingGaps'])
sources = [row for row in context['evidence'] if row.get('layer') == 'source']
assert sources and all('sourceLocation' not in row['scoreSignals'] for row in sources)
assert 'modus.machine' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        shell=False,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert document.read_bytes() == original
    assert not (tmp_path / "modus/.cache").exists()
