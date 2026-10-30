"""Host projection boundary for the neutral Modus distribution.

The package follows a small ports-and-adapters design:

``models``
    Immutable projection data and declarative host layouts.
``base``
    The shared install/uninstall lifecycle and manifest ownership rules.
``rendering`` / ``sections`` / ``hooks``
    Pure content rendering plus non-destructive shared-file editors.
``claude`` / ``codex`` / ``cursor`` / ``codebuddy`` / ``dsh``
    Thin adapters that state only host paths, metadata, and presentation quirks.

Downstream code normally needs only the stable facade exported here.
"""

from .base import Command, PlatformAdapter, Skill
from .models import (
    HookFile,
    InstructionFile,
    PlatformLayout,
    ProjectionConfigurationError,
)
from .registry import (
    BUILTIN_REGISTRY,
    PlatformRegistry,
    UnknownPlatformError,
    available_platforms,
    get_adapters,
)

__all__ = [
    "BUILTIN_REGISTRY",
    "Command",
    "HookFile",
    "InstructionFile",
    "PlatformAdapter",
    "PlatformLayout",
    "PlatformRegistry",
    "ProjectionConfigurationError",
    "Skill",
    "UnknownPlatformError",
    "available_platforms",
    "get_adapters",
]
