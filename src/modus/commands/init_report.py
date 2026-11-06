"""中文接入报告与带所有权说明的目录地图。"""

from __future__ import annotations

import click

from ..platforms.display import ordered_platforms, platform_title
from ..text_tree import TreeNode, render_tree


# 目录树描述接入后的所有权约定，并非实时扫描磁盘。
# 中立接入资产与项目长期知识分别展示，便于理解更新范围。
# 缓存标注为按需创建，避免把示意结构误读成已生成文件。
# 知识目录中的人工主定义不能由接入刷新覆盖。
def _install_tree() -> tuple[TreeNode, ...]:
    knowledge_children = (
        TreeNode(
            "constraint/",
            "约束文档主定义",
            (
                TreeNode(
                    "global-standard.md",
                    "人工维护的全局约束；/modus-init 只读",
                ),
                TreeNode(
                    "team-standard.md",
                    "团队约束种子；/modus-init 首次创作后由人工维护",
                ),
            ),
        ),
        TreeNode(
            "domain/",
            "已确认领域：技能路由、六类专题与模块指南",
        ),
        TreeNode(
            "architecture-overview.md",
            "系统概览与导航；各领域完成后创作",
        ),
    )
    return (
        TreeNode(
            ".modus/",
            "平台中立的接入资产",
            (
                TreeNode("commands/", "命令模板"),
                TreeNode("skills/", "五个知识技能的中立源文件"),
                TreeNode("hooks/", "会话引导脚本"),
                TreeNode("manifest.json", "供 modus update 使用的所有权清单"),
            ),
        ),
        TreeNode(
            "modus/",
            "Modus 项目数据",
            (
                TreeNode(
                    "knowledge/",
                    "项目知识主定义",
                    knowledge_children,
                ),
                TreeNode(
                    ".cache/",
                    "按需创建的临时分析与创作状态",
                ),
            ),
        ),
    )


# 工作区地图突出成员配置与跨仓库导航的职责。
# 这里展示工作区自身资产，不展开或声称创建成员仓库内容。
# 人工业务知识和可重新生成的导航各有明确目录。
# 地图与项目模式分开构造，防止混用两种知识布局。
def _workspace_install_tree() -> tuple[TreeNode, ...]:
    return (
        TreeNode(
            ".modus/",
            "工作区技能、命令与清单",
            (
                TreeNode("config.yaml", "kind: workspace 与已确认成员"),
                TreeNode("commands/"),
                TreeNode("skills/"),
                TreeNode("hooks/"),
                TreeNode("manifest.json"),
            ),
        ),
        TreeNode(
            "modus/",
            "本地工作区导航数据",
            (
                TreeNode(
                    "knowledge/handbook/",
                    "渐进式跨仓库导航",
                    (
                        TreeNode("SKILL.md"),
                        TreeNode("references/business/", "人工维护的知识"),
                        TreeNode("references/generated/", "成员知识与源码导航"),
                    ),
                ),
                TreeNode(".cache/", "按需创建的临时创作状态"),
            ),
        ),
    )


# 只展示实际选择的平台，未知平台不会生成猜测性的路径。
# 平台文件承载入口与适配，知识主定义仍位于中立目录。
# 受管区块与独占文件在说明中区分，反映不同的更新粒度。
# 返回不可变节点序列，由统一树形渲染器决定排版。
def _platform_tree(platforms: list[str]) -> tuple[TreeNode, ...]:
    selected = set(platforms)
    nodes: list[TreeNode] = []
    if "codex" in selected:
        nodes.extend(
            (
                TreeNode(
                    ".agents/",
                    "供 Codex 读取的技能",
                    (TreeNode("skills/"),),
                ),
                TreeNode(".codex/", "", (TreeNode("hooks.json", "Codex 会话钩子"),)),
            )
        )
    if "dsh" in selected:
        nodes.append(TreeNode(".dsh/", "供 DSH 读取的技能", (TreeNode("skills/"),)))
    if selected & {"codex", "dsh"}:
        nodes.append(TreeNode("AGENTS.md", "Modus 共享指引区块"))
    if "codebuddy" in selected:
        nodes.extend(
            (
                TreeNode(
                    ".codebuddy/",
                    "供 CodeBuddy 读取的技能与命令",
                    (
                        TreeNode("skills/"),
                        TreeNode(
                            "commands/",
                            "/modus-init, /modus-reinit, /modus-update-knowledge",
                        ),
                        TreeNode("settings.json", "CodeBuddy 会话钩子"),
                    ),
                ),
                TreeNode("CODEBUDDY.md", "Modus 受管区块中的 CodeBuddy 指引"),
            )
        )
    if "cursor" in selected:
        nodes.append(
            TreeNode(
                ".cursor/",
                "供 Cursor 读取的技能与规则",
                (
                    TreeNode("skills/"),
                    TreeNode("rules/", "", (TreeNode("modus.mdc", "Cursor 常驻指引"),)),
                    TreeNode("hooks.json", "Cursor 会话钩子"),
                ),
            )
        )
    if "claude" in selected:
        nodes.extend(
            (
                TreeNode(
                    ".claude/",
                    "供 Claude Code 读取的技能",
                    (
                        TreeNode("skills/"),
                        TreeNode("settings.json", "Claude Code 会话钩子"),
                    ),
                ),
                TreeNode("CLAUDE.md", "Modus 受管区块中的 Claude Code 指引"),
            )
        )
    return tuple(nodes)


# 成功报告消费接入服务返回的摘要，不再触发文件写入。
# 平台标题和顺序来自共同的显示规则，避免各命令自行排序。
# 项目与工作区共享报告骨架，具体目录图按 kind 选择。
# 成员访问提示明确只读关系，防止将接入理解为复制成员数据。
# 只有平台节点存在时才增加该段，避免产生空树标题。
# 下一步命令保持在末尾，使初次使用者可直接开始知识创作。
def format_init_success(summary: dict) -> str:
    """Human-readable success report for ``modus init``."""
    platforms = ordered_platforms(summary.get("platforms") or [])
    labels = [platform_title(name) for name in platforms]
    workspace_kind = summary.get("kind") == "workspace"
    title = "Modus 工作区已接入" if workspace_kind else "Modus 项目已接入"
    lines = [
        f"{title}： {summary['root']}",
        f"  接入平台： {'、'.join(labels)}" if labels else "  接入平台： ",
        *([f"  工作区成员： {', '.join(summary.get('members') or [])}"] if workspace_kind else []),
        *(["  成员访问：只读引用"] if workspace_kind else []),
        "",
        "  Modus 目录：",
        render_tree(_workspace_install_tree() if workspace_kind else _install_tree()),
    ]
    platform_nodes = _platform_tree(platforms)
    if platform_nodes:
        lines.extend(["", "  编程助手接入文件：", render_tree(platform_nodes)])
    lines.extend(["", click.style("  下一步：在编程助手中运行 /modus-init", bold=True)])
    return "\n".join(lines)
