"""D-GENERATED-FACT-HAS-NO-HOME — the recorded-cast write-back.

The defect this exists for, measured 2026-08-01 on a real 4-scene chapter:

    scene 2 ends   "**He** is the anchor," Cassius said.
    scene 3 opens  "**She's** a Scribe."

Both facts were INVENTED by the drafter — no spec, no glossary, no canon contained them — so
there was nothing authoritative to contradict and nothing to compare against. The facts did
reach scene 3, as prose, inside a 14,314-character `<recent>`; and prose is the first thing the
budget compresses.

These tests pin the two halves of the fix separately, because they fail differently:
the RECORDING (deterministic, no model) and the CARRYING (a protected prompt segment).
"""
from __future__ import annotations

import pytest

from app.db.models import MAX_EXIT_CAST, SceneExitStateIn
from app.engine.exit_state import (
    cast_rows_from_people,
    merge_authored_exit_state,
    merge_generated_cast,
    recorded_people,
    render_carried_cast,
)


# ────────────────────────────── the deterministic half ──────────────────────────────

def test_only_people_the_passage_NAMES_are_recorded():
    """A row keyed on a referring expression means "everybody who could be called that". As a
    stored fact it is handed to the next scene as though it described a character."""
    rows = cast_rows_from_people([
        {"who": "She", "name": "", "pronoun": "she", "role": "Scribe"},
        {"who": "the stranger", "name": "", "pronoun": "he", "role": ""},
        {"who": "Cassius", "name": "Cassius", "pronoun": "he", "role": "the anchor"},
    ])
    assert [r["who"] for r in rows] == ["Cassius"]


def test_the_MEASURED_vietnamese_row_set_records_nothing():
    """VERBATIM from the first live run of this feature (2026-08-01, gemma-4-26b, a Vietnamese
    scene). Ten rows came back and the English `_NOT_A_NAME` list filtered NONE of them —
    including `Ánh mắt họ`, "their gaze", which is not a person. All ten would have been
    injected into the next scene's prompt as facts about the cast.

    The scene genuinely named nobody, so the correct recording is empty. This is the control
    that the old filter could not pass and the reason the extractor now fills a `name` slot."""
    measured = [
        {"who": "Người kia", "role": "đối phương", "pronoun": "he"},
        {"who": "Anh ta", "role": "", "pronoun": "he"},
        {"who": "Người đàn ông", "role": "", "pronoun": "he"},
        {"who": "Anh", "role": "", "pronoun": "he"},
        {"who": "cộng đồng", "role": "", "pronoun": "they"},
        {"who": "những người xung quanh", "role": "", "pronoun": "they"},
        {"who": "đối phương", "role": "", "pronoun": "he"},
        {"who": "ngươi", "role": "", "pronoun": "he"},
        {"who": "hai người đàn ông", "role": "", "pronoun": "they"},
        {"who": "Ánh mắt họ", "role": "", "pronoun": "they"},
    ]
    assert cast_rows_from_people(measured) == []


def test_CONTROL_a_vietnamese_passage_that_DOES_name_someone_still_records():
    """The control for the test above. Without it, "records nothing" could equally mean the
    recorder is broken for Vietnamese — which is a detector that cannot fire, dressed as a
    fix."""
    rows = cast_rows_from_people([
        {"who": "Tô Thanh Dao", "name": "Tô Thanh Dao", "pronoun": "she", "role": "đế"},
        {"who": "Anh ta", "name": "", "pronoun": "he", "role": ""},
    ])
    assert rows == [{"who": "Tô Thanh Dao", "pronoun": "she", "role": "đế"}]


def test_an_unnamed_seam_links_NOBODY_rather_than_reading_clean():
    """MEASURED as a false green, live, on the control run: a Vietnamese scene where nobody is
    named came back `linked=2, clean=true` because two common nouns matched. `clean` requires
    `linked > 0`, so that is a chapter reported as verified on the strength of an accident.

    An empty `name` is the extractor ANSWERING "not named" — not a missing value to fall back
    from."""
    from app.engine.cross_scene_check import compare_people
    r = compare_people(
        [{"who": "Người đàn ông", "name": "", "pronoun": "he"},
         {"who": "Anh ta", "name": "", "pronoun": "he"}],
        [{"who": "Người đàn ông", "name": "", "pronoun": "she"},
         {"who": "Anh ta", "name": "", "pronoun": "she"}],
    )
    assert r.linked == 0 and r.clean is False
    assert r.contradictions == [], "and it must not manufacture a finding from them either"


