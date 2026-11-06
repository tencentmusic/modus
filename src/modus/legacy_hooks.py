"""仅供旧安装升级和卸载使用的 hook 清理；新安装不生成任何 hook。"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

LEGACY_HOOK_PATHS = MappingProxyType(
    {
        "claude": (".claude/settings.json",),
        "codex": (".codex/hooks.json", ".agents/hooks.json"),
        "cursor": (".cursor/hooks.json",),
        "codebuddy": (".codebuddy/settings.json",),
    }
)
_SIGNATURE = ".modus/hooks/run-hook.cmd"


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    data: dict[str, object] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("旧 hook 配置包含重复键")
        data[key] = value
    return data


def _is_modus_command(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    return any(
        isinstance(command := entry.get(key), str) and _SIGNATURE in command.replace("\\", "/")
        for key in ("command", "commandWindows")
    )


def _retained_entries(entries: list[object]) -> list[object]:
    retained: list[object] = []
    for entry in entries:
        if _is_modus_command(entry):
            continue
        if isinstance(entry, dict) and "hooks" in entry:
            nested = entry["hooks"]
            if not isinstance(nested, list):
                raise ValueError("旧 hook 事件组必须包含命令列表")
            remaining = _retained_entries(nested)
            if remaining != nested:
                if remaining:
                    retained.append({**entry, "hooks": remaining})
                continue
        retained.append(entry)
    return retained


def clean_legacy_hook_config(path: Path, *, apply: bool = True) -> bool:
    """按命令签名撤销旧条目；无法安全读取返回 False，写入失败交给外层事务。

    同一 matcher 内的外部命令与未知字段均保留。未找到 Modus 命令时不改写
    文件，包括用户自己的空事件和版本字段。预览只验证结构，不触碰磁盘。
    """
    if path.is_symlink():
        return False
    if not path.exists():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict) or any(not isinstance(v, list) for v in hooks.values()):
        return False

    changed = False
    for event, entries in list(hooks.items()):
        try:
            remaining = _retained_entries(entries)
        except ValueError:
            return False
        if remaining == entries:
            continue
        changed = True
        if remaining:
            hooks[event] = remaining
        else:
            del hooks[event]
    if not apply or not changed:
        return True
    if not hooks:
        data.pop("hooks", None)
    # Cursor 的旧生成器独有 version: 1；其他字段和版本均视为用户配置。
    if not data or (
        path.name == "hooks.json" and path.parent.name == ".cursor" and data == {"version": 1}
    ):
        path.unlink()
    else:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline=""
        )
    return True
