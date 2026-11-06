"""各平台共享的激活与交付检查规则。

规则不依赖平台实现，各平台常驻指引引用同一份文本，避免行为随宿主漂移。
"""

from typing import Final

_PROJECT_EVIDENCE_ACTIVATION: Final = (
    "当前任务需要本项目的业务知识、工程规范或实现证据时（包括确有项目知识价值的问答、文档或演示材料），"
    "请按需读取 `.modus/skills/using-modus/SKILL.md` 或其平台接入副本。"
    "只加载相关知识；技能、知识、CLI 或缓存缺失不阻塞任务。"
    "与项目无关的任务（如查询股价、翻译给定文本）不加载 using-modus，"
    "不检查 Modus 目录，也不查询项目知识。"
    "面向用户的说明与新创作的知识默认使用简体中文；用户明确指定其他语言时遵从其要求。"
)

_KNOWLEDGE_RETENTION_CHECKPOINT: Final = (
    "使用 using-modus 进行项目实现、公开契约、运行配置或源码锚点的变更时，"
    "在实现与验证期间保留知识影响检查点。最终回复前，结合当前任务与实际差异，"
    "判断长期知识语义或锚点是否发生变化。受影响或影响尚未查明时加载 modus-sync-knowledge；"
    "无影响时静默完成检查。该检查是助手的语义判断，不要求额外命令、扫描、报告、"
    "审批或持久化状态。"
)

# 供优先级说明与平台常驻指引共同引用的稳定入口。
MODUS_ENTRY_HINT: Final = " ".join((_PROJECT_EVIDENCE_ACTIVATION, _KNOWLEDGE_RETENTION_CHECKPOINT))

__all__ = ["MODUS_ENTRY_HINT"]
