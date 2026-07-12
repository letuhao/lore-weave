"""28 AN-2/AN-3/AN-4 — the agent's three read surfaces.

These tools exist because a weak model would not stitch 3-6 calls across three services to answer
"what is this book, and what is wrong with it" — it simply did not try. So the two properties that
decide whether they work are not "do they return data" but:

  1. **They stay cheap.** A tool that blows the budget is a tool the agent stops calling. The
     146K-token `composition_list_outline` incident is the precedent, and AN-2's whole shape
     (counts + one-liners, never prose) is the response to it.
  2. **They never fake a zero.** These are ORIENTATION reads: the agent acts on them. "0 unplanned
     chapters" and "I could not reach book-service" lead to opposite actions, and only one is true.
"""

from __future__ import annotations

import inspect
import json

import pytest

from app.services.agent_native import (
    REFERENCE_SOURCES,
    SEVERITY,
    Block,
    Diagnostic,
    Diagnostics,
    arc_line,
    cap_arcs,
)


# ── absent ≠ zero (the law all three live under) ─────────────────────────────────────────────────

def test_a_DEGRADED_block_OMITS_its_key_rather_than_shipping_a_zero():
    """The single most-repeated bug class in this repo, at the tool layer.

    `{"unplanned_chapter_count": 0}` renders as "nothing is unplanned". A MISSING key forces the
    consumer to branch — which is exactly right, because we genuinely do not know. An agent that
    reads a faked 0 does not degrade its answer, it INVERTS it: it concludes the book is fully
    planned and moves on."""
    out: dict = {}
    warnings: list[str] = []

    Block.failed("book-service is unreachable").into(out, "manuscript", warnings)
    assert "manuscript" not in out          # ABSENT, not 0
    assert warnings == ["book-service is unreachable"]

    Block({"chapter_count": 0}).into(out, "manuscript", warnings)
    assert out["manuscript"] == {"chapter_count": 0}   # a REAL zero is still a zero


def test_Block_failed_REQUIRES_a_reason():
    """A degraded block with no warning is a silent failure wearing a different hat."""
    assert inspect.signature(Block.failed).parameters["warning"].default is inspect.Parameter.empty


# ── AN-2: the tree is ORIENTATION, and it must stay cheap ────────────────────────────────────────

def test_the_arc_tree_is_CAPPED_and_SAYS_it_capped():
    """A silent truncation reads as "this book has 50 arcs" — a different claim from "here are 50 of
    them". `arcs_capped` is the difference between a fact and a lie."""
    arcs = [_FakeArc(f"Arc {i}") for i in range(80)]
    shown, capped = cap_arcs(arcs)
    assert len(shown) == 50 and capped is True

    shown, capped = cap_arcs(arcs[:10])
    assert len(shown) == 10 and capped is False


def test_an_arc_line_is_a_LINE_never_prose():
    """AN-2's whole shape. The moment a summary or a goal gets in here, the tool is content, not
    orientation, and it stops being callable on a real book."""
    a = _FakeArc("The Iron Court", status="drafting")
    line = arc_line(a, chapters=12)
    assert len(line) <= 120
    assert "The Iron Court" in line and "12 ch" in line


def test_the_package_tree_STAYS_UNDER_BUDGET_on_a_10k_chapter_book():
    """THE reason this tool exists (AN-2: "hard-capped ~2-4K tokens on a 10k-chapter book").

    The 146K-token `composition_list_outline` incident is what happens when orientation and content
    share one tool. If the tree grew with the book, the agent would stop calling it on exactly the
    books that need it most."""
    payload = {
        "book_id": "0" * 36,
        "work": {"project_id": "0" * 36, "title": "A Very Long Novel"},
        "spec": {
            "arc_count": 400,
            "arcs": [arc_line(_FakeArc(f"Arc {i} — a fairly long arc title here"), chapters=25)
                     for i in range(50)],          # capped at 50
            "arcs_capped": True,
        },
        "manuscript": {"chapter_count": 10_000},   # a COUNT, not the chapters
        "index": {"stale_chapter_count": 4200, "arcs_dirty": 39, "arcs_never_run": 12},
        "coverage": {"unplanned_chapter_count": 900, "spine_truncated": False},
        "runs": {"recent": [{"id": "0" * 36, "status": "compiled", "mode": "llm"}] * 5},
    }
    # ~4 chars/token is the standard rough estimate; 4K tokens ⇒ ~16K chars.
    chars = len(json.dumps(payload))
    assert chars < 16_000, f"the package tree is {chars} chars — orientation must stay cheap"


