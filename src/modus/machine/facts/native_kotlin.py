"""Kotlin 包、扩展函数和客户端 DSL 的文件内结构观察。"""

from __future__ import annotations

import re
from typing import Any

from .native_visitor import _children, _FileParser


class KotlinParser(_FileParser):
    def _metadata(self, node: Any) -> dict:
        body = next(
            (
                child
                for child in node.named_children
                if child.type in {"class_body", "function_body", "enum_class_body"}
            ),
            None,
        )
        signature = (
            self.raw[node.start_byte : body.start_byte if body is not None else node.end_byte]
            .decode()
            .strip()
        )
        modifiers = next(
            (child for child in node.named_children if child.type == "modifiers"), None
        )
        words = self.text(modifiers).split()
        return {
            "signature": signature,
            "visibility": next(
                (word for word in words if word in {"private", "protected", "internal", "public"}),
                "public",
            ),
            "expect": "expect" in words,
            "actual": "actual" in words,
            "modifiers": self.text(modifiers),
            "constraints": [
                self.text(child)
                for child in node.named_children
                if child.type == "type_constraints"
            ],
        }

    def _callee(self, node: Any) -> str:
        if node is None:
            return "<dynamic>"
        if node.type in {"identifier", "simple_identifier", "this_expression", "super_expression"}:
            return self.text(node).strip("`")
        if node.type in {"navigation_expression", "navigation_suffix", "user_type"}:
            parts = [
                self._callee(child)
                for child in node.named_children
                if child.type != "type_arguments"
            ]
            return ".".join(parts) if parts else "<dynamic>"
        return "<dynamic>"

    def walk(self, node: Any, scope: dict, owners: tuple[str, ...] = ()) -> None:
        kind = node.type
        if kind in {"line_comment", "multiline_comment", "string_literal"}:
            return
        if kind == "package_header":
            target = next(iter(node.named_children), None)
            self.package = self.text(target)
            return
        if kind == "import":
            match = re.fullmatch(
                r"import\s+([\w.`]+(?:\*)?)(?:\s+as\s+([\w`]+))?\s*;?", self.text(node).strip()
            )
            if match:
                specifier = match[1].replace("`", "")
                tail = specifier.rsplit(".", 1)[-1]
                self.import_row(
                    scope,
                    (match[2] or tail).strip("`"),
                    specifier,
                    tail,
                    "star" if tail == "*" else "named",
                    node.start_point.row + 1,
                )
            return
        if kind in {
            "class_declaration",
            "object_declaration",
            "companion_object",
            "object_literal",
        }:
            name = self.text(node.child_by_field_name("name"))
            if not name:
                name = next(
                    (
                        self.text(child)
                        for child in node.named_children
                        if child.type == "identifier"
                    ),
                    "",
                )
            name = name or (
                "Companion"
                if kind == "companion_object"
                else f"object_{node.start_point.row + 1}_{node.start_point.column + 1}"
            )
            inner, nested = self.declare(
                node,
                scope,
                owners,
                name=name,
                kind="type",
                metadata={**self._metadata(node), "kotlinKind": kind},
            )
            for child in node.named_children:
                if child.type in {"class_body", "enum_class_body"}:
                    self.walk(child, inner, nested)
            return
        if kind in {"function_declaration", "secondary_constructor"}:
            name_node = node.child_by_field_name("name")
            name = self.text(name_node).strip("`") or "constructor"
            receiver = next(
                (
                    child
                    for child in node.named_children
                    if child.type in {"user_type", "nullable_type"}
                    and name_node is not None
                    and child.end_byte <= name_node.start_byte
                ),
                None,
            )
            inner, nested = self.declare(
                node,
                scope,
                owners,
                name=name,
                kind="method" if scope["kind"] == "type" else "function",
                metadata={
                    **self._metadata(node),
                    "extensionReceiver": self.text(receiver),
                },
            )
            body = next(
                (child for child in node.named_children if child.type == "function_body"), None
            )
            if body is not None:
                self.walk(body, inner, nested)
            return
        if kind == "property_declaration":
            variable = next(
                (
                    child
                    for child in node.named_children
                    if child.type in {"variable_declaration", "multi_variable_declaration"}
                ),
                None,
            )
            names = (
                [child for child in variable.named_children if child.type == "identifier"]
                if variable
                else []
            )
            if variable is not None and variable.type == "multi_variable_declaration":
                names = [
                    next(iter(child.named_children), child)
                    for child in variable.named_children
                    if child.type == "variable_declaration"
                ]
            for name_node in names:
                assert variable is not None
                name = self.text(name_node)
                if scope["kind"] in {"type", "module"}:
                    self.declare(
                        node,
                        scope,
                        owners,
                        name=name,
                        kind="property",
                        metadata={
                            **self._metadata(node),
                            "signature": self.raw[node.start_byte : variable.end_byte]
                            .decode()
                            .strip(),
                        },
                    )
                else:
                    self.bind(scope, name, "local")
            for child in node.named_children:
                if child != variable:
                    self.walk(child, scope, owners)
            return
        if kind == "lambda_literal":
            inner, nested = self.declare(
                node,
                scope,
                owners,
                name=f"lambda_{node.start_point.row + 1}_{node.start_point.column + 1}",
                kind="function",
                metadata={"signature": "lambda"},
            )
            parameters = next(
                (child for child in node.named_children if child.type == "lambda_parameters"), None
            )
            if parameters is not None:
                for parameter in _children(parameters):
                    if parameter.type == "variable_declaration":
                        parameter_name = next(iter(parameter.named_children), None)
                        self.bind(inner, self.text(parameter_name), "parameter")
            else:
                self.bind(inner, "it", "parameter")
            for child in node.named_children:
                if child != parameters:
                    self.walk(child, inner, nested)
            return
        if kind == "binary_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if (
                self.text(node.child_by_field_name("operator")) == ">"
                and left is not None
                and left.type == "binary_expression"
                and self.text(left.child_by_field_name("operator")) == "<"
                and right is not None
                and right.type == "lambda_literal"
            ):
                callee = left.child_by_field_name("left")
                self.reference(
                    node,
                    scope,
                    name=self._callee(callee),
                    metadata={
                        "syntaxRecovery": "generic-trailing-lambda",
                    },
                )
                self.walk(right, scope, owners)
                return
        if kind == "call_expression":
            callee = next(iter(node.named_children), None)
            if callee is None or callee.type != "call_expression":
                self.reference(node, scope, name=self._callee(callee))
            for child in node.named_children:
                self.walk(child, scope, owners)
            return
        for child in node.named_children:
            self.walk(child, scope, owners)

    def result(self, partial: bool):
        facts = super().result(partial)
        if any(row.get("syntaxRecovery") for row in self.references):
            facts["analysisCompleteness"] = "partial"
            facts["diagnostics"].append(
                {
                    "code": "machine.facts.kotlin-generic-call-candidate",
                    "path": self.relative,
                    "message": "语法树将泛型尾随闭包解析成比较表达式；调用仅作为候选保留。",
                }
            )
        private = {
            row["name"]
            for row in self.declarations
            if row["scope_id"] == self.root_scope["id"] and row.get("visibility") == "private"
        }
        self.exports[:] = [row for row in self.exports if row["name"] not in private]
        return facts
