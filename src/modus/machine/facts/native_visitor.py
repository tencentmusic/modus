"""单文件语法树访问器：记录声明、词法作用域和未绑定引用。

这里不查询文件系统、不决定跨文件目标。可序列化观察交给绑定阶段处理，
解析入口和语法选择继续由 native_parser 管理。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from modus.machine.corpus.source_snapshot import SourcePath
from modus.machine.facts.native_syntax import (
    _CALL_NODES,
    _FUNCTION_NODES,
    _IDENTIFIERS,
    _LAMBDAS,
    _TYPE_NODES,
    PARSER_CONTRACT_VERSION,
    FileFacts,
    file_identity,
)
from modus.machine.store.ids import make_id, occurrence_id

_IMPORT_NODES = {
    "import_statement",
    "import_from_statement",
    "import_declaration",
    "import_spec",
    "use_declaration",
    "preproc_include",
}


# 显式栈按源码顺序遍历命名节点，避免递归遍历器自身耗尽 Python 栈。
# 只访问 named_children，标点不应成为标识符或绑定候选。
def _children(node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.named_children))


# 实例只属于一个文件，列表保存纯值观察，不保存跨项目状态。
# 作用域和声明分别建模，局部遮蔽不能仅靠全局名称表表达。
# 引用在此处保留候选名称，真实目标由后续绑定阶段决定。
# 新增语言节点类别放在 native_syntax，避免入口与访问器维护两套词汇。
class _FileParser:
    # 文件根同时是图节点和模块作用域所有者，所有后续观察都能回溯到它。
    # used_ids 只负责本文件声明冲突，不能替代跨文件身份解析。
    # 相对路径由提取上下文提供，输出不携带开发者 checkout 的绝对位置。
    def __init__(self, path: SourcePath, language: str, raw: bytes) -> None:
        self.path, self.language, self.raw = path, language, raw
        self.relative, self.file_id, self.prefix = file_identity(path)
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.scopes: list[dict] = []
        self.declarations: list[dict] = []
        self.imports: list[dict] = []
        self.exports: list[dict] = []
        self.aliases: list[dict] = []  # 别名关系独立于声明，不能直接改写被引用符号。
        self.references: list[dict] = []  # 保留调用点身份，绑定阶段才合并候选目标。
        self.used_ids: set[str] = {self.file_id}
        self.package = ""
        self.root_scope = self.new_scope(self.file_id, "", "module", self.file_id)
        self.nodes.append(
            {
                "id": self.file_id,
                "label": path.name,
                "kind": "file",
                "file_type": "code",
                "source_file": self.relative,
                "source_location": "L1:1",
                "source_end_line": max(1, raw.count(b"\n") + 1),
                "language": language,
                "scope_id": self.root_scope["id"],
            }
        )

    # tree-sitter 提供字节区间，必须先切原始字节再按 UTF-8 解码。
    # 先解码再按字符偏移截取会使中文前后的名称与源码错位。
    def text(self, node) -> str:
        return self.raw[node.start_byte : node.end_byte].decode("utf-8") if node is not None else ""

    # 作用域引用父 scope 和拥有者节点，词法嵌套与图包含关系分别可追溯。
    # 绑定先保存局部声明，再交由项目解析器沿父链查找。
    # 块作用域也使用稳定身份，不能复用兄弟块的局部变量集合。
    def new_scope(self, identity: str, parent: str, kind: str, owner: str) -> dict:
        row = {
            "id": "scope:" + identity,
            "parent": parent,
            "kind": kind,
            "owner": owner,
            "bindings": [],
        }
        self.scopes.append(row)
        return row

    # 对外行列从 1 开始，字节偏移保持 tree-sitter 的半开区间。
    # 显式声明 utf8-byte，消费者不能把列号解释为 Unicode 字符索引。
    # 同一锚点用于声明与调用点，避免不同记录出现坐标口径差异。
    def anchor(self, node) -> dict:
        return {
            "file": self.relative,
            "line": node.start_point.row + 1,
            "column": node.start_point.column + 1,
            "endLine": node.end_point.row + 1,
            "endColumn": node.end_point.column + 1,
            "columnEncoding": "utf8-byte",
            "startByte": node.start_byte,
            "endByte": node.end_byte,
        }

    # PHP 的美元前缀不属于统一绑定名，原语法文本仍可从锚点恢复。
    # 空名称只表示无局部绑定，不应进入可查找符号表。
    def bind(self, scope, name: str, kind: str, **extra) -> None:
        if name:
            scope["bindings"].append({"name": name.lstrip("$"), "kind": kind, **extra})

    # 优先使用语法命名字段，随后才处理 C/C++ 的嵌套 declarator。
    # Rust impl 的类型位置具有独立语义，不能按普通函数名称读取。
    # 最终回退只寻找标识节点，不用任意正文猜测名称。
    def name_node(self, node):
        name = node.child_by_field_name("name")
        if name is not None:
            return name
        declarator = node.child_by_field_name("declarator")
        while declarator is not None:
            if declarator.type in _IDENTIFIERS or declarator.type in {
                "scoped_identifier",
                "qualified_identifier",
            }:
                return declarator
            child = declarator.child_by_field_name("declarator") or declarator.child_by_field_name(
                "name"
            )
            if child is None:
                break
            declarator = child
        if node.type == "impl_item":
            return node.child_by_field_name("type")
        return next(
            (
                child
                for child in node.named_children
                if child.type in _IDENTIFIERS | {"type_identifier"}
            ),
            None,
        )

    # 不同语法的参数根位置不一致，统一到局部作用域的 parameter 绑定。
    # 解构参数只提取命名节点，不把默认值表达式作为参数名字。
    # 参数缺失是合法语法情况，返回空绑定而非虚构占位变量。
    def parameters(self, node, scope) -> None:
        parameter_root = node.child_by_field_name("parameters") or node.child_by_field_name(
            "parameter"
        )
        if parameter_root is None:
            declarator = node.child_by_field_name("declarator")
            if declarator is not None:
                parameter_root = declarator.child_by_field_name("parameters")
        if parameter_root is None:
            parameter_root = next(
                (
                    child
                    for child in node.named_children
                    if child.type
                    in {
                        "parameters",
                        "formal_parameters",
                        "parameter_list",
                        "function_value_parameters",
                    }
                ),
                None,
            )
        if parameter_root is None:
            return
        parameters = (
            [parameter_root]
            if parameter_root.type in _IDENTIFIERS
            else parameter_root.named_children
        )
        for parameter in parameters:
            name = parameter.child_by_field_name("name") or parameter.child_by_field_name("pattern")
            if name is None and parameter.type in _IDENTIFIERS:
                name = parameter
            if name is None:
                name = next(
                    (
                        child
                        for child in parameter.named_children
                        if child.type in _IDENTIFIERS | {"object_pattern", "array_pattern"}
                    ),
                    None,
                )
            if name is not None:
                for part in _children(name):
                    if part.type in _IDENTIFIERS:
                        self.bind(scope, self.text(part), "parameter")

    # 常见声明优先使用可读名称身份，重名时再以源码 occurrence 区分。
    # 匿名函数以行列命名，既可定位也不宣称存在源码中的显式名称。
    # signature 在函数体前截断并限长，避免把实现正文复制进声明摘要。
    # contains 表达语法所有权，因此可以精确；它不证明动态调用目标。
    # 声明所属作用域和函数体作用域分开保存，支持遮蔽与参数解析。
    # 显式 export 的别名单独记录，默认导出名不能覆盖局部声明名。
    def declare(
        self,
        node,
        scope,
        owners: tuple[str, ...],
        *,
        expression=None,
        name: str | None = None,
        kind: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[dict, tuple[str, ...]]:
        name_node = self.name_node(node)
        name = self.text(name_node).lstrip("$") if name is None else name
        if not name:
            name = (
                "lambda_" + str(node.start_point.row + 1) + "_" + str(node.start_point.column + 1)
            )
        kind = kind or (
            "type"
            if node.type in _TYPE_NODES
            else "method"
            if scope["kind"] == "type"
            else "function"
        )
        preferred = make_id(self.prefix, *owners, name)
        identity = (
            preferred
            if preferred not in self.used_ids
            else preferred
            + "_"
            + occurrence_id(self.relative, node.start_byte, node.end_byte, kind)[-10:]
        )
        self.used_ids.add(identity)
        anchor = self.anchor(node)
        body = (expression or node).child_by_field_name("body")
        signature_end = body.start_byte if body is not None else node.end_byte
        signature = self.raw[node.start_byte : signature_end].decode("utf-8").strip()[:1000]
        qualified = ".".join((*owners, name))
        inner = self.new_scope(identity, scope["id"], kind, identity)
        record = {
            "id": identity,
            "name": name,
            "kind": kind,
            "scope_id": scope["id"],
            "body_scope_id": inner["id"],
            "qualified_name": qualified,
            "signature": signature,
            "exported": bool(node.parent and node.parent.type == "export_statement"),
            "line": anchor["line"],
            "column": anchor["column"],
            **(metadata or {}),
        }
        self.declarations.append(record)
        self.bind(scope, name, "declaration", target=identity)
        self.nodes.append(
            {
                **record,
                "label": name,
                "file_type": "code",
                "source_file": self.relative,
                "source_location": f"L{anchor['line']}:{anchor['column']}",
                "source_end_line": anchor["endLine"],
                "source_ranges": [anchor],
                "occurrenceId": occurrence_id(
                    self.relative, node.start_byte, node.end_byte, "declaration", name
                ),
                "language": self.language,
                "owner": ".".join(owners),
            }
        )
        self.edges.append(
            {
                "source": scope["owner"],
                "target": identity,
                "relation": "contains",
                "resolution": "exact",
                "binding_kind": "declared-exact",
                "confidence": "EXTRACTED",
                "resolvedBy": "syntax",
                "source_file": self.relative,
                "source_location": f"L{anchor['line']}:{anchor['column']}",
                "call_site": anchor,
            }
        )
        if record["exported"]:
            export_name = (
                "default"
                if node.parent and re.search(r"\bexport\s+default\b", self.text(node.parent))
                else name
            )
            self.exports.append({"name": export_name, "local": name, "scope_id": scope["id"]})
        self.parameters(expression or node, inner)
        return inner, (*owners, name)

    # 导入行和局部绑定通过索引关联，保持原模块 specifier 不作文件系统解析。
    # 副作用导入可没有 local 名称，但仍需保留依赖观察。
    # 行号用于定位导入声明，不表示被导入目标的源码位置。
    def import_row(
        self,
        scope,
        local: str,
        specifier: str,
        imported: str = "*",
        kind: str = "named",
        line: int = 1,
    ) -> None:
        row = {
            "scope_id": scope["id"],
            "local": local,
            "specifier": specifier,
            "imported": imported,
            "kind": kind,
            "line": line,
        }
        self.imports.append(row)
        self.bind(scope, local, "import", import_index=len(self.imports) - 1)

    # 具名、默认、命名空间和再导出是不同绑定形式，必须分别记录。
    # 仅副作用导入没有本地符号，不能错误创建一个星号变量。
    # type 修饰在名称提取时剥离，模块 specifier 仍保持原值。
    # 再导出直接进入 exports，不应先伪造成本文件实现声明。
    # 命名、命名空间、默认与重导出分别记录，绑定阶段才能区分目标证明方式。
    def javascript_imports(self, text: str, scope, line: int) -> None:
        source = re.search(r"\bfrom\s*['\"]([^'\"]+)['\"]", text)
        if not source:
            side_effect = re.match(r"import\s*['\"]([^'\"]+)['\"]", text)
            if side_effect:
                self.import_row(scope, "", side_effect[1], "*", "side-effect", line)
            return
        specifier = source[1]
        if text.startswith("export"):
            if re.match(r"export\s*\*", text):
                self.exports.append({"name": "*", "specifier": specifier, "star": True})
            else:
                braces = re.search(r"\{(.*?)\}", text, re.DOTALL)
                if braces:
                    for item in braces[1].split(","):
                        names = re.split(r"\s+as\s+", item.strip().removeprefix("type "))
                        if names[0]:
                            self.exports.append(
                                {
                                    "name": names[-1],
                                    "imported": names[0],
                                    "specifier": specifier,
                                }
                            )
            return
        clause = text[text.find("import") + 6 : source.start()].strip().removeprefix("type ")
        braces = re.search(r"\{(.*?)\}", clause, re.DOTALL)
        if braces:
            for item in braces[1].split(","):
                names = re.split(r"\s+as\s+", item.strip().removeprefix("type "))
                if names[0]:
                    self.import_row(scope, names[-1], specifier, names[0], "named", line)
            clause = clause[: braces.start()].strip().rstrip(",")
        namespace = re.search(r"\*\s+as\s+(\w+)", clause)
        if namespace:
            self.import_row(scope, namespace[1], specifier, "*", "namespace", line)
            clause = clause[: namespace.start()].strip().rstrip(",")
        if clause:
            self.import_row(scope, clause, specifier, "default", "default", line)
        return

    # 语言分支只解释语法中的导入名字，不探测依赖是否安装。
    # Python 普通 import 的局部名是首段，带 as 时使用显式别名。
    # Go、Java、C/C++ 与 Rust 保留各自 specifier，供语言绑定器后续解释。
    # 没有匹配到受支持形状时保持无观察，避免猜测外部模块。
    # 副作用导入也需留下依赖记录，即使没有局部绑定名称。
    def imports_for(self, node, scope) -> None:
        text = self.text(node)
        line = node.start_point.row + 1
        if self.language == "python":
            self._python_imports(text, scope, line)
            return
        if self.language in {"javascript", "typescript", "tsx"}:
            self.javascript_imports(text, scope, line)
            return
        if self.language == "go":
            for go_import in re.finditer(r"(?:(\w+|\.)\s+)?[\"`]([^\"`]+)[\"`]", text):
                self.import_row(
                    scope,
                    go_import[1] or go_import[2].rsplit("/", 1)[-1],
                    go_import[2],
                    "*",
                    "namespace",
                    line,
                )
        elif self.language == "java":
            match = re.search(r"import\s+(?:static\s+)?([\w.*]+)", text)
            if match:
                specifier = match[1]
                self.import_row(
                    scope,
                    specifier.rsplit(".", 1)[-1],
                    specifier,
                    specifier.rsplit(".", 1)[-1],
                    "star" if specifier.endswith(".*") else "named",
                    line,
                )
        elif self.language in {"c", "cpp"}:
            match = re.search(r"#\s*include\s*[<\"]([^>\"]+)[>\"]", text)
            if match:
                self.import_row(scope, "", match[1], "*", "include", line)
        elif self.language == "rust":
            match = re.search(r"use\s+([\w:]+)(?:\s+as\s+(\w+))?", text)
            if match:
                self.import_row(
                    scope,
                    match[2] or match[1].split("::")[-1],
                    match[1],
                    match[1].split("::")[-1],
                    "named",
                    line,
                )

    # Python 导入保留别名、命名导入与命名空间的不同绑定方式。
    def _python_imports(self, text: str, scope: dict, line: int) -> None:
        match = re.match(r"from\s+(\S+)\s+import\s+(.+)", text, re.DOTALL)
        if match:
            specifier, names = match.groups()
            for item in names.strip().strip("()").split(","):
                pieces = re.split(r"\s+as\s+", item.strip())
                if pieces[0]:
                    self.import_row(
                        scope,
                        pieces[-1],
                        specifier,
                        pieces[0],
                        "star" if pieces[0] == "*" else "named",
                        line,
                    )
        elif text.startswith("import "):
            for item in text[7:].split(","):
                pieces = re.split(r"\s+as\s+", item.strip())
                self.import_row(
                    scope,
                    pieces[-1] if len(pieces) > 1 else pieces[0].split(".")[0],
                    pieces[0],
                    "*",
                    "namespace",
                    line,
                )

    # 泛型实参是调用表达式的补充证据，不属于成员访问链。
    # 保留实参坐标及截断标记，后续消费者知道文本是否完整。
    # 递归深度上限保护病态嵌套，无法结构化的表达式交由动态回退处理。
    # Rust turbofish 表示泛型实参，不能误当成成员访问链的一段。
    def rust_callee(self, node, type_arguments: list[dict], depth: int = 0) -> str | None:
        if node is None or depth > 128:
            return None
        if node.type in {
            "identifier",
            "field_identifier",
            "type_identifier",
            "primitive_type",
            "self",
            "super",
            "crate",
        }:
            return self.text(node)
        if node.type in {"generic_function", "generic_type"}:
            arguments = node.child_by_field_name("type_arguments")
            if arguments is not None:
                argument_text = self.text(arguments)
                type_arguments.append(
                    {
                        "text": argument_text[:2048],
                        "textTruncated": len(argument_text) > 2048,
                        "location": self.anchor(arguments),
                    }
                )
            callee = node.child_by_field_name(
                "function" if node.type == "generic_function" else "type"
            )
            return self.rust_callee(callee, type_arguments, depth + 1)
        if node.type in {"scoped_identifier", "scoped_type_identifier", "field_expression"}:
            member = node.child_by_field_name(
                "field" if node.type == "field_expression" else "name"
            )
            receiver = node.child_by_field_name(
                "value" if node.type == "field_expression" else "path"
            )
            tail = self.rust_callee(member, type_arguments, depth + 1)
            prefix = self.rust_callee(receiver, type_arguments, depth + 1)
            return prefix + "." + tail if prefix and tail else None
        return None

    # 记录调用点 occurrence，使同名函数的不同调用不会被过早去重。
    # 统一成员分隔符仅用于名称匹配，不修改原始源码见证。
    # 复杂表达式标为 dynamic，不能从残余字符串推断一个精确目标。
    # Rust 泛型保留原表达式与类型实参，便于解释解析降级。
    def reference(
        self,
        node,
        scope,
        *,
        context="call",
        name_node=None,
        name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        explicit_name = name is not None
        expression = (
            name_node or node.child_by_field_name("function") or node.child_by_field_name("name")
        )
        if expression is None:
            expression = next(iter(node.named_children), node if explicit_name else None)
        if expression is None:
            return
        original_expression = self.text(expression).strip()
        type_arguments: list[dict] = []
        if name is None:
            name = (
                self.rust_callee(expression, type_arguments) or "<dynamic>"
                if self.language == "rust"
                else original_expression
            )
        receiver_node = node.child_by_field_name("object")
        if receiver_node is not None and not explicit_name:
            name = self.text(receiver_node) + "." + name
        name = name.replace("?.", ".").replace("->", ".").replace("::", ".").lstrip("$")
        simple = name if explicit_name or self.language == "rust" else name.split("<", 1)[0]
        if not simple or "(" in simple or "\n" in simple:
            simple = "<dynamic>"
        parts = simple.split(".")
        anchor = self.anchor(node)
        self.references.append(
            {
                "occurrenceId": occurrence_id(
                    self.relative,
                    node.start_byte,
                    node.end_byte,
                    context,
                    original_expression if self.language == "rust" else name,
                ),
                "caller_nid": scope["owner"],
                "caller": scope["owner"],
                "scope_id": scope["id"],
                "name": simple,
                "nameTail": parts[-1],
                "receiver": ".".join(parts[:-1]),
                "member": len(parts) > 1,
                "context": context,
                "source_file": self.relative,
                "callerFile": self.relative,
                "line": anchor["line"],
                "column": anchor["column"],
                "endLine": anchor["endLine"],
                "endColumn": anchor["endColumn"],
                "call_site": anchor,
                **(metadata or {}),
                **(
                    {
                        "sourceExpression": original_expression[:2048],
                        "sourceExpressionTruncated": len(original_expression) > 2048,
                        "expressionLocation": self.anchor(expression),
                        "typeArguments": sorted(
                            type_arguments, key=lambda item: item["location"]["startByte"]
                        ),
                    }
                    if self.language == "rust" and (type_arguments or simple == "<dynamic>")
                    else {}
                ),
            }
        )

    # 简单标识链才可作为别名；普通右值无需保存，避免泄漏字面量。
    # 命名 lambda 由 declare 处理，不能再生成一个竞争性的普通局部绑定。
    # CommonJS require 作为导入观察，仍由后续阶段确定其模块目标。
    # 普通赋值只记录可识别别名，不能把任意表达式冒充确定引用。
    def assignment(self, node, scope) -> None:
        rust_pattern = self.language == "rust" and node.type == "let_declaration"
        left = (
            node.child_by_field_name("pattern")
            if rust_pattern
            else node.child_by_field_name("name") or node.child_by_field_name("left")
        )
        value = node.child_by_field_name("value") or node.child_by_field_name("right")
        if left is None:
            return
        if not rust_pattern and value is not None and value.type in _LAMBDAS:
            return
        identifiers = [item for item in _children(left) if item.type in _IDENTIFIERS]
        names = (
            self.pattern_names(left)
            if rust_pattern
            else [self.text(item).lstrip("$") for item in identifiers]
        )
        self._bind_assignment_names(names, left, value, rust_pattern, scope)
        if value is not None:
            match = re.match(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", self.text(value))
            if match:
                for item in identifiers:
                    self.import_row(
                        scope, self.text(item), match[1], "*", "namespace", node.start_point.row + 1
                    )

    # 仅为可解析别名保留右侧目标，普通局部变量不保存任意源码字面量。
    def _bind_assignment_names(
        self, names: list[str], left: Any, value: Any, rust_pattern: bool, scope: dict
    ) -> None:
        for name in names:
            target = self.text(value).strip() if value is not None else ""
            alias = bool(
                (not rust_pattern or left.type == "identifier")
                and target
                and all(part.isidentifier() for part in target.split("."))
            )
            extra = {"target_name": target} if alias else {}
            self.bind(scope, name, "alias" if alias else "local", **extra)
            if alias:
                self.aliases.append({"scope_id": scope["id"], "local": name, "target": target})

    # 解构只沿绑定位置递归，属性键和默认值属于表达式而非新局部变量。
    # 未知模式返回空列表，避免在不理解语法时扩大可见作用域。
    # 只收集绑定位置；属性键和默认值表达式中的名称不是局部声明。
    def pattern_names(self, node) -> list[str]:
        if node is None:
            return []
        if node.type in {
            "identifier",
            "shorthand_field_identifier",
            "shorthand_property_identifier_pattern",
        }:
            return [self.text(node)]
        if node.type == "pair_pattern":
            return self.pattern_names(node.child_by_field_name("value"))
        if node.type == "field_pattern":
            return self.pattern_names(
                node.child_by_field_name("pattern") or node.child_by_field_name("name")
            )
        if node.type in {"assignment_pattern", "object_assignment_pattern"}:
            return self.pattern_names(node.child_by_field_name("left"))
        if node.type in {
            "array_pattern",
            "object_pattern",
            "rest_pattern",
            "tuple_pattern",
            "tuple_struct_pattern",
            "struct_pattern",
            "slice_pattern",
            "reference_pattern",
            "mut_pattern",
            "captured_pattern",
        }:
            return [name for child in node.named_children for name in self.pattern_names(child)]
        return []

    # 本地导出保留声明所在作用域，重命名只改变对外名称。
    # 带 source 的再导出由导入逻辑处理，防止同一语句产生两套关系。
    # 本地导出别名绑定当前作用域，跨模块重导出仍由导入规则处理。
    def export_statement(self, node, scope) -> None:
        self.imports_for(node, scope)
        if not node.child_by_field_name("source") and not node.child_by_field_name("declaration"):
            braces = re.search(r"\{([^}]+)\}", self.text(node))
            if braces:
                for item in braces[1].split(","):
                    parts = re.split(r"\s+as\s+", item.strip())
                    if parts[0]:
                        self.exports.append(
                            {"name": parts[-1], "local": parts[0], "scope_id": scope["id"]}
                        )

    # 遇到拥有独立作用域的声明后立即在内部递归，不再走通用遍历。
    # catch 参数拥有块作用域，不能污染相邻代码的名称解析。
    # 调用参数中的裸标识额外记录 callback 候选，仍不宣称它实际被调用。
    # JS/Rust 非函数体块建立词法边界，避免局部变量跨兄弟块泄漏。
    # 声明分支已经递归消费子树，通用遍历不能再生成重复观察。
    def walk(self, node, scope, owners: tuple[str, ...] = ()) -> None:
        kind = node.type
        if kind in {"package_clause", "package_declaration"}:
            self.package = self.text(node).removeprefix("package").strip().rstrip(";")
            return
        if kind in _IMPORT_NODES:
            self.imports_for(node, scope)
            return
        if kind == "export_statement":
            self.export_statement(node, scope)
        if self.language in {"javascript", "typescript", "tsx"} and kind == "catch_clause":
            catch_scope = self.new_scope(
                occurrence_id(self.relative, node.start_byte, node.end_byte, "catch"),
                scope["id"],
                "block",
                scope["owner"],
            )
            for name in self.pattern_names(node.child_by_field_name("parameter")):
                self.bind(catch_scope, name, "parameter")
            for child in node.named_children:
                self.walk(child, catch_scope, owners)
            return
        if self._walk_declaration(node, scope, owners):
            return
        if kind in {
            "variable_declarator",
            "assignment",
            "assignment_expression",
            "short_var_declaration",
            "var_spec",
            "let_declaration",
        }:
            self.assignment(node, scope)
        if kind in _CALL_NODES:
            self.reference(node, scope)
            arguments = node.child_by_field_name("arguments")
            if arguments is not None:
                for argument in arguments.named_children:
                    if argument.type in _IDENTIFIERS:
                        self.reference(argument, scope, context="callback", name_node=argument)
        scope = self._lexical_block_scope(node, scope)
        for child in node.named_children:
            self.walk(child, scope, owners)

    # 声明拥有自己的作用域，完成子树遍历后通知入口停止重复访问。
    def _walk_declaration(self, node: Any, scope: dict, owners: tuple[str, ...]) -> bool:
        kind = node.type
        value = node.child_by_field_name("value")
        named_expression = (
            kind == "variable_declarator" and value is not None and value.type in _LAMBDAS
        )
        if kind in _TYPE_NODES | _FUNCTION_NODES or named_expression:
            inner, nested_owners = self.declare(
                node, scope, owners, expression=value if named_expression else None
            )
            syntax = value if named_expression else node
            for child in syntax.named_children:
                if child is not self.name_node(syntax):
                    self.walk(child, inner, nested_owners)
            return True
        if kind in _LAMBDAS:
            inner, nested_owners = self.declare(node, scope, owners)
            for child in node.named_children:
                self.walk(child, inner, nested_owners)
            return True
        return False

    # 块绑定不能泄露到兄弟块，函数体继续复用声明创建的作用域。
    def _lexical_block_scope(self, node: Any, scope: dict) -> dict:
        kind = node.type
        if (
            (
                self.language in {"javascript", "typescript", "tsx"}
                and kind == "statement_block"
                or self.language == "rust"
                and kind == "block"
            )
            and node.parent
            and node.parent.type not in _FUNCTION_NODES | _LAMBDAS
        ):
            scope = self.new_scope(
                occurrence_id(self.relative, node.start_byte, node.end_byte, "block"),
                scope["id"],
                "block",
                scope["owner"],
            )
        return scope

    # 最终结果只包含可序列化数据，tree-sitter 节点随访问器生命周期释放。
    # Python 顶层导入也可作为模块导出，星号导入则不能伪造具体名称。
    # sourceDigest 对原字节计算，组件遮罩不改变证据绑定的文件身份。
    # 语法 partial 与结构性完整观察明确区分，后层不能把降级升级为 exact。
    def result(self, partial: bool) -> FileFacts:
        if self.language in {"python", "go", "java", "c", "cpp", "rust", "csharp", "kotlin", "php"}:
            for declaration in self.declarations:
                if declaration["scope_id"] == self.root_scope["id"]:
                    self.exports.append(
                        {
                            "name": declaration["name"],
                            "local": declaration["name"],
                            "scope_id": self.root_scope["id"],
                        }
                    )
        if self.language == "python":
            for imported in self.imports:
                if imported["scope_id"] == self.root_scope["id"] and imported["local"] != "*":
                    self.exports.append(
                        {
                            "name": imported["local"],
                            "local": imported["local"],
                            "scope_id": self.root_scope["id"],
                        }
                    )
        return {
            "path": self.relative,
            "language": self.language,
            "package": self.package,
            "parserContract": PARSER_CONTRACT_VERSION,
            "sourceDigest": hashlib.sha256(self.raw).hexdigest(),
            "nodes": self.nodes,
            "edges": self.edges,
            "scopes": self.scopes,
            "declarations": self.declarations,
            "imports": self.imports,
            "exports": self.exports,
            "aliases": self.aliases,
            "references": self.references,
            "raw_calls": self.references,  # 保留旧消费者字段，与 references 共用同一观察集。
            "diagnostics": [
                {
                    "code": "machine.facts.parser-syntax-partial",
                    "path": self.relative,
                    "message": "The grammar reported missing or invalid syntax.",
                }
            ]
            if partial
            else [],
            "analysisCompleteness": "partial" if partial else "structural",
            "input_tokens": 0,
            "output_tokens": 0,
        }
