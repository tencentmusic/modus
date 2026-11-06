"""Knowledge verification checks objective integrity and declared publication scope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from _support.sensitive_samples import synthetic_source_assignment
from modus.cli import app
from modus.commands.seed_business import seed_domain_business
from modus.commands.verify_knowledge import run_verify_knowledge
from modus.paths import ModusPaths

runner = CliRunner()


def test_anchor_declarations_ignore_mentions_and_preserve_concurrent_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modus.commands import verify_anchors
    from modus.skillmd import render

    paths = _clean_project(tmp_path)
    source = tmp_path / "src/app.py"
    source.write_text(
        '# run() is obsolete\nmessage = "run"\nclass A:\n    def run(self):\n        pass\nclass B:\n    def run(self):\n        pass\n',
        encoding="utf-8",
    )
    module = paths.module("core", "runner")

    def anchor(symbol, line, end=None):
        location = {"path": "src/app.py", "symbol": symbol, "startLine": line}
        if end is not None:
            location["endLine"] = end
        module.write_text(
            render({"anchors": {"locations": [location]}}, "# 正文\n"), encoding="utf-8"
        )

    anchor("run", 1)
    assert verify_anchors.run_verify_anchors(str(tmp_path))["counts"] == {"ambiguous": 1}
    anchor("A.run", 1)
    result = verify_anchors.run_verify_anchors(str(tmp_path))
    assert result["findings"][0]["actualLine"] == 4
    anchor("A.run", 4, 8)
    assert verify_anchors.run_verify_anchors(str(tmp_path))["counts"] == {"range_drift": 1}
    anchor("A.run", 1)
    original = verify_anchors._read_source

    def concurrent(paths, relative):
        module.write_text(module.read_text(encoding="utf-8") + "\n人工新增说明\n", encoding="utf-8")
        return original(paths, relative)

    monkeypatch.setattr(verify_anchors, "_read_source", concurrent)
    result = verify_anchors.run_verify_anchors(str(tmp_path), fix=True)
    assert "anchor_write_conflict" in result["counts"] and not result["fixedDocuments"]
    assert "人工新增说明" in module.read_text(encoding="utf-8")
    assert "startLine: 1" in module.read_text(encoding="utf-8")


def test_java_anchor_signature_separates_overloads(tmp_path: Path) -> None:
    from modus.scope_models import SourceLocation
    from modus.source_anchors import declaration_matches, source_declarations

    code = ["class A {", " void run(String value) {}", " void run(int value) {}", "}"]
    declarations = source_declarations("A.java", code)
    assert declarations is not None
    assert declaration_matches(declarations, SourceLocation("A.java", "A.run(String)", 1)) == [
        (2, 2)
    ]
    assert declaration_matches(declarations, SourceLocation("A.java", "A.run(int)", 1)) == [(3, 3)]
    fields = source_declarations("A.java", ["class A { int run; }"])
    assert fields is not None
    assert declaration_matches(fields, SourceLocation("A.java", "A.run()", 1)) == []


def test_python_constant_anchors_preserve_kind_owner_and_range() -> None:
    from modus.scope_models import SourceLocation
    from modus.source_anchors import declaration_matches, source_declarations

    declarations = source_declarations(
        "settings.py",
        [
            "# MAX_ROWS = 99 is only a comment",
            "MAX_ROWS: int = 100",
            "LEFT, RIGHT = (1, 2)",
            "class Settings:",
            "    LIMIT = (",
            "        2",
            "    )",
            "    def run(self):",
            "        MAX_ROWS = 9",
            "        self.limit = 1",
        ],
    )
    assert declarations is not None
    assert declaration_matches(declarations, SourceLocation("settings.py", "MAX_ROWS", 1)) == [
        (2, 2)
    ]
    assert declaration_matches(declarations, SourceLocation("settings.py", "RIGHT", 1)) == [(3, 3)]
    assert declaration_matches(
        declarations, SourceLocation("settings.py", "Settings.LIMIT", 1)
    ) == [(5, 7)]
    assert declaration_matches(declarations, SourceLocation("settings.py", "MAX_ROWS()", 2)) == []
    assert declaration_matches(declarations, SourceLocation("settings.py", "limit", 10)) == []


def test_java_multiline_anchor_keeps_range_and_syntax_parameter_types(tmp_path: Path) -> None:
    from modus.commands.verify_anchors import run_verify_anchors
    from modus.skillmd import render

    source = (
        "class A {\n"
        " void run(final String value, @Deprecated java.util.Map<String, Integer> data, "
        "int array[], String... rest) {\n"
        "  System.out.println(value);\n"
        " }\n"
        "}\n"
    )
    (tmp_path / "A.java").write_text(source, encoding="utf-8")
    document = tmp_path / "modus/knowledge/domain/core/SKILL.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        render(
            {
                "anchors": {
                    "locations": [
                        {
                            "path": "A.java",
                            "symbol": "A.run(String,java.util.Map<String,Integer>,int[],String...)",
                            "startLine": 2,
                            "endLine": 4,
                        }
                    ]
                }
            },
            "# 任务\n",
        ),
        encoding="utf-8",
    )
    assert run_verify_anchors(str(tmp_path))["counts"] == {}
    (tmp_path / "A.java").write_text("\n" + source, encoding="utf-8")
    result = run_verify_anchors(str(tmp_path), fix=True)
    assert result["counts"] == {"line_drift": 1}
    assert "endLine: 5" in document.read_text(encoding="utf-8")
    assert run_verify_anchors(str(tmp_path))["counts"] == {}


def test_cpp_anchor_preserves_namespace_owner_and_parameter_qualification() -> None:
    from modus.scope_models import SourceLocation
    from modus.source_anchors import declaration_matches, source_declarations

    declarations = source_declarations(
        "service.cpp",
        [
            "namespace First {",
            " void run(const std::string& value) {",
            " }",
            "}",
            "namespace Second { void run(const std::string& value) {} }",
        ],
    )
    assert declarations is not None
    assert declaration_matches(
        declarations, SourceLocation("service.cpp", "First::run(const std::string&)", 1)
    ) == [(2, 3)]
    assert declaration_matches(
        declarations, SourceLocation("service.cpp", "Second::run(const std::string&)", 1)
    ) == [(5, 5)]


def test_card_rejects_duplicate_frontmatter_and_ignores_body_tables(tmp_path: Path) -> None:
    from modus.knowledge_verification.authoring_card import (
        load_authoring_plan,
        verify_module_execution,
    )

    paths = _clean_project(tmp_path)
    _write_publication_card(paths)
    original = paths.scope_confirmation_path.read_text(encoding="utf-8")
    paths.scope_confirmation_path.write_text(
        original + "\n| status | reviewed |\n| mode | source-fallback |\n", encoding="utf-8"
    )
    plan, findings = load_authoring_plan(paths)
    assert plan and not findings
    paths.scope_confirmation_path.write_text(
        original.replace(
            "executionMode: serial", "executionMode: serial\n    executionMode: domain-parallel"
        ),
        encoding="utf-8",
    )
    plan, findings = load_authoring_plan(paths)
    assert plan is None and findings[0].code == "authoring-card-invalid"
    assert "executionMode" in findings[0].detail and "行" in findings[0].detail
    _, findings = verify_module_execution(
        "core",
        "runner",
        {
            "status": "reviewed",
            "evidence": {
                "status": "ready",
                "mode": "source-fallback",
                "requestedScope": "module:core/runner",
                "selector": "src/app.py",
            },
        },
    )
    assert any(
        finding.context.get("field")
        == "modus.authoring.domains.core.modules.runner.evidence.reason"
        for finding in findings
    )


# 所有夹具使用 UTF-8，与知识读取契约一致。
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# 已确认模块仍需源码锚点，状态字段不能替代可回查证据。
# 自定义标题用于证明验证器不强制固定叙事模板。
def _module_body(*, module_id: str = "core/runner", parent: str | None = None) -> str:
    parent_line = f"parent: {parent}\n" if parent is not None else ""
    return f"""---
