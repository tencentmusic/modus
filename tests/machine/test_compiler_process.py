"""提供器子进程保留必需的系统环境，同时隔离用户目录及工具选项。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from modus.machine.facts.compiler.process import _run_process


def test_provider_process_has_isolated_windows_cache_and_temporary_directories(
    tmp_path: Path,
) -> None:
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    result = _run_process(
        [
            sys.executable,
            "-c",
            """import json, os
from pathlib import Path
names = ('HOME', 'USERPROFILE', 'LOCALAPPDATA', 'TMPDIR', 'TEMP', 'TMP')
directories = {name: os.environ.get(name) for name in names}
print(json.dumps({
    'directories': directories,
    'exist': all(value and Path(value).is_dir() for value in directories.values()),
    'systemRoot': os.environ.get('SYSTEMROOT') or os.environ.get('SystemRoot'),
    'windir': os.environ.get('WINDIR'),
    'leaked': any(key in os.environ for key in ('USER_SECRET', 'JAVA_TOOL_OPTIONS', 'GOFLAGS')),
}))
""",
        ],
        cwd=tmp_path,
        env={
            "PATH": os.defpath,
            # 自定义调用方可传入 Windows 原生混合大小写名称。
            "SystemRoot": system_root,
            "WINDIR": system_root,
            "LOCALAPPDATA": str(tmp_path / "private-user-cache"),
            "USERPROFILE": str(tmp_path / "private-user-profile"),
            "TEMP": str(tmp_path / "private-user-temp"),
            "USER_SECRET": "must-not-be-inherited",
            "JAVA_TOOL_OPTIONS": "must-not-be-inherited",
            "GOFLAGS": "must-not-be-inherited",
        },
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["exist"] is True
    directories = set(observed["directories"].values())
    assert len(directories) == 1
    runtime = Path(directories.pop())
    assert runtime != tmp_path / "private-user-cache"
    assert not runtime.exists(), "子进程结束后应清理隔离的缓存及临时目录"
    assert observed["systemRoot"] == observed["windir"] == system_root
    assert observed["leaked"] is False
