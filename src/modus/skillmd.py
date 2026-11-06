"""Bounded Markdown frontmatter parsing and rendering."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence, Set
from typing import Any, Final

import yaml

# Frontmatter delimiter.
_FM_RE: Final = re.compile(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)$", re.DOTALL)

# SKILL frontmatter is routing input, not an arbitrary YAML document. Keep its
# parser work bounded before schema validation sees it. The limits are generous
# for generated Domain/Module metadata while preventing recursive/alias bombs.
_MAX_FRONTMATTER_CHARS: Final = 1_000_000
_MAX_FRONTMATTER_DEPTH: Final = 64
_MAX_FRONTMATTER_NODES: Final = 10_000

# Machine-managed marker regions in the body. Each key maps to a BEGIN/END pair;
# the graph engine rewrites the text between them and nothing else.
DOMAIN_SKILL_KIND: Final = "domain-scope-skill"
MODULE_SKILL_KIND: Final = "module-scope-skill"


class _UnsafeFrontmatter(ValueError):
    """The YAML graph exceeded the bounded SKILL frontmatter contract."""


class _BoundedSafeLoader(yaml.SafeLoader):
    """SafeLoader with construction-time depth, node, and cycle limits."""

    def __init__(self, stream: str, *, reject_duplicates: bool = False) -> None:
        super().__init__(stream)
        self._modus_reject_duplicates = reject_duplicates
        self._modus_nodes = 0
        self._modus_depth = 0
        self._modus_active_anchors: set[str] = set()

    def construct_mapping(self, node, deep=False):
        if self._modus_reject_duplicates:
            seen: set[str] = set()
            for key, _value in node.value:
                if isinstance(key, yaml.ScalarNode) and key.tag != "tag:yaml.org,2002:merge":
                    if key.value in seen:
                        raise _UnsafeFrontmatter(
                            f"frontmatter 第 {key.start_mark.line + 2} 行存在重复字段：{str(key.value)[:80]!r}"
                        )
                    seen.add(key.value)
        return super().construct_mapping(node, deep=deep)

    def compose_node(self, parent, index):
        event = self.peek_event()
        self._modus_nodes += 1
        if self._modus_nodes > _MAX_FRONTMATTER_NODES:
            raise _UnsafeFrontmatter("frontmatter 节点超过预算")

        is_collection = isinstance(
            event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)
        )
        anchor = event.anchor if is_collection else None
        if isinstance(event, yaml.events.AliasEvent):
            if event.anchor in self._modus_active_anchors:
                raise _UnsafeFrontmatter("frontmatter 别名存在递归")

        if not is_collection:
            return super().compose_node(parent, index)

        self._modus_depth += 1
        if self._modus_depth > _MAX_FRONTMATTER_DEPTH:
            self._modus_depth -= 1
            raise _UnsafeFrontmatter("frontmatter 深度超过预算")
        if anchor is not None:
            if anchor in self._modus_active_anchors:
                self._modus_depth -= 1
                raise _UnsafeFrontmatter("frontmatter 锚点存在递归")
            self._modus_active_anchors.add(anchor)
        try:
            return super().compose_node(parent, index)
        finally:
            if anchor is not None:
                self._modus_active_anchors.remove(anchor)
            self._modus_depth -= 1


def _collection_children(value: object) -> tuple[object, ...] | None:
    if isinstance(value, Mapping):
        return tuple(item for pair in value.items() for item in pair)
    if isinstance(value, (Sequence, Set)) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return None


def _validate_loaded_yaml_graph(value: object) -> None:
    """Bound alias-expanded traversal and reject cycles in constructed values."""
    # Frames are (entering, value, depth). Exit frames make the active set an
    # ancestry set rather than a global de-dup set, so harmless shared aliases
    # remain compatible while recursive aliases fail closed.
    stack: list[tuple[bool, object, int]] = [(True, value, 0)]
    active: set[int] = set()
    nodes = 0
    while stack:
        entering, current, depth = stack.pop()
        children = _collection_children(current)
        if children is None:
            if entering:
                nodes += 1
                if nodes > _MAX_FRONTMATTER_NODES:
                    raise _UnsafeFrontmatter("展开后的 frontmatter 节点超过预算")
            continue

        identity = id(current)
        if not entering:
            active.remove(identity)
            continue
        nodes += 1
        if nodes > _MAX_FRONTMATTER_NODES:
            raise _UnsafeFrontmatter("展开后的 frontmatter 节点超过预算")
        if depth > _MAX_FRONTMATTER_DEPTH:
            raise _UnsafeFrontmatter("展开后的 frontmatter 深度超过预算")
        if identity in active:
            raise _UnsafeFrontmatter("frontmatter 值存在递归")
        active.add(identity)
        stack.append((False, current, depth))
        stack.extend((True, child, depth + 1) for child in reversed(children))


def split_frontmatter(text: str, *, strict: bool = False) -> tuple[dict[str, Any], str]:
    """Split ``text`` into ``(frontmatter_dict, body)``.

    Returns ``({}, text)`` when there is no leading ``---`` frontmatter block or
    when it does not parse as a YAML mapping.
    """
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        source = m.group(1)
        if len(source) > _MAX_FRONTMATTER_CHARS:
            raise _UnsafeFrontmatter("frontmatter 字符数超过预算")
        # Construct through SafeLoader directly so its resource bounds remain in
        # force; safe_load() alone would discard our depth and alias guards.
        loader = _BoundedSafeLoader(source, reject_duplicates=strict)
        try:
            data = loader.get_single_data()
        finally:
            loader.dispose()
        _validate_loaded_yaml_graph(data)
    except (yaml.YAMLError, RecursionError, _UnsafeFrontmatter) as exc:
        if strict:
            mark = getattr(exc, "problem_mark", None)
            detail = (
                str(exc)
                if isinstance(exc, _UnsafeFrontmatter)
                else (
                    f"frontmatter 第 {mark.line + 2} 行 YAML 无效"
                    if mark
                    else "frontmatter 无效或超过解析预算"
                )
            )
            raise ValueError(detail) from exc
        return {}, text
    if not isinstance(data, dict):
        return {}, m.group(2)
    return data, m.group(2)


def render(frontmatter: Mapping[str, Any], body: str) -> str:
    """Render a SKILL.md from a frontmatter mapping + body string."""
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{fm}\n---\n\n{body.strip()}\n"


__all__ = ["DOMAIN_SKILL_KIND", "MODULE_SKILL_KIND", "render", "split_frontmatter"]
