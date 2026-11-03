"""Authored retrieval keeps source boundaries and request budgets."""

from __future__ import annotations

import json
import time
from pathlib import Path, PureWindowsPath

import pytest

from modus.orchestrator import context_resolver, fallback
from modus.paths import ModusPaths
from modus.retrieval import runtime
from modus.retrieval.budget import RetrievalBudget
from modus.retrieval.delivery import EvidenceCollector
from modus.retrieval.index import scan_index
from modus.retrieval.query import analyze_query
from modus.scaffold.catalog import TemplateCatalog


# 构造完整导航链，测试检索时可以从架构入口路由到模块正文。
# 正文和元数据分开传入，便于独立测试缺失或损坏元数据。
def _knowledge(root: Path, body: str, frontmatter: str = "") -> tuple[ModusPaths, Path]:
    paths = ModusPaths.for_root(root)
    module = paths.domain("payments") / "references/modules/refund.md"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(frontmatter + body, encoding="utf-8")
    (paths.domain("payments") / "SKILL.md").write_text(
        "# Payments\nRefund settlement [Refund](references/modules/refund.md)\n", encoding="utf-8"
    )
    paths.architecture_overview.write_text(
        "# Architecture\nRefund settlement [Payments](domain/payments/SKILL.md)\n", encoding="utf-8"
    )
    return paths, module


# 当前模板不作为项目规则参与检索，人工填写后必须能被检索到。
@pytest.mark.parametrize("name", ["team-standard", "global-standard"])
def test_constraint_templates_enter_retrieval_only_after_authoring(
    tmp_path: Path, name: str
) -> None:
    paths = ModusPaths.for_root(tmp_path)
    relative = f"modus/knowledge/constraint/{name}.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    seed = TemplateCatalog().read(f"knowledge/constraint/{name}.md")
    target.write_text(seed, encoding="utf-8", newline="")

    index = scan_index(paths, kind="project")
    assert not any(row["path"] == relative for row in index["sections"])

    target.write_text(seed + "\n## 项目约束\n禁止自动覆盖人工内容。\n", encoding="utf-8")
    index = scan_index(paths, kind="project")
    assert any(row["path"] == relative for row in index["sections"])


@pytest.mark.parametrize(
    "filename",
    [
        "team-standard.md",
        "team-standard/concurrency.md",
        "team-standard/legacy/concurrency.md",
        "team-standard/api.md",
    ],
)
def test_team_example_retrieval_preserves_scope_and_declaration_authority(
    tmp_path: Path,
    filename: str,
) -> None:
    """示例续读带回平台、规则性质与例外，专题不能升级成人工强制政策。"""
    paths = ModusPaths.for_root(tmp_path)
    relative = f"modus/knowledge/constraint/{filename}"
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# 团队规范\n## 批量查询\n### 有界执行\n"
        '<a id="item-bounded"></a>\n性质: 通用建议\n状态: current\n'
        "适用: server/，Java 8，共享 executor；不适用于 UI。\n"
        "#### 示例\n使用已注入 Executor；get 接收剩余预算。\n"
        "#### 例外\ncancel 不保证中断任务；不能关闭共享池。\n"
        '### 页面请求\n<a id="item-ui"></a>\n只适用于浏览器。\n',
        encoding="utf-8",
    )
    index = scan_index(paths, kind="project")
    example = next(row for row in index["sections"] if row["heading"] == "示例")
    assert example["authority"] == "document-declaration"
    assert example["facet"] == "rule"
    entry = runtime._entry_refs(index, [example])[0]
    assert "Java 8" in entry["excerpt"] and "通用建议" in entry["excerpt"]
    assert "cancel 不保证中断" in entry["excerpt"]
    assert "只适用于浏览器" not in entry["excerpt"]


