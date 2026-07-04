"""§13b — MCP response-shape contract SNAPSHOT (translation slice).

Pins the committed ref set for the refactored translation SET tools
(`translation_list_versions`, `translation_job_status`) so a silent re-bloat of a
summary payload (e.g. a full translated body sneaking back into a ref tuple) turns
a test red — the per-tool guards in `test_mcp_server.py` only assert heavy fields
are absent, not the exact set.

Regenerate an intentional change with
`WRITE_MCP_SHAPES=1 pytest tests/test_response_shape_snapshot.py`.
"""
from __future__ import annotations

from loreweave_mcp import assert_or_write_shape_snapshot

from app.mcp.server import _JOB_STATUS_CHAPTER_REF_FIELDS, _VERSION_REF_FIELDS


def test_response_shapes_match_committed_snapshot():
    assert_or_write_shape_snapshot(
        "translation",
        {
            "_VERSION_REF_FIELDS": _VERSION_REF_FIELDS,
            "_JOB_STATUS_CHAPTER_REF_FIELDS": _JOB_STATUS_CHAPTER_REF_FIELDS,
        },
        test_file=__file__,
    )
