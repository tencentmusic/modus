"""Content-addressed input bytes shared by parser, providers and projections."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from modus.artifacts_io import atomic_write_text
from modus.knowledge_reader import BoundKnowledgeReadError, read_bound_regular_bytes
from modus.machine.errors import DriftError, IntegrityError, InvariantError
from modus.paths import ModusPaths


# 内容地址只提供寻址，每次读取仍需核验字节摘要。
# 冻结路径和原始路径分离，解析阶段不会意外读到活跃文件。
@dataclass(frozen=True)
class FrozenSource:
    path: Path
    blob: Path
    digest: str
    max_bytes: int = 2 * 1024 * 1024

    def read_bytes(self) -> bytes:
        raw = read_bound_regular_bytes(self.blob.parent, self.blob, max_bytes=self.max_bytes)
        if hashlib.sha256(raw).hexdigest() != self.digest:
            raise IntegrityError("machine.corpus.corrupt-frozen-input")
        return raw

    def read_text(self, **kwargs: Any) -> str:
        return self.read_bytes().decode("utf-8")


_ACTIVE: ContextVar[InputSnapshot | None] = ContextVar("modus_input_snapshot", default=None)


# 源码、额外描述文件、目录发现及工具链共同构成实际读取集合。
# 封存前允许按需补充输入，封存后新增读取属于生命周期错误。
# 镜像是给外部工具的临时视图，不是第二份可变输入权威。
@dataclass
class InputSnapshot:
    root: Path
    files: dict[str, FrozenSource]
    digest: str
    dispositions: tuple[dict[str, str], ...] = ()
    _mirror: Any = field(default=None, init=False, repr=False)
    _observations: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _extra_blobs: dict[str, FrozenSource] = field(default_factory=dict, init=False, repr=False)
    _directories: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _toolchains: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _coverage_gaps: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _runtime: dict[str, Any] = field(
        default_factory=lambda: runtime_envelope(), init=False, repr=False
    )
    _sealed: bool = field(default=False, init=False, repr=False)
    _mirror_copied: set[str] = field(default_factory=set, init=False, repr=False)
    _mirror_pending: set[str] = field(default_factory=set, init=False, repr=False)
    _dependency_paths: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    memo: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    # 扫描回调直接保存已读字节，避免扫描后再次读取产生时间差。
    # 已有内容块先验证再复用，损坏缓存会按原始字节重建。
    # 源码路径与内容摘要排序后共同确定初始语料身份。
    @classmethod
    def capture(cls, root: Path) -> InputSnapshot:
        from modus.machine.corpus import scan

        root = root.resolve()
        blobs = ModusPaths.for_root(root).analysis_extraction_cache_dir / "inputs"
        files: dict[str, FrozenSource] = {}

        def accept(path: Path, raw: bytes) -> None:
            content_digest = hashlib.sha256(raw).hexdigest()
            target = blobs / content_digest[:2] / content_digest
            try:
                valid = (
                    hashlib.sha256(
                        read_bound_regular_bytes(root, target, max_bytes=scan.MAX_SOURCE_BYTES)
                    ).hexdigest()
                    == content_digest
                )
            except (OSError, ValueError):
                valid = False
            if not valid:
                atomic_write_text(target, raw.decode("utf-8"))
            files[path.relative_to(root).as_posix()] = FrozenSource(path, target, content_digest)

        dispositions: list[dict[str, str]] = []
        scan.source_files(root, on_read=accept, on_disposition=dispositions.append)
        hashes = {path: value.digest for path, value in sorted(files.items())}
        value = hashlib.sha256(
            json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(root, files, value, tuple(dispositions))

    # 仓库内使用相对身份，显式外部依赖保留独立命名空间供后续可移植化。
    def _key(self, path: Path) -> tuple[str, str, str]:
        path = Path(os.path.abspath(path))
        try:
            relative = path.relative_to(self.root).as_posix()
            return relative, "repository", relative
        except ValueError:
            return "external:" + str(path), "external", str(path)

    # 首次观察同时记录存在和缺失，后续读取复用同一事实。
    # 缺失输入也是分析条件，不能在同一轮中突然接受新出现的文件。
    # 二进制额外输入按字节无损保存，不强求 UTF-8 编码。
    # 镜像已创建时，新观察的仓库输入加入待复制集合。
    def observe(self, path: Path, *, dependency: bool = False) -> bytes:
        """Freeze the first actual read, including ignored descriptors and absence."""
        path = Path(os.path.abspath(path))
        key, scope, name = self._key(path)
        if scope == "repository" and name in self.files:
            return self.files[name].read_bytes()
        if key in self._extra_blobs:
            return self._extra_blobs[key].read_bytes()
        if key in self._observations:
            record = self._observations[key]
            raise BoundKnowledgeReadError(
                record["status"], path, "snapshot recorded unavailable input: " + name
            )
        if self._sealed:
            raise InvariantError(
                "machine.corpus.input-after-seal",
                details={"input": name},
            )
        root = self.root if scope == "repository" else path.parent
        try:
            raw = read_bound_regular_bytes(root, path, max_bytes=MAX_ANALYSIS_INPUT_BYTES)
        except (OSError, BoundKnowledgeReadError) as exc:
            status = getattr(exc, "kind", "unavailable")
            self._observations[key] = {
                "scope": scope,
                "path": name,
                "status": str(status),
                "digest": "",
            }
            raise
        content_digest = hashlib.sha256(raw).hexdigest()
        blob = (
            ModusPaths.for_root(self.root).analysis_extraction_cache_dir
            / "inputs"
            / content_digest[:2]
            / content_digest
        )
        try:
            valid = (
                hashlib.sha256(
                    read_bound_regular_bytes(self.root, blob, max_bytes=MAX_ANALYSIS_INPUT_BYTES)
                ).hexdigest()
                == content_digest
            )
        except (OSError, ValueError):
            valid = False
        if not valid:
            atomic_write_text(blob, raw.decode("latin1"), encoding="latin1")
        self._extra_blobs[key] = FrozenSource(path, blob, content_digest, MAX_ANALYSIS_INPUT_BYTES)
        if scope == "repository":
            self._mirror_pending.add(key)
        self._observations[key] = {
            "scope": scope,
            "path": name,
            "status": "present",
            "digest": content_digest,
            "dependency": dependency,
        }
        return raw

    # 目录结果绑定查询条件，同一目录不同过滤不能共享错误缓存。
    # 成员排序由目录扫描统一提供，封存后只允许复用已观察查询。
    def observe_directory(
        self,
        path: Path,
        *,
        names: tuple[str, ...] = (),
        exclude_dirs: tuple[str, ...] = (),
        patterns: tuple[str, ...] = (),
    ) -> list[Path]:
        path = Path(os.path.abspath(path))
        key, scope, name = self._key(path)
        key += (
            "#query:"
            + hashlib.sha256(json.dumps([names, exclude_dirs, patterns]).encode()).hexdigest()[:16]
        )
        if key in self._directories:
            return [path / relative for relative in self._directories[key]["members"]]
        if self._sealed:
            raise InvariantError(
                "machine.corpus.directory-after-seal",
                details={"input": name},
            )
        members = directory_members(path, names=names, exclude_dirs=exclude_dirs, patterns=patterns)
        self._directories[key] = {
            "scope": scope,
            "path": name,
            "members": members,
            "names": list(names),
            "excludeDirs": list(exclude_dirs),
            "patterns": list(patterns),
        }
        return [path / relative for relative in members]

    # 工具路径、探测参数与观察版本一起记录，单纯工具名称不足以标识环境。
    def record_toolchain(
        self, *, name: str, executable: str, args: tuple[str, ...], observed_version: str
    ) -> None:
        if self._sealed:
            raise InvariantError("machine.corpus.toolchain-after-seal")
        record = {
            "name": name,
            "executable": executable,
            "args": list(args),
            "version": observed_version,
        }
        if record not in self._toolchains:
            self._toolchains.append(record)

    # 旧读取集只用于预检，不注入本轮未实际消费的输入。
    def observe_previous_inputs(self, payload: object) -> bool:
        if not valid_analysis_inputs(payload):
            return False
        assert isinstance(payload, Mapping)
        # A preflight compares the previous read set without retaining inputs
        # that the new derivation may no longer read.
        return not verify_analysis_inputs(self.root, payload)

    # 未封闭输入必须明确记录为覆盖缺口，不能只留在调试日志。
    def record_input_gap(self, code: str, detail: str, *, context_id: str = "") -> None:
        if self._sealed:
            raise InvariantError("machine.corpus.input-gap-after-seal")
        row = {"code": code, "contextId": context_id, "detail": detail}
        if row not in self._coverage_gaps:
            self._coverage_gaps.append(row)

    # 规范化排序后计算摘要，使观察顺序不影响分析上下文身份。
    # 覆盖状态由缺口事实决定，不能由调用方任意标记完整。
    def analysis_inputs(self) -> dict[str, Any]:
        payload = {
            "schemaVersion": 1,
            "files": dict(sorted(self._observations.items())),
            "directories": dict(sorted(self._directories.items())),
            "runtime": self._runtime,
            "coverage": {
                "status": "partial" if self._coverage_gaps else "complete",
                "gaps": sorted(
                    self._coverage_gaps, key=lambda row: (row["code"], row["contextId"])
                ),
            },
            "toolchains": sorted(
                self._toolchains, key=lambda row: (row["name"], row["executable"])
            ),
        }
        payload["digest"] = analysis_digest(payload)
        return payload

    # 封存仅关闭新增观察；已有内容仍可被提供者按需读取和核验。
    def seal(self) -> None:
        self._sealed = True

    @property
    def hashes(self) -> dict[str, str]:
        return {path: item.digest for path, item in self.files.items()}

    # ContextVar 隔离不同分析上下文，嵌套退出时恢复外层快照。
    # 临时镜像随激活周期清理，后续激活可按同一冻结材料重建。
    @contextmanager
    def activate(self) -> Iterator[InputSnapshot]:
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)
            if self._mirror is not None:
                self._mirror.cleanup()
                self._mirror = None
                self._mirror_copied.clear()
                self._dependency_paths.clear()
                self._mirror_pending.update(
                    key for key, row in self._observations.items() if row["scope"] == "repository"
                )

    # 发布前重读当前源码并比较集合和内容，不信任修改时间。
    # 增删文件与内容修改分别检测，避免遗漏库存漂移。
    # 额外输入和工具链也参与复核，源码未变不代表分析条件未变。
    def verify(
        self,
        *,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """Verify current inputs without trusting timestamps or mutable AST reads.

        ``on_progress`` is observational only. It receives the number of source
        files re-read and the frozen inventory size, so long verification passes
        remain visible without changing drift semantics.
        """
        from modus.machine.corpus.scan import source_files

        current = {}
        expected = len(self.files)
        completed = 0

        def accept(path: Path, raw: bytes) -> None:
            nonlocal completed
            current[path.relative_to(self.root).as_posix()] = hashlib.sha256(raw).hexdigest()
            completed += 1
            if on_progress is not None:
                on_progress(completed, expected)

        source_files(self.root, on_read=accept)
        if on_progress is not None and completed == 0:
            on_progress(0, expected)
        if set(current) != set(self.files):
            raise DriftError(
                "machine.corpus.changed-during-build",
                "repository inventory changed after capture",
            )
        if current != self.hashes:
            raise DriftError(
                "machine.corpus.changed-during-build",
                "repository content changed after capture",
            )
        changed = verify_analysis_inputs(self.root, self.analysis_inputs(), require_complete=False)
        if changed:
            raise DriftError(
                "machine.corpus.changed-during-build",
                "analysis inputs changed after capture",
            )

    # 外部工具读取真实副本，不能通过链接重新访问活跃源码。
    # 惰性发现的描述文件和头文件在后续调用前补入共享镜像。
    def mirror_root(self) -> Path:
        """Materialize captured application inputs once for local tool consumers."""
        if self._mirror is None:
            self._mirror = tempfile.TemporaryDirectory(prefix="modus-semantic-input-")
            mirror = Path(self._mirror.name).resolve()
            for relative, source in self.files.items():
                target = mirror / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                self._mirror_copied.add(relative)

        mirror = Path(self._mirror.name).resolve()

        # Unit discovery can lazily add descriptors, headers, and binary inputs
        # after an earlier provider already created the shared mirror.
        for key in tuple(self._mirror_pending):
            extra_source = self._extra_blobs.get(key)
            if extra_source is None:
                continue
            relative = self._observations[key]["path"]
            if relative in self._mirror_copied:
                continue
            target = mirror / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(extra_source.read_bytes())
            self._mirror_copied.add(relative)
        self._mirror_pending.clear()
        return mirror

    # Python 内置提供者直接使用快照读取，其他工具接收镜像根。
    # 已冻结的外部依赖复制到独立摘要目录，避免同名依赖覆盖。
    # 工具自身安装位置保持原身份，项目输入路径才映射到镜像。
    # 结果中的临时路径由结果类型统一回写，语料层不依赖事实层类型。
    def provider_executor(
        self, runner: Callable[..., Any], paths: ModusPaths, config: Any, unit: Any
    ) -> Any:
        """Run external providers against captured application inputs.

        Installed SDKs retain their tool identity; explicitly unclosed inputs
        are reported separately from the observations a compiler can produce.
        No project source is symlinked back into the live checkout.
        """
        if unit.language == "python":
            return runner(paths, config, unit)
        mirror = self.mirror_root()

        dependency_paths = self._dependency_paths
        for entry in str(unit.metadata.get("resolvedClasspath") or "").split(os.pathsep):
            if not entry:
                continue
            if entry in dependency_paths:
                continue
            original = Path(entry)
            try:
                original.relative_to(self.root)
                continue
            except ValueError:
                pass
            target_root = (
                mirror / "__modus_dependencies" / hashlib.sha256(entry.encode()).hexdigest()[:24]
            )
            if original.is_dir():
                for frozen in self._extra_blobs.values():
                    try:
                        dependency_relative = frozen.path.relative_to(original)
                    except ValueError:
                        continue
                    target = target_root / dependency_relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.is_file():
                        target.write_bytes(frozen.read_bytes())
                dependency_paths[entry] = str(target_root)
            else:
                key, _, _ = self._key(original)
                frozen_file = self._extra_blobs.get(key)
                if frozen_file is not None:
                    target = target_root / original.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.is_file():
                        target.write_bytes(frozen_file.read_bytes())
                    dependency_paths[entry] = str(target)

        def remap(value: Any) -> Any:
            if isinstance(value, Path):
                try:
                    return mirror / value.relative_to(self.root)
                except ValueError:
                    return value
            if isinstance(value, str):
                if value == str(unit.metadata.get("resolvedClasspath") or "") and value:
                    return os.pathsep.join(
                        dependency_paths.get(item, item.replace(str(self.root), str(mirror)))
                        for item in value.split(os.pathsep)
                    )
                return value.replace(str(self.root), str(mirror))
            if isinstance(value, Mapping):
                return {
                    key: item if key in {"typescriptModule", "nodeExecutable"} else remap(item)
                    for key, item in value.items()
                }
            if isinstance(value, tuple):
                return tuple(remap(item) for item in value)
            if isinstance(value, list):
                return [remap(item) for item in value]
            return value

        mapped = replace(
            unit, root=remap(unit.root), files=remap(unit.files), metadata=remap(unit.metadata)
        )
        mirrored_paths = ModusPaths.for_root(mirror)
        facts = runner(mirrored_paths, config, mapped)
        # Providers normally emit repo-relative anchors. Absolute metadata
        # and diagnostics must not leak the disposable mirror identity. The
        # result type owns its own serialisation, so this stage stays free of
        # fact-layer imports (corpus never depends on facts).
        return facts.rewritten(str(mirror), str(self.root))


def active_snapshot() -> InputSnapshot | None:
    return _ACTIVE.get()


# 活跃快照优先接管应用输入读取，缓存产物不计入应用输入。
# 仓库外显式依赖同样记录，不能因位于外部就绕过漂移检查。
def read_bytes(root: Path, path: Path) -> bytes:
    snapshot = _ACTIVE.get()
    if snapshot is not None:
        try:
            relative = path.absolute().relative_to(snapshot.root).as_posix()
        except ValueError:
            relative = ""
        if relative:
            # Generated caches are products, not application inputs. Their
            # resolved dependency paths are recorded independently by providers.
            try:
                path.absolute().relative_to(
                    ModusPaths.for_root(snapshot.root).analysis_extraction_cache_dir
                )
            except ValueError:
                return snapshot.observe(path)
        elif root.resolve() == snapshot.root:
            return snapshot.observe(path, dependency=True)
    return read_bound_regular_bytes(root, path, max_bytes=MAX_ANALYSIS_INPUT_BYTES)


MAX_ANALYSIS_INPUT_BYTES = 128 * 1024 * 1024
_TOOL_PROBES = {
    "python": ("--version",),
    "javac": ("-version",),
    "go": ("version",),
    "clang++": ("--version",),
    "node": ("--version",),
}
_ENVIRONMENT_INPUTS = (
    "PATH",
    "JAVA_HOME",
    "JDK_HOME",
    "CLASSPATH",
    "GOOS",
    "GOARCH",
    "GOFLAGS",
    "CGO_ENABLED",
    "GOPATH",
    "GOMODCACHE",
    "GOWORK",
    "CPATH",
    "CPLUS_INCLUDE_PATH",
    "C_INCLUDE_PATH",
    "SDKROOT",
    "MACOSX_DEPLOYMENT_TARGET",
    "PYTHONPATH",
    "VIRTUAL_ENV",
)
_PARSER_PACKAGES = (
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
    "tree-sitter-php",
    "tree-sitter-rust",
)


# 解析包缺失本身也是环境状态，安装新语法包应使旧分析上下文失效。
def runtime_envelope() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for name in _PARSER_PACKAGES:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "unavailable"
    return {
        "python": sys.version,
        "packages": packages,
        "environment": {name: os.environ.get(name, "") for name in _ENVIRONMENT_INPUTS},
    }


# 摘要字段自身不参与散列，避免递归依赖；其余输入状态全部纳入。
def analysis_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            {key: item for key, item in value.items() if key != "digest"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


# 先验证模式与内容摘要，再解释文件、目录、覆盖及工具链字段。
# 仓库内路径不能包含父目录跳转，外部路径需显式标记作用域。
# 缺口集合与覆盖状态必须一致，不能同时声称完整且存在缺口。
def valid_analysis_inputs(value: object) -> bool:
    if not isinstance(value, Mapping) or value.get("schemaVersion") != 1:
        return False
    try:
        if value.get("digest") != analysis_digest(value):
            return False
        if not isinstance(value["files"], dict) or not isinstance(value["directories"], dict):
            return False
        if not _valid_input_paths(value["files"], value["directories"]):
            return False
        if not isinstance(value["runtime"], dict) or not isinstance(value["toolchains"], list):
            return False
        if not _valid_input_coverage(value.get("coverage")):
            return False
        for record in value["files"].values():
            if not isinstance(record.get("status"), str) or not isinstance(
                record.get("digest"), str
            ):
                return False
        for record in value["directories"].values():
            if not isinstance(record.get("members"), list) or any(
                not isinstance(item, str) for item in record["members"]
            ):
                return False
        if not _valid_toolchain_inputs(value["toolchains"]):
            return False
        return True
    except (KeyError, ValueError, TypeError):
        return False


def _valid_input_paths(files: dict[str, Any], directories: dict[str, Any]) -> bool:
    """路径检查仅约束仓库相对输入，外部工具链路径保留既有语义。"""
    for record in (*files.values(), *directories.values()):
        if record["scope"] not in {"repository", "external"} or not isinstance(record["path"], str):
            return False
        if record["scope"] == "repository" and (
            Path(record["path"]).is_absolute() or ".." in Path(record["path"]).parts
        ):
            return False
    return True


def _valid_input_coverage(coverage: object) -> bool:
    """覆盖状态必须与缺口列表一致，完整与部分结果使用相同记录契约。"""
    if not isinstance(coverage, Mapping) or coverage.get("status") not in {
        "complete",
        "partial",
    }:
        return False
    if not isinstance(coverage.get("gaps"), list) or any(
        not isinstance(row, Mapping)
        or any(not isinstance(row.get(key), str) for key in ("code", "contextId", "detail"))
        for row in coverage["gaps"]
    ):
        return False
    if bool(coverage["gaps"]) != (coverage["status"] == "partial"):
        return False
    return True


def _valid_toolchain_inputs(toolchains: list[Any]) -> bool:
    """只接受已注册的工具探测结果，保留其可执行文件和版本字段约束。"""
    for record in toolchains:
        if not isinstance(record, Mapping) or record.get("name") not in _TOOL_PROBES:
            return False
        if not isinstance(record.get("executable"), str) or not isinstance(
            record.get("version"), str
        ):
            return False
    return True


# 按输入回执的作用域还原路径：仓库输入相对根目录，外部输入保留绝对位置。
def input_path(root: Path, record: Mapping[str, Any]) -> Path:
    path = str(record["path"])
    return root / path if record["scope"] == "repository" else Path(path)


# 不跟随目录与文件链接，稳定排序支持可重复的目录观察。
# 模式查询用于目录发现，名称过滤用于文件清单，两条路径各有用途。
# 目录成员也属于输入观察，新建或删除文件必须能够使分析身份失效。
def directory_members(
    path: Path,
    *,
    names: tuple[str, ...] = (),
    exclude_dirs: tuple[str, ...] = (),
    patterns: tuple[str, ...] = (),
) -> list[str]:
    if not path.is_dir() or path.is_symlink():
        return []
    if patterns:
        return sorted(
            {
                item.relative_to(path).as_posix()
                for pattern in patterns
                for item in path.glob(pattern)
                if item.is_dir() and not item.is_symlink()
            }
        )
    result = []
    for base, dirs, file_names in os.walk(path, followlinks=False):
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in exclude_dirs and not (Path(base) / name).is_symlink()
        )
        for name in sorted(file_names):
            if names and name not in names:
                continue
            target = Path(base) / name
            if target.is_file() and not target.is_symlink():
                result.append(target.relative_to(path).as_posix())
    return result


# 检查旧回执时只读当前状态，返回变化坐标而不修改冻结材料。
# 工具探测使用固定参数列表和超时，不通过 shell 执行文本。
# 探测失败产生版本不匹配，不能默认为原工具仍可用。
def verify_analysis_inputs(
    root: Path, value: object, *, require_complete: bool = True
) -> list[str]:
    """Verify one analysis run's closed input receipt, read-only."""
    if not valid_analysis_inputs(value):
        return ["analysis-inputs.invalid-manifest"]
    assert isinstance(value, Mapping)
    changed = []
    if require_complete and value.get("coverage", {}).get("status") == "partial":
        changed.append("analysis-inputs.incomplete")
    if value["runtime"] != runtime_envelope():
        changed.append("runtime-environment")
    for key, record in value["files"].items():
        path = input_path(root, record)
        try:
            raw = read_bound_regular_bytes(
                root if record["scope"] == "repository" else path.parent,
                path,
                max_bytes=MAX_ANALYSIS_INPUT_BYTES,
            )
            status, content = "present", hashlib.sha256(raw).hexdigest()
        except (OSError, BoundKnowledgeReadError) as exc:
            status, content = str(getattr(exc, "kind", "unavailable")), ""
        if record.get("status") != status or record.get("digest") != content:
            changed.append(key)
    for key, record in value["directories"].items():
        if directory_members(
            input_path(root, record),
            names=tuple(record.get("names", ())),
            exclude_dirs=tuple(record.get("excludeDirs", ())),
            patterns=tuple(record.get("patterns", ())),
        ) != record.get("members"):
            changed.append(key)
    for record in value["toolchains"]:
        name = record["name"]
        if name == "python":
            executable = sys.executable
        elif name == "javac":
            from modus.machine.runtime.toolchains import java_executable

            executable = java_executable("javac") or ""
        else:
            executable = (
                shutil.which(name) or (shutil.which("clang") if name == "clang++" else "") or ""
            )
        observed = ""
        if executable:
            try:
                # NOCA:dangerous-subprocess-use-audit(可执行文件来自本机工具发现，版本参数来自固定探针表，不经过 shell)
                completed = subprocess.run(
                    [executable, *_TOOL_PROBES[name]],
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                lines = (completed.stdout or completed.stderr).strip().splitlines()
                if completed.returncode == 0 and lines:
                    observed = lines[0][:500]
            except (OSError, subprocess.SubprocessError):
                pass
        if executable != record["executable"] or observed != record["version"]:
            changed.append("toolchain:" + record["name"])
    return changed


def input_exists(root: Path, path: Path) -> bool:
    try:
        read_bytes(root, path)
        return True
    except (OSError, ValueError):
        return False


# 已冻结源码直接复用摘要，额外输入摘要同时包含存在状态。
# 缺失和空文件具有不同身份，避免缓存将两种条件混同。
# 内容摘要由同一输入读取边界产生，不能只用修改时间证明内容一致。
def content_digest(root: Path, path: Path) -> str:
    snapshot = active_snapshot()
    if snapshot is not None:
        key, scope, name = snapshot._key(path)
        if scope == "repository" and name in snapshot.files:
            return snapshot.files[name].digest
        if key not in snapshot._observations:
            read_bytes(root, path)
        if key in snapshot._observations:
            record = snapshot._observations[key]
            return str(record["status"]) + ":" + str(record["digest"])
    return hashlib.sha256(read_bytes(root, path)).hexdigest()
