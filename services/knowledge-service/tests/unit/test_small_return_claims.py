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

# The pinned count of `@small_return:` claims across the tool modules. Bump this
# ONLY when you have confirmed the added/removed tool genuinely returns bounded
# data (no heavy body) — that confirmation is the point of the gate.
_EXPECTED_SMALL_RETURN_CLAIMS = 6


def _service_root() -> pathlib.Path:
    # tests/unit/<this> → service root is two parents up from tests/.
    return pathlib.Path(__file__).resolve().parents[2]


def test_small_return_claim_set_is_pinned():
    root = _service_root()
    total = 0
    per_module: dict[str, int] = {}
    for rel in _TOOL_MODULES:
        text = (root / rel).read_text(encoding="utf-8")
        n = text.count("@small_return")
        per_module[rel] = n
        total += n
    assert total == _EXPECTED_SMALL_RETURN_CLAIMS, (
        f"@small_return claim count drifted to {total} (per-module {per_module}); "
        "if you added/removed a small-return tool, confirm it truly returns bounded "
        "data (no heavy body — D7 backstops the pathological case at runtime) and "
        f"update _EXPECTED_SMALL_RETURN_CLAIMS to {total}."
    )
