"""在任意测试主机覆盖无 openat、Windows 换行及文件替换的回归边界。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from modus import artifacts_io, atomic_writes, knowledge_reader
from modus import knowledge_write_session as session
from modus.cli_commands.presentation import _parser_detail
from modus.knowledge_reader import (
    BoundKnowledgeReadError,
    read_bound_regular_bytes,
    read_bound_regular_text,
)
from modus.knowledge_update import update_knowledge
from modus.manifest import hash_file
from modus.platforms import available_platforms
from modus.scaffold import scaffold_project


@pytest.fixture(autouse=True)
def portable_reads_and_deletions(monkeypatch: pytest.MonkeyPatch) -> None:
    """选择可移植后端，保留测试主机真实的文件、线程和锁行为。"""
    monkeypatch.setattr(knowledge_reader, "_supports_bound_reads", lambda: False)
    monkeypatch.setattr(session, "_supports_bound_reads", lambda: False)


@pytest.mark.parametrize("raw", [b"", "# 中文\r\n\r\n内容\n".encode()])
def test_portable_read_preserves_exact_bytes_and_budget(tmp_path: Path, raw: bytes) -> None:
    target = tmp_path / "knowledge.md"
    target.write_bytes(raw)
    assert read_bound_regular_bytes(tmp_path, target, max_bytes=len(raw)) == raw
    assert read_bound_regular_text(tmp_path, target) == raw.decode("utf-8")
    if raw:
        with pytest.raises(BoundKnowledgeReadError) as caught:
            read_bound_regular_bytes(tmp_path, target, max_bytes=len(raw) - 1)
        assert caught.value.kind == "oversized-file"


def test_portable_read_distinguishes_missing_and_invalid_text(tmp_path: Path) -> None:
    with pytest.raises(BoundKnowledgeReadError) as caught:
        read_bound_regular_bytes(tmp_path, tmp_path / "absent" / "document.md")
    assert caught.value.kind == "missing"
    target = tmp_path / "document.md"
    target.write_bytes(b"\xff")
    with pytest.raises(BoundKnowledgeReadError) as caught:
        read_bound_regular_text(tmp_path, target)
    assert caught.value.kind == "invalid-file"


@pytest.mark.parametrize("linked_parent", [False, True])
def test_portable_read_rejects_links(tmp_path: Path, linked_parent: bool) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    original = outside / "document.md"
    original.write_bytes(b"private")
    if linked_parent:
        parent = tmp_path / "linked"
        parent.symlink_to(outside, target_is_directory=True)
        target = parent / original.name
    else:
        target = tmp_path / "linked.md"
        target.symlink_to(original)
    with pytest.raises(BoundKnowledgeReadError):
        read_bound_regular_bytes(tmp_path, target)
    assert original.read_bytes() == b"private"


@pytest.mark.parametrize("reparse_parent", [False, True])
def test_portable_read_rejects_windows_reparse_attributes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reparse_parent: bool
) -> None:
    target = tmp_path / "document.md"
    target.write_bytes(b"private")
    original = atomic_writes._portable_lstat if reparse_parent else Path.lstat

    def reparse_stat(path: Path):
        info = original(path)
        if path == (tmp_path if reparse_parent else target):
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            fields["st_file_attributes"] = 0x0400
            return SimpleNamespace(**fields)
        return info

    if reparse_parent:
        monkeypatch.setattr(atomic_writes, "_portable_lstat", reparse_stat)
    else:
        monkeypatch.setattr(Path, "lstat", reparse_stat)
    with pytest.raises(BoundKnowledgeReadError):
        read_bound_regular_bytes(tmp_path, target)


def test_portable_read_rejects_file_replaced_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "document.md"
    target.write_bytes(b"original")
    original = os.open

    def replace_before_open(path, flags, *args, **kwargs):
        if Path(path) == target:
            target.rename(target.with_suffix(".retained"))
            target.write_bytes(b"replacement")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_before_open)
    with pytest.raises(BoundKnowledgeReadError) as caught:
        read_bound_regular_bytes(tmp_path, target)
    assert caught.value.kind == "changed-file"
    assert target.with_suffix(".retained").read_bytes() == b"original"


def test_portable_read_rejects_parent_replaced_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "knowledge"
    parent.mkdir()
    target = parent / "document.md"
    target.write_bytes(b"original")
    original = knowledge_reader._read_stable_bytes

    def replace_after_read(*args, **kwargs):
        raw = original(*args, **kwargs)
        parent.rename(tmp_path / "retained")
        parent.mkdir()
        target.write_bytes(b"replacement")
        return raw

    monkeypatch.setattr(knowledge_reader, "_read_stable_bytes", replace_after_read)
    with pytest.raises(BoundKnowledgeReadError) as caught:
        read_bound_regular_bytes(tmp_path, target)
    assert caught.value.kind == "changed-file"


def test_portable_knowledge_lifecycle_uses_raw_digest_and_detects_conflicts(tmp_path: Path) -> None:
    relative = "modus/knowledge/domain/orders/references/modules/payment.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    original = "# 人工内容\r\n".encode()
    target.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    conflict = update_knowledge(
        str(tmp_path), {relative: "# Wrong\n"}, expected_hashes={relative: "0" * 64}
    )
    assert conflict["status"] == "partial"
    assert target.read_bytes() == original
    updated = "# 已更新\n"
    result = update_knowledge(
        str(tmp_path), {relative: updated}, expected_hashes={relative: digest}
    )
    assert result["status"] == "completed"
    assert target.read_bytes() == updated.encode()
    expected = {relative: hashlib.sha256(updated.encode()).hexdigest()}
    result = update_knowledge(str(tmp_path), {}, deletions=[relative], expected_hashes=expected)
    assert result["deleted"] == [relative], result
    result = update_knowledge(str(tmp_path), {}, deletions=[relative], expected_hashes=expected)
    assert result["alreadyAbsent"] == [relative]


def test_portable_delete_handles_different_stat_and_fstat_creation_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = "modus/knowledge/domain/orders/references/modules/old.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    original = Path.lstat

    def path_creation_time(path: Path):
        info = original(path)
        if path == target:
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            fields["st_ctime_ns"] += 1_000_000_000
            return SimpleNamespace(**fields)
        return info

    monkeypatch.setattr(Path, "lstat", path_creation_time)
    result = update_knowledge(
        str(tmp_path),
        {},
        deletions=[relative],
        expected_hashes={relative: hashlib.sha256(b"original").hexdigest()},
    )
    assert result["deleted"] == [relative], result
    assert not target.exists()


def test_portable_delete_preserves_a_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = "modus/knowledge/domain/orders/references/modules/old.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    original = session._unlink_verified_candidate

    def replace_before_unlink(*args, **kwargs):
        target.rename(target.with_suffix(".retained"))
        target.write_bytes(b"replacement")
        return original(*args, **kwargs)

    monkeypatch.setattr(session, "_unlink_verified_candidate", replace_before_unlink)
    result = update_knowledge(
        str(tmp_path),
        {},
        deletions=[relative],
        expected_hashes={relative: hashlib.sha256(b"original").hexdigest()},
    )
    assert result["status"] == "partial"
    assert target.read_bytes() == b"replacement"
    assert target.with_suffix(".retained").read_bytes() == b"original"


@pytest.mark.parametrize("linked_parent", [False, True])
def test_windows_required_lock_rejects_links_without_writing(
    tmp_path: Path, linked_parent: bool
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    original = outside / "document.lock"
    original.write_bytes(b"preserved")
    if linked_parent:
        parent = tmp_path / "linked"
        parent.symlink_to(outside, target_is_directory=True)
        lock_path = parent / "nested" / "document.lock"
    else:
        lock_path = tmp_path / "document.lock"
        lock_path.symlink_to(original)
    with pytest.raises(artifacts_io.FileLockIntegrityError):
        with artifacts_io._windows_required_file_lock(lock_path, SimpleNamespace()):
            pytest.fail("不安全路径不能进入锁保护区")
    assert original.read_bytes() == b"preserved"
    assert not (outside / "nested").exists()


def test_resource_policy_without_unix_sysconf(monkeypatch: pytest.MonkeyPatch) -> None:
    from modus.machine.runtime.resources import resolve_policy

    monkeypatch.delattr(os, "sysconf", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 64)
    policy = resolve_policy()
    assert policy.memory_bytes == 512 * 1024**2
    assert policy.workers == policy.compiler_workers == 2
    assert resolve_policy("throughput", memory_budget=16 * 1024**3).workers == 32


@pytest.mark.parametrize("path", [r"C:\Users\dev\[bold] 中文", r"C:\a'b\c", 'C:\\a"b\\c'])
def test_parser_error_preserves_windows_path(path: str) -> None:
    assert _parser_detail(f"Directory {path!r} does not exist.") == f"路径不存在：{path}"


def test_install_manifest_matches_bytes_with_windows_default_newlines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.write_text

    def windows_write_text(self, data, encoding=None, errors=None, newline=None):
        return original(
            self,
            data,
            encoding=encoding,
            errors=errors,
            newline="\r\n" if newline is None else newline,
        )

    monkeypatch.setattr(Path, "write_text", windows_write_text)
    first = scaffold_project(tmp_path, available_platforms())
    assert all(entry.sha256 == hash_file(tmp_path / entry.path) for entry in first.files)
    second = scaffold_project(tmp_path, available_platforms())
    assert first.to_dict() == second.to_dict()
