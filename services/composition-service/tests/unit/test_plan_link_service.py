"""27 V2-E — the LINK step. The SQL contract + the report semantics.

The live upserts run against a DB in the integration suite. What is pinned HERE is the set of
things that break SILENTLY:

  • the `ON CONFLICT` predicate must repeat the partial index's WHERE clause VERBATIM — Postgres
    will not infer a partial unique index for arbitration otherwise, and the statement fails at
    runtime with "no unique or exclusion constraint matching the ON CONFLICT specification". In a
    linker that means every re-link INSERTS A DUPLICATE instead of updating;
  • the writer must stamp `source='planforge'` — a value reserved in the CHECK and written by
    nobody is the write-only bug class, and the decompiler's preservation predicate depends on it;
  • zero nodes linked must be an ERROR, never a silent 200 (E4) — that is the entire reason this
    step exists.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.services import plan_link_service as pls
from app.services.plan_link_service import LinkError, LinkReport, PlanLinkService, TargetCounts

SRC = Path(inspect.getfile(PlanLinkService)).read_text(encoding="utf-8")

# The partial-index predicates, exactly as migrate.py declares them (27 V2-A2).
ARC_PRED = "plan_run_id IS NOT NULL AND plan_arc_id IS NOT NULL AND NOT is_archived"
NODE_PRED = "plan_run_id IS NOT NULL AND plan_event_id IS NOT NULL AND NOT is_archived"


def _stmt(name: str) -> str:
    return getattr(pls, name)


# ── PF-10: the ON CONFLICT predicate MUST match the partial index ─────────────


@pytest.mark.parametrize(
    "stmt,pred,target",
    [
        ("_UPSERT_ARC", ARC_PRED, "(book_id, plan_run_id, plan_arc_id)"),
        ("_UPSERT_CHAPTER", NODE_PRED, "(book_id, plan_run_id, plan_event_id)"),
        ("_UPSERT_SCENE", NODE_PRED, "(book_id, plan_run_id, plan_event_id)"),
    ],
)
def test_on_conflict_repeats_the_partial_index_predicate(stmt, pred, target):
    sql = " ".join(_stmt(stmt).split())
    assert f"ON CONFLICT {target}" in sql
    assert f"WHERE {pred}" in sql, (
        "the ON CONFLICT inference predicate must repeat the partial index's WHERE clause verbatim "
        "or Postgres refuses to use it for arbitration — and every re-link inserts a duplicate"
    )


def test_the_idempotency_key_is_RUN_SCOPED_not_bare_event_id():
    """PF-10 refines BPS-18. Event ids are 100% stable WITHIN a run and 0% stable ACROSS re-proposes
    (POC 03: title overlap 100%, id overlap 0%). A bare `event_id` key would therefore collide two
    unrelated runs' nodes onto each other."""
    for stmt in ("_UPSERT_CHAPTER", "_UPSERT_SCENE"):
        sql = " ".join(_stmt(stmt).split())
        assert "ON CONFLICT (book_id, plan_run_id, plan_event_id)" in sql


# ── E2b: the writer STAMPS source='planforge' ────────────────────────────────


@pytest.mark.parametrize("stmt", ["_UPSERT_ARC", "_UPSERT_CHAPTER", "_UPSERT_SCENE"])
def test_every_linked_node_is_stamped_planforge(stmt):
    """The value is reserved in `outline_node_source_check` / `structure_node_source_check` and was
    written by NOBODY — a reserved-but-never-written enum value is the write-only bug class. It is
    also load-bearing: 26 IX-11's preservation predicate protects `source='authored'` rows, and it
    can only tell PlanForge's mints from a human's if the stamp lands."""
    assert "'planforge'" in _stmt(stmt)


# ── PF-11: a re-link never silently reclaims an author's edit ────────────────


@pytest.mark.parametrize("stmt", ["_UPSERT_CHAPTER", "_UPSERT_SCENE"])
def test_the_update_is_GUARDED_by_the_version_we_last_wrote(stmt):
    """`DO UPDATE ... WHERE outline_node.version <= $n`. If a human has edited the row since we
    linked it, its version has moved past our guard, the update is skipped, and their words stand.
    Without this the generator silently wins over the human — the write-only bug, inverted."""
    sql = " ".join(_stmt(stmt).split())
    assert re.search(r"WHERE outline_node\.version <= \$\d+", sql), sql


def test_the_report_records_the_version_of_every_node_it_wrote():
    # PF-11's comparison has nothing to compare against otherwise.
    r = LinkReport(run_id="r", target="skeleton")
    assert r.linked_versions == {}
    assert "linked_versions" in r.to_dict()


def test_the_arc_upsert_is_NOT_version_guarded():
    """An arc carries no authored prose — only a title and a summary the plan owns. Guarding it
    would freeze the arc after any incidental version bump, for no protection gained."""
    assert "structure_node.version <=" not in _stmt("_UPSERT_ARC")


# ── E4: zero linked is an ERROR, never a silent success ──────────────────────


class _Pool:
    """A pool whose transaction body never runs — enough to reach the pre-flight guards."""

    def acquire(self):
        raise AssertionError("must not reach the DB: the guard should have fired first")


@pytest.mark.asyncio
async def test_a_package_with_no_chapters_FAILS_it_does_not_return_ok():
    svc = PlanLinkService(_Pool())
    with pytest.raises(LinkError) as ei:
        await svc.link_outline_skeleton(
            created_by="00000000-0000-4000-8000-000000000001",
            book_id="00000000-0000-4000-8000-000000000002",
            project_id="00000000-0000-4000-8000-000000000003",
            run_id="00000000-0000-4000-8000-000000000004",
            package={"arc_id": "arc_1", "chapters": []},
        )
    assert ei.value.report.success is False
    # …and the report is carried on the exception, so the caller can PERSIST it: a failure the user
    # cannot inspect is barely better than a silent success.
    assert "nothing to link" in (ei.value.report.detail or "")


