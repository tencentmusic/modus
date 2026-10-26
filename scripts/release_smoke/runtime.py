"""Installed-wheel acceptance scenarios for the public Modus lifecycle."""

from __future__ import annotations

import importlib
import json
import shlex
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .archive import extract_wheel
from .contracts import (
    COMMAND_NAMES,
    PLATFORM_NAMES,
    WORKFLOW_NAMES,
    ReleaseCheckError,
    RuntimeVerification,
)
from .diagnostics import require

if TYPE_CHECKING:
    from typer import Typer
    from typer.testing import CliRunner

KNOWLEDGE_DOCUMENT = Path("modus/knowledge/domain/example/SKILL.md")
SAMPLE_SOURCE = "def helper(): return 1\ndef run(): return helper()\n"


# 所有操作都以临时项目根为边界，场景之间共享同一安装包入口。
# 命令失败包含输出及异常，便于定位安装后才出现的资源问题。
@dataclass(frozen=True, slots=True)
class SmokeProject:
    """An isolated project plus the installed CLI used to operate on it."""

    root: Path
    app: Typer
    runner: CliRunner

    # 参数列表直接交给 CLI 测试运行器；shlex.join 仅用于错误展示。
    # 返回 stdout 保持 JSON 场景可解析，不把诊断输出混入数据。
    def invoke(self, *arguments: str) -> str:
        result = self.runner.invoke(self.app, ["-C", str(self.root), *arguments])
        if result.exit_code != 0:
            command = shlex.join(("modus", *arguments))
            output = result.output.rstrip() or "<命令无输出>"
            exception = f"\nexception: {result.exception!r}" if result.exception else ""
            raise ReleaseCheckError(f"{command} 退出状态为 {result.exit_code}\n{output}{exception}")
        return result.stdout


# 先移除进程中已加载的 Modus 模块，防止仓库源码掩盖缺包问题。
# 临时导入路径只在此上下文有效，退出时恢复原模块与搜索路径。
# finally 清理包括失败场景，不让一次冒烟污染后续测试。
# 这里隔离 Modus 包来源，第三方依赖仍使用当前验证环境。
@contextmanager
def _isolated_wheel_imports(wheel: Path) -> Iterator[tuple[Path, Path]]:
    """Temporarily make one unpacked wheel the only importable Modus package."""

    with tempfile.TemporaryDirectory(prefix="modus-wheel-runtime-") as temporary:
        workspace = Path(temporary).resolve()
        package_root = workspace / "package"
        extract_wheel(wheel, package_root)

        original_path = sys.path.copy()
        original_modules = {
            name: module
            for name, module in tuple(sys.modules.items())
            if name == "modus" or name.startswith("modus.")
        }
        for name in original_modules:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(package_root))
        importlib.invalidate_caches()
        try:
            yield workspace, package_root
        finally:
            sys.path[:] = original_path
            for name in tuple(sys.modules):
                if name == "modus" or name.startswith("modus."):
                    sys.modules.pop(name, None)
            sys.modules.update(original_modules)
            importlib.invalidate_caches()


# JSON 格式有效不代表满足接口形状，顶层必须是对象。
# 错误带调用来源，便于区分多个生命周期步骤。
def _parse_json_object(document: str, *, source: str) -> Mapping[str, object]:
    try:
        payload = json.loads(document)
    except json.JSONDecodeError as exc:
        raise ReleaseCheckError(f"{source} 未返回有效 JSON：{exc}") from exc
    require(isinstance(payload, dict), f"{source} 必须返回 JSON 对象")
    return payload