# 不同长度与字符的代码围栏都不应产生知识标题。
# 子条目交付需带回前提、失败和恢复说明，同时排除相邻独立操作。
def test_fences_are_not_headings_and_children_keep_entry_context(tmp_path: Path) -> None:
    paths, module = _knowledge(
        tmp_path,
        """# Payments
## 规则
### Refund settlement {{item:refund-settlement}}
Preconditions are business conditions.
````python
# not a heading
```
## also code
````
~~~text
### sample heading
~~~
#### Failure
Keep the refund pending if settlement fails.
#### Recovery
Retry using the original key.
### Other {{item:other}}
An independent operation.
""",
    )
    index = scan_index(paths, kind="project")
    records = [row for row in index["sections"] if row["path"] == paths.relative(module)]
    assert [row["heading"] for row in records] == [
        "Payments",
        "规则",
        "Refund settlement {{item:refund-settlement}}",
        "Failure",
        "Recovery",
        "Other {{item:other}}",
    ]
    failure = next(row for row in records if row["heading"] == "Failure")
    refund = records[2]
    assert failure["headingPath"] == [
        "Payments",
        "规则",
        "Refund settlement {{item:refund-settlement}}",
        "Failure",
    ]
    assert failure["itemIds"] == ["refund-settlement"]
    assert failure["facet"] == "rule"
    assert failure["entryRange"] == refund["entryRange"]
    assert failure["entryRange"]["lineEnd"] == records[-1]["lineStart"] - 1
    assert failure["layer"] == "narrative"
    # 人工正文的权威标签保持独立，不能被源码增强误改为编译器事实。
    assert failure["authority"] == "authored-projection"
    group = runtime._entry_refs(index, [failure])[0]
    assert "Preconditions" in group["excerpt"]
    assert "Failure" in group["excerpt"] and "Recovery" in group["excerpt"]
    assert "independent operation" not in group["excerpt"]
    # 续读范围与交付条目一致，不能指向更宽的整个章节。
    assert group["readTarget"] == {"path": paths.relative(module), **refund["entryRange"]}


# 有效知识锚点应直接定位源码，禁止再次进行全仓库搜索。
# 故障替身让多余扫描立即失败，验证的是路由行为而非耗时阈值。
def test_narrative_routes_before_source_and_valid_anchors_avoid_full_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "refund.py").write_text("def settle_refund():\n    return 'pending'\n")
    paths, _module = _knowledge(
        tmp_path,
        "# Refund\n## Settlement\nRefund settlement retains pending state.\n",
        "---\nmoduleId: payments/refund\nanchors:\n  locations:\n    - path: refund.py\n"
        "      symbol: settle_refund\n      startLine: 1\n      endLine: 2\n---\n",
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("full source scan should not run after a valid routed anchor")

    monkeypatch.setattr(fallback, "search", unexpected)
    result = context_resolver.resolve_context(
        str(paths.root), "refund settlement", scope="project-read"
    )
    assert any(row["path"] == "refund.py" for row in result["evidence"])
    assert result["route"]["modules"] == ["payments/refund"]


# 传入已过期共享预算，后续阶段不得重置起点或启动源码搜索。
# 结果仍需满足原输出字符上限并给出明确停止原因。
def test_expired_request_does_not_start_search_or_reset_its_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _knowledge(tmp_path, "# Refund\n## Settlement\nRefund settlement.\n")
    started = time.monotonic() - 1
    budget = RetrievalBudget(started, started + 0.1, 2000)
    monkeypatch.setattr(
        fallback, "search", lambda *args, **kwargs: pytest.fail("expired source search")
    )
    result = context_resolver.resolve_context(
        str(tmp_path), "refund", scope="project-read", budget=budget
    )
    assert result["retrieval"]["elapsedMs"] >= 1000
    assert result["retrieval"]["stopReason"] == "budget-exhausted"
    assert len(result["contextMarkdown"]) <= 2000


# 模拟解析完成后另一个来源追加超大证据，验证最终交付再次施加预算。
# 原先有效证据应保留，不能用整包清空来满足上限。
def test_oversized_added_evidence_is_trimmed_to_the_original_output_budget(
    tmp_path: Path,
) -> None:
    """Any evidence added after resolution still respects the output budget.

    ``limit_result`` is a generic delivery-budget enforcer; it has no
    knowledge of any particular evidence source (machine, source, narrative).
    """
    paths, _module = _knowledge(tmp_path, "# Refund\n## Settlement\nRefund settlement.\n")
    result = context_resolver.resolve_context(
        str(paths.root), "refund", scope="project-read", budget=RetrievalBudget.start(3000, 2500)
    )
    original = [row["id"] for row in result["evidence"]]
    result["evidence"].append(
        {
            "id": "oversized:test",
            "path": "oversized.txt",
            "sourceType": "current-source",
            "status": "current",
            "authority": "navigation",
            "excerpt": "x" * 2400,
        }
    )
    runtime.limit_result(result)
    assert len(result["contextMarkdown"]) <= 2500
    assert [row["id"] for row in result["evidence"]] == original


# 两个成员必须收到同一个预算对象，成员数量不能扩大总请求时限。
# 续读路径重新带上成员前缀，确保从工作区根能够直接定位。
@pytest.mark.parametrize("windows_paths", [False, True])
def test_workspace_members_share_deadline_and_continuation_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, windows_paths: bool
) -> None:
    from modus import workspace
    from modus.commands import context_cmd
    from modus.retrieval import pipeline

    if windows_paths:
        monkeypatch.setattr(pipeline, "Path", PureWindowsPath)

    for name in ("one", "two"):
        _knowledge(tmp_path / name, "# Refund\n## Settlement\nRefund settlement.\n")
    members = [{"id": name, "path": name} for name in ("one", "two")]
    monkeypatch.setattr(
        runtime,
        "select_workspace_members",
        lambda *args, **kwargs: (members, {"members": ["one", "two"]}),
    )
    actual = context_cmd.resolve
    observed: list[RetrievalBudget] = []

    def resolve(*args, **kwargs):
        observed.append(kwargs["budget"])
        return actual(*args, **kwargs)

    monkeypatch.setattr(context_cmd, "resolve", resolve)
    budget = RetrievalBudget.start(3000, 5000)
    result = workspace.resolve_context(tmp_path, "refund", scope="project-read", budget=budget)
    # 比较对象序列而非近似时间，直接验证跨成员预算传递。
    assert observed == [budget, budget]
    assert len(result["contextMarkdown"]) <= 5000
    evidence = [row for row in result["evidence"] if row.get("readTarget")]
    assert evidence and all(
        row["readTarget"]["path"].startswith(("one/", "two/")) for row in evidence
    )


