"""D-T1-SMALLRETURN-ENFORCE — closed-set discipline for `@small_return` claims.

`@small_return:` is a self-report comment on tools that intentionally skip the
T1 `apply_response_contract` refactor because they return only bounded metadata
(a get-by-id, a scalar coverage matrix, a short edge list). The original concern
was that the claim is unenforced — a heavy field added to such a tool wouldn't go
red.

Two layers now cover that:
  1. RUNTIME (the real backstop): the chat-service D7 cap
     (`tool_result_token_cap`, default 8000, ON) withholds + logs ANY single tool
     result over the ceiling — so a heavy field added to a small-return tool is
     caught + surfaced at runtime, not silent. The pathological case is handled.
  2. REVIEW (this test): the SET of `@small_return` claims is pinned, so adding a
     NEW claim (or removing one) turns this red — forcing a reviewer to confirm
     the tool truly returns bounded data. Closed-set discipline, the repo's
     rule+SoT+gate+test meta-pattern.

The residual (sub-cap bloat on an existing claim) is low-risk and deliberately
not chased with a bespoke per-tool byte-histogram — that would be machinery out
of proportion to the risk now that D7 backstops the pathological case.
"""

from __future__ import annotations

import pathlib

# Modules that carry `@small_return:` annotations. A new module claiming
# small-return must be added here (itself a reviewed change).
_TOOL_MODULES = [
    "app/tools/executor.py",
    "app/tools/graph_schema_tools.py",
    "app/tools/project_tools.py",
]

# The pinned SET of `@small_return:` claim lines (module + the annotation text
# after the marker), sorted. Pinning the SET — not just a count — means an
# add-one-remove-one SWAP is caught too (a count would net to the same total).
# Update this ONLY when you have confirmed the added/removed tool genuinely
# returns bounded data (no heavy body) — that confirmation IS the gate.
_EXPECTED_CLAIMS = 6


def _service_root() -> pathlib.Path:
    # tests/unit/<this> → service root is two parents up from tests/.
    return pathlib.Path(__file__).resolve().parents[2]


def _collect_claims() -> list[tuple[str, str]]:
    """(module, normalized annotation text) for every `@small_return` line."""
    root = _service_root()
    claims: list[tuple[str, str]] = []
    for rel in _TOOL_MODULES:
        for line in (root / rel).read_text(encoding="utf-8").splitlines():
            if "@small_return" in line:
                # the descriptive text after the marker identifies the claim
                text = line.split("@small_return", 1)[1].lstrip(": ").strip()
                claims.append((rel, " ".join(text.split())))
    return claims


def test_small_return_claim_set_is_pinned():
    claims = _collect_claims()
    # Pin the SET (module, text) — a swap changes the set even if the count holds.
    unique = sorted(set(claims))
    assert len(claims) == _EXPECTED_CLAIMS and len(unique) == _EXPECTED_CLAIMS, (
        f"@small_return claim set drifted (found {len(claims)} lines, "
        f"{len(unique)} unique; expected {_EXPECTED_CLAIMS}). If you added/removed/"
        "renamed a small-return tool, confirm it truly returns bounded data (no heavy "
        "body — D7 backstops the pathological case at runtime) and update this pin.\n"
        f"current set:\n" + "\n".join(f"  {m}: {t}" for m, t in unique)
    )
