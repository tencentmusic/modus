"""Knowledge writes preserve authorship under retries and conflicts."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event

import pytest
import yaml
from typer.testing import CliRunner

from modus import knowledge_write_session as session
from modus.cli import app
from modus.commands.seed_business import seed_domain_business
from modus.knowledge_update import update_knowledge
from modus.orchestrator import knowledge_sync
from modus.paths import ModusPaths
from modus.scaffold.catalog import TemplateCatalog

MODULE = "modus/knowledge/domain/order/references/modules/refund.md"
OLD = "modus/knowledge/domain/order/references/modules/old-refund.md"
TEAM = "modus/knowledge/constraint/team-standard.md"
API_SHARD = "modus/knowledge/domain/order/references/api/commands.md"


# 摘要用于 compare-and-swap；测试与生产都对完整 UTF-8 字节计算。
def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# 直接写夹具绕过业务 API，便于模拟既有人工材料和冲突状态。
def _put(root: Path, relative: str, text: str = "# Existing knowledge\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


# 模块锚点给同步候选提供真实所有者，不靠文件名推断关联。
def _module(root: Path, name: str, source: str, symbol: str) -> str:
    relative = f"modus/knowledge/domain/order/references/modules/{name}.md"
    metadata = {
        "moduleId": f"order/{name}",
        "parent": "order",
        "anchors": {"locations": [{"path": source, "symbol": symbol, "startLine": 1}]},
    }
    _put(root, relative, "---\n" + yaml.safe_dump(metadata) + "---\n# Module\n")
    return relative


# 先落地替代文档再退役旧文档，避免失败后知识出现空窗。
# 同一批次重试应识别未变化写入和已不存在目标。
# 旧摘要绑定的是观察时的内容，不能无条件删除当前文件。
def test_writes_precede_explicit_retirement_and_retry_is_idempotent(tmp_path: Path) -> None:
    old = _put(tmp_path, OLD, "# Old\n")
    new = "# Replacement\n"
    result = update_knowledge(
        str(tmp_path), {MODULE: new}, deletions=[OLD], expected_hashes={OLD: _digest("# Old\n")}
    )
    assert result["status"] == "completed"
    assert result["writes"] == [MODULE]
    assert result["deleted"] == [OLD]
    assert not old.exists()
    retry = update_knowledge(
        str(tmp_path), {MODULE: new}, deletions=[OLD], expected_hashes={OLD: _digest("# Old\n")}
    )
    assert retry["status"] == "noop"
    assert retry["unchanged"] == [MODULE]
    assert retry["alreadyAbsent"] == [OLD]


# 两个写者观察同一版本，只有一个能成功更新。
# 不约定竞争胜者，只保护失败方不会覆盖胜者内容。
def test_concurrent_writers_require_the_observed_digest(tmp_path: Path) -> None:
    target = "modus/knowledge/domain/order/SKILL.md"
    original = "# Order\n"
    assert update_knowledge(str(tmp_path), {target: original})["status"] == "completed"
    digest = _digest(original)

    def write(value: str) -> dict:
        return update_knowledge(str(tmp_path), {target: value}, expected_hashes={target: digest})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["# A\n", "# B\n"]))

    # 竞争必须在真实写入锁内比较摘要，否则两个写者可能同时认为自己成功。
    # 最终字节只能来自胜者，不能混合两个提交的正文。
    assert sorted(result["status"] for result in results) == ["completed", "partial"]
    assert (tmp_path / target).read_text(encoding="utf-8") in {"# A\n", "# B\n"}


# 合法字符串前缀不能证明真实路径仍在知识树中。
# 外部目标不存在的断言覆盖拒绝前是否发生写入。
def test_write_does_not_follow_a_symlink_outside_knowledge(tmp_path: Path) -> None:
    paths = ModusPaths.for_root(tmp_path)
    paths.knowledge_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (paths.knowledge_dir / "linked").symlink_to(outside, target_is_directory=True)

    result = update_knowledge(str(tmp_path), {"modus/knowledge/linked/no.md": "# No"})

    assert result["status"] == "partial"
    assert not (outside / "no.md").exists()


# 种子只负责填空，重复生成不能修订人工口径。
# 首次创建数量和二次不变结果同时保护幂等与必要产出。
def test_domain_business_seeds_preserve_human_bytes(tmp_path: Path) -> None:
    paths = ModusPaths.for_root(tmp_path)
    paths.domain_skill("orders").parent.mkdir(parents=True)
    paths.domain_skill("orders").write_text("# Orders\n", encoding="utf-8")

    first = seed_domain_business(tmp_path, ["orders"])
    assert first["status"] == "changed"
    assert len(first["created"]) == 4

    meta = paths.domain_business_index("orders", "meta")
    meta.write_text("# 人工口径\n", encoding="utf-8")
    second = seed_domain_business(tmp_path, ["orders"])

    assert second["status"] == "unchanged"
    assert meta.read_text(encoding="utf-8") == "# 人工口径\n"


# API 分片贯穿创建、CAS 更新、同步选择和退役全生命周期。
# 创建使用 None 表达“预期不存在”，不同于缺省不提供摘要。
# 删除必须绑定最后一次已观察内容，避免用旧摘要授权新版本。
def test_api_shard_supports_create_update_sync_target_and_cas_delete(tmp_path: Path) -> None:
    created = "# Commands\n\n## 分组边界\n\n命令组。\n\n## 契约详情\n\n### Create\n\n创建。\n"
    result = update_knowledge(
        str(tmp_path), {API_SHARD: created}, expected_hashes={API_SHARD: None}
    )
    assert result["writes"] == [API_SHARD]

    updated = created.replace("创建。", "创建并返回结果。")
    result = update_knowledge(
        str(tmp_path),
        {API_SHARD: updated},
        expected_hashes={API_SHARD: _digest(created)},
    )
    assert result["writes"] == [API_SHARD]
    assert (
        knowledge_sync.sync_knowledge(str(tmp_path), targets=[API_SHARD])["candidates"][0]["path"]
        == API_SHARD
    )

    result = update_knowledge(
        str(tmp_path),
        {},
        deletions=[API_SHARD],
        expected_hashes={API_SHARD: _digest(updated)},
    )
    assert result["deleted"] == [API_SHARD], result


# 批量写入允许部分成功；旧文档退役要等替代写入全部成功。
# 因此保留已完成的新文档，同时延迟删除，不能冒充整批事务回滚。
# 冲突目标的人工作品必须逐字保留。
def test_write_conflict_defers_retirement_without_rolling_back_other_writes(tmp_path: Path) -> None:
    _put(tmp_path, MODULE, "# Human edit\n")
    old = _put(tmp_path, OLD)
    another = "modus/knowledge/domain/order/references/rule.md"
    result = update_knowledge(
        str(tmp_path),
        {another: "# New rules\n", MODULE: "# Replacement\n"},
        expected_hashes={
            MODULE: _digest("# Stale\n"),
            OLD: _digest(old.read_text(encoding="utf-8")),
        },
        deletions=[OLD],
    )
    assert result["status"] == "partial"
    assert result["writes"] == [another]
    # 替代文档冲突时保留旧入口，避免部分成功留下知识导航空洞。
    assert result["deferredDeletions"] == [OLD]
    assert result["deleted"] == []
    assert old.exists()
    assert (tmp_path / MODULE).read_text(encoding="utf-8") == "# Human edit\n"


# 请求结构错误在预检阶段统一拒绝，不能边写边发现后续参数非法。
# 参数化覆盖类型、重复删除、写删冲突和显式授权标志。
@pytest.mark.parametrize(
    "extra",
    [
        {"expected_hashes": []},
        {"expected_hashes": {MODULE: 42}},
        {"expected_hashes": {MODULE: "bad-digest"}},
        {"deletions": OLD},
        {"deletions": [42]},
        {"deletions": [OLD]},
        {"deletions": [OLD, OLD], "expected_hashes": {OLD: _digest("old")}},
        {"deletions": [MODULE], "expected_hashes": {MODULE: _digest("old")}},
        {"allow_team_standard": "true"},
        {"initialize_team_standard": "true"},
        {"initialize_team_standard": True, "allow_team_standard": True},
    ],
)
def test_invalid_batch_is_rejected_before_any_write(tmp_path: Path, extra: dict) -> None:
    with pytest.raises(ValueError):
        update_knowledge(str(tmp_path), {MODULE: "# New\n"}, **extra)
    assert not (tmp_path / "modus").exists()


@pytest.mark.parametrize(
    "options",
    [
        {"initialize_team_standard": True, "allow_team_standard": True},
        {"initialize_team_standard": "true"},
        {"allow_team_standard": 1},
    ],
)
def test_direct_writer_rejects_invalid_permissions_before_side_effects(
    tmp_path: Path, options: dict
) -> None:
    """直接调用与批量调用同样拒绝矛盾权限，不能依赖上层预检。"""
    with pytest.raises(ValueError):
        session.write_document(
            ModusPaths.for_root(tmp_path),
            TEAM,
            "# 项目规范\n",
            expected_hash=None,
            allow_human=True,
            **options,
        )
    assert list(tmp_path.iterdir()) == []


def test_empty_write_distinguishes_a_missing_document_from_existing_empty_bytes(
    tmp_path: Path,
) -> None:
    """写入回执必须对应实际文件，空正文不能绕过新建或所有权判断。"""
    first = update_knowledge(str(tmp_path), {MODULE: ""})
    assert first["writes"] == [MODULE]
    assert (tmp_path / MODULE).read_bytes() == b""
    retry = update_knowledge(str(tmp_path), {MODULE: ""})
    assert retry["status"] == "noop"
    assert retry["unchanged"] == [MODULE]

    denied = update_knowledge(str(tmp_path), {TEAM: ""})
    assert denied["status"] == "partial"
    assert denied["writes"] == []
    assert not (tmp_path / TEAM).exists()


# 摘要匹配只证明内容未变，不赋予删除人工文档的权限。
# 退役还需通过类别所有权检查，未知类别保守保留。
@pytest.mark.parametrize(
    "target",
    [
        TEAM,
        "modus/knowledge/constraint/custom.md",
        "modus/knowledge/domain/order/references/business/index.md",
        "modus/knowledge/domain/order/references/business/original/requirement.md",
        "modus/knowledge/domain/order/module-map.md",
        "modus/knowledge/architecture-overview.md",
        "modus/knowledge/arbitrary.md",
    ],
)
def test_retirements_never_delete_human_or_unclassified_material(
    tmp_path: Path, target: str
) -> None:
    document = _put(tmp_path, target)
    before = document.read_bytes()
    result = update_knowledge(
        str(tmp_path),
        {},
        deletions=[target],
        expected_hashes={target: hashlib.sha256(before).hexdigest()},
    )
    assert result["status"] == "partial"
    assert document.read_bytes() == before


# 分别覆盖文件软链和父目录软链，二者都会改变真实删除对象。
# 匹配目标内容摘要仍不足以绕过“不跟随链接”的路径规则。
@pytest.mark.parametrize("link_parent", [False, True])
def test_symlink_retirement_preserves_the_referenced_file(
    tmp_path: Path, link_parent: bool
) -> None:
    real = _put(tmp_path, "source.md", "# Do not remove\n")
    target = tmp_path / OLD
    target.parent.mkdir(parents=True)
    if link_parent:
        outside = tmp_path / "outside"
        outside.mkdir()
        real = _put(outside, target.name, real.read_text(encoding="utf-8"))
        target.parent.rmdir()
        target.parent.symlink_to(outside, target_is_directory=True)
    else:
        target.symlink_to(real)
    result = update_knowledge(
        str(tmp_path),
        {},
        deletions=[OLD],
        expected_hashes={OLD: _digest(real.read_text(encoding="utf-8"))},
    )
    assert result["status"] == "partial"
    assert real.read_text(encoding="utf-8") == "# Do not remove\n"


# 在路径绑定检查之间替换目标，模拟检查后到删除前的竞态。
# 即使旧内容被重命名保留，新目标也不能继承旧删除授权。
# 同时核对两个文件，证明拒绝没有误删任一版本。
def test_target_replacement_during_delete_preserves_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _put(tmp_path, OLD, "# Old\n")
    original = session._unlink_verified_candidate

    def replace_before_unlink(*args, **kwargs) -> None:
        target.rename(target.with_suffix(".retained"))
        target.write_text("# Concurrent replacement\n", encoding="utf-8", newline="")
        original(*args, **kwargs)

    monkeypatch.setattr(session, "_unlink_verified_candidate", replace_before_unlink)
    result = update_knowledge(
        str(tmp_path), {}, deletions=[OLD], expected_hashes={OLD: _digest("# Old\n")}
    )
    assert result["status"] == "partial"
    assert target.read_text(encoding="utf-8") == "# Concurrent replacement\n"
    assert target.with_suffix(".retained").read_text(encoding="utf-8") == "# Old\n"


# 更新和退役必须竞争同一文档锁，而非各自独立串行化。
# 只允许一方使用旧摘要成功，最终存在的文件必须是新内容。
def test_same_document_write_and_delete_share_the_cas_lock(tmp_path: Path) -> None:
    _put(tmp_path, OLD, "# Original\n")
    hashes = {OLD: _digest("# Original\n")}
    with ThreadPoolExecutor(max_workers=2) as executor:
        write = executor.submit(
            update_knowledge, str(tmp_path), {OLD: "# Revised\n"}, expected_hashes=hashes
        )
        remove = executor.submit(
            update_knowledge, str(tmp_path), {}, deletions=[OLD], expected_hashes=hashes
        )
        results = [write.result(), remove.result()]
    assert sorted(result["status"] for result in results) == ["completed", "partial"]
    target = tmp_path / OLD
    if target.exists():
        assert target.read_text(encoding="utf-8") == "# Revised\n"


# 首次初始化只允许填充当前模板，追加过人工规则的正文必须原样保留。
@pytest.mark.parametrize("authored", [False, True])
def test_team_standard_initialization_preserves_authored_content(
    tmp_path: Path, authored: bool
) -> None:
    original = TemplateCatalog().read("knowledge/constraint/team-standard.md")
    if authored:
        original += "\n团队新增的人工规则。\n"
    target = _put(tmp_path, TEAM, original)
    paths = ModusPaths.for_root(tmp_path)
    replacement = "# 团队规范\n\n经过项目分析生成的规范。\n"

    def initialize() -> None:
        session.write_document(
            paths,
            TEAM,
            replacement,
            expected_hash=_digest(original),
            allow_human=True,
            initialize_team_standard=True,
        )

    if authored:
        with pytest.raises(session.KnowledgeWriteSessionError, match="保留内容"):
            initialize()
        assert target.read_text(encoding="utf-8") == original
    else:
        initialize()
        assert target.read_text(encoding="utf-8") == replacement


# 团队规范需要类别授权与当前摘要两道独立条件。
# 显式授权不取消并发保护，过时摘要仍然必须拒绝。
@pytest.mark.parametrize(
    "target_name",
    [
        TEAM,
        "modus/knowledge/constraint/team-standard/tasks.md",
        "modus/knowledge/constraint/team-standard/legacy/tasks.md",
    ],
)
def test_explicit_team_standard_maintenance_requires_opt_in_and_current_digest(
    tmp_path: Path,
    target_name: str,
) -> None:
    target = _put(tmp_path, target_name, "# Team's existing standard\n")
    hashes = {target_name: _digest(target.read_text(encoding="utf-8"))}
    denied = update_knowledge(
        str(tmp_path), {target_name: "# Revised standard\n"}, expected_hashes=hashes
    )
    assert denied["status"] == "partial"
    accepted = update_knowledge(
        str(tmp_path),
        {target_name: "# Revised standard\n"},
        expected_hashes=hashes,
        allow_team_standard=True,
    )
    assert accepted["writes"] == [target_name]
    stale = update_knowledge(
        str(tmp_path),
        {target_name: "# Overwrite\n"},
        expected_hashes=hashes,
        allow_team_standard=True,
    )
    assert stale["status"] == "partial"
    assert target.read_text(encoding="utf-8") == "# Revised standard\n"


@pytest.mark.parametrize("nested", [False, True])
def test_team_topic_initialization_is_missing_only_and_not_machine_owned(
    tmp_path: Path, nested: bool
) -> None:
    """拆成专题不解除人工保护；入口种子也不能充当专题的覆盖凭据。"""
    from modus.knowledge_identity import KnowledgePathIdentity

    topic = "modus/knowledge/constraint/team-standard/" + (
        "legacy/concurrency.md" if nested else "concurrency.md"
    )
    body = "# 并发\n\n性质: 通用建议\n"
    denied = update_knowledge(str(tmp_path), {topic: body})
    assert denied["status"] == "partial"
    assert not (tmp_path / topic).exists()
    created = update_knowledge(str(tmp_path), {topic: body}, initialize_team_standard=True)
    assert created["writes"] == [topic]
    assert update_knowledge(str(tmp_path), {topic: body})["status"] == "noop"
    identity = KnowledgePathIdentity.classify(ModusPaths.for_root(tmp_path), topic)
    assert identity is not None and identity.ownership_plane == "human"

    for existing in (body, TemplateCatalog().read("knowledge/constraint/team-standard.md")):
        _put(tmp_path, topic, existing)
        result = update_knowledge(
            str(tmp_path),
            {topic: "# Replacement\n"},
            expected_hashes={topic: _digest(existing)},
            initialize_team_standard=True,
        )
        assert result["status"] == "partial"
        retired = update_knowledge(
            str(tmp_path),
            {},
            deletions=[topic],
            expected_hashes={topic: _digest(existing)},
        )
        assert retired["status"] == "partial"
        assert (tmp_path / topic).read_text(encoding="utf-8") == existing


def test_initialization_cannot_add_topics_after_entry_is_human_owned(tmp_path: Path) -> None:
    """不能把新增文件当作绕过既有团队规范维护授权的入口。"""
    _put(tmp_path, TEAM, "# 人工规范\n")
    topic = "modus/knowledge/constraint/team-standard/database.md"
    result = update_knowledge(str(tmp_path), {topic: "# 数据库\n"}, initialize_team_standard=True)
    assert result["status"] == "partial"
    assert not (tmp_path / topic).exists()
    maintained = update_knowledge(str(tmp_path), {topic: "# 数据库\n"}, allow_team_standard=True)
    assert maintained["writes"] == [topic]
    assert (tmp_path / TEAM).read_text(encoding="utf-8") == "# 人工规范\n"


@pytest.mark.parametrize("seed_exists", [False, True])
def test_team_topics_publish_before_entry_and_retry_without_maintenance(
    tmp_path: Path, seed_exists: bool
) -> None:
    """专题先发布，入口最后成稿；原请求重试不需要升级人工维护授权。"""
    seed = TemplateCatalog().read("knowledge/constraint/team-standard.md")
    if seed_exists:
        _put(tmp_path, TEAM, seed)
    topic = "modus/knowledge/constraint/team-standard/database.md"
    documents = {topic: "# 数据库\n", TEAM: "# 团队规范\n\n[数据库](team-standard/database.md)\n"}
    hashes = {topic: None, TEAM: _digest(seed) if seed_exists else None}

    published = update_knowledge(
        str(tmp_path), documents, expected_hashes=hashes, initialize_team_standard=True
    )
    assert published["status"] == "completed"
    assert published["writes"] == [topic, TEAM]
    retried = update_knowledge(
        str(tmp_path), documents, expected_hashes=hashes, initialize_team_standard=True
    )
    assert retried["status"] == "noop"
    assert retried["unchanged"] == [topic, TEAM]


def test_failed_entry_publication_preserves_completed_topic(tmp_path: Path) -> None:
    """CAS 冲突只影响入口；调用者可回读后继续发布，不回滚已完成专题。"""
    seed = TemplateCatalog().read("knowledge/constraint/team-standard.md")
    _put(tmp_path, TEAM, seed)
    topic = "modus/knowledge/constraint/team-standard/database.md"
    documents = {topic: "# 数据库\n", TEAM: "# 团队规范\n"}
    partial = update_knowledge(
        str(tmp_path),
        documents,
        expected_hashes={TEAM: _digest("# 过时种子\n")},
        initialize_team_standard=True,
    )
    assert partial["status"] == "partial"
    assert partial["writes"] == [topic]
    assert partial["conflicts"][0]["path"] == TEAM
    assert (tmp_path / topic).read_text(encoding="utf-8") == documents[topic]
    assert (tmp_path / TEAM).read_text(encoding="utf-8") == seed

    retried = update_knowledge(
        str(tmp_path),
        documents,
        expected_hashes={TEAM: _digest(seed)},
        initialize_team_standard=True,
    )
    assert retried["status"] == "completed"
    assert retried["unchanged"] == [topic]
    assert retried["writes"] == [TEAM]


def test_topic_initialization_observes_entry_published_while_waiting_for_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """入口锁串行化交接：专题等待期间入口成稿，唤醒后必须重新判定权限。"""
    paths = ModusPaths.for_root(tmp_path)
    seed = TemplateCatalog().read("knowledge/constraint/team-standard.md")
    _put(tmp_path, TEAM, seed)
    topic = "modus/knowledge/constraint/team-standard/database.md"
    entry_lock = paths.knowledge_document_lock(paths.team_standard)
    original_lock = session.required_reentrant_file_lock
    waiting = Event()

    @contextmanager
    def observed_lock(path: Path):
        if path == entry_lock:
            waiting.set()
        with original_lock(path):
            yield

    monkeypatch.setattr(session, "required_reentrant_file_lock", observed_lock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with original_lock(entry_lock):
            pending = pool.submit(
                update_knowledge,
                str(tmp_path),
                {topic: "# 数据库\n"},
                initialize_team_standard=True,
            )
            assert waiting.wait(timeout=5), "专题初始化必须先取得入口锁"
            session.write_document(
                paths,
                TEAM,
                "# 已发布规范\n",
                expected_hash=_digest(seed),
                allow_human=True,
                initialize_team_standard=True,
            )
        result = pending.result(timeout=5)

    assert result["status"] == "partial"
    assert "入口已包含保留内容" in result["conflicts"][0]["reason"]
    assert not (tmp_path / topic).exists()


@pytest.mark.parametrize("seed_exists", [False, True])
def test_cli_initializes_team_standard_once_and_preserves_it_on_retry(
    tmp_path: Path, seed_exists: bool
) -> None:
    """真实 CLI 必须连接窄权限；初始化重试不能获得人工正文维护权限。"""
    seed = TemplateCatalog().read("knowledge/constraint/team-standard.md")
    if seed_exists:
        _put(tmp_path, TEAM, seed)
    replacement = "# 团队规范\n\n当前项目约束。\n"
    payload = {
        "documents": {TEAM: replacement},
        "expectedHashes": {TEAM: _digest(seed) if seed_exists else None},
    }
    request = tmp_path / "initialize.json"
    runner = CliRunner()

    def invoke() -> tuple[int, dict]:
        request.write_text(json.dumps(payload), encoding="utf-8")
        result = runner.invoke(
            app, ["-C", str(tmp_path), "knowledge", "update", "--input", str(request)]
        )
        return result.exit_code, json.loads(result.output)

    code, result = invoke()
    assert code == 1, result
    assert result["writes"] == []
    if seed_exists:
        assert (tmp_path / TEAM).read_text(encoding="utf-8") == seed
    else:
        assert not (tmp_path / TEAM).exists()

    payload["initializeTeamStandard"] = True
    code, result = invoke()
    assert code == 0, result
    assert result["writes"] == [TEAM]
    assert (tmp_path / TEAM).read_text(encoding="utf-8") == replacement

    code, result = invoke()
    assert code == 0, result
    assert result["status"] == "noop"
    assert result["unchanged"] == [TEAM]

    payload["documents"] = {TEAM: "# 不能通过首次填充重写\n"}
    payload["expectedHashes"] = {TEAM: _digest(replacement)}
    code, result = invoke()
    assert code == 1, result
    assert result["writes"] == []
    assert (tmp_path / TEAM).read_text(encoding="utf-8") == replacement


@pytest.mark.parametrize("content", ["", "# 旧版种子\n", "# 人工规范\n"])
def test_initialization_rejects_non_seed_even_with_current_digest(
    tmp_path: Path, content: str
) -> None:
    target = _put(tmp_path, TEAM, content)
    result = update_knowledge(
        str(tmp_path),
        {TEAM: "# 首次规范\n"},
        expected_hashes={TEAM: _digest(content)},
        initialize_team_standard=True,
    )
    assert result["status"] == "partial"
    assert result["conflicts"][0]["path"] == TEAM
    assert target.read_text(encoding="utf-8") == content


def test_initialization_rechecks_seed_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """调查和预读之后发生人工修改，最终锁内检查仍须阻止覆盖。"""
    from modus import knowledge_update

    seed = TemplateCatalog().read("knowledge/constraint/team-standard.md")
    target = _put(tmp_path, TEAM, seed)
    human = seed + "\n人工补充。\n"
    original_write = knowledge_update.write_document

    def concurrent_edit(*args, **kwargs):
        target.write_text(human, encoding="utf-8")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(knowledge_update, "write_document", concurrent_edit)
    result = update_knowledge(
        str(tmp_path),
        {TEAM: "# 首次规范\n"},
        expected_hashes={TEAM: _digest(seed)},
        initialize_team_standard=True,
    )
    assert result["status"] == "partial"
    assert result["writes"] == []
    assert target.read_text(encoding="utf-8") == human


def test_sync_discovers_topic_file_links_and_protected_candidates_without_writing(
    tmp_path: Path,
) -> None:
    from modus.skillmd import render

    _put(tmp_path, "refund.py", "# run is no longer declared\nmessage = 'run'\n")
    _put(tmp_path, "settings.yaml", "limit: 3\n")
    _module(tmp_path, "refund", "refund.py", "run")
    _put(
        tmp_path,
        API_SHARD,
        render(
            {"anchors": {"locations": [{"path": "refund.py", "symbol": "run", "startLine": 1}]}},
            "# 接口\n",
        ),
    )
    rule = "modus/knowledge/domain/order/references/rule.md"
    _put(tmp_path, rule, render({"anchors": {"paths": ["settings.yaml"]}}, "# 规则\n"))
    _put(tmp_path, TEAM, render({"anchors": {"paths": ["settings.yaml"]}}, "# 人工规范\n"))
    originals = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = knowledge_sync.inspect_knowledge_impact(str(tmp_path), ["refund.py", "settings.yaml"])
    candidates = {row["path"]: row for row in result["candidates"]}
    assert set(candidates) == {MODULE, API_SHARD, rule, TEAM}
    assert candidates[MODULE]["moduleId"] == "order/refund"
    assert candidates[API_SHARD]["moduleId"] is None
    assert candidates[rule]["confidence"] == "path-only"
    assert candidates[rule]["matchedSourcePaths"] == ["settings.yaml"]
    assert {row["document"] for row in result["anchorReviewCandidates"]} == {MODULE, API_SHARD}
    assert all(
        row["disposition"] == "anchor-symbol-missing" for row in result["anchorReviewCandidates"]
    )
    assert result["writes"] == [] and not result["conflicts"]
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == originals
    protected = update_knowledge(
        str(tmp_path),
        {TEAM: "# Changed\n"},
        expected_hashes={TEAM: _digest((tmp_path / TEAM).read_text())},
    )
    assert protected["conflicts"] and (tmp_path / TEAM).read_bytes() == originals[tmp_path / TEAM]


@pytest.mark.parametrize(
    ("source", "symbol", "line", "disposition"),
    [
        ("\n\ndef run():\n    pass\n", "run", 1, "anchor-line-drift"),
        (
            "# run\nclass A:\n    def run(self): pass\nclass B:\n    def run(self): pass\n",
            "run",
            1,
            "anchor-ambiguous",
        ),
        ("def run(:\n", "run", 1, "anchor-verification-unavailable"),
    ],
)
def test_sync_reports_declaration_review_reasons(
    tmp_path: Path, source: str, symbol: str, line: int, disposition: str
) -> None:
    _put(tmp_path, "source.py", source)
    _module(tmp_path, "refund", "source.py", symbol)
    result = knowledge_sync.inspect_knowledge_impact(str(tmp_path), ["source.py"])
    assert result["anchorReviewCandidates"][0]["disposition"] == disposition
    assert not result["writes"]


def test_moved_source_is_routable_after_existing_cas_maintenance(tmp_path: Path) -> None:
    from modus.commands.verify_anchors import run_verify_anchors
    from modus.orchestrator.context_resolver import resolve_context
    from modus.skillmd import render

    old = {"path": "old.py", "symbol": "refund", "startLine": 1}
    original = render({"anchors": {"locations": [old]}}, "# 退款\n退款由 `refund` 执行。\n")
    _put(tmp_path, API_SHARD, original)
    _put(tmp_path, "new.py", "def refund():\n    return 'settled'\n")
    unmatched = knowledge_sync.inspect_knowledge_impact(str(tmp_path), ["new.py"])
    assert not unmatched["candidates"] and unmatched["skipped"]
    impact = knowledge_sync.inspect_knowledge_impact(str(tmp_path), ["old.py", "new.py"])
    assert [row["path"] for row in impact["candidates"]] == [API_SHARD]
    assert impact["anchorReviewCandidates"][0]["disposition"] == "anchor-symbol-missing"
    revised = render(
        {"anchors": {"locations": [{**old, "path": "new.py", "endLine": 2}]}},
        "# 退款\n退款由 `refund` 执行，返回已结算结果。\n",
    )
    updated = update_knowledge(
        str(tmp_path), {API_SHARD: revised}, expected_hashes={API_SHARD: _digest(original)}
    )
    assert updated["writes"] == [API_SHARD]
    assert run_verify_anchors(str(tmp_path))["status"] == "clean"
    context = resolve_context(str(tmp_path), "退款 refund", scope="project-read")
    assert any(
        row["path"] == "new.py" and row.get("symbol") == "refund" for row in context["evidence"]
    )
    assert not context["groundingGaps"]
