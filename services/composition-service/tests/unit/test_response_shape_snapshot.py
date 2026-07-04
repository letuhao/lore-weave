"""§13b — MCP response-shape contract SNAPSHOT (composition slice).

The per-tool guard tests (`test_outline_response_contract.py`,
`test_motif_response_contract.py`) assert *semantic* invariants — a heavy body is
absent at `detail=summary`, refs survive, summary < full. They do NOT pin the
EXACT ref set, so a silent RE-BLOAT (someone adds `synopsis` back into
`_OUTLINE_REF_FIELDS`) keeps every guard green while the summary payload grows
again — the 146K regression the Context Budget Law exists to kill.

This snapshot pins the committed ref set (see `loreweave_mcp.shape_snapshot`), so
drift in EITHER direction turns a test red. Regenerate an intentional change with
`WRITE_MCP_SHAPES=1 pytest tests/unit/test_response_shape_snapshot.py`.
"""
from __future__ import annotations

from loreweave_mcp import assert_or_write_shape_snapshot

from app.mcp.server import (
    _ARC_REF_FIELDS,
    _MOTIF_BOOK_REF_FIELDS,
    _MOTIF_REF_FIELDS,
    _OUTLINE_REF_FIELDS,
)


def test_response_shapes_match_committed_snapshot():
    assert_or_write_shape_snapshot(
        "composition",
        {
            "_OUTLINE_REF_FIELDS": _OUTLINE_REF_FIELDS,
            "_MOTIF_REF_FIELDS": _MOTIF_REF_FIELDS,
            "_MOTIF_BOOK_REF_FIELDS": _MOTIF_BOOK_REF_FIELDS,
            "_ARC_REF_FIELDS": _ARC_REF_FIELDS,
        },
        test_file=__file__,
    )
