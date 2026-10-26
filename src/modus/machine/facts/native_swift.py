"""Swift 文件内结构；模块装配、类型推断及运行时派发由后续证据决定。"""

from __future__ import annotations

import re
from typing import Any

from .native_visitor import _children, _FileParser

_FUNCTIONS = {
    "function_declaration",
    "protocol_function_declaration",
    "init_declaration",
    "deinit_declaration",
    "subscript_declaration",
}
_TYPES = {"class_declaration", "protocol_declaration"}


class SwiftParser(_FileParser):
    def parameters(self, node: Any, scope: dict) -> None:
        for parameter in node.named_children:
            if parameter.type != "parameter":
                continue
            names = parameter.children_by_field_name("name")
            name = next((child for child in names if child.type == "simple_identifier"), None)
            if name is not None:
                self.bind(scope, self.text(name).strip("`"), "parameter")

    def _metadata(self, node: Any) -> dict:
        body = node.child_by_field_name("body") or node.child_by_field_name("computed_value")
        end = body.start_byte if body is not None else node.end_byte
        modifiers = next(
            (child for child in node.named_children if child.type == "modifiers"), None
        )
        text = self.text(modifiers)
        visibility = next(
            (
                word
                for word in ("private", "fileprivate", "internal", "public", "open")
                if re.search(r"\b" + word + r"\b", text)
            ),
            "internal",
        )
        return {
            "signature": self.raw[node.start_byte : end].decode().strip(),
            "visibility": visibility,
            "attributes": [
                self.text(child) for child in _children(modifiers) if child.type == "attribute"
            ]
            if modifiers
            else [],
            "constraints": [
                self.text(child)
                for child in node.named_children
                if child.type == "type_constraints"
            ],
        }

    def _labels(self, node: Any) -> list[str]:
        labels = []
        for child in node.named_children:
            if child.type != "parameter":
                continue
            external = child.child_by_field_name("external_name")
            names = child.children_by_field_name("name")
            local = next((item for item in names if item.type == "simple_identifier"), None)
            labels.append(self.text(external or local).strip("`"))
        return labels

    def _callee(self, node: Any) -> str:
        if node is None:
            return "<dynamic>"
        if node.type in {
            "simple_identifier",
            "type_identifier",
            "self_expression",
            "super_expression",
        }:
            return self.text(node).strip("`")
        if node.type in {"navigation_expression", "navigation_suffix", "user_type", "identifier"}:
            parts = [
                self._callee(child)
                for child in node.named_children
                if child.type not in {"type_arguments", "type_parameters"}
            ]
            return (
                ".".join(parts)
                if parts and all(part != "<dynamic>" for part in parts)
                else "<dynamic>"
            )
        return "<dynamic>"

    def walk(self, node: Any, scope: dict, owners: tuple[str, ...] = ()) -> None:
        kind = node.type
        if kind in {
            "comment",
            "multiline_comment",
            "line_string_literal",
            "multi_line_string_literal",
        }:
            return
        if kind == "import_declaration":
            name = next(
                (child for child in node.named_children if child.type == "identifier"), None
            )
            target = self.text(name)
            if target:
                self.import_row(scope, "", target, "*", "module", node.start_point.row + 1)
            return
        if kind in _TYPES:
            name = self.text(node.child_by_field_name("name"))
            declaration_kind = self.text(node.child_by_field_name("declaration_kind"))
            metadata = {**self._metadata(node), "swiftKind": declaration_kind}
            if declaration_kind == "extension":
                metadata["extensionTarget"] = name
            inner, nested = self.declare(
                node, scope, owners, name=name, kind="type", metadata=metadata
            )
            body = node.child_by_field_name("body")
            if body is not None:
                self.walk(body, inner, nested)
            return
        if kind in _FUNCTIONS:
            name = self.text(node.child_by_field_name("name")) or kind.removesuffix("_declaration")
            inner, nested = self.declare(
                node,
                scope,
                owners,
                name=name.strip("`"),
                kind="method" if scope["kind"] == "type" else "function",
                metadata={
                    **self._metadata(node),
                    "argumentLabels": self._labels(node),
                },
            )
            body = node.child_by_field_name("body")
            if body is not None:
                self.walk(body, inner, nested)
            return
        if kind == "property_declaration":
            pattern = node.child_by_field_name("name")
            names = (
                [child for child in _children(pattern) if child.type == "simple_identifier"]
                if pattern
                else []
            )
            computed = node.child_by_field_name("computed_value")
            value = node.child_by_field_name("value")
            for name_node in names:
                name = self.text(name_node).strip("`")
                if scope["kind"] in {"type", "module"}:
                    metadata = self._metadata(node)
                    if value is not None:
                        metadata["signature"] = (
                            self.raw[node.start_byte : value.start_byte]
                            .decode()
                            .strip()
                            .rstrip("=")
                            .strip()
                        )
                    inner, nested = self.declare(
                        node, scope, owners, name=name, kind="property", metadata=metadata
                    )
                    if computed is not None:
                        self.walk(computed, inner, nested)
                else:
                    self.bind(scope, name, "local")
            for child in node.named_children:
                if child is not pattern and child != computed:
                    self.walk(child, scope, owners)
            return
        if kind == "lambda_literal":
            inner, nested = self.declare(
                node,
                scope,
                owners,
                name=f"lambda_{node.start_point.row + 1}_{node.start_point.column + 1}",
                kind="function",
                metadata={"signature": "closure"},
            )
            for child in node.named_children:
                if child.type in {"lambda_function_type", "lambda_function_type_parameters"}:
                    for item in _children(child):
                        if item.type == "simple_identifier":
                            self.bind(inner, self.text(item), "parameter")
                else:
                    self.walk(child, inner, nested)
            return
        if kind == "call_expression":
            callee = next(iter(node.named_children), None)
            labels = []
            suffix = next(
                (child for child in node.named_children if child.type == "call_suffix"), None
            )
            if suffix:
                arguments = next(
                    (child for child in suffix.named_children if child.type == "value_arguments"),
                    None,
                )
                if arguments:
                    for argument in arguments.named_children:
                        label = argument.child_by_field_name("name")
                        labels.append(self.text(label) or "_")
            self.reference(
                node, scope, name=self._callee(callee), metadata={"argumentLabels": labels}
            )
            for child in node.named_children:
                self.walk(child, scope, owners)
            return
        for child in node.named_children:
            self.walk(child, scope, owners)

    def result(self, partial: bool):
        for declaration in self.declarations:
            if (
                declaration["scope_id"] == self.root_scope["id"]
                and declaration.get("visibility") not in {"private", "fileprivate"}
                and declaration.get("swiftKind") != "extension"
            ):
                self.exports.append(
                    {
                        "name": declaration["name"],
                        "local": declaration["name"],
                        "scope_id": self.root_scope["id"],
                    }
                )
        return super().result(partial)
