"""当前源码锚点的声明匹配；检索、同步和核验共用，不读取初始化证据包。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .paths import ModusPaths
from .scope_models import SourceLocation
from .skillmd import split_frontmatter


def identifier_stem(symbol: str) -> str:
    """The searchable identifier inside an authored anchor symbol."""
    cleaned = symbol.replace("::", ".").strip().strip("()").lstrip(".")
    cleaned = cleaned.split("(", 1)[0]
    return cleaned.rsplit(".", 1)[-1].rsplit("#", 1)[-1].strip()


# 声明索引来自当前语法树，不把注释和引用当作定义。
def source_declarations(relative: str, lines: list[str]) -> list[dict[str, Any]] | None:
    """每个当前文件解析一次声明；注释、调用和字符串不进入锚点候选。"""
    content = "\n".join(lines)
    if Path(relative).suffix == ".py":
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None
        declarations: list[dict[str, Any]] = []

        def visit(node: ast.AST, owners: tuple[str, ...] = (), scope_kind: str = "module") -> None:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                owners = (*owners, node.name)
                scope_kind = "class" if isinstance(node, ast.ClassDef) else "function"
                declarations.append(
                    {
                        "name": node.name,
                        "qualified_name": ".".join(owners),
                        "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                        "line": node.lineno,
                        "endLine": node.end_lineno,
                        "signature": f"{node.name}({ast.unparse(node.args)})"
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        else node.name,
                    }
                )
            elif scope_kind in {"module", "class"} and isinstance(
                node, (ast.Assign, ast.AnnAssign)
            ):
                # 模块常量和类字段是合法锚点；不把属性写入、局部变量或调用当声明。
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if not isinstance(target, (ast.Name, ast.Tuple, ast.List)):
                        continue
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                            declarations.append(
                                {
                                    "name": name.id,
                                    "qualified_name": ".".join((*owners, name.id)),
                                    "kind": "field",
                                    "line": node.lineno,
                                    "endLine": node.end_lineno,
                                }
                            )
            for child in ast.iter_child_nodes(node):
                visit(child, owners, scope_kind)

        visit(tree)
        return declarations
    try:
        from .machine.corpus.source_snapshot import SourceSnapshot
        from .machine.facts.native_parser import parse_file

        facts = parse_file(SourceSnapshot(Path(relative).resolve(), content))
        if facts.get("diagnostics"):
            return None
        package = str(facts.get("package") or "")
        return [
            {
                **row,
                "qualified_name": ".".join(filter(None, (package, row.get("qualified_name", "")))),
            }
            for row in facts.get("declarations", [])
        ]
    except (ImportError, KeyError, ValueError):
        return None


def declaration_matches(
    declarations: list[dict[str, Any]], location: SourceLocation
) -> list[tuple[int, int]]:
    requested = location.symbol.split("(", 1)[0].replace("::", ".").replace("#", ".").strip(".")
    stem = identifier_stem(location.symbol)
    matches = []
    for row in declarations:
        if "(" in location.symbol and row.get("kind") not in {"function", "method", "constructor"}:
            continue
        qualified = str(row.get("qualified_name") or row.get("name") or "").replace("::", ".")
        qualified_names = (qualified, Path(location.path).stem + "." + qualified)
        if not any(name == requested or name.endswith("." + requested) for name in qualified_names):
            continue
        if "(" in location.symbol and not location.symbol.endswith("()"):
            expected = location.symbol.split("(", 1)[1].rsplit(")", 1)[0]
            types = row.get("parameterTypes")
            if types is None:
                signature = re.search(
                    rf"\b{re.escape(stem)}\s*\(([^)]*)\)", str(row.get("signature", ""))
                )
                if signature is None:
                    continue
                types = []
                for parameter in signature[1].split(","):
                    parameter = parameter.split("=", 1)[0].strip()
                    annotation = re.search(r"(?<!:):(?!:)", parameter)
                    type_name = (
                        parameter[annotation.end() :] if annotation else parameter.rsplit(" ", 1)[0]
                    )
                    types.append(type_name)
            if re.sub(r"\s+", "", ",".join(types)) != re.sub(r"\s+", "", expected):
                continue
        start, name_line = int(row["line"]), int(row.get("name_line") or row["line"])
        matches.append(
            (
                location.start_line if location.start_line in {start, name_line} else name_line,
                int(row.get("endLine") or row.get("source_end_line") or name_line),
            )
        )
    return sorted(set(matches))


# 锚点是可选元数据；结构非法时逐项记录，避免一个坏条目遮蔽全部结果。
def document_locations(
    paths: ModusPaths, path: Path, text: str
) -> tuple[list[SourceLocation], list[dict[str, Any]]]:
    """Read optional ``anchors.locations`` without assuming a document type."""

    document = paths.relative(path)
    frontmatter, _body = split_frontmatter(text)
    anchors = frontmatter.get("anchors")
    if anchors is None:
        return [], []
    if not isinstance(anchors, dict):
        return [], [
            {
                "document": document,
                "finding": "anchor_metadata_invalid",
                "detail": "anchors 必须为映射",
            }
        ]
    raw_locations = anchors.get("locations")
    if raw_locations is None:
        return [], []
    if not isinstance(raw_locations, list):
        return [], [
            {
                "document": document,
                "finding": "anchor_metadata_invalid",
                "detail": "anchors.locations 必须为列表",
            }
        ]

    locations: list[SourceLocation] = []
    findings: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_locations):
        try:
            locations.append(SourceLocation.from_dict(raw))
        except (TypeError, ValueError) as exc:
            findings.append(
                {
                    "document": document,
                    "finding": "anchor_metadata_invalid",
                    "detail": f"anchors.locations[{index}]: {exc}",
                }
            )
    return locations, findings


@dataclass(frozen=True, slots=True)
class AnchorCheck:
    """声明核验与当前范围；只有唯一漂移可供机械修复。"""

    finding: Literal[
        "current",
        "line_drift",
        "range_drift",
        "symbol_missing",
        "ambiguous",
        "anchor_verification_unavailable",
    ]
    start_line: int | None = None
    end_line: int | None = None
    candidate_lines: tuple[int, ...] = ()
    detail: str = ""


def check_location(
    location: SourceLocation, declarations: list[dict[str, Any]] | None
) -> AnchorCheck:
    if declarations is None:
        return AnchorCheck(
            "anchor_verification_unavailable",
            detail="当前语言或文件无法建立可靠声明索引，需人工核对",
        )
    matches = declaration_matches(declarations, location)
    if not matches:
        return AnchorCheck("symbol_missing", detail="文件中未找到符号声明")
    claimed = [(start, end) for start, end in matches if start == location.start_line]
    if not claimed and len(matches) > 1:
        return AnchorCheck(
            "ambiguous",
            candidate_lines=tuple(start for start, _ in matches),
            detail="匹配到多个声明，需核对归属或签名",
        )
    start, declaration_end = (claimed or matches)[0]
    end = (
        declaration_end
        if location.end_line is None
        else location.end_line + start - location.start_line
    )
    if end > declaration_end:
        return AnchorCheck(
            "range_drift", start, declaration_end, detail="结束行超出当前声明范围，需回读确认"
        )
    return AnchorCheck("current" if start == location.start_line else "line_drift", start, end)
