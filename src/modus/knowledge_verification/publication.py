"""Deterministic publication-readiness checks bound to the init execution card.

These checks do not grade prose or impose global diagram counts. They prove that
the author fulfilled the concrete scope, evidence, business-seed and visual
decisions recorded in the unique ``scope-confirmation.md`` execution card, and
that generated prose keeps source locations in structured frontmatter instead
of turning the reader-facing body into an evidence catalog.
"""

from __future__ import annotations

import re
from typing import Final

from ..knowledge_identity import KnowledgePathIdentity
from ..knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ..knowledge_seeds import domain_business_seed_files
from ..orchestrator.module_meta import load_module
from ..paths import ModusPaths
from ..skillmd import split_frontmatter
from .authoring_card import (
    CARD_DOCUMENT,
    AuthoringPlanSource,
    load_authoring_plan,
    string_mapping,
    verify_domain_coverage,
    verify_module_execution,
)
from .discovery import KnowledgeInventory
from .markdown_integrity import read_document
from .models import VerificationFinding, finding

_DOMAIN_STATUSES: Final = frozenset({"pending", "evidence-ready", "authored", "reviewed"})
_DOMAIN_OUTCOMES: Final = frozenset({"pending", "changed", "unchanged", "blocked"})
_VISUAL_KINDS: Final = frozenset({"mermaid", "table", "none"})
_VISUAL_STATUSES: Final = frozenset({"planned", "authored", "waived"})
_INLINE_SOURCE_REF_RE: Final = re.compile(r"[\w][\w./-]*\.[A-Za-z0-9_]+#L\d+")
_BODY_SOURCE_PATH_RE: Final = re.compile(
    r"(?<![A-Za-z0-9_./:-])"
    r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\."
    r"(?:py|pyi|java|kt|kts|go|rs|php|c|cc|cpp|h|hpp|cs|js|jsx|ts|tsx|"
    r"vue|svelte|sql|graphql|proto|yaml|yml|json|toml|xml|gradle|tf|hcl)\b",
    re.IGNORECASE,
)
_MERMAID_RE: Final = re.compile(r"(?m)^```mermaid\s*$")
_TABLE_RE: Final = re.compile(r"(?m)^\|.+\|\s*$\n^\|(?:\s*:?-+:?\s*\|)+\s*$")


# 实际模块来自安全扫描库存，不从执行卡假定文件已存在。
# 实际库存是完成情况的证据，执行卡中列出的计划不能替代文件存在性。
def _actual_modules(inventory: KnowledgeInventory, domain: str) -> set[str]:
    return {item.path.stem for item in inventory.modules if item.domain == domain}


# 领域身份经公共路径分类器确认，避免按任意目录名扩大发布范围。
# 实际存在与计划声明分别收集，后续可同时发现遗漏与越界。
# 领域集合从规范身份中派生，非领域知识目录不计入覆盖承诺。
def _actual_domains(paths: ModusPaths, inventory: KnowledgeInventory) -> set[str]:
    domains: set[str] = set()
    for path in inventory.documents:
        identity = KnowledgePathIdentity.classify(paths, paths.relative(path))
        if identity is not None and identity.domain is not None:
            domains.add(identity.domain)
    return domains


# 纯业务模块没有源码实现，不强求虚假的代码锚点。
# 读取失败按缺少有效锚点处理，由发布核验给出具体发现。
# 纯业务模块允许没有代码锚点，发布校验尊重其实现类型。
def _module_has_source_anchor(paths: ModusPaths, domain: str, module: str) -> bool:
    try:
        metadata = load_module(paths, domain, module)
    except (OSError, TypeError, ValueError):
        return False
    if metadata is not None and metadata.realization == "business-only":
        return True
    return metadata is not None and bool(metadata.anchor_locations)


# 这里只验证必需业务索引可读，不自动创建或重写人工内容。
# 缺失时创建的规则仍属于种子服务，发布核验保持只读。
def _verify_business_seeds(paths: ModusPaths, domain: str) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    for target in domain_business_seed_files(paths, domain):
        relative = paths.relative(target)
        try:
            read_bound_regular_text(paths.root, target, max_bytes=2 * 1024 * 1024)
        except BoundKnowledgeReadError as exc:
            findings.append(
                finding(
                    relative,
                    "domain-business-seed-missing",
                    f"发布需要以下缺失时才创建的业务索引： {exc.kind}",
                )
            )
    return findings


# 正文标记只绑定图表决策 ID，图表是否需要由执行卡决定。
def _visual_marker(visual_id: str) -> str:
    return f"<!-- modus:visual:{visual_id} -->"