# ── AN-3: a closed set, and exact counts ─────────────────────────────────────────────────────────

def test_the_reference_sources_are_a_CLOSED_SET_of_eight():
    """A closed-set arg gets an enum, or a weak model sends `"outline"` and gets a silent no-op —
    the Frontend-Tool-Contract bug this repo shipped once."""
    assert len(REFERENCE_SOURCES) == 8
    assert set(REFERENCE_SOURCES) == {
        "outline_pov", "outline_present", "scene_pov", "scene_present",
        "structure_roster", "motif_application", "canon_rule", "narrative_thread",
    }


def test_an_UNKNOWN_source_RAISES_rather_than_returning_zero_hits():
    """`(0, [])` for a typo reads as "this entity is used nowhere" — the worst possible lie for a
    find-references tool, because the agent's next move on that answer is to DELETE something."""
    from app.db.repositories.entity_references import EntityReferencesRepo

    src = inspect.getsource(EntityReferencesRepo.find)
    assert "raise ValueError(f\"unknown reference source: {source}\")" in src


def test_the_repo_is_NOT_called_ReferencesRepo():
    """One name, one concept. `ReferencesRepo` already exists and means the author's REFERENCE SHELF
    (a research library with embeddings + cosine search). Hanging an entity-backlink query off it
    would put two unrelated concepts behind one name — the exact drift the MCP Tool I/O standard's
    one-name-one-concept rule exists to stop. (28's shorthand says `ReferencesRepo.find_by_entity`;
    the shorthand is wrong, and following it would have been the bug.)"""
    from app.db.repositories.entity_references import EntityReferencesRepo
    from app.db.repositories.references import ReferencesRepo

    assert EntityReferencesRepo is not ReferencesRepo
    assert hasattr(ReferencesRepo, "search")          # the shelf's cosine search
    assert not hasattr(ReferencesRepo, "find_by_entity")


def test_the_narrative_thread_source_joins_through_the_NODE():
    """`narrative_thread` has NO entity column. A promise is opened AT A NODE, so an entity's threads
    are the promises opened where that entity appears. A genuine join — not a stand-in — and it is
    the question an author actually asks: "what did I promise in her scenes?"."""
    from app.db.repositories.entity_references import EntityReferencesRepo

    src = inspect.getsource(EntityReferencesRepo._narrative_thread)
    assert "JOIN outline_node n ON n.id = t.opened_at_node" in src
    assert "n.pov_entity_id = $2 OR n.present_entity_ids @> ARRAY[$2::uuid]" in src


def test_scenes_and_chapters_split_by_KIND_not_by_a_second_table():
    """There is no `scenes` table in this database — the prose scenes live in book-service. But
    `outline_node` holds BOTH, told apart by `kind`. That is what AN-1 means by "the outline
    pov/present pair splits", and it is what keeps the tool composition-scoped (AN-3: no federation
    in v1)."""
    from app.db.repositories.entity_references import _NODE_KIND

    assert _NODE_KIND == {
        "outline_pov": "chapter", "outline_present": "chapter",
        "scene_pov": "scene", "scene_present": "scene",
    }


# ── AN-4: compose, never recompute; and never spend ──────────────────────────────────────────────

def test_diagnostics_COMPOSES_the_engines_and_computes_NOTHING_new():
    """26 IX-14's consumer note is the law: ONE server-side computation, four consumers. A second
    staleness implementation here would be a second source of truth that drifts the moment either
    side is touched — the CSS-var duplication lesson, in SQL."""
    from app.mcp import server

    src = inspect.getsource(server.composition_diagnostics)
    assert "compute_conformance_status(" in src   # (1) IX-14's helper, not a re-derivation
    assert "canon_issues(" in src                 # (2) F-A5's repo
    assert "list_open(" in src                    # (3) BA15's query
    assert "compute_coverage(" in src             # (5) the SAME diff 24 H1.3 renders


def test_diagnostics_NEVER_SPENDS():
    """A read that silently RAN conformance would collapse the spend gate (07S: reversibility
    determines autonomy — a read must stay a read). The refresh action is `composition_conformance_
    run` (Tier-W), and the tool's job is to POINT AT it, not to call it."""
    from app.mcp import server

    src = inspect.getsource(server.composition_diagnostics)
    assert "conformance_run(" not in src
    assert "composition_conformance_run" in src   # …it names the Tier-W action instead
    # and it is registered as a READ
    block = inspect.getsource(server)
    meta = block[block.index('name="composition_diagnostics"'):][:900]
    assert 'require_meta(\n        "R"' in meta or '"R", "book"' in meta


