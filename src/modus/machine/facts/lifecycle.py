"""Run independent fact producers over one frozen corpus.

N2 observes structural, compiler and explicit rule facts. It does not bind
cross-producer identities or infer behavior; those are N3/N4 responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..corpus.lifecycle import FrozenCorpus, SealedCorpus
from ..languages import validate_language_registry
from ..states import Completeness, ExecutionStatus
from .compiler.models import CompilerSemanticResult
from .extension_registry import builtin_extensions
from .materials import observe_material
from .rule_signals import LoadedAuthoringRules, load_authoring_rules, project_authoring_records
from .semantic_providers import run_compiler_analysis
from .structural import extract


# 冻结输入与 sealed 基线同时传递，后续阶段无需再次读取工作树。
@dataclass(frozen=True, slots=True)
class ObservedProgramFacts:
    """Compact N2 products plus the final baseline they were observed against."""

    corpus: FrozenCorpus
    sealed_corpus: SealedCorpus
    extraction: dict[str, Any]
    compiler: CompilerSemanticResult
    compiler_snapshot: dict[str, Any]
    authoring_rules: LoadedAuthoringRules
    stage_summary: dict[str, dict[str, Any]]
    materials: dict[str, list[dict[str, Any]]]
    rule_observations: dict[str, list[dict[str, Any]]]


# 先验证配置身份，再运行彼此独立的结构、编译与规则生产者。
# 编译器观测参与封存身份；禁用编译器是显式 unavailable，而非完整成功。
# 阶段摘要保留各自完整性，局部缺口不会被另一生产者的成功覆盖。
def observe(corpus: FrozenCorpus) -> ObservedProgramFacts:
    """Run every configured producer and preserve independent degradation."""
    builtin_extensions()
    validate_language_registry()
    corpus.verify_configuration()
    authoring_rules = load_authoring_rules(corpus.paths, corpus.config)
    files = [item.path for item in corpus.snapshot.files.values()]
    materials = {
        path: observe_material(path, frozen.read_text())
        for path, frozen in corpus.snapshot.files.items()
        if frozen.path.suffix.casefold() in {".md", ".markdown", ".txt"}
    }
    rule_observations = {
        path: project_authoring_records(path, frozen.read_text(), authoring_rules.rules)
        for path, frozen in corpus.snapshot.files.items()
        if path not in materials
    }
    extraction = (
        extract(files, cache_root=corpus.paths.root)
        if files
        else {"nodes": [], "edges": [], "diagnostics": []}
    )
    compiler = run_compiler_analysis(
        corpus.paths,
        corpus.config,
        mode=corpus.compiler_mode,
        provider_executor=corpus.snapshot.provider_executor,
    )
    compiler_snapshot = compiler.snapshot(corpus.paths.root)
    sealed = corpus.seal(compiler_snapshot)
    structural_diagnostics = list(extraction.get("diagnostics") or [])
    compiler_completeness = (
        Completeness.UNAVAILABLE
        if compiler.mode == "off"
        else Completeness.PARTIAL
        if any(
            str(row.get("analysisCompleteness") or "") != "complete"
            for row in compiler.provider_status
        )
        else Completeness.COMPLETE
    )
    stages = {
        "rules": {
            "status": str(ExecutionStatus.ANALYZED),
            "completeness": str(
                Completeness.PARTIAL if authoring_rules.diagnostics else Completeness.COMPLETE
            ),
            "rules": len(authoring_rules.rules),
            "diagnostics": len(authoring_rules.diagnostics),
        },
        "structural": {
            "status": str(ExecutionStatus.ANALYZED),
            "completeness": str(
                Completeness.PARTIAL if structural_diagnostics else Completeness.COMPLETE
            ),
            "files": len(files),
            "nodes": len(extraction.get("nodes") or []),
            "edges": len(extraction.get("edges") or []),
        },
        "compiler": {
            "status": str(
                ExecutionStatus.SKIPPED if compiler.mode == "off" else ExecutionStatus.ANALYZED
            ),
            "completeness": str(compiler_completeness),
            "providers": len(compiler.provider_status),
            "semanticNodes": len(compiler.facts.nodes),
            "semanticEdges": len(compiler.facts.edges),
        },
    }
    return ObservedProgramFacts(
        corpus,
        sealed,
        extraction,
        compiler,
        compiler_snapshot,
        authoring_rules,
        stages,
        materials,
        rule_observations,
    )


__all__ = ["ObservedProgramFacts", "observe"]
