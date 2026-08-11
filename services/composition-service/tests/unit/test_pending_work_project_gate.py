"""TOOLV2 LOOP #142 — a Work awaiting its knowledge-project backfill produced a false error.

Measured live on `composition_arc_apply`, the tool's first ever invocation, against a book with
chapters and with every motif the arc template's placements reference:

    {"message": "bad reference", "code": "BAD_REFERENCE",
     "detail": "project None has no composition_work row"}

Two things are wrong with that sentence and neither is cosmetic. The composition_work row *does*
exist — it is the PROJECT that is absent — so the caller is told to look for the one thing that is
already there. And `None` is a Python literal leaking into a caller-facing string, which names no
argument, no state and no way out.

The cause is structural. `_book_or_deny` is the documented canonicalization point (D-COMPOSITION-ID-
TRAP): a book has three uuids, callers may hand in any of them, and every caller that needs the
project must re-bind `pid` from `meta.project_id`. Ten sites do exactly that. None of them
considered that `meta.project_id` is NULL for a Work created while knowledge-service was
unreachable (C16/WG-3 `pending_project_backfill`), so the NULL was re-bound and carried into the
engines as a dangling reference.

Population, measured rather than assumed: 82 of 516 Works (15.9%) carry a NULL project_id, and all
82 are flagged pending. The discriminator was confirmed by A/B — the same tool and template against
a BACKED Work answers with a clean, actionable `NO_CHAPTERS`.
"""

import re
from pathlib import Path

import pytest

from app.mcp.server import _require_project


class _Meta:
    def __init__(self, project_id):
        self.project_id = project_id
        self.book_id = "book"


def test_a_bound_project_is_returned_unchanged():
    """The control. Without this, a helper that always raised would pass every other case."""
    assert _require_project(_Meta("019fccd7-2a31-731a-ba56-a6f58cdb02b9")) == (
        "019fccd7-2a31-731a-ba56-a6f58cdb02b9"
    )


def test_a_pending_work_is_refused_before_the_null_reaches_an_engine():
    with pytest.raises(ValueError) as exc:
        _require_project(_Meta(None))
    msg = str(exc.value)
    # It must name the STATE — the thing that is actually absent.
    assert "knowledge project" in msg
    # ...and the satisfier, because the whole failure of the original was having none.
    assert "composition_create_work" in msg
    # ...and it must not resurrect either half of the false claim.
    assert "None" not in msg
    assert "has no composition_work row" not in msg


def test_every_project_rebinding_site_goes_through_the_gate():
    """The helper is worth nothing if a call site skips it.

    A guard that only exercises the helper stays green when a site is reverted to the bare
    attribute read — that has happened repeatedly in this loop, so the wiring gets its own
    anchor. Ten sites re-bind `pid`; the only permitted bare read is the one inside the helper.
    """
    src = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")

    gated = len(re.findall(r"^    pid = _require_project\(meta\)$", body, re.M))
    assert gated == 10, f"expected 10 gated re-binding sites, found {gated}"

    # The helper itself reads the attribute; every other bare read is a bypass.
    bare = len(re.findall(r"^    pid = meta\.project_id$", body, re.M))
    assert bare == 1, (
        f"{bare} bare `pid = meta.project_id` reads — every consuming site must go through "
        "_require_project, or a pending Work's NULL reaches an engine again"
    )


def test_create_work_adopts_a_pending_row_before_creating_a_second():
    """TOOLV2 LOOP #142 — the REMEDY was itself dead for the state it remedies.

    `composition_create_work` is what the gate above tells the caller to run. Measured live, it
    answered "not found or not accessible" for the throwaway book — permanently, on every retry —
    while healing other pending books fine.

    The discriminator was whether the book's knowledge project ALREADY existed. The pending-row
    backfill lives on `_resolve_or_create_default_project`'s project-CREATE branch, so a book that
    resolved to an EXISTING project skipped it; then `works.get(pid)` could not see the pending row
    (it keys on project_id, which is NULL), `works.create` collided with the one-Work-per-book
    constraint, and the re-get by project_id missed for the same reason — landing on the
    `raise uniform_not_accessible` that the comment there calls defensive. 5 of 80 pending Works
    were in that state; for those five the authoring workspace could never be opened at all.

    LIMITATION, stated rather than implied: this reads the source. The branch needs a live pool,
    two services and a book whose project exists while its Work does not, and this package has no
    such harness — the live proof is in the ledger instead (the pending row was adopted, keeping
    its id, and composition_arc_apply then succeeded through it). The anchors are ordered
    statements rather than loose substrings, so a revert reds them.
    """
    src = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")

    adopt = body.find("pending = await works.get_pending_for_book(bid)")
    assert adopt != -1, "create_work no longer looks for this book's pending Work"

    backfill = body.find("adopted = await works.backfill_project(pending.id, pid", adopt)
    assert backfill != -1, "the pending Work is found but never bound to the resolved project"

    # Order is the whole fix: adopting AFTER the create is the collision it exists to avoid.
    create = body.find("work = await works.create(tc.user_id, pid, bid)", adopt)
    assert create != -1, "the create tail vanished — re-check this guard against the new shape"
    assert adopt < backfill < create, (
        "the pending Work must be adopted BEFORE works.create, or the one-Work-per-book "
        "constraint fires and the caller is denied again"
    )
