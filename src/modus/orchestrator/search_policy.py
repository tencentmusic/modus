"""Filesystem and data-protection policy for evidence search."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

from ..paths import MANAGED_ROOT_FILES, PROJECT_OUTPUT_DIRS

EXCLUDED_SOURCE_DIRECTORIES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".cache",
        "third_party",
        *PROJECT_OUTPUT_DIRS,
    }
)

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)([A-Za-z0-9_]*(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?key|"
    r"private[_-]?key|token|password|passwd|pwd|credential)[A-Za-z0-9_]*)"
    r"(\s*[=:]\s*)"
    r"""(['"]?)([A-Za-z0-9\-_/+=.]{8,})(['"]?)"""
)
_AWS_ACCESS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.=]{10,}")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_PEM_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_REDACTED = "***REDACTED***"


def source_suffixes() -> frozenset[str]:
    """Return the source suffixes supported by ordinary text retrieval."""
    return frozenset(
        {
            ".c",
            ".cc",
            ".cpp",
            ".cs",
            ".cxx",
            ".go",
            ".h",
            ".hh",
            ".hpp",
            ".hxx",
            ".m",
            ".mm",
            ".java",
            ".js",
            ".jsx",
            ".kt",
            ".kts",
            ".php",
            ".py",
            ".pyi",
            ".rs",
            ".scala",
            ".sql",
            ".swift",
            ".ts",
            ".tsx",
            ".vue",
            ".xml",
            ".yaml",
            ".yml",
        }
    )


# 排除工具自身生成与受管内容，防止检索结果递归引用自身产物。
# 根文件与目录前缀分别判断，不能用模糊名称匹配扩大排除范围。
def _is_modus_owned(relative: str) -> bool:
    parts = Path(relative).parts
    return (
        not parts
        or parts[0] in {"modus", ".modus", *PROJECT_OUTPUT_DIRS}
        or relative in MANAGED_ROOT_FILES
    )


# 脱敏发生在文本离开进程前，原始源码不在这里改写。
# 保留赋值名称、分隔符与引号，使摘录仍可解释配置意图。
def redact_secrets(text: str) -> str:
    """Mask common credential shapes before a source line leaves the process."""
    text = _AWS_ACCESS_KEY_RE.sub(_REDACTED, text)
    text = _BEARER_TOKEN_RE.sub(lambda _match: f"Bearer {_REDACTED}", text)
    text = _JWT_RE.sub(_REDACTED, text)
    text = _PEM_PRIVATE_KEY_RE.sub(_REDACTED, text)
    return _SECRET_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}{match.group(3)}{_REDACTED}{match.group(5)}"
        ),
        text,
    )


# 目录与文件都拒绝符号链接，遍历不跨出项目选择的树。
# 稳定排序让相同预算下选中的文件可重复。
def iter_source_files(root: Path) -> Iterator[Path]:
    """Yield safe project source files in deterministic path order."""
    for parent, directories, names in os.walk(root, followlinks=False):
        directory = Path(parent)
        directories[:] = sorted(
            name
            for name in directories
            if name not in EXCLUDED_SOURCE_DIRECTORIES
            and not (directory / name).is_symlink()
            and not _is_modus_owned((directory / name).relative_to(root).as_posix())
        )
        for name in sorted(names):
            path = directory / name
            if (
                path.suffix.lower() in source_suffixes()
                and path.is_file()
                and not path.is_symlink()
                and not _is_modus_owned(path.relative_to(root).as_posix())
            ):
                yield path


# 知识搜索只遍历调用者选定的目标，不自动扩大到项目全部文档。
def iter_markdown_files(targets: Sequence[Path]) -> Iterator[Path]:
    """Yield caller-selected Markdown knowledge without widening its scope."""
    for target in targets:
        if not target.exists():
            continue
        if target.is_file():
            yield target
            continue
        for path in target.rglob("*.md"):
            if path.is_file():
                yield path


# 前缀按完整路径段匹配，src/api 不包含 src/api-old。
# 此函数处理逻辑范围；实际文件系统边界由根目录解析负责。
def path_is_allowed(relative: str, prefixes: Sequence[str]) -> bool:
    """Return whether a normalized path is contained by one allowed prefix."""
    normalized = relative.replace("\\", "/").lstrip("./")
    for prefix in prefixes:
        candidate = str(prefix or "").replace("\\", "/").rstrip("/")
        if candidate and (
            candidate == "." or normalized == candidate or normalized.startswith(candidate + "/")
        ):
            return True
    return False


# 无过滤条件表示整个根目录，过滤无效则返回空集合。
# 不能把无效范围回退为全仓库，否则会悄然扩大检索权限。
def search_roots(root: Path, prefixes: Sequence[str]) -> list[Path]:
    """Resolve scoped search roots without ever widening an invalid scope."""
    if not prefixes:
        return [root]

    resolved_root = root.resolve()
    found: list[Path] = []
    seen: set[Path] = set()
    for prefix in prefixes:
        target = (resolved_root / str(prefix)).resolve()
        try:
            target.relative_to(resolved_root)
        except ValueError:
            continue
        if target.exists() and target not in seen:
            seen.add(target)
            found.append(target)
    return found
