"""Project explicit entry, effect and resource signals into the evidence model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from modus.config import (
    AuthoringRule,
    ModusConfig,
    RuleEmit,
    RuleMatch,
    parse_authoring_rules,
)
from modus.machine.corpus.input_snapshot import read_bytes
from modus.machine.errors import ConfigurationError, safe_error_summary
from modus.paths import ModusPaths

_MAX_PACK_BYTES = 1024 * 1024
_MAX_HITS_PER_RULE_AND_FILE = 64
_OPENAPI_ENTRY = re.compile(
    r"@OpenApi(?P<verb>Get|Post|Put|Patch|Delete)Mapping\s*\("
    r"(?P<arguments>.*?)\)\s*(?:public\s+)?[\w<>, ?\[\].]+\s+"
    r"(?P<method>[A-Za-z_]\w*)\s*\(",
    re.DOTALL,
)
_NAMED_ARGUMENT = re.compile(r"(?P<name>apiName|apiUrl)\s*=\s*[\"'](?P<value>[^\"']+)[\"']")
# 内置规则分别观察入口、副作用与资源，输出协议保持一致。
# 这些模式提供调查线索，命中名称本身不构成业务语义证明。
_BUILTIN_RULES = (
    AuthoringRule(
        "builtin.http-entry",
        RuleMatch(r"(?im)@(?:Get|Post|Put|Patch|Delete|Request)Mapping\s*\(([^)]*)\)"),
        RuleEmit("entry", "external-http"),
    ),
    AuthoringRule(
        "builtin.scheduled-entry",
        RuleMatch(r"(?im)@(?:Scheduled|XxlJob)\s*\(([^)]*)\)"),
        RuleEmit("entry", "job"),
    ),
    AuthoringRule(
        "builtin.message-entry",
        RuleMatch(
            r"(?im)@(?:KafkaListener|RabbitListener|JmsListener|RocketMQMessageListener)\s*\(([^)]*)\)"
        ),
        RuleEmit("entry", "mq"),
    ),
    AuthoringRule(
        "builtin.rpc-entry",
        RuleMatch(r"(?im)\b(@GrpcService|@RpcService|rpc\s+[A-Za-z_]\w*)\b"),
        RuleEmit("entry", "external-rpc"),
    ),
    AuthoringRule(
        "builtin.cli-entry",
        RuleMatch(
            r"(?im)\b(@Command|@CliCommand|click\.command|typer\.(?:Typer|command)|cobra\.Command)\b"
        ),
        RuleEmit("entry", "cli"),
    ),
    AuthoringRule(
        "builtin.transaction-boundary",
        RuleMatch(r"(?im)(@Transactional\b|\btransaction\s*\(|\bBEGIN\s+TRANSACTION\b)"),
        RuleEmit("effect", "transaction"),
    ),
    AuthoringRule(
        "builtin.lock-boundary",
        RuleMatch(r"(?im)(\block\s*\(|\bacquire\s*\(|\bFOR\s+UPDATE\b|@Lock\b)"),
        RuleEmit("effect", "lock"),
    ),
    AuthoringRule(
        "builtin.idempotency-boundary",
        RuleMatch(r"(?im)\b(idempotenc(?:y|e)|deduplicat(?:e|ion)|request[_-]?id)\b"),
        RuleEmit("effect", "idempotency"),
    ),
    AuthoringRule(
        "builtin.authoritative-write",
        RuleMatch(r"(?im)\b(save|insert|update|delete|upsert|commit|publish|send)\s*\("),
        RuleEmit("effect", "authoritative-write"),
    ),
    AuthoringRule(
        "builtin.state-enum",
        RuleMatch(r"(?im)\b(?:enum\s+\w*(?:State|Status)|(?:State|Status)\s*=)\b"),
        RuleEmit("effect", "state"),
    ),
    AuthoringRule(
        "builtin.table-resource",
        RuleMatch(
            r"(?im)(?:@Table(?:Name)?\s*\(|\b(?:from|into|update|join)\s+[`\"]?([A-Za-z_]\w*))"
        ),
        RuleEmit("resource", "table"),
    ),
    AuthoringRule(
        "builtin.cache-resource",
        RuleMatch(
            r"(?im)\b(@Cacheable|@CachePut|@CacheEvict|redis|memcached|"
            r"cache\.(?:get|set|put))\b"
        ),
        RuleEmit("resource", "cache"),
    ),
    AuthoringRule(
        "builtin.message-target",
        RuleMatch(r"(?im)\btopics?\s*=\s*[\"']([^\"']+)[\"']"),
        RuleEmit("resource", "topic"),
    ),
    AuthoringRule(
        "builtin.queue-target",
        RuleMatch(r"(?im)\bqueues?\s*=\s*[\"']([^\"']+)[\"']"),
        RuleEmit("resource", "queue"),
    ),
    AuthoringRule(
        "builtin.configuration-resource",
        RuleMatch(
            r"(?im)(?:getenv|@Value|config(?:uration)?\.(?:get|require))\s*\(?[\"']([^\"']+)"
        ),
        RuleEmit("resource", "config"),
    ),
)


# 冻结后的规则与加载诊断一同返回，部分规则包失败不会抹去内置能力。
@dataclass(frozen=True, slots=True)
class LoadedAuthoringRules:
    rules: tuple[AuthoringRule, ...]
    diagnostics: tuple[dict[str, str], ...] = ()


# 内置、内联和外部规则共用同一校验契约。
# 规则包限制在仓库内，并限制字节数，避免无界读取。
# 重复 ID 会破坏证据溯源，因此合并后作为配置错误拒绝。
def load_authoring_rules(paths: ModusPaths, config: ModusConfig) -> LoadedAuthoringRules:
    """Freeze rule packs and validate them through the inline rule contract."""

    rules = [*_BUILTIN_RULES, *config.init_analysis.authoring_rules.rules]
    diagnostics: list[dict[str, str]] = []
    for configured in config.init_analysis.authoring_rules.packs:
        target = (paths.root / configured).resolve()
        try:
            target.relative_to(paths.root)
            # 复用受边界约束的读取函数，规则配置不能任意打开仓库外文件。
            raw = read_bytes(paths.root, target)
            if len(raw) > _MAX_PACK_BYTES:
                raise ConfigurationError("machine.facts.authoring-pack-too-large")
            value = yaml.safe_load(raw)
            # 严格限制顶层字段，避免拼写错误被静默忽略。
            if not isinstance(value, dict) or set(value) != {"schemaVersion", "rules"}:
                raise ConfigurationError("machine.facts.invalid-authoring-pack-fields")
            if value.get("schemaVersion") != 1:
                raise ConfigurationError("machine.facts.invalid-authoring-pack-schema")
            # 保留规则包路径作为来源，诊断可定位到具体配置。
            rules.extend(parse_authoring_rules(value.get("rules"), source=configured))
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            diagnostics.append(
                {
                    "reasonCode": "machine.facts.authoring-pack-unavailable",
                    "path": configured,
                    "summary": safe_error_summary(exc),
                }
            )
    # 唯一性覆盖内置规则与全部外部来源，防止后加载规则偷偷覆盖前者。
    duplicates = sorted(
        {item.id for item in rules if sum(other.id == item.id for other in rules) > 1}
    )
    if duplicates:
        raise ConfigurationError("machine.facts.duplicate-authoring-rule")
    return LoadedAuthoringRules(tuple(rules), tuple(diagnostics))


# 优先使用捕获组作为证据值，并压缩空白、限制长度。
# 规则命中只保存局部摘要，不复制整段业务源码。
# 截断只影响展示值，规则身份和源码位置仍用于回查完整上下文。
def _matched_value(match: re.Match[str]) -> str:
    if match.lastindex and match.group(1):
        return " ".join(match.group(1).split())[:160]
    return " ".join(match.group(0).split())[:160]


# 正则信号服务于知识创作，不能替代编译器语义。
# 普通规则始终标注启发式等级，并保留规则 ID 与源码行号。
# 每条规则在单文件内限制命中数，控制产物规模。
def bind_authoring_records(
    records: list[dict[str, Any]],
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """N3 只协调已观察的信号与声明，不再次扫描源码规则。"""
    from modus.machine.facts.entry_observation import declaration_aliases

    aliases = declaration_aliases(entries or [])
    by_id = {str(row["entryId"]): row for row in entries or []}
    # 先建立入口区间表，随后所有规则共享同一归属选择。
    owners: list[tuple[int, int, dict[str, Any]]] = []
    for entry in entries or []:
        location = entry.get("location") or {}
        if not isinstance(location, dict):
            continue
        start = location.get("startLine")
        end = location.get("endLine", start)
        if isinstance(start, int) and not isinstance(start, bool):
            owners.append((start, end if isinstance(end, int) else start, entry))

    # 只绑定完整包含命中范围的最小声明；邻近声明不是归属证据。
    # OpenAPI 注解显式命名方法，以该声明位置绑定，不能落到前一个方法。
    def bind_owner(record: dict[str, Any], declaration_line: int | None = None) -> None:
        location = record.get("location") or {}
        first = declaration_line or location.get("startLine")
        last = declaration_line or location.get("endLine", first)
        if not isinstance(first, int) or not isinstance(last, int):
            return
        containing = [item for item in owners if item[0] <= first <= last <= item[1]]
        if declaration_line is None:
            # 同一行可能有类型和多个成员；按字节列排除并未包含命中的声明。
            containing = [
                item
                for item in containing
                if (
                    item[0] < first
                    or not item[2]["location"].get("startColumn")
                    or not location.get("startColumn")
                    or item[2]["location"]["startColumn"] <= location["startColumn"]
                )
                and (
                    item[1] > last
                    or not item[2]["location"].get("endColumn")
                    or not location.get("endColumn")
                    or item[2]["location"]["endColumn"] >= location["endColumn"]
                )
            ]
        if declaration_line is not None:
            containing = [
                item for item in containing if item[2].get("declarationName") == record["symbol"]
            ]
        if not containing:
            return
        span = min(end - start for start, end, _entry in containing)
        smallest = [entry for start, end, entry in containing if end - start == span]
        groups = {aliases.get(str(row["entryId"]), str(row["entryId"])) for row in smallest}
        if len(groups) != 1:
            return
        owner = by_id[next(iter(groups))]
        record["entryId"] = str(owner["entryId"])
        record["symbol"] = str(owner.get("symbol") or owner.get("displayName") or "")
        if owner.get("signature"):
            record["signature"] = str(owner["signature"])
            if owner.get("signatureOmittedCharacters"):
                record["signatureOmittedCharacters"] = owner["signatureOmittedCharacters"]

    result = [dict(row) for row in records]
    for record in result:
        bind_owner(record, record.pop("declarationLine", None))
    return result


def project_authoring_records(
    relative: str,
    content: str,
    rules: tuple[AuthoringRule, ...],
    *,
    entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return bounded, source-anchored signals without composing business prose."""

    result: list[dict[str, Any]] = []

    # 专用 OpenAPI 注解保留方法、路由和显示名的组合契约。
    for match in _OPENAPI_ENTRY.finditer(content):
        arguments = {
            item.group("name"): item.group("value")
            for item in _NAMED_ARGUMENT.finditer(match.group("arguments"))
        }
        route = arguments.get("apiUrl")
        # 缺少路由的注解不足以建立入口契约，跳过而不猜测地址。
        if not route:
            continue
        verb = match.group("verb").upper()
        start_line = content.count("\n", 0, match.start()) + 1
        record = {
            "kind": "entry",
            "evidenceKind": "external-http",
            "ruleId": "builtin.openapi-entry",
            "value": f"{verb} {route}",
            "contract": f"http:{verb}:{route}",
            "displayName": arguments.get("apiName", ""),
            "symbol": match.group("method"),
            "location": {
                "path": relative,
                "startLine": start_line,
                "endLine": content.count("\n", 0, match.end()) + 1,
            },
            "resolution": "exact",
            "sourceLayer": "cst",
        }
        record["declarationLine"] = content.count("\n", 0, match.start("method")) + 1
        result.append(record)
    # 后缀限制按大小写无关形式比较，保持规则包跨平台一致。
    suffix = Path(relative).suffix.casefold()
    for rule in rules:
        if rule.match.suffixes and suffix not in {item.casefold() for item in rule.match.suffixes}:
            continue
        # 规则在配置入口已验证，此处仅构造用于当前文件的匹配器。
        pattern = re.compile(rule.match.regex, re.MULTILINE)
        for position, match in enumerate(pattern.finditer(content)):
            # 提前终止单条规则的遍历，而非在生成无界结果后截断。
            if position >= _MAX_HITS_PER_RULE_AND_FILE:
                break
            value = _matched_value(match)
            if not value:
                continue
            start_line = content.count("\n", 0, match.start()) + 1
            # 契约模板只替换命中值，不执行插值表达式或项目代码。
            record = {
                "kind": rule.emit.type,
                "evidenceKind": rule.emit.kind,
                "ruleId": rule.id,
                "value": value,
                "contract": rule.emit.contract.replace("{value}", value),
                "observation": rule.emit.observation,
                "location": {
                    "path": relative,
                    "startLine": start_line,
                    "startColumn": len(
                        content[content.rfind("\n", 0, match.start()) + 1 : match.start()].encode()
                    )
                    + 1,
                    "endLine": content.count("\n", 0, match.end()) + 1,
                    "endColumn": len(
                        content[content.rfind("\n", 0, match.end()) + 1 : match.end()].encode()
                    )
                    + 1,
                },
                "resolution": "heuristic",
                "sourceLayer": "cst",
            }
            result.append(record)
    return bind_authoring_records(result, entries) if entries is not None else result


__all__ = [
    "LoadedAuthoringRules",
    "load_authoring_rules",
    "project_authoring_records",
]
