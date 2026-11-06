from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from modus.config import ModusConfig
from modus.machine import (
    AnalysisIdentity,
    AnalysisOptions,
    EvidenceQuery,
    analyze_repository,
    open_analysis,
    query_evidence,
)
from modus.machine.errors import ProviderError
from modus.machine.facts.build_context import BuildContextResolver
from modus.machine.facts.compiler.cpp import _run_cpp
from modus.machine.facts.compiler.go import _run_go
from modus.machine.facts.compiler.java import _run_java
from modus.machine.facts.extension_registry import (
    ExtensionRegistry,
    RegisteredImplementation,
    builtin_extensions,
)
from modus.machine.facts.semantic_ir import SemanticFacts
from modus.machine.facts.semantic_providers import run_compiler_analysis
from modus.machine.facts.structural import extract
from modus.machine.runtime.toolchains import java_executable
from modus.paths import ModusPaths


# 夹具统一创建父目录，调用方只表达语言或框架需要的文件布局。
def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")
    return path


def test_java_packaged_openapi_declarations_bind_once_with_compiler(tmp_path: Path) -> None:
    if not java_executable("javac"):
        pytest.skip("javac is unavailable")
    from modus.machine.capability import compose
    from modus.machine.corpus import freeze
    from modus.machine.facts import observe
    from modus.machine.resolution import resolve

    _write(
        tmp_path / "acme/ContractApi.java",
        """package acme;
@interface OpenApiPostMapping { String apiUrl(); String apiName(); }
interface ContractApi {
    @OpenApiPostMapping(apiUrl="/contracts", apiName="创建合同")
    Boolean save(String request);
    @OpenApiPostMapping(apiUrl="/contracts/by-id", apiName="按编号保存")
    Boolean save(int request);
}
""",
    )
    corpus = freeze(tmp_path, compiler_mode="auto")
    with corpus.activate():
        resolved = resolve(observe(corpus))
        packet = next(iter(resolved.source_evidence.packets.values()))
        signals = [
            row for row in packet["authoringRecords"] if row["ruleId"] == "builtin.openapi-entry"
        ]
        assert len(signals) == 2
        assert len({row["entryId"] for row in signals}) == 2
        assert all(
            sum(
                entry["location"]["startLine"] == row["location"]["startLine"]
                for entry in packet["entries"]
                if entry["kind"] == "method"
            )
            == 2
            for row in signals
        )
        model = compose(resolved).model
    assert {row.entry_signature for row in model.slices} == {
        "POST /contracts",
        "POST /contracts/by-id",
    }
    assert model.seed_count == 2


# 最小多语言仓库同时提供源码与构建描述，验证单元发现而非目录猜测。
# C++ 夹具包含本地头文件，使头文件闭包也成为受测输入。
def _polyglot_project(root: Path) -> tuple[ModusPaths, ModusConfig]:
    _write(root / "app.py", "def main() -> int:\n    return 1\n")
    _write(root / "src/main/java/acme/App.java", "package acme; class App {}\n")
    _write(root / "pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>\n")
    _write(root / "web/app.ts", "export const value: number = 1;\n")
    _write(root / "web/tsconfig.json", '{"compilerOptions":{"strict":true}}\n')
    _write(root / "go/go.mod", "module example.com/demo\ngo 1.21\n")
    _write(root / "go/cmd/main.go", "package main\nfunc main() {}\n")
    _write(root / "native/local.h", "#pragma once\ninline int answer(){return 42;}\n")
    source = _write(
        root / "native/main.cpp",
        '#include "local.h"\nint compute(){return answer();}\nint main(){return compute();}\n',
    )
    (root / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(source.parent),
                    "file": str(source),
                    "arguments": ["clang++", "-std=c++17", "-I.", "-c", str(source)],
                }
            ]
        )
    )
    return ModusPaths.for_root(root), ModusConfig()


