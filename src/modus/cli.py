"""公开 CLI 的组合入口。

这里只声明命令树与全局选项。终端适配器负责交互和输出，应用服务负责行为；
公开命令与内部技能入口共享同一套中文帮助策略。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from . import __version__
from . import command_reference as catalog
from .artifacts_io import CorruptArtifactError
from .cli_commands import (
    analysis,
    context,
    desktop,
    discovery,
    initialize,
    knowledge,
    uninstall,
    update,
)
from .cli_commands.common import HELP_CONTEXT_SETTINGS, ModusCommand, ModusGroup, command_panel


# 版本查询在参数分发前短路，损坏项目配置不应妨碍诊断安装版本。
def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


_DIRECTORY_OPTION = typer.Option(
    None,
    "-C",
    "--directory",
    exists=True,
    file_okay=False,
    dir_okay=True,
    resolve_path=True,
    help="在指定项目目录中运行命令。",
    rich_help_panel="全局选项",
)


_VERSION_OPTION = typer.Option(
    False,
    "--version",
    callback=_version_callback,
    is_eager=True,
    help="显示 Modus 版本。",
    rich_help_panel="全局选项",
)


def _normalize_top_level_help_args(args: list[str]) -> list[str]:
    """保证无参数调用与根帮助输出完全一致。"""
    return ["--help"] if not args else args


app = typer.Typer(
    cls=ModusGroup,
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
    help=catalog.TOP_LEVEL_HELP,
    epilog=catalog.TOP_LEVEL_EPILOG,
    context_settings=HELP_CONTEXT_SETTINGS,
)


internal_app = typer.Typer(
    cls=ModusGroup,
    no_args_is_help=True,
    help="供 Modus 技能使用的内部命令。",
    context_settings=HELP_CONTEXT_SETTINGS,
)


# 目录切换挂接上下文关闭回调，嵌入式调用与测试结束后恢复原 cwd。
# 全局参数只在组合入口处理，服务层仍接收显式项目根。
@app.callback()
def root_callback(
    ctx: typer.Context,
    directory: Path | None = _DIRECTORY_OPTION,
    version_option: bool = _VERSION_OPTION,
) -> None:
    """在分发命令前应用全局选项，并在结束时恢复工作目录。"""
    del version_option
    if directory is not None:
        previous = Path.cwd()
        try:
            os.chdir(directory)
        except OSError as exc:
            raise typer.BadParameter(str(exc), param_hint="--directory") from exc
        ctx.call_on_close(lambda: os.chdir(previous))
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


# Keep the supported human surface visible in one place.
app.command(
    name="help",
    cls=ModusCommand,
    help=catalog.cli_help("help"),
    rich_help_panel=command_panel("help"),
)(discovery.help_cmd)
app.command(
    name="status",
    cls=ModusCommand,
    help=catalog.cli_help("status"),
    rich_help_panel=command_panel("status"),
)(discovery.status)
app.command(
    name="dashboard",
    cls=ModusCommand,
    help=catalog.cli_help("dashboard"),
    rich_help_panel=command_panel("dashboard"),
)(desktop.launch)
app.command(
    name="init",
    cls=ModusCommand,
    help=catalog.cli_help("init"),
    rich_help_panel=command_panel("init"),
)(initialize.init)
app.command(
    name="update",
    cls=ModusCommand,
    help=catalog.UPDATE_COMMAND_HELP,
    rich_help_panel=command_panel("update"),
)(update.update_project)
app.command(
    name="uninstall",
    cls=ModusCommand,
    help=catalog.cli_help("uninstall"),
    rich_help_panel=command_panel("uninstall"),
)(uninstall.uninstall_cmd)

# Shipped Skills can invoke these groups; public help and suggestions omit them.
internal_app.add_typer(analysis.init_analysis_app, name="init-analysis")
app.add_typer(internal_app, name="internal", hidden=True)
app.add_typer(context.context_app, name="context", hidden="context" in catalog.HIDDEN_CLI_GROUPS)
app.add_typer(
    knowledge.knowledge_app, name="knowledge", hidden="knowledge" in catalog.HIDDEN_CLI_GROUPS
)


# 仅把已知分析依赖缺失转为用户诊断，未知导入错误继续暴露以便定位。
# 标准退出码区分输入或产物问题与执行能力缺失，不把失败写成成功。
def main(args: list[str] | None = None) -> None:
    """CLI 入口：将已知产物损坏与可选依赖缺失转换为可恢复的中文提示。"""
    normalized_args = _normalize_top_level_help_args(list(sys.argv[1:] if args is None else args))
    try:
        app(args=normalized_args)
    except CorruptArtifactError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise SystemExit(2) from exc
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").split(".", 1)[0]
        if missing not in {
            "networkx",
            "tree_sitter",
        } and not missing.startswith("tree_sitter_"):
            raise
        # Initialization-analysis modules may be imported while loading the
        # internal build adapter. Keep source/Markdown-only commands usable.
        typer.secho(
            f"初始化分析依赖不可用： {missing}；当前 Modus 安装"
            "不完整或已损坏，请更新或重新安装 Modus。源码与 Markdown "
            "检索仍可使用。",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise SystemExit(3) from exc


__all__ = ["app", "main"]

if __name__ == "__main__":  # pragma: no cover
    main()