schemaVersion: 1
moduleId: {module_id}
{parent_line}state: confirmed
anchors:
  locations:
    - path: src/app.py
      symbol: run
      startLine: 1
      endLine: 2
---

# Runner

## A deliberately custom heading

The request completes synchronously and returns the committed result.
"""


# 最小可用知识集包含架构、领域、模块和索引，供各损坏场景单独变异。
# 共享夹具保持正文自然结构，让校验聚焦客观完整性。
def _clean_project(root: Path) -> ModusPaths:
    paths = ModusPaths.for_root(root)
    _write(root / "src/app.py", "def run():\n    return 'ok'\n")
    _write(paths.architecture_overview, "# Overview\n\n[Core](domain/core/SKILL.md)\n")
    _write(
        paths.domain_skill("core"),
        "# Core domain\n\n[Runner](references/modules/runner.md)\n",
    )
    _write(paths.module("core", "runner"), _module_body())
    _write(
        paths.domain_references("core") / "api.md",
        "# API\n\n## Commands that change state\n\n### Run\n\nExecutes one request.\n",
    )
    _write(
        paths.domain_references("core") / "object.md",
        "# Objects\n\n## Request envelope\n\nThe input accepted by the runner.\n",
    )
    return paths


# 断言使用稳定发现码，不把中文提示措辞绑定为实现细节。
def _codes(result: dict) -> set[str]:
    return {str(item["finding"]) for item in result["findings"]}


# 执行卡显式记录覆盖、模块证据与图表决策，形成发布承诺。
# 参数只改变图表处置，其他前置条件保持可比较。
def _write_publication_card(
    paths: ModusPaths,
    *,
    visual_status: str = "authored",
    visual_kind: str = "mermaid",
    visual_target: str = "modus/knowledge/domain/core/references/state_machine.md",
    visual_reason: str | None = None,
) -> None:
    reason = f"\n            reason: {visual_reason}" if visual_reason is not None else ""
    _write(
        paths.scope_confirmation_path,
        f"""---
