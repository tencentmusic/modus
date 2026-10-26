"""Objective-C 的 selector、类型片段与消息观察；不推断运行时派发。"""

from __future__ import annotations

import re
from typing import Any

from .native_visitor import _children, _FileParser

_TYPES = {"class_interface", "class_implementation", "protocol_declaration"}
_METHODS = {"method_declaration", "method_definition"}


class ObjectiveCParser(_FileParser):
    def parameters(self, node: Any, scope: dict) -> None:
        if node.type not in _METHODS:
            super().parameters(node, scope)
            return
        for parameter in node.named_children:
            if parameter.type == "method_parameter":
                names = [child for child in parameter.named_children if child.type == "identifier"]
                if names:
                    self.bind(scope, self.text(names[-1]), "parameter")

    def _selector(self, node: Any) -> str:
        if node.type == "message_expression":
            names = node.children_by_field_name("method")
            return (
                "".join(self.text(name) + ":" for name in names)
                if any(child.type == ":" for child in node.children)
                else "".join(self.text(name) for name in names)
            )
        parts: list[str] = []
        for child in node.named_children:
            if child.type == "identifier":
                parts.append(self.text(child))
            elif child.type == "method_parameter":
                if not parts:
                    parts.append("")
                parts[-1] += ":"
        return "".join(parts)

    def _type(self, node: Any, scope: dict, owners: tuple[str, ...]) -> None:
        name_node = next(
            (child for child in node.named_children if child.type == "identifier"), None
        )
        if name_node is None:
            return
        name = self.text(name_node)
        category = self.text(node.child_by_field_name("category"))
        role = node.type.removeprefix("class_").removesuffix("_declaration")
        members = [
            child
            for child in node.named_children
            if child.type
            in _METHODS
            | {
                "property_declaration",
                "implementation_definition",
                "instance_variables",
            }
        ]
        end = members[0].start_byte if members else node.end_byte
        inner, nested = self.declare(
            node,
            scope,
            owners,
            name=name,
            kind="type",
            metadata={
                "objcClass": name,
                "category": category,
                "objcRole": role,
                "signature": self.raw[node.start_byte : end].decode().removesuffix("@end").strip(),
                "superclass": self.text(node.child_by_field_name("superclass")),
                "protocols": [
                    self.text(child)
                    for child in node.named_children
                    if child.type
                    in {
                        "protocol_reference_list",
                        "parameterized_arguments",
                    }
                ],
            },
        )
        for child in node.named_children:
            if child.type not in {
                "identifier",
                "parameterized_arguments",
                "protocol_reference_list",
            }:
                self.walk(child, inner, nested)

    def _method(self, node: Any, scope: dict, owners: tuple[str, ...]) -> None:
        selector = self._selector(node)
        if not selector:
            return
        body = next(
            (child for child in node.named_children if child.type == "compound_statement"), None
        )
        end = body.start_byte if body is not None else node.end_byte
        inner, nested = self.declare(
            node,
            scope,
            owners,
            name=selector,
            kind="method",
            metadata={
                "objcSelector": selector,
                "methodKind": "class" if self.text(node).lstrip().startswith("+") else "instance",
                "signature": self.raw[node.start_byte : end].decode().strip(),
                "declarationOnly": body is None,
            },
        )
        if body is not None:
            self.walk(body, inner, nested)

    def _property(self, node: Any, scope: dict, owners: tuple[str, ...]) -> None:
        for declarator in _children(node):
            if declarator.type != "struct_declarator":
                continue
            name = self.name_node(declarator)
            if name is None:
                name = next(
                    (child for child in _children(declarator) if child.type == "identifier"), None
                )
            if name is not None:
                self.declare(
                    node,
                    scope,
                    owners,
                    name=self.text(name),
                    kind="property",
                    metadata={
                        "signature": self.text(node),
                        "propertyAttributes": [
                            self.text(item)
                            for item in _children(node)
                            if item.type == "property_attribute"
                        ],
                    },
                )

    def walk(self, node: Any, scope: dict, owners: tuple[str, ...] = ()) -> None:
        kind = node.type
        if kind in {"comment", "string_literal", "string_expression"}:
            return
        if kind in _TYPES:
            self._type(node, scope, owners)
            return
        if kind in _METHODS:
            self._method(node, scope, owners)
            return
        if kind == "property_declaration":
            self._property(node, scope, owners)
            return
        if kind in {"class_declaration", "protocol_forward_declaration"}:
            return
        if kind == "preproc_include":
            target = node.child_by_field_name("path")
            if target is not None:
                self.import_row(
                    scope,
                    "",
                    self.text(target).strip('<>"'),
                    "*",
                    "include",
                    node.start_point.row + 1,
                )
            return
        if kind == "module_import":
            target = self.text(node.child_by_field_name("path"))
            self.import_row(scope, "", target, "*", "module", node.start_point.row + 1)
            return
        if kind == "message_expression":
            selector = self._selector(node)
            receiver = node.child_by_field_name("receiver")
            receiver_text = self.text(receiver)
            simple_receiver = bool(re.fullmatch(r"[\w.]+", receiver_text))
            name = (receiver_text if simple_receiver else "<dynamic>") + "." + selector
            self.reference(node, scope, name=name, metadata={"objcSelector": selector})
            for child in node.named_children:
                self.walk(child, scope, owners)
            return
        if kind == "selector_expression":
            match = re.fullmatch(r"@selector\s*\(\s*([\w\s:]+)\s*\)", self.text(node))
            if match:
                selector = re.sub(r"\s+", "", match[1])
                self.reference(
                    node,
                    scope,
                    name=selector,
                    context="callback",
                    metadata={"objcSelector": selector},
                )
            return
        if kind == "block_literal":
            inner, nested = self.declare(
                node,
                scope,
                owners,
                name=f"block_{node.start_point.row + 1}_{node.start_point.column + 1}",
                kind="function",
            )
            for child in node.named_children:
                self.walk(child, inner, nested)
            return
        if self.language == "objective-cpp":
            for child in node.named_children:
                self.walk(child, scope, owners)
        else:
            super().walk(node, scope, owners)
