"""§13b — MCP response-shape contract SNAPSHOT (jobs slice).

Pins the committed ref set for `jobs_list` (`_JOB_REF_FIELDS`) so a silent
re-bloat (params/error sneaking back into the summary ref set) turns a test red.
`test_jobs_list_summary_drops_heavy_params` asserts the heavy fields are dropped;
this snapshot pins the exact set that survives.

Regenerate an intentional change with
`WRITE_MCP_SHAPES=1 pytest tests/test_response_shape_snapshot.py`.
"""
from __future__ import annotations

from loreweave_mcp import assert_or_write_shape_snapshot

from app.mcp.server import _JOB_REF_FIELDS


def test_response_shapes_match_committed_snapshot():
    assert_or_write_shape_snapshot(
        "jobs",
        {"_JOB_REF_FIELDS": _JOB_REF_FIELDS},
        test_file=__file__,
    )
