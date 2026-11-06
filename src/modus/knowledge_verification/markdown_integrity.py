"""Portable Markdown, link, source-reference, and leak checks.

Every rule in this module detects objective document damage. Editorial choices
such as headings, coverage, diagrams, or prose depth intentionally live outside
the verifier.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from ..commands.verify_anchors import _REF_RE
from ..knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ..markdown import body_start, markdown_anchors, markdown_headings
from ..markdown import markdown_slug as markdown_slug
from ..markdown import strip_fenced_code as _strip_fenced_code
from ..paths import ModusPaths
from .models import VerificationFinding, finding

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
LINK_RE = re.compile(r"!?\[([^\]]+)\]\(([^)]+)\)")
_ABSOLUTE_LOCAL_RE = re.compile(
    r"(?:file://)?(?:/Users/[^\s)`]+|/home/[^\s)`]+|/root/[^\s)`]+|"
    r"/private/(?:tmp|var)/[^\s)`]+|/tmp/[^\s)`]+|/workspace/[^\s)`]+|"
    r"[A-Za-z]:\\Users\\[^\s)`]+)"
)
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)\b(?:password|passwd|token|api[-_]?key|secret|client[-_]?secret|"
        r"access[-_]?token|refresh[-_]?token)\b\s*[:=]\s*['\"]"
        r"(?!<|\$\{|example|replace|redacted)[^'\"\s]{12,}['\"]"
    ),
)
_CANONICAL_SOURCE_REF_RE = re.compile(
    r"`(?P<path>[\w][\w./-]*\.[A-Za-z0-9_]+#L\d+)`\s*[（(]\s*"
    r"`(?P<symbol>[^`\n]{1,512})`\s*[）)]"
)
_NONCANONICAL_LINE_REF_RE = re.compile(
    r"`(?P<reference>[A-Za-z0-9_./-]+\."
    r"(?:py|java|kt|kts|go|php|c|cc|cpp|h|hpp|cs|rs|js|jsx|ts|tsx|vue|svelte|sql|"
    r"yaml|yml|json|toml|xml)(?::L?\d+|#\d+))`",
    re.IGNORECASE,
)


# 读取限制大小并绑定仓库根，拒绝链接和非常规文件。
# 不可读返回空状态，由各核验器决定是否已存在对应发现，避免重复报错。
def read_document(paths: ModusPaths, path: Path) -> str | None:
    try:
        return read_bound_regular_text(paths.root, path, max_bytes=MAX_DOCUMENT_BYTES)
    except (BoundKnowledgeReadError, OSError, ValueError):
        return None


# 复用检索层的正文边界与标题解析，使核验和阅读使用相同锚点来源。
def document_headings(text: str, level: int | None = None) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    headings = markdown_headings(lines, body_start(lines))
    if level is None:
        return headings
    return [item for item in headings if item[1] == level]


# 逐级检查路径，不能只检查最终文件而遗漏中间目录链接。
def _path_uses_symlink(root: Path, relative: str) -> bool:
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


# 返回未闭合围栏的起始行，定位真正需要修复的位置。
# 反引号信息串中的反引号不作为合法开头，避免误判示例文本。
def _unclosed_fence_line(text: str) -> int | None:
    fence: tuple[str, int, int] | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None:
            if match and not (match[1][0] == "`" and "`" in match[2]):
                fence = (match[1][0], len(match[1]), line_number)
            continue
        if match and match[1][0] == fence[0] and len(match[1]) >= fence[1] and not match[2].strip():
            fence = None
    return fence[2] if fence is not None else None


# 基础核验只判断客观损坏，不要求特定章节或图表数量。
# 文件不可读与围栏不闭合是不同发现，便于采取针对性修复。
def verify_markdown_basics(
    paths: ModusPaths, documents: tuple[Path, ...]
) -> list[VerificationFinding]:
    """Report generic Markdown damage without grading diagram semantics."""

    findings: list[VerificationFinding] = []
    for path in documents:
        text = read_document(paths, path)
        if text is None:
            findings.append(
                finding(
                    paths.relative(path),
                    "document-unreadable",
                    "Markdown 文档不是可读的 UTF-8 常规文件",
                )
            )
            continue
        line = _unclosed_fence_line(text)
        if line is not None:
            findings.append(
                finding(
                    paths.relative(path),
                    "markdown-fence-unclosed",
                    "Markdown 代码围栏未闭合",
                    line=line,
                )
            )
    return findings


# 标题、显式 HTML 锚点与条目标记共同构成可链接目标。
# 三类锚点统一大小写后匹配，不从普通正文推测锚点。
def _anchors_for(text: str) -> set[str]:
    return {anchor for anchors in markdown_anchors(text).values() for anchor in anchors}


# 只核验仓库内的相对链接，不发起网络请求检查外部 URL。
# 路径先解码并解析，再检查仓库边界，避免编码路径逃逸。
# Markdown 目标才核验片段，其他文件的片段语义留给其格式处理。
# 目标正文按路径缓存，避免同一轮重复读取热门导航页。
def verify_links(paths: ModusPaths, documents: tuple[Path, ...]) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    cache: dict[Path, str | None] = {}
    for path in documents:
        text = read_document(paths, path)
        if text is None:
            continue
        document = paths.relative(path)
        for label, raw in LINK_RE.findall(_strip_fenced_code(text)):
            destination = raw.strip().strip("<>")
            if not destination or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", destination):
                continue
            target_text, separator, fragment = destination.partition("#")
            target = path if not target_text else (path.parent / unquote(target_text)).resolve()
            try:
                target.relative_to(paths.root)
            except ValueError:
                findings.append(
                    finding(
                        document,
                        "link-outside-repository",
                        f"link {label!r} 解析后指向仓库外部",
                        link=raw,
                    )
                )
                continue
            if not target.is_file() or target.is_symlink():
                findings.append(
                    finding(
                        document,
                        "link-target-missing",
                        f"link {label!r} 未指向常规文件",
                        link=raw,
                    )
                )
                continue
            if separator and target.suffix.casefold() == ".md":
                if target not in cache:
                    cache[target] = read_document(paths, target)
                target_body = cache[target]
                if target_body is not None and markdown_slug(unquote(fragment)) not in _anchors_for(
                    target_body
                ):
                    findings.append(
                        finding(
                            document,
                            "link-anchor-missing",
                            f"link {label!r} 指向不存在的 Markdown 锚点",
                            link=raw,
                        )
                    )
    return findings


# 可移植性、敏感字面量和源码引用契约在此统一检查。
# 发现敏感值时只返回位置，不把原始凭据复制进诊断结果。
# 每篇文档只报首个敏感模式，避免同一值被多个规则重复回显。
# 源码引用需有规范路径、行号和符号，行号本身不足以表达身份。
# 解析后的绝对路径仍需位于仓库内，随后再检查原路径链接链。
# 非规范引用单独报告，便于区分格式迁移与目标不存在。
# 此层不会移动行号或改写正文，修复属于显式锚点更新流程。
# 绝对本机路径样本限长，防止单条诊断占满报告。
def verify_portability_and_sources(
    paths: ModusPaths, documents: tuple[Path, ...]
) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    for path in documents:
        text = read_document(paths, path)
        if text is None:
            continue
        document = paths.relative(path)
        local = _ABSOLUTE_LOCAL_RE.search(text)
        if local:
            findings.append(
                finding(
                    document,
                    "absolute-local-path",
                    "知识包含特定机器的绝对路径",
                    sample=local.group(0)[:160],
                )
            )
        for pattern in _SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append(
                    finding(
                        document,
                        "sensitive-value",
                        "知识包含高置信度敏感字面量",
                        line=text.count("\n", 0, match.start()) + 1,
                    )
                )
                break
        for line_number, line in enumerate(text.splitlines(), start=1):
            canonical_starts = {
                match.start("path") for match in _CANONICAL_SOURCE_REF_RE.finditer(line)
            }
            for match in _NONCANONICAL_LINE_REF_RE.finditer(line):
                findings.append(
                    finding(
                        document,
                        "source-ref-noncanonical",
                        "源码引用必须使用 repository/path.ext#L<行号>，并附带完整限定"
                        "符号或非代码章节定位信息",
                        line=line_number,
                        reference=match.group("reference"),
                    )
                )
            if not _REF_RE.search(line):
                continue
            for match in _REF_RE.finditer(line):
                relative_source = match.group("path")
                source = (paths.root / relative_source).resolve(strict=False)
                try:
                    source.relative_to(paths.root)
                except ValueError:
                    findings.append(
                        finding(
                            document,
                            "source-ref-outside-repository",
                            "源码引用必须位于仓库内",
                            line=line_number,
                            reference=match.group(0),
                        )
                    )
                    continue
                if _path_uses_symlink(paths.root, relative_source):
                    findings.append(
                        finding(
                            document,
                            "source-ref-unsafe",
                            "源码引用不能经过符号链接",
                            line=line_number,
                            reference=match.group(0),
                        )
                    )
                    continue
                if match.start() not in canonical_starts:
                    findings.append(
                        finding(
                            document,
                            "source-ref-symbol-missing",
                            "源码引用需要仓库路径、#L 行号与完整限定符号或非代码章节定位信息",
                            line=line_number,
                            reference=match.group(0),
                        )
                    )
    return findings


__all__ = [
    "document_headings",
    "markdown_slug",
    "read_document",
    "verify_links",
    "verify_markdown_basics",
    "verify_portability_and_sources",
]
