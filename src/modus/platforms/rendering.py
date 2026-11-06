"""Deterministic renderers shared by platform instruction surfaces."""

from __future__ import annotations

from collections.abc import Sequence

import yaml

from ..precedence import (
    MODUS_DISPATCHER_FALLBACK,
    MODUS_PRECEDENCE_NOTICE,
    USER_INVOKED_WORKFLOWS_SENTENCE,
)
from ..skillmd import split_frontmatter
from ..surface import EXPLICIT_SKILLS, INTENT_ROUTED_SKILLS
from .models import Skill


def render_agents_instructions(skills: Sequence[Skill]) -> str:
    """Render the AGENTS.md section shared by Codex and DSH."""

    heading = f"## Modus\n\n{MODUS_DISPATCHER_FALLBACK} {USER_INVOKED_WORKFLOWS_SENTENCE}:"
    return render_skill_index(skills, heading)


def render_invocation_metadata(content: str, *, model_invocable: bool, user_invocable: bool) -> str:
    """补齐 Claude 与 DSH 的顶层调用权限，保留正文、已有配置和换行。

    使用有界 frontmatter 解析，避免把正文示例或嵌套键误认为权限。
    模板合法性由 catalog 校验；无法解析时保留原文，不在投影层猜测修复。
    """
    metadata, body = split_frontmatter(content)
    defaults = {
        "user-invocable": user_invocable,
        "disable-model-invocation": not model_invocable,
    }
    if not metadata or defaults.keys() <= metadata.keys():
        return content
    for key, value in defaults.items():
        metadata.setdefault(key, value)
    newline = "\r\n" if content.startswith("---\r\n") else "\n"
    header = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True, line_break=newline)
    return f"---{newline}{header}---{newline}{body}"


def _skill_line(skill: Skill) -> str:
    return f"- `{skill.name}`: {skill.description}"


# 未知技能保留在末尾，新增扩展不会挤入具有不同调用授权的内置分类。
def render_skill_index(skills: Sequence[Skill], heading: str) -> str:
    """Render the shared dispatcher/workflow/lifecycle information architecture.

    Classification comes from :mod:`modus.surface`, so host documentation can
    vary in framing without drifting from the framework's invocation policy.
    The input order is irrelevant; category order is canonical and stable.
    """

    by_name = {skill.name: skill for skill in skills}
    lines = [heading, "", MODUS_PRECEDENCE_NOTICE, ""]

    dispatcher = by_name.get("using-modus")
    if dispatcher is not None:
        lines.extend(
            [
                "**项目证据与生命周期协调（按需读取；启动时仅提示入口）：**",
                _skill_line(dispatcher),
                "",
            ]
        )

    intent_routed = [
        by_name[name]
        for name in EXPLICIT_SKILLS
        if name in by_name and name in INTENT_ROUTED_SKILLS
    ]
    if intent_routed:
        lines.append("**意图路由工作流（明确匹配用户意图或显式调用）：**")
        lines.extend(_skill_line(skill) for skill in intent_routed)
        lines.append("")

    explicit_only = [
        by_name[name]
        for name in EXPLICIT_SKILLS
        if name in by_name and name not in INTENT_ROUTED_SKILLS
    ]
    if explicit_only:
        lines.append("**仅显式调用的主工作流（用户明确要求后加载）：**")
        lines.extend(_skill_line(skill) for skill in explicit_only)
        lines.append("")

    listed = {"using-modus", *EXPLICIT_SKILLS}
    maintenance = by_name.get("modus-sync-knowledge")
    if maintenance is not None:
        lines.extend(
            [
                "**知识影响调查与维护（自动执行）：**",
                _skill_line(maintenance),
                "",
            ]
        )
        listed.add(maintenance.name)

    remaining = [skill for skill in skills if skill.name not in listed]
    if remaining:
        lines.append("**其他技能：**")
        lines.extend(_skill_line(skill) for skill in remaining)
        lines.append("")

    return "\n".join(lines).rstrip()
