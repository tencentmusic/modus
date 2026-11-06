"""Ingest Markdown knowledge into deterministic, provenance-aware sections."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...knowledge_identity import is_team_standard_path
from ...knowledge_reader import BoundKnowledgeReadError, read_bound_regular_text
from ...knowledge_seeds import is_constraint_seed
from ...paths import ModusPaths
from ...skillmd import split_frontmatter

INDEX_SCHEMA_VERSION = 1

# 三个预算分别约束单文档、整轮读取与持久索引，不能相互替代。
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_INDEX_BYTES = 256 * 1024 * 1024

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_LABELED_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ITEM_ID_RE = re.compile(r"\{\{item:([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\}\}")
_ITEM_ANCHOR_RE = re.compile(
    r'<a\s+id=["\']item-([A-Za-z0-9][A-Za-z0-9._:-]{0,127})["\']\s*></a>',
    re.IGNORECASE,
)
_HTML_ANCHOR_RE = re.compile(r'<a\s+(?:name|id)=["\']([^"\']+)["\']', re.IGNORECASE)


def markdown_slug(value: str) -> str:
    """标题与链接片段共享 Unicode 归一化，不依赖文档语言。"""
    value = value.strip().casefold()
    result = [
        character
        for character in value
        if character in {"-", "_", " "} or unicodedata.category(character)[0] in {"L", "N", "M"}
    ]
    return re.sub(r"[ -]+", "-", "".join(result)).strip("-")


def strip_fenced_code(text: str) -> str:
    """示例内的链接不参与导航；保留空行以维持来源坐标。"""
    output: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None and match and not (match[1][0] == "`" and "`" in match[2]):
            fence = (match[1][0], len(match[1]))
            output.append("")
            continue
        if fence is not None:
            if (
                match
                and match[1][0] == fence[0]
                and len(match[1]) >= fence[1]
                and not match[2].strip()
            ):
                fence = None
            output.append("")
            continue
        output.append("" if line.startswith(("    ", "\t")) else line)
    return "\n".join(output)


# 扫描结果同时保存正文、链接、输入摘要与降级原因。
# partial 说明本轮读取边界，不能通过已有章节数推断是否完整。
@dataclass(frozen=True, slots=True)
class DocumentScan:
    """Complete output of one bounded Markdown ingestion pass."""

    sections: list[dict[str, Any]]
    markdown_links: dict[str, list[str]]
    input_digests: dict[str, str]
    partial: bool
    issues: list[dict[str, Any]]
    read_bytes: int = 0

    def as_legacy_tuple(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        dict[str, list[str]],
        dict[str, str],
        bool,
        list[dict[str, Any]],
    ]:
        """Expose the pre-refactor tuple for compatibility facades."""

        return (
            self.sections,
            self.markdown_links,
            self.input_digests,
            self.partial,
            self.issues,
        )


# 索引身份使用稳定键序与紧凑编码，不受字典构造顺序影响。
def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# YAML 元数据转换为可序列化形状，特殊对象不直接进入检索协议。
def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


# 来源类型、权威性与所属范围分别表达，目录存在不意味着人工确认。
# 业务索引是导航，业务正文才携带人工维护来源。
# 团队约束保留文档声明身份，不自动升级成人工授权。
def classify_document(relative: str) -> tuple[str, str, dict[str, str | None]]:
    """Classify a knowledge path into source, authority, and ownership scope."""

    parts = relative.split("/")
    scope: dict[str, str | None] = {
        "memberId": None,
        "domain": None,
        "module": None,
    }
    if "/handbook/references/business/" in f"/{relative}":
        if relative.endswith("/index.md"):
            return "workspace-business-router", "routing-authority", scope
        return "workspace-business", "human-authority", scope
    if "/handbook/references/generated/members/" in f"/{relative}":
        scope["memberId"] = Path(relative).stem
        return "workspace-generated", "authored-projection", scope
    if "/handbook/references/generated/" in f"/{relative}":
        return "workspace-generated", "authored-projection", scope
    if relative.endswith("/handbook/SKILL.md"):
        return "workspace-router", "routing-authority", scope
    if "/knowledge/constraint/" in f"/{relative}":
        if is_team_standard_path(relative):
            return "project-constraint", "document-declaration", scope
        return "project-constraint", "human-authority", scope
    if relative.endswith("/knowledge/architecture-overview.md"):
        return "project-router", "routing-authority", scope
    try:
        domain_index = parts.index("domain")
        scope["domain"] = parts[domain_index + 1]
    except (ValueError, IndexError):
        domain_index = -1
    if "/references/business/" in f"/{relative}":
        if relative.endswith("/index.md"):
            return "project-business-router", "routing-authority", scope
        return "project-business", "human-authority", scope
    if domain_index >= 0 and "modules" in parts:
        scope["module"] = Path(relative).stem
        return "project-module", "authored-projection", scope
    if domain_index >= 0 and relative.endswith("/SKILL.md"):
        return "project-domain", "routing-authority", scope
    if domain_index >= 0:
        return "project-generated", "authored-projection", scope
    return "project-generated", "authored-projection", scope


_FACET_STEMS = {
    "team-standard": "rule",
    "api": "api",
    "downstream": "downstream",
    "infrastructure": "infrastructure",
    "object": "object",
    "rule": "rule",
    "state_machine": "state_machine",
    "contract-map": "api",
    "object-map": "object",
    "infrastructure-map": "infrastructure",
}


_ROLE_FACETS = {
    "contract": "api",
    "data": "object",
    "lifecycle": "state_machine",
    "collaboration": "downstream",
    "runtime": "infrastructure",
    "constraint": "rule",
    "operability": "infrastructure",
    "recovery": "state_machine",
}


_GENERIC_MODULE_HEADING_FACETS = {
    "api": "api",
    "downstream": "downstream",
    "infrastructure": "infrastructure",
    "object": "object",
    "rule": "rule",
    "state machine": "state_machine",
    "状态机": "state_machine",
    "接口": "api",
    "下游": "downstream",
    "基础设施": "infrastructure",
    "对象": "object",
    "规则": "rule",
}

# H3 is a business entry in these canonical facet documents. Elsewhere, H3
# may be a subsection such as Preconditions/Failure and stays with its parent.
_ENTRY_FACET_FILES = {"api", "downstream", "infrastructure", "object", "rule", "state_machine"}
_ENTRY_CONTAINER_HEADINGS = {
    "接口详解",
    "逐对象定义",
    "业务规则详解",
    "安全红线",
    "例外场景",
    "待确认项",
    "场景与行为",
    "下游依赖详解",
    "状态机详解",
    "链路详解",
}

# Best-effort retrieval hints, never an authoring or verification contract.
# Unknown and localized headings remain valid prose; they simply do not receive
# a specialized retrieval facet.
_MODULE_SECTION_ROLES = {
    "模块定位与边界": "boundary",
    "module scope": "boundary",
    "核心场景与行为": "scenario",
    "core scenarios and behavior": "scenario",
    "界面、路由与交互": "interaction",
    "interfaces, routes and interactions": "interaction",
    "接口、命令与扩展点": "contract",
    "contracts, commands and extension points": "contract",
    "对象、数据与状态": "data",
    "objects, data and state": "data",
    "状态与生命周期": "lifecycle",
    "state and lifecycle": "lifecycle",
    "依赖、事件与系统协作": "collaboration",
    "dependencies, events and collaboration": "collaboration",
    "资源、配置与运行": "runtime",
    "resources, configuration and runtime": "runtime",
    "规则、安全与兼容": "constraint",
    "rules, security and compatibility": "constraint",
    "性能、并发与可观测性": "operability",
    "performance, concurrency and observability": "operability",
    "失败、恢复与清理": "recovery",
    "failure, recovery and cleanup": "recovery",
    "设计取舍与扩展边界": "design",
    "design tradeoffs and extension boundaries": "design",
    "实现、扩展与验证": "implementation",
    "implementation, extension and verification": "implementation",
}


def _normalize_contract_heading(heading: str) -> str:
    return re.sub(r"^\d+(?:[.、．]\d+)*[.、．]?\s*", "", heading).strip()


# 角色仅是检索提示，未知或本地化标题仍是合法正文。
# 仅模块正文使用这套角色映射，其他知识类型保留自己的章节语义。
def classify_section_role(relative: str, heading: str) -> str | None:
    """Derive a known Module role as a retrieval hint, never as validation."""

    if "/references/modules/" not in f"/{relative}":
        return None
    return _MODULE_SECTION_ROLES.get(_normalize_contract_heading(heading).casefold())


# 合法显式 facet 优先，随后才使用文件用途与标题线索。
# 模块章节继承的语义不能反过来成为文档核验的强制模板。
def classify_section_facet(
    relative: str, heading: str, frontmatter: Mapping[str, object]
) -> str | None:
    declared = frontmatter.get("facet")
    if isinstance(declared, str) and declared in {
        "api",
        "downstream",
        "infrastructure",
        "object",
        "rule",
        "state_machine",
    }:
        return declared
    path = Path(relative)
    if is_team_standard_path(relative):
        return "rule"
    stem = path.stem
    if stem in _FACET_STEMS:
        return _FACET_STEMS[stem]
    if path.parent.name in {"api", "object"}:
        return path.parent.name
    if "/references/modules/" in f"/{relative}":
        role = classify_section_role(relative, heading)
        if role:
            return _ROLE_FACETS.get(role)
        normalized = _normalize_contract_heading(heading).casefold().replace("_", " ")
        return _GENERIC_MODULE_HEADING_FACETS.get(normalized)
    return None


# 导航层与正文层分开，使检索可以先确定范围再加载细节。
def load_level_for(source_type: str) -> str:
    if source_type in {
        "project-router",
        "project-domain",
        "workspace-router",
        "project-business-router",
        "workspace-business-router",
    }:
        return "L1"
    return "L2"


# 显式非当前状态优先于默认值，子章节不能无声解除父级不确定性。
# 普通自然语言中的计划词不会直接触发状态，需匹配声明格式。
def infer_status(
    text: str, frontmatter: dict[str, Any] | None = None, inherited: str = "current"
) -> str:
    declared = str(
        next(
            (
                (frontmatter or {}).get(key)
                for key in ("status", "factStatus", "state")
                if (frontmatter or {}).get(key) is not None
            ),
            "",
        )
    ).casefold()
    if declared in {"planned", "hypothesis", "deprecated"}:
        return declared
    if inherited != "current":
        return inherited
    lowered = text.casefold()
    if re.search(r"(?:status|状态)\s*[:：]\s*`?hypothesis", lowered):
        return "hypothesis"
    if re.search(r"(?:status|状态)\s*[:：]\s*`?planned", lowered):
        return "planned"
    if re.search(r"(?:status|状态)\s*[:：]\s*`?deprecated", lowered):
        return "deprecated"
    return "current"


# 规则的待确认与退役状态跨标题拆分保留。
# 模块整体已确认也不能把待确认规则提升为当前事实。
# 规则状态不能因父模块已确认而自动升级，保留局部不确定性。
def infer_rule_status(text: str, heading: str, frontmatter: dict[str, Any], inherited: str) -> str:
    """Keep rule uncertainty through heading splits and confirmed module metadata."""
    document_status = infer_status("", frontmatter)
    if document_status != "current":
        return document_status
    if inherited != "current":
        return inherited
    normalized = re.sub(r"^\d+(?:[.、．]\d+)*[.、．]?\s*", "", heading).strip()
    if normalized in {"待确认", "待确认项", "待确认事项"}:
        return "hypothesis"
    if normalized in {"已废弃", "废弃规则"}:
        return "deprecated"
    match = re.search(
        r"(?:status|状态)\s*[:：]\s*`?(current|hypothesis|planned|deprecated|待确认|已废弃)\b",
        text,
        re.IGNORECASE,
    )
    if match:
        value = match[1].casefold()
        return {"待确认": "hypothesis", "已废弃": "deprecated"}.get(value, value)
    if re.search(r"性质\s*[:：]\s*待确认事项", text):
        return "hypothesis"
    return infer_status(text)


# 规则可检索只表示存在材料，不表示该规则已获用户批准或适用于当前修改。
def is_rule_evidence(item: Mapping[str, Any]) -> bool:
    """Rule evidence availability is not human approval or normative strength."""
    if item.get("status") != "current":
        return False
    source = item.get("sourceType")
    authority = item.get("authority")
    return (
        (
            source in {"workspace-business", "project-business", "project-constraint"}
            and authority == "human-authority"
        )
        or (source == "project-constraint" and authority == "document-declaration")
        or (
            source in {"project-generated", "project-module"}
            and authority == "authored-projection"
            and item.get("facet") == "rule"
        )
    )


def matches_knowledge_need(need: str, item: Mapping[str, Any]) -> bool:
    """分开提示业务正文与工程约束到场，保留旧 business-rule 的宽泛兼容语义。"""
    if need == "business-rule":
        return is_rule_evidence(item)
    if item.get("status") != "current" or item.get("loadLevel") == "L1":
        return False
    text = str(item.get("text") or item.get("excerpt") or "")
    if not any(
        line.strip() and not line.lstrip().startswith(("#", "<a ", "{{item:"))
        for line in text.splitlines()
    ):
        return False
    if need == "domain-knowledge":
        return bool((item.get("scope") or {}).get("domain")) and item.get("sourceType") in {
            "project-generated",
            "project-module",
            "project-business",
        }
    if need == "engineering-constraint":
        return item.get("sourceType") == "project-constraint" and is_rule_evidence(item)
    return False


# 仅跳过有闭合边界的 frontmatter，损坏元数据不能吞掉整篇正文。
# 前置元数据不作为正文证据，行号偏移仍需保留供定位。
def body_start(lines: list[str]) -> int:
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, min(len(lines), 4096)):
        if lines[index].strip() == "---":
            return index + 1
    return 0


# 代码围栏与缩进代码中的井号不能切分知识章节。
# 同时支持 ATX 与 Setext 标题，保持常见 Markdown 写法可读。
def markdown_headings(lines: list[str], start: int = 0) -> list[tuple[int, int, str]]:
    """Recognize Markdown headings outside backtick/tilde fences and indented code.

    Fence closing requires the same character and at least the opening length;
    a shorter embedded fence is source text, not a new document section.
    """
    headings: list[tuple[int, int, str]] = []
    fence: tuple[str, int] | None = None
    for index in range(start, len(lines)):
        line = lines[index]
        fence_match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if (
                fence_match
                and fence_match[1][0] == fence[0]
                and len(fence_match[1]) >= fence[1]
                and not fence_match[2].strip()
            ):
                fence = None
            continue
        if fence_match and not (fence_match[1][0] == "`" and "`" in fence_match[2]):
            fence = (fence_match[1][0], len(fence_match[1]))
            continue
        _append_markdown_heading(lines, index, start, headings)
    return headings


def _append_markdown_heading(
    lines: list[str], index: int, start: int, headings: list[tuple[int, int, str]]
) -> None:
    """调用方排除围栏后，在正文中识别 ATX 与 Setext 标题。"""
    line = lines[index]
    match = _HEADING_RE.match(line[0:]) if not line.startswith(("    ", "\t")) else None
    if match is None and line.startswith(" ") and not line.startswith("    "):
        match = _HEADING_RE.match(line.lstrip(" "))
    if match:
        title = re.sub(r"\s+#+\s*$", "", match[2]).strip()
        headings.append((index, len(match[1]), title))
    elif index > start and re.fullmatch(r" {0,3}(?:=+|-+)\s*", line):
        previous = lines[index - 1]
        if (
            previous.strip()
            and not previous.startswith(("    ", "\t"))
            and not re.match(r"^\s*(?:#|[-*+]>?|>|```|~~~)", previous)
        ):
            if not headings or headings[-1][0] != index - 1:
                headings.append(
                    (index - 1, 1 if line.lstrip().startswith("=") else 2, previous.strip())
                )


# 文件大小、总读取量和截止时间共同约束扫描。
# 单个不可读文档产生发现后继续，整体超预算则保留已完成结果。
# 约束种子仍参与新鲜度摘要，但不被当作已经成立的项目规则。
# 章节身份由路径和行范围生成，文本摘要另行描述内容版本。
def scan_documents(
    paths: ModusPaths,
    targets: list[Path],
    *,
    deadline_monotonic: float | None = None,
    max_document_bytes: int = MAX_DOCUMENT_BYTES,
    max_scan_bytes: int = MAX_SCAN_BYTES,
) -> DocumentScan:
    """Read and segment documents while preserving deterministic partial results.

    The byte limits are explicit injection points so callers can tighten resource
    policy without mutating this module's globals.  The compatibility facade in
    :mod:`modus.retrieval.stages.sections` uses them to preserve its historical
    monkeypatch surface.
    """
    records: list[dict[str, Any]] = []
    links: dict[str, list[str]] = {}
    total_bytes = 0
    inputs = {}
    limited = False
    scan_issues: list[dict[str, Any]] = []
    for target in targets:
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            limited = True
            scan_issues.append({"type": "knowledge-budget", "reason": "section-scan-deadline"})
            break
        try:
            text = read_bound_regular_text(paths.root, target, max_bytes=max_document_bytes)
        except (BoundKnowledgeReadError, OSError) as exc:
            limited = True
            scan_issues.append(
                {
                    "type": "knowledge-read",
                    "path": str(target.relative_to(paths.root)),
                    "reason": getattr(exc, "kind", "unreadable-file"),
                }
            )
            continue
        try:
            relative = paths.relative(target)
        except BoundKnowledgeReadError:
            continue
        total_bytes += len(text.encode("utf-8"))
        if total_bytes > max_scan_bytes:
            limited = True
            scan_issues.append(
                {"type": "knowledge-budget", "path": relative, "reason": "scan-byte-budget"}
            )
            break
        # 仅完整读入且在总预算内的文档计入本轮输入摘要。
        # 摘要用于后续索引新鲜度判断，不代表正文事实已核验。
        inputs[relative] = content_digest(text)
        # Keep the digest in index freshness, but do not offer authoring prompts
        # as established project rules. Ordinary reads never fill these seeds.
        if is_constraint_seed(relative, text):
            links[relative] = []
            continue
        frontmatter, _body = split_frontmatter(text)
        lines = text.splitlines()
        start = body_start(lines)
        if lines and lines[0].strip() == "---" and (_body == text or not start):
            scan_issues.append(
                {
                    "type": "knowledge-frontmatter",
                    "path": relative,
                    "reason": "invalid-frontmatter",
                    "fallback": "read-body-without-metadata",
                }
            )
        headings = markdown_headings(lines, start)
        if headings and any(line.strip() for line in lines[start : headings[0][0]]):
            headings.insert(0, (start, 1, str(frontmatter.get("name") or target.stem)))
        if not headings:
            title = str(frontmatter.get("name") or target.stem)
            headings = [(start, 1, title)]
        source_type, authority, scope = classify_document(relative)
        file_links: list[str] = []
        for match in _LINK_RE.finditer(text):
            raw_link = match.group(1).split("#", 1)[0].strip()
            if not raw_link or raw_link.startswith(("http://", "https://", "#", "/")):
                continue
            candidate = (target.parent / raw_link).resolve()
            try:
                candidate.relative_to(paths.knowledge_dir)
            except ValueError:
                continue
            normalized_link = paths.relative(candidate)
            if candidate.is_symlink() or normalized_link in file_links:
                continue
            # 链接目标限定在知识树中，外部 URL 和绝对路径不进入本地导航图。
            # 同一文档的重复目标只保留一条，避免导航权重被重复链接放大。
            file_links.append(normalized_link)
        file_links.sort()
        links[relative] = file_links
        # 标题栈保留父级角色、主题与状态，子章节可继承阅读上下文。
        # 子树终点单独计算，用于构造完整条目的继续阅读范围。
        heading_context: list[dict[str, Any]] = []
        heading_counts: defaultdict[str, int] = defaultdict(int)
        subtree_ends = [len(lines)] * len(headings)
        open_headings: list[int] = []
        for ordinal, (line_index, level, _heading) in enumerate(headings):
            while open_headings and headings[open_headings[-1]][1] >= level:
                subtree_ends[open_headings.pop()] = line_index
            open_headings.append(ordinal)
        for ordinal, (line_index, level, heading) in enumerate(headings):
            end_index = headings[ordinal + 1][0] if ordinal + 1 < len(headings) else len(lines)
            section_text = "\n".join(lines[line_index:end_index]).strip()
            if not section_text:
                continue
            identity = f"{relative}#{line_index + 1}:{end_index}"
            load_level = load_level_for(source_type)
            while heading_context and heading_context[-1]["level"] >= level:
                heading_context.pop()
            own_role = classify_section_role(relative, heading)
            section_role = own_role or (
                heading_context[-1]["sectionRole"] if heading_context else None
            )
            own_facet = classify_section_facet(relative, heading, frontmatter)
            facet = own_facet or (heading_context[-1]["facet"] if heading_context else None)
            inherited_status = heading_context[-1]["status"] if heading_context else "current"
            status = (
                infer_rule_status(section_text, heading, frontmatter, inherited_status)
                if facet == "rule"
                else infer_status(section_text, frontmatter, inherited_status)
            )
            prose = strip_fenced_code(section_text)
            own_items = sorted(
                set(_ITEM_ID_RE.findall(prose)) | set(_ITEM_ANCHOR_RE.findall(prose))
            )
            slug = markdown_slug(heading)
            occurrence = heading_counts[slug]
            heading_counts[slug] += 1
            section_anchors = [slug if occurrence == 0 else f"{slug}-{occurrence}"]
            section_anchors.extend(match.casefold() for match in _HTML_ANCHOR_RE.findall(prose))
            section_anchors.extend(f"item-{item}".casefold() for item in own_items)
            parent = heading_context[-1] if heading_context else None
            normalized_heading = re.sub(
                r"^\d+[.、．]\s*", "", heading.casefold().replace("_", " ").strip()
            )
            facet_heading = (
                own_role is not None
                or normalized_heading in _GENERIC_MODULE_HEADING_FACETS
                or normalized_heading in _ENTRY_CONTAINER_HEADINGS
            )
            # 显式条目标记、主题条目及状态变化都会开启新交付单元。
            # 普通失败/前置条件子章节应跟随其业务条目，避免只返回成功路径。
            new_entry = (
                bool(own_items)
                or level <= 2
                or (level == 3 and Path(relative).stem in _ENTRY_FACET_FILES)
                or (level == 3 and Path(relative).parent.name in {"api", "object"})
                or parent is None
                or bool(parent["facetHeading"] and level > parent["level"])
                or bool(parent and status != parent["status"])
            )
            entry_ordinal = ordinal if new_entry or parent is None else int(parent["entryOrdinal"])
            item_ids = own_items or (list(parent["itemIds"]) if parent and not new_entry else [])
            heading_path = [item["heading"] for item in heading_context] + [heading]
            heading_context.append(
                {
                    "level": level,
                    "heading": heading,
                    "facet": facet,
                    "sectionRole": section_role,
                    "ownFacet": own_facet,
                    "facetHeading": facet_heading,
                    "status": status,
                    "entryOrdinal": entry_ordinal,
                    "itemIds": item_ids,
                }
            )
            # 内部行索引从零开始，公开行范围统一转换为一基。
            # 条目范围与当前小章节范围同时保留，分别服务交付和排序。
            entry_range = {
                "lineStart": headings[entry_ordinal][0] + 1,
                "lineEnd": max(headings[entry_ordinal][0] + 1, subtree_ends[entry_ordinal]),
            }
            records.append(
                {
                    "id": "ev-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
                    "path": relative,
                    "heading": heading,
                    "headingPath": heading_path,
                    "anchors": list(dict.fromkeys(section_anchors)),
                    "entryRange": entry_range,
                    "_entryOrdinal": entry_ordinal,
                    "readTarget": {"path": relative, **entry_range},
                    "layer": "narrative",
                    "headingLevel": level,
                    "lineStart": line_index + 1,
                    "lineEnd": max(line_index + 1, end_index),
                    "frontmatter": json_safe(frontmatter),
                    "frontmatterLineEnd": start,
                    "sourceLocations": json_safe(
                        (frontmatter.get("anchors") or {}).get("locations", [])
                    )
                    if isinstance(frontmatter.get("anchors"), dict)
                    else [],
                    "provenance": json_safe(
                        {
                            key: frontmatter[key]
                            for key in (
                                "source",
                                "sources",
                                "sourceVersion",
                                "factStatus",
                                "classification",
                                "authoredBy",
                                "reviewedAt",
                                "verifiedAt",
                                "sourceDigest",
                                "sourceCommit",
                                "evidence",
                            )
                            if key in frontmatter
                        }
                    ),
                    "sourceType": source_type,
                    "loadLevel": load_level,
                    "facet": facet,
                    "sectionRole": section_role,
                    "itemIds": item_ids,
                    "parentRouter": None,
                    "authority": authority,
                    "status": status,
                    "scope": scope,
                    "digest": content_digest(section_text),
                    "text": section_text,
                }
            )
    # 统一排序后再绑定逻辑条目，避免输入目标顺序影响分组。
    # 扫描发现与部分结果一起交付，调用方能够解释缺口。
    records.sort(key=lambda item: (item["path"], item["lineStart"], item["id"]))
    _bind_entry_ranges(records)
    _bind_parent_routers(records)
    return DocumentScan(
        sections=records,
        markdown_links=dict(sorted(links.items())),
        input_digests=inputs,
        partial=limited,
        issues=scan_issues,
        read_bytes=total_bytes,
    )


# 排序后的相邻片段按条目身份和状态合并。
# 不同状态必须断开，避免把不确定子项包装在 current 摘录内。
# 临时 entryOrdinal 只用于分组，交付前移除内部字段。
# 父章节引言与子条目分开交付，避免同一正文被多个入口重复引用。
def _bind_entry_ranges(records: list[dict[str, Any]]) -> None:
    """Publish contiguous, same-status entry spans, excluding nested entries.

    A chapter's introductory text is navigation, not all of its independently
    retrievable children. A status boundary also ends a group so an uncertain
    or retired subsection is never presented under a current parent's label.
    """
    group: list[dict[str, Any]] = []
    previous: tuple[str, int, str] | None = None

    def bind() -> None:
        if not group:
            return
        entry_range = {"lineStart": group[0]["lineStart"], "lineEnd": group[-1]["lineEnd"]}
        for record in group:
            record["entryRange"] = dict(entry_range)
            record["readTarget"] = {"path": record["path"], **entry_range}

    for record in records:
        key = (record["path"], record.pop("_entryOrdinal"), record["status"])
        if key != previous:
            bind()
            group = []
        group.append(record)
        previous = key
    bind()


# 优先绑定所属领域导航，无领域时再选项目或工作区总入口。
# 父路由使用证据 ID，使正文与导航可以一起去重交付。
# 父路由提供导航上下文，不替代所选子条目的具体证据。
def _bind_parent_routers(records: list[dict[str, Any]]) -> None:
    l1 = [item for item in records if item.get("loadLevel") == "L1"]
    domain_routers: dict[str, str] = {}
    project_router = next(
        (item["id"] for item in l1 if item.get("sourceType") == "project-router"), None
    )
    workspace_router = next(
        (item["id"] for item in l1 if item.get("sourceType") == "workspace-router"), None
    )
    for item in l1:
        domain = (item.get("scope") or {}).get("domain")
        if domain and item.get("sourceType") == "project-domain":
            domain_routers.setdefault(str(domain), item["id"])
    for item in records:
        if item.get("loadLevel") != "L2":
            continue
        domain = (item.get("scope") or {}).get("domain")
        item["parentRouter"] = (
            domain_routers.get(str(domain))
            if domain
            else (
                workspace_router
                if item.get("sourceType", "").startswith("workspace-")
                else project_router
            )
        )


# 同一条目可通过领域、模块、契约、符号或条目 ID 定位。
# 这些索引只关联既有章节，不创建新的事实关系。
# 输出排序去重，使同一元数据的重复声明不放大命中。
def build_link_index(
    records: list[dict[str, Any]], markdown_links: dict[str, list[str]]
) -> dict[str, Any]:
    mappings: dict[str, defaultdict[str, list[str]]] = {
        "members": defaultdict(list),
        "domains": defaultdict(list),
        "modules": defaultdict(list),
        "contracts": defaultdict(list),
        "symbols": defaultdict(list),
        "items": defaultdict(list),
    }
    for record in records:
        scope = record.get("scope") or {}
        for mapping, key in (
            ("members", scope.get("memberId")),
            ("domains", scope.get("domain")),
        ):
            if key and record["id"] not in mappings[mapping][str(key)]:
                mappings[mapping][str(key)].append(record["id"])
        if scope.get("module"):
            module_key = "/".join(
                item for item in (scope.get("domain"), scope.get("module")) if item
            )
            mappings["modules"][module_key].append(record["id"])

        frontmatter = record.get("frontmatter") or {}
        for field in ("contractKey", "contract", "schema", "api"):
            value = frontmatter.get(field) if isinstance(frontmatter, dict) else None
            values = value if isinstance(value, list) else [value]
            for item in values:
                if item:
                    mappings["contracts"][str(item)].append(record["id"])
        anchors = frontmatter.get("anchors") if isinstance(frontmatter, dict) else None
        if isinstance(anchors, dict):
            for symbol in anchors.get("symbols") or []:
                if symbol:
                    mappings["symbols"][str(symbol)].append(record["id"])
        if record["path"].endswith("contract-map.md"):
            for contract_key in re.findall(r"(?m)^- `([^`]+)`", record.get("text") or ""):
                mappings["contracts"][contract_key].append(record["id"])
        for item_id in record.get("itemIds") or []:
            mappings["items"][str(item_id)].append(record["id"])

    return {
        "markdown": markdown_links,
        **{
            name: {key: sorted(set(evidence_ids)) for key, evidence_ids in sorted(values.items())}
            for name, values in mappings.items()
        },
    }


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "MAX_DOCUMENT_BYTES",
    "MAX_INDEX_BYTES",
    "MAX_SCAN_BYTES",
    "DocumentScan",
    "build_link_index",
    "canonical_json",
    "classify_document",
    "content_digest",
    "is_rule_evidence",
    "json_safe",
    "markdown_headings",
    "scan_documents",
]