# 图表义务来自执行卡中明确记录的读者问题和机制。
# 同一领域内 ID 必须唯一，使正文标记能对应唯一决策。
# 豁免必须说明原因，planned 不能被视作已完成。
# 目标必须是当前领域的规范知识文档，不能借用其他领域图表过关。
# 内容只在标记后的有限窗口内查找，避免匹配到远处无关图表。
# 这里只验证声明兑现，不评价 Mermaid 语义或表格设计质量。
def _verify_visual(
    paths: ModusPaths,
    domain: str,
    raw: object,
    *,
    seen_ids: set[str],
) -> list[VerificationFinding]:
    visual = string_mapping(raw)
    if visual is None:
        return [finding(CARD_DOCUMENT, "authoring-visual-invalid", "visual 必须为映射")]
    visual_id = visual.get("id")
    kind = visual.get("kind")
    status = visual.get("status")
    reason = visual.get("reason")
    target = visual.get("target")
    reader_question = visual.get("readerQuestion")
    mechanism = visual.get("mechanism")
    if not isinstance(visual_id, str) or not visual_id.strip() or visual_id in seen_ids:
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-visual-invalid",
                f"Domain {domain!r} 的图表 ID 必须为唯一的非空字符串",
            )
        ]
    seen_ids.add(visual_id)
    if kind not in _VISUAL_KINDS or status not in _VISUAL_STATUSES:
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-visual-invalid",
                f"visual {visual_id!r} 的类型或状态不受支持",
            )
        ]
    if not isinstance(reader_question, str) or not reader_question.strip():
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-visual-question-missing",
                f"visual {visual_id!r} 需要说明其回答的读者问题",
            )
        ]
    if not isinstance(mechanism, str) or not mechanism.strip():
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-visual-mechanism-missing",
                f"visual {visual_id!r} 需要说明触发绘制的机制",
            )
        ]
    if status == "waived":
        if not isinstance(reason, str) or not reason.strip():
            return [
                finding(
                    CARD_DOCUMENT,
                    "authoring-visual-waiver-empty",
                    f"visual {visual_id!r} 需要具体的豁免原因",
                )
            ]
        return []
    if status != "authored":
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-visual-incomplete",
                f"visual {visual_id!r} remains {status!r}",
            )
        ]
    if kind == "none" or not isinstance(target, str):
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-visual-invalid",
                f"已创作图表 {visual_id!r} 需要 mermaid/table 类型与目标路径",
            )
        ]
    identity = KnowledgePathIdentity.classify(paths, target)
    if identity is None or identity.domain != domain:
        return [
            finding(
                CARD_DOCUMENT,
                "authoring-visual-target-invalid",
                f"visual {visual_id!r} 的目标必须是以下领域内的规范文档：{domain!r}",
                target=target,
            )
        ]
    try:
        text = read_bound_regular_text(paths.root, paths.root / target, max_bytes=2 * 1024 * 1024)
    except BoundKnowledgeReadError as exc:
        return [
            finding(
                target,
                "authoring-visual-target-unavailable",
                f"visual {visual_id!r} 的目标不可用： {exc.kind}",
            )
        ]
    marker = _visual_marker(visual_id)
    marker_at = text.find(marker)
    if marker_at < 0:
        return [
            finding(
                target,
                "authoring-visual-marker-missing",
                f"已创作图表 {visual_id!r} 必须包含 {marker}",
            )
        ]
    following = text[marker_at + len(marker) : marker_at + len(marker) + 16_384]
    pattern = _MERMAID_RE if kind == "mermaid" else _TABLE_RE
    if pattern.search(following) is None:
        return [
            finding(
                target,
                "authoring-visual-content-missing",
                f"visual {visual_id!r} 标记后缺少已声明的 {kind}",
            )
        ]
    return []


