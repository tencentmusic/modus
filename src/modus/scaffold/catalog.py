"""读取并校验随包模板，在安装写入前确立完整的工作流输入。

公开入口由调用方显式选择，支持文件按包内路径原样保留。本模块拥有路径、
编码与文档格式；工作流语义由 Markdown 维护，项目写入由 scaffold.writer 负责。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..platforms import Command, Skill
from ..platforms.models import ProjectionConfigurationError, validate_relative_path
from ..skillmd import split_frontmatter
from ..surface import command_invocation

TEMPLATES_DIR: Final = Path(__file__).with_name("templates")


class TemplateCatalogError(RuntimeError):
    """模板分发不可读或违反安装契约。"""


class TemplateNotFoundError(FileNotFoundError, TemplateCatalogError):
    """分发中缺少当前工作流必需的模板。"""


class TemplateFormatError(ValueError, TemplateCatalogError):
    """模板路径或内容不符合分发契约。"""


@dataclass(frozen=True, slots=True)
class TemplateCatalog:
    """从同一模板根读取显式选择的命令和 Skill。

    新增磁盘文件不会自动发布工作流；产品入口须先在 modus.surface 声明。
    """

    root: Path = TEMPLATES_DIR

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))

    def read(self, template_id: str) -> str:
        """按规范 POSIX 相对路径读取 UTF-8 模板，保留其文本。"""

        path = self._path(template_id)
        if not path.is_file():
            raise TemplateNotFoundError(f"必需的 Modus 模板缺失：{template_id}")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise TemplateCatalogError(
                f"无法读取 Modus 模板：{template_id!r}，要求 UTF-8 编码：{exc}"
            ) from exc
        if not content.endswith("\n"):
            raise TemplateFormatError(f"Modus 模板必须以换行结束：{template_id}")
        return content

    def load_skills(self, names: Sequence[str]) -> list[Skill]:
        """按调用方顺序验证并加载 Skill 及全部支持文件。"""

        self._reject_duplicate_names(names, kind="skill")
        return [self._load_skill(name) for name in names]

    def load_commands(self, names: Sequence[str]) -> list[Command]:
        """按调用方顺序验证并加载斜杠命令。"""

        self._reject_duplicate_names(names, kind="command")
        commands: list[Command] = []
        for name in names:
            template_id = f"commands/{name}.md"
            body = self.read(template_id)
            metadata = self._validate_document(template_id, body)
            description = metadata.get("description")
            if not isinstance(description, str) or not description.strip():
                raise TemplateFormatError(f"Modus 命令模板需要非空 description：{template_id}")
            expected_heading = f"# /{command_invocation(name)}"
            if expected_heading not in body.splitlines():
                raise TemplateFormatError(
                    f"Modus 命令模板 {template_id} 缺少标题 {expected_heading!r}"
                )
            commands.append(Command(name=name, body=body))
        return commands

    def _load_skill(self, name: str) -> Skill:
        template_id = f"skills/{name}/SKILL.md"
        body = self.read(template_id)
        metadata = self._validate_document(template_id, body)

        declared_name = metadata.get("name")
        if declared_name != name:
            raise TemplateFormatError(
                f"Modus 技能模板 {template_id} 声明了非预期名称 {declared_name!r}；预期为 {name!r}"
            )
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            raise TemplateFormatError(f"Modus 技能模板需要非空 description： {template_id}")

        skill_root = self._path(f"skills/{name}")
        support_files = {
            path.relative_to(skill_root).as_posix(): self.read(
                path.relative_to(self.root).as_posix()
            )
            for path in sorted(skill_root.rglob("*"))
            if path.is_file() and path != skill_root / "SKILL.md"
        }
        return Skill(
            name=name,
            description=description,
            body=body,
            support_files=support_files,
        )

    @staticmethod
    def _validate_document(template_id: str, text: str) -> dict[str, object]:
        metadata, body = split_frontmatter(text)
        if not metadata:
            raise TemplateFormatError(f"Modus 模板需要有效的 YAML frontmatter：{template_id}")
        if not body.strip():
            raise TemplateFormatError(f"Modus 模板需要非空正文：{template_id}")
        return metadata

    @staticmethod
    def _reject_duplicate_names(names: Sequence[str], *, kind: str) -> None:
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            joined = ", ".join(duplicates)
            raise TemplateFormatError(f"duplicate {kind} 模板名称：{joined}")

    def _path(self, template_id: str) -> Path:
        # 在 Path 规范化之前检查原始身份，与投影和清单使用同一套路径规则。
        try:
            validate_relative_path(template_id, label="模板 ID")
        except ProjectionConfigurationError as exc:
            raise TemplateFormatError(
                f"模板 ID 必须为相对于模板根的规范 POSIX 路径：{template_id!r}"
            ) from exc
        path = self.root.joinpath(*template_id.split("/"))
        try:
            resolved_root = self.root.resolve()
            resolved_path = path.resolve()
        except (OSError, RuntimeError) as exc:
            raise TemplateCatalogError(f"无法解析 Modus 模板路径：{template_id!r}: {exc}") from exc
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise TemplateFormatError(f"模板路径越出目录根：{template_id!r}") from exc
        return path
