"""DSH 使用项目 Skill 和 AGENTS.md；运行时上下文由原生插件提供。"""

from __future__ import annotations

from .base import Command, PlatformAdapter, Skill
from .models import InstructionFile, PlatformLayout
from .rendering import render_agents_instructions, render_invocation_metadata

_LAYOUT = PlatformLayout(
    skills_root=".dsh/skills",
    owned_file_prefixes=(".dsh/skills/",),
    instructions=InstructionFile(path="AGENTS.md", marker="modus"),
)


class DshAdapter(PlatformAdapter):
    """项目投影复用安装生命周期；profile 配置由 DSH 独立管理。"""

    name = "dsh"
    layout = _LAYOUT

    def _post_process_skill_md(
        self,
        content: str,
        *,
        model_invocable: bool = True,
        user_invocable: bool = False,
    ) -> str:
        return render_invocation_metadata(
            content, model_invocable=model_invocable, user_invocable=user_invocable
        )

    def _render_instructions(self, skills: list[Skill], _commands: list[Command]) -> str:
        return render_agents_instructions(skills)
