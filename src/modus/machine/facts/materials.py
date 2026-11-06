"""从冻结文本保留材料块和原始位置；不解释材料是否代表当前业务事实。"""

from __future__ import annotations

import re
from typing import Any

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_MENTION = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")


def observe_material(relative: str, content: str) -> list[dict[str, Any]]:
    """按原顺序保留章节、表格、围栏和文本；长块续片仍指向原文行号。"""
    lines = content.splitlines(keepends=True)
    records: list[dict[str, Any]] = []
    headings: list[tuple[int, str]] = []
    start = 0
    fence = ""
    kind = "text"
    block: list[str] = []

    def emit() -> None:
        if not block:
            return
        text = "".join(block)
        # 超长单行也分片，完整内容留在原材料；每片都可按行号回查。
        for offset in range(0, len(text), 6000):
            fragment = text[offset : offset + 6000]
            records.append(
                {
                    "kind": "resource",
                    "materialType": kind,
                    "heading": " / ".join(title for _, title in headings),
                    "content": fragment,
                    "links": list(dict.fromkeys(_LINK.findall(fragment))),
                    "mentions": list(dict.fromkeys(_MENTION.findall(fragment))),
                    "continued": offset > 0,
                    "blockIndex": len(records),
                    "location": {
                        "path": relative,
                        "startLine": start + 1,
                        "endLine": start + len(block),
                    },
                    "resolution": "exact",
                    "sourceLayer": "cst",
                }
            )
        block.clear()

    for index, line in enumerate(lines):
        marker = _FENCE.match(line)
        heading = _HEADING.match(line) if not fence else None
        next_kind = "code" if fence or marker else "table" if "|" in line else "text"
        if heading or (not fence and (not line.strip() or next_kind != kind)):
            emit()
            start = index
        if heading:
            level = len(heading[1])
            headings[:] = [(depth, title) for depth, title in headings if depth < level]
            headings.append((level, heading[2]))
            kind = "heading"
            block.append(line)
            emit()
            start = index + 1
            continue
        if not block:
            start = index
        kind = next_kind
        block.append(line)
        if marker:
            if fence and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
                emit()
            elif not fence:
                fence = marker[1]
    emit()
    return records
