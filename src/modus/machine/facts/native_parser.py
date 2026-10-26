"""File-local syntax observations for the Modus analysis contract.

This module only reads its source argument. Project configuration, filesystem
lookups and cross-file identity decisions belong to native_binding. A cached
FileFacts value contains no tree-sitter objects and no repository-wide state.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable

from modus.machine.corpus.source_snapshot import SourcePath, parse_source
from modus.machine.facts import native_syntax
from modus.machine.facts.native_syntax import (
    _GRAMMARS,
    PARSER_CONTRACT_VERSION,
    component_script_bytes,
    file_identity,
)
from modus.machine.facts.native_visitor import _FileParser
from modus.machine.store.ids import make_id

# Public parser contracts remain available at their original import location.
FileFacts = native_syntax.FileFacts
Extractor = native_syntax.Extractor
REFERENCE_CONTEXTS = native_syntax.REFERENCE_CONTEXTS


def _syntax_tree(path: SourcePath, language: str, raw: bytes):
    from tree_sitter import Language, Parser

    module_name, factory = _GRAMMARS[language]
    module = importlib.import_module("tree_sitter_" + module_name)
    return parse_source(path, Parser(Language(getattr(module, factory)())), raw)


def _header_language(path: SourcePath, raw: bytes) -> str:
    """只使用冻结语法判定歧义头文件；注释、字符串不能成为语言证据。"""
    from modus.machine.facts.native_visitor import _children

    cpp_tree = _syntax_tree(path, "cpp", raw)
    cpp = any(
        node.type
        in {
            "namespace_definition",
            "class_specifier",
            "template_declaration",
            "qualified_identifier",
            "reference_declarator",
            "linkage_specification",
            "using_declaration",
            "alias_declaration",
        }
        and not raw[: node.start_byte].rstrip().endswith(b"@")
        for node in _children(cpp_tree.root_node)
    )
    if re.search(
        rb"@\s*(?:interface|implementation|protocol|class|import|property)\b|#\s*import\b", raw
    ):
        objc_tree = _syntax_tree(path, "objective-c", raw)
        objc = any(
            node.type
            in {
                "class_interface",
                "class_implementation",
                "protocol_declaration",
                "class_declaration",
                "protocol_forward_declaration",
                "module_import",
            }
            or node.type == "preproc_include"
            and bool(re.match(rb"#\s*import\b", raw[node.start_byte : node.end_byte]))
            for node in _children(objc_tree.root_node)
        )
        if objc:
            return "objective-cpp" if cpp else "objective-c"
    return "cpp" if cpp else "c"


# 组件模板仅遮罩非脚本字节，访问器仍从原字节提取文本与摘要。
# 语法错误产生 partial 观察，不把可恢复语法树当作完整编译结果。
def parse_file(path: SourcePath, language: str | None = None) -> dict:
    from modus.machine.facts.language_capabilities import capability_for

    language = language or capability_for(str(path)).language
    if path.suffix in {".ts", ".mts", ".cts"}:
        language = "typescript"
    raw = path.read_bytes()
    masked = raw
    if path.suffix == ".h":
        language = _header_language(path, raw)
    if path.suffix in {".vue", ".svelte", ".astro"}:
        masked, typed = component_script_bytes(path, astro=path.suffix == ".astro")
        language = "typescript" if typed else "javascript"
    if path.suffix == ".tsx":
        language = "tsx"
    tree = _syntax_tree(path, language, masked)
    visitor_type: type[_FileParser] = _FileParser
    if language in {"objective-c", "objective-cpp"}:
        from modus.machine.facts.native_objc import ObjectiveCParser

        visitor_type = ObjectiveCParser
    elif language == "swift":
        from modus.machine.facts.native_swift import SwiftParser

        visitor_type = SwiftParser
    elif language == "kotlin":
        from modus.machine.facts.native_kotlin import KotlinParser

        visitor_type = KotlinParser
    elif language == "cpp":
        from modus.machine.facts.native_cpp import CppParser

        visitor_type = CppParser
    visitor = visitor_type(path, language, raw)
    visitor.walk(tree.root_node, visitor.root_scope)
    if language == "objective-cpp":
        _observe_objcpp(visitor, tree.root_node)
    facts: dict = dict(visitor.result(tree.root_node.has_error))
    if language == "objective-cpp":
        facts["analysisCompleteness"] = "partial"
        facts["diagnostics"].append(
            {
                "code": "machine.facts.objcpp-structural-partial",
                "path": visitor.relative,
                "message": "OC 与 C++ 分别恢复结构；宏展开、编译条件及跨语言类型绑定未解析。",
            }
        )
    return facts


def _observe_objcpp(visitor: _FileParser, root) -> None:
    """等长遮罩 OC 后补充 C++；合成方法壳只辅助解析，不进入事实。"""
    from modus.machine.facts.native_cpp import CppParser
    from modus.machine.facts.native_visitor import _children

    raw = visitor.raw
    masked = bytearray(raw)

    def blank(start: int, end: int) -> None:
        masked[start:end] = bytes(byte if byte in (10, 13) else 32 for byte in raw[start:end])

    objc_nodes = list(_children(root))
    for node in objc_nodes:
        if node.type in {"class_interface", "class_implementation", "protocol_declaration"}:
            blank(node.start_byte, node.end_byte)
    scopes = {scope["id"]: scope for scope in visitor.scopes}
    declarations = {
        item["source_ranges"][0]["startByte"]: item
        for item in visitor.nodes
        if item.get("kind") == "method" and item.get("source_ranges")
    }
    bodies: dict[int, tuple[dict, tuple[str, ...]]] = {}
    for node in objc_nodes:
        if node.type != "method_definition":
            continue
        body = next(
            (child for child in node.named_children if child.type == "compound_statement"), None
        )
        declaration = declarations.get(node.start_byte)
        if body is None or declaration is None:
            continue
        header = re.search(rb"[^\r\n]{8,}", bytes(masked[node.start_byte : body.start_byte]))
        if header is None:
            continue
        start = node.start_byte + header.start()
        masked[start : start + 8] = b"void f()"
        masked[body.start_byte : body.end_byte] = raw[body.start_byte : body.end_byte]
        bodies[body.start_byte] = (
            scopes[declaration["body_scope_id"]],
            tuple(declaration["qualified_name"].split(".")),
        )
    for node in objc_nodes:
        if node.type in {
            "message_expression",
            "selector_expression",
            "encode_expression",
            "class_declaration",
            "protocol_forward_declaration",
            "module_import",
        }:
            blank(node.start_byte, node.end_byte)
            if node.type.endswith("expression"):
                masked[node.start_byte] = ord("0")
        elif (
            node.type == "string_expression" and raw[node.start_byte : node.start_byte + 1] == b"@"
        ):
            masked[node.start_byte] = 32
    tree = _syntax_tree(visitor.path, "cpp", bytes(masked))
    cpp = CppParser(visitor.path, "cpp", raw)
    cpp.used_ids.update(visitor.used_ids)

    def walk(node) -> None:
        if node.type == "function_definition":
            body = node.child_by_field_name("body")
            if body is not None and body.start_byte in bodies:
                scope, owners = bodies[body.start_byte]
                cpp.walk(body, scope, owners)
                return
        if any(node.start_byte <= start < node.end_byte for start in bodies):
            for child in node.named_children:
                walk(child)
        else:
            cpp.walk(node, cpp.root_scope)

    walk(tree.root_node)
    visitor.nodes.extend(cpp.nodes[1:])
    visitor.scopes.extend(cpp.scopes[1:])
    for field in ("declarations", "edges", "aliases", "references", "exports"):
        getattr(visitor, field).extend(getattr(cpp, field))
    for row in cpp.imports:
        if row not in visitor.imports:
            visitor.imports.append(row)
    visitor.root_scope["bindings"].extend(cpp.root_scope["bindings"])
    visitor.used_ids.update(cpp.used_ids)


# 注册表绑定语言但不持有解析器状态，每个文件拥有独立访问器。
def parser_for(language: str) -> Callable[[SourcePath], dict]:
    def extract(path: SourcePath) -> dict:
        return parse_file(path, language)

    return extract


# 标题只形成文档包含关系，不能当成程序声明或调用证据。
# 入口保持在原模块，现有注册表和消费者无需随访问器拆分改名。
def extract_markdown(path: SourcePath) -> dict:
    """Document headings are deterministic source sections, not semantic code."""
    raw = path.read_bytes()
    parser = _FileParser(path, "markdown", raw)
    for line, text in enumerate(raw.decode("utf-8").splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", text)
        if not match:
            continue
        identity = make_id(parser.prefix, "section", str(line), match[2])
        parser.nodes.append(
            {
                "id": identity,
                "label": match[2],
                "kind": "section",
                "file_type": "document",
                "source_file": parser.relative,
                "source_location": f"L{line}:1",
                "heading_level": len(match[1]),
            }
        )
        parser.edges.append(
            {
                "source": parser.file_id,
                "target": identity,
                "relation": "contains",
                "resolution": "exact",
                "source_file": parser.relative,
                "source_location": f"L{line}:1",
            }
        )
    return dict(parser.result(False))


__all__ = [
    "PARSER_CONTRACT_VERSION",
    "REFERENCE_CONTEXTS",
    "FileFacts",
    "Extractor",
    "component_script_bytes",
    "file_identity",
    "parse_file",
    "parser_for",
    "extract_markdown",
]
