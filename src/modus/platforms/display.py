"""平台展示词汇；注册名是协议，显示名与交互顺序由此统一维护。"""

from collections.abc import Iterable
from types import MappingProxyType

_PLATFORM_TITLES = MappingProxyType(
    {
        "codex": "Codex",
        "codebuddy": "CodeBuddy",
        "cursor": "Cursor",
        "claude": "Claude Code",
        "dsh": "DeepSeek Harness",
    }
)


def platform_title(name: str) -> str:
    return _PLATFORM_TITLES.get(name, name)


def ordered_platforms(names: Iterable[str]) -> list[str]:
    """内置平台保持熟悉顺序，新注册平台按调用方顺序追加且不重复。"""
    selected = dict.fromkeys(names)
    return [name for name in _PLATFORM_TITLES if name in selected] + [
        name for name in selected if name not in _PLATFORM_TITLES
    ]