modus:
  authoring:
    schemaVersion: 2
    executionMode: serial
    domains:
      core:
        status: reviewed
        outcome: changed
        coverage:
          status: audited
          mode: machine-context
          selector: "capability:core"
        modules:
          runner:
            status: reviewed
            evidence:
              status: ready
              mode: machine-context
              requestedScope: module:core/runner
              selector: "capability:runner"
        visuals:
          - id: request-flow
            kind: {visual_kind}
            target: {visual_target}
            status: {visual_status}{reason}
            readerQuestion: How does a request reach its visible result?
            mechanism: A request crosses the runner boundary.
---

# Scope confirmation
""",
    )


# clean 表示客观完整性通过，不代表正文质量或业务结论获得认证。
# 完整字典断言保护公开线协议的字段、类型和空结果表示。
def test_clean_means_integrity_only_and_preserves_wire_shape(tmp_path: Path) -> None:
    _clean_project(tmp_path)
    result = run_verify_knowledge(str(tmp_path))

    assert result == {
        "schemaVersion": 1,
        "status": "clean",
        "scope": {"domain": None},
        "counts": {},
        "findings": [],
        "checkedDocuments": 5,
    }


# 中文、英文和其他语言都可使用自然标题结构。
# 保留合法元数据，只替换正文，隔离标题策略与身份契约。
@pytest.mark.parametrize(
    "body",
    [
        "# 中文标题\n\n## 任意自然结构\n\n按项目事实组织。\n",
        "# English title\n\n## Natural project structure\n\nUse project facts.\n",
        "# Título\n\n## Estructura propia\n\nContenido verificado.\n",
    ],
)
def test_localized_and_custom_headings_are_not_gates(tmp_path: Path, body: str) -> None:
    paths = _clean_project(tmp_path)
    paths.architecture_overview.write_text(body, encoding="utf-8")
    paths.domain_skill("core").write_text(body, encoding="utf-8")
    module = paths.module("core", "runner")
    # 复用相同元数据，确保多语言测试只改变叙事而不改变模块身份。
    frontmatter = _module_body().split("---\n", 2)[1]
    module.write_text(f"---\n{frontmatter}---\n\n{body}", encoding="utf-8")

    assert run_verify_knowledge(str(tmp_path))["status"] == "clean"


# 同一文档注入缺失链接、坏锚点、本机路径、合成令牌与未闭合围栏。
# 验证器应汇总所有客观损坏，不能在首个问题后停止。
# 令牌是测试专用字母序列，用于验证检测边界而非真实凭据。
def test_objective_markdown_link_portability_and_secret_damage_fails(
    tmp_path: Path,
) -> None:
    paths = _clean_project(tmp_path)
    api = paths.domain_references("core") / "api.md"
    api.write_text(
        f"""# API

