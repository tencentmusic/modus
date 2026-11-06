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

import hashlib
import re
from pathlib import Path
from typing import Any

from ..knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ..paths import ModusPaths
from ..skillmd import render, split_frontmatter
from ..source_anchors import check_location, document_locations, source_declarations

__all__ = ["run_verify_anchors"]

_REF_RE = re.compile(r"(?P<path>[\w][\w./-]*\.[A-Za-z0-9_]+)#L(?P<line>\d+)")

_MAX_SOURCE_BYTES = 8 * 1024 * 1024


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
        locations, metadata_findings = document_locations(paths, path, original_text)
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
                declaration_cache[location.path] = source_declarations(location.path, source_lines)
            check = check_location(location, declaration_cache[location.path])
            if check.finding == "current":
                continue
            finding: dict[str, Any] = {**base, "finding": check.finding}
            if check.detail:
                finding["detail"] = check.detail
            if check.start_line is not None and check.start_line != location.start_line:
                finding["actualLine"] = check.start_line
            if check.candidate_lines:
                finding["candidateLines"] = list(check.candidate_lines[:10])
            if check.finding == "line_drift" and check.start_line is not None:
                finding["fixable"] = True
                repairs[(location.path, location.symbol, location.start_line)] = check.start_line
            findings.append(finding)
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