def test_CONTROL_a_named_seam_still_links_and_still_fires():
    """The control for the test above: the strict key must not have made the check inert."""
    from app.engine.cross_scene_check import compare_people
    r = compare_people(
        [{"who": "Lục công tử", "name": "Lục Hàn", "pronoun": "he"}],
        [{"who": "hắn", "name": "Lục Hàn", "pronoun": "she"}],
    )
    assert r.linked == 1 and len(r.contradictions) == 1


def test_a_stored_cast_row_has_no_name_key_and_is_still_an_identity():
    """`recorded_people` emits `{who, pronoun, role}` — those rows already passed the name
    filter when they were written, so the absence of the key must not demote them."""
    from app.engine.cross_scene_check import compare_people
    r = compare_people(
        recorded_people({"cast": [{"who": "Lục Hàn", "pronoun": "he"}]}),
        [{"who": "hắn", "name": "Lục Hàn", "pronoun": "she"}],
    )
    assert r.linked == 1 and len(r.contradictions) == 1


def test_a_name_slot_echoing_a_pronoun_is_still_refused():
    """A weak model will sometimes copy `who` into `name`. The English list stays as a second
    net on the one field that reaches a prompt as an assertion."""
    assert cast_rows_from_people([{"who": "She", "name": "She", "pronoun": "she"}]) == []


def test_an_article_and_a_possessive_do_not_split_one_person_into_two():
    rows = cast_rows_from_people([
        {"who": "The Weaver", "name": "The Weaver", "pronoun": "she", "role": ""},
        {"who": "Weaver's", "name": "Weaver's", "pronoun": "she", "role": "guild head"},
    ])
    assert len(rows) == 1, rows


def test_an_out_of_set_pronoun_becomes_none_rather_than_being_stored_raw():
    """A Vietnamese passage answers `anh ấy`. Storing it raw would put a value in the column
    that no downstream membership test knows about — the contradiction check would neither
    fire nor say why."""
    rows = cast_rows_from_people(
        [{"who": "Tô Thanh Dao", "name": "Tô Thanh Dao", "pronoun": "anh ấy", "role": ""}])
    assert rows[0]["pronoun"] == "none"


def test_the_recorded_cast_is_capped():
    rows = cast_rows_from_people(
        [{"who": f"Person{i:03d}", "name": f"Person{i:03d}", "pronoun": "they"}
         for i in range(200)])
    assert len(rows) == MAX_EXIT_CAST


def test_a_non_dict_row_does_not_crash_the_recording():
    assert cast_rows_from_people(["Cassius", None, {"who": "Elara", "name": "Elara"}]) == [
        {"who": "Elara", "pronoun": "none", "role": ""}]


# ────────────────────────────── provenance ──────────────────────────────

def test_an_authors_curated_cast_is_never_overwritten_by_a_regeneration():
    stored = {"v": 1, "source": "author", "cast": [{"who": "Cassius", "pronoun": "she"}]}
    env, reason = merge_generated_cast(stored, [{"who": "Cassius", "pronoun": "he"}])
    assert env is None and reason == "author_owned"


def test_the_decline_is_REPORTED_not_silent():
    """`None` alone would be indistinguishable from "nothing was extracted". The two mean
    opposite things to whoever reads the job envelope."""
    assert merge_generated_cast(None, [])[1] == "no_cast_extracted"
    assert merge_generated_cast({"source": "author", "cast": [{"who": "X"}]},
                                [{"who": "X"}])[1] == "author_owned"
    assert merge_generated_cast(None, [{"who": "X"}])[1] == "recorded"


def test_a_write_back_preserves_every_authored_prose_field():
    """The generator writes ONE key. A regeneration that reset an author's `plot` note would
    be the same data loss as overwriting their cast, only harder to notice."""
    stored = {"v": 1, "source": "generator", "characters": "Elara is afraid",
              "world": "the undercroft, past midnight", "plot": "the ledger is still missing",
              "advances": ["the seal cracked"]}
    env, _ = merge_generated_cast(stored, [{"who": "Elara", "pronoun": "she", "role": ""}])
    assert env["characters"] == "Elara is afraid"
    assert env["world"] == "the undercroft, past midnight"
    assert env["plot"] == "the ledger is still missing"
    assert env["advances"] == ["the seal cracked"]
    assert env["source"] == "generator"


