"""§13b — MCP response-shape contract SNAPSHOT helper (shared kit).

`apply_response_contract` (this kit) lets a SET tool return a *reference-first*
summary: only `ref_fields` survive at `detail=summary`, the heavy body is dropped.
The savings are real ONLY as long as `ref_fields` stays small. Per-tool guard
tests assert "this heavy field is absent" — but they don't pin the EXACT set, so
a silent RE-BLOAT (a heavy field added back into a ref tuple) keeps them green
while the summary payload grows again. That is the 146K regression the Context
Budget Law exists to prevent.

This helper pins the committed ref-field set for every refactored SET tool into a
cross-cutting JSON under `contracts/mcp-response-shapes/<service>.json`, so drift
in EITHER direction turns a test red. It mirrors the frontend-tool contract
machinery (a committed JSON + env-gated regen): each provider service calls
`assert_or_write_shape_snapshot("<service>", {CONST_NAME: ref_tuple, ...})` from
one tiny test. Regenerate an intentional change with `WRITE_MCP_SHAPES=1 pytest …`
and commit the JSON alongside the code.
"""
from __future__ import annotations

import ast
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

# The reference-first keyword args whose value must be a snapshot-pinned NAMED
# constant, never an inline literal (an inline tuple escapes the drift guard).
_REF_KW = {"ref_fields", "node_ref", "edge_ref"}


