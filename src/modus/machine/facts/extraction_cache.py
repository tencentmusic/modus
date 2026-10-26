"""Invocation-owned parser state and content-addressed structural snapshots."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast, overload

from modus.artifacts_io import atomic_write_text
from modus.knowledge_reader import read_bound_regular_text
from modus.machine.corpus.source_snapshot import SourcePath, SourceSnapshot
from modus.machine.errors import ContractError, safe_error_summary
from modus.machine.facts.generic import extract_generic_text
from modus.machine.facts.language_capabilities import capability_for
from modus.paths import ModusPaths

if TYPE_CHECKING:
    from modus.machine.facts.native_parser import Extractor, FileFacts

F = TypeVar("F", bound=Callable[..., dict[str, Any]])
_CACHE_RESULT_MAX_BYTES = 64 * 1024 * 1024


# 会话状态通过 ContextVar 隔离，避免并发分析共享命中计数。
# 解析器的辅助索引也只在一次提取上下文内复用。
@dataclass
class ExtractionSession:
    """Counters and resolver memos owned by one invocation, including nested calls."""

    root: Path
    hits: int = 0
    misses: int = 0
    oversize: int = 0
    resolvers: dict[str, dict[Any, Any]] = field(default_factory=dict)


_STATE: ContextVar[ExtractionSession | None] = ContextVar("modus_parser_state", default=None)


@overload
def resolver_cache(name: Literal["aliases"]) -> dict[str, dict[str, str]]:
    """Return the active extraction's string-valued alias cache."""


@overload
def resolver_cache(name: Literal["packages"]) -> dict[str, dict[str, Path]]:
    """Return the active extraction's resolved package paths."""


@overload
def resolver_cache(name: str) -> dict[Any, Any]:
    """Return a resolver-owned cache within the current extraction context."""


def resolver_cache(name: str) -> dict[Any, Any]:
    state = _STATE.get()
    return state.resolvers.setdefault(name, {}) if state is not None else {}


# 根目录同时限定源码读取范围和缓存身份，不能仅作显示用途。
# 所有输入先归一到同一个项目坐标系，再交给提取器。
# finally 恢复上下文，嵌套调用与异常退出都不污染后续分析。
def extraction_context(function: F) -> F:
    @wraps(function)
    def run(paths: list[Path], cache_root: Path | None = None, **kwargs: Any) -> dict[str, Any]:
        original = (
            Path(cache_root).absolute()
            if cache_root
            else Path(os.path.commonpath([str(Path(p).absolute()) for p in paths]))
            if paths
            else Path.cwd()
        )
        if original.is_file():
            original = original.parent
        root = original.resolve()
        normalized = []
        for path in paths:
            path = Path(path).absolute()
            try:
                relative = path.relative_to(original)
            except ValueError:
                relative = path.relative_to(root)
            if ".." in relative.parts:
                raise ContractError("machine.corpus.source-outside-root")
            normalized.append(root / relative)
        session = ExtractionSession(root)
        token = _STATE.set(session)
        try:
            result = function(normalized, cache_root=root, **kwargs)
            result["cacheStats"] = {
                "reusedFiles": session.hits,
                "parsedFiles": session.misses,
                "uncachedOversizeFiles": session.oversize,
            }
            return result
        finally:
            _STATE.reset(token)

    return cast(F, run)


def project_root() -> Path | None:
    state = _STATE.get()
    return state.root if state else None


# 优先读取已捕获的快照，使同一轮提取不受中途文件修改影响。
def read_source_bytes(path: SourcePath) -> bytes:
    if isinstance(path, SourceSnapshot):
        return path.read_bytes()
    root = project_root() or Path(path).parent
    from modus.machine.corpus.input_snapshot import read_bytes

    return read_bytes(root, Path(path))


