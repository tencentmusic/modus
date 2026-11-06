"""Small Markdown assertions for repository-owned contract documents."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from modus.markdown import strip_fenced_code

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_HTML_LINK_RE = re.compile(r"""\bhref=["']([^"']+)["']""")
_HTML_ANCHOR_RE = re.compile(r"""\b(?:id|name)=["']([^"']+)["']""")
_EXTERNAL_SCHEMES = ("http://", "https://", "mailto:")


# 示例代码中的标题不能成为正文锚点，先剥离围栏再提取层级。
def markdown_headings(text: str) -> tuple[tuple[int, str], ...]:
    """Return headings outside fenced examples as ``(level, title)`` pairs."""

    prose = strip_fenced_code(text)
    return tuple((len(marker), title.strip()) for marker, title in _HEADING_RE.findall(prose))


# 只验证本地引用，不引入网络可用性与第三方页面变更的测试噪声。
# 重复标题使用递增后缀，与文档阅读时的锚点区分保持一致。
def assert_local_markdown_links_resolve(path: Path, *, root: Path) -> set[Path]:
    """验证本地链接及锚点，返回已解析目标供工作流可达性检查复用。"""

    prose = strip_fenced_code(path.read_text(encoding="utf-8"))
    targets: set[Path] = set()
    for raw_destination in (*_LINK_RE.findall(prose), *_HTML_LINK_RE.findall(prose)):
        destination = raw_destination.strip().strip("<>")
        target_text, _, fragment = destination.partition("#")
        if target_text.startswith(_EXTERNAL_SCHEMES) or "://" in target_text:
            continue
        target = (path.parent / unquote(target_text)).resolve() if target_text else path.resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            raise AssertionError(f"{path}: local link escapes repository: {destination}") from None
        assert target.is_file(), f"{path}: local link target is missing: {destination}"
        targets.add(target)
        if fragment and target.suffix.lower() == ".md":
            text = target.read_text(encoding="utf-8")
            anchors = set(_HTML_ANCHOR_RE.findall(strip_fenced_code(text)))
            counts: dict[str, int] = {}
            for _, heading in markdown_headings(text):
                heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
                heading = re.sub(r"<[^>]+>", "", heading)
                slug = re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")
                occurrence = counts.get(slug, 0)
                counts[slug] = occurrence + 1
                anchors.add(f"{slug}-{occurrence}" if occurrence else slug)
            assert unquote(fragment) in anchors, f"{path}: missing Markdown anchor: {destination}"
    return targets


__all__ = ["assert_local_markdown_links_resolve", "markdown_headings"]
