"""Bounded compiler processes and compilation of shipped analyzer assets."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from modus.artifacts_io import atomic_write_text
from modus.machine.facts.build_contracts import BuildUnit
from modus.paths import ModusPaths

from .models import CompilerSemanticError

_MAX_PROVIDER_OUTPUT = 256 * 1024 * 1024


def _safe_name(value: str) -> str:
    """Collapse *value* to characters safe for use as a filesystem path segment."""
    return "".join(
        character if character.isalnum() or character in "._-" else "_" for character in value
    )


def _source_list(paths: ModusPaths, unit: BuildUnit) -> Path:
    """Persist *unit*'s file list for a provider subprocess to read by path."""
    target = paths.compiler_cache_dir / "requests" / f"{_safe_name(unit.id)}.sources"
    atomic_write_text(target, "\n".join(str(item) for item in unit.files) + "\n")
    return target


def _asset(name: str) -> Path:
    """Resolve a bundled analyzer source file under ``provider_assets/``."""
    return Path(__file__).parents[1] / "provider_assets" / name


# argv 是独立参数列表，不经 shell 解释；调用方仍负责选择可信可执行文件。
# 环境白名单限制继承范围，临时 HOME 避免读取用户级工具配置。
# stdout 与 stderr 并行排空，共用字节计数，防止任一路阻塞或绕过总预算。
# CompletedProcess 仅封装已结束进程的结果，本身不会再次启动命令。
def _run_process(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    """Run *argv* with a bounded environment, output size, and wall-clock timeout.

    The child inherits none of the caller's environment beyond an explicit
    allow-list, runs with an isolated ``HOME``/``TMPDIR``, and is killed --
    process group included -- on timeout or once combined stdout/stderr
    exceeds :data:`_MAX_PROVIDER_OUTPUT`.
    """
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "LANG",
        "LC_ALL",
        "JAVA_HOME",
        "SDKROOT",
        "DEVELOPER_DIR",
        "GOROOT",
        "GOPATH",
        "GOCACHE",
        "GOMODCACHE",
        "GOPROXY",
        "GOSUMDB",
        "GOTOOLCHAIN",
        "GOWORK",
        "CGO_ENABLED",
        "PIP_NO_INDEX",
        "NO_PROXY",
    }
    source_env = dict(env) if env is not None else dict(os.environ)
    bounded_env = {key: value for key, value in source_env.items() if key.upper() in allowed}
    bounded_env.setdefault("PATH", os.defpath)
    with tempfile.TemporaryDirectory(prefix="modus-provider-runtime-") as temporary:
        # Windows 的 Go 用 LOCALAPPDATA 定位必需的构建缓存，不读取 HOME。
        # 用户目录和临时目录都指向本轮隔离空间，既可构建又不继承用户配置。
        bounded_env.update(
            {
                "HOME": temporary,
                "USERPROFILE": temporary,
                "LOCALAPPDATA": temporary,
                "TMPDIR": temporary,
                "TEMP": temporary,
                "TMP": temporary,
                "LC_ALL": "C",
            }
        )
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            # NOCA:dangerous-subprocess-use-audit(内部提供器构造参数数组，保留环境白名单及输出超时边界，不经过 shell)
            process = subprocess.Popen(
                argv,
                shell=False,
                cwd=cwd,
                env=bounded_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name != "nt",
            )

            def terminate_group() -> None:
                try:
                    if os.name == "nt":
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    if process.poll() is None:
                        process.kill()
                process.wait()

            exceeded = threading.Event()
            counter_lock = threading.Lock()
            total = 0

            def drain(pipe: BinaryIO, target: BinaryIO) -> None:
                nonlocal total
                try:
                    while True:
                        chunk = pipe.read(65536)
                        if not chunk:
                            break
                        with counter_lock:
                            total += len(chunk)
                            if total > _MAX_PROVIDER_OUTPUT:
                                exceeded.set()
                                return
                        target.write(chunk)
                finally:
                    pipe.close()

            drainers = [
                threading.Thread(target=drain, args=(pipe, target), daemon=True)
                for pipe, target in ((process.stdout, stdout), (process.stderr, stderr))
            ]
            for drainer in drainers:
                drainer.start()
            started = time.monotonic()
            try:
                while process.poll() is None:
                    if exceeded.wait(0.025):
                        raise CompilerSemanticError(
                            "compiler provider output exceeded its byte budget"
                        )
                    if time.monotonic() - started > timeout:
                        raise CompilerSemanticError(
                            f"compiler provider exceeded {timeout}s timeout"
                        )
                for drainer in drainers:
                    drainer.join(timeout=0.5)
                if exceeded.is_set():
                    raise CompilerSemanticError("compiler provider output exceeded its byte budget")
                if any(drainer.is_alive() for drainer in drainers):
                    raise CompilerSemanticError(
                        "compiler provider left an unfinished output process"
                    )
            # 取消和中断也必须终止子进程组，避免调用方退出后遗留编译器。
            # 清理完成后原样抛出；这里不把失败降级成成功结果。
            except BaseException:
                terminate_group()
                for drainer in drainers:
                    drainer.join(timeout=2)
                raise
            stdout.seek(0)
            stderr.seek(0)
            # NOCA:dangerous-subprocess-use-audit(仅封装已结束进程的参数及结果，此构造器不执行命令)
            return subprocess.CompletedProcess(
                argv,
                process.returncode,
                stdout.read().decode("utf-8", errors="replace"),
                stderr.read().decode("utf-8", errors="replace"),
            )


