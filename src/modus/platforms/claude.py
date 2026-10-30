"""Claude Code projection: Agent Skills, ``CLAUDE.md``, and lifecycle hooks."""

from __future__ import annotations

from ..hooks import bootstrap
from ..precedence import MODUS_DISPATCHER_FALLBACK, USER_INVOKED_WORKFLOWS_SENTENCE
from .base import Command, PlatformAdapter, Skill
from .models import HookFile, InstructionFile, PlatformLayout
from .rendering import render_invocation_metadata, render_skill_index

_LAYOUT = PlatformLayout(
    skills_root=".claude/skills",
    owned_file_prefixes=(".claude/skills/",),
    instructions=InstructionFile(path="CLAUDE.md", marker="modus-claude"),
    hook=HookFile(
        path=".claude/settings.json",
        template="hooks/claude-settings.json",
        render_config=bootstrap.claude_hook_config,
    ),
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
        heading = f"## Modus\n\n{MODUS_DISPATCHER_FALLBACK} {USER_INVOKED_WORKFLOWS_SENTENCE}:"
        return render_skill_index(skills, heading)
