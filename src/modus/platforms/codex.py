"""Codex 接入：Agent Skills 与 AGENTS.md 常驻指引。"""

from __future__ import annotations

from .base import Command, PlatformAdapter, Skill
from .models import InstructionFile, PlatformLayout
from .rendering import render_agents_instructions

_LAYOUT = PlatformLayout(
    skills_root=".agents/skills",
    owned_file_prefixes=(".agents/skills/",),
    instructions=InstructionFile(path="AGENTS.md", marker="modus"),
)


class CodexAdapter(PlatformAdapter):
    """将 Modus 投影到 Codex 的技能与常驻指引。"""

    name = "codex"
    layout = _LAYOUT

    def _render_instructions(
        self,
        skills: list[Skill],
        _commands: list[Command],
    ) -> str:
        return render_agents_instructions(skills)
