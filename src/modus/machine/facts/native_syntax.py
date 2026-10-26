"""File-local syntax vocabulary and coordinate contracts shared by extractors.

The grammar table and node categories describe syntax only. They do not resolve
imports, inspect project manifests or choose a runtime target. File identities
are relative to the active extraction root; component masking preserves every
source byte position used by parser and framework observations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol, TypedDict

from modus.machine.corpus.source_snapshot import SourcePath
from modus.machine.store.ids import make_id

PARSER_CONTRACT_VERSION = 1
REFERENCE_CONTEXTS = frozenset(
    {"call", "callback", "value", "inheritance", "type", "decorator", "export"}
)


class FileFacts(TypedDict, total=False):
    """One file's cached extraction result under the parser contract.

    Values are plain JSON-serialisable data: no tree-sitter handles, no
    absolute paths, no repository-wide state. Key spelling (camelCase and
    snake_case alike) is part of the persisted cache contract and must not
    be renamed without bumping ``PARSER_CONTRACT_VERSION``.
    """

    path: str
    language: str
    package: str
    parserContract: int
    sourceDigest: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    scopes: list[dict[str, Any]]
    declarations: list[dict[str, Any]]
    imports: list[dict[str, Any]]
    exports: list[dict[str, Any]]
    aliases: list[dict[str, Any]]
    references: list[dict[str, Any]]
    raw_calls: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    analysisCompleteness: str
    input_tokens: int
    output_tokens: int
    error: str
    skipped: str
    cacheStats: dict[str, int]


class Extractor(Protocol):
    """Callable that turns one source file into :class:`FileFacts`-shaped data."""

    # 位置参数协议不要求第三方解析器采用同一个形参名。
    def __call__(self, __path: SourcePath) -> dict[str, Any]:
        """Observe one frozen source without retaining parser-native objects."""


_GRAMMARS = {
    "python": ("python", "language"),
    "javascript": ("javascript", "language"),
    "typescript": ("typescript", "language_typescript"),
    "tsx": ("typescript", "language_tsx"),
    "java": ("java", "language"),
    "go": ("go", "language"),
    "c": ("c", "language"),
    "cpp": ("cpp", "language"),
    "csharp": ("c_sharp", "language"),
    "kotlin": ("kotlin", "language"),
    "objective-c": ("objc", "language"),
    "objective-cpp": ("objc", "language"),
    "swift": ("swift", "language"),
    "php": ("php", "language_php"),
    "rust": ("rust", "language"),
}
_TYPE_NODES = frozenset(
    {
        "class_definition",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "class_specifier",
        "struct_specifier",
        "struct_item",
        "enum_item",
        "trait_item",
        "type_spec",
        "object_declaration",
        "impl_item",
    }
)
_FUNCTION_NODES = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_declaration",
        "constructor_declaration",
        "method_definition",
        "function_item",
        "local_function_statement",
        "function_signature",
        "method_signature",
        "abstract_method_signature",
    }
)
_LAMBDAS = frozenset(
    {
        "arrow_function",
        "function_expression",
        "lambda",
        "lambda_expression",
        "anonymous_function",
        "closure_expression",
        "func_literal",
    }
)
_CALL_NODES = frozenset(
    {
        "call",
        "call_expression",
        "method_invocation",
        "invocation_expression",
        "member_call_expression",
        "scoped_call_expression",
        "nullsafe_member_call_expression",
    }
)
_IDENTIFIERS = frozenset(
    {
        "identifier",
        "name",
        "simple_identifier",
        "property_identifier",
        "field_identifier",
        "variable_name",
    }
)


def file_identity(path: SourcePath) -> tuple[str, str, str]:
    from modus.machine.facts.extraction_cache import project_root

    root = project_root() or Path(path).parent
    relative = Path(path).relative_to(root).as_posix()
    return relative, make_id(relative), make_id(str(Path(relative).with_suffix("")))


def component_script_bytes(path: SourcePath, *, astro: bool = False) -> tuple[bytes, bool]:
    """Mask template bytes without moving a script's original coordinates."""
    raw = path.read_bytes()
    masked = bytearray(10 if byte == 10 else 32 for byte in raw)
    ranges: list[tuple[int, int]] = []
    typescript = False
    if astro:
        match = re.match(rb"\s*---[^\n]*\n(.*?)\n---", raw, re.DOTALL)
        if match:
            ranges.append(match.span(1))
            typescript = True
    for match in re.finditer(
        rb"<script\b([^>]*)>(.*?)</script\s*>", raw, re.DOTALL | re.IGNORECASE
    ):
        ranges.append(match.span(2))
        typescript = typescript or bool(
            re.search(rb"lang\s*=\s*['\"](?:ts|typescript)['\"]", match[1], re.IGNORECASE)
        )
    for start, end in ranges:
        masked[start:end] = raw[start:end]
    return bytes(masked), typescript