[missing](missing.md#nowhere)

[bad anchor](object.md#absent)

Local path: /Users/example/private/source.py

{synthetic_source_assignment()}

```mermaid
A --> B
""",
        encoding="utf-8",
    )

    assert {
        "link-target-missing",
        "link-anchor-missing",
        "absolute-local-path",
        "sensitive-value",
        "markdown-fence-unclosed",
    } <= _codes(run_verify_knowledge(str(tmp_path), domain="core"))


# 旧式引用与真实行号漂移同时出现，应分别给出对应发现。
# 源码符号仍存在，因此不能把位置变化误判为符号删除。
def test_source_reference_syntax_and_anchor_drift_are_checked(tmp_path: Path) -> None:
    paths = _clean_project(tmp_path)
    module = paths.module("core", "runner")
    module.write_text(
        module.read_text(encoding="utf-8") + "\nLegacy `src/app.py:1`.\n",
        encoding="utf-8",
    )
    (tmp_path / "src/app.py").write_text("# moved\ndef run():\n    return 'ok'\n", encoding="utf-8")

    codes = _codes(run_verify_knowledge(str(tmp_path), domain="core"))
    assert "source-ref-noncanonical" in codes
    # 漂移保持可机械修复的分类，后续维护无需重建模块身份。
    assert "line_drift" in codes


# 分别构造父目录逃逸与目录链接，验证两类读取边界。
# 链接能力不可用的平台显式跳过该场景，不伪造通过。
# 外部文件实际存在，使拒绝理由确实来自边界而非目标缺失。
def test_source_references_cannot_escape_or_cross_symlinks(tmp_path: Path) -> None:
    paths = _clean_project(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("def leaked():\n    pass\n", encoding="utf-8")
    real_source = tmp_path / "real-src/linked.py"
    _write(real_source, "def linked():\n    pass\n")
    link = tmp_path / "linked-src"
    try:
        link.symlink_to(real_source.parent, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")
    module = paths.module("core", "runner")
    module.write_text(
        module.read_text(encoding="utf-8")
        + f"\nEscape `src/../../{outside.name}#L1` (`leaked`).\n"
        + "Unsafe `linked-src/linked.py#L1` (`linked`).\n",
        encoding="utf-8",
    )

    codes = _codes(run_verify_knowledge(str(tmp_path), domain="core"))
    assert {"source-ref-outside-repository", "source-ref-unsafe"} <= codes


# JSON CLI 返回显式领域范围，验证期间所有文件字节保持不变。
# 不存在的领域返回发现而非扩大扫描到整个项目。
def test_domain_scope_is_validated_and_cli_is_read_only(tmp_path: Path) -> None:
    _clean_project(tmp_path)
    before = sorted(
        (path.relative_to(tmp_path).as_posix(), path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    result = runner.invoke(
        app,
        ["knowledge", "verify", "--root", str(tmp_path), "--domain", "core", "--json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["scope"] == {"domain": "core"}
    after = sorted(
        (path.relative_to(tmp_path).as_posix(), path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    # 逐字节快照覆盖所有文档，防止只读校验悄悄修复或重排正文。
    assert after == before

    missing = run_verify_knowledge(str(tmp_path), domain="missing")
    assert missing["status"] == "findings"
    assert "domain-missing" in _codes(missing)


# 执行卡声明了创作义务，但业务种子、源码锚点和图表尚未完成。
# 发布模式必须同时报告这些缺口，不能凭 reviewed 标签直接放行。
def test_publication_fails_closed_on_unfulfilled_authoring_commitments(
    tmp_path: Path,
) -> None:
    paths = _clean_project(tmp_path)
    paths.module("core", "runner").write_text("# Runner\n", encoding="utf-8")
    _write_publication_card(paths, visual_status="planned")

    codes = _codes(run_verify_knowledge(str(tmp_path), publication=True))

    assert {
        "domain-business-seed-missing",
        "module-source-anchor-missing",
        "authoring-visual-incomplete",
    } <= codes


# 先建立合法图表豁免，再分别破坏卡版本、覆盖证据和执行模式。
# 每种失败应对应稳定诊断，避免升级要求被普通未完成状态掩盖。
# 豁免说明来自读者需要，不强制每个模块都画图。
def test_publication_requires_supported_execution_evidence_and_coverage(tmp_path: Path) -> None:
    paths = _clean_project(tmp_path)
    # 补齐业务种子，避免其他缺口干扰执行卡协议的独立验证。
    seed_domain_business(tmp_path, ["core"])
    _write_publication_card(
        paths,
        visual_status="waived",
        visual_kind="none",
        visual_reason="No relationship benefits from a visual explanation.",
    )
    # 每次变异同一执行卡，使结果不能由多份竞争性承诺解释。
    card = paths.scope_confirmation_path
    text = card.read_text(encoding="utf-8")
    assert run_verify_knowledge(str(tmp_path), publication=True)["status"] == "clean"
    assert card.read_text(encoding="utf-8") == text
    card.write_text(text.replace("schemaVersion: 2", "schemaVersion: 1"), encoding="utf-8")

    assert "authoring-card-upgrade-required" in _codes(
        run_verify_knowledge(str(tmp_path), publication=True)
    )

    card.write_text(
        text.replace("status: audited", "status: pending", 1).replace(
            "status: ready", "status: pending", 1
        ),
        encoding="utf-8",
    )
    codes = _codes(run_verify_knowledge(str(tmp_path), publication=True))
    assert {"authoring-coverage-incomplete", "authoring-module-evidence-incomplete"} <= codes

    card.write_text(
        text.replace("executionMode: serial", "executionMode: automatic"),
        encoding="utf-8",
    )
    assert "authoring-execution-mode-invalid" in _codes(
        run_verify_knowledge(str(tmp_path), publication=True)
    )


@pytest.mark.parametrize(
    "selector",
    [
        "not-a-selector",
        "path:modus/knowledge/domain/core",
        "path:modus/.cache/init-analysis",
        "path:../outside",
        "path:.//",
        "candidate: ",
    ],
)
def test_publication_rejects_invalid_source_selectors(selector: str) -> None:
    from modus.knowledge_verification.authoring_card import (
        verify_domain_coverage,
        verify_module_execution,
    )

    coverage = verify_domain_coverage(
        "core", {"status": "audited", "mode": "machine-context", "selector": selector}
    )
    module = verify_module_execution(
        "core",
        "runner",
        {
            "status": "reviewed",
            "evidence": {
                "status": "ready",
                "mode": "machine-context",
                "requestedScope": "module:core/runner",
                "selector": selector,
            },
        },
    )[1]
    assert {item.code for item in coverage} == {"authoring-coverage-selector-invalid"}
    assert {item.code for item in module} == {"authoring-module-selector-invalid"}


def test_publication_accepts_explicit_queries_and_source_fallback() -> None:
    from modus.knowledge_verification.authoring_card import (
        verify_domain_coverage,
        verify_module_execution,
    )

    assert not verify_domain_coverage(
        "core",
        {
            "status": "audited",
            "mode": "machine-context",
            "selector": ["candidate:core", "path:src/runner.py"],
        },
    )
    assert not verify_module_execution(
        "core",
        "runner",
        {
            "status": "reviewed",
            "evidence": {
                "status": "ready",
                "mode": "source-fallback",
                "requestedScope": "module:core/runner",
                "selector": "src/runner.py",
                "reason": "source changed",
            },
        },
    )[1]


def test_retrieval_and_verifier_share_real_markdown_targets(tmp_path: Path) -> None:
    from modus.knowledge_verification.markdown_integrity import verify_links
    from modus.retrieval.stages.documents import scan_documents

    target = tmp_path / "modus/knowledge/domain/core/references/rule.md"
    _write(
        target,
        "# 恢复\n## 失败恢复\n第一处。\n## 失败恢复\n第二处。\n"
        '```md\n<a id="fake"></a>\n{{item:example}}\n## 失败恢复\n```\n'
        '<a id="real"></a>\n{{item:actual}}\n',
    )
    source = target.with_name("index.md")
    _write(
        source,
        "[第二处](rule.md#失败恢复-1)\n[真实](rule.md#real)\n"
        "[条目](rule.md#item-actual)\n[示例](rule.md#fake)\n"
        "[示例条目](rule.md#item-example)\n",
    )
    paths = ModusPaths.for_root(tmp_path)
    findings = verify_links(paths, (source,))
    assert {item.context["link"] for item in findings} == {"rule.md#fake", "rule.md#item-example"}
    sections = scan_documents(paths, [target]).sections
    anchors = {anchor for section in sections for anchor in section["anchors"]}
    assert {"失败恢复", "失败恢复-1", "real", "item-actual"} <= anchors
    assert not {"失败恢复-2", "fake", "item-example"} & anchors


def test_workspace_publication_uses_root_card_and_isolates_same_named_domains(
    tmp_path: Path,
) -> None:
    import subprocess

    import yaml

    from modus.config import ModusConfig
    from modus.skillmd import split_frontmatter
    from modus.workspace import normalize_members

    plans = {}
    for name in ("orders", "payments"):
        root = tmp_path / name
        paths = _clean_project(root)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        seed_domain_business(root, ["core"])
        _write_publication_card(
            paths, visual_status="waived", visual_kind="none", visual_reason="No visual needed."
        )
        meta, _ = split_frontmatter(paths.scope_confirmation_path.read_text())
        plans[name] = {"path": name, "domains": meta["modus"]["authoring"]["domains"]}
        paths.scope_confirmation_path.unlink()
    plans["payments"]["domains"]["core"]["modules"]["runner"]["status"] = "pending"
    outer = ModusPaths.for_root(tmp_path)
    ModusConfig(
        kind="workspace", workspace={"members": normalize_members(tmp_path, ["orders", "payments"])}
    ).write(outer)

    def save_card() -> None:
        _write(
            outer.scope_confirmation_path,
            "---\n"
            + yaml.safe_dump(
                {
                    "modus": {
                        "authoring": {
                            "schemaVersion": 2,
                            "executionMode": "serial",
                            "members": plans,
                        }
                    }
                },
                allow_unicode=True,
            )
            + "---\n",
        )

    save_card()
    assert "authoring-member-required" in _codes(
        run_verify_knowledge(str(tmp_path), publication=True)
    )
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    run = runner.invoke(
        app,
        [
            "knowledge",
            "verify",
            "--root",
            str(tmp_path),
            "--member",
            "orders",
            "--publication",
            "--json",
        ],
    )
    assert run.exit_code == 0, run.output
    assert json.loads(run.output)["scope"] == {
        "domain": None,
        "member": "orders",
        "memberPath": "orders",
    }
    payment = run_verify_knowledge(str(tmp_path), publication=True, member="payments")
    assert "authoring-module-incomplete" in _codes(payment)
    assert "authoring-card-unavailable" not in _codes(payment)
    assert {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    } == before
    with pytest.raises(ValueError, match="未配置"):
        run_verify_knowledge(str(tmp_path), publication=True, member="../orders")
    with pytest.raises(ValueError, match="仅用于"):
        run_verify_knowledge(str(tmp_path), member="orders")
    # 旧根卡未记录成员归属时，报告真实缺项，不能把单仓计划套到所选成员。
    _write_publication_card(
        outer, visual_status="waived", visual_kind="none", visual_reason="No visual needed."
    )
    codes = _codes(run_verify_knowledge(str(tmp_path), publication=True, member="orders"))
    assert "authoring-member-invalid" in codes
    assert "authoring-card-upgrade-required" not in codes
    plans["orders"]["path"] = "payments"
    save_card()
    assert "authoring-member-invalid" in _codes(
        run_verify_knowledge(str(tmp_path), publication=True, member="orders")
    )
    plans["orders"]["path"] = "orders"
    save_card()
    (tmp_path / "orders").rename(tmp_path / "old-orders")
    (tmp_path / "orders").symlink_to(tmp_path / "old-orders", target_is_directory=True)
    with pytest.raises(ValueError, match="符号链接"):
        run_verify_knowledge(str(tmp_path), publication=True, member="orders")
