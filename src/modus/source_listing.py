"""Small, read-only source inventory for ordinary workspace navigation."""

from __future__ import annotations

import os
from pathlib import Path

from .paths import MANAGED_ROOT_FILES, PROJECT_OUTPUT_DIRS

_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".cxx",
        ".go",
        ".h",
        ".hh",
        ".hpp",
        ".hxx",
        ".m",
        ".mm",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".kts",
        ".php",
        ".py",
        ".pyi",
        ".rs",
        ".scala",
        ".sql",
        ".swift",
        ".ts",
        ".tsx",
        ".vue",
        ".xml",
        ".yaml",
        ".yml",
        ".properties",
    }
)


# 普通导航只列路径，不加载初始化分析器或建立持久化缓存。
# 依赖目录与框架输出被排除，防止生成内容重新成为源码候选。
# 后缀表表达导航可见范围，不等同于语言解析器的能力声明。
# 目录与文件都拒绝软链，遍历不会跟随链接进入外部仓库。
# 稳定排序让同一树的导航结果与文件系统枚举顺序无关。
# 逐文件大小限制避免把大型构建输入纳入轻量导航。
# 消失或不可读文件直接略过，导航保持尽力可用且不写入修复。
def list_source_paths(root: Path) -> tuple[str, ...]:
    """List bounded source paths without loading the init-only analyzer."""

    root = root.resolve()
    excluded = {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        "node_modules",
        "__pycache__",
        "modus",
        ".modus",
        *PROJECT_OUTPUT_DIRS,
    }
    result: list[str] = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(
            name for name in dirs if name not in excluded and not (base / name).is_symlink()
        )
        for name in sorted(names):
            path = base / name
            relative = path.relative_to(root).as_posix()
            if (
                path.is_symlink()
                or relative in MANAGED_ROOT_FILES
                or path.suffix.lower() not in _SUFFIXES
            ):
                continue
            try:
                if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
                    result.append(relative)
            except OSError:
                continue
    return tuple(result)


__all__ = ["list_source_paths"]
