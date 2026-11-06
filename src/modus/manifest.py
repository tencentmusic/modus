"""The install manifest (``.modus/manifest.json``).

The manifest is what makes explicit project updates safe: it records exactly which
files and which in-file sections Modus owns, plus a content hash for each. On
update, Modus only touches managed files/sections whose hash still matches what
it last wrote -- anything a user edited by hand is left alone.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, TypeVar, cast

from .artifacts_io import atomic_write_text
from .paths import ModusPaths

MANIFEST_VERSION: Final = 1


def hash_text(text: str) -> str:
    """Return the canonical UTF-8 SHA-256 digest for generated text."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    """Return the SHA-256 digest of a file's current bytes."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ManagedFile:
    """One complete file owned by a scaffold template."""

    path: str  # POSIX, relative to project root
    sha256: str
    template: str  # template source id this file was rendered from

    @property
    def is_legacy_hook_config(self) -> bool:
        """旧清单中的共享 hook 容器，仅按签名清理，不能整文件删除。"""
        return self.template.startswith("hooks/") and self.path.endswith(".json")


@dataclass(frozen=True, slots=True)
class ManagedSection:
    """One marker-delimited section inside a user-owned file."""

    path: str  # file that contains the managed section
    marker: str  # marker id, e.g. "modus-skills"
    sha256: str


@dataclass(slots=True)
class Manifest:
    """Mutable aggregate describing exactly what one installation owns."""

    framework_version: str
    platforms: list[str] = field(default_factory=list)
    files: list[ManagedFile] = field(default_factory=list)
    sections: list[ManagedSection] = field(default_factory=list)

    def add_file(self, rel_path: str, content: str, template: str) -> None:
        """Insert or replace a managed-file record by project-relative path."""

        self.files = [f for f in self.files if f.path != rel_path]
        self.files.append(ManagedFile(rel_path, hash_text(content), template))

    def add_section(self, rel_path: str, marker: str, content: str) -> None:
        """Insert or replace a 受管区块 by ``(path, marker)`` identity."""

        self.sections = [
            s for s in self.sections if not (s.path == rel_path and s.marker == marker)
        ]
        self.sections.append(ManagedSection(rel_path, marker, hash_text(content)))

    def is_managed_file(self, rel_path: str) -> bool:
        """Return whether ``rel_path`` belongs to the installed file set."""

        return any(f.path == rel_path for f in self.files)

    def managed_file(self, rel_path: str) -> ManagedFile | None:
        """Return the managed-file record for ``rel_path``, if present."""

        return next((f for f in self.files if f.path == rel_path), None)

    def to_dict(self) -> dict[str, Any]:
        """Serialize deterministically to the stable manifest wire format."""

        return {
            "schemaVersion": MANIFEST_VERSION,
            "frameworkVersion": self.framework_version,
            "platforms": self.platforms,
            "files": [asdict(f) for f in sorted(self.files, key=lambda f: f.path)],
            "sections": [
                asdict(s) for s in sorted(self.sections, key=lambda s: (s.path, s.marker))
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        """Validate and construct a manifest from its persisted wire format."""

        if (
            not isinstance(data, dict)
            or type(data.get("schemaVersion")) is not int
            or data["schemaVersion"] != MANIFEST_VERSION
        ):
            raise ValueError("安装清单格式无效")
        if not isinstance(data.get("frameworkVersion"), str) or not data["frameworkVersion"]:
            raise ValueError("安装清单缺少 frameworkVersion")
        from .platforms import available_platforms

        platforms = data.get("platforms")
        if not isinstance(platforms, list) or any(
            p not in available_platforms() for p in platforms
        ):
            raise ValueError("安装清单的平台列表无效")
        for kind in ("files", "sections"):
            _validate_managed_entries(data.get(kind), kind)
        return cls(
            framework_version=data["frameworkVersion"],
            platforms=list(data.get("platforms", [])),
            files=[ManagedFile(**f) for f in data.get("files", [])],
            sections=[ManagedSection(**s) for s in data.get("sections", [])],
        )

    def write(self, paths: ModusPaths) -> Path:
        """Atomically persist the manifest below its project root."""

        paths.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            paths.manifest_path,
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
        )
        return paths.manifest_path

    @classmethod
    def read(cls, paths: ModusPaths) -> Manifest:
        """Read and validate the current project's install manifest."""

        from .knowledge_reader import read_bound_regular_text

        data = json.loads(read_bound_regular_text(paths.root, paths.manifest_path))
        return cls.from_dict(data)


def _validate_managed_entries(entries: Any, kind: str) -> None:
    """同类受管条目共享路径、摘要与身份约束，按原顺序拒绝无效清单。"""
    if not isinstance(entries, list):
        raise ValueError(f"安装清单缺少 {kind}")
    identities = set()
    for entry in entries:
        relative = entry.get("path", "") if isinstance(entry, dict) else ""
        if (
            not isinstance(relative, str)
            or not relative
            or relative.startswith("/")
            or "\\" in relative
            or any(p in {"", ".", ".."} for p in relative.split("/"))
        ):
            raise ValueError("受管路径无效")
        digest = entry.get("sha256", "")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("受管内容哈希无效")
        identity = (relative, entry.get("marker")) if kind == "sections" else relative
        if identity in identities:
            raise ValueError("受管条目重复")
        identities.add(identity)


_InstallOperation = TypeVar("_InstallOperation", bound=Callable[..., Any])


def serialized_install(function: _InstallOperation) -> _InstallOperation:
    """Serialize installers for the same root without adding project cache files."""
    import tempfile
    from functools import wraps

    from .artifacts_io import required_reentrant_file_lock

    @wraps(function)
    def locked(root: str | Path, *args: Any, **kwargs: Any) -> Any:
        identity = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()
        lock = Path(tempfile.gettempdir()).resolve() / "modus-install-locks" / f"{identity}.lock"
        with required_reentrant_file_lock(lock):
            return function(root, *args, **kwargs)

    return cast(_InstallOperation, locked)


__all__ = [
    "MANIFEST_VERSION",
    "ManagedFile",
    "ManagedSection",
    "Manifest",
    "hash_file",
    "hash_text",
    "serialized_install",
]