# 机器所有的正文强调读者叙事，源码位置留在结构化 anchors 中。
# 人工所有的知识不受该正文样式规则强制改写。
# 分别统计正文路径与结构化锚点，供报告解释迁移状态。
# 示例样本排序并限量，诊断大小不随正文重复引用无限增长。
def _generated_body_source_paths(
    paths: ModusPaths, inventory: KnowledgeInventory
) -> tuple[list[VerificationFinding], int, int]:
    """Reject source-file paths in machine-owned reader-facing Markdown bodies."""

    findings: list[VerificationFinding] = []
    documents_with_paths = 0
    documents_with_anchors = 0
    for path in inventory.documents:
        relative = paths.relative(path)
        identity = KnowledgePathIdentity.classify(paths, relative)
        if identity is None or identity.ownership_plane != "machine":
            continue
        text = read_document(paths, path)
        if text is None:
            continue
        frontmatter, body = split_frontmatter(text)
        anchors = string_mapping(frontmatter.get("anchors"))
        if anchors is not None and isinstance(anchors.get("locations"), list):
            documents_with_anchors += 1
        matches = {
            *(match.group(0) for match in _INLINE_SOURCE_REF_RE.finditer(body)),
            *(match.group(0) for match in _BODY_SOURCE_PATH_RE.finditer(body)),
        }
        if not matches:
            continue
        documents_with_paths += 1
        findings.append(
            finding(
                relative,
                "generated-body-source-path",
                "生成正文的源码路径必须保存在 frontmatter 的 anchors.locations 中",
                count=len(matches),
                samples=sorted(matches)[:5],
            )
        )
    return findings, documents_with_paths, documents_with_anchors


# 数量仅作为发布观察，不以图表多寡给文档质量打分。
# 字段名是公开统计协议，长名称不是云访问密钥。
# 统计读取失败的文档时不伪造内容，其他核验负责报告不可读。
def _knowledge_signals(
    paths: ModusPaths,
    inventory: KnowledgeInventory,
    *,
    body_path_documents: int,
    anchored_documents: int,
) -> dict[str, int]:
    diagrams = 0
    table_documents = 0
    anchored_modules = 0
    for path in inventory.documents:
        text = read_document(paths, path)
        if text is None:
            continue
        diagrams += len(_MERMAID_RE.findall(text))
        table_documents += int(_TABLE_RE.search(text) is not None)
    for module in inventory.modules:
        anchored_modules += int(_module_has_source_anchor(paths, module.domain, module.path.stem))
    return {
        "documents": len(inventory.documents),
        "modules": len(inventory.modules),
        "modulesWithSourceAnchors": anchored_modules,
        "documentsWithStructuredAnchors": anchored_documents,
        # NOCA:QCloudAkCheck(公开报告的稳定 JSON 字段名，不是认证数据，重命名会破坏消费者契约)
        "generatedDocumentsWithBodySourcePaths": body_path_documents,
        "mermaidBlocks": diagrams,
        "documentsWithTables": table_documents,
    }


