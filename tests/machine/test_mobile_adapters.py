"""客户端语法观察与保守绑定：以最小真实语法模式固定回归。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modus.machine.corpus.source_snapshot import SourceSnapshot
from modus.machine.facts.native_binding import bind_files
from modus.machine.facts.native_parser import parse_file


def _parse(root: Path, name: str, source: str) -> dict[str, Any]:
    return parse_file(SourceSnapshot(root / name, source))


def test_objc_selectors_categories_properties_and_callbacks(tmp_path: Path) -> None:
    facts = _parse(
        tmp_path,
        "View.m",
        """#import "View.h"
@import UIKit;
@interface View (Binding) <Binder>
@property(nonatomic, strong) NSString *title;
- (void)send:(NSString *)text done:(void(^)(int))done;
@end
@implementation View (Binding)
+ (void)run {}
- (void)run { [self send:title done:handler]; @selector(send:done:); }
@end
""",
    )
    assert not facts["diagnostics"]
    assert {row["kind"] for row in facts["imports"]} == {"include", "module"}
    types = [row for row in facts["declarations"] if row["kind"] == "type"]
    assert all(row["objcClass"] == "View" and row["category"] == "Binding" for row in types)
    assert any(
        row["name"] == "title" and row["kind"] == "property" for row in facts["declarations"]
    )
    selector = next(row for row in facts["declarations"] if row["name"] == "send:done:")
    assert selector["declarationOnly"]
    assert {row["methodKind"] for row in facts["declarations"] if row["name"] == "run"} == {
        "class",
        "instance",
    }
    assert any(
        row["name"] == "self.send:done:" and row["context"] == "call" for row in facts["references"]
    )
    assert any(
        row["name"] == "send:done:" and row["context"] == "callback" for row in facts["references"]
    )
    assert all("handler" not in row["signature"] for row in facts["declarations"])


def test_objc_comment_and_string_pseudo_code_is_not_extracted(tmp_path: Path) -> None:
    facts = _parse(
        tmp_path,
        "Comment.m",
        """/*
#import "Fake.h"
@interface Fake : NSObject
- (void)fake { [self fake]; }
@end
*/
const char *text = "@implementation Fake";
""",
    )
    assert not facts["declarations"]
    assert not facts["imports"]
    assert not facts["references"]


def test_swift_labels_overloads_extensions_and_private_exports(tmp_path: Path) -> None:
    facts = _parse(
        tmp_path,
        "View.swift",
        """import UIKit
@MainActor public struct Binder<T: AnyObject> {
    weak var target: T?
    init(target: T) { self.target = target }
    func bind(_ value: Int, to target: T) { use(value) }
    func bind(to target: T) { use(target) }
}
private extension Binder where T: UIView {
    var text: String { return target.name }
    func refresh() { viewModel.$title.bind(to: label.text) }
}
private func hidden() {}
""",
    )
    assert not facts["diagnostics"]
    binds = [row for row in facts["declarations"] if row["name"] == "bind"]
    assert len({row["id"] for row in binds}) == 2
    assert {tuple(row["argumentLabels"]) for row in binds} == {("_", "to"), ("to",)}
    assert all("use(" not in row["signature"] for row in binds)
    extension = next(row for row in facts["declarations"] if row.get("swiftKind") == "extension")
    assert extension["extensionTarget"] == "Binder"
    assert extension["constraints"] == ["where T: UIView"]
    assert not any(row["name"] == "hidden" for row in facts["exports"])
    assert any(row["name"] == "viewModel.$title.bind" for row in facts["references"])
    method_scope = next(
        scope for scope in facts["scopes"] if scope["id"] == binds[0]["body_scope_id"]
    )
    assert {row["name"] for row in method_scope["bindings"]} >= {"value", "target"}


def test_kotlin_packages_imports_extensions_and_compose_lambdas(tmp_path: Path) -> None:
    facts = _parse(
        tmp_path,
        "View.kt",
        """package sample.ui