def test_an_author_editing_prose_does_not_wipe_the_recorded_cast():
    """The whole-envelope replace was the pre-existing semantic. Left alone it would have made
    the continuity floor evaporate on a perfectly ordinary authoring action."""
    stored = {"v": 1, "source": "generator",
              "cast": [{"who": "Cassius", "pronoun": "he", "role": "the anchor"}]}
    incoming = SceneExitStateIn(plot="the ledger is still missing").model_dump(mode="json")
    out = merge_authored_exit_state(stored, incoming)
    assert out["cast"] == [{"who": "Cassius", "pronoun": "he", "role": "the anchor"}]
    assert out["source"] == "generator", "an untouched cast must keep the provenance that made it"
    assert out["plot"] == "the ledger is still missing"


def test_an_author_who_DOES_send_a_cast_is_stamped_as_its_author():
    incoming = SceneExitStateIn(
        cast=[{"who": "Cassius", "pronoun": "she"}]).model_dump(mode="json")
    out = merge_authored_exit_state({"source": "generator", "cast": []}, incoming)
    assert out["source"] == "author"
    # …and that stamp is what makes the next generate stand down.
    assert merge_generated_cast(out, [{"who": "Cassius", "pronoun": "he"}])[1] == "author_owned"


def test_an_explicit_empty_cast_clears_it_and_omitting_it_does_not():
    stored = {"source": "generator", "cast": [{"who": "Cassius", "pronoun": "he"}]}
    cleared = merge_authored_exit_state(
        stored, SceneExitStateIn(cast=[]).model_dump(mode="json"))
    assert cleared["cast"] == []
    kept = merge_authored_exit_state(stored, SceneExitStateIn().model_dump(mode="json"))
    assert kept["cast"] == [{"who": "Cassius", "pronoun": "he"}]


def test_the_wire_model_refuses_a_caller_chosen_provenance():
    """A caller able to send `source` could stamp its own write `author` and freeze the record
    against every future write-back. `extra='forbid'` makes that a 422 that says so, rather
    than a value silently overridden."""
    with pytest.raises(Exception) as exc:
        SceneExitStateIn(source="author")
    assert "source" in str(exc.value)


# ────────────────────────────── the carrying half ──────────────────────────────

def test_the_carried_line_is_facts_not_a_sentence():
    line = render_carried_cast({"cast": [
        {"who": "Cassius", "pronoun": "he", "role": "the anchor"},
        {"who": "Elara", "pronoun": "she", "role": ""},
    ]})
    assert line == "Cassius — he — the anchor; Elara — she"


def test_nothing_recorded_renders_nothing_rather_than_an_empty_label():
    assert render_carried_cast(None) == ""
    assert render_carried_cast({"cast": []}) == ""
    assert render_carried_cast({"v": 1, "source": "generator"}) == ""


def test_recorded_people_is_None_not_empty_when_there_is_no_record():
    """`[]` would be compared against the later scene, match nobody, and report `linked=0` as
    though an extraction had run — rebuilding the exact false green the seam check removed."""
    assert recorded_people(None) is None
    assert recorded_people({"cast": []}) is None
    assert recorded_people({"cast": [{"who": "Cassius", "pronoun": "he"}]}) == [
        {"who": "Cassius", "pronoun": "he", "role": ""}]


# ────────────────────────────── the seam check consumes the record ──────────────────────────────

class _LLM:
    def __init__(self, replies, status="completed"):
        self._replies = list(replies)
        self._status = status
        self.calls = 0

    async def submit_and_wait(self, **kw):
        from types import SimpleNamespace
        self.calls += 1
        body = self._replies.pop(0) if self._replies else '{"people": []}'
        return SimpleNamespace(status=self._status,
                               result={"messages": [{"content": body}]})


