"""TOOLV2 LOOP #163 — run_close told the caller a sibling tool lies. It does not.

composition_authoring_run_close's description said the generic jobs_cancel "does NOT work on a run
(a run is not a background job; it silently no-ops)".

Measured against a real run, with the service argument jobs_cancel requires:

    jobs_cancel(service="composition", job_id=<run_id>)
      -> {"code": "NOT_FOUND", "message": "not found or not accessible"}
    run status afterwards: report_ready (unchanged)

So jobs_cancel refuses VISIBLY. The first half of the sentence is right — jobs_cancel cannot stop a
run, and run_close is the only tool that can — but "it silently no-ops" is false.

That half matters more than it looks. A silent no-op and an explicit deny call for opposite
reactions: the first means "this did nothing and told you nothing, go elsewhere", the second means
"you addressed the wrong thing". Telling a model the sibling lies teaches it to distrust a correct
signal it will actually receive, which is the same misattributed-blame failure as #150 — advice
that cannot be acted on is worse than none.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _close_description() -> str:
    start = BODY.index('name="composition_authoring_run_close"')
    return BODY[start: BODY.index("meta=require_meta", start)]


def test_the_silent_no_op_claim_is_gone():
    assert "silently no-ops" not in _close_description(), (
        "jobs_cancel is described as silently no-opping on a run again; measured, it answers "
        "'not found or not accessible' and leaves the run untouched"
    )


def test_the_true_part_of_the_warning_survives():
    """The steer is still needed — jobs_cancel genuinely cannot stop a run — so the correction
    must not delete the guidance along with the false clause."""
    desc = _close_description()
    assert "jobs_cancel" in desc, "the caller still needs to know which tool NOT to reach for"
    assert "ONLY" in desc and "stop a run" in desc
    assert "not found or not accessible" in desc, (
        "naming the answer jobs_cancel actually gives is what makes the warning verifiable"
    )
