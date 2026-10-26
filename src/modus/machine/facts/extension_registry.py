"""Built-in N2 extension registry.

This module owns the implementations that may observe source input. It does
not discover entry points or import third-party code: extending the registry is
an explicit repository change that must be accompanied by a declaration and a
fixture. The immutable registry is the single dispatch surface used by the
structural, compiler, entry-detection, and boundary-observation pipelines.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Generic, TypeVar, cast

from ..errors import ConfigurationError
from .contracts import BoundaryResolver, CompilerProvider, EntryDetector, StructuralExtractor

Implementation = TypeVar("Implementation", bound=Callable[..., Any])


@dataclass(frozen=True, slots=True)
class RegisteredImplementation(Generic[Implementation]):
    """A versioned implementation addressable from ``language-registry.json``."""

    name: str
    version: str
    implementation: Implementation

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ConfigurationError(
                "machine.facts.invalid-extension-registration",
                "extension names and versions are required",
            )


def _index(
    kind: str,
    implementations: Iterable[RegisteredImplementation[Implementation]],
) -> Mapping[str, RegisteredImplementation[Implementation]]:
    indexed: dict[str, RegisteredImplementation[Implementation]] = {}
    for extension in implementations:
        if extension.name in indexed:
            raise ConfigurationError(
                "machine.facts.duplicate-extension-registration",
                f"duplicate {kind} registration",
                details={"kind": kind, "name": extension.name},
            )
        indexed[extension.name] = extension
    return MappingProxyType(indexed)


@dataclass(frozen=True, slots=True)
class ExtensionRegistry:
    """Immutable implementations scheduled by the N2 observation stage."""

    structural_extractors: Mapping[str, RegisteredImplementation[StructuralExtractor]]
    compiler_providers: Mapping[str, RegisteredImplementation[CompilerProvider]]
    entry_detectors: Mapping[str, RegisteredImplementation[EntryDetector]]
    boundary_resolvers: Mapping[str, RegisteredImplementation[BoundaryResolver]]

    @classmethod
    def create(
        cls,
        *,
        structural_extractors: Iterable[RegisteredImplementation[StructuralExtractor]],
        compiler_providers: Iterable[RegisteredImplementation[CompilerProvider]],
        entry_detectors: Iterable[RegisteredImplementation[EntryDetector]],
        boundary_resolvers: Iterable[RegisteredImplementation[BoundaryResolver]],
    ) -> ExtensionRegistry:
        """Build a registry while rejecting duplicate implementation names."""
        return cls(
            _index("structural extractor", structural_extractors),
            _index("compiler provider", compiler_providers),
            _index("entry detector", entry_detectors),
            _index("boundary resolver", boundary_resolvers),
        )


def _identity_boundary(_source: Any, facts: dict[str, Any]) -> dict[str, Any]:
    """A scheduled boundary resolver for languages with inline observations."""
    return facts


# Keep registration order stable; implementation imports remain lazy below.
_STRUCTURAL_EXTRACTOR_NAMES = (
    "extract_python",
    "extract_js",
    "extract_java",
    "extract_go",
    "extract_c",
    "extract_cpp",
    "extract_header",
    "extract_objc",
    "extract_objcpp",
    "extract_swift",
    "extract_csharp",
    "extract_kotlin",
    "extract_php",
    "extract_rust",
    "extract_svelte",
    "extract_astro",
    "extract_blade",
    "extract_markdown",
)


@lru_cache(maxsize=1)
def builtin_extensions() -> ExtensionRegistry:
    """Return the process-wide, immutable built-in implementation registry.

    Imports stay inside this function so help, status and ordinary knowledge
    retrieval do not initialize parser and compiler dependencies. Registration
    names and versions form the language registry's dispatch contract.
    """
    from . import structural
    from .compiler.cpp import _run_cpp
    from .compiler.go import _run_go
    from .compiler.java import _run_java
    from .compiler.python import _run_python
    from .compiler.typescript import _run_typescript
    from .entry_contracts import augment_entries
    from .frontend import enrich_frontend_cached
    from .generic import extract_generic_text

    extractors = cast(
        tuple[RegisteredImplementation[StructuralExtractor], ...],
        (
            RegisteredImplementation(
                "extract_generic_text", "generic-text/1", extract_generic_text
            ),
            *(
                RegisteredImplementation(
                    name,
                    "tree-sitter/2",
                    cast(StructuralExtractor, getattr(structural, name)),
                )
                for name in _STRUCTURAL_EXTRACTOR_NAMES
            ),
        ),
    )
    providers = cast(
        tuple[RegisteredImplementation[CompilerProvider], ...],
        (
            RegisteredImplementation("python", "python-builtin/1", _run_python),
            RegisteredImplementation("java", "java-javac/1", _run_java),
            RegisteredImplementation("go", "go-types/1", _run_go),
            RegisteredImplementation("cpp", "cpp-clang/1", _run_cpp),
            RegisteredImplementation("typescript", "typescript-checker/1", _run_typescript),
        ),
    )
    detectors = cast(
        tuple[RegisteredImplementation[EntryDetector], ...],
        tuple(
            RegisteredImplementation(name, "builtin-entry-detector/1", augment_entries)
            for name in ("http", "rpc", "mq", "job", "cli", "public-export")
        ),
    )
    resolvers = cast(
        tuple[RegisteredImplementation[BoundaryResolver], ...],
        (
            RegisteredImplementation(
                "builtin-python-frameworks", "builtin-frameworks/1", enrich_frontend_cached
            ),
            RegisteredImplementation(
                "builtin-go-frameworks", "builtin-frameworks/1", enrich_frontend_cached
            ),
            RegisteredImplementation(
                "builtin-js-frameworks", "builtin-frameworks/1", enrich_frontend_cached
            ),
            RegisteredImplementation(
                "builtin-jvm-frameworks", "builtin-frameworks/1", _identity_boundary
            ),
            RegisteredImplementation(
                "builtin-php-frameworks", "builtin-frameworks/1", _identity_boundary
            ),
        ),
    )
    return ExtensionRegistry.create(
        structural_extractors=extractors,
        compiler_providers=providers,
        entry_detectors=detectors,
        boundary_resolvers=resolvers,
    )


__all__ = [
    "ExtensionRegistry",
    "RegisteredImplementation",
    "builtin_extensions",
]