# 只解析上下文，不物化 Maven 查询，避免发现测试触发项目构建。
# 五种语言必须同时被保留，不能让首个提供者决定整仓库语言。
# 额外检查 Java 源集与 C++ 头文件，确认单元内元数据没有丢失。
def test_build_context_resolves_one_unit_for_each_builtin_provider(tmp_path: Path) -> None:
    paths, config = _polyglot_project(tmp_path)

    context = BuildContextResolver(paths, config, materialize=False).resolve()

    languages = {unit.language for unit in context.units}
    assert languages == {"python", "typescript", "java", "go", "cpp"}
    assert next(unit for unit in context.units if unit.language == "cpp").metadata[
        "headerClosure"
    ] == ["native/local.h"]
    assert (
        next(unit for unit in context.units if unit.language == "java").metadata["sourceSet"]
        == "main"
    )
    assert {diagnostic.code for diagnostic in context.diagnostics} <= {
        "machine.facts.maven-classpath-query-available"
    }


# 在本机 clang++ 可用时运行真实提供者，验证声明与调用都能形成事实。
# 缺少工具时显式跳过，不能把空输出当作分析成功。
@pytest.mark.skipif(shutil.which("clang++") is None, reason="clang++ is unavailable")
def test_cpp_provider_observes_declarations_and_calls(tmp_path: Path) -> None:
    paths, config = _polyglot_project(tmp_path)
    context = BuildContextResolver(paths, config, materialize=False).resolve()
    unit = next(unit for unit in context.units if unit.language == "cpp")

    facts = _run_cpp(paths, config, unit)

    names = {node.qualified_name for node in facts.nodes}
    assert any("answer" in name for name in names)
    assert any("compute" in name for name in names)
    # 真实提供者必须产生关系证据，仅识别名称不足以满足调用分析契约。
    assert any(edge.relation == "calls" for edge in facts.edges)


@pytest.mark.parametrize("language", ["java", "go"])
def test_compiler_keeps_nested_and_same_start_chained_calls(tmp_path: Path, language: str) -> None:
    if language == "java":
        if not java_executable("javac"):
            pytest.skip("javac is unavailable")
        _write(tmp_path / "pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>\n")
        _write(
            tmp_path / "Chain.java",
            """class Chain {
 Chain next() { return this; }
 Chain accept(Chain other) { return this; }
 void run() { next().next().next(); accept(accept(this)); }
}
""",
        )
        provider = _run_java
    else:
        if not shutil.which("go"):
            pytest.skip("go is unavailable")
        _write(tmp_path / "go.mod", "module example.test/chain\ngo 1.21\n")
        _write(
            tmp_path / "chain.go",
            """package chain
type Chain struct{}
func (c Chain) Next() Chain { return c }
func (c Chain) Accept(other Chain) Chain { return c }
func (c Chain) Run() { c.Next().Next().Next(); c.Accept(c.Accept(c)) }
""",
        )
        provider = _run_go
    paths, config = ModusPaths.for_root(tmp_path), ModusConfig()
    context = BuildContextResolver(paths, config, materialize=False).resolve()
    unit = next(unit for unit in context.units if unit.language == language)
    facts = provider(paths, config, unit)
    calls = [edge for edge in facts.edges if edge.operation.casefold() in {"next", "accept"}]
    assert len(calls) == len({edge.id for edge in calls}) == 5
    chain = [edge.call_site for edge in calls if edge.operation.casefold() == "next"]
    assert len({(anchor.line, anchor.column) for anchor in chain if anchor}) == 1
    assert len({(anchor.end_line, anchor.end_column) for anchor in chain if anchor}) == 3
    assert not [item for item in facts.dispositions if item.status in {"conflict", "rejected"}]


