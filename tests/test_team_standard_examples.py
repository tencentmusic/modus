"""编译并执行独立编码样本；工具缺失显式跳过，不用文本断言替代行为。"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures/team_standard/validation"


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.skip(f"编码演练需要 {name}，当前环境未安装")
    return executable


def _run(args: list[str], *, cwd: Path) -> None:
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False
    )
    assert result.returncode == 0, (
        f"命令失败（退出码 {result.returncode}）：{shlex.join(args)}\n"
        f"{result.stdout}{result.stderr}"
    )


def test_java_batch_uses_existing_capabilities_and_preserves_failure_contract(
    tmp_path: Path,
) -> None:
    javac, java = _tool("javac"), _tool("java")
    root = FIXTURES / "java"
    version = subprocess.run(
        [javac, "-version"], capture_output=True, text=True, timeout=10, check=True
    )
    # 新 JDK 的 --release 同时约束语法与标准库，避免误用本机的新 API。
    target = (
        ["-source", "8", "-target", "8"]
        if "1.8." in version.stdout + version.stderr
        else ["--release", "8"]
    )
    _run(
        [
            javac,
            *target,
            "-encoding",
            "UTF-8",
            "-Xlint:unchecked",
            "-Werror",
            "-d",
            str(tmp_path),
            str(root / "Kit.java"),
            str(root / "solution/ReserveBatch.java"),
            str(root / "checks/ReserveBatchCheck.java"),
        ],
        cwd=tmp_path,
    )
    _run([java, "-cp", str(tmp_path), "ReserveBatchCheck"], cwd=tmp_path)


def test_typescript_separates_browser_and_worker_and_handles_late_results(tmp_path: Path) -> None:
    node = _tool("node")
    compiler = os.environ.get("MODUS_TEST_TSC") or shutil.which("tsc")
    if compiler is None:
        pytest.skip("编码演练需要 tsc 或 MODUS_TEST_TSC")
    prefix = [node, compiler] if compiler.endswith(".js") else [compiler]
    root = FIXTURES / "typescript"
    # 隔离 ambient types，避免宿主的 @types/node 掩盖共享包的平台泄漏。
    type_roots = tmp_path / "types"
    type_roots.mkdir()
    for target, libraries in (("worker", "ES2020"), ("browser", "ES2020,DOM")):
        _run(
            [
                *prefix,
                "--strict",
                "--noEmitOnError",
                "--typeRoots",
                str(type_roots),
                "--target",
                "ES2020",
                "--module",
                "commonjs",
                "--lib",
                libraries,
                "--outDir",
                str(tmp_path / target),
                str(root / f"solution/{target}.ts"),
            ],
            cwd=tmp_path,
        )
    _run([node, str(root / "checks.cjs"), str(tmp_path)], cwd=tmp_path)
