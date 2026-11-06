"""Codex adapter: Agent Skills plus lifecycle hooks in ``.codex/hooks.json``.

The official hook contract provides a stable session id to hook processes but
no persistent environment-file channel for later CLI invocations. Consequently
session continuation cannot auto-bind on Codex: an explicit existing binding or
the deliberately narrow clear-session singleton recovery is required.
"""

from __future__ import annotations

from ..hooks import bootstrap
from .base import Command, PlatformAdapter, Skill
from .models import HookFile, InstructionFile, PlatformLayout
from .rendering import render_agents_instructions

_LAYOUT = PlatformLayout(
    skills_root=".agents/skills",
    owned_file_prefixes=(".agents/skills/",),
    instructions=InstructionFile(path="AGENTS.md", marker="modus"),
    hook=HookFile(
        path=".codex/hooks.json",
        template="hooks/codex-hooks.json",
        render_config=bootstrap.codex_hook_config,
    ),
)


class CodexAdapter(PlatformAdapter):
    """Project Modus into Codex' standard Agent Skills and hook surfaces."""

    name = "codex"
    layout = _LAYOUT

    def _render_instructions(
        self,
        skills: list[Skill],
        _commands: list[Command],
    ) -> str:
        return render_agents_instructions(skills)