def _assert_no_inline_ref_literals(service: str, modules: Iterable) -> None:
    """§13/MED-1: fail if any `apply_response_contract(...)` in a tool module passes an
    INLINE literal (tuple/list/set/constant) to ref_fields/node_ref/edge_ref. Such a
    literal never becomes a named `*_REF_FIELDS` constant, so the snapshot guard can't
    pin it and a re-bloat sails through. A NAME is allowed — it is either a pinned
    constant OR a helper parameter fed pinned constants at its callers (the knowledge
    `_project_graph(node_ref, edge_ref)` indirection), so requiring a literal-free call
    site is false-positive-free while closing the quickest re-bloat route."""
    for mod in modules:
        src_path = getattr(mod, "__file__", None)
        if not src_path:
            continue
        try:
            tree = ast.parse(Path(src_path).read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover — unreadable/compiled module, skip
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if fname != "apply_response_contract":
                continue
            for kw in node.keywords:
                if kw.arg in _REF_KW and isinstance(
                    kw.value, (ast.Tuple, ast.List, ast.Set, ast.Constant)
                ):
                    raise AssertionError(
                        f"{service}: apply_response_contract in {Path(src_path).name}:"
                        f"{kw.value.lineno} passes an INLINE literal to `{kw.arg}=` — use a "
                        f"named *_REF_FIELDS constant so the snapshot pins it (§13/MED-1)."
                    )


def repo_root_from(start: str | Path) -> Path:
    """Walk up from a test file until the monorepo root (has contracts/ + services/).

    Robust to the differing test-dir depths across services (tests/ vs tests/unit/)
    so callers don't hardcode a fragile ``parents[N]``.
    """
    p = Path(start).resolve()
    for parent in p.parents:
        if (parent / "contracts").is_dir() and (parent / "services").is_dir():
            return parent
    raise RuntimeError(f"repo root (contracts/ + services/) not found above {start}")


def build_shape_map(ref_sets: Mapping[str, Iterable[str]]) -> dict[str, list[str]]:
    """{const_name: ref_tuple} → the normalized, sort-stable snapshot dict."""
    return {name: sorted(fields) for name, fields in sorted(ref_sets.items())}


def _scan_ref_field_names(modules: Iterable) -> set[str]:
    """Every module-level ``*_REF_FIELDS`` constant (a tuple/list/set of str) across
    the given tool modules — the universe of ref sets that COULD feed
    ``apply_response_contract``. §13 coverage: each must be snapshot-pinned or a new
    one silently escapes the drift guard (the un-pinned-constant hole)."""
    found: set[str] = set()
    for mod in modules:
        for name in dir(mod):
            if not name.endswith("_REF_FIELDS"):
                continue
            val = getattr(mod, name)
            if isinstance(val, (tuple, list, set, frozenset)) and all(
                isinstance(x, str) for x in val
            ):
                found.add(name)
    return found


def assert_or_write_shape_snapshot(
    service: str,
    ref_sets: Mapping[str, Iterable[str]],
    *,
    test_file: str,
    scan_modules: Iterable | None = None,
) -> None:
    """Assert the service's ref-field sets match the committed snapshot.

    With ``WRITE_MCP_SHAPES=1`` in the environment, (re)writes the JSON and skips
    (the intentional-change escape hatch). Otherwise a mismatch — in EITHER
    direction — fails, catching both a dropped ref and a silent re-bloat.

    ``test_file`` is the caller's ``__file__`` (used to locate the repo root).

    ``scan_modules`` (§13 coverage meta-check): the tool module(s) that DEFINE the
    ref constants. The helper introspects them for every ``*_REF_FIELDS`` name and
    asserts each is present in ``ref_sets`` — so ADDING a new ref constant + tool
    WITHOUT adding it to this snapshot turns the test RED (an unproven/un-pinned item
    can't silently ship). This is the machine-checked half of §13 ("checklist → test,
    not self-report").
    """
    if scan_modules is not None:
        scan_modules = list(scan_modules)
        # (a) every `*_REF_FIELDS` constant DEFINED in a tool module is pinned, and
        # (b) no call site passes an inline literal that would dodge (a). Coverage
        # boundary (honest, per MED-1): this pins every ref set that is a NAMED
        # `*_REF_FIELDS` constant in a LISTED module + rejects inline literals; a
        # renamed constant (no `_REF_FIELDS` suffix) or a ref set in a module NOT in
        # `scan_modules` still relies on convention + review, not this check.
        _assert_no_inline_ref_literals(service, scan_modules)
        defined = _scan_ref_field_names(scan_modules)
        pinned = set(ref_sets)
        missing = defined - pinned
        assert not missing, (
            f"{service}: ref-field constant(s) {sorted(missing)} are defined but NOT "
            "snapshot-pinned — add them to the snapshot test's ref_sets (§13 coverage: "
            "an un-pinned ref set escapes the drift guard). If a constant is intentionally "
            "not a tool ref, rename it off the *_REF_FIELDS convention."
        )
    built = build_shape_map(ref_sets)
    root = repo_root_from(test_file)
    contract_path = root / "contracts" / "mcp-response-shapes" / f"{service}.json"
    # audit MED-2: WRITE_MCP_SHAPES=1 makes this test SKIP (regen), not assert. If it
    # ever leaks into a gating CI profile, all snapshot guards would silently go green-
    # by-skip and drift would sail through. Fail LOUDLY when both are set — a CI run
    # must never be in write mode.
    if os.environ.get("WRITE_MCP_SHAPES") == "1" and os.environ.get("CI"):
        raise RuntimeError(
            "WRITE_MCP_SHAPES=1 under CI — the snapshot guard would skip, not assert. "
            "Regenerate locally and commit the JSON; never set WRITE_MCP_SHAPES in CI."
        )
    if os.environ.get("WRITE_MCP_SHAPES") == "1":
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(built, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        import pytest

        pytest.skip(f"regenerated {contract_path.relative_to(root)}")
    assert contract_path.exists(), (
        f"{contract_path} missing — generate with WRITE_MCP_SHAPES=1 pytest "
        f"(from services/{service}-service)"
    )
    on_disk = json.loads(contract_path.read_text(encoding="utf-8"))
    assert on_disk == built, (
        f"{service} MCP response-shapes drifted from the committed snapshot — a "
        "ref-field set changed. If intentional, regenerate with WRITE_MCP_SHAPES=1; "
        "if not, you likely re-bloated a summary payload (Context Budget Law §13b)."
    )
