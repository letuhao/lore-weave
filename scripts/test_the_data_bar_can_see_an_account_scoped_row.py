"""D-DATA-BAR-BLIND-TO-ACCOUNT-SCOPED-ARC-TEMPLATE.

`store_snapshot` sweeps BY book_id. `arc_template` has a NULLABLE book_id, and 25 of its 57 rows
carry NULL — so for the whole arc-template family "store unchanged" was never a statement about
the tool at all. Demonstrated live: the idempotency probe archived a real template (active ->
archived, verified by direct SQL either side) and `store_diff` was `{}` on BOTH calls, so the
probe reported "STRICTLY IDEMPOTENT" and then flagged its own verdict as vacuous.

The row called it the EIGHTH instance of the non-book-scoped blind spot, after `_world_counts`
(the world/map family) and `_motif_link_counts`. So the fix is the shape those two already
argue for rather than another special case: count through the RUN'S OWN NONCE.

    an owner-wide sweep folds in the account's 57 unrelated rows and destroys the
    attribution per-scenario fixtures exist to provide            — _world_counts, verbatim

The row also listed a BLOCKER — the scenario used a fixed code, so there was no per-run row to
scope to. Re-derived 2026-08-26: scenarios-c-arcapply.json already seeds `loop-arc-{run_id}`
with `{run_word}` in the name, and the store holds ZERO `loop-arc-%` rows, so the per-run
teardown works. The blocker was resolved and the row never updated; only the count was missing.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import store_snapshot as ss  # noqa: E402

pytestmark = pytest.mark.skipif(
    subprocess.run(["docker", "ps"], capture_output=True).returncode != 0,
    reason="needs the local stack",
)

RUN = "zzguard99"
DB = "loreweave_composition"


def _sql(q: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave", "-d", DB, "-At", "-c", q],
        capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def seeded_template():
    owner = _sql("SELECT owner_user_id FROM arc_template WHERE book_id IS NULL LIMIT 1;")
    if not owner:
        pytest.skip("no account-scoped arc_template to model the case on")
    _sql(f"DELETE FROM arc_template WHERE code = 'loop-arc-{RUN}';")
    yield owner
    _sql(f"DELETE FROM arc_template WHERE code = 'loop-arc-{RUN}';")


def test_the_table_really_is_invisible_to_a_book_scoped_sweep(seeded_template):
    """ANTI-VACUITY, and the defect itself. If the old sweep DID see these rows, the whole fix
    is pointless — so prove it does not."""
    owner = seeded_template
    book_id = _sql("SELECT book_id FROM arc_template WHERE book_id IS NOT NULL LIMIT 1;")
    if not book_id:
        pytest.skip("no book-scoped arc_template to sweep against")
    before = ss.snapshot(book_id)
    _sql(f"INSERT INTO arc_template (owner_user_id, code, name, status) "
         f"VALUES ('{owner}', 'loop-arc-{RUN}', 'zz guard', 'active');")
    after = ss.snapshot(book_id)
    assert ss.diff(before, after) == {}, (
        "the book-scoped sweep now sees an account-scoped template — this test's premise is gone"
    )


def test_the_run_scoped_count_sees_it(seeded_template):
    owner = seeded_template
    before = ss._run_scoped_counts(RUN)
    _sql(f"INSERT INTO arc_template (owner_user_id, code, name, status) "
         f"VALUES ('{owner}', 'loop-arc-{RUN}', 'zz guard', 'active');")
    after = ss._run_scoped_counts(RUN)
    assert before == {}
    assert after.get(f"{DB}.arc_template.run", {}).get("rows") == 1, after
    assert ss.diff(before, after), "the DATA bar still cannot see the write"


def test_it_does_NOT_fold_in_the_accounts_other_rows(seeded_template):
    """The reason it is scoped to the run and not the owner. 57 rows exist; a run that seeded
    nothing must count ZERO, or every scenario inherits the account's history."""
    assert ss._run_scoped_counts("nosuchrunnonce") == {}
    total = int(_sql("SELECT count(*) FROM arc_template;") or 0)
    assert total > 1, "premise gone: the account has no unrelated templates to fold in"


def test_a_run_without_a_nonce_is_unchanged():
    """PRECISION. snapshot() must behave exactly as before when no run_id is passed — every
    existing scenario calls it that way through the older evidence on disk."""
    book_id = _sql("SELECT book_id FROM arc_template WHERE book_id IS NOT NULL LIMIT 1;")
    if not book_id:
        pytest.skip("no book to sweep")
    assert ss.snapshot(book_id) == ss.snapshot(book_id, run_id=None)


def test_the_runner_passes_the_nonce():
    """A counter nothing calls is the defect this file is about, arriving by another route."""
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    assert src.count("fx.run_id") >= 2, (
        "fe_runner does not pass the run nonce to BOTH snapshots (before and after)"
    )


def test_snapshot_ITSELF_includes_the_run_scoped_count(seeded_template):
    """🔴 THE GUARD ABOVE WAS VACUOUS WITHOUT THIS. Every other case here calls
    `_run_scoped_counts` DIRECTLY, so disabling the one line that wires it into `snapshot()`
    (`if run_id:` -> `if False and run_id:`) left all five green — the counter worked perfectly
    and nothing used it, which is precisely the defect this file is about arriving by another
    route. Go through the front door."""
    owner = seeded_template
    book_id = _sql("SELECT book_id FROM arc_template WHERE book_id IS NOT NULL LIMIT 1;")
    if not book_id:
        pytest.skip("no book to sweep")
    before = ss.snapshot(book_id, run_id=RUN)
    _sql(f"INSERT INTO arc_template (owner_user_id, code, name, status) "
         f"VALUES ('{owner}', 'loop-arc-{RUN}', 'zz guard', 'active');")
    after = ss.snapshot(book_id, run_id=RUN)
    d = ss.diff(before, after)
    assert f"{DB}.arc_template.run" in d, (
        f"snapshot() does not carry the run-scoped count — the counter is not wired in: {d}"
    )