@pytest.mark.asyncio
async def test_a_package_with_no_arc_id_FAILS():
    svc = PlanLinkService(_Pool())
    with pytest.raises(LinkError):
        await svc.link_outline_skeleton(
            created_by="00000000-0000-4000-8000-000000000001",
            book_id="00000000-0000-4000-8000-000000000002",
            project_id="00000000-0000-4000-8000-000000000003",
            run_id="00000000-0000-4000-8000-000000000004",
            package={"chapters": [{"title": "c", "ordinal": 1}]},
        )


@pytest.mark.asyncio
async def test_an_empty_scene_plan_FAILS():
    svc = PlanLinkService(_Pool())
    with pytest.raises(LinkError):
        await svc.link_scene_plan(
            created_by="00000000-0000-4000-8000-000000000001",
            book_id="00000000-0000-4000-8000-000000000002",
            project_id="00000000-0000-4000-8000-000000000003",
            run_id="00000000-0000-4000-8000-000000000004",
            scenes_by_event={},
        )


# ── the report always carries per-target counts (E4) ────────────────────────


def test_counts_are_per_target_never_a_bare_total():
    """A linker that reports only a total cannot tell you it created nothing and updated nothing."""
    d = LinkReport(run_id="r", target="skeleton").to_dict()
    for target in ("arcs", "chapters", "scenes"):
        assert set(d[target]) == {
            "created", "updated", "unchanged", "skipped", "preserved_user_edit",
        }


def test_touched_counts_preserved_edits_as_LINKED():
    """A row we preserved is still linked — it just kept its author's words. Excluding it from
    `touched` would make a fully-preserved re-link look like a zero-node failure and raise."""
    c = TargetCounts(preserved_user_edit=3)
    assert c.touched == 3


# ── PF-10: duplicates are SURFACED, never merged ─────────────────────────────


def test_the_duplicate_probe_spans_OTHER_RUNS_and_the_DECOMPILER():
    """E2b widens PF-10 to cross-AXIS duplicates: an imported-then-replanned book legitimately has
    both a decompiled node and a planforge one with the same title. Surfaced as a question — never
    auto-merged, because a title match is a heuristic and a silent merge is unrecoverable."""
    sql = " ".join(pls._FIND_DUPES.split())
    assert "plan_run_id IS DISTINCT FROM" in sql   # a different run
    assert "source = 'decompiled'" in sql          # …or the decompiler's mint
    assert "lower(btrim(title))" in sql            # title-match heuristic, case/space-insensitive


def test_there_is_no_merge_path_at_all():
    # The safest way to guarantee "never auto-merged" is to have no code that could.
    assert "merge" not in SRC.lower().replace("auto-merged", "").replace("never merge", "")


# ── the reading axis is the ONE strided global axis ─────────────────────────


def test_scenes_slot_onto_their_chapters_strided_story_order():
    """chapter n sits at n*1000; its i-th scene at +i+1. One reading axis, one convention — the Hub,
    the packer, and the canon-rule windows all read the same one."""
    assert "ordinal * 1000" in SRC
    assert '(chap["story_order"] or 0) + i + 1' in SRC


# ── the regression the linker EXPOSED ────────────────────────────────────────


def test_arc_1_events_are_parsed_the_bug_the_linker_found():
    """Found 2026-07-12 by 27 V2-E's zero-node error, on the first real compile.

    `_parse_arcs_and_events` appended Arc 1 but never called `_parse_events_in_block` for it — the
    Arc 2 branch did. So EVERY rules-mode plan whose arc_overview held only "Arc 1" compiled to a
    package with zero chapters, 100% of the time.

    It was invisible because nothing CONSUMED the package: the compiler compiled into the void, and
    `chapters: []` looked like a quiet success. This is BPS-18/DA-13's law paying for itself — "an
    emitted artifact with no linker is a bug" — and E4's "zero nodes linked ⇒ success:false" is what
    turned a silent 100% failure into a loud one.
    """
    from app.engine.plan_forge.compile import compile_artifacts
    from app.engine.plan_forge.ingest import ingest_markdown
    from app.engine.plan_forge.propose import propose_spec

    md = (
        "# 1. Arc Overview\n\nOne arc.\n\n## Arc 1\n\n"
        "### Event 1: The Summons\n**Goal:** g1.\n\n"
        "### Event 2: Through the Gate\n**Goal:** g2.\n"
    )
    spec = propose_spec(ingest_markdown(md))
    assert [e["id"] for e in spec["events"]] == ["arc_1_event_1", "arc_1_event_2"]

    package = compile_artifacts(spec, arc_id="arc_1")["planning_package"]
    # …and therefore the package has chapters for the linker to materialise.
    assert [c["event_id"] for c in package["chapters"]] == ["arc_1_event_1", "arc_1_event_2"]


def test_the_linked_arcs_status_is_in_the_DB_CHECKs_set():
    """`structure_node_status_check` allows empty|outline|drafting|done — NOT 'active' (that is the
    WORK's status vocabulary, a different table's). A freshly linked arc is planned-but-unwritten,
    which is `outline`.

    Caught by the LIVE smoke: no unit test that never touches the DB could see it, and the SQL is a
    string until Postgres parses it."""
    sql = _stmt("_UPSERT_ARC")
    # Check the VALUES clause, not the whole string — the comment above it legitimately contains
    # the word 'active' while explaining why it must NOT be used.
    values = [ln for ln in sql.splitlines() if ln.strip().startswith("VALUES")][0]
    assert "'outline'" in values
    assert "'active'" not in values
