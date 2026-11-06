"""从公开消费入口验证联合定位、条目交付与两类知识的取证边界。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from modus.cli import app
from modus.commands.context_cmd import resolve
from modus.retrieval.budget import RetrievalBudget
from modus.retrieval.delivery import limit_result


def _write(root: Path, relative: str, text: str) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


TEAM = "modus/knowledge/constraint/team-standard.md"
TOPIC = "modus/knowledge/constraint/team-standard/concurrency.md"
MODULE = "modus/knowledge/domain/orders/references/modules/reservation.md"


@pytest.mark.parametrize("long_entry", [False, True])
def test_cli_delivers_one_complete_rule_entry_and_honest_continuation(
    tmp_path: Path, long_entry: bool
) -> None:
    padding = "详细说明。" * 300 if long_entry else ""
    _write(
        tmp_path,
        TEAM,
        "# 团队规范\n## 批量查询\n### 有界执行\n"
        '<a id="item-bounded"></a>\n性质: 通用建议\n'
        "适用: Java 8，服务端共享 executor。\n"
        f"#### 示例\n调用 reserveOrders。{padding}\n"
        "#### 例外\nreserveOrders 不拥有共享池，不能关闭共享池。\n"
        "### 页面请求\n独立浏览器行为。\n",
    )
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    run = CliRunner().invoke(
        app,
        [
            "context",
            "resolve",
            "reserveOrders",
            "--scope",
            "project-read",
            "--purpose",
            "change",
            "--root",
            str(tmp_path),
        ],
    )
    assert run.exit_code == 0, run.output
    result = json.loads(run.output)
    refs = [
        row for row in result["evidence"] if row["path"] == TEAM and row["heading"] == "有界执行"
    ]
    assert len(refs) == 1
    ref = refs[0]
    assert "Java 8" in ref["excerpt"] and "通用建议" in ref["excerpt"]
    assert "独立浏览器行为" not in ref["excerpt"]
    assert ref["truncated"] is long_entry
    assert ref["id"] in {row["id"] for row in result["applicableConstraints"]}
    assert ref["id"] not in {row["id"] for row in result["constraintCandidates"]}
    assert (
        sum(
            bool(set(row.get("sectionIds", [])) & set(ref["sectionIds"]))
            for row in result["evidence"]
        )
        == 1
    )
    if long_entry:
        assert ref["readTarget"] in result["continuation"]["readTargets"]
        assert result["continuation"]["available"]
    else:
        assert "不能关闭共享池" in ref["excerpt"]
    assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == before


@pytest.mark.parametrize("fragment", ["item-bounded", "%E6%9C%89%E7%95%8C%E6%89%A7%E8%A1%8C"])
def test_scenario_link_delivers_topic_without_shared_query_words(
    tmp_path: Path, fragment: str
) -> None:
    _write(tmp_path, "modus/knowledge/constraint/global-standard.md", "# 全局\n遵循明确要求。\n")
    _write(
        tmp_path,
        TEAM,
        f"# 团队规范\n## 场景导航\n[reserveOrders](team-standard/concurrency.md#{fragment})\n",
    )
    _write(
        tmp_path,
        TOPIC,
        '# 并发\n## 有界执行\n<a id="item-bounded"></a>\n性质: 通用建议\n适用: Java 8。\n'
        "### 示例\n使用已注入的 Executor。\n### 例外\n不得关闭共享池。\n"
        "## 无关条目\n仅用于浏览器。\n",
    )
    result = resolve(str(tmp_path), "reserveOrders", scope="project-read", purpose="change")
    refs = [row for row in result["evidence"] if row["path"] == TOPIC]
    assert len(refs) == 1
    assert "Java 8" in refs[0]["excerpt"] and "不得关闭共享池" in refs[0]["excerpt"]
    assert "仅用于浏览器" not in refs[0]["excerpt"]
    assert refs[0]["authority"] == "document-declaration"
    assert TOPIC in result["freshness"]["knowledgeSelection"]["selectedFiles"]


def test_domain_scenario_links_to_constraint_and_navigation_stops_after_one_hop(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        MODULE,
        "# 预订\n## reserveOrders\n按[有界执行](../../../../constraint/team-standard/concurrency.md#item-bounded)。\n",
    )
    _write(
        tmp_path,
        TOPIC,
        '# 线程池\n## 所有权\n<a id="item-bounded"></a>\n不得关闭共享池。\n'
        "另见[实现细节](second.md#details)。\n",
    )
    _write(tmp_path, "modus/knowledge/constraint/global-standard.md", "# 全局\n有效规范。\n")
    _write(tmp_path, TEAM, "# 团队\n有效规范。\n")
    second = "modus/knowledge/constraint/team-standard/second.md"
    _write(tmp_path, second, "# Details\n这里不应因为链式链接自动读取。\n")
    result = resolve(str(tmp_path), "reserveOrders", scope="project-read", purpose="change")
    assert any(
        row["path"] == TOPIC and "不得关闭共享池" in row["excerpt"] for row in result["evidence"]
    )
    assert second not in result["freshness"]["knowledgeSelection"]["selectedFiles"]


def test_navigation_ignores_examples_planned_sections_and_symlink_aliases(tmp_path: Path) -> None:
    _write(
        tmp_path,
        TEAM,
        "# 团队\n## 场景\n```md\n[reserveOrders](team-standard/concurrency.md#item-bounded)\n```\n"
        "[reserveOrders](team-standard/alias.md#item-bounded)\n"
        "## 待确认\n状态: planned\n[reserveOrders](team-standard/concurrency.md#item-bounded)\n",
    )
    target = _write(tmp_path, TOPIC, '# 并发\n## 所有权\n<a id="item-bounded"></a>\n共享池。\n')
    target.with_name("alias.md").symlink_to(target)
    result = resolve(str(tmp_path), "reserveOrders", scope="project-read")
    assert not result["freshness"]["knowledgeSelection"]["navigationTargets"]
    assert any(gap.get("reason") == "unsafe-file" for gap in result["groundingGaps"])


def test_missing_fragment_and_link_limit_are_visible_gaps(tmp_path: Path) -> None:
    _write(
        tmp_path,
        TEAM,
        "# 团队\n## 导航\n"
        + "\n".join(f"[reserveOrders {i}](team-standard/topic-{i}.md#missing)" for i in range(12))
        + "\n",
    )
    for i in range(12):
        _write(
            tmp_path,
            f"modus/knowledge/constraint/team-standard/topic-{i}.md",
            "# 专题\n有效正文。\n",
        )
    result = resolve(str(tmp_path), "reserveOrders", scope="project-read")
    reasons = {gap.get("reason") for gap in result["groundingGaps"]}
    assert {"unresolved-target", "navigation-limit"} <= reasons
    assert not result["coverage"]["complete"]
    assert len(result["freshness"]["knowledgeSelection"]["navigationTargets"]) <= 8


def test_change_purpose_preserves_debug_and_separates_knowledge_needs(tmp_path: Path) -> None:
    _write(tmp_path, TEAM, "# 团队\n## refund\n使用现有能力。\n")
    _write(tmp_path, "refund.py", "def refund():\n    return 'pending'\n")
    result = resolve(str(tmp_path), "修复 refund 异常", scope="project-read", purpose="change")
    assert result["query"]["intent"] == "debug"
    coverage = {row["need"]: row["status"] for row in result["coverage"]["items"]}
    assert coverage["engineering-constraint"] == "covered"
    assert coverage["domain-knowledge"] == "missing"
    _write(tmp_path, MODULE, "# refund\n## 恢复\n恢复继续未完成操作，不重做已完成副作用。\n")
    result = resolve(str(tmp_path), "修复 refund 异常", scope="project-read", purpose="change")
    coverage = {row["need"]: row["status"] for row in result["coverage"]["items"]}
    assert coverage["domain-knowledge"] == coverage["engineering-constraint"] == "covered"
    assert result["coverage"]["semantics"] == "retrieval-hint-only"
    limit_result(result, evidence_limit=1)
    coverage = {row["need"]: row["status"] for row in result["coverage"]["items"]}
    assert (
        coverage["domain-knowledge"] != "covered" or coverage["engineering-constraint"] != "covered"
    )
    assert not result["coverage"]["complete"]


def test_source_anchor_truncation_has_exact_read_target(tmp_path: Path) -> None:
    source = "def reserveOrders():\n" + "    # business detail\n" * 80 + "    return 1\n"
    _write(tmp_path, "orders.py", source)
    _write(
        tmp_path,
        MODULE,
        "---\nanchors:\n  locations:\n    - path: orders.py\n      symbol: reserveOrders\n      startLine: 1\n      endLine: 82\n---\n# reserveOrders\n## 行为\n保留原始业务结果。\n",
    )
    result = resolve(
        str(tmp_path),
        "reserveOrders",
        scope="project-read",
        budget=RetrievalBudget.start(3000, 5000),
    )
    ref = next(row for row in result["evidence"] if row["path"] == "orders.py")
    assert ref["truncated"]
    assert ref["readTarget"] == {"path": "orders.py", "lineStart": 1, "lineEnd": 82}
    assert ref["readTarget"] in result["continuation"]["readTargets"]
    assert len(result["contextMarkdown"]) <= 5000


def test_explicit_source_path_finds_domain_without_business_words(tmp_path: Path) -> None:
    _write(tmp_path, "orders.py", "def reserveOrders():\n    return 1\n")
    _write(
        tmp_path,
        MODULE,
        "---\nanchors:\n  locations:\n    - path: orders.py\n      symbol: reserveOrders\n"
        "      startLine: 1\n      endLine: 2\n---\n# 预订\n## 业务行为\n保留原始业务结果。\n",
    )
    result = resolve(
        str(tmp_path),
        "调整实现",
        scope="project-read",
        explicit_paths=["orders.py"],
        purpose="change",
    )
    assert result["route"]["modules"] == ["orders/reservation"]
    assert any(
        row["path"] == MODULE and "保留原始业务结果" in row["excerpt"] for row in result["evidence"]
    )
    assert result["sourceFiles"] == ["orders.py"]


def test_long_rule_metadata_preview_does_not_lose_late_match(tmp_path: Path) -> None:
    _write(
        tmp_path,
        TEAM,
        '# 团队规范\n## 执行\n<a id="item-owner"></a>\n性质: 明确约束\n适用: 共享资源。\n'
        + "".join(f"### 说明 {i}\n保留调用者所有权。\n" for i in range(40))
        + "### 最后一步\nreserveOrders 不得关闭共享池。\n",
    )
    result = resolve(str(tmp_path), "reserveOrders", scope="project-read")
    refs = [row for row in result["applicableConstraints"] if row["heading"] == "执行"]
    assert len(refs) == 1 and refs[0]["sectionIdsTotal"] > 32
    assert refs[0]["id"] not in {row["id"] for row in result["constraintCandidates"]}


def test_navigation_reading_keeps_original_byte_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modus.retrieval import index

    _write(tmp_path, "modus/knowledge/constraint/global-standard.md", "# 全局\n有效规范。\n")
    _write(tmp_path, TEAM, "# 团队\n[reserveOrders](team-standard/concurrency.md#item-bounded)\n")
    _write(tmp_path, TOPIC, '# 专题\n<a id="item-bounded"></a>\n' + "有界执行。" * 1000)
    monkeypatch.setattr(index, "MAX_SCAN_BYTES", 200)
    result = resolve(str(tmp_path), "reserveOrders", scope="project-read")
    assert any(gap.get("reason") == "scan-byte-budget" for gap in result["groundingGaps"])
    assert not any(row["path"] == TOPIC for row in result["evidence"])
    assert any(row["path"] == TEAM for row in result["evidence"])


def test_broad_document_navigation_does_not_hide_precise_answer(tmp_path: Path) -> None:
    _write(tmp_path, "orders.py", "def reserveOrders():\n    return 1\n")
    _write(
        tmp_path,
        "modus/knowledge/domain/orders/SKILL.md",
        "# 订单\n## 导航\n[订单通用对象](references/object.md)\n",
    )
    _write(
        tmp_path,
        "modus/knowledge/domain/orders/references/object.md",
        "# 订单对象\n" + "".join(f"## 对象 {i}\n记录订单状态。\n" for i in range(20)),
    )
    _write(
        tmp_path,
        MODULE,
        "---\nanchors:\n  locations:\n    - path: orders.py\n      symbol: reserveOrders\n"
        "      startLine: 1\n      endLine: 2\n---\n# 预订\n## 内存清理时机\n"
        "只有显式清理才移除记录，查询不会触发清理。\n",
    )
    result = resolve(
        str(tmp_path), "订单 内存清理时机", scope="project-read", explicit_paths=["orders.py"]
    )
    assert any("查询不会触发清理" in row["excerpt"] for row in result["evidence"])


@pytest.mark.parametrize("heading", ["例外", "例外场景", "Exception scenarios"])
@pytest.mark.parametrize("marker", ['<a id="item-bounded"></a>', "{{item:bounded}}"])
def test_nested_exception_keeps_explicit_rule_conditions(
    tmp_path: Path, heading: str, marker: str
) -> None:
    _write(
        tmp_path,
        TOPIC,
        f"# 并发\n## 有界执行\n{marker}\n性质: 通用建议\n适用: Java 8 服务端。\n"
        f"### {heading}\n#### 共享池\nreserveOrders 不得关闭借用的线程池。\n"
        "## 浏览器\n只适用于页面。\n",
    )
    result = resolve(str(tmp_path), "reserveOrders", scope="project-read", purpose="change")
    ref = next(row for row in result["evidence"] if row["path"] == TOPIC)
    assert "通用建议" in ref["excerpt"] and "Java 8" in ref["excerpt"]
    assert "不得关闭" in ref["excerpt"] and "只适用于页面" not in ref["excerpt"]
    assert ref["readTarget"] == {"path": TOPIC, "lineStart": 2, "lineEnd": 8}
    assert not ref["truncated"]
