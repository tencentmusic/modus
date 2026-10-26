"""C++ 命名空间、声明和模板调用的结构补充；不执行预处理。"""

from __future__ import annotations

from typing import Any

from .native_visitor import _FileParser


class CppParser(_FileParser):
    def _callee(self, node: Any) -> str:
        if node is None:
            return "<dynamic>"
        if node.type in {
            "identifier",
            "field_identifier",
            "type_identifier",
            "namespace_identifier",
            "this",
            "destructor_name",
            "operator_name",
        }:
            return self.text(node)
        if node.type in {"template_function", "template_method", "template_type"}:
            return self._callee(node.child_by_field_name("name"))
        if node.type == "qualified_identifier":
            head = node.child_by_field_name("scope")
            tail = self._callee(node.child_by_field_name("name"))
            return self._callee(head) + "." + tail if head is not None else tail
        if node.type == "field_expression":
            return (
                self._callee(node.child_by_field_name("argument"))
                + "."
                + self._callee(node.child_by_field_name("field"))
            )
        return "<dynamic>"

    def walk(self, node: Any, scope: dict, owners: tuple[str, ...] = ()) -> None:
        kind = node.type
        if kind in {"comment", "string_literal", "raw_string_literal"}:
            return
        if kind == "namespace_definition":
            name = self.text(node.child_by_field_name("name"))
            name = name.replace("::", ".") or f"anonymous_namespace_{node.start_point.row + 1}"
            inner, nested = self.declare(node, scope, owners, name=name, kind="namespace")
            body = node.child_by_field_name("body")
            if body is not None:
                self.walk(body, inner, nested)
            return
        if kind in {"declaration", "field_declaration"}:
            declarators = node.children_by_field_name("declarator")
            for declarator in declarators:
                current = declarator
                while current is not None and current.type not in {
                    "function_declarator",
                    "init_declarator",
                }:
                    current = current.child_by_field_name("declarator")
                if current is not None and current.type == "function_declarator":
                    name_node = self.name_node(current)
                    if name_node is not None:
                        if node.has_error and node.child_by_field_name("type") is None:
                            self.reference(
                                node,
                                scope,
                                name=self.text(name_node),
                                context="value",
                                metadata={"syntaxRole": "unexpanded-macro-or-invalid-declaration"},
                            )
                            continue
                        self.declare(
                            node,
                            scope,
                            owners,
                            name=self.text(name_node).replace("::", "."),
                            kind="method" if scope["kind"] == "type" else "function",
                            metadata={"declarationOnly": True},
                        )
                else:
                    name_node = self.name_node(declarator)
                    if name_node is None and declarator.type in {"identifier", "field_identifier"}:
                        name_node = declarator
                    if name_node is not None:
                        self.bind(scope, self.text(name_node), "local")
                    self.walk(declarator, scope, owners)
            for child in node.named_children:
                if child not in declarators:
                    self.walk(child, scope, owners)
            return
        if kind == "function_definition":
            name_node = self.name_node(node)
            name = self.text(name_node).replace("::", ".")
            if name:
                parts = name.split(".")
                inner, nested = self.declare(
                    node,
                    scope,
                    (*owners, *parts[:-1]),
                    name=parts[-1],
                    metadata={"declarationOnly": False},
                )
                body = node.child_by_field_name("body")
                if body is not None:
                    self.walk(body, inner, nested)
                return
        if kind == "call_expression":
            callee = node.child_by_field_name("function")
            self.reference(node, scope, name=self._callee(callee))
            for child in node.named_children:
                self.walk(child, scope, owners)
            return
        if kind == "lambda_expression":
            inner, nested = self.declare(
                node,
                scope,
                owners,
                name=f"lambda_{node.start_point.row + 1}_{node.start_point.column + 1}",
                kind="function",
            )
            for child in node.named_children:
                self.walk(child, inner, nested)
            return
        super().walk(node, scope, owners)