# 缓存身份包含解析实现与语法包版本，代码升级会自然失效。
# 文件级访问器虽然拆分到独立模块，仍属于同一解析契约。
def _implementation_digest() -> hashlib._Hash:
    """Hash the structural-extraction implementation and its parser versions.

    Files and dependency/configuration changes can alter import resolution, so
    the digest participates in every per-file cache key. It is derived from the
    shipped implementation instead of relying on a manually bumped cache version.
    """
    code = hashlib.sha256()
    import modus.machine.languages as _languages
    from modus.machine.corpus import source_snapshot as _source_snapshot
    from modus.machine.facts import (
        generic as _generic,
    )
    from modus.machine.facts import (
        language_capabilities as _language_capabilities,
    )
    from modus.machine.facts import native_cpp, native_kotlin, native_objc, native_swift
    from modus.machine.facts import (
        native_parser as _native_parser,
    )
    from modus.machine.facts import native_syntax as _native_syntax
    from modus.machine.facts import native_visitor as _native_visitor
    from modus.machine.store import ids as _ids

    # Missing implementation inputs must fail loudly: silently skipping one
    # would freeze stale cache entries across code changes.
    for path in (
        Path(_generic.__file__),
        Path(_languages.__file__).with_name("language-registry.json"),
        Path(_languages.__file__),
        Path(_language_capabilities.__file__),
        Path(_ids.__file__),
        Path(_source_snapshot.__file__),
        Path(_native_parser.__file__),
        Path(_native_syntax.__file__),
        Path(_native_visitor.__file__),
        *(
            Path(cast(str, module.__file__))
            for module in (
                native_objc,
                native_swift,
                native_cpp,
                native_kotlin,
            )
        ),
        Path(__file__),
    ):
        code.update(path.read_bytes())
    for name in (
        "tree-sitter",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
        "tree-sitter-java",
        "tree-sitter-go",
        "tree-sitter-c",
        "tree-sitter-cpp",
        "tree-sitter-c-sharp",
        "tree-sitter-kotlin",
        "tree-sitter-objc",
        "tree-sitter-swift",
        "tree-sitter-php",
        "tree-sitter-rust",
    ):
        try:
            code.update(f"{name}:{version(name)}".encode())
        except PackageNotFoundError:
            code.update(f"{name}:unavailable".encode())
    return code


def implementation_fingerprint() -> str:
    """Hex fingerprint of the structural extraction implementation."""
    return _implementation_digest().hexdigest()


# 原生解析失败时保留通用事实，并附上明确的降级诊断。
# 降级结果不能伪装成完整解析，后续阶段需据完整度解释证据。
def _parse_one(path: Path, raw: bytes, parser_for: Callable[[Path], Extractor]) -> dict[str, Any]:
    snapshot = SourceSnapshot(path, raw.decode("utf-8"))
    try:
        result = parser_for(path)(snapshot)
        if result.get("error"):
            fallback = extract_generic_text(snapshot)
            result = {
                **fallback,
                "diagnostics": fallback["diagnostics"]
                + [{"code": "machine.facts.parser-failed", "message": "parser failed"}],
            }
    except (ImportError, ValueError, RuntimeError, RecursionError) as exc:
        result = extract_generic_text(snapshot)
        result.setdefault("diagnostics", []).append(
            {
                "code": "machine.facts.parser-unavailable",
                "message": safe_error_summary(exc),
            }
        )
    return result


# 子进程显式建立根目录上下文，不能依赖父进程的隐式状态。
def _parse_worker(root: Path, path: Path, raw: bytes) -> dict[str, Any]:
    """Worker receives captured bytes; it cannot reopen a mutable source file."""
    from modus.machine.facts.structural import _get_extractor

    token = _STATE.set(ExtractionSession(root))
    try:
        return _parse_one(path, raw, _get_extractor)
    finally:
        _STATE.reset(token)