# 只替换 Python 提供者，其余注册项复用内置集合。
# 注入通过正式扩展契约完成，避免测试依赖全局注册表修改。
def _registry_with_python_provider(
    provider: Callable[..., SemanticFacts],
) -> ExtensionRegistry:
    builtins = builtin_extensions()
    providers = [
        registration
        for name, registration in builtins.compiler_providers.items()
        if name != "python"
    ]
    # 测试提供者带独立实现版本，缓存身份仍遵守扩展协议。
    providers.append(RegisteredImplementation("python", "fake-python/1", provider))
    return ExtensionRegistry.create(
        structural_extractors=builtins.structural_extractors.values(),
        compiler_providers=providers,
        entry_detectors=builtins.entry_detectors.values(),
        boundary_resolvers=builtins.boundary_resolvers.values(),
    )


# 同一提供者故障分别验证 auto 降级与 required 拒绝。
# 异常原文包含敏感标记，公开快照只能交付安全原因码。
# 成功路径先确认注入确实被调用，避免故障测试绕过提供者。
def test_fake_provider_is_injectable_and_optional_failure_is_local(tmp_path: Path) -> None:
    source = _write(tmp_path / "service.py", "def serve() -> None:\n    pass\n")
    paths = ModusPaths.for_root(tmp_path)
    config = ModusConfig()

    def successful_provider(*_args: object) -> SemanticFacts:
        return SemanticFacts()

    successful = run_compiler_analysis(
        paths,
        config,
        mode="auto",
        extensions=_registry_with_python_provider(successful_provider),
    )
    assert successful.analyzed_units
    assert source.as_posix().endswith("service.py")
    # 改变源码输入使成功缓存失效，后续失败必须真正经过注入提供者。
    source.write_text(
        source.read_text(encoding="utf-8") + "\n# force a distinct provider input\n",
        encoding="utf-8",
        newline="",
    )

    def failing_provider(*_args: object) -> SemanticFacts:
        raise ValueError("sensitive provider text must not escape")

    optional = run_compiler_analysis(
        paths,
        config,
        mode="auto",
        extensions=_registry_with_python_provider(failing_provider),
    )
    # 可选模式允许继续，但提供者状态不能伪装成成功。
    assert optional.provider_status[0]["status"] == "failed"
    assert optional.provider_status[0]["reasonCode"] == "machine.facts.execution-failed"
    assert "sensitive provider text" not in repr(optional.snapshot(tmp_path))

    with pytest.raises(ProviderError, match="machine.facts.required-provider-failed"):
        run_compiler_analysis(
            paths,
            config,
            mode="required",
            extensions=_registry_with_python_provider(failing_provider),
        )


# 夹具把页面路由、事件处理、网络请求和响应状态放在同一可追溯链路。
# Vue 另用模板事件验证不同语法入口仍产出一致的观察种类。
def _write_ui_framework_sources(web: Path) -> tuple[Path, Path, Path]:
    """Exercise filesystem routes, explicit client routes and component state together."""
    # 动态目录参数与页面默认导出共同构成 Next 页面路由证据。
    next_page = _write(
        web / "app/orders/[id]/page.tsx",
        """
import React, {useState} from 'react';
import axios from 'axios';
export default function Orders() {
  const [items, setItems] = useState([]);
  async function load() {
    const response = await axios.get('/api/orders');
    setItems(response.data);
  }
  return <button onClick={load}>{items.length}</button>;
}
""",
    )
    # 显式 React Router 配置用于区分文件约定与工厂声明两类入口。
    router = _write(
        web / "router.tsx",
        """
import {createBrowserRouter} from 'react-router-dom';
import Orders from './app/orders/[id]/page';
export const router = createBrowserRouter([{path: '/orders', element: <Orders />}]);
""",
    )
    vue = _write(
        web / "Counter.vue",
        """
<template><button @click="save">{{ count }}</button></template>
<script setup lang="ts">
import {ref} from 'vue';
const count = ref(0);
function save() { count.value++; }
</script>
""",
    )
    return next_page, router, vue