# 嵌套报告也需独立验证，避免属性访问异常掩盖协议缺失。
def _require_json_object(value: object, *, message: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ReleaseCheckError(message)
    return value


# 用原始字节快照核验知识保护，不能只比较解析后的语义。
# 路径相对项目根保存，临时目录名称不会影响对比。
def _snapshot_markdown(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*.md")}


# 确认实际加载的是解包后的 wheel，再检查非 Python 资源。
# 可导入并不保证提供者源码、模式文件和类型标记已正确打包。
# 路径检查限定在临时包目录，避免回退到本地开发安装。
def _verify_import_origin(package_root: Path) -> None:
    import modus

    module_file = getattr(modus, "__file__", None)
    if not isinstance(module_file, str):
        raise ReleaseCheckError("已安装的 modus 包缺少 __file__ 位置")
    loaded_module = Path(module_file).resolve()
    require(
        loaded_module.is_relative_to(package_root),
        f"运行时冒烟检查从以下位置导入 modus：{loaded_module}，预期位置为 {package_root}",
    )
    required_assets = (
        package_root / "modus/py.typed",
        package_root / "modus/machine/language-registry.json",
        package_root / "modus/machine/facts/provider_assets/ModusJavaAnalyzer.java",
        package_root / "modus/machine/facts/provider_assets/modus_go_analyzer.go",
        package_root / "modus/machine/facts/provider_assets/modus_typescript_analyzer.cjs",
        package_root / "modus/_bundled/schemas/machine/analysis-receipt.schema.json",
        package_root / "modus/_bundled/schemas/machine/evidence-page.schema.json",
        package_root / "modus/_bundled/schemas/machine/authoring-context-packet.schema.json",
        package_root / "modus/_bundled/schemas/machine/capability-slice.schema.json",
    )
    missing = [
        path.relative_to(package_root).as_posix() for path in required_assets if not path.is_file()
    ]
    require(not missing, f"已安装 wheel 缺少带类型的分析资源：{missing!r}")


# 接入、读取与知识写入构成无需分析缓存的基本使用路径。
# 核验长期知识只要求机械完整，不能把内容成熟度当作程序错误。
# 保存正文快照供后续分析场景验证只读边界。
# 技能与命令集合使用发布契约核验，防止安装时漏发模板。
def _exercise_knowledge_paths(project: SmokeProject) -> dict[Path, bytes]:
    from modus.knowledge_update import update_knowledge
    from modus.paths import ModusPaths

    # Installation and ordinary read paths are deliberately analysis-cache-free.
    project.invoke("init", "--all-platforms")
    paths = ModusPaths.for_root(project.root)
    require(not paths.cache_dir.exists(), f"初始化意外创建了 {paths.cache_dir}")
    require(
        {entry.name for entry in paths.data_dir.iterdir()} == {"knowledge"},
        "首次安装创建了知识之外的项目数据",
    )
    require(
        {entry.name for entry in paths.skills_dir.iterdir()} == WORKFLOW_NAMES,
        "首次安装的技能范围不符合发布契约",
    )
    require(
        {entry.stem for entry in paths.commands_dir.glob("*.md")} == COMMAND_NAMES,
        "首次安装的显式命令范围不符合发布契约",
    )
    project.invoke("context", "resolve", "helper", "--scope", "project-read")
    project.invoke("status", "--json")

    result = update_knowledge(
        str(project.root),
        {KNOWLEDGE_DOCUMENT.as_posix(): "# Example\n\nRead main.py."},
    )
    require(
        result.get("status") == "completed",
        f"知识更新未完成：{result!r}",
    )
    verification = project.runner.invoke(
        project.app,
        ["-C", str(project.root), "knowledge", "verify", "--json"],
    )
    require(verification.exit_code == 0, "机械完整的知识应通过核验")
    verification_payload = _parse_json_object(
        verification.stdout,
        source="knowledge verify",
    )
    require(verification_payload.get("schemaVersion") == 1, "知识核验结果模式无效")
    require(
        verification_payload.get("status") == "clean",
        "知识核验混淆了编辑完整度与机械完整性",
    )
    return _snapshot_markdown(project.root / "modus")


# 模板目录需可从已安装资源读取，而非依赖仓库相对路径。
# 覆盖创作交付物、语言适配器与约束配置三类资源。
# 检查正文非空即可，不把特定语言措辞写成脆弱断言。
# 公开作者契约的存在性与内容质量分别由自动验收和评审负责。
def _exercise_authoring_contract() -> None:
    from modus.scaffold import TemplateCatalog

    catalog = TemplateCatalog()
    required_references = (
        "skills/modus-init/SKILL.md",
        "skills/modus-reinit/SKILL.md",
        "skills/using-modus/references/authoring/index.md",
        "skills/using-modus/references/authoring/evidence/index.md",
        "skills/using-modus/references/authoring/evidence/machine-packet.md",
        "skills/using-modus/references/authoring/evidence/scenario-closure.md",
        "skills/using-modus/references/authoring/evidence/scope-modeling.md",
        "skills/using-modus/references/authoring/parallel-domain-authoring.md",
        "skills/using-modus/references/authoring/framework/index.md",
        "skills/using-modus/references/authoring/framework/surface-profiles.md",
        "skills/using-modus/references/authoring/framework/visual-expression.md",
        "skills/using-modus/references/authoring/framework/deliverables/module.md",
        "skills/using-modus/references/authoring/framework/deliverables/topics.md",
        "skills/using-modus/references/authoring/publication.md",
    )
    # Packaging protects resource availability. Semantic prose quality belongs
    # to review, not to assertions about a particular language or sentence.
    for name in required_references:
        require(bool(catalog.read(name).strip()), f"创作参考为空：{name}")
    for deliverable in (
        "root",
        "domain",
        "module",
        "topics",
        "api",
        "object",
        "rule",
        "state-machine",
        "collaboration",
        "infrastructure",
        "team-standard",
        "business",
    ):
        name = f"skills/using-modus/references/authoring/framework/deliverables/{deliverable}.md"
        require(bool(catalog.read(name).strip()), f"创作契约为空：{name}")
    for seed in ("index.md", "meta/index.md", "experience/index.md", "scenario/index.md"):
        catalog.read(f"knowledge/business/{seed}")
    catalog.read("knowledge/handbook/SKILL.md")
    for adapter in (
        "generic",
        "java",
        "kotlin",
        "typescript",
        "python",
        "go",
        "rust",
        "native",
        "dotnet",
        "php",
        "iac",
    ):
        catalog.read(
            f"skills/using-modus/references/authoring/evidence/language-adapters/{adapter}.md"
        )
    for profile in ("python", "kotlin", "dotnet", "rust"):
        catalog.read(f"skills/modus-init/references/constraint-profiles/{profile}.md")


# 关闭外部编译器让冒烟只依赖安装包自身的基础能力。
# 构建返回的两个摘要必须能直接驱动后续证据查询。
# 分析前后比较全部知识字节，确认机器事实不会改写人工正文。
# 这里只验收公开数据形状，深入语义准确性由专门测试覆盖。
def _exercise_init_analysis(
    project: SmokeProject,
    retained_knowledge: dict[Path, bytes],
) -> None:
    receipt = _parse_json_object(
        project.invoke(
            "internal",
            "init-analysis",
            "build",
            "--root",
            str(project.root),
            "--compiler",
            "off",
            "--json",
        ),
        source="internal init-analysis build",
    )
    bundle_digest = receipt.get("bundleDigest")
    snapshot_digest = receipt.get("baselineDigest")
    if not isinstance(bundle_digest, str) or len(bundle_digest) != 64:
        raise ReleaseCheckError("证据包摘要无效")
    if not isinstance(snapshot_digest, str) or len(snapshot_digest) != 64:
        raise ReleaseCheckError("快照摘要无效")
    selection = _parse_json_object(
        project.invoke(
            "internal",
            "init-analysis",
            "select",
            "--root",
            str(project.root),
            "--bundle-digest",
            bundle_digest,
            "--baseline-digest",
            snapshot_digest,
            "--view",
            "scope",
            "--json",
        ),
        source="internal init-analysis select",
    )
    require(selection.get("schemaVersion") == 1, "证据筛选结果模式无效")
    require(isinstance(selection.get("items"), list), "证据筛选没有条目")
    require(
        _snapshot_markdown(project.root / "modus") == retained_knowledge,
        "初始化分析修改了保留的知识正文",
    )


# 新安装应被识别为最新，验证清单与模板版本的一致性。
# 额外放入用户文件，以真实数据验证卸载的所有权边界。
# 默认卸载保留知识，再次初始化也必须继续保留。
# 显式删除知识是独立场景，既核对报告也核对磁盘结果。
# 同一项目连续执行这些步骤，可暴露生命周期之间的状态遗漏。
def _exercise_maintenance_paths(project: SmokeProject) -> None:
    from modus.commands.update import run_update

    update_status = run_update(project.root)
    require(
        update_status.get("status") == "up-to-date",
        f"更新检查未报告安装已是最新：{update_status!r}",
    )

    personal_note = project.root / ".modus" / "personal-notes.txt"
    personal_note.write_text("retain", encoding="utf-8")
    uninstall_result = _parse_json_object(
        project.invoke("uninstall", "--project", "--yes", "--json"),
        source="project uninstall",
    )
    project_result = _require_json_object(
        uninstall_result.get("project"),
        message="项目卸载未返回项目报告",
    )
    require(
        not project_result.get("manualReview"),
        f"卸载意外要求人工评审：{uninstall_result!r}",
    )
    require(personal_note.read_text(encoding="utf-8") == "retain", "卸载删除了用户数据")
    require(
        (project.root / KNOWLEDGE_DOCUMENT).is_file(),
        "默认卸载删除了长期知识",
    )

    project.invoke("init", "--all-platforms")
    require(
        (project.root / KNOWLEDGE_DOCUMENT).is_file(),
        "重新初始化未保留已创作知识",
    )
    deleted = _parse_json_object(
        project.invoke(
            "uninstall",
            "--project",
            "--delete-knowledge",
            "--yes",
            "--json",
        ),
        source="project uninstall with knowledge deletion",
    )
    deleted_project = _require_json_object(
        deleted.get("project"),
        message="删除式卸载未返回项目报告",
    )
    deleted_knowledge = _require_json_object(
        deleted_project.get("knowledge"),
        message="删除式卸载未返回知识报告",
    )
    require(
        deleted_knowledge.get("disposition") == "delete",
        "删除式卸载未报告明确的知识处置",
    )
    require(
        not (project.root / "modus/knowledge").exists(),
        "显式删除知识后仍残留知识树",
    )


# 成员仓库是只读引用，工作区删除知识不能波及成员数据。
# 用两个不同深度的成员路径覆盖常见目录布局。
# 卸载前后逐文件字节比较，而非只检查目录还存在。
# 项目报告必须保留 workspace 类型，避免使用单仓库删除策略。
def _exercise_workspace_uninstall_boundary(
    workspace: Path,
    app: Typer,
    runner: CliRunner,
) -> None:
    root = workspace / "workspace-root"
    member_paths = ("teams/service-a", "clients/service-b")
    for relative in member_paths:
        member = root / relative
        (member / ".git").mkdir(parents=True)
        (member / "member-owned.txt").write_text(relative, encoding="utf-8")
    project = SmokeProject(root, app, runner)
    project.invoke(
        "init",
        "--workspace",
        "--platform",
        "codex",
        "--member",
        member_paths[0],
        "--member",
        member_paths[1],
    )
    before = {
        relative: {
            path.relative_to(root / relative): path.read_bytes()
            for path in (root / relative).rglob("*")
            if path.is_file()
        }
        for relative in member_paths
    }

    result = _parse_json_object(
        project.invoke(
            "uninstall",
            "--project",
            "--delete-knowledge",
            "--yes",
            "--json",
        ),
        source="workspace project uninstall",
    )
    project_result = _require_json_object(
        result.get("project"),
        message="工作区卸载未返回项目报告",
    )
    require(
        project_result.get("projectKind") == "workspace",
        "工作区卸载丢失了项目类型",
    )
    after = {
        relative: {
            path.relative_to(root / relative): path.read_bytes()
            for path in (root / relative).rglob("*")
            if path.is_file()
        }
        for relative in member_paths
    }
    require(after == before, "工作区卸载修改了成员仓库")


# 验收顺序覆盖接入、创作、分析、更新和卸载的完整基本链路。
# 平台集合从实际安装的注册表读取，不能复用仓库清单伪造成功。
# 此处是场景最外层异常边界，统一包装意外失败供发布门禁报告。
# 保留异常链，库内部错误不会被吞掉或转成通过。
# 临时目录由导入上下文统一回收，无需触碰用户真实项目。
def exercise_installed_wheel(wheel: Path) -> RuntimeVerification:
    """Run a representative lifecycle against an unpacked, isolated wheel."""

    try:
        with _isolated_wheel_imports(wheel) as (workspace, package_root):
            from typer.testing import CliRunner

            from modus.cli import app
            from modus.platforms import available_platforms

            _verify_import_origin(package_root)
            _exercise_authoring_contract()
            project_root = workspace / "project"
            project_root.mkdir()
            from modus.machine.corpus.source_snapshot import SourceSnapshot
            from modus.machine.facts.structural import _get_extractor

            for name, source in {
                "View.m": "@implementation View\n- (void)run {}\n@end",
                "View.mm": "@implementation View\n- (void)run {}\n@end",
                "View.swift": "class View { func run() {} }",
                "View.kt": "class View { fun run() {} }",
            }.items():
                path = project_root / name
                facts = _get_extractor(path)(SourceSnapshot(path, source))
                require(bool(facts.get("declarations")), f"安装后的语言解析不可用：{name}")
            (project_root / "main.py").write_text(SAMPLE_SOURCE, encoding="utf-8")
            project = SmokeProject(project_root, app, CliRunner())

            retained_knowledge = _exercise_knowledge_paths(project)
            _exercise_init_analysis(project, retained_knowledge)
            _exercise_maintenance_paths(project)
            _exercise_workspace_uninstall_boundary(workspace, app, CliRunner())
            platforms = frozenset(available_platforms())
            require(
                platforms == PLATFORM_NAMES,
                "installed platform catalog mismatch: "
                f"expected {sorted(PLATFORM_NAMES)!r}, found {sorted(platforms)!r}",
            )
    except ReleaseCheckError:
        raise
    except Exception as exc:
        raise ReleaseCheckError(f"安装后 wheel 场景失败：{type(exc).__name__}: {exc}") from exc

    return RuntimeVerification(
        workflow_count=len(WORKFLOW_NAMES),
        platform_count=len(platforms),
    )