@pytest.mark.asyncio
async def test_a_recorded_earlier_side_replaces_its_extraction_call():
    from app.engine.cross_scene_check import check_chapter_consistency
    llm = _LLM(['{"people": [{"who": "Cassius", "name": "Cassius", "pronoun": "she", "role": "Scribe"}]}'])
    r = await check_chapter_consistency(
        llm, user_id="u", model_source="s", model_ref="m",
        scenes=["earlier prose", "later prose"],
        earlier_recorded=[{"who": "Cassius", "pronoun": "he", "role": "the anchor"}],
    )
    assert llm.calls == 1, "the earlier side was recorded; only the later side needs reading"
    assert r.earlier_source == "recorded"
    assert len(r.contradictions) == 1, "and it still catches the flip"


@pytest.mark.asyncio
async def test_CONTROL_no_record_still_extracts_both_sides():
    """The control for the test above. Without it, "one call" could equally mean the check
    silently stopped reading a side — the same shape as a detector that cannot fail."""
    from app.engine.cross_scene_check import check_chapter_consistency
    llm = _LLM(['{"people": [{"who": "Cassius", "name": "Cassius", "pronoun": "he", "role": "the anchor"}]}',
                '{"people": [{"who": "Cassius", "name": "Cassius", "pronoun": "she", "role": "Scribe"}]}'])
    r = await check_chapter_consistency(
        llm, user_id="u", model_source="s", model_ref="m",
        scenes=["earlier prose", "later prose"],
    )
    assert llm.calls == 2 and r.earlier_source == "extracted"
    assert len(r.contradictions) == 1


@pytest.mark.asyncio
async def test_an_EMPTY_record_falls_back_to_extraction_rather_than_comparing_against_nobody():
    from app.engine.cross_scene_check import check_chapter_consistency
    llm = _LLM(['{"people": [{"who": "Cassius", "name": "Cassius", "pronoun": "he"}]}',
                '{"people": [{"who": "Cassius", "name": "Cassius", "pronoun": "she"}]}'])
    r = await check_chapter_consistency(
        llm, user_id="u", model_source="s", model_ref="m",
        scenes=["earlier", "later"], earlier_recorded=[],
    )
    assert llm.calls == 2 and r.earlier_source == "extracted"
    assert len(r.contradictions) == 1


# ────────────────────────────── the orchestrator is degrade-safe ──────────────────────────────

class _Repo:
    """Stands in for OutlineRepo. Records the write so a test can assert what was persisted."""

    def __init__(self, exit_state=None, missing=False, raises=False):
        from types import SimpleNamespace
        self._node = None if missing else SimpleNamespace(exit_state=exit_state)
        self._raises = raises
        self.written = None

    async def get_node(self, node_id, conn=None):
        if self._raises:
            raise RuntimeError("db down")
        return self._node

    async def update_node(self, node_id, patch, **kw):
        self.written = patch


@pytest.fixture
def _patched_repo(monkeypatch):
    made = {}

    def _factory(repo):
        made["repo"] = repo
        import app.db.repositories.outline as outline_mod
        monkeypatch.setattr(outline_mod, "OutlineRepo", lambda _pool: repo)
        return repo

    _factory.made = made
    return _factory


@pytest.mark.asyncio
async def test_the_happy_path_persists_the_cast_and_says_so(_patched_repo):
    from app.services.exit_state_writeback import record_scene_exit_state
    repo = _patched_repo(_Repo(exit_state=None))
    llm = _LLM(['{"people": [{"who": "Cassius", "name": "Cassius", "pronoun": "he", '
                '"role": "the anchor"}]}'])
    out = await record_scene_exit_state(
        object(), llm, user_id="u", outline_node_id="00000000-0000-0000-0000-000000000001",
        final_text="…he is the anchor…", model_source="s", model_ref="m")
    assert out == {"status": "recorded", "cast_size": 1}
    assert repo.written["exit_state"]["cast"] == [
        {"who": "Cassius", "pronoun": "he", "role": "the anchor"}]
    assert repo.written["exit_state"]["source"] == "generator"


@pytest.mark.asyncio
async def test_an_extraction_outage_records_nothing_and_never_claims_it_did(_patched_repo):
    from app.services.exit_state_writeback import record_scene_exit_state
    repo = _patched_repo(_Repo(exit_state=None))
    llm = _LLM(['{"people": []}'], status="failed")
    out = await record_scene_exit_state(
        object(), llm, user_id="u", outline_node_id="00000000-0000-0000-0000-000000000001",
        final_text="prose", model_source="s", model_ref="m")
    assert out["status"] == "degraded"
    assert repo.written is None


