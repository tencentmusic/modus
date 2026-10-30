"""Published CLI examples stay parseable and local links stay valid."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import click
from typer.main import get_command

from _support.markdown import assert_local_markdown_links_resolve
from _support.paths import REPO_ROOT
from modus.cli import app

_PUBLIC_READMES = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "READMEs/README.en.md",
)
_DEVELOPER_DOCS = (
    *_PUBLIC_READMES,
    REPO_ROOT / "ARCHITECTURE.md",
    REPO_ROOT / "CONTRIBUTING.md",
    *sorted((REPO_ROOT / "docs").rglob("*.md")),
    *sorted((REPO_ROOT / "src/modus").rglob("README.md")),
    *sorted((REPO_ROOT / "skills/modus-development").rglob("*.md")),
    REPO_ROOT / "tests/README.md",
    REPO_ROOT / "scripts/README.md",
    *sorted((REPO_ROOT / "integrations/dsh").glob("*.md")),
)
_MARKDOWN_ROOTS = (
    *_DEVELOPER_DOCS,
    REPO_ROOT / "src/modus/scaffold/templates",
)
_PLACEHOLDER = re.compile(r"<[^>]+>")


# 维护指南与随包模板共用命令契约检查，避免其中一份停留在旧接口。
# 目录展开按稳定顺序进行，使失败路径在本地和 CI 一致。
def _managed_markdown() -> list[Path]:
    result: list[Path] = []
    for root in _MARKDOWN_ROOTS:
        if root.is_file():
            result.append(root)
        else:
            result.extend(sorted(root.rglob("*.md")))
    return result


# 文件存在还不够：跨页标题锚点也属于贡献者的阅读路径。
def test_developer_documentation_has_valid_files_and_anchors() -> None:
    for readme in _DEVELOPER_DOCS:
        assert readme.is_file()
        assert_local_markdown_links_resolve(readme, root=REPO_ROOT)


# 同时覆盖行内示例和围栏内的命令行，不执行示例中的业务动作。
# 只提取显式 modus 调用，普通叙述文字不参与参数校验。
def _documented_commands(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    commands = [
        match.group(1).strip() for match in re.finditer(r"`([^`\n]*\bmodus\s+[^`\n]+)`", text)
    ]
    commands.extend(
        line.strip() for line in text.splitlines() if line.lstrip().startswith("modus ")
    )
    return commands


# 占位符和备选值是文档记法，在真实命令树校验前归一化。
# 保留 shlex 的引号语义，使带空格参数仍是一个参数。
def _tokens(example: str) -> list[str]:
    command = example[example.index("modus ") :]
    normalized: list[str] = []
    for token in shlex.split(command):
        token = token.strip("[]")
        if not token:
            continue
        token = _PLACEHOLDER.sub("value", token)
        if "|" in token and not token.startswith("--"):
            token = token.split("|", 1)[0]
        normalized.append(token)
    return normalized


# 从实际 Typer 注册结果遍历，避免测试维护第二份命令清单。
# 子命令切换后重新计算位置参数，选项值则按声明的数量跳过。
# 检查只读取命令元数据，不触发安装、卸载或文件写入。
# 普通参数不应被误认为子命令，未知 token 必须可定位。
def _assert_command_parses(tokens: list[str]) -> None:
    command = get_command(app)
    arguments = 0
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if isinstance(command, click.Group) and not token.startswith("-"):
            child = command.get_command(click.Context(command), token)
            if child is not None:
                command = child
                arguments = 0
                index += 1
                continue
        if token.startswith("-"):
            option = next(
                (
                    parameter
                    for parameter in command.get_params(click.Context(command))
                    if isinstance(parameter, click.Option)
                    and token in (*parameter.opts, *parameter.secondary_opts)
                ),
                None,
            )
            assert option is not None, f"unknown option {token!r} in {' '.join(tokens)!r}"
            index += 1
            if not option.is_flag and not option.count:
                assert index < len(tokens), f"missing value for {token!r}"
                index += max(1, option.nargs)
            continue
        positional = [
            item
            for item in command.get_params(click.Context(command))
            if isinstance(item, click.Argument)
        ]
        assert arguments < len(positional), f"unknown command or argument in {' '.join(tokens)!r}"
        arguments += 1
        index += 1


# 异常附上来源路径与原示例，让文档作者能直接修正文档。
# 要求至少找到一个示例，防止提取规则失效时全套检查空跑。
def test_every_documented_cli_example_uses_the_real_command_tree() -> None:
    examples = [
        (path, example) for path in _managed_markdown() for example in _documented_commands(path)
    ]
    assert examples
    for path, example in examples:
        try:
            _assert_command_parses(_tokens(example))
        except (AssertionError, ValueError) as exc:
            raise AssertionError(f"{path.relative_to(REPO_ROOT)}: {example}") from exc
