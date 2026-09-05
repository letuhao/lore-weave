"""TOOLV2 LOOP #147 — an arc built from a template did not record which template.

composition_arc_get on an arc that composition_arc_apply had just materialized from template
019f0d28 reported `arc_template_id: null`. composition_arc_template_drift exists to answer "did
this arc drift from the TEMPLATE it came from (its pinned arc_template_id + template_version)?" —
so with the provenance unwritten it has nothing to answer about.

Measured: 1 of 137 arc/saga nodes in the database carried an arc_template_id, and apply is the
only thing that creates an arc FROM a template.

Unlike the tracks/roster question recorded as DQ-18, this one is not a design choice. The column
exists, composition_arc_edit(op=create) accepts it as a first-class argument, the drift tool names
it as its input, and StructureRepo.update already whitelists it. It was simply never written on
the path that has the value in hand.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "engine" / "arc_apply.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _live_apply() -> str:
    start = BODY.index("async def apply_arc_to_spec(")
    nxt = BODY.find("\nasync def ", start + 10)
    return BODY[start: nxt if nxt != -1 else len(BODY)]


def test_apply_stamps_both_halves_of_the_provenance():
    live = _live_apply()
    assert '"arc_template_id": arc_template.id' in live, (
        "the arc no longer records the template it came from — composition_arc_template_drift "
        "has nothing to compare against"
    )
    assert '"template_version": arc_template.version' in live, (
        "drift is against a template VERSION; the id alone cannot tell you the template moved"
    )


def test_the_stamp_cannot_fail_a_committed_apply():
    """The outline tree is committed before this runs. Losing the whole apply over a metadata
    label would trade something real for something descriptive, so the write is best-effort and
    says so in the log rather than silently."""
    live = _live_apply()
    stamp = live.index('"arc_template_id": arc_template.id')
    before = live.rindex("try:", 0, stamp)
    after = live.index("except Exception:", stamp)
    assert before < stamp < after, "the provenance stamp must be inside the try/except"
    assert "could not stamp template provenance" in live, (
        "a swallowed failure with no log is a mechanism nobody can tell has stopped working"
    )


def test_the_stamp_runs_after_the_commit_that_mints_the_arc():
    """It needs created["arc_id"], so ordering is not cosmetic."""
    live = _live_apply()
    assert live.index('arc_id_str = str(created["arc_id"])') < live.index('"arc_template_id": arc_template.id')
