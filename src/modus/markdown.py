"""知识读取与核验共用的 Markdown 标题、条目标记和锚点语义。"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ITEM_ID_RE = re.compile(r"\{\{item:([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\}\}")
_ITEM_ANCHOR_RE = re.compile(
    r'<a\s+id=["\']item-([A-Za-z0-9][A-Za-z0-9._:-]{0,127})["\']\s*></a>',
    re.IGNORECASE,
)
_HTML_ANCHOR_RE = re.compile(r'<a\s+(?:name|id)=["\']([^"\']+)["\']', re.IGNORECASE)


def markdown_slug(value: str) -> str:
    """标题与链接片段共享 Unicode 归一化，不依赖文档语言。"""
    value = value.strip().casefold()
    result = [
        character
        for character in value
        if character in {"-", "_", " "} or unicodedata.category(character)[0] in {"L", "N", "M"}
    ]
    return re.sub(r"[ -]+", "-", "".join(result)).strip("-")


def strip_fenced_code(text: str) -> str:
    """示例内的链接不参与导航；保留空行以维持来源坐标。"""
    output: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None and match and not (match[1][0] == "`" and "`" in match[2]):
            fence = (match[1][0], len(match[1]))
            output.append("")
            continue
        if fence is not None:
            if (
                match
                and match[1][0] == fence[0]
                and len(match[1]) >= fence[1]
                and not match[2].strip()
            ):
                fence = None
            output.append("")
            continue
        output.append("" if line.startswith(("    ", "\t")) else line)
    return "\n".join(output)


# 仅跳过有闭合边界的 frontmatter，损坏元数据不能吞掉整篇正文。
# 前置元数据不作为正文证据，行号偏移仍需保留供定位。
def body_start(lines: list[str]) -> int:
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, min(len(lines), 4096)):
        if lines[index].strip() == "---":
            return index + 1
    return 0


# 代码围栏与缩进代码中的井号不能切分知识章节。
# 同时支持 ATX 与 Setext 标题，保持常见 Markdown 写法可读。
def markdown_headings(lines: list[str], start: int = 0) -> list[tuple[int, int, str]]:
    """Recognize Markdown headings outside backtick/tilde fences and indented code.

    Fence closing requires the same character and at least the opening length;
    a shorter embedded fence is source text, not a new document section.
    """
    headings: list[tuple[int, int, str]] = []
    fence: tuple[str, int] | None = None
    for index in range(start, len(lines)):
        line = lines[index]
        fence_match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if (
                fence_match
                and fence_match[1][0] == fence[0]
                and len(fence_match[1]) >= fence[1]
                and not fence_match[2].strip()
            ):
                fence = None
            continue
        if fence_match and not (fence_match[1][0] == "`" and "`" in fence_match[2]):
            fence = (fence_match[1][0], len(fence_match[1]))
            continue
        _append_markdown_heading(lines, index, start, headings)
    return headings


def _append_markdown_heading(
    lines: list[str], index: int, start: int, headings: list[tuple[int, int, str]]
) -> None:
    """调用方排除围栏后，在正文中识别 ATX 与 Setext 标题。"""
    line = lines[index]
    match = _HEADING_RE.match(line[0:]) if not line.startswith(("    ", "\t")) else None
    if match is None and line.startswith(" ") and not line.startswith("    "):
        match = _HEADING_RE.match(line.lstrip(" "))
    if match:
        title = re.sub(r"\s+#+\s*$", "", match[2]).strip()
        headings.append((index, len(match[1]), title))
    elif index > start and re.fullmatch(r" {0,3}(?:=+|-+)\s*", line):
        previous = lines[index - 1]
        if (
            previous.strip()
            and not previous.startswith(("    ", "\t"))
            and not re.match(r"^\s*(?:#|[-*+]>?|>|```|~~~)", previous)
        ):
            if not headings or headings[-1][0] != index - 1:
                headings.append(
                    (index - 1, 1 if line.lstrip().startswith("=") else 2, previous.strip())
                )


def markdown_anchors(text: str) -> dict[int, tuple[str, ...]]:
    """按零基行号枚举真实正文锚点；重复标题顺序与检索、核验一致。"""
    lines = text.splitlines()
    start = body_start(lines)
    anchors: dict[int, list[str]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for line, _level, heading in markdown_headings(lines, start):
        slug = markdown_slug(heading)
        occurrence = counts[slug]
        counts[slug] += 1
        anchors[line].append(slug if occurrence == 0 else f"{slug}-{occurrence}")
    prose = strip_fenced_code("\n".join(lines[start:]))
    for line, content in enumerate(prose.splitlines(), start):
        anchors[line].extend(value.casefold() for value in _HTML_ANCHOR_RE.findall(content))
        anchors[line].extend(f"item-{value}".casefold() for value in _ITEM_ID_RE.findall(content))
    return {line: tuple(dict.fromkeys(values)) for line, values in anchors.items()}


def markdown_item_ids(text: str) -> list[str]:
    """显式条目身份不受展示标题或示例代码影响。"""
    prose = strip_fenced_code(text)
    return sorted(set(_ITEM_ID_RE.findall(prose)) | set(_ITEM_ANCHOR_RE.findall(prose)))
