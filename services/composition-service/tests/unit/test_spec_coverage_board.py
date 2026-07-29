"""The coverage board — "what did the read recover, and where it recovered nothing, why".

The surface it replaces was format-bound three times over: `coverage.build_section_map_from_text`
matches `## 1.x` / `### Event N`, the POC fixture's heading shape, exactly like
`ingest._parse_top_sections` (which read 6 of 17 real documents as nothing) and `validate.py`. The
module's own docstring records where that ends: a user's "what is missing from my plan" was computed
against the POC's novel.

The board is computed from the SPEC, which both propose paths produce for any document.
"""

from __future__ import annotations

from app.engine.plan_forge.coverage import spec_coverage_board
from app.engine.plan_forge.ingest import ingest_markdown
from app.engine.plan_forge.propose import propose_spec

_ALL_KINDS = {
    "character_seed", "mechanics", "planner_variables",
    "arc_overview", "writing_principles", "open_questions",
}


def _spec(**over):
    base = {
        "meta": {"open_questions": [], "ingest_unread": {"unclassified": [], "note": ""}},
        "charter": {"style_constraints": [], "forbids": [], "consistency_anchors": []},
        "layers": {"characters": [], "mechanics": [], "variables": []},
        "arcs": [], "events": [], "links": [],
    }
    base.update(over)
    return base


def test_every_kind_is_reported_even_when_empty():
    """A kind that is simply missing from the payload is the silent-absence bug in miniature: a
    consumer cannot tell "nothing there" from "this board does not cover that"."""
    board = spec_coverage_board(_spec())
    assert {k["kind"] for k in board["kinds"]} == _ALL_KINDS
    assert set(board["absent"]) == _ALL_KINDS
    assert board["recovered"] == [] and board["unknown"] == []


def test_a_present_kind_shows_WHAT_was_found_not_just_a_count():
    """Measured reason (POC 6f): the three lines the loop retrieved for the one kind it thought was
    missing were all tone/world rules, not state variables — visible in one glance, invisible in a
    count. The board shows, it does not conclude."""
    board = spec_coverage_board(_spec(
        layers={
            "characters": [{"name": "Lâm Uyên"}, {"name": "Tô Thanh Dao"}],
            "mechanics": [], "variables": [],
        },
    ))
    cast = next(k for k in board["kinds"] if k["kind"] == "character_seed")
    assert cast["status"] == "present" and cast["count"] == 2
    assert cast["evidence"] == ["Lâm Uyên", "Tô Thanh Dao"]


def test_an_absent_kind_is_UNKNOWN_when_the_read_itself_failed():
    """The bug class this board exists inside. A kind is empty either because the author has not
    written it or because the read failed and took it with it — identical in a count, and the second
    is a silent degrade. `unknown` is a refusal to claim either, not a third flavour of absent."""
    confident = spec_coverage_board(_spec())
    assert confident["kinds"][0]["status"] == "absent"

    failed = _spec()
    failed["meta"]["ingest_unread"] = {"empty_read": True, "note": "... FAILED read ...",
                                       "unclassified": []}
    board = spec_coverage_board(failed)
    assert set(board["unknown"]) == _ALL_KINDS
    assert board["absent"] == []
    assert board["read"]["failed"] is True


def test_UNCLASSIFIED_sections_also_make_absence_unclaimable():
    """Weaker than a failed read but the same logic: material the matcher could not place may have
    held any kind, so "absent" would be an overstatement."""
    spec = _spec()
    spec["meta"]["ingest_unread"] = {"unclassified": ["Giọt nước tràn ly"], "note": "1 section..."}
    board = spec_coverage_board(spec)
    assert set(board["unknown"]) == _ALL_KINDS
    assert board["read"]["unclassified"] == ["Giọt nước tràn ly"]


def test_events_count_toward_the_arc_kind():
    """`arc_overview` is the kind an author writes their plot under; a spec that carries events but
    no arc row has plainly not left that kind empty."""
    board = spec_coverage_board(_spec(events=[{"title": "The Wet Ink"}]))
    arc = next(k for k in board["kinds"] if k["kind"] == "arc_overview")
    assert arc["status"] == "present" and arc["evidence"] == ["The Wet Ink"]


def test_plain_string_kinds_carry_their_own_text():
    board = spec_coverage_board(_spec(
        meta={"open_questions": ["What is her name?"], "ingest_unread": {}},
        charter={"style_constraints": ["Short sentences."], "forbids": [],
                 "consistency_anchors": []},
    ))
    by = {k["kind"]: k for k in board["kinds"]}
    assert by["open_questions"]["evidence"] == ["What is her name?"]
    assert by["writing_principles"]["evidence"] == ["Short sentences."]