# 结果按输入位置回填，进程完成顺序不影响输出顺序。
# 缓存同时核验请求身份与内容摘要，损坏记录会重新提取。
# 缓存写入失败不丢弃有效解析结果；缓存始终是可重建的优化。
# 待处理任务设上限，防止大仓库一次排队占用过多内存。
def extract_files(
    paths: list[Path], root: Path, parser_for: Callable[[Path], Extractor]
) -> list[FileFacts]:
    """Parse captured bytes, retaining caller order across cache hits and workers.

    Cache publication is best effort; an I/O failure must not discard a valid
    parse result. Worker completion order never becomes source ordering, and
    parser failure remains visible through fallback diagnostics.
    """

    from collections import deque
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context

    from modus.machine.runtime.resources import current_policy

    context = _implementation_digest().digest()
    cache = ModusPaths.for_root(root).analysis_extraction_cache_dir / "structure"
    results: list[FileFacts | None] = [None] * len(paths)
    policy = current_policy()
    workers = min(policy.workers, max(1, len(paths) // 32))
    executor = None
    pending: Any = deque()
    state = _STATE.get()

    def finish(
        index: int, path: Path, raw: bytes, key: str, target: Path, result: dict[str, Any]
    ) -> None:
        capability = capability_for(path)
        completeness = result.get("analysisCompleteness", "structural")
        if completeness == "partial":
            result.setdefault("diagnostics", []).append(
                {
                    "code": "machine.facts.parser-partial",
                    "path": str(path),
                    "message": "Recovered structure contains syntax errors or incomplete analysis.",
                }
            )
        content_digest = hashlib.sha256(raw).hexdigest()
        for item in result.get("nodes", []) + result.get("edges", []):
            item.setdefault("language", capability.language)
            item.setdefault(
                "analysis_source",
                "text"
                if completeness == "fallback"
                else "document"
                if capability.extractor == "extract_markdown"
                else "tree-sitter",
            )
            item.setdefault("analysis_completeness", completeness)
            item.setdefault("content_digest", content_digest)
        try:
            result_digest = hashlib.sha256(
                json.dumps(
                    result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            payload = json.dumps(
                {"key": key, "root": str(root), "result": result, "resultDigest": result_digest}
            )
            if len(payload.encode()) <= _CACHE_RESULT_MAX_BYTES:
                atomic_write_text(target, payload)
            elif state:
                state.oversize += 1
        except OSError:
            pass
        results[index] = cast("FileFacts", result)

    def drain_one() -> None:
        index, path, raw, key, target, future = pending.popleft()
        finish(index, path, raw, key, target, future.result())

    try:
        for index, path in enumerate(paths):
            raw = read_source_bytes(path)
            key = hashlib.sha256(
                context + path.relative_to(root).as_posix().encode() + raw
            ).hexdigest()
            target = cache / (key + ".json")
            result = None
            try:
                saved = json.loads(
                    read_bound_regular_text(root, target, max_bytes=_CACHE_RESULT_MAX_BYTES)
                )
                if (
                    isinstance(saved, dict)
                    and saved.get("key") == key
                    and saved.get("root") == str(root)
                ):
                    candidate = saved["result"]
                    if (
                        isinstance(candidate, dict)
                        and saved.get("resultDigest")
                        == hashlib.sha256(
                            json.dumps(
                                candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                            ).encode()
                        ).hexdigest()
                    ):
                        result = candidate
            except (OSError, ValueError, TypeError, KeyError):
                pass
            if isinstance(result, dict):
                results[index] = cast("FileFacts", result)
                if state:
                    state.hits += 1
                continue
            if state:
                state.misses += 1
            if workers == 1:
                finish(index, path, raw, key, target, _parse_one(path, raw, parser_for))
            else:
                if executor is None:
                    executor = ProcessPoolExecutor(
                        max_workers=workers, mp_context=get_context("spawn")
                    )
                pending.append(
                    (index, path, raw, key, target, executor.submit(_parse_worker, root, path, raw))
                )
                if len(pending) >= workers * 2:
                    drain_one()
        while pending:
            drain_one()
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    return [item for item in results if item is not None]
