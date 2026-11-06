"""Read-only source inventory for one initialization analysis."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

from modus.knowledge_reader import BoundKnowledgeReadError, read_bound_regular_bytes
from modus.machine.corpus.source_filters import (
    is_ignored,
    is_noise_directory,
    is_sensitive,
    parse_gitignore_line,
)
from modus.paths import MANAGED_ROOT_FILES, PROJECT_OUTPUT_DIRS

MAX_SOURCE_BYTES = 2 * 1024 * 1024
_ROOT_OUTPUTS = {"modus", ".modus", *PROJECT_OUTPUT_DIRS}
_SKIP_FILES = {
    "uv.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
    ".DS_Store",
}


# 忽略规则随目录继承并按顺序应用，不能把子目录规则提升为全局规则。
# 读取回调复用已校验的完整字节，避免选择后再次读出不同内容。
# 大小、编码和常规文件约束在纳入清单前检查，坏输入不会进入解析器。
def source_files(
    root: Path,
    *,
    extra_excludes: Sequence[str] = (),
    on_read: Callable[[Path, bytes], None] | None = None,
    on_disposition: Callable[[dict[str, str]], None] | None = None,
) -> list[Path]:
    """Walk *root* and return every analyzable source file, sorted.

    Selection honours ``.gitignore``/``.modusignore`` rules (directory-scoped,
    ordered), skips symlinks, secrets, lockfiles, binaries, and files larger
    than ``MAX_SOURCE_BYTES``. ``on_read`` observes the head bytes of each
    accepted file, letting callers hash content in the same pass.
    """
    root = root.resolve()
    root_rules = [(root, value) for value in extra_excludes]

    def disposition(path: Path, reason: str, *, directory: bool = False) -> None:
        if on_disposition is not None:
            on_disposition(
                {
                    "path": path.relative_to(root).as_posix(),
                    "scope": "directory" if directory else "file",
                    "reason": reason,
                }
            )

    rules_by_directory: dict[Path, list[tuple[Path, str]]] = {}
    result = []

    def unavailable(error: OSError) -> None:
        if error.filename:
            disposition(Path(error.filename), "unavailable", directory=True)

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=unavailable):
        base = Path(directory)
        rules = list(rules_by_directory.get(base.parent, ()))
        for name in (".gitignore", ".modusignore"):
            ignore = base / name
            if ignore.is_file() and not ignore.is_symlink():
                for line in ignore.read_text(encoding="utf-8", errors="replace").splitlines():
                    parsed = parse_gitignore_line(line)
                    if parsed:
                        rules.append((base, parsed))
        if base == root:
            rules.extend(root_rules)
        rules_by_directory[base] = rules
        ignored: dict[Path, bool] = {}
        kept = []
        for name in sorted(dirs):
            path = base / name
            reason = (
                "symlink"
                if path.is_symlink()
                else "noise-directory"
                if is_noise_directory(name, base)
                else "managed-output"
                if base == root and name in _ROOT_OUTPUTS
                else "sensitive"
                if is_sensitive(path / "_")
                else "ignored"
                if is_ignored(path, root, rules, _cache=ignored)
                else ""
            )
            if reason:
                disposition(path, reason, directory=True)
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(names):
            path = base / name
            relative = path.relative_to(root)
            reason = (
                "symlink"
                if path.is_symlink()
                else "generated-or-lockfile"
                if name in _SKIP_FILES or name.endswith((".lock", ".min.js", ".map"))
                else "managed-output"
                if relative.as_posix() in MANAGED_ROOT_FILES
                else "sensitive"
                if is_sensitive(relative)
                else "ignored"
                if is_ignored(path, root, rules, _cache=ignored)
                else ""
            )
            if reason:
                disposition(path, reason)
                continue
            try:
                if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
                    disposition(path, "size-or-file-type")
                    continue
                head = read_bound_regular_bytes(root, path, max_bytes=MAX_SOURCE_BYTES)
                if b"\0" in head:
                    disposition(path, "unsupported-binary")
                    continue
                head.decode("utf-8")
            except UnicodeError:
                disposition(path, "unsupported-encoding")
                continue
            except (OSError, BoundKnowledgeReadError):
                disposition(path, "unavailable")
                continue
            if on_read is not None:
                on_read(path, head)
            result.append(path)
    return sorted(result)


__all__ = ["MAX_SOURCE_BYTES", "source_files"]
