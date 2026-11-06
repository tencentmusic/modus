"""Extracted implementation modules remain part of persisted cache identity.

Moving a visitor or grammar table must not leave its old cache reusable after
that implementation changes. These checks model a change between invocations.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from pathlib import Path

import pytest

from modus.machine.facts.extraction_cache import implementation_fingerprint
from modus.machine.facts.frontend import _framework_implementation


@pytest.mark.parametrize(
    ("module_name", "fingerprint"),
    (
        ("native_visitor", implementation_fingerprint),
        ("native_visitor", _framework_implementation),
        ("native_syntax", implementation_fingerprint),
        ("native_syntax", _framework_implementation),
        ("native_objc", implementation_fingerprint),
        ("native_swift", implementation_fingerprint),
        ("native_cpp", implementation_fingerprint),
        ("native_kotlin", implementation_fingerprint),
        ("frontend_context", _framework_implementation),
        ("frontend_state", _framework_implementation),
        ("frontend_server", _framework_implementation),
    ),
)
def test_implementation_change_invalidates_extraction_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    fingerprint: Callable[[], str],
) -> None:
    module = import_module(f"modus.machine.facts.{module_name}")
    assert module.__file__ is not None
    original = Path(module.__file__).read_bytes()
    before = fingerprint()

    changed = tmp_path / f"{module_name}.py"
    changed.write_bytes(original + b"\n# changed extraction implementation\n")
    monkeypatch.setattr(module, "__file__", str(changed))

    assert fingerprint() != before


def test_config_change_rebinds_cached_syntax_like_a_fresh_final_tree(tmp_path: Path) -> None:
    import json

    from modus.machine.facts.structural import extract

    warm, cold = tmp_path / "warm", tmp_path / "cold"
    for root in (warm, cold):
        root.mkdir()
        (root / "app.ts").write_text(
            "import { run } from '@impl';\nexport function main() { return run(); }\n"
        )
        (root / "first.ts").write_text("export function run() { return 1; }\n")
        (root / "second.ts").write_text("export function run() { return 2; }\n")

    def config(root: Path, target: str) -> None:
        (root / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@impl": [target]}}})
        )

    def observe(root: Path):
        return extract(sorted(root.glob("*.ts")), cache_root=root)

    config(warm, "first.ts")
    first = observe(warm)
    config(warm, "second.ts")
    config(cold, "second.ts")
    updated, fresh = observe(warm), observe(cold)
    assert updated["cacheStats"]["reusedFiles"] == 3
    assert updated["edges"] == fresh["edges"]
    assert updated["edges"] != first["edges"]
    assert updated["unresolved_refs"] == fresh["unresolved_refs"]
