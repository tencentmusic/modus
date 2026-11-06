"""Freeze and seal the complete input boundary for one machine run.

N1 owns repository/configuration identity and portability. It does not parse
symbols or infer relations; later producers may only read through the active
snapshot and return their observed analysis context for sealing.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from modus.config import ModusConfig
from modus.paths import ModusPaths

from ..errors import ConfigurationError, DriftError
from ..states import SelectionOutcome
from .contracts import (
    CorpusBaseline,
    InputRecord,
    InputRole,
    RepositoryIdentity,
    compose_baseline_digests,
)
from .input_snapshot import InputSnapshot
from .source_roles import build_unit_memberships, source_role


# Git 元数据用于说明来源，真实内容身份仍由冻结字节决定。
def _repository_identity(root: Path) -> RepositoryIdentity:
    """Read optional Git metadata without making Git an input authority."""
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        )
        return RepositoryIdentity(revision, dirty)
    except (OSError, subprocess.SubprocessError):
        return RepositoryIdentity()


# 公开投影移除本机绝对路径，执行时使用的内部快照仍保留完整位置。
# 可移植键发生冲突时按内容稳定编号，不能丢弃同名外部依赖。
def portable(paths: ModusPaths, value: Any, key: str = "") -> Any:
    """Remove checkout- and host-specific identities from persisted evidence."""
    if isinstance(value, Mapping):
        grouped: dict[str, list[Any]] = {}
        for name, item in value.items():
            portable_name = str(portable(paths, str(name), "path"))
            grouped.setdefault(portable_name, []).append(portable(paths, item, str(name)))
        result: dict[str, Any] = {}
        for name, items in grouped.items():
            if len(items) == 1:
                result[name] = items[0]
                continue
            # External paths with the same basename deliberately collapse to
            # the same portable key. Keep every record and number them by
            # portable content, never by their host-specific absolute path.
            ordered = sorted(
                items,
                key=lambda item: json.dumps(
                    item, sort_keys=True, separators=(",", ":"), default=str
                ),
            )
            for index, item in enumerate(ordered, start=1):
                result[f"{name}#{index}"] = item
        return result
    if isinstance(value, (list, tuple)):
        return [portable(paths, item, key) for item in value]
    if isinstance(value, str):
        normalized = value.replace(str(paths.root), ".")
        if normalized.startswith("external:") and os.path.isabs(normalized[9:]):
            normalized = normalized[9:]
        if key.lower().endswith("executable"):
            return Path(normalized).name
        if os.path.isabs(normalized):
            return "external:" + Path(normalized).name
        return normalized.replace("\\", "/")
    return value


def _input_role(relative: str) -> InputRole:
    return {
        "test": InputRole.TEST,
        "fixture": InputRole.TEST,
        "generated": InputRole.GENERATED,
        "configuration": InputRole.CONFIGURATION,
        "document": InputRole.DOCUMENT,
    }.get(source_role(relative), InputRole.SOURCE)


@dataclass(frozen=True, slots=True)
class SealedCorpus:
    """The immutable N1 contract and its publication projection."""

    baseline: CorpusBaseline
    snapshot_payload: dict[str, Any]


# 冻结对象持有本轮配置，后续阶段不能无声切换到新读取的配置。
@dataclass(frozen=True, slots=True)
class FrozenCorpus:
    """Captured bytes plus the semantic configuration governing this run."""

    paths: ModusPaths
    config: ModusConfig
    compiler_mode: str
    snapshot: InputSnapshot

    def activate(self) -> AbstractContextManager[InputSnapshot]:
        """Make frozen reads authoritative for all downstream stages."""
        return self.snapshot.activate()

    # 缺失配置也被观察；配置由不存在变为存在同样属于输入漂移。
    def verify_configuration(self) -> None:
        """Observe configuration and reject drift since initial capture."""
        try:
            self.snapshot.observe(self.paths.config_path)
        except (OSError, ValueError):
            pass
        if ModusConfig.read_available(self.paths).to_dict() != self.config.to_dict():
            raise DriftError(
                "machine.corpus.changed-during-build",
                "analysis configuration changed after capture",
            )

    # 源码角色与语言能力分别描述用途和可分析程度，不能互相替代。
    def _source_records(self, compiler_snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Describe frozen sources with memberships from the completed build context."""
        raw_build_context = compiler_snapshot.get("buildContext", {})
        raw_units = (
            raw_build_context.get("units", []) if isinstance(raw_build_context, Mapping) else []
        )
        memberships = build_unit_memberships(
            self.snapshot.files,
            (row for row in raw_units if isinstance(row, Mapping)),
        )
        sources = []
        for relative, frozen in sorted(self.snapshot.files.items()):
            from modus.machine.languages import capability_for

            capability = capability_for(relative)
            unit_ids, primary_unit_id = memberships[relative]
            sources.append(
                {
                    "path": relative,
                    "sha256": frozen.digest,
                    "bytes": len(frozen.read_bytes()),
                    "language": capability.language,
                    "capabilityTier": str(capability.tier),
                    "structuralExtractor": capability.extractor,
                    "compilerProvider": capability.compiler_provider or None,
                    "frameworkAdapters": list(capability.framework_adapters),
                    "entryDetectors": list(capability.entry_detectors),
                    "degradationReason": capability.degradation_reason,
                    "role": source_role(relative),
                    "buildUnitIds": list(unit_ids),
                    "primaryBuildUnitId": primary_unit_id,
                }
            )
        return sources

    # 构建发现可能晚于源码捕获，最终基线需纳入这些后发现输入。
    # 公开快照先做可移植化，避免工具路径污染可共享证据。
    def seal(self, compiler_snapshot: Mapping[str, Any]) -> SealedCorpus:
        """Bind late-discovered build inputs into the final N1 identity."""
        analysis_config = {
            "compilerMode": self.compiler_mode,
            "initAnalysis": asdict(self.config.init_analysis),
        }
        inputs_summary = {
            "files": portable(self.paths, self.snapshot.analysis_inputs().get("files", {})),
            "directories": portable(
                self.paths, self.snapshot.analysis_inputs().get("directories", {})
            ),
            "toolchains": portable(
                self.paths, self.snapshot.analysis_inputs().get("toolchains", [])
            ),
            "coverage": portable(self.paths, self.snapshot.analysis_inputs().get("coverage", {})),
        }
        records = tuple(
            InputRecord(
                path=relative,
                role=_input_role(relative),
                outcome=SelectionOutcome.INCLUDED,
                content_digest=frozen.digest,
                size_bytes=len(frozen.read_bytes()),
            )
            for relative, frozen in sorted(self.snapshot.files.items())
        )
        build_context = portable(self.paths, compiler_snapshot.get("buildContext", {}))
        context = {
            "analysisConfig": analysis_config,
            "analysisInputs": inputs_summary,
            "buildContext": build_context,
        }
        digests = compose_baseline_digests(records, context)
        sources = self._source_records(compiler_snapshot)
        repository = _repository_identity(self.paths.root)
        baseline = CorpusBaseline(
            repository=repository,
            inputs=records,
            digests=digests,
            analysis_config=analysis_config,
            toolchains=tuple(
                dict(row) for row in inputs_summary["toolchains"] if isinstance(row, Mapping)
            ),
        )
        payload = {
            "schemaVersion": 1,
            "baselineDigest": digests.baseline_digest,
            **digests.to_dict(),
            "repository": repository.to_dict(),
            "analysisConfig": analysis_config,
            "sources": sources,
            "sourceDispositions": list(self.snapshot.dispositions),
            "analysisInputs": inputs_summary,
            "buildContext": build_context,
            "providerContext": {
                "mode": compiler_snapshot.get("mode", self.compiler_mode),
                "providers": portable(self.paths, compiler_snapshot.get("providers", [])),
                "analysisContexts": portable(
                    self.paths, compiler_snapshot.get("analysisContexts", [])
                ),
                "coverageReceipts": portable(
                    self.paths, compiler_snapshot.get("coverageReceipts", [])
                ),
                "inputCoverage": self.snapshot.analysis_inputs().get("coverage", {}),
            },
        }
        return SealedCorpus(baseline, payload)


# 工作区成员需分别分析，外层导航根不是一个合并编译单元。
# 根目录与配置先校验，再创建本轮临时分析区域。
def freeze(root: str | Path, *, compiler_mode: str) -> FrozenCorpus:
    """Capture one repository input set and its analysis configuration."""
    paths = ModusPaths.for_root(root)
    if not paths.root.is_dir():
        raise ConfigurationError(
            "machine.corpus.invalid-root",
            "repository root is not a directory",
        )
    config = ModusConfig.read_available(paths)
    if config.kind == "workspace":
        raise ConfigurationError(
            "machine.corpus.workspace-root",
            "analyze confirmed workspace members independently",
        )
    paths.init_analysis_dir.mkdir(parents=True, exist_ok=True)
    return FrozenCorpus(paths, config, compiler_mode, InputSnapshot.capture(paths.root))


__all__ = ["FrozenCorpus", "SealedCorpus", "freeze", "portable"]
