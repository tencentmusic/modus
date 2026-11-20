"""按发布脚本提供的桌面资源构建 Apple Silicon wheel。"""

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        archive = os.environ.get("MODUS_MANAGER_ARCHIVE")
        if version != "standard" or not archive:
            return

        # Python 入口跨版本可用，随包的 Mach-O 资源限定了系统和处理器。
        build_data["tag"] = "py3-none-macosx_11_0_arm64"
        build_data["pure_python"] = False
        build_data["force_include"][str(Path(archive).resolve(strict=True))] = (
            "modus/_bundled/modus-manager.zip"
        )