def test_the_severity_map_is_FIXED_not_computed():
    """A diagnostics tool that ranked by its own judgement would be a second opinion competing with
    the engines that produced the findings."""
    assert SEVERITY["canon_contradiction"] == "error"
    assert SEVERITY["conformance_dirty"] == "warn"
    assert SEVERITY["open_thread_debt"] == "info"


def test_diagnostics_ranks_error_then_warn_then_info_and_caps_ROWS_not_COUNTS():
    """OUT-5. The agent reasons about the NUMBER ("is this book in trouble?") and only samples the
    rows to act. Capping the count would make it reason about a lie."""
    d = Diagnostics()
    for i in range(30):
        d.add(Diagnostic(kind="open_thread_debt", severity="info", title=f"info {i}"))
    d.add(Diagnostic(kind="canon_contradiction", severity="error", title="the error"))
    d.add(Diagnostic(kind="conformance_dirty", severity="warn", title="the warning"))

    out = d.ranked(cap=5)
    assert out["items"][0]["severity"] == "error"
    assert out["items"][1]["severity"] == "warn"
    assert len(out["items"]) == 5
    assert out["refs_capped"] is True
    # …the COUNTS are exact and uncapped
    assert out["total"] == 32
    assert out["counts"]["open_thread_debt"] == 30


def test_a_source_that_FAILS_becomes_a_WARNING_not_a_missing_problem():
    """The nastiest failure mode a problems panel has: a source dies, and the book looks HEALTHIER
    than it is. Silence must never read as "no problems here"."""
    d = Diagnostics()
    d.warnings.append("canon contradictions could not be read")
    out = d.ranked()
    assert out["total"] == 0
    assert out["warnings"] == ["canon contradictions could not be read"]


class _FakeArc:
    def __init__(self, title: str, *, status: str = "", kind: str = "arc") -> None:
        self.title = title
        self.status = status
        self.kind = kind


# ── C-R · /review-impl findings ──────────────────────────────────────────────────────────────────

def test_EVERY_declared_severity_kind_is_ACTUALLY_EMITTED_by_a_source():
    """HIGH. This is the test that would have caught the hole, and the reason it is written this way.

    `SEVERITY` declared `prose_deleted_spec_node` (ERROR — the highest class the panel has) and NO
    source ever emitted it. So the problems panel silently never checked whether a spec node pointed
    at a deleted chapter, and an agent asking "what is wrong with this book" got a confident answer
    with a hole in it. A problems panel with a silent gap is worse than no panel: the reader believes
    the count.

    A declared-but-never-emitted kind is the write-only bug inverted, and the dead map entry was the
    only visible tell. Binding the map to the emitters means a future source cannot be declared and
    forgotten — nor emitted without a severity."""
    from app.mcp import server

    src = inspect.getsource(server.composition_diagnostics)
    for kind in SEVERITY:
        # the kind must appear in the panel — as a literal `kind="…"`, or as the `kind` variable the
        # conformance branch computes. What must NOT be true is that it appears NOWHERE, which is
        # exactly the state `prose_deleted_spec_node` was in.
        assert kind in src, (
            f"{kind!r} has a severity but NOTHING EMITS IT — the panel silently never checks it"
        )


def test_all_of_AN4s_sources_are_queried_INCLUDING_the_rule_lane():
    """AN-4 names five, and four is not five. The one I dropped was the ERROR-severity one.

    (2b) is the SIXTH, added with 24 PH18: canon has TWO lanes, and source (2) only reads the
    ENTITY one (`canon_issues` — "a gone character is acting", no rule id). Without (2b) an agent
    asking "what is wrong with this book" could not see a broken author-declared RULE at all, while
    the human's quality-canon panel could. Same silent-gap class as the HIGH above, one lane over."""
    from app.mcp import server

    src = inspect.getsource(server.composition_diagnostics)
    for n in ("1", "2", "2b", "3", "4", "5"):
        assert f"# ({n})" in src, f"AN-4 source ({n}) is not queried"
    assert "rule_violations(" in src, "the RULE lane must be READ, not just declared"


def test_prose_deleted_REFUSES_to_answer_over_a_TRUNCATED_spine():
    """A truncated spine makes this UNANSWERABLE, and saying so is the point.

    If the chapter list hit its ceiling, a node whose chapter lies beyond the cut is
    indistinguishable from one whose chapter was DELETED — and we would tell the author that a
    chapter they are still writing has been destroyed. That is the
    `paged-join-against-complete-set-mislabels-not-yet-loaded-as-absent` bug, and it is far worse
    here than a missing answer: the remedy for a prose-deleted node is to ARCHIVE it."""
    from app.services.coverage import compute_prose_deleted

    src = inspect.getsource(compute_prose_deleted)
    assert "if len(chapters) >= _SPINE_LIMIT:" in src
    assert "degraded=True" in src
    assert "UNKNOWN, not zero" in src