# 按执行卡确认的范围核验，不能用磁盘现状反向补齐计划。
# 单领域模式只检查该领域，全量模式还检查计划外领域。
# 正文约束与统计先计算，即使执行卡缺失也保留可用诊断。
# 领域与模块都必须完成评审，不能由父级状态替代子项状态。
# changed 与 unchanged 都可作为完成结果，blocked 必须保留为未完成。
# 图表决策与业务种子同属发布约定，但各自拥有独立发现类型。
def verify_publication_readiness(
    paths: ModusPaths,
    inventory: KnowledgeInventory,
    *,
    domain: str | None,
    plan_source: AuthoringPlanSource | None = None,
) -> tuple[list[VerificationFinding], dict[str, int]]:
    """Verify declared authoring commitments without grading narrative prose."""
    body_path_findings, body_path_documents, anchored_documents = _generated_body_source_paths(
        paths, inventory
    )
    planned, findings = load_authoring_plan(paths, source=plan_source)
    findings.extend(body_path_findings)
    signals = _knowledge_signals(
        paths,
        inventory,
        body_path_documents=body_path_documents,
        anchored_documents=anchored_documents,
    )
    if planned is None:
        return findings, signals

    selected = {domain} if domain is not None else set(planned)
    if domain is not None and domain not in planned:
        findings.append(
            finding(
                CARD_DOCUMENT,
                "authoring-domain-unplanned",
                f"指定领域 {domain!r} 未列入执行卡",
            )
        )
        return findings, signals

    actual_domains = _actual_domains(paths, inventory)
    if domain is None:
        for extra in sorted(actual_domains - set(planned)):
            findings.append(
                finding(
                    paths.relative(paths.domain(extra)),
                    "authoring-domain-unplanned",
                    "已发布领域未列入已确认的执行卡",
                )
            )

    for domain_id in sorted(selected):
        raw_domain = string_mapping(planned.get(domain_id))
        if raw_domain is None:
            findings.append(
                finding(
                    CARD_DOCUMENT,
                    "authoring-domain-invalid",
                    f"Domain {domain_id!r} plan 必须为映射",
                )
            )
            continue
        try:
            domain_document = paths.relative(paths.domain_skill(domain_id))
        except ValueError:
            findings.append(
                finding(
                    CARD_DOCUMENT,
                    "authoring-domain-invalid",
                    f"领域 ID {domain_id!r} 不是规范标识",
                )
            )
            continue
        status = raw_domain.get("status")
        outcome = raw_domain.get("outcome")
        if status not in _DOMAIN_STATUSES or status != "reviewed":
            findings.append(
                finding(
                    CARD_DOCUMENT,
                    "authoring-domain-incomplete",
                    f"Domain {domain_id!r} 必须已评审，实际为 {status!r}",
                )
            )
        if outcome not in _DOMAIN_OUTCOMES or outcome not in {"changed", "unchanged"}:
            findings.append(
                finding(
                    CARD_DOCUMENT,
                    "authoring-domain-outcome-incomplete",
                    f"Domain {domain_id!r} 需要 changed/unchanged 结果，实际为 {outcome!r}",
                )
            )
        if not paths.domain_skill(domain_id).is_file():
            findings.append(finding(domain_document, "authoring-domain-missing", "已确认领域缺失"))
        findings.extend(_verify_business_seeds(paths, domain_id))
        findings.extend(verify_domain_coverage(domain_id, raw_domain.get("coverage")))

        planned_modules = string_mapping(raw_domain.get("modules"))
        if planned_modules is None or not planned_modules:
            findings.append(
                finding(
                    CARD_DOCUMENT,
                    "authoring-modules-invalid",
                    f"Domain {domain_id!r} 必须声明已确认的模块映射",
                )
            )
            planned_modules = {}
        # 先校验模块身份，再构造路径，防止非法 ID 进入文件访问。
        # 无效声明不能参与实际模块集合对比。
        valid_planned_modules: dict[str, object] = {}
        for module_id, raw_module in planned_modules.items():
            try:
                paths.module(domain_id, module_id)
            except ValueError:
                findings.append(
                    finding(
                        CARD_DOCUMENT,
                        "authoring-module-invalid",
                        f"模块 ID {domain_id}/{module_id!r} 不是规范标识",
                    )
                )
                continue
            valid_planned_modules[module_id] = raw_module
        # 计划缺失和实际多出分别报告，避免只检查文件存在而遗漏范围漂移。
        # 集合比较排序后输出，使相同问题的报告次序稳定。
        actual_modules = _actual_modules(inventory, domain_id)
        for missing in sorted(set(valid_planned_modules) - actual_modules):
            findings.append(
                finding(
                    paths.relative(paths.module(domain_id, missing)),
                    "authoring-module-missing",
                    "已确认模块的文档缺失",
                )
            )
        for extra in sorted(actual_modules - set(valid_planned_modules)):
            findings.append(
                finding(
                    paths.relative(paths.module(domain_id, extra)),
                    "authoring-module-unplanned",
                    "模块未列入已确认的执行卡",
                )
            )
        # 模块执行状态与文档锚点分别验证。
        # 文件存在不能证明取证完成，状态完成也不能证明文档有可追溯位置。
        for module_id, raw_module in sorted(valid_planned_modules.items()):
            module_status, module_findings = verify_module_execution(
                domain_id, module_id, raw_module
            )
            findings.extend(module_findings)
            if module_status != "reviewed":
                findings.append(
                    finding(
                        CARD_DOCUMENT,
                        "authoring-module-incomplete",
                        f"Module {domain_id}/{module_id} 必须已评审，实际为 {module_status!r}",
                    )
                )
            if module_id in actual_modules and not _module_has_source_anchor(
                paths, domain_id, module_id
            ):
                findings.append(
                    finding(
                        paths.relative(paths.module(domain_id, module_id)),
                        "module-source-anchor-missing",
                        "初始化或重建中已实现的模块至少需要一个结构化 frontmatter anchors.locations 条目",
                    )
                )

        # 每个领域需作出图表决策，但允许有依据的明确豁免。
        # 不以全项目统一图表数量取代各领域的读者需求。
        visuals = raw_domain.get("visuals")
        if not isinstance(visuals, list) or not visuals:
            findings.append(
                finding(
                    CARD_DOCUMENT,
                    "authoring-visual-decision-missing",
                    f"Domain {domain_id!r} 至少需要一个已创作或明确豁免的图表决策",
                )
            )
            continue
        # ID 唯一性限定在当前领域，跨领域可独立使用各自图表命名。
        seen_ids: set[str] = set()
        for visual in visuals:
            findings.extend(_verify_visual(paths, domain_id, visual, seen_ids=seen_ids))

    return findings, signals


__all__ = ["verify_publication_readiness"]