def test_the_board_reads_a_REAL_document_end_to_end():
    """The point of the rewrite: no fixture, no rubric, no heading shape. A document written the most
    ordinary way there is — one that the old section-map matcher scores 0 on — must produce a board
    that tells the author what they have."""
    doc = ingest_markdown(
        "# The Weight of a Thousand Years\n\n"
        "## Premise\nA woman is murdered by the man she loves.\n\n"
        "## Character: The Protagonist\n- **Name:** Seraphine\n- She returns each cycle.\n\n"
        "## Plot Structure\nThree cycles, each worse than the last.\n"
    )
    board = spec_coverage_board(propose_spec(doc))
    by = {k["kind"]: k for k in board["kinds"]}
    assert by["character_seed"]["evidence"] == ["Seraphine"]
    assert "character_seed" in board["recovered"]

    from app.engine.plan_forge.coverage import build_section_map_from_text
    assert build_section_map_from_text(
        "# The Weight of a Thousand Years\n## Premise\n## Character: The Protagonist\n"
    ) == [], "the matcher this replaces still scores this document 0 — that is why the board exists"


def test_self_check_promotes_the_board_to_the_top_level():
    """Without it, `plan_self_check` answers "what is missing from my plan" with nothing: fidelity is
    None without a per-run rubric, gaps and suggestions are then empty, and `section_map_size` counts
    headings most documents do not have."""
    from app.engine.plan_forge.self_check import run_self_check_on_document

    out = run_self_check_on_document(_spec(), "# Anything\nsome prose\n")
    assert out["fidelity"]["score"] is None and out["ranked_gaps"] == []
    assert out["board"] is not None and set(out["board"]["absent"]) == _ALL_KINDS


async def test_the_service_returns_the_board_even_when_everything_else_degrades():
    """The wiring, proven by EFFECT — a board nobody receives is a bug, not a feature.

    `self_check` returned `{"gaps": [], "fidelity_score": None}` whenever the run had no source
    document, no per-run rubric, or the own-document coverage raised. That payload reads as "your
    plan is fine" and means "we computed nothing" — the exact silent-degrade shape this cycle has
    been closing everywhere else. The board is computed from the spec before any of those branches,
    so it survives all three.
    """
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.plan_forge_service import PlanForgeService

    spec = _spec(layers={"characters": [{"name": "Seraphine"}], "mechanics": [], "variables": []})

    class _Runs:
        async def get_for_book(self, book_id, run_id):
            # source_markdown EMPTY: `_document_markdown` returns "", so the own-document coverage
            # never runs at all — the harshest of the three degrade paths.
            return SimpleNamespace(id=run_id, source_markdown="")

        async def latest_artifact(self, book_id, run_id, kind):
            return SimpleNamespace(content=spec) if kind == "spec" else None

    svc = PlanForgeService.__new__(PlanForgeService)
    svc._runs = _Runs()  # type: ignore[attr-defined]

    out = await svc.self_check(uuid4(), uuid4(), uuid4())
    assert out["fidelity_score"] is None
    board = out["coverage_board"]
    assert board is not None, "the board did not reach the caller"
    cast = next(k for k in board["kinds"] if k["kind"] == "character_seed")
    assert cast["evidence"] == ["Seraphine"]


def test_a_REGENERATED_step_makes_absence_unclaimable_on_the_llm_path():
    """The gap the dogfood found: the board could only ever say `absent` on the DEFAULT path.

    `unclassified` is written by the RULES propose alone, so the LLM path — where most runs now go —
    had no degrade signal at all. Its equivalent is a step that had to be regenerated (a repetition
    loop) or repaired (unparseable output): the answer arrived, but not cleanly, so an empty kind may
    be the read's fault rather than the document's.
    """
    spec = _spec()
    spec["meta"]["ingest_unread"] = {"path": "llm", "unclassified": [],
                                     "degraded_steps": ["analyze_retry1"], "note": "…"}
    board = spec_coverage_board(spec)
    assert set(board["unknown"]) == _ALL_KINDS
    assert board["absent"] == []
    assert board["read"]["degraded_steps"] == ["analyze_retry1"]
    assert board["read"]["path"] == "llm"


def test_a_CLEAN_llm_read_still_claims_absence_confidently():
    """The guard must not cry wolf on every LLM run — a clean read is a clean read."""
    spec = _spec()
    spec["meta"]["ingest_unread"] = {"path": "llm", "unclassified": [], "degraded_steps": [],
                                     "note": ""}
    board = spec_coverage_board(spec)
    assert set(board["absent"]) == _ALL_KINDS and board["unknown"] == []


def test_the_llm_propose_ACTUALLY_attaches_the_block():
    """Consumption, not shape: the board can only report what the producer writes."""
    from app.engine.plan_forge.propose_llm_async import _attach_read_provenance

    spec = {"meta": {}}
    _attach_read_provenance(spec, [{"step": "analyze"}, {"step": "materialize_repair"}])
    blk = spec["meta"]["ingest_unread"]
    assert blk["path"] == "llm"
    assert blk["degraded_steps"] == ["materialize_repair"]
    assert "not cleanly" in blk["note"]

    clean = {"meta": {}}
    _attach_read_provenance(clean, [{"step": "analyze"}, {"step": "materialize"}])
    assert clean["meta"]["ingest_unread"]["degraded_steps"] == []
    assert clean["meta"]["ingest_unread"]["note"] == ""
