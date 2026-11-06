"""Public Python and JSON contracts remain independently consumable.

Schema checks exercise real serialized values, and positional-construction
checks guard compatibility when selectors gain optional fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

import modus.machine as machine
from modus.machine.capability.contracts import CapabilitySlice
from modus.machine.packet.contracts import AuthoringContextPacket, TaskIntent
from modus.machine.states import Resolution
from modus.machine.store.contracts import (
    AnalysisIdentity,
    AnalysisReceipt,
    EntryEvidence,
    EvidencePage,
    Witness,
)

SCHEMA_ROOT = Path(__file__).parents[2] / "schemas" / "machine"
_DIGEST = "a" * 64


# 选择 schema 声明的验证器版本，既校验契约自身也校验实例。
def _validate(name: str, value: Any) -> None:
    schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    validator(schema).validate(value)


# 根包导出是消费者入口，不应随内部模块拆分扩张。
# 这份集合保护明确发布的 API，而不是所有可导入实现。
def test_root_exports_only_the_consumer_contract() -> None:
    assert set(machine.__all__) == {
        "AnalysisBundle",
        "AUTHORING_CONTEXT_SCHEMA_VERSION",
        "AnalysisIdentity",
        "AnalysisOptions",
        "AnalysisReceipt",
        "AuthoringContextPacket",
        "BudgetError",
        "ConfigurationError",
        "ContextRequest",
        "ContractError",
        "DriftError",
        "EvidenceBudget",
        "EvidencePage",
        "EvidenceQuery",
        "IntegrityError",
        "InvariantError",
        "MachineError",
        "PacketBudget",
        "PacketScope",
        "ProviderError",
        "TaskIntent",
        "analyze_repository",
        "build_authoring_context",
        "open_analysis",
        "query_evidence",
    }


# 回执保持公共摘要边界，不重新暴露内部源快照字段。
def test_analysis_receipt_matches_its_wire_schema() -> None:
    payload = AnalysisReceipt(AnalysisIdentity(_DIGEST, _DIGEST), {}, {}).to_dict()
    _validate("analysis-receipt.schema.json", payload)
    assert "sourceSnapshotDigest" not in payload


# 使用位置参数模拟旧调用者，新可选字段只能兼容地追加。
# 查询和上下文范围必须以同样方式解释这些参数。
def test_capability_selectors_extend_existing_positional_scope_compatibly() -> None:
    query = machine.EvidenceQuery(
        "services",
        ("candidate:orders",),
        ("boundary:orders",),
        ("orders.py",),
        ("OrderService.place",),
    )
    scope = machine.PacketScope(
        ("candidate:orders",),
        ("boundary:orders",),
        ("orders.py",),
        ("OrderService.place",),
    )

    assert query.boundary_ids == scope.boundary_ids == ("boundary:orders",)
    assert query.paths == scope.paths == ("orders.py",)
    assert query.symbols == scope.symbols == ("OrderService.place",)
    assert query.capability_ids == scope.capability_ids == ()


# 用真实值对象序列化后验证，防止手写字典绕过生产序列化逻辑。
def test_evidence_page_matches_its_wire_schema() -> None:
    item = EntryEvidence(
        "entry:orders",
        ("candidate:orders",),
        "exact",
        "cst",
        Witness("orders.py", _DIGEST, start_line=1, end_line=2),
    )
    payload = EvidencePage(_DIGEST, _DIGEST, "evidence", (item,)).to_dict()
    _validate("evidence-page.schema.json", payload)
    assert "sourceSnapshotDigest" not in json.dumps(payload)


# 未解析能力也是合法结果，schema 不能暗含“所有证据均精确”。
def test_capability_and_packet_match_their_wire_schemas() -> None:
    capability = CapabilitySlice(
        capability_id="cap-" + "b" * 24,
        entry_signature="orders.create",
        trigger={},
        entry={},
        resolution=Resolution.UNRESOLVED,
    )
    _validate("capability-slice.schema.json", capability.to_dict())

    packet = AuthoringContextPacket(TaskIntent.SCOPE_DISCOVERY, _DIGEST, _DIGEST)
    packet_payload = packet.to_dict()
    _validate("authoring-context-packet.schema.json", packet_payload)
    assert packet_payload["schemaVersion"] == 1
