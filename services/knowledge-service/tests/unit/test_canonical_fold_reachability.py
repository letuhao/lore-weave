"""T46g — the KG canonical-snapshot fold is BUILT BUT UNREACHABLE, pinned so it cannot
change silently.

T46's row names four capabilities to move from Go to Python: `maintain_chain` (pin-aware
supersession — landed, T46f), the content-addressed natural key (the KG has it), half-open
interval invariants (the KG has them), and **the `anchor+delta` fold with
`folds_since_reground`**. Measuring the last one before building it (rule 8) killed the batch:

    PG   canonical_fold_state + fold_handler.go (296 lines) READS AND WRITES the counters
         — working machinery, a debounced batch fold with a deterministic re-ground trigger.
    KG   entity_canonical_snapshots: schema ✓, repository ✓, unit + integration tests ✓,
         PRODUCER ✗, READER ✗, 0 rows, and the ONLY importers of the repo are tests.

Porting `folds_since_reground` into that would add re-ground counters to a fold that never
runs — bookkeeping for a consumer that does not exist, which would read as parity while
nothing happens. It is also the wrong shape: the KG's staleness model is `fact_coverage_at` +
`fold_algo_version` (a coverage-keyed lazy rebuild-on-read, self-healing per B3), whereas the
counters exist in Postgres because ITS fold is batch + debounced. The two are different
designs for the same problem, not a gap.

So the fold half of T46 is scoped to F3/§12.1 (wiring the KG fold), not to T46's bitemporal
port. This test is that decision's tripwire: the moment production code imports the repo, the
fold has a consumer, the measurement above is stale, and T46's scoping must be revisited
deliberately rather than by whoever notices first.
"""

from __future__ import annotations

import pathlib
import re

_APP = pathlib.Path(__file__).resolve().parents[2] / "app"
_MODULE = "entity_canonical_snapshots"
#: the module's own file — it obviously "references" itself
_SELF = _APP / "db" / "repositories" / f"{_MODULE}.py"
#: the DDL lives here; declaring a table is not consuming it
_DDL = _APP / "db" / "migrate.py"

_IMPORT = re.compile(
    r"^\s*(?:from\s+[\w.]*" + _MODULE + r"\s+import|import\s+[\w.]*" + _MODULE + r")",
    re.MULTILINE,
)


def _production_importers() -> list[str]:
    hits = []
    for path in _APP.rglob("*.py"):
        if path == _SELF or path == _DDL:
            continue
        if _IMPORT.search(path.read_text(encoding="utf-8", errors="replace")):
            hits.append(str(path.relative_to(_APP)))
    return sorted(hits)


def test_the_canonical_fold_repo_still_has_NO_production_importer():
    """The measurement T46g's scoping decision rests on.

    If this goes red, that is GOOD NEWS — someone wired the fold — but it invalidates the
    reason `folds_since_reground` was left in Postgres. Revisit T46's scope in
    docs/specs/2026-08-13-knowledge-refactor-open-decisions.md §6.3 before deleting this.
    """
    importers = _production_importers()
    assert importers == [], (
        f"the canonical-snapshot fold now has production importer(s): {importers}. "
        "T46g scoped the `anchor+delta` fold / `folds_since_reground` port OUT because the "
        "KG destination was unreachable — that reason no longer holds. Revisit §6.3 and "
        "decide the port deliberately."
    )


def test_the_repo_it_is_pinning_actually_EXISTS():
    """The control. `_production_importers()` returns [] just as happily when the module was
    renamed or deleted, and an assertion that passes because its subject vanished is the
    green-by-construction shape this plan keeps finding. Pin the subject too.
    """
    assert _SELF.is_file(), f"{_SELF} is gone — this tripwire is now guarding nothing"
    src = _SELF.read_text(encoding="utf-8", errors="replace")
    assert "class EntityCanonicalSnapshotsRepo" in src
    assert "def snapshot_content_hash" in src


def test_the_import_matcher_can_actually_MATCH():
    """The second control: a regex that never matches would make the first test vacuous
    forever. Prove it fires on a real import line — the tests import this module, so the
    pattern is exercised against the exact shape it must catch.
    """
    assert _IMPORT.search(
        "from app.db.repositories.entity_canonical_snapshots import EntityCanonicalSnapshotsRepo"
    )
    assert _IMPORT.search("import app.db.repositories.entity_canonical_snapshots")
    assert not _IMPORT.search("# entity_canonical_snapshots is mentioned in a comment")
