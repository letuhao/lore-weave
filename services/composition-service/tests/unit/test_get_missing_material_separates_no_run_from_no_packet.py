"""TOOLV2 LOOP #275 — "no material check has been run for this plan yet", about a plan that does
not exist.

`plan_get_missing_material` is the free read-back of the last material packet. It works: on the run
#274 computed a packet for, it returned the identical buckets (recovered 1, review 0, ask 6,
unavailable 0) plus `computed_at` and `stale: false`, and it spends nothing.

Measured on a fabricated run_id, it answered:

    {"packet": null, "note": "no material check has been run for this plan yet"}

There is no such plan. Its two siblings in the same namespace — plan_find_missing_material and
plan_bootstrap_propose — answer "not found or not accessible" for that same id. So three tools, one
run, two stories, and the cheapest one tells the friendliest lie: an agent that believes it goes on
to call the search, which then refuses.

The cause is a None that meant two things. `get_material_review` reads the artifact and never looks
the RUN up, so it returns None both for "no such run" and for "run exists, never searched", and the
handler collapsed both into the sentence that is only true for the second.

Not an oracle concern: conflating them is the SAFE direction, but the siblings already refuse by
name for an unreachable run under the same book gate, so nothing is protected by this tool being
vaguer — only the caller is misled.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"


def _handler() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("async def plan_get_missing_material(")
    return body[start: body.index("\n@mcp_server.tool", start)]


def test_an_unreachable_run_is_refused_like_its_siblings():
    fn = _handler()
    assert "raise uniform_not_accessible()" in fn, (
        "an unknown run is reported as 'no material check yet' again — the same sentence a real "
        "un-searched run gets, and a claim that the plan exists"
    )
    assert "get_run_detail(" in fn, "the run must actually be looked up to tell the two apart"


def test_a_real_run_without_a_packet_still_says_so():
    """The correction must not swallow the honest case: a run that exists and has never been
    searched is exactly what that note is for."""
    fn = _handler()
    assert '"note": "no material check has been run for this plan yet"' in fn
    assert '"packet": None' in fn


def test_the_refusal_is_reached_only_when_the_run_is_missing():
    """Order matters: the packet read comes first, so an existing packet is returned without the
    extra lookup, and the run check only runs on the None path."""
    fn = _handler()
    assert fn.index("get_material_review(") < fn.index("get_run_detail("), (
        "the run lookup moved ahead of the packet read — every successful call now pays for it"
    )
    assert "if out is None:" in fn


def test_the_happy_path_returns_the_packet_unchanged():
    fn = _handler()
    assert fn.rstrip().endswith("return out"), (
        "the packet is no longer returned as-is; the read-back must not reshape what "
        "plan_find_missing_material computed"
    )