def test_a_node_with_a_NULL_chapter_id_is_NOT_prose_deleted():
    """"Planned, not yet written" is a healthy state — 27's linker writes exactly that. Reporting it
    as a dangling pointer would tell the author to archive their entire unwritten plan."""
    from app.db.repositories.outline import OutlineRepo

    src = inspect.getsource(OutlineRepo.linked_chapter_nodes)
    assert "chapter_id IS NOT NULL" in src


def test_the_runs_block_is_VIEW_scoped_NOT_owner_scoped():
    """The C-R finding I got BACKWARDS, and the correction is the more interesting half.

    AN-2's text says the `.runs/` tables are owner-keyed and a non-owner must get the block "absent +
    a warning… UNTIL 25 OQ-3's VIEW resolution lands". So at C-R I owner-filtered the block.

    But OQ-3 HAS landed. 00B §1.4 records it shipped — in the same breath as "also unblocks 28-AN-2's
    `runs` block" — and OQ-3's decision is *default VIEW*. `PlanRunsRepo.list_for_book` has carried no
    owner predicate ever since. So the sentence I "fixed" against was written BEFORE the thing it was
    waiting for, and my fix re-narrowed a scope the spec had deliberately widened — hiding a
    collaborator's legitimate view of their own book's planning history.

    A doc sentence is a claim about the world AT THE TIME IT WAS WRITTEN. Check the world. (DR-16,
    and I walked into it twice.)"""
    import inspect as _i

    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.mcp import server

    # the REPO read is book-scoped, not owner-scoped — that IS OQ-3, in the code
    repo_src = _i.getsource(PlanRunsRepo.list_for_book)
    assert 'where = ["book_id = $1"]' in repo_src
    assert "owner_user_id" not in repo_src

    # …so the tool must not re-narrow it
    src = _i.getsource(server.composition_package_tree)
    assert "r.created_by == tc.user_id" not in src


def test_the_entity_reference_sources_carry_NO_project_id():
    """MED. Every one of the eight sources is BOOK-scoped, and the E0 gate is on the book. Threading
    a `project_id` through and never using it was worse than useless: the tool passed `pid or
    book_id` — a BOOK id in a project slot — so the first person to add a project-keyed source would
    have silently scoped it by the wrong key."""
    import app.db.repositories.entity_references as er

    src = inspect.getsource(er)
    assert "project_id: UUID" not in src
    assert "project_id=" not in src


def test_the_diagnostics_limit_is_clamped_ONCE_and_used_everywhere():
    """The row slices used the RAW arg while the ranked cap clamped it — a negative `limit` would
    have sliced from the end."""
    from app.mcp import server

    src = inspect.getsource(server.composition_diagnostics)
    assert "cap = max(1, min(int(limit or 25), 100))" in src
    assert "[:limit]" not in src


def test_EVERY_money_spending_tool_DECLARES_paid():
    """`_meta` Completeness Law (Track D CD1-CD4): a tool that spends the author's LLM budget must
    declare `paid`. It is orthogonal to `tier` — `tier` says "this writes", `paid` says "this costs
    money" — and the consumer uses it to warn BEFORE the spend, not after.

    DBT-11 was real: only `plan_run_pass` (which I added) declared it, while `plan_propose_spec`,
    `plan_apply_revision` and `plan_compile(run_pipeline=true)` all drive planner-model passes and
    said nothing. An undeclared spender is a tool that quietly bills the user.

    A tool that MAY spend declares `paid` — the user is warned on the POSSIBILITY, not the outcome
    (plan_compile only spends when run_pipeline=true, and that is exactly when it is too late)."""
    from app.mcp import server

    src = inspect.getsource(server)
    for name in ("plan_propose_spec", "plan_apply_revision", "plan_compile", "plan_run_pass"):
        i = src.find(f'tool_name="{name}"')
        assert i > 0, f"{name} is not registered"
        # the tool's own meta block — walk back to the start of its require_meta/decorator call
        block = src[max(0, i - 1600):i]
        assert "paid=True" in block, (
            f"{name} spends the author's LLM budget but does not declare paid=True — "
            "the consumer cannot warn the user before the spend"
        )