# 链接被拒绝与元数据损坏都要可见，损坏元数据不应抹去可读正文。
def test_symlink_and_invalid_frontmatter_are_visible_diagnostics(tmp_path: Path) -> None:
    paths, module = _knowledge(
        tmp_path, "---\ninvalid: [\n---\n# Refund\nRefund body remains readable.\n"
    )
    module.with_name("link.md").symlink_to(module)
    index = scan_index(paths, kind="project")
    assert {row["reason"] for row in index["scanIssues"]} >= {"invalid-frontmatter", "unsafe-file"}
    assert any("Refund body" in row["text"] for row in index["sections"])


# 非列表和混合非法元素都应降为锚点缺口，不能使上下文请求抛异常。
@pytest.mark.parametrize("locations", ["400", "[400, bad]"])
def test_malformed_source_locations_are_diagnostics_not_exceptions(
    tmp_path: Path, locations: str
) -> None:
    paths, _module = _knowledge(
        tmp_path,
        "# Refund\nRefund settlement.\n",
        f"---\nanchors:\n  locations: {locations}\n---\n",
    )
    result = context_resolver.resolve_context(
        str(paths.root), "refund settlement", scope="project-read"
    )
    assert any(gap["type"] == "source-anchor" for gap in result["groundingGaps"])


# 大量锚点不仅占正文预算，也可能通过元数据放大 JSON 输出。
# 交付保留总数、截断标志和续读入口，避免静默遗漏造成完整性误解。
def test_four_hundred_anchors_do_not_escape_metadata_delivery_limits(tmp_path: Path) -> None:
    import yaml

    (tmp_path / "refund.py").write_text("def refund():\n    return 'pending'\n")
    anchor = {"path": "refund.py", "symbol": "refund", "startLine": 1, "endLine": 2}
    metadata = {
        "anchors": {"locations": [dict(anchor) for _ in range(400)]},
        "sources": ["large-source-description" * 400],
    }
    paths, _module = _knowledge(
        tmp_path, "# Refund\nRefund settlement.\n", "---\n" + yaml.safe_dump(metadata) + "---\n"
    )
    result = context_resolver.resolve_context(
        str(paths.root), "refund", scope="project-read", budget=RetrievalBudget.start(3000, 2000)
    )
    refs = [row for row in result["evidence"] if row.get("sourceLocationsTotal")]
    assert refs
    assert all(
        len(row["sourceLocations"]) <= 8
        and row["sourceLocationsTotal"] == 400
        and row["sourceLocationsTruncated"]
        for row in refs
    )
    assert all(
        row["provenanceTruncated"] and row["sourceLocationsReadTarget"]["lineStart"] == 1
        for row in refs
    )
    assert len(result["contextMarkdown"]) <= 2000
    # JSON has structural overhead; anchor count cannot grow its metadata without limit.
    assert len(json.dumps(result, ensure_ascii=False)) < 16000


# 未知目的不能静默采用默认策略，调用方应收到可操作的参数错误。
def test_query_rejects_an_unknown_purpose() -> None:
    with pytest.raises(ValueError, match="purpose 必须为 change"):
        analyze_query("inspect refund", purpose="unknown")


# 轮询合并让不同证据来源都有交付机会，重复身份只占一个名额。
# 预先添加的路由证据保留优先位置，整体仍遵守数量预算。
def test_evidence_delivery_is_fair_bounded_and_unique() -> None:
    collector = EvidenceCollector(limit=4)
    collector.add({"id": "router"})
    collector.drain_round_robin(
        [
            [{"id": "source"}, {"id": "source-2"}],
            [{"id": "rule"}, {"id": "rule-2"}],
            [{"id": "source"}],
        ]
    )

    assert [item["id"] for item in collector.items] == ["router", "source", "rule", "source-2"]
