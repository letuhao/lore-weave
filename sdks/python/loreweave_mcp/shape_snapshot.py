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

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path


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


def assert_or_write_shape_snapshot(
    service: str,
    ref_sets: Mapping[str, Iterable[str]],
    *,
    test_file: str,
) -> None:
    """Assert the service's ref-field sets match the committed snapshot.

    With ``WRITE_MCP_SHAPES=1`` in the environment, (re)writes the JSON and skips
    (the intentional-change escape hatch). Otherwise a mismatch — in EITHER
    direction — fails, catching both a dropped ref and a silent re-bloat.

    ``test_file`` is the caller's ``__file__`` (used to locate the repo root).
    """
    built = build_shape_map(ref_sets)
    root = repo_root_from(test_file)
    contract_path = root / "contracts" / "mcp-response-shapes" / f"{service}.json"
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
