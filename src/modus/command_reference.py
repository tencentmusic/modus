"""命令元数据的唯一目录。

终端命令、助手工作流和自动技能有不同的调用位置。注册与帮助复用此处的
语义说明，避免公开入口与文档各自演进；名称是协议，描述面向中文读者。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final, TypeVar

from .surface import AUTOMATIC_SKILLS, EXPLICIT_SKILLS

_CatalogEntry = TypeVar("_CatalogEntry")


# 重复声明在导入时失败，避免后定义的入口静默覆盖先前契约。
def _unique_index(
    entries: Iterable[_CatalogEntry],
    *,
    identity: Callable[[_CatalogEntry], str],
    kind: str,
) -> dict[str, _CatalogEntry]:
    """建立唯一索引，在目录声明阶段拒绝标识冲突。"""

    index: dict[str, _CatalogEntry] = {}
    for entry in entries:
        key = identity(entry)
        if key in index:
            raise RuntimeError(f"{kind}目录中存在重复标识：{key}")
        index[key] = entry
    return index


# 别名与主名称共享唯一性约束，不能让同一个调用名指向两个工作流。
def _unique_pairs(
    entries: Iterable[tuple[str, _CatalogEntry]], *, kind: str
) -> dict[str, _CatalogEntry]:
    """为显式别名建立索引，保留映射对象并拒绝重复声明。"""

    index: dict[str, _CatalogEntry] = {}
    for key, entry in entries:
        if key in index:
            raise RuntimeError(f"{kind}目录中存在重复标识：{key}")
        index[key] = entry
    return index


PANEL_CORE: Final = "终端命令"
PANEL_MAINTENANCE: Final = "维护命令"
PANEL_UTILITIES: Final = "实用命令"
PANEL_ADVANCED: Final = "高级命令"
PANEL_SLASH: Final = "知识工作流（在编程助手中运行）"
PANEL_AUTOMATIC: Final = "自动知识能力"

TIER_COMMON: Final = "common"
TIER_ADVANCED: Final = "advanced"

# Internal workflow adapters are invokable by shipped Skills but are not part
# of the supported human CLI surface.
HIDDEN_CLI_GROUPS: Final[frozenset[str]] = frozenset(
    {
        "context",
        "knowledge",
    }
)

HIDDEN_CLI_KEYS: Final[frozenset[str]] = frozenset()

CORE_CLI_KEYS: Final[frozenset[str]] = frozenset({"init", "update", "help", "uninstall", "status"})
MAINTENANCE_CLI_KEYS: Final[frozenset[str]] = frozenset()
UTILITY_CLI_KEYS: Final[frozenset[str]] = frozenset()


# 名称与调用方式是稳定协议，中文说明可独立演进。
# 分组仅影响可发现性，不改变命令注册与执行能力。
# 隐藏内部入口仍可服务已发布技能的调用需求。
@dataclass(frozen=True, slots=True)
class CliCommand:
    """Metadata for one CLI leaf command."""

    key: str
    short: str
    role: str
    purpose: str
    usage: tuple[str, ...]
    related: tuple[str, ...] = ()
    misuse: str = ""
    tier: str = TIER_ADVANCED

    @property
    def invocation(self) -> str:
        return f"modus {self.key}"

    @property
    def panel(self) -> str:
        if self.key in CORE_CLI_KEYS:
            return PANEL_CORE
        if self.key in MAINTENANCE_CLI_KEYS:
            return PANEL_MAINTENANCE
        if self.key in UTILITY_CLI_KEYS:
            return PANEL_UTILITIES
        return PANEL_ADVANCED

    @property
    def hidden(self) -> bool:
        """True when this command's group (or the command itself) is display-hidden.

        See :data:`HIDDEN_CLI_GROUPS` / :data:`HIDDEN_CLI_KEYS`. Still fully
        invocable for Agent/CI integrations but absent from public help and completion.
        """
        return self.key.split()[0] in HIDDEN_CLI_GROUPS or self.key in HIDDEN_CLI_KEYS


# 助手工作流与终端命令分别建模，避免文档混淆调用位置。
# 别名保留兼容入口，但详细帮助指向同一份主定义。
# 输入类型描述工作流可接收的材料，不是终端参数解析规则。
@dataclass(frozen=True, slots=True)
class SlashCommand:
    """Metadata for a slash command invoked in an agent host."""

    name: str
    short: str
    role: str
    purpose: str
    usage: tuple[str, ...]
    related: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    inputs: tuple[tuple[str, str], ...] = ()
    summary: str = ""
    misuse: str = ""
    mechanism: str = "助手技能"

    def detail_summary(self) -> str:
        """First paragraph of ``modus help /modus-*``."""
        if self.summary:
            return self.summary
        return self.short if self.short.endswith(("。", ".")) else f"{self.short}。"


# --------------------------------------------------------------------------- #
# 终端命令
# --------------------------------------------------------------------------- #

# 终端注册、帮助与文档测试共享这份声明。
# 修改公开入口时应同时核对用途、误用提示及关联命令。
CLI_COMMANDS: Final[tuple[CliCommand, ...]] = (
    CliCommand(
        key="init",
        short="接入 Modus 项目",
        role="项目接入",
        purpose="安装项目资产与平台技能；通过 /modus-init 创作知识。",
        usage=("modus init", "modus init --all-platforms", "modus init --platform dsh"),
        related=("/modus-init",),
        tier="common",
    ),
    CliCommand(
        key="update",
        short="更新 CLI 与项目技能",
        role="更新入口",
        purpose="升级 Modus CLI 或同步项目受管资产。",
        usage=("modus update", "modus update --project"),
        related=("modus init",),
        tier="common",
    ),
    CliCommand(
        key="help",
        short="查看命令帮助",
        role="命令参考",
        purpose="查看五个公开命令、三个知识工作流和两项自动能力。",
        usage=("modus help", "modus help init"),
        tier="common",
    ),
    CliCommand(
        key="uninstall",
        short="卸载 Modus",
        role="卸载入口",
        purpose="默认卸载项目资产与个人 CLI，保留已创作的知识。",
        usage=("modus uninstall --dry-run", "modus uninstall --project --dry-run"),
        related=("modus init",),
        tier="common",
    ),
    CliCommand(
        key="status",
        short="查看安装与知识状态",
        role="只读状态",
        purpose="查看安装与知识状态，无需读取分析缓存。",
        usage=("modus status", "modus status --json"),
        tier="common",
    ),
    CliCommand(
        key="context resolve",
        short="汇集任务证据",
        role="内部只读检索",
        purpose="汇集当前源码、知识正文与约束，无需读取初始化分析。",
        usage=('modus context resolve "question" --scope project-read',),
    ),
    CliCommand(
        key="knowledge verify",
        short="核验知识契约",
        role="内部知识核验",
        purpose="核验结构完整性；发布模式还检查声明的范围、证据与图表。",
        usage=(
            "modus knowledge verify",
            "modus knowledge verify --domain order --json",
            "modus knowledge verify --publication --json",
            "modus knowledge verify --publication --member backend --json",
        ),
    ),
    CliCommand(
        key="knowledge verify-anchors",
        short="核验知识锚点",
        role="内部锚点核验",
        purpose="检查模块锚点与源码引用漂移。",
        usage=("modus knowledge verify-anchors",),
    ),
    CliCommand(
        key="knowledge sync",
        short="查找可能受影响的知识",
        role="内部知识同步",
        purpose="返回待语义评审的正文候选，无需读取初始化分析。",
        usage=("modus knowledge sync --changed-file src/order.py --validation passed",),
    ),
)

CLI_BY_KEY: Final[dict[str, CliCommand]] = _unique_index(
    CLI_COMMANDS,
    identity=lambda command: command.key,
    kind="终端命令",
)


# --------------------------------------------------------------------------- #
# Slash commands (agent host only)
# --------------------------------------------------------------------------- #

_SLASH_METADATA: tuple[SlashCommand, ...] = (
    SlashCommand(
        name="/modus-init",
        short="基于当前证据创建项目知识",
        role="由助手技能驱动的语义创作工作流",
        purpose=(
            "发现项目证据、确认范围、撰写与评审正文，"
            "补全导航；已有正式领域或模块时，"
            "复用重建流程。仅在可读取 kind: workspace 配置时启用"
            "工作区路由：只读盘点成员，再确认是"
            "仅构建外层导航，还是先初始化缺失的成员。"
        ),
        usage=("/modus-init", "/modus-init 按这份完整的领域与模块范围初始化"),
        related=("modus internal init-analysis build", "/modus-reinit"),
        aliases=("/modus:init", "/modus.init"),
        inputs=(
            ("自然语言", "描述需要初始化的完整范围。"),
            (
                "文档",
                "使用文档识别领域与模块，创作项目知识。",
            ),
            (
                "图片",
                "使用图片识别领域与模块，需要支持图片的模型。",
            ),
            (
                "业务页面",
                "使用业务页面识别领域与模块，需要浏览器访问能力。",
            ),
        ),
        summary=("为项目选择初始化或重建；一次确认工作区导航，只读盘点成员。"),
        misuse="终端帮助：modus help /modus-init。",
        mechanism="助手技能",
    ),
    SlashCommand(
        name="/modus-reinit",
        short="沿既有边界重建项目知识",
        role="由助手技能驱动的语义创作工作流",
        purpose=(
            "复用稳定的领域与模块身份，评审完整正文。统一确认"
            "新增、拆分、合并、迁移或退役；无正式范围时使用"
            "初始化。冻结源码，为本轮创建一份证据包；"
            "分析失败时回到当前源码。在原位置修订，"
            "只删除已确认退役的生成正文。"
        ),
        usage=(
            "/modus-reinit",
            "/modus-reinit 重建订单知识并保留人工维护的规则",
        ),
        related=("/modus-init", "/modus-update-knowledge"),
        aliases=("/modus:reinit", "/modus.reinit"),
        inputs=(
            ("自然语言", "描述评审范围与约束。"),
            ("新增领域", "说明需要新增的领域。"),
            ("新增模块", "说明需要新增的模块。"),
        ),
        summary=(
            "未经明确授权，保留人工维护的内容。复用稳定身份，"
            "修订主定义、修复引用、精确退役。跳过"
            "无变化的写入，并明确说明可选机器证据的降级。"
        ),
        misuse="在编程助手中运行；终端帮助：modus help /modus-reinit。",
        mechanism="助手技能",
    ),
    SlashCommand(
        name="/modus-update-knowledge",
        short="根据新事实或材料更新相关知识",
        role="显式调用或通过自然语言路由接收材料",
        purpose=(
            "核对当前源码和材料，确定增量范围，联动受影响的"
            "主定义、消费者与导航；不构建或读取初始化证据包，"
            "也不修改无关知识。人工内容仅在明确委托范围内维护。"
        ),
        usage=("/modus-update-knowledge 将这些需求和截图纳入项目知识",),
        related=("/modus-init", "modus knowledge update"),
        aliases=("/modus:update-knowledge", "/modus.update-knowledge"),
        inputs=(
            ("自然语言", "描述需要新增、修正或保留的知识。"),
            (
                "文档与图片",
                "撰写带来源与版本信息的 Markdown，不复制原始材料。",
            ),
            (
                "链接与页面观察",
                "被动观察页面首次加载，并对网络元数据脱敏。",
            ),
        ),
        summary="更新明确受影响的知识，保留无关文件。",
        misuse=(
            "使用 knowledge update 批量执行基于内容哈希的条件写入；助手"
            "在原位置完成普通修订。只读的 knowledge sync 命令"
            "不接收用户材料。"
        ),
        mechanism="助手技能",
    ),
)

_SLASH_METADATA_BY_NAME = _unique_index(
    _SLASH_METADATA,
    identity=lambda command: command.name,
    kind="斜杠命令",
)
# 显式技能集合决定公开顺序，元数据不能自行新增未发布工作流。
# 别名索引引用原始对象，使摘要与详细帮助始终一致。
SLASH_COMMANDS: Final[tuple[SlashCommand, ...]] = tuple(
    _SLASH_METADATA_BY_NAME[f"/{skill_name}"] for skill_name in EXPLICIT_SKILLS
)

SLASH_BY_NAME: Final[dict[str, SlashCommand]] = _unique_pairs(
    ((key, command) for command in SLASH_COMMANDS for key in (command.name, *command.aliases)),
    kind="斜杠命令或别名",
)

# 自动能力只展示用途，不伪造需要用户输入的斜杠命令。
_AUTOMATIC_SKILL_DESCRIPTIONS: Final[dict[str, str]] = {
    "using-modus": "按需读取项目证据，并在交付代码前判断知识影响",
    "modus-sync-knowledge": "确认知识受影响后，在原位置做必要修订",
}
AUTOMATIC_SKILL_HELP: Final[tuple[tuple[str, str], ...]] = tuple(
    (name, _AUTOMATIC_SKILL_DESCRIPTIONS[name]) for name in AUTOMATIC_SKILLS
)


# 未知主题返回空值，调用方可以继续尝试其他帮助目录。
def lookup_slash(topic: str) -> SlashCommand | None:
    """Return the public slash command for a ``modus help`` topic, if any."""
    return SLASH_BY_NAME.get(topic)


# --------------------------------------------------------------------------- #
# Root help text
# --------------------------------------------------------------------------- #

TOP_LEVEL_HELP: Final = "Modus"

TOP_LEVEL_EPILOG: Final = ""

HELP_OPTION_TEXT: Final = "显示帮助信息。"

UPDATE_COMMAND_HELP: Final = (
    "更新 CLI 安装包与项目技能\n\n"
    "默认更新分为两个阶段：\n"
    "- 升级个人 Modus CLI。\n"
    "- 同步当前项目的受管命令、技能与平台接入文件。\n\n"
    "确认前展示受影响文件。使用 --dry-run 仅预览，或 --yes 直接执行。"
)


# 已注册命令缺少元数据属于开发错误，保留索引异常以尽早发现。
def cli_help(key: str) -> str:
    """Return the short help text for a registered CLI command."""
    return CLI_BY_KEY[key].short


__all__ = [
    "CLI_BY_KEY",
    "CLI_COMMANDS",
    "AUTOMATIC_SKILL_HELP",
    "CORE_CLI_KEYS",
    "HELP_OPTION_TEXT",
    "HIDDEN_CLI_GROUPS",
    "HIDDEN_CLI_KEYS",
    "MAINTENANCE_CLI_KEYS",
    "PANEL_ADVANCED",
    "PANEL_AUTOMATIC",
    "PANEL_CORE",
    "PANEL_MAINTENANCE",
    "PANEL_SLASH",
    "PANEL_UTILITIES",
    "SLASH_BY_NAME",
    "SLASH_COMMANDS",
    "TIER_ADVANCED",
    "TIER_COMMON",
    "TOP_LEVEL_EPILOG",
    "TOP_LEVEL_HELP",
    "UPDATE_COMMAND_HELP",
    "UTILITY_CLI_KEYS",
    "CliCommand",
    "SlashCommand",
    "cli_help",
    "lookup_slash",
]
