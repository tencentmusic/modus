"""Immutable domain models for platform projection.

The platform package translates a neutral Modus distribution into host-specific
files.  These models make that translation declarative: an adapter describes
*where* each artifact belongs, while :mod:`modus.platforms.base` owns the
installation lifecycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


class ProjectionConfigurationError(ValueError):
    """A platform declares an invalid or unsafe project-relative layout."""


def validate_relative_path(value: str, *, label: str = "接入路径") -> str:
    """Validate and return a canonical POSIX path relative to a project root.

    Projection paths are persisted in manifests and later joined to a project
    root.  Rejecting platform-native separators and traversal components here
    keeps that boundary explicit for both built-in and third-party adapters.
    """

    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(character) < 32 for character in value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ProjectionConfigurationError(f"{label} 必须为规范的项目相对 POSIX 路径： {value!r}")
    return value


def _validate_artifact_name(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ProjectionConfigurationError(f"{label} 必须为不带首尾空白的非空字符串")
    if (
        "/" in value
        or "\\" in value
        or value in {".", ".."}
        or any(ord(character) < 32 for character in value)
    ):
        raise ProjectionConfigurationError(f"{label} 必须为单个路径片段： {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class Skill:
    """One neutral skill bundle ready to be projected onto a host."""

    name: str
    description: str
    body: str
    support_files: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_artifact_name(self.name, label="技能名称")
        if not isinstance(self.description, str) or not isinstance(self.body, str):
            raise TypeError("技能描述与正文必须为字符串")

        support_files = dict(self.support_files)
        for relative_path, content in support_files.items():
            validate_relative_path(relative_path, label="技能支持文件路径")
            if not isinstance(content, str):
                raise TypeError(f"技能支持文件内容必须为文本： {relative_path}")
        object.__setattr__(self, "support_files", MappingProxyType(support_files))


@dataclass(frozen=True, slots=True)
class Command:
    """One neutral slash-command document ready for host projection."""

    name: str
    body: str

    def __post_init__(self) -> None:
        _validate_artifact_name(self.name, label="命令名称")
        if not isinstance(self.body, str):
            raise TypeError("命令正文必须为文本")


@dataclass(frozen=True, slots=True)
class InstructionFile:
    """A shared host instruction file containing one Modus-owned section."""

    path: str
    marker: str
    preamble: str = ""

    def __post_init__(self) -> None:
        validate_relative_path(self.path, label="指引文件路径")
        if (
            not isinstance(self.marker, str)
            or not self.marker
            or self.marker.strip() != self.marker
            or "\n" in self.marker
            or "-->" in self.marker
        ):
            raise ProjectionConfigurationError(f"受管区块标记无效： {self.marker!r}")
        if not isinstance(self.preamble, str):
            raise TypeError("指引文件前言必须为文本")


@dataclass(frozen=True, slots=True)
class PlatformLayout:
    """Declarative filesystem contract for one platform adapter.

    ``owned_file_prefixes`` only covers files Modus can delete outright.
    Shared instruction files have section-based ownership and are therefore
    intentionally modeled separately.
    """

    skills_root: str
    owned_file_prefixes: tuple[str, ...]
    instructions: InstructionFile
    commands_root: str | None = None

    def __post_init__(self) -> None:
        validate_relative_path(self.skills_root, label="技能根目录")
        if self.commands_root is not None:
            validate_relative_path(self.commands_root, label="命令根目录")
        if not self.owned_file_prefixes:
            raise ProjectionConfigurationError("平台必须声明其拥有的文件前缀")

        for prefix in self.owned_file_prefixes:
            if not prefix.endswith("/"):
                raise ProjectionConfigurationError(f"所有权文件前缀必须以 '/' 结尾： {prefix!r}")
            validate_relative_path(prefix[:-1], label="所有权文件前缀")

        projected_roots = [self.skills_root]
        if self.commands_root is not None:
            projected_roots.append(self.commands_root)
        for root in projected_roots:
            relative = f"{root}/"
            if not any(relative.startswith(prefix) for prefix in self.owned_file_prefixes):
                raise ProjectionConfigurationError(
                    f"平台接入根目录 {root!r} 未被所有权文件前缀覆盖"
                )
