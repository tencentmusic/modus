"""Deterministic source-anchor verification for authored knowledge.

Checks compare authored anchors with current source. Findings distinguish
mechanically repairable drift from changes that need author review:

- ``line_drift``     the anchored symbol still exists in the file but on a
                     different line, and the match is unique -- safe to repair
                     mechanically (``--fix`` rewrites only the line number).
- ``symbol_missing`` the anchored symbol no longer occurs in the file (or the
                     file is gone) -- an editorial decision, never auto-fixed.
- ``ambiguous``      several lines match; a mechanical fix could silently pick
                     the wrong one, so it is reported and left alone.
- ``anchor_metadata_invalid`` malformed structured source anchors on any
                              knowledge document.
- ``ref_*``                  legacy inline ``path#L`` references in knowledge
                              bodies whose file is missing or whose line is out
                              of range.

Repair honesty: a fix updates the *anchor's claimed line* to where the symbol
verifiably is now.  The claimed line is never overwritten just to silence a
finding -- ``symbol_missing`` and ``ambiguous`` stay visible until an author
revises the document through a knowledge-maintenance workflow.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any

from ..knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ..paths import ModusPaths
from ..scope_models import SourceLocation
from ..skillmd import render, split_frontmatter

__all__ = ["run_verify_anchors"]

_REF_RE = re.compile(r"(?P<path>[\w][\w./-]*\.[A-Za-z0-9_]+)#L(?P<line>\d+)")

_MAX_SOURCE_BYTES = 8 * 1024 * 1024


def _identifier_stem(symbol: str) -> str:
    """The searchable identifier inside an authored anchor symbol."""
    cleaned = symbol.replace("::", ".").strip().strip("()").lstrip(".")
    cleaned = cleaned.split("(", 1)[0]
    return cleaned.rsplit(".", 1)[-1].rsplit("#", 1)[-1].strip()


# 声明索引来自当前语法树，不把注释和引用当作定义。
def _source_declarations(relative: str, lines: list[str]) -> list[dict[str, Any]] | None:
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
        from ..machine.corpus.source_snapshot import SourceSnapshot
        from ..machine.facts.native_parser import parse_file

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


def _declaration_matches(
    declarations: list[dict[str, Any]], location: SourceLocation
) -> list[tuple[int, int]]:
    requested = location.symbol.split("(", 1)[0].replace("::", ".").replace("#", ".").strip(".")
    stem = _identifier_stem(location.symbol)
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


# 读取当前工作树并限制文件大小，验证结果不依赖历史分析缓存。
def _read_source(paths: ModusPaths, relative: str) -> list[str] | None:
    try:
        return read_bound_regular_text(
            paths.root, paths.root / relative, max_bytes=_MAX_SOURCE_BYTES
        ).splitlines()
    except (BoundKnowledgeReadError, OSError, ValueError):
        return None


def _in_domain(paths: ModusPaths, path: Path, domain: str | None) -> bool:
    """判断路径是否属于指定领域。"""

    if domain is None:
        return True
    try:
        path.relative_to(paths.domain(domain))
    except ValueError:
        return False
    return True


# 锚点是可选元数据；结构非法时逐项记录，避免一个坏条目遮蔽全部结果。
def _document_locations(
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


def _verify_structured_anchors(
    paths: ModusPaths,
    *,
    fix: bool,
    source_cache: dict[str, list[str] | None],
    domain: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    from ..retrieval.stages.sections import markdown_files

    findings: list[dict[str, Any]] = []
    fixed_documents: list[str] = []
    declaration_cache: dict[str, list[dict[str, Any]] | None] = {}
    for path in markdown_files(paths, "project"):
        if not _in_domain(paths, path, domain):
            continue
        document = paths.relative(path)
        try:
            original_text = read_bound_regular_text(paths.root, path, max_bytes=2 * 1024 * 1024)
        except (BoundKnowledgeReadError, OSError, ValueError):
            continue
        locations, metadata_findings = _document_locations(paths, path, original_text)
        findings.extend(metadata_findings)
        repairs: dict[tuple[str, str, int], int] = {}
        for location in locations:
            if location.path not in source_cache:
                source_cache[location.path] = _read_source(paths, location.path)
            source_lines = source_cache[location.path]
            base = {
                "document": document,
                "path": location.path,
                "symbol": location.symbol,
                "claimedLine": location.start_line,
            }
            if source_lines is None:
                findings.append({**base, "finding": "symbol_missing", "detail": "文件缺失"})
                continue
            if location.path not in declaration_cache:
                declaration_cache[location.path] = _source_declarations(location.path, source_lines)
            declarations = declaration_cache[location.path]
            if declarations is None:
                findings.append(
                    {
                        **base,
                        "finding": "anchor_verification_unavailable",
                        "detail": "当前语言或文件无法建立可靠声明索引，需人工核对",
                    }
                )
                continue
            declarations_at = _declaration_matches(declarations, location)
            matches = sorted({start for start, _ in declarations_at})
            if not matches:
                findings.append({**base, "finding": "symbol_missing", "detail": "文件中未找到符号"})
                continue
            if location.start_line in matches:
                if location.end_line is not None and all(
                    location.end_line > end
                    for start, end in declarations_at
                    if start == location.start_line
                ):
                    findings.append(
                        {
                            **base,
                            "finding": "range_drift",
                            "detail": "结束行超出当前声明范围，需回读确认",
                        }
                    )
                continue
            if len(matches) == 1:
                end = next(end for start, end in declarations_at if start == matches[0])
                if (
                    location.end_line is not None
                    and location.end_line + matches[0] - location.start_line > end
                ):
                    findings.append(
                        {
                            **base,
                            "finding": "range_drift",
                            "actualLine": matches[0],
                            "detail": "声明位置与范围均已变化，需回读确认",
                        }
                    )
                    continue
                findings.append(
                    {
                        **base,
                        "finding": "line_drift",
                        "actualLine": matches[0],
                        "fixable": True,
                    }
                )
                repairs[(location.path, location.symbol, location.start_line)] = matches[0]
            else:
                findings.append(
                    {
                        **base,
                        "finding": "ambiguous",
                        "candidateLines": matches[:10],
                        "detail": "匹配到多个行，无法自动修复",
                    }
                )
        if fix and repairs:
            if _repair_document(paths, document, repairs, original_text):
                fixed_documents.append(document)
                for finding in findings:
                    key = (
                        finding.get("path"),
                        finding.get("symbol"),
                        finding.get("claimedLine"),
                    )
                    if finding.get("document") == document and key in repairs:
                        finding["fixed"] = True
            else:
                findings.append(
                    {
                        "document": document,
                        "finding": "anchor_write_conflict",
                        "detail": "未写入修复；保留原读时版本，核对并发变化或写入失败",
                    }
                )
    return findings, fixed_documents


# 机械修复仅更新可唯一定位的行号，写入依赖原始内容摘要检测并发编辑。
def _repair_document(
    paths: ModusPaths, document: str, repairs: dict[tuple[str, str, int], int], text: str
) -> bool:
    """Rewrite only the drifted startLine values, under the shared CAS writer."""
    from ..knowledge_write_session import write_document

    frontmatter, body = split_frontmatter(text)
    anchors = frontmatter.get("anchors")
    if not isinstance(anchors, dict):
        return False
    locations = anchors.get("locations")
    if not isinstance(locations, list):
        return False
    changed = False
    for item in locations:
        if not isinstance(item, dict):
            continue
        key = (item.get("path"), item.get("symbol"), item.get("startLine"))
        if key in repairs:
            offset = repairs[key] - int(item.get("startLine") or 0)
            item["startLine"] = repairs[key]
            if isinstance(item.get("endLine"), int):
                item["endLine"] = max(item["startLine"], item["endLine"] + offset)
            changed = True
    if not changed:
        return False
    try:
        write_document(
            paths,
            document,
            render(frontmatter, body),
            expected_hash=hashlib.sha256(text.encode()).hexdigest(),
        )
    except (OSError, ValueError, RuntimeError):
        return False
    return True


def _verify_body_references(
    paths: ModusPaths,
    source_cache: dict[str, list[str] | None],
    *,
    domain: str | None,
) -> list[dict[str, Any]]:
    from ..retrieval.stages.sections import markdown_files

    findings: list[dict[str, Any]] = []
    for path in markdown_files(paths, "project"):
        if not _in_domain(paths, path, domain):
            continue
        try:
            text = read_bound_regular_text(paths.root, path, max_bytes=2 * 1024 * 1024)
        except (BoundKnowledgeReadError, OSError, ValueError):
            continue
        document = paths.relative(path)
        _frontmatter, body = split_frontmatter(text)
        for match in _REF_RE.finditer(body):
            relative = match.group("path")
            line = int(match.group("line"))
            if not (paths.root / relative).exists():
                findings.append(
                    {
                        "document": document,
                        "finding": "ref_file_missing",
                        "reference": match.group(0),
                    }
                )
                continue
            if relative not in source_cache:
                source_cache[relative] = _read_source(paths, relative)
            source_lines = source_cache[relative]
            if source_lines is not None and line > len(source_lines):
                findings.append(
                    {
                        "document": document,
                        "finding": "ref_line_out_of_range",
                        "reference": match.group(0),
                        "fileLines": len(source_lines),
                    }
                )
    return findings


def run_verify_anchors(
    root: str = ".", *, fix: bool = False, domain: str | None = None
) -> dict[str, Any]:
    """Verify structured anchors and legacy body references; optionally repair drift."""
    paths = ModusPaths.for_root(root)
    source_cache: dict[str, list[str] | None] = {}
    anchor_findings, fixed_documents = _verify_structured_anchors(
        paths, fix=fix, source_cache=source_cache, domain=domain
    )
    reference_findings = _verify_body_references(paths, source_cache, domain=domain)
    findings = [*anchor_findings, *reference_findings]
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["finding"]] = counts.get(finding["finding"], 0) + 1
    return {
        "status": "clean" if not findings else "findings",
        "findings": findings,
        "counts": counts,
        "fixedDocuments": fixed_documents,
        "checkedDocuments": len({finding["document"] for finding in findings})
        if findings
        else None,
    }
