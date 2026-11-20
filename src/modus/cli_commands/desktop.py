"""通过 macOS Launch Services 打开本机桌面应用。"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory

import typer

logger = logging.getLogger(__name__)

_APP_NAME = "modus-manager.app"
_SYSTEM_APPLICATIONS = Path("/Applications")


def _is_launchable(bundle: Path) -> bool:
    executable = bundle / "Contents/MacOS/modus-manager"
    return executable.is_file() and os.access(executable, os.X_OK)


def _install_bundled_app(destination: Path) -> None:
    archive = files("modus").joinpath("_bundled", "modus-manager.zip")
    if not archive.is_file():
        raise FileNotFoundError("此安装包未包含 Modus Manager。桌面安装包适用于 Apple Silicon。")
    if destination.exists() or destination.is_symlink():
        if _is_launchable(destination):
            return
        raise FileExistsError(f"已有桌面应用无法启动，请检查 {destination}。")

    typer.echo("正在安装随 Modus 提供的桌面应用…")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        as_file(archive) as archive_path,
        TemporaryDirectory(prefix=".modus-install-", dir=destination.parent) as staging,
    ):
        bundle = Path(staging) / _APP_NAME
        # ditto 保留原生应用权限和元数据。完整性校验通过后再移入 Applications。
        for command in (
            ["/usr/bin/ditto", "-x", "-k", str(archive_path), staging],
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)],
        ):
            logger.debug("准备随包桌面应用：%s", command[0])
            subprocess.run(command, check=True, capture_output=True, text=True)
        if not _is_launchable(bundle):
            raise OSError(f"随包桌面应用缺少可执行文件：{bundle}")

        # 传入父目录，避免并发首次启动时覆盖已经就绪的应用。
        subprocess.run(
            ["/bin/mv", "-n", str(bundle), str(destination.parent)],
            check=True,
            capture_output=True,
            text=True,
        )
    if not _is_launchable(destination):
        raise OSError(f"桌面应用安装后无法启动：{destination}")


def launch() -> None:
    """首次运行时安装随包应用，随后通过 Launch Services 打开。"""
    if sys.platform != "darwin":
        typer.echo("Modus Dashboard 当前仅支持 macOS。", err=True)
        raise typer.Exit(1)

    user_bundle = Path.home() / "Applications" / _APP_NAME
    system_bundle = _SYSTEM_APPLICATIONS / _APP_NAME
    bundle = user_bundle
    try:
        if not _is_launchable(user_bundle):
            if _is_launchable(system_bundle):
                bundle = system_bundle
            else:
                _install_bundled_app(user_bundle)

        # 用完整路径选中本应用，避免启动同 bundle ID 的其他构建。
        logger.debug("请求 Launch Services 打开 %s", bundle)
        subprocess.run(
            ["/usr/bin/open", "-a", str(bundle)], check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (
            (exc.stderr or "").strip() if isinstance(exc, subprocess.CalledProcessError) else ""
        )
        typer.echo(f"无法启动 Modus Manager（{bundle}）。{detail or exc}", err=True)
        raise typer.Exit(1) from exc
