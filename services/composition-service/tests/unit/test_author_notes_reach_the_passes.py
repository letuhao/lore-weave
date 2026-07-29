"""The author's unfiled words must REACH A PROMPT — the stored-and-unread bug class.

History, because it repeated: `canon` was compiled on every run and read by nobody until E6 added a
reader. `author_notes` then did exactly the same thing one iteration later — `ingest` carried them so
the matcher could not delete the author's prose, `compile` copied them into
`planning_package.author_notes`, and **nothing read them**. Verified on a live package: the key was
present, and `grep author_notes` across every service and the frontend found only comments, a
docstring that claimed "the LLM passes read it", and a count rendered in the UI.

It got worse before it got better: `apply_kept_material` routed FOUR of the six planning kinds there
and told both the author and the model that it reached the passes.

These tests assert the CONSUMPTION, not the field. A test that only checked the key exists would have
passed throughout.
"""

from __future__ import annotations

import inspect

from app.services.plan_pass_adapters import PassContext


def _ctx(**over):
    return PassContext(llm=None, user_id="u", book_id=None, project_id=None,  # type: ignore[arg-type]
                       model_source="user_model", model_ref="m", **over)


def test_author_notes_render_as_a_labelled_block():
    ctx = _ctx(package={"author_notes": [
        {"title": "Giọt nước tràn ly", "text": "Lâm Uyên mất Ký ức từng lớp một."},
        {"text": "Không ai sống sót khỏi Huyết Chủ."},
    ]})
    out = ctx.author_notes
    assert "Lâm Uyên mất Ký ức từng lớp một." in out
    assert "Không ai sống sót khỏi Huyết Chủ." in out
    assert "Giọt nước tràn ly" in out, "the note's own heading is orientation the author gave us"


def test_notes_are_NOT_silently_promoted_into_canon():
    """Canon is what the author FIXED; these are words nobody could file. Folding them together
    would turn an unplaced note into an established fact."""
    ctx = _ctx(package={"canon": "Lâm Uyên: thiên phú tuyệt thế.",
                        "author_notes": [{"text": "Có thể đổi tên nhân vật phụ."}]})
    assert ctx.canon == "Lâm Uyên: thiên phú tuyệt thế."
    assert "Có thể đổi tên" not in ctx.canon
    g = ctx.grounding
    assert "Lâm Uyên: thiên phú tuyệt thế." in g and "Có thể đổi tên" in g
    assert "not as canon" in g, "the block must say what it is"


def test_grounding_degrades_to_canon_when_there_are_no_notes():
    ctx = _ctx(package={"canon": "only canon"})
    assert ctx.grounding == "only canon"
    assert _ctx(package={}).grounding == ""


def test_malformed_notes_do_not_break_the_block():
    ctx = _ctx(package={"author_notes": ["a bare string", {"text": ""}, {"text": "real"}, 7]})
    assert "real" in ctx.author_notes and "a bare string" not in ctx.author_notes


def test_the_PACKAGE_READING_passes_actually_pass_the_grounding_block():
    """The assertion that would have caught the original bug.

    `run_cast` and `run_world` are the package readers that take a grounding string. Both must send
    `ctx.grounding`, not `ctx.canon` — otherwise the notes are stored, compiled, rendered as a count
    in the UI, and read by nobody.
    """
    from app.services import plan_pass_adapters as mod

    for fn_name in ("run_cast", "run_world"):
        src = inspect.getsource(getattr(mod, fn_name))
        assert "canon=ctx.grounding" in src, (
            f"{fn_name} passes canon without the author's notes — they reach no prompt"
        )
        assert "canon=ctx.canon," not in src, f"{fn_name} still sends canon alone"


def test_compile_puts_the_notes_where_the_context_looks_for_them():
    """The two halves must agree on ONE key. They are in different modules, which is how they drifted
    the first time."""
    from app.engine.plan_forge.compile import compile_artifacts

    src = inspect.getsource(compile_artifacts)
    assert '"author_notes"' in src
    assert '"author_notes"' in inspect.getsource(PassContext.author_notes.fget)  # type: ignore[union-attr]


# ── the two dogfood traps: a message that names nothing ───────────────────────────────────────────

def test_a_wrong_arc_id_names_the_ids_that_exist():
    """Live in the dogfood: the spec's ids are `arc_01`/`arc_02`, the obvious guess `arc_1` is wrong,
    and nothing listed them. A wrong id used to sail through as `arc = None`, produce a package with
    no chapters, and fail three layers later as "there is nothing to link" — naming neither cause nor
    fix."""
    import pytest

    from app.engine.plan_forge.compile import compile_artifacts

    spec = {"arcs": [{"id": "arc_01", "title": "A"}, {"id": "arc_02", "title": "B"}],
            "events": [], "layers": {"characters": []}, "charter": {}, "meta": {}}
    with pytest.raises(ValueError) as ei:
        compile_artifacts(spec, "arc_1")
    msg = str(ei.value)
    assert "arc_01" in msg and "arc_02" in msg, "the error must list the ids that DO exist"


def test_a_spec_with_no_arcs_at_all_does_not_pretend_one_is_missing():
    """An empty spec is a different failure and must not be reported as a typo."""
    from app.engine.plan_forge.compile import compile_artifacts

    out = compile_artifacts({"arcs": [], "events": [], "layers": {"characters": []},
                             "charter": {}, "meta": {}}, "arc_01")
    assert out["planning_package"]["arc_id"] == "arc_01"


def test_the_PF7_refusal_names_the_proposal_the_gate_actually_reads():
    """The decoy. Without the id, the message sends the author to bootstrap/propose, which mints a
    SECOND proposal; approving and applying that one leaves the gate reading the pass-opened proposal
    and refusing with the identical sentence. Both instruction and failure are word-for-word the
    same, so the loop is invisible. Walked into live."""
    import inspect

    from app.services.plan_forge_service import PlanForgeService

    src = inspect.getsource(PlanForgeService)
    i = src.index("cast cannot be accepted while its glossary seed proposal is")
    msg = src[i:i + 700]
    assert "proposal.id" in msg, "the refusal does not name WHICH proposal"
    assert "Do NOT call bootstrap/propose" in msg, "the decoy is not called out"