# 显式注册与文件约定路由同时覆盖，验证多种服务框架的统一输出。
# 框架导入和包清单是真实来源标记，测试不只提供熟悉的方法名。
def _write_server_framework_sources(tmp_path: Path, web: Path) -> tuple[Path, ...]:
    """Keep server registrations beside their real language and package markers."""
    # Express 样例先声明子路由再挂载，检查父前缀能够正确传播。
    express = _write(
        web / "server.ts",
        """
import express from 'express';
const app = express();
const router = express.Router();
function getOrder(req, res) { res.json({ok: true}); }
router.get('/orders/:id', getOrder);
app.use('/api', router);
""",
    )
    nest = _write(
        web / "orders.controller.ts",
        """
import {Controller, Get, Post} from '@nestjs/common';
@Controller('orders')
export class OrdersController {
  @Get(':id') getOrder() { return {}; }
  @Post() createOrder() { return {}; }
}
""",
    )
    # FastAPI 样例同时包含应用入口和带本地前缀的子路由。
    fastapi = _write(
        tmp_path / "backend/api.py",
        """
from fastapi import APIRouter, FastAPI
app = FastAPI()
router = APIRouter(prefix='/public')
@router.get('/orders/{order_id}')
def get_order(order_id: str): return {'id': order_id}
@app.post('/orders')
def create_order(): return {}
app.include_router(router, prefix='/api')
""",
    )
    go = _write(
        tmp_path / "backend/main.go",
        """
package main
import "github.com/gin-gonic/gin"
func getOrder(c *gin.Context) {}
func main() { r := gin.Default(); r.GET("/orders/:id", getOrder) }
""",
    )
    # Nuxt 放入独立包根，避免继承上级 Next 依赖而误判框架。
    nuxt_root = tmp_path / "nuxt"
    _write(nuxt_root / "package.json", '{"dependencies":{"nuxt":"4.0.0"}}')
    nuxt = _write(
        nuxt_root / "server/api/orders/[id].get.ts",
        "export default defineEventHandler((event) => ({id: event.context.params.id}));\n",
    )

    return express, nest, fastapi, go, nuxt


# 先检查结构提取的节点和关系，再经公开分析接口查询服务证据。
# 这覆盖从框架观察到持久化查询的完整交付边界。
# 文件路由参数应规范化，结果仍与本轮包身份绑定。
def test_framework_fixtures_cover_server_ui_and_filesystem_routes(tmp_path: Path) -> None:
    web = tmp_path / "web"
    _write(
        web / "package.json",
        json.dumps(
            {
                "dependencies": {
                    "next": "15.0.0",
                    "react": "19.0.0",
                    "react-router-dom": "7.0.0",
                    "express": "5.0.0",
                    "@nestjs/common": "11.0.0",
                    "axios": "1.0.0",
                    "vue": "3.0.0",
                }
            }
        ),
    )
    next_page, router, vue = _write_ui_framework_sources(web)
    express, nest, fastapi, go, nuxt = _write_server_framework_sources(tmp_path, web)

    result = extract(
        [next_page, express, nest, router, vue, fastapi, go, nuxt],
        cache_root=tmp_path,
    )

    kinds = {str(node.get("kind")) for node in result["nodes"]}
    relations = {str(edge.get("relation")) for edge in result["edges"]}
    labels = {str(node.get("label")) for node in result["nodes"]}
    # 检查最低必要种类而非完整快照，允许后续增加兼容观察。
    assert {"page-route", "page-action", "request", "state"} <= kinds
    assert {"handled_by", "exposes"} & relations
    assert "/orders/{id}" in labels
    assert any("orders" in label for label in labels)

    receipt = analyze_repository(tmp_path, AnalysisOptions(compiler_mode="off"))
    bundle = open_analysis(
        tmp_path,
        AnalysisIdentity(receipt.bundle_digest, receipt.baseline_digest),
    )
    services = query_evidence(bundle, EvidenceQuery("services"))
    # 查询必须回到同一发布包，不能退回其他已存在缓存。
    assert services.bundle_digest == receipt.bundle_digest
    assert services.items
