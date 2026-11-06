"""Golden behavior slices for the deterministic N4 composer."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from modus.machine.capability import EffectKind, PathStatus, compose
from modus.machine.capability.composition_model import Seed
from modus.machine.capability.seed_selection import select_seeds
from modus.machine.corpus import freeze
from modus.machine.facts import observe
from modus.machine.resolution import resolve
from modus.machine.states import Resolution


# 关闭编译器以隔离 N4 组合行为，测试不依赖外部工具链。
# 三个前序阶段仍使用真实实现，确保输入协议能够连接。
def _compose(root: Path):
    corpus = freeze(root, compiler_mode="off")
    with corpus.activate():
        return compose(resolve(observe(corpus))).model


def test_container_routes_and_client_calls_do_not_become_service_seeds(tmp_path: Path) -> None:
    (tmp_path / "Controller.java").write_text(
        """@RequestMapping("/orders")
class Controller {
 @PostMapping("/create")
 void create() { repository.save(order); }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "client.ts").write_text(
        'export async function load() { return fetch("/orders"); }', encoding="utf-8"
    )
    model = _compose(tmp_path)
    assert all(
        row.entry["kind"] in {"method", "function", "constructor", "handler"}
        for row in model.slices
    )
    clients = [row for row in model.slices if str(row.entry["symbol"]).endswith("load")]
    assert clients and all(row.trigger["kind"] == "public-export" for row in clients)
    assert sum(row.trigger["kind"] == "external-http" for row in model.slices) == 1


def test_every_seed_has_an_inventory_entry_when_expansion_is_budgeted(tmp_path: Path) -> None:
    from modus.machine.capability.composer import compose_capabilities

    (tmp_path / "api.ts").write_text(
        "export function first() { return 1; }\nexport function second() { return 2; }\n",
        encoding="utf-8",
    )
    corpus = freeze(tmp_path, compiler_mode="off")
    with corpus.activate():
        model = compose_capabilities(resolve(observe(corpus)), max_slices=1)
    assert model.seed_count == 2 and len(model.slices) == 1
    assert len(model.seed_inventory) == model.seed_count
    assert {
        row["entryId"] for row in model.seed_inventory if row["expansionStatus"] == "not-expanded"
    } == set(model.uncovered_seeds)
    assert all(
        row["reasonCode"] == "machine.capability.slice-budget"
        for row in model.seed_inventory
        if row["expansionStatus"] == "not-expanded"
    )


# 验证从显式 HTTP 入口到写入终点的有界能力切片。
# 结构证据只能达到启发式精度，关闭编译器的原因必须随结果保留。
# 同时检查线协议 schema，防止内部正确但交付格式失效。
def test_http_entry_is_compressed_into_one_entry_to_write_slice(tmp_path: Path) -> None:
    (tmp_path / "OrderController.java").write_text(
        """class OrderController {
 @OpenApiPostMapping(apiName = "Create", apiUrl = "/orders")
 public void create() { persist(); }
 private void persist() { repository.save(order); }
}
""",
        encoding="utf-8",
    )

    model = _compose(tmp_path)

    assert model.seed_count == 1
    assert model.uncovered_seeds == ()
    capability = model.slices[0]
    assert capability.entry_signature == "POST /orders"
    assert capability.capability_id.startswith("cap-")
    assert capability.evidence_tier == "T2"
    assert capability.degradation_reasons == ("machine.facts.compiler-disabled",)
    assert capability.receipts[0].completeness == "partial"
    assert capability.terminal_effects[0].kind is EffectKind.DATA_WRITE
    assert capability.representative_paths[0].status is PathStatus.TERMINATED
    assert [step.symbol for step in capability.representative_paths[0].steps] == [
        "OrderController.create",
        "OrderController.persist",
    ]
    assert capability.resolution is Resolution.HEURISTIC
    # 整体解析等级必须与组成证据一致，不能仅修改展示字段。
    assert capability.resolution_is_consistent()
    # 回执计数只描述实际访问节点与终点，不把整个文件图算作覆盖。
    assert capability.receipts[0].counts == {
        "visitedNodes": 2,
        "visitedEdges": 1,
        "terminalEffects": 1,
    }
    schema = json.loads(
        (
            Path(__file__).parents[2] / "schemas" / "machine" / "capability-slice.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(capability.to_dict())


# 空行插入只改变源码位置，不应改变业务能力身份。
# 位置仍须更新，稳定身份不能掩盖陈旧锚点。
def test_capability_identity_survives_line_drift(tmp_path: Path) -> None:
    source = tmp_path / "OrderController.java"
    body = """class OrderController {
 @OpenApiPostMapping(apiName = "Create", apiUrl = "/orders")
 public void create() { repository.save(order); }
}
"""
    source.write_text(body, encoding="utf-8")
    first = _compose(tmp_path).slices[0]
    source.write_text("\n\n" + body, encoding="utf-8")
    second = _compose(tmp_path).slices[0]

    assert second.capability_id == first.capability_id
    # 精确检查位移量，区分保留身份与错误复用旧位置缓存。
    assert second.entry["location"]["startLine"] == first.entry["location"]["startLine"] + 2


# 生产与测试文件都声明 HTTP 入口，刻意让名称模式同样匹配。
# 只有运行时源码可以成为能力种子，测试样例不能扩大业务范围。
def test_test_sources_do_not_become_capability_seeds(tmp_path: Path) -> None:
    runtime = tmp_path / "src/main/java/acme/OrderController.java"
    runtime.parent.mkdir(parents=True)
    runtime.write_text(
        """class OrderController {
 @OpenApiPostMapping(apiName = "Create", apiUrl = "/orders")
 public void create() { repository.save(order); }
}
""",
        encoding="utf-8",
    )
    test_source = tmp_path / "src/test/java/acme/OrderControllerTest.java"
    test_source.parent.mkdir(parents=True)
    test_source.write_text(
        """class OrderControllerTest {
 @OpenApiPostMapping(apiName = "Fixture", apiUrl = "/fixture")
 public void fixture() { repository.save(order); }
}
""",
        encoding="utf-8",
    )

    model = _compose(tmp_path)

    assert model.seed_count == 1
    assert [item.entry_signature for item in model.slices] == ["POST /orders"]


# 预算不足时优先选择显式触发入口，而非按普通导出数量占满配额。
# 两个入口位于不同目录，防止目录顺序偏置选择结果。
def test_slice_budget_prioritizes_explicit_triggers_across_directories() -> None:
    seeds = tuple(
        Seed(
            f"entry-{index}",
            f"signature-{index}",
            {"kind": "public-export"},
            Resolution.EXACT,
        )
        for index in range(8)
    ) + (
        Seed("entry-http-a", "GET /a", {"kind": "external-http"}, Resolution.EXACT),
        Seed("entry-http-z", "GET /z", {"kind": "external-http"}, Resolution.EXACT),
    )
    entries = {
        seed.entry_id: {
            "location": {
                "path": (
                    "src/a/Controller.java"
                    if seed.entry_id == "entry-http-a"
                    else "src/z/Controller.java"
                    if seed.entry_id == "entry-http-z"
                    else "src/export/Public.java"
                ),
                "startLine": index + 1,
            }
        }
        for index, seed in enumerate(seeds)
    }

    # 把预算设为仅够两个显式入口，使优先级策略成为可观察结果。
    selected = select_seeds(seeds, entries, max_slices=2)

    assert {seed.entry_id for seed in selected} == {"entry-http-a", "entry-http-z"}
