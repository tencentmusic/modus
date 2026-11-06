"""Derived precedence notices for generated host integrations.

The workflow catalog in :mod:`modus.surface` is authoritative.  This module
only renders that policy, ensuring every host receives the same activation and
explicit-invocation semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from .activation_guidance import MODUS_ENTRY_HINT
from .surface import AUTOMATIC_SKILLS, EXPLICIT_SKILLS, INTENT_ROUTED_SKILLS


def _skill_names(names: Iterable[str]) -> str:
    return ", ".join(f"`{name}`" for name in names)


MODUS_PRECEDENCE_NOTICE: Final = "\n".join(
    [
        "### Modus 项目知识",
        "",
        MODUS_ENTRY_HINT,
        "",
        f"自动能力：{_skill_names(AUTOMATIC_SKILLS)}。"
        f"知识保留意图可选择 {_skill_names(INTENT_ROUTED_SKILLS)}。"
        f"显式工作流：{_skill_names(EXPLICIT_SKILLS)}。"
        "其他工作流在用户提出相应需求后，按该需求的范围运行。",
    ]
)
MODUS_SKILL_GATE_NOTICE: Final = MODUS_PRECEDENCE_NOTICE
USER_INVOKED_WORKFLOWS_SENTENCE: Final = (
    f"由用户调用的 Modus 工作流：{_skill_names(EXPLICIT_SKILLS)}"
)

__all__ = [
    "MODUS_PRECEDENCE_NOTICE",
    "MODUS_SKILL_GATE_NOTICE",
    "USER_INVOKED_WORKFLOWS_SENTENCE",
]