def _java_env() -> dict[str, str]:
    """Base environment for javac/java subprocesses, stripped of ambient JVM options."""
    env = dict(os.environ)
    for name in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH"):
        env.pop(name, None)
    return env


# 离线与 local 工具链策略避免 Go 自动下载依赖或切换工具版本。
def _go_env(*, go_work: str = "off", cgo: str = "off") -> dict[str, str]:
    """Base environment for `go` subprocesses: offline, and free of ambient tool overrides."""
    env = dict(os.environ)
    for name in ("GOPACKAGESDRIVER", "GOFLAGS", "GOTOOLDIR"):
        env.pop(name, None)
    env.update(
        {
            "CGO_ENABLED": "0" if cgo == "off" else os.environ.get("CGO_ENABLED", "1"),
            "GOPROXY": "off",
            "GOSUMDB": "off",
            "GOTOOLCHAIN": "local",
            "GOWORK": go_work,
        }
    )
    return env


# 仅编译随包提供器源码，不调用项目自定义构建生命周期。
# 源码内容、编译器路径及版本共同决定缓存目录，避免跨工具复用二进制。
def _compile_asset(
    paths: ModusPaths,
    *,
    language: str,
    source: Path,
    compiler: str,
) -> Path:
    """Compile a bundled analyzer *source* once per (content, compiler) pair.

    The output directory name is a digest of the source bytes and the
    resolved compiler's version banner, so a compiler upgrade or a changed
    analyzer transparently invalidates the cached binary.
    """
    identity = hashlib.sha256()
    identity.update(source.read_bytes())
    identity.update(str(Path(compiler).resolve()).encode("utf-8"))
    try:
        version = _run_process(
            [compiler, "-version" if language == "java" else "version"],
            cwd=paths.root,
            timeout=20,
        )
        identity.update((version.stdout + version.stderr).encode("utf-8"))
    except (OSError, subprocess.SubprocessError, CompilerSemanticError):
        identity.update(b"compiler-version-unavailable")
    digest = identity.hexdigest()[:24]
    output_dir = paths.compiler_cache_dir / "provider-bin" / language / digest
    output_dir.mkdir(parents=True, exist_ok=True)
    if language == "java":
        marker = output_dir / "ModusJavaAnalyzer.class"
        if marker.is_file():
            return output_dir
        tools_jar = _java_tools_jar(compiler)
        classpath_args = ["-cp", str(tools_jar)] if tools_jar is not None else []
        completed = _run_process(
            [
                compiler,
                *classpath_args,
                "-encoding",
                "UTF-8",
                "-d",
                str(output_dir),
                str(source),
            ],
            cwd=paths.root,
            env=_java_env(),
            timeout=120,
        )
        if completed.returncode != 0 or not marker.is_file():
            raise CompilerSemanticError(
                "could not compile bundled Javac provider: " + completed.stderr.strip()[-2000:]
            )
        return output_dir
    # Windows 通过显式 .exe 路径启动提供器，不依赖隐式扩展名查找。
    marker = output_dir / ("modus-go-analyzer.exe" if os.name == "nt" else "modus-go-analyzer")
    if marker.is_file():
        return marker
    env = _go_env()
    completed = _run_process(
        [compiler, "build", "-trimpath", "-o", str(marker), str(source)],
        cwd=paths.root,
        env=env,
        timeout=180,
    )
    if completed.returncode != 0 or not marker.is_file():
        raise CompilerSemanticError(
            "could not compile bundled Go provider: " + completed.stderr.strip()[-2000:]
        )
    return marker


def _java_tools_jar(compiler: str) -> Path | None:
    """Locate ``tools.jar`` beside *compiler*, if the JDK still ships one."""
    candidates = [Path(compiler).resolve().parent.parent / "lib" / "tools.jar"]
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home) / "lib" / "tools.jar")
    return next((item for item in candidates if item.is_file()), None)
