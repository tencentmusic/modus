"""Claude Code 接入：Agent Skills 与 CLAUDE.md 常驻指引。"""

from __future__ import annotations

from ..precedence import USER_INVOKED_WORKFLOWS_SENTENCE
from .base import Command, PlatformAdapter, Skill
from .models import InstructionFile, PlatformLayout
from .rendering import render_invocation_metadata, render_skill_index

_LAYOUT = PlatformLayout(
    skills_root=".claude/skills",
    owned_file_prefixes=(".claude/skills/",),
    instructions=InstructionFile(path="CLAUDE.md", marker="modus-claude"),
)


class ClaudeAdapter(PlatformAdapter):
    """Add Claude invocation metadata while reusing the shared lifecycle."""

    name = "claude"
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

    def _render_instructions(
        self,
        skills: list[Skill],
        _commands: list[Command],
    ) -> str:
        heading = f"## Modus\n\n{USER_INVOKED_WORKFLOWS_SENTENCE}:"
        return render_skill_index(skills, heading)
