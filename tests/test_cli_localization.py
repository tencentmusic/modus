"""中文用户体验与稳定机器协议共同构成终端边界。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click import command, echo
from click.testing import CliRunner as ClickRunner
from typer.testing import CliRunner

from modus.cli import app
from modus.cli_commands.analysis_display import format_machine_error, format_progress
from modus.cli_commands.presentation import confirm
from modus.commands.init_project import run_init
from modus.machine.errors import DriftError
from modus.workspace_maps import member_markdown, render_maps


# 帮助由真实注册命令生成，中文说明不能翻译实际可输入的标识。
# 根帮助隐藏内部分析入口，内部命令自身的帮助仍须可访问。
# 覆盖空调用和显式 help，避免只有一种入口被本地化。
@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--help"],
        ["help"],
        *[[command, "--help"] for command in ("init", "update", "uninstall", "status")],
        ["help", "/modus-init"],
        ["help", "/modus-reinit"],
        ["help", "/modus-update-knowledge"],
        ["knowledge", "--help"],
        ["internal", "init-analysis", "build", "--help"],
        ["context", "resolve", "--help"],
    ],
)
def test_help_is_chinese_and_keeps_real_command_names(arguments: list[str]) -> None:
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert "用法：" in result.stdout
    assert re.search(r"[\u4e00-\u9fff]", result.stdout)
    for legacy in ("Usage:", "Options", "Show this help message", "Global options"):
        assert legacy not in result.stdout
    if not arguments or arguments in (["--help"], ["help"]):
        assert all(
            name in result.stdout for name in ("init", "update", "/modus-init", "using-modus")
        )
        assert "init-analysis" not in result.stdout


# 用未知命令、缺值、非法枚举等不同解析失败覆盖统一错误边界。
# 保留原 token 便于用户复制修正；中文只用于解释。
# 参数错误写 stderr，stdout 留给可解析的成功数据。
@pytest.mark.parametrize(
    ("arguments", "message", "preserved"),
    [
        (["udpate"], "未知命令", "update"),
        (["--not-an-option"], "未知选项", "--not-an-option"),
        (["init", "--platform"], "缺少参数值", "--platform"),
        (["context", "resolve"], "缺少必填参数", "REQUEST"),
        (["internal", "init-analysis", "build", "--compiler", "bad"], "无效", "--compiler"),
        (["internal", "init-analysis", "select", "--max-items", "many"], "有效整数", "many"),
    ],
)
def test_argument_failures_use_chinese_stderr_without_rewriting_tokens(
    arguments: list[str], message: str, preserved: str
) -> None:
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert message in result.stderr
    assert preserved in result.stderr
    assert "--help" in result.stderr
    assert "Traceback" not in result.output


# 路径包含 Rich 标记和中文，验证提示不会把用户输入当样式执行。
# 失败不能顺手创建目录，否则只读参数校验具有意外副作用。
def test_directory_error_keeps_literal_user_path(tmp_path: Path) -> None:
    missing = tmp_path / "[bold] English data 不存在"
    result = CliRunner().invoke(app, ["-C", str(missing), "status"])
    assert result.exit_code == 2
    assert "路径不存在" in result.stderr
    assert str(missing) in result.stderr
    assert not missing.exists()


# 接受中文和传统 Y/N，同时维持调用者指定的默认选择。
# 无法理解的回答必须重问，不能悄悄接受破坏性动作。
@pytest.mark.parametrize(
    ("answer", "default", "expected"),
    [
        ("是\n", False, True),
        ("否\n", True, False),
        ("y\n", False, True),
        ("N\n", True, False),
        ("\n", False, False),
        ("\n", True, True),
        ("不确定\n否\n", False, False),
    ],
)
def test_confirmation_accepts_chinese_and_preserves_safe_defaults(
    answer: str, default: bool, expected: bool
) -> None:
    @command()
    def confirmation_command() -> None:
        echo(f"结果={confirm('确认操作？', default=default)}")

    result = ClickRunner().invoke(confirmation_command, input=answer)
    assert result.exit_code == 0
    assert f"结果={expected}" in result.stdout
    assert "默认：" in result.stdout
    if answer.startswith("不确定"):
        assert "请输入 是/否" in result.stderr


# 安装产物的说明中文化，文件名和平台协议仍沿用既有身份。
# 检查所有宿主投影，避免仅修改仓库 README 而漏掉真实交付内容。
def test_installation_projects_chinese_guidance_without_renaming_assets(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["-C", str(tmp_path), "init", "--all-platforms"])
    assert result.exit_code == 0, result.output
    assert "项目已接入" in result.stdout and "下一步" in result.stdout
    manifest = json.loads((tmp_path / ".modus/manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["platforms"]) == {"codex", "cursor", "claude", "codebuddy", "dsh"}
    for name in ("AGENTS.md", "CLAUDE.md", "CODEBUDDY.md", ".cursor/rules/modus.mdc"):
        content = (tmp_path / name).read_text(encoding="utf-8")
        assert "默认使用简体中文" in content
        assert "using-modus" in content
    localization = (
        tmp_path / ".modus/skills/using-modus/references/authoring/framework/localization.md"
    )
    assert "只有用户明确指定其他语言时才切换" in localization.read_text(encoding="utf-8")


# 取消是有结果的终端分支，既给中文回执也保留完整项目字节。
# 交互性由测试注入，避免依赖执行环境是否连接终端。
def test_maintenance_cancel_does_not_modify_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modus.cli_commands import uninstall

    run_init(tmp_path, ["codex"])
    snapshot = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(uninstall, "is_interactive", lambda: True)
    result = CliRunner().invoke(app, ["-C", str(tmp_path), "uninstall", "--project"], input="否\n")
    assert result.exit_code == 1
    assert "确认卸载" in result.stdout and "已取消" in result.stdout
    assert snapshot == {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }


# 通过管道输入模拟回车和 Ctrl-C，验证实际键盘流程。
# 不连接用户终端，也不依赖第三方组件默认英文提示。
# 正常选择与取消分别保护列表返回值和退出语义。
@pytest.mark.parametrize("cancel", (False, True))
def test_platform_selection_keyboard_flow_has_chinese_receipt(
    cancel: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from modus.cli_commands.initialize import PlatformPromptChoice, _prompt_platforms

    choices = [PlatformPromptChoice("codex", "Codex"), PlatformPromptChoice("cursor", "Cursor")]
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        pipe.send_text("\x03" if cancel else "\r")
        selected = _prompt_platforms(choices)
    output = capsys.readouterr().out
    if cancel:
        assert selected is None
        assert "已取消平台选择" in output
    else:
        assert selected == ["codex", "cursor"]
        assert "已选择平台：Codex、Cursor" in output
    assert "Cancelled by user" not in output
    assert "selections" not in output


# 进度和机器错误都在 stderr，stdout 不留半截 JSON。
# 注入漂移异常验证稳定错误码不随中文展示变化。
# 异常分支保持目录为空，确保展示适配不会启动额外写入。
def test_analysis_json_keeps_wire_shape_and_chinese_progress_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import modus.machine as machine

    def fail_with_progress(*args, **kwargs):
        kwargs["progress"]("freeze")
        raise DriftError("machine.corpus.drift", details={"paths": ["src/order.py"]})

    monkeypatch.setattr(machine, "analyze_repository", fail_with_progress)
    result = CliRunner().invoke(
        app, ["-C", str(tmp_path), "internal", "init-analysis", "build", "--json"]
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert lines[0] == "初始化分析：冻结源码基线"
    # 只解析最后一行机器错误，前面的中文进度必须保持为独立展示消息。
    # 整体对象比对保护字段名、嵌套关系和原始源码路径不被本地化改写。
    payload = json.loads(lines[-1])
    assert payload == {
        "status": "error",
        "error": {"code": "machine.corpus.drift", "details": {"paths": ["src/order.py"]}},
    }
    human = format_machine_error(DriftError("machine.corpus.drift"))
    assert "重新构建" in human and "machine.corpus.drift" in human
    assert list(tmp_path.iterdir()) == []


# 状态显示名与原对象分离，本地化不得原地改写协议值。
# 仓库路径保持字面形式，避免生成不可访问的导航。
def test_progress_and_workspace_maps_translate_only_display_values() -> None:
    progress = format_progress(
        "package.catalog.evidence-write progress=2/8 unit=records elapsedMs=10"
    )
    assert "进度 2/8 条记录" in progress and "耗时 10 毫秒" in progress
    member = {
        "id": "order",
        "repositoryId": "order-repo",
        "path": "services/order",
        "knowledge": {"state": "missing"},
    }
    maps = render_maps([member])
    assert "# 成员地图" in maps["member-map"]
    assert "缺失" in maps["fact-status"]
    assert "暂无正式成员知识" in member_markdown(member)
    assert member["knowledge"] == {"state": "missing"}
    assert "services/order" in maps["member-map"]
