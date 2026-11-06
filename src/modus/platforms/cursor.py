"""Cursor 接入：.cursor/skills 技能与 .cursor/rules/modus.mdc 常驻规则。"""

from __future__ import annotations

from ..precedence import USER_INVOKED_WORKFLOWS_SENTENCE
from .base import Command, PlatformAdapter, Skill
from .models import InstructionFile, PlatformLayout
from .rendering import render_skill_index

_FRONTMATTER = "---\ndescription: Modus 框架入口\nalwaysApply: true\n---\n\n"
_LAYOUT = PlatformLayout(
    skills_root=".cursor/skills",
    owned_file_prefixes=(".cursor/",),
    instructions=InstructionFile(
        path=".cursor/rules/modus.mdc",
        marker="modus-cursor",
        preamble=_FRONTMATTER,
    ),
)


# 布局只描述宿主拥有的路径与标记，文件合并和所有权校验由基类负责。
# 常驻规则只呈现工作流入口，具体技能仍从权威资产投影。
class CursorAdapter(PlatformAdapter):
    """将 Modus 投影到 Cursor 的技能与常驻规则。"""

    name = "cursor"
    layout = _LAYOUT

    def _render_instructions(
        self,
        skills: list[Skill],
        _commands: list[Command],
    ) -> str:
        heading = f"# Modus\n\n{USER_INVOKED_WORKFLOWS_SENTENCE}.\nModus 核心能力："
        return render_skill_index(skills, heading)
