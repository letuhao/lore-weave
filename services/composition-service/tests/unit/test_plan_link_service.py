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


def test_the_arc_IS_version_guarded_too():
    """An earlier version of this test asserted the OPPOSITE, on the reasoning that "an arc carries
    no authored prose — only a title and a summary the plan owns". That premise is FALSE:
    `PATCH /arcs/{id}` patches title/summary through StructureRepo with If-Match OCC — arcs are a
    first-class authored surface.

    Unguarded, every compile silently reverted a user's arc rename. And the unconditional
    `version + 1` staled their held ETag, so their NEXT arc edit 412'd, and it invalidated the
    arc-conformance manifest's structure_node_version on every compile whether the arc changed or
    not. A test that pins the wrong behaviour as intentional is worse than no test."""
    sql = " ".join(_stmt("_UPSERT_ARC").split())
    assert re.search(r"WHERE structure_node\.version <= \$\d+", sql), sql
    # …and it only bumps the version when something ACTUALLY changed.
    assert "IS DISTINCT FROM EXCLUDED.title" in sql


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
    """The chapter sits at n * STORY_ORDER_CHAPTER_STRIDE; its i-th scene at `+ i`, ZERO-BASED.

    Every other writer uses that convention (`_renumber_scene_story_order`'s `row_number() - 1`,
    `resync_reading_order`, plan.py's `enumerate`) — the chapter sits exactly at its own scene 0. An
    earlier version used `+ i + 1`, which put linker-minted scenes one slot above everyone else's:
    the first scene drag or book reorder would renumber them all down by one, shifting the packer's
    strictly-prior cutoffs and the canon-rule windows that key on those exact integers. Two
    conventions on one column is a bug this repo has already shipped once.

    The stride is IMPORTED, not a literal: a hardcoded 1000 that later disagreed with the canonical
    constant would desynchronise the whole axis while this test stayed green."""
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE

    assert "from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE" in SRC
    assert "ordinal * STORY_ORDER_CHAPTER_STRIDE" in SRC
    assert '(chap["story_order"] or 0) + i,' in SRC
    assert STORY_ORDER_CHAPTER_STRIDE == 1000  # the value today; the import is what keeps it honest


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


# ── HIGH-1: PF-11 must survive MORE THAN ONE re-compile ──────────────────────


def test_the_preserved_path_CARRIES_THE_PRIOR_GUARD_not_the_current_version():
    """The ledger means "the version this row had immediately after OUR last write".

    A preserve is not a write, so that value does not change. My first fix recorded the row's CURRENT
    version instead, and the LIVE SMOKE caught what this unit test could not: on the next compile the
    guard equalled the human's version, `version <= guard` was TRUE, the update fired, and the human
    survived exactly ONE more compile. A two-compile smoke shows a green `preserved_user_edit: 1`; it
    takes three to see the overwrite.
    """
    src = SRC
    for marker, key, guard in (
        ("report.chapters.preserved_user_edit += 1", "key", "guard"),
        ("report.scenes.preserved_user_edit += 1", "skey", "guard"),
        ("report.arcs.preserved_user_edit += 1", "arc_key", "arc_guard"),
    ):
        # scope to the PRESERVE branch — the `else` after it is the no-op branch, where recording
        # the row's current version is not just allowed but correct.
        after = src[src.index(marker) :]
        branch = after[: after.index("else:")]  # the first `else:` IS this branch's no-op arm
        assert f"report.linked_versions[{key}] = {guard}" in branch, marker
        assert f"report.linked_versions[{key}] = existing" not in branch, (
            f"{marker}: adopting the human's CURRENT version as ours overwrites them next compile"
        )


def test_a_skipped_update_is_disambiguated_by_VERSION_not_by_content():
    """`row is None` means the DO UPDATE's WHERE was false, which is TWO different situations:
    a human is ahead of us (preserve), or nothing differed (no-op). They need OPPOSITE ledger writes,
    so telling them apart has to be exact.

    The version alone decides it: the WHERE is `version <= guard AND <something differs>`, so a
    skipped update with the version PAST the guard can only have been blocked by the version clause.
    An earlier arc-only version compared CONTENT, which is a proxy: a human who edited and reverted
    was mislabelled "unchanged" and handed their row back."""
    assert "def _settled(current_version: int, guard: int) -> bool:" in SRC
    assert "return current_version > guard" in SRC
    # …and all three branches use it, rather than re-deriving the answer three ways.
    assert SRC.count("if _settled(existing[\"version\"], ") == 3
    # the arc's old content-compare is gone
    assert 'existing["title"] != title or existing["summary"] != summary' not in SRC


def test_a_NOOP_compile_does_not_bump_any_version():
    """Every DO UPDATE must also require that something ACTUALLY differs.

    Without it, a compile that changed nothing still bumped `version` on every chapter and every
    scene — which (a) staled every ETag the user was holding, so their next edit 412'd, and (b) made
    `unchanged` structurally unreachable in the report: a counter that can never be non-zero is a
    lying metric. The arc had the clause; the chapters and scenes did not, and the 5-compile live
    smoke showed it plainly — `updated: 1, unchanged: 0` on every no-op compile, Event 1 climbing to
    v4 while nothing about it changed.

    The DISTINCT list must cover EVERY column the DO UPDATE SETs, or a real change to an uncovered
    column is silently skipped as a no-op — the same bug wearing the other mask."""
    import re as _re

    for name, table in (
        ("_UPSERT_ARC", "structure_node"),
        ("_UPSERT_CHAPTER", "outline_node"),
        ("_UPSERT_SCENE", "outline_node"),
    ):
        sql = _stmt(name)
        set_block = sql[sql.index("DO UPDATE SET") : sql.index("WHERE %s.version" % table)]
        # the columns the update writes, minus the two bookkeeping ones we always touch
        set_cols = {
            m.group(1)
            for m in _re.finditer(r"^\s*(\w+)\s*=", set_block, _re.M)
        } - {"updated_at", "version"}
        where_block = sql[sql.index("WHERE %s.version" % table) :]
        distinct_cols = set(_re.findall(r"(?:%s\.)?(\w+)\s+IS DISTINCT FROM" % table, where_block))
        assert set_cols, name
        assert set_cols == distinct_cols, (
            f"{name}: the no-op guard must cover every column the update writes. "
            f"written={sorted(set_cols)} guarded={sorted(distinct_cols)}"
        )


def test_the_prior_report_is_selected_BY_TARGET():
    """Both linkers emit kind `link_report`. A bare latest-by-kind read would hand the SKELETON link
    the SCENE link's report — whose ledger holds only `scene:*` keys — so the skeleton would find no
    prior arc/chapter version, use the open sentinel, and clobber every human edit. Same root cause:
    "missing bookkeeping ⇒ overwrite" is only safe if the bookkeeping cannot go missing."""
    from pathlib import Path as _P

    from app.services.plan_forge_service import PlanForgeService

    svc = _P(inspect.getfile(PlanForgeService)).read_text(encoding="utf-8")
    assert 'latest_link_report(book_id, run_id, "skeleton")' in svc
    assert 'latest_artifact(book_id, run_id, "link_report")' not in svc