import sample.model.View as Model
import sample.state.*
class View {
    companion object {
        fun of(value: View): View = value
    }
    fun render() {
        val title by flow.collectAsState()
        WithViewModel<Model> { vm ->
            Box { Text(title) }
            vm.uploadConfig(value = title)
        }
    }
}
inline fun <reified VM> View.model(): VM where VM: Model { return get(this) }
private fun hidden() {}
""",
    )
    assert facts["analysisCompleteness"] == "partial"
    assert facts["diagnostics"][0]["code"] == "machine.facts.kotlin-generic-call-candidate"
    assert facts["package"] == "sample.ui"
    assert facts["imports"][0]["local"] == "Model"
    assert facts["imports"][1]["kind"] == "star"
    assert any(row["qualified_name"] == "View.Companion.of" for row in facts["declarations"])
    assert (
        next(row for row in facts["declarations"] if row["name"] == "model")["extensionReceiver"]
        == "View"
    )
    assert not any(row["name"] == "hidden" for row in facts["exports"])
    calls = [row["name"] for row in facts["references"]]
    assert calls.count("WithViewModel") == 1
    assert {"Box", "Text", "vm.uploadConfig", "flow.collectAsState"} <= set(calls)
    assert not any(row["name"] == "Box" for row in facts["declarations"])
    assert any(
        row["name"] == "vm" and row["kind"] == "parameter"
        for scope in facts["scopes"]
        for row in scope["bindings"]
    )


def test_cpp_namespaces_prototypes_and_template_receivers(tmp_path: Path) -> None:
    facts = _parse(
        tmp_path,
        "Model.hpp",
        """namespace Shared {
class Model { public: void Run(int value); };
void Model::Run(int value) { Factory<Model>::Create(); }
}
""",
    )
    assert not facts["diagnostics"]
    assert any(
        row["qualified_name"] == "Shared.Model.Run" and row.get("declarationOnly")
        for row in facts["declarations"]
    )
    assert any(
        row["qualified_name"] == "Shared.Model.Run" and row.get("declarationOnly") is False
        for row in facts["declarations"]
    )
    assert any(row["name"] == "Factory.Create" for row in facts["references"])


def test_cpp_unexpanded_registration_is_not_a_method(tmp_path: Path) -> None:
    facts = _parse(
        tmp_path,
        "Model.hpp",
        """class Model {
REGISTER_MODEL(Model, Type::Example)
public:
void Run();
};
""",
    )
    assert facts["analysisCompleteness"] == "partial"
    assert not any(row["name"] == "REGISTER_MODEL" for row in facts["declarations"])
    assert any(row["name"] == "Run" for row in facts["declarations"])


def test_kotlin_import_and_source_sets_remain_candidates(tmp_path: Path) -> None:
    files = [
        _parse(
            tmp_path,
            "Caller.kt",
            "package client\nimport api.execute as run\nfun main() { run() }\n",
        ),
        _parse(tmp_path, "Common.kt", "package api\nexpect fun execute()\n"),
        _parse(tmp_path, "Android.kt", "package api\nactual fun execute() {}\n"),
    ]
    result = bind_files(files, tmp_path)
    edges = [row for row in result["bindingEdges"] if row["relation"] == "calls"]
    assert len(edges) == 2
    assert all(row["resolution"] == "candidate" for row in edges)


def test_mobile_parameters_block_global_homonyms(tmp_path: Path) -> None:
    for name, source in {
        "View.kt": "fun action() {}\nfun run(action: () -> Unit) { action() }\n",
        "View.swift": "func action() {}\nfunc run(action: () -> Void) { action() }\n",
    }.items():
        result = bind_files([_parse(tmp_path, name, source)], tmp_path)
        assert not any(row["relation"] == "calls" for row in result["bindingEdges"])
        assert any(row["reasonCode"] == "shadowed-binding" for row in result["unresolved_refs"])


def test_swift_module_name_does_not_resolve_as_filename(tmp_path: Path) -> None:
    files = [
        _parse(tmp_path, "View.swift", "import UIKit\nclass View {}"),
        _parse(tmp_path, "UIKit.swift", "class UIKit {}"),
    ]
    assert not bind_files(files, tmp_path)["bindingEdges"]


def test_objc_instance_and_class_methods_stay_distinct(tmp_path: Path) -> None:
    facts = _parse(
        tmp_path,
        "View.m",
        """@implementation View
+ (void)refresh {}
- (void)refresh {}
- (void)run { [self refresh]; }
@end
""",
    )
    result = bind_files([facts], tmp_path)
    methods = {row["id"]: row for row in result["nodes"] if row["kind"] == "method"}
    calls = [row for row in result["bindingEdges"] if row["relation"] == "calls"]
    assert len(calls) == 1
    assert calls[0]["resolution"] == "candidate"
    assert methods[calls[0]["target"]]["methodKind"] == "instance"
