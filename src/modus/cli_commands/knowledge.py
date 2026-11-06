"""知识核验与受保护发布的终端入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .. import workspace
from ..artifacts_io import CorruptArtifactError
from ..command_reference import cli_help
from ..display_labels import display_label
from .common import (
    HELP_CONTEXT_SETTINGS,
    ModusCommand,
    ModusGroup,
    command_panel,
    public_error,
)

knowledge_app = typer.Typer(
    cls=ModusGroup,
    no_args_is_help=True,
    help="知识维护与核验命令。",
    context_settings=HELP_CONTEXT_SETTINGS,
)


# 兼容入口只负责调用与序列化，刷新规则由工作区层维护。
# 运行失败使用独立退出码，避免把错误当作成功的 JSON 数据。
@knowledge_app.command(cls=ModusCommand, name="workspace-refresh", hidden=True)
def knowledge_workspace_refresh_cmd(
    root: str = typer.Option(".", "--root", help="工作区根目录。"),
) -> None:
    try:
        result = workspace.refresh_generated(root)
    except (OSError, RuntimeError, ValueError) as exc:
        typer.secho(f"工作区知识刷新失败： {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(3) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


# 状态查询保持只读；导入预检放在命令内以降低其他命令启动成本。
# 输出沿用预检的数据契约，终端层不推导新的健康结论。
@knowledge_app.command(
    cls=ModusCommand,
    name="status",
    help="只读查看知识与可选增强能力的状态。",
)
def knowledge_status_cmd(root: str = typer.Option(".", "--root")) -> None:
    from ..orchestrator.preflight import check

    typer.echo(json.dumps(check(root), ensure_ascii=False))


# 领域列表来自显式参数，不根据目录名自动猜测业务归属。
# 写入边界与已有内容保护由业务种子服务统一执行。
# 机器模式和人类摘要使用同一份结果，避免两套状态判断。
@knowledge_app.command(cls=ModusCommand, name="seed-business", hidden=True)
def knowledge_seed_business_cmd(
    domain: Annotated[list[str], typer.Option("--domain", help="已确认的领域标识，可重复指定。")],
    json_output: bool = typer.Option(False, "--json", help="输出机器可读的 JSON。"),
    root: str = typer.Option(".", "--root", help="项目根目录。"),
) -> None:
    """补充缺失的人工业务索引，保留已有内容。"""
    from ..commands.seed_business import seed_domain_business

    try:
        result = seed_domain_business(root, domain)
    except (CorruptArtifactError, OSError, RuntimeError, ValueError) as exc:
        public_error(str(exc), json_output=json_output)
        raise typer.Exit(3) from exc
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        typer.echo(
            f"业务种子： 新增 {len(result['created'])} 份，保留 {len(result['preserved'])} 份"
        )


# 核验结果与运行失败分开编码：发现问题不等同于核验器异常。
# 终端仅展示前二十条，完整发现保留在 JSON 输出中。
# 发布核验是显式扩展选项，不改变普通结构核验的含义。
@knowledge_app.command(
    cls=ModusCommand,
    name="verify",
    help=cli_help("knowledge verify"),
    rich_help_panel=command_panel("knowledge verify"),
)
def knowledge_verify_cmd(
    member: str | None = typer.Option(
        None, "--member", help="工作区已配置的成员 ID，仅用于 --publication；--root 指向工作区根。"
    ),
    domain: str | None = typer.Option(None, "--domain", help="仅核验指定领域标识。"),
    publication: bool = typer.Option(
        False,
        "--publication",
        help="同时核验执行卡、业务种子、模块锚点与声明的图表。",
    ),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读的 JSON。"),
    root: str = typer.Option(".", "--root", help="项目根目录。"),
) -> None:
    """只读核验知识结构、链接、源码证据与安全边界。"""
    from ..commands.verify_knowledge import run_verify_knowledge

    try:
        result = run_verify_knowledge(root, domain=domain, publication=publication, member=member)
    except (CorruptArtifactError, OSError, RuntimeError, ValueError) as exc:
        public_error(str(exc), json_output=json_output)
        raise typer.Exit(3) from exc
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    elif result["status"] == "clean":
        assurance = "通过发布核验" if publication else "结构核验通过"
        typer.echo(f"知识核验完成： {result['checkedDocuments']} 份文档 {assurance}")
    else:
        for name, count in sorted(result["counts"].items()):
            typer.echo(f"{display_label(name)}：{count}")
        for finding in result["findings"][:20]:
            location = f":{finding['line']}" if finding.get("line") else ""
            typer.echo(
                f"  {display_label(finding['finding'])}： {finding['document']}{location} "
                f"{finding.get('detail', '')}".rstrip()
            )
        if len(result["findings"]) > 20:
            typer.echo(f"  ... {len(result['findings']) - 20} 条其他问题（使用 --json 查看全部）")
    if result["status"] != "clean":
        raise typer.Exit(4)


# 修复必须由 --fix 显式请求，默认只报告锚点漂移。
# 可修复范围及哈希并发保护留在领域服务中实现。
# 展示已修复文件后仍按最终核验状态决定退出码。
@knowledge_app.command(
    cls=ModusCommand,
    name="verify-anchors",
    help=cli_help("knowledge verify-anchors"),
    rich_help_panel=command_panel("knowledge verify-anchors"),
)
def knowledge_verify_anchors_cmd(
    fix: bool = typer.Option(
        False,
        "--fix",
        help="仅通过哈希条件写入修复唯一匹配的行号漂移，其他问题只报告。",
    ),
    json_output: bool = typer.Option(False, "--json", help="输出机器可读的 JSON。"),
    root: str = typer.Option(".", "--root", help="项目根目录。"),
) -> None:
    """核验源码锚点与 path#L 引用，明确报告漂移。"""
    from ..commands.verify_anchors import run_verify_anchors

    try:
        result = run_verify_anchors(root, fix=fix)
    except (CorruptArtifactError, OSError, RuntimeError, ValueError) as exc:
        public_error(str(exc), json_output=json_output)
        raise typer.Exit(3) from exc
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        if result["status"] == "clean":
            typer.echo("锚点核验通过，未发现漂移")
        else:
            for name, count in sorted(result["counts"].items()):
                typer.echo(f"{display_label(name)}：{count}")
            for finding in result["findings"][:20]:
                anchor = finding.get("symbol") or finding.get("reference") or ""
                extra = (f" -> L{finding['actualLine']}" if finding.get("actualLine") else "") + (
                    "（已修复）" if finding.get("fixed") else ""
                )
                typer.echo(
                    f"  {display_label(finding['finding'])}： {finding['document']} {anchor}{extra}"
                )
            if len(result["findings"]) > 20:
                typer.echo(
                    f"  ... {len(result['findings']) - 20} 条其他问题（使用 --json 查看全部）"
                )
        if result.get("fixedDocuments"):
            typer.echo("已修复：" + ", ".join(result["fixedDocuments"]))
    if result["status"] != "clean":
        raise typer.Exit(4)