@pytest.mark.asyncio
async def test_a_repo_failure_is_advisory_and_never_raises_into_the_generate(_patched_repo):
    """F1. The prose is the expensive thing; the record is not worth losing it for."""
    from app.services.exit_state_writeback import record_scene_exit_state
    _patched_repo(_Repo(raises=True))
    llm = _LLM(['{"people": [{"who": "Cassius", "name": "Cassius", "pronoun": "he"}]}'])
    out = await record_scene_exit_state(
        object(), llm, user_id="u", outline_node_id="00000000-0000-0000-0000-000000000001",
        final_text="prose", model_source="s", model_ref="m")
    assert out["status"] == "write_failed"


@pytest.mark.asyncio
async def test_a_chapter_scoped_generate_reports_no_node_rather_than_looking_recorded():
    """The chapter single-pass and the stitch path have no per-scene node. That is a real
    boundary of this feature and the envelope has to name it — otherwise a chapter draft is
    indistinguishable from a scene whose write-back silently did nothing."""
    from app.services.exit_state_writeback import record_scene_exit_state
    out = await record_scene_exit_state(
        object(), _LLM([]), user_id="u", outline_node_id=None,
        final_text="prose", model_source="s", model_ref="m")
    assert out == {"status": "no_node", "cast_size": 0}


@pytest.mark.asyncio
async def test_a_supplied_extraction_is_reused_rather_than_paid_for_twice(_patched_repo):
    from app.services.exit_state_writeback import record_scene_exit_state
    repo = _patched_repo(_Repo(exit_state=None))
    llm = _LLM([])
    out = await record_scene_exit_state(
        object(), llm, user_id="u", outline_node_id="00000000-0000-0000-0000-000000000001",
        final_text="prose", model_source="s", model_ref="m",
        people=[{"who": "Elara", "name": "Elara", "pronoun": "she", "role": ""}])
    assert out["status"] == "recorded" and llm.calls == 0


# ────────────────────────────── the floor, under a real squeeze ──────────────────────────────

def _squeeze(carried: str, prose_paragraphs: list[str], budget: int, *, canon=()):
    """Run the actual assemble → budget path, not a stand-in for it."""
    from app.packer import assemble
    from app.packer import budget as B
    from app.packer.lenses import LensBundle

    bundle = LensBundle(recent=list(prose_paragraphs), carried_cast=carried,
                        extra_canon=list(canon))
    res = B.enforce_budget(assemble.build_segments(bundle), budget, B.default_counter())
    return assemble.segments_to_blocks(res.kept), res


def test_the_carried_cast_survives_the_squeeze_that_drops_the_prose_it_came_from():
    """THE POINT OF THE SLICE. The same facts are in `recent` as prose; prose is what a tight
    budget trims. Measured on a real chapter: `recent_floor_compressed > 0` and the gender of a
    just-introduced character fell out between scene 2 and scene 3.

    ⚠ THIS TEST'S FIRST VERSION WAS THEATRE. It squeezed a budget until the prose dropped and
    asserted the `carries=` line was still there — and it stayed green with `protected=False`
    injected, because `enforce_budget` drops largest-first within a priority and stops the
    moment it is under budget. A 25-character line survives that by being SMALL, which proves
    nothing about it being protected. Caught only by injecting the defect and watching.

    So the squeeze has to reach the regime where the two differ: protected content alone over
    budget, which makes the drop loop exhaust every droppable segment. `over_budget` asserts
    the run actually got there rather than the numbers happening to be comfortable."""
    prose = [f"paragraph {i} " + "filler words here " * 60 for i in range(8)]
    canon = ["a standing rule that must hold in every scene " * 40]
    blocks, res = _squeeze("Cassius — he — the anchor", prose, budget=120, canon=canon)

    assert res.over_budget, "control: the squeeze must reach the regime where protection decides"
    assert "paragraph 0" not in blocks.get("recent", ""), \
        "control: at this budget the older prose must actually be dropped"
    assert "carries=Cassius — he — the anchor" in blocks["beat"]


def test_CONTROL_nothing_recorded_puts_no_empty_label_in_the_prompt():
    blocks, _ = _squeeze("", ["a paragraph"], budget=100000)
    assert "carries=" not in blocks.get("beat", "")
