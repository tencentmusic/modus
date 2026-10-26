"""Full project binding over immutable file observations.

The resolver never reparses source. Failed lookups and export-set reads remain
explicit evidence, preserving why a relation is exact, ambiguous, or unresolved.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from modus.machine.corpus.input_snapshot import read_bytes

BINDING_CONTRACT_VERSION = 1  # 绑定结果协议版本参与下游兼容判断。
_SOURCE_SUFFIXES = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mts",
    ".mjs",
    ".cts",
    ".cjs",
    ".vue",
    ".svelte",
    ".py",
    ".java",
    ".go",
    ".rs",
    ".php",
    ".h",
    ".hpp",
    ".hh",
    ".hxx",
)
_MOBILE_LANGUAGES = frozenset({"kotlin", "swift", "objective-c", "objective-cpp"})
_BUILTINS = frozenset(
    {
        "len",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "range",
        "print",
        "isinstance",
        "super",
        "enumerate",
        "zip",
        "sorted",
        "min",
        "max",
        "sum",
        "abs",
        "open",
        "getattr",
        "setattr",
        "hasattr",
    }
)


# 相对模块路径按段归一化，越过项目根时返回空候选。
# 这里处理逻辑身份，不触发文件系统解析或链接跟随。
# 路径规范化服务于项目绑定，文件内解析无需知道其他文件布局。
def _normalize(value: str) -> str:
    parts: list[str] = []
    for part in value.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return ""
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


# 项目绑定只使用不可变文件观察，名称解析不重新解析源码。
# 成功与失败的查找都记录依赖，使未解析原因可以追溯。
# 词法作用域、模块导出与全局名称分别建索引，避免混淆证明强度。
class _Project:
    def __init__(self, files: list[dict], root: Path) -> None:
        self.root = root
        self.files = {row["path"]: row for row in files if row.get("path")}
        self.nodes = {node["id"]: node for row in files for node in row.get("nodes", ())}
        self.declarations = {
            node["id"]: node for row in files for node in row.get("declarations", ())
        }
        self.scopes = {scope["id"]: scope for row in files for scope in row.get("scopes", ())}
        self.scope_bindings: dict[str, dict[str, list[dict]]] = {}
        for scope_id, scope in self.scopes.items():
            index: dict[str, list[dict]] = defaultdict(list)
            for binding in scope.get("bindings", ()):
                index[binding["name"]].append(binding)
            self.scope_bindings[scope_id] = index
        self.names: dict[str, set[str]] = defaultdict(set)
        self.java_types: dict[str, set[str]] = defaultdict(set)
        self.directories: dict[str, set[str]] = defaultdict(set)
        self.package_names: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.java_packages: dict[str, set[str]] = defaultdict(set)
        self.kotlin_packages: dict[str, set[str]] = defaultdict(set)
        self.kotlin_symbols: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.named_exports: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.star_exports: dict[str, list[dict]] = defaultdict(list)
        for path, file in self.files.items():
            directory = str(PurePosixPath(path).parent)
            self.directories[directory].add(path)
            if file.get("language") == "java":
                self.java_packages[file.get("package", "")].add(path)
            elif file.get("language") == "kotlin":
                self.kotlin_packages[file.get("package", "")].add(path)
            for exported in file.get("exports", ()):
                if exported.get("star"):
                    self.star_exports[path].append(exported)
                else:
                    self.named_exports[(path, exported.get("name", ""))].append(exported)
            for decl in file.get("declarations", ()):
                self.names[decl["name"]].add(decl["id"])
                self.package_names[(directory, decl["name"])].add(decl["id"])
                if file.get("language") == "java" and decl["kind"] == "type":
                    self.java_types[(file.get("package", "") + "." + decl["name"]).strip(".")].add(
                        path
                    )
                elif (
                    file.get("language") == "kotlin"
                    and self.scopes.get(decl.get("scope_id"), {}).get("kind") == "module"
                ):
                    self.kotlin_symbols[(file.get("package", ""), decl["name"])].add(decl["id"])
        self.dependencies: list[dict] = []  # 失败查找也参与依赖记录，供缓存失效判断。
        self.configs: dict[str, dict] = {}  # 配置读取按项目会话复用。
        self.modules: dict[tuple[str, str], tuple[str, ...]] = {}
        self.export_cache: dict[tuple[str, str], frozenset[str]] = {}
        self.export_active: set[tuple[str, str]] = set()  # 跟踪跨导出递归的当前分支。
        self.edges: list[dict] = []  # 图关系与未解析结果分别保存。
        self.unresolved: list[dict] = []  # 找不到目标仍是需要发布的观察结果。
        self.outcomes: list[dict] = []  # 逐引用保留解析结论，便于解释候选证据。
        self.diagnostics: list[dict] = []  # 资源上限等降级原因不混入事实关系。
        self.active_owner = ""  # 依赖记录关联到当前工作拥有者。
        self.owner_files: dict[str, str] = {}  # 跨文件展开后仍能归因到发起查找的拥有者。

    # 深度上限产生部分完整诊断，不能把截断解释为没有目标。
    def depth_limit(self, file: str, phase: str) -> None:
        row = {
            "code": "machine.facts.binding-depth-limit",
            "path": file,
            "phase": phase,
            "analysisCompleteness": "partial",
            "message": "Binding expansion exceeded the bounded depth of 128.",
        }
        if row not in self.diagnostics:
            self.diagnostics.append(row)

    # 依赖同时记录实际观察文件和当前绑定拥有者。
    # 重导出跨文件展开时仍能回溯最初触发查找的符号。
    def dependency(self, file: str, kind: str, key: str, *, resolved: bool, **extra) -> None:
        self.dependencies.append(
            {
                "sourceFile": self.owner_files.get(self.active_owner, file),
                "observedFrom": file,
                "ownerId": self.active_owner,
                "kind": kind,
                "key": key,
                "resolved": resolved,
                **extra,
            }
        )

    # 配置通过快照读取，失败也缓存为本轮观察。
    # 空或无效配置不能触发执行脚本，只影响候选解析。
    def config(self, file: str, candidate: str) -> dict:
        if candidate not in self.configs:
            try:
                raw = read_bytes(self.root, self.root / candidate)
                value = json.loads(raw)
                self.configs[candidate] = value if isinstance(value, dict) else {}
            except (OSError, ValueError):
                self.configs[candidate] = {}
        self.dependency(
            file, "config", candidate, resolved=bool(self.configs[candidate]), targetFile=candidate
        )
        return self.configs[candidate]

    # 扩展名和目录入口按既定顺序尝试，保留解析优先级。
    def candidates(self, base: str) -> tuple[str, ...]:
        normalized = _normalize(base)
        if not normalized:
            return ()
        return tuple(
            dict.fromkeys(
                (
                    normalized,
                    *(normalized + suffix for suffix in _SOURCE_SUFFIXES),
                    *(normalized + "/index" + suffix for suffix in _SOURCE_SUFFIXES[:8]),
                    normalized + "/__init__.py",
                )
            )
        )

    # 从当前目录向上查找最近匹配模块，记录每次 go.mod 观察。
    # 包解析返回该目录的 Go 文件集合，而非任意同名符号。
    def _go_module_files(self, file: str, parent: str, specifier: str) -> set[str]:
        """Resolve a package from the nearest matching module, recording config reads."""
        exact: set[str] = set()
        current = PurePosixPath(parent)
        while True:
            config_path = str(current / "go.mod")
            try:
                content = read_bytes(self.root, self.root / config_path).decode()
                module = next(
                    (
                        line.split()[1]
                        for line in content.splitlines()
                        if line.startswith("module ")
                    ),
                    "",
                )
            except (OSError, ValueError):
                module = ""
            self.dependency(
                file, "config", config_path, resolved=bool(module), targetFile=config_path
            )
            if module and (specifier == module or specifier.startswith(module + "/")):
                base = _normalize(str(current / specifier[len(module) :].lstrip("/")))
                exact.update(
                    path for path in self.directories.get(base or ".", ()) if path.endswith(".go")
                )
                break
            if str(current) == ".":
                break
            current = current.parent
        return exact

    # 采用最近可读配置并保留 paths 目标顺序。
    # 非法 compilerOptions 显式诊断，不能影响其他文件的结构提取。
    def _typescript_module_bases(self, file: str, parent: str, specifier: str) -> list[str]:
        """Expand aliases from the nearest config, preserving target precedence."""
        bases: list[str] = []
        current = PurePosixPath(parent)
        while True:
            config = self.config(file, str(current / "tsconfig.json"))
            options = config.get("compilerOptions") or {}
            if not isinstance(options, dict):
                self.diagnostics.append(
                    {
                        "code": "machine.facts.binding-invalid-config",
                        "path": file,
                        "message": "compilerOptions must be an object.",
                        "analysisCompleteness": "partial",
                    }
                )
                options = {}
            if config:
                base_url = str(current / str(options.get("baseUrl", ".")))
                paths = options.get("paths") or {}
                if not isinstance(paths, dict):
                    self.diagnostics.append(
                        {
                            "code": "machine.facts.binding-invalid-config",
                            "path": file,
                            "message": "compilerOptions.paths must be an object.",
                            "analysisCompleteness": "partial",
                        }
                    )
                    paths = {}
                for pattern, targets in paths.items():
                    head, star, tail = pattern.partition("*")
                    if (
                        specifier == pattern
                        or star
                        and specifier.startswith(head)
                        and specifier.endswith(tail)
                    ):
                        middle = (
                            specifier[len(head) : len(specifier) - len(tail) if tail else None]
                            if star
                            else ""
                        )
                        if isinstance(targets, list):
                            bases.extend(
                                base_url + "/" + str(target).replace("*", middle)
                                for target in targets
                            )
                bases.append(base_url + "/" + specifier)
                break
            if str(current) == ".":
                break
            current = current.parent
        bases.extend([specifier, "src/" + specifier])
        return bases

    # 语言专属规则只产生已捕获文件候选，不搜索仓库外任意路径。
    # 缓存命中也记录模块集合依赖，复用不能丢失解释依据。
    # 本地 package.json 入口作为数据读取，不运行 JavaScript。

    def resolve_module(
        self, file: str, specifier: str, *, import_kind: str = ""
    ) -> tuple[str, ...]:
        if (
            self.files[file].get("language") in {"objective-c", "objective-cpp"}
            and import_kind == "module"
        ):
            self.dependency(
                file,
                "module-set",
                specifier,
                resolved=False,
                targetFiles=[],
                importKind=import_kind,
            )
            return ()
        cache_key = (file, specifier)
        if cache_key in self.modules:
            result = self.modules[cache_key]
            self.dependency(
                file, "module-set", specifier, resolved=bool(result), targetFiles=list(result)
            )
            return result
        info = self.files[file]
        language = info.get("language")
        parent = str(PurePosixPath(file).parent)
        bases: list[str] = []
        exact: set[str] = set()
        if language == "python":
            level = len(specifier) - len(specifier.lstrip("."))
            module = specifier[level:].replace(".", "/")
            if level:
                current = PurePosixPath(parent)
                for _ in range(level - 1):
                    current = current.parent
                bases.append(str(current / module))
            else:
                bases.extend([module, "src/" + module])
        elif language == "java":
            exact.update(self.java_types.get(specifier, ()))
            if specifier.endswith(".*"):
                exact.update(self.java_packages.get(specifier[:-2], ()))
            bases.append(specifier.replace(".", "/"))
        elif language == "kotlin":
            if specifier.endswith(".*"):
                exact.update(self.kotlin_packages.get(specifier[:-2], ()))
            else:
                package, _, name = specifier.rpartition(".")
                exact.update(
                    self.nodes[target]["source_file"]
                    for target in self.kotlin_package_targets(file, package, name)
                )
        elif language == "swift":
            # Swift import 指向构建模块；同名源码文件不能证明模块身份。
            pass
        elif language == "go":
            exact.update(self._go_module_files(file, parent, specifier))
        elif specifier.startswith("."):
            bases.append(parent + "/" + specifier)
        elif language in {"javascript", "typescript", "tsx"}:
            bases.extend(self._typescript_module_bases(file, parent, specifier))
        else:
            bases.extend([parent + "/" + specifier, specifier])
        for base in bases:
            for candidate in self.candidates(base):
                exists = candidate in self.files
                if exists:
                    exact.add(candidate)
                    break
            exact.update(self._package_entry_files(file, base))
        result = tuple(sorted(exact))
        self.modules[cache_key] = result
        self.dependency(
            file,
            "module-set",
            specifier,
            resolved=bool(result),
            targetFiles=list(result),
        )
        return result

    def _package_entry_files(self, file: str, base: str) -> set[str]:
        """仅按包元数据解析入口，不执行 JavaScript；保留 exports 的既有优先级。"""
        exact: set[str] = set()
        # A local package's entrypoint is data, never executed JavaScript.
        package_path = _normalize(base + "/package.json")
        if package_path in self.files:
            package = self.config(file, package_path)
            exported = package.get("exports")
            if isinstance(exported, dict):
                exported = exported.get(".")
            if isinstance(exported, dict):
                exported = (
                    exported.get("types") or exported.get("import") or exported.get("default")
                )
            entry = exported or package.get("module") or package.get("main")
            if isinstance(entry, str):
                exact.update(
                    candidate
                    for candidate in self.candidates(base + "/" + entry)
                    if candidate in self.files
                )
        return exact

    # 逐层查找最近词法绑定，遇到作用域循环停止。
    # Python 方法不能闭包捕获类命名空间，遵循其语言作用域规则。
    def binding(self, file: str, scope_id: str, name: str):
        visited = set()  # 损坏作用域链不能导致无限循环。
        while scope_id and scope_id not in visited:
            visited.add(scope_id)
            scope = self.scopes.get(scope_id)
            if not scope:
                break
            # Python method bodies do not close over the class namespace.
            skip_type = self.files[file].get("language") == "python" and scope["kind"] == "type"
            values = [] if skip_type else self.scope_bindings.get(scope_id, {}).get(name, [])
            if values:
                return values, scope_id
            scope_id = scope["parent"]
        return [], ""

    # 参数和局部赋值会阻断全局同名回退，避免建立错误调用边。
    # 别名递归保留已访问集合，循环和深度截断都明确阻断。
    # 导入目标必须经模块及导出解析，不能仅按尾部名称匹配。
    def lookup(self, file: str, scope_id: str, name: str, seen: frozenset[tuple] = frozenset()):
        key = (file, scope_id, name)
        if len(seen) > 128:
            self.depth_limit(file, "alias")
        if key in seen or len(seen) > 128:
            return set(), "alias-cycle", True
        seen = seen | {key}
        bindings, owner = self.binding(file, scope_id, name)
        self.dependency(
            file,
            "lookup",
            scope_id + ":" + name,
            resolved=bool(bindings),
            scopeId=scope_id,
            lookupName=name,
        )
        if not bindings:
            return set(), "no-declaration", False
        kinds = {row["kind"] for row in bindings}
        # Any assignment or parameter means a module-level homonym is not a
        # justified binding. Never fall through to a global-name heuristic.
        if kinds & {"parameter", "local"}:
            return set(), "shadowed-binding", True
        targets: set[str] = set()
        proof = "scope"  # 仅词法声明可从此证明起点继续。
        for row in bindings:
            if row["kind"] == "declaration":
                targets.add(row["target"])
            elif row["kind"] == "alias":
                alias_targets, _, _ = self.resolve_name(file, owner, row["target_name"], seen)
                targets.update(alias_targets)
            elif row["kind"] == "import":
                imported = self.files[file]["imports"][row["import_index"]]
                modules = self.resolve_module(
                    file, imported["specifier"], import_kind=imported["kind"]
                )
                if self.files[file].get("language") == "kotlin":
                    package, _, imported_name = imported["specifier"].rpartition(".")
                    targets.update(self.kotlin_package_targets(file, package, imported_name))
                    proof = "kotlin-import"
                    continue
                for module in modules:
                    self.dependency(
                        file,
                        "exports",
                        module,
                        resolved=True,
                        targetFile=module,
                        exportName=imported["imported"],
                    )
                    targets.update(self.export(module, imported["imported"], set()))
                proof = "import"  # 显式导入具有不同的解释来源。
        for target in targets:
            self.dependency(
                file,
                "symbol",
                target,
                resolved=True,
                targetId=target,
                targetFile=self.nodes[target].get("source_file", ""),
            )
        return targets, proof, True

    def kotlin_package_targets(self, file: str, package: str, name: str) -> set[str]:
        """包声明只证明潜在可见性，不证明构建单元或 expect/actual 的目标选择。"""
        targets = {
            target
            for target in self.kotlin_symbols.get((package, name), ())
            if self.nodes[target].get("source_file") == file
            or (
                self.declarations[target].get("visibility") != "private"
                and "private" not in self.declarations[target].get("modifiers", ())
            )
        }
        self.dependency(
            file,
            "package-set",
            package + "." + name,
            resolved=bool(targets),
            targetFiles=sorted(self.kotlin_packages.get(package, ())),
        )
        return targets

    def kotlin_unqualified(self, file: str, name: str) -> tuple[set[str], str, bool]:
        targets = self.kotlin_package_targets(file, self.files[file].get("package", ""), name)
        if targets:
            return targets, "kotlin-package", True
        for imported in self.files[file].get("imports", ()):
            if imported["kind"] == "star":
                self.resolve_module(file, imported["specifier"], import_kind=imported["kind"])
                targets.update(
                    self.kotlin_package_targets(
                        file, imported["specifier"].removesuffix(".*"), name
                    )
                )
        return targets, "kotlin-star-import" if targets else "no-declaration", True

    # 重导出与星号导出递归展开，循环分支不产生猜测目标。
    # 只有最外层完整结果可缓存，避免把循环中途的部分集合当作全集。
    def export(self, file: str, name: str, seen: set[tuple[str, str]]) -> set[str]:
        key = (file, name)
        if len(seen) > 128:
            self.depth_limit(file, "exports")
        if key in seen or key in self.export_active or len(seen) > 128:
            return set()
        outermost = not self.export_active  # 递归中间结果不能作为完整缓存。
        if outermost and key in self.export_cache:
            return set(self.export_cache[key])
        branch = seen | {key}  # 分支副本避免兄弟导出互相剪枝。
        self.export_active.add(key)
        result: set[str] = set()
        for row in (*self.named_exports.get(key, ()), *self.star_exports.get(file, ())):
            if row.get("specifier"):
                for target in self.resolve_module(file, row["specifier"]):
                    self.dependency(
                        file,
                        "exports",
                        target,
                        resolved=True,
                        targetFile=target,
                        exportName=name if row.get("star") else row.get("imported", name),
                    )
                    result.update(
                        self.export(
                            target, name if row.get("star") else row.get("imported", name), branch
                        )
                    )
            elif row.get("local"):
                targets, _, _ = self.lookup(file, row.get("scope_id", ""), row["local"])
                result.update(targets)
        self.export_active.discard(key)
        if outermost:
            self.export_cache[key] = frozenset(result)
        return result

    # 多级接收者链需要类型证据，不能丢弃中间对象简化名称。
    # self/this 先检查遮蔽，再从所属类型中定位成员。
    # Go 包级名称补充仅在词法查找未明确阻断时启用。
    def resolve_name(
        self, file: str, scope_id: str, name: str, seen: frozenset[tuple] = frozenset()
    ):
        if len(seen) > 128:
            self.depth_limit(file, "member")
        if (file, scope_id, name) in seen or len(seen) > 128:
            return set(), "alias-cycle", True
        if "." not in name:
            targets, reason, blocked = self.lookup(file, scope_id, name, seen)
            if self.files[file].get("language") == "kotlin":
                if not targets and not blocked:
                    return self.kotlin_unqualified(file, name)
                if (
                    targets
                    and reason == "scope"
                    and all(
                        self.scopes.get(self.declarations.get(target, {}).get("scope_id"), {}).get(
                            "kind"
                        )
                        == "module"
                        for target in targets
                    )
                ):
                    package_targets = self.kotlin_package_targets(
                        file, self.files[file].get("package", ""), name
                    )
                    if package_targets - targets:
                        return targets | package_targets, "kotlin-package", True
            if not targets and not blocked and self.files[file].get("language") == "go":
                targets = set(self.package_names.get((str(PurePosixPath(file).parent), name), ()))
                self.dependency(file, "package-set", name, resolved=bool(targets))
                if targets:
                    return targets, "package", True
            return targets, reason, blocked
        head, *remaining = name.split(".")
        if len(remaining) != 1:
            # Dropping intermediate receivers would falsely turn ns.object.f()
            # into ns.f(). Typed providers may refine this observation later.
            return set(), "member-chain-needs-types", True
        member = remaining[-1]  # 此时已拒绝多级接收者链。
        if head in {"self", "this"}:
            bindings, _ = self.binding(file, scope_id, head)
            if any(row["kind"] == "local" for row in bindings):
                return set(), "shadowed-receiver", True
            current = self.scopes.get(scope_id)
            while current and current["kind"] != "type":
                current = self.scopes.get(current["parent"])
            targets = (
                {
                    row["target"]
                    for row in self.scope_bindings.get(current["id"], {}).get(member, ())
                    if row["kind"] == "declaration"
                }
                if current
                else set()
            )
            return targets, "scope", True
        values, owner = self.binding(file, scope_id, head)
        targets = set()
        for binding in values:
            if binding["kind"] == "import":
                imported = self.files[file]["imports"][binding["import_index"]]
                modules = self.resolve_module(
                    file, imported["specifier"], import_kind=imported["kind"]
                )
                if imported["kind"] in {"named", "default"}:
                    imported_targets, _, _ = self.lookup(file, scope_id, head, seen)
                    for target in imported_targets:
                        declared = self.declarations.get(target, {})
                        targets.update(
                            row["target"]
                            for row in self.scope_bindings.get(
                                declared.get("body_scope_id"), {}
                            ).get(member, ())
                            if row["kind"] == "declaration"
                        )
                    if self.files[file].get("language") == "kotlin":
                        # 具名导入的成员必须属于该声明，不能取同文件任意顶层导出。
                        continue
                    if not imported_targets and self.files[file].get("language") == "python":
                        modules = self.resolve_module(
                            file, imported["specifier"].rstrip(".") + "." + imported["imported"]
                        )
                for module in modules:
                    self.dependency(
                        file, "exports", module, resolved=True, targetFile=module, exportName=member
                    )
                    targets.update(self.export(module, member, set()))
            elif binding["kind"] == "alias":
                alias_name = binding["target_name"] + "." + ".".join(remaining)
                alias_targets, _, _ = self.resolve_name(
                    file, owner, alias_name, seen | {(file, scope_id, name)}
                )
                targets.update(alias_targets)
            elif binding["kind"] == "declaration":
                declared = self.declarations[binding["target"]]
                targets.update(
                    row["target"]
                    for row in self.scope_bindings.get(declared["body_scope_id"], {}).get(
                        member, ()
                    )
                    if row["kind"] == "declaration"
                )
        return targets, "import" if targets else "member-call", True

    def objc_member_targets(self, file: str, reference: dict, targets: set[str]) -> set[str]:
        """仅在所属类或已导入头文件提供证据时补充 category/interface 方法候选。"""
        receiver = reference.get("receiver", "")
        if not receiver or "." in receiver or receiver == "super":
            return targets
        bindings, _ = self.binding(file, reference["scope_id"], receiver)
        if any(row["kind"] in {"local", "parameter"} for row in bindings):
            return set()
        visible_files = {file}
        for imported in self.files[file].get("imports", ()):
            if imported["kind"] == "include":
                visible_files.update(
                    self.resolve_module(file, imported["specifier"], import_kind=imported["kind"])
                )
        owner_names: set[str] = set()
        method_kind = reference.get("methodKind", "")
        if receiver == "self":
            current = self.scopes.get(reference["scope_id"])
            visited: set[str] = set()
            while current and current["kind"] != "type" and current["id"] not in visited:
                visited.add(current["id"])
                current = self.scopes.get(current["parent"])
            if current and current["kind"] == "type":
                owner = self.declarations.get(current["owner"], {})
                owner_names.add(owner.get("objcClass") or owner.get("name", ""))
            method_kind = method_kind or self.declarations.get(reference["caller_nid"], {}).get(
                "methodKind", ""
            )
        else:
            owner_names.add(receiver)
            method_kind = method_kind or "class"
        for visible_file in visible_files:
            if self.files[visible_file].get("language") not in {"objective-c", "objective-cpp"}:
                continue
            for declaration in self.files[visible_file].get("declarations", ()):
                if (
                    declaration["kind"] != "type"
                    or (declaration.get("objcClass") or declaration["name"]) not in owner_names
                ):
                    continue
                targets.update(
                    row["target"]
                    for row in self.scope_bindings.get(declaration["body_scope_id"], {}).get(
                        reference["nameTail"], ()
                    )
                    if row["kind"] == "declaration"
                )
        if method_kind in {"class", "instance"}:
            targets = {
                target
                for target in targets
                if self.declarations[target].get("methodKind", method_kind) == method_kind
            }
        return targets

    # 内建函数只有未被本地绑定遮蔽时才直接归类。
    # 全局同名回退明确标为 heuristic，不能因为只剩一个候选就升级。
    # 多目标保留候选集及未解析说明，而不是任意选择第一个。
    def bind_reference(self, file: str, reference: dict) -> None:
        name = reference["name"]
        if (
            self.files[file].get("language") == "python"
            and name in _BUILTINS
            and not self.binding(file, reference["scope_id"], name)[0]
        ):
            self.outcomes.append({**reference, "status": "builtin", "resolvedBy": "language"})
            return
        language = self.files[file].get("language")
        targets, proof, blocked = self.resolve_name(file, reference["scope_id"], name)
        if (
            language in {"objective-c", "objective-cpp"}
            and reference.get("member")
            and (reference.get("objcRole") == "message" or reference.get("objcSelector"))
        ):
            targets = self.objc_member_targets(file, reference, targets)
            if targets:
                proof = "objc-member"
        if not targets and not blocked and not reference.get("member"):
            targets = {
                target
                for target in self.names.get(reference["nameTail"], ())
                if language not in _MOBILE_LANGUAGES
                or self.nodes[target].get("language") == language
                or (
                    language == "objective-cpp"
                    and not reference.get("objcRole")
                    and not reference.get("objcSelector")
                    and self.nodes[target].get("language") in {"c", "cpp"}
                )
            }
            self.dependency(
                file,
                "lookup",
                "global:" + reference["nameTail"],
                resolved=bool(targets),
                occurrenceId=reference["occurrenceId"],
                ownerId=reference["caller_nid"],
            )
            proof = "heuristic"  # 同名匹配不构成精确绑定。
        if language in _MOBILE_LANGUAGES and reference["context"] == "call":
            callable_targets = {
                target for target in targets if self.declarations[target].get("kind") != "property"
            }
            if targets and not callable_targets:
                proof = "non-callable-binding"
            targets = callable_targets
        mobile_candidate = (
            language in _MOBILE_LANGUAGES
            and proof != "heuristic"
            and (
                proof.startswith("kotlin-")
                or reference.get("member")
                or reference.get("syntaxRecovery")
                or reference.get("bindingConservative")
                or any(
                    self.declarations[target].get("kind") == "method"
                    or self.declarations[target].get("extensionReceiver")
                    or self.declarations[target].get("syntaxRecovery")
                    or any(
                        modifier in self.declarations[target].get("modifiers", ())
                        for modifier in ("expect", "actual")
                    )
                    for target in targets
                )
            )
        )
        certainty = (
            "candidate"
            if len(targets) > 1 or mobile_candidate
            else "heuristic"
            if proof == "heuristic"
            else "exact"
        )
        if not targets or certainty == "candidate":
            reason = (
                "ambiguous"
                if len(targets) > 1
                else "insufficient-evidence"
                if targets
                else "member-call"
                if reference.get("member")
                else "no-declaration"
            )
            self.unresolved.append(
                {
                    **reference,
                    "name": reference["nameTail"],
                    "fullName": name,
                    "caller": reference["caller_nid"],
                    "reason": reason,
                    "reasonCode": proof,
                    "candidates": sorted(targets),
                }
            )
        self._publish_reference(file, reference, targets, certainty, proof)

    # 声明解析与运行时派发分别表达，结构绑定不声称分析了动态派发。
    # 候选排序决定稳定的候选集身份与边输出顺序。
    # 调用点身份随边保留，同一目标的不同源码出现不会混淆。
    def _publish_reference(
        self, file: str, reference: dict, targets: set[str], certainty: str, proof: str
    ) -> None:
        """Publish candidate identities and edges from one completed name lookup."""
        from modus.machine.store.ids import candidate_set_identity

        sorted_targets = sorted(targets)
        candidate_set_id = candidate_set_identity(sorted_targets) if len(sorted_targets) > 1 else ""
        self.outcomes.append(
            {
                **reference,
                "status": certainty if targets else "unresolved",
                "resolvedBy": proof,
                "candidateCount": len(sorted_targets),
                **({"candidateSetId": candidate_set_id} if candidate_set_id else {}),
            }
        )
        for target in sorted_targets:
            anchor = reference["call_site"]
            self.edges.append(
                {
                    "source": reference["caller_nid"],
                    "target": target,
                    "relation": "calls" if reference["context"] == "call" else "references",
                    "context": reference["context"],
                    "resolution": certainty,
                    "declaration_resolution": certainty,
                    "dispatch_resolution": "not-analyzed",
                    "resolvedBy": proof,
                    "binding_kind": "declared-exact"
                    if certainty == "exact"
                    else "heuristic"
                    if certainty == "heuristic"
                    else "runtime-candidate",
                    "confidence": "EXTRACTED" if certainty == "exact" else "INFERRED",
                    "source_file": file,
                    "source_location": f"L{anchor['line']}:{anchor['column']}",
                    "call_site": anchor,
                    "occurrenceId": reference["occurrenceId"],
                    **(
                        {
                            **({"candidateSetId": candidate_set_id} if candidate_set_id else {}),
                            "candidateCount": len(sorted_targets),
                            "reason_code": "machine.facts.binding-multiple-targets"
                            if len(targets) > 1
                            else "machine.facts.binding-insufficient-evidence",
                        }
                        if certainty == "candidate"
                        else {}
                    ),
                }
            )


# 可读键冲突只在冲突文件加入路径命名空间，保持普通键可读。
# 节点、作用域及引用字段同步映射，不能留下悬空的旧身份。
# 映射生成新对象，原文件观察仍可用于其他投影。
# 跨语言同名文件也可触发碰撞，原始发生身份继续作为持久证据。
def _isolate_file_identities(files: list[dict]) -> list[dict]:
    claims: dict[str, str] = {}
    conflicts: set[str] = set()
    for facts in files:
        for row in (*facts.get("nodes", ()), *facts.get("scopes", ())):
            if claims.setdefault(row["id"], facts["path"]) != facts["path"]:
                conflicts.add(row["id"])
    if not conflicts:
        return files
    result = []
    reference_fields = {
        "id",
        "parent",
        "scope_id",
        "body_scope_id",
        "source",
        "target",
        "caller_nid",
        "caller",
        "handlerId",
        "ownerId",
        "componentId",
    }
    for facts in files:
        suffix = "__" + hashlib.sha256(facts["path"].encode()).hexdigest()[:20]
        mapping = {
            row["id"]: row["id"] + suffix
            for row in (*facts.get("nodes", ()), *facts.get("scopes", ()))
            if row["id"] in conflicts
        }
        if not mapping:
            result.append(facts)
            continue

        def remap(value: object, key: str = "", mapping=mapping):
            if isinstance(value, dict):
                return {
                    field: mapping.get(item, item)
                    if field == "owner" and "bindings" in value and isinstance(item, str)
                    else remap(item, field)
                    for field, item in value.items()
                }
            if isinstance(value, list):
                return [remap(item, key) for item in value]
            if isinstance(value, str) and key in reference_fields:
                return mapping.get(value, value)
            return value

        result.append(remap(facts))
    return result


# 导入边连接文件节点，符号调用关系由后续名称绑定独立建立。
# 导入解析集中在完整项目视图，单文件提取缓存不携带跨文件推断。
def _bind_imports(project: _Project, file: str, facts: dict) -> None:
    for row in facts.get("imports", ()):
        for target in project.resolve_module(file, row["specifier"], import_kind=row["kind"]):
            source_id = next(
                (node["id"] for node in facts["nodes"] if node.get("kind") == "file"), ""
            )
            target_id = next(
                (
                    node["id"]
                    for node in project.files[target]["nodes"]
                    if node.get("kind") == "file"
                ),
                "",
            )
            if source_id and target_id:
                project.edges.append(
                    {
                        "source": source_id,
                        "target": target_id,
                        "relation": "imports",
                        "resolution": "candidate" if facts.get("language") == "kotlin" else "exact",
                        "binding_kind": "runtime-candidate"
                        if facts.get("language") == "kotlin"
                        else "declared-exact",
                        "resolvedBy": "kotlin-import"
                        if facts.get("language") == "kotlin"
                        else "import",
                        "confidence": "INFERRED"
                        if facts.get("language") == "kotlin"
                        else "EXTRACTED",
                        "source_file": file,
                        "source_location": f"L{row.get('line', 1)}:1",
                    }
                )


# 按拥有者组织绑定工作，使每次依赖观察都有明确归属。
# 工作排序稳定，输入文件枚举次序不应改变绑定结论。
# 文件局部边和项目绑定边一起返回，但仍保留独立绑定边视图。
# 诊断合并解析与绑定来源，后续阶段可以解释不同降级边界。
# 所有文件冻结完成后才进行项目绑定，避免枚举先后改变候选集合。
def bind_files(
    files: list[dict],
    root: Path,
) -> dict[str, Any]:
    """Resolve every import and reference in one complete frozen project."""
    files = _isolate_file_identities(files)
    project = _Project(files, root)
    work: dict[str, tuple[str, list[dict], bool]] = {}
    for file, facts in sorted(project.files.items()):
        if facts.get("imports"):
            work["@imports:" + file] = (file, facts["imports"], True)
        for reference in facts.get("references", ()):
            owner = reference["caller_nid"]
            work.setdefault(owner, (file, [], False))[1].append(reference)
    for owner, (file, references, imports_only) in sorted(work.items()):
        project.active_owner = owner  # 跨模块展开仍归属初始工作项。
        project.owner_files[owner] = file
        project.dependency(file, "binding-input", file, resolved=True, targetFile=file)
        if imports_only:
            _bind_imports(project, file, project.files[file])
        else:
            for reference in references:
                project.bind_reference(file, reference)
    return {
        "nodes": [node for file in files for node in file.get("nodes", ())],
        "edges": [edge for file in files for edge in file.get("edges", ())] + project.edges,
        "bindingEdges": project.edges,
        "unresolved_refs": project.unresolved,
        "referenceOutcomes": project.outcomes,
        "dependencies": project.dependencies,
        "diagnostics": project.diagnostics
        + [diagnostic for file in files for diagnostic in file.get("diagnostics", ())],
        "bindingContract": BINDING_CONTRACT_VERSION,  # 供消费者识别绑定协议。
        "bindingStats": {"boundOwners": len(work)},
    }
