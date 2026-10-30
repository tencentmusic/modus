"""Validated adapter registry and the built-in platform catalog."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from .base import PlatformAdapter
from .claude import ClaudeAdapter
from .codebuddy import CodeBuddyAdapter
from .codex import CodexAdapter
from .cursor import CursorAdapter
from .dsh import DshAdapter


class UnknownPlatformError(ValueError):
    """One or more requested platform names are not registered."""

    def __init__(self, unknown: Sequence[str], available: Sequence[str]) -> None:
        self.unknown = tuple(unknown)
        self.available = tuple(available)
        super().__init__(
            f"未知平台： {', '.join(self.unknown)}. 可选平台： {', '.join(self.available)}"
        )


@dataclass(frozen=True, slots=True, init=False)
class PlatformRegistry:
    """An immutable, validated collection of platform adapter types.

    The built-in registry remains intentionally closed at runtime. Integrators
    can construct a separate registry with their own adapters for tests or an
    embedding application, without mutating process-global framework state.
    """

    _adapter_types: Mapping[str, type[PlatformAdapter]]

    def __init__(self, adapter_types: Iterable[type[PlatformAdapter]]) -> None:
        adapters: dict[str, type[PlatformAdapter]] = {}
        for adapter_type in adapter_types:
            if not isinstance(adapter_type, type) or not issubclass(adapter_type, PlatformAdapter):
                raise TypeError(f"注册适配器必须继承 PlatformAdapter： {adapter_type!r}")
            name = getattr(adapter_type, "name", "")
            if not isinstance(name, str) or not name or name.strip() != name:
                raise ValueError(f"适配器名称必须为不带首尾空白的非空字符串： {name!r}")
            if name in adapters:
                raise ValueError(f"平台适配器重复： {name}")
            adapters[name] = adapter_type
        object.__setattr__(self, "_adapter_types", MappingProxyType(adapters))

    @property
    def names(self) -> tuple[str, ...]:
        """Return deterministic platform names suitable for CLI and manifests."""

        return tuple(sorted(self._adapter_types))

    def create(self, names: Sequence[str]) -> list[PlatformAdapter]:
        """Instantiate requested adapters in caller-supplied order."""

        unknown = [name for name in names if name not in self._adapter_types]
        if unknown:
            raise UnknownPlatformError(unknown, self.names)
        return [self._adapter_types[name]() for name in names]


BUILTIN_REGISTRY = PlatformRegistry(
    (
        ClaudeAdapter,
        CodexAdapter,
        CursorAdapter,
        CodeBuddyAdapter,
        DshAdapter,
    )
)


def available_platforms() -> list[str]:
    """Return the names accepted by the built-in Modus CLI."""

    return list(BUILTIN_REGISTRY.names)


def get_adapters(names: Sequence[str]) -> list[PlatformAdapter]:
    """Create built-in adapters or raise :class:`UnknownPlatformError`."""

    return BUILTIN_REGISTRY.create(names)