# 同步入口只生成受影响知识的提示，不代替作者改写主定义。
# 冲突返回非零退出码，便于调用方停止后续自动化。
@knowledge_app.command(
    cls=ModusCommand,
    name="sync",
    help="只读查找可能受影响的知识，由助手修订其主定义。",
)
def knowledge_sync_cmd(
    changed_file: Annotated[list[str] | None, typer.Option("--changed-file")] = None,
    target: Annotated[list[str] | None, typer.Option("--target")] = None,
    root: str = ".",
    validation: str = "passed",
) -> None:
    from ..orchestrator.knowledge_sync import sync_knowledge

    result = sync_knowledge(root, changed_file or [], targets=target or [], validation=validation)
    typer.echo(json.dumps(result, ensure_ascii=False))
    if result["conflicts"]:
        raise typer.Exit(1)


# 输入文件按实际读取字节数限流，避免参数检查后的文件增长。
# 只转交更新协议字段，预期哈希和删除列表由写入服务核验。
# 格式错误属于参数错误，读取失败属于运行错误。
# 允许空 documents 支持纯删除请求，但仍要求该字段显式存在。
# 存在写入冲突时返回结果及失败退出码，调用者可据此重新读取。
@knowledge_app.command(
    cls=ModusCommand,
    name="update",
    help="按文件读取时的哈希写入知识或删除已退役的生成正文。",
)
def knowledge_update_cmd(
    input_file: Annotated[Path, typer.Option("--input", exists=True, dir_okay=False)],
    root: str = ".",
) -> None:
    from ..knowledge_update import update_knowledge

    try:
        # Bound the actual read, including files that grow after argument parsing.
        limit = 16 * 1024 * 1024
        with input_file.open("rb") as stream:
            payload = stream.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("输入超过 16 MiB 上限")
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict) or "documents" not in data:
            raise ValueError("输入需包含 documents 映射（仅删除时可为空）")
        result = update_knowledge(
            root,
            data["documents"],
            expected_hashes=data.get("expectedHashes"),
            deletions=data.get("deletions", []),
            allow_team_standard=data.get("allowTeamStandard", False),
            initialize_team_standard=data.get("initializeTeamStandard", False),
        )
    except (ValueError, UnicodeError) as exc:
        raise typer.BadParameter(str(exc), param_hint="--input") from exc
    except OSError as exc:
        public_error(f"无法读取知识更新输入： {exc}", json_output=True)
        raise typer.Exit(3) from exc
    typer.echo(json.dumps(result, ensure_ascii=False))
    if result["conflicts"]:
        raise typer.Exit(1)
