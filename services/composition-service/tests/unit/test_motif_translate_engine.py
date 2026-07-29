"""app/engine/motif_translate.py — the USER-PAID translate path.

The model call itself is stubbed; what is worth guarding is everything around it,
because every failure here is one the user has ALREADY PAID FOR:

  · a leaf the model drops must keep its source wording, never blank
  · a key the model invents must be dropped, never merged onto a different beat
  · a whole-call failure must not write a "translation" that is the English source
    (a row like that reports text_fallback=false forever — a lie the reader cannot see)
  · a leaf handed back in English must be REPORTED, since we deliberately do not
    re-spend to retry it
  · structure (tension_target/order/actant) must never reach the translator
  · the tenancy gate must be re-applied at run time, not trusted from the proposal
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from app.engine import motif_translate as mtr
from app.motif_i18n import TranslationFileError


def _motif(**over):
    m = {
        "id": uuid4(),
        "code": "mystery.witness",
        "original_language": "en",
        "name": "The Witness Who Lies",
        "summary": "a statement contradicts one small checkable thing",
        "emotion_target": "tension",
        "roles": [{"key": "witness", "actant": "subject", "label": "the witness",
                   "constraints": ["must have been present"]}],
        "beats": [
            {"key": "testify", "label": "The account is given",
             "intent": "a coherent account", "tension_target": 2, "order": 1},
            {"key": "press", "label": "The lie is pressed",
             "intent": "the gap is put to them", "tension_target": 4, "order": 2},
        ],
        "preconditions": [{"text": "someone saw something"}],
        "effects": [{"text": "the frame of the case moves"}],
        "examples": [{"text": "He was not at the warehouse."}],
    }
    m.update(over)
    return m


class _LLM:
    """Stands in for the gateway. `respond` maps the sent {key: text} → the reply."""

    def __init__(self, respond):
        self._respond = respond
        self.calls: list[dict] = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        sent = json.loads(kw["input"]["messages"][-1]["content"].split("\n", 2)[-1]
                          .split(":\n", 1)[-1])
        out = self._respond(sent)

        class _Job:
            status = "completed"
            result = {"messages": [{"role": "assistant",
                                    "content": json.dumps(out, ensure_ascii=False)}]}
        return _Job()


async def _run(motif, respond, **kw):
    return await mtr.translate_one(
        _LLM(respond), motif, user_id=str(uuid4()), target_language="ja",
        model_source="user_model", model_ref="m-1", **kw)


# ── what reaches the model ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_structure_is_never_sent_for_translation():
    """`tension_target`, `order`, the greimas `actant`, the code — machine values. A
    model asked to 'localize' them would return a translated number and the merge
    would take it."""
    llm = _LLM(lambda sent: {k: f"JA::{v}" for k, v in sent.items()})
    await mtr.translate_one(llm, _motif(), user_id=str(uuid4()), target_language="ja",
                            model_source="user_model", model_ref="m-1")
    blob = json.dumps(llm.calls[0]["input"]["messages"][-1]["content"], ensure_ascii=False)
    for structural in ("tension_target", "order", "actant", "mystery.witness"):
        assert structural not in blob, f"{structural} must not reach the translator"


@pytest.mark.asyncio
async def test_the_response_schema_pins_the_exact_key_set():
    """Key-set identity enforced at the schema layer, not only checked afterwards — a
    provider that honours it cannot drop or invent a key at all."""
    llm = _LLM(lambda sent: {k: f"JA::{v}" for k, v in sent.items()})
    await mtr.translate_one(llm, _motif(), user_id=str(uuid4()), target_language="ja",
                            model_source="user_model", model_ref="m-1")
    schema = llm.calls[0]["input"]["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "beats.testify.label" in schema["properties"]
    assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.asyncio
async def test_the_motif_name_is_given_as_context_not_as_a_key_to_translate():
    """A beat label only reads correctly against the pattern it belongs to. Translating
    'the witness' with no idea which story pattern it serves gives a literal,
    characterless result — naming the pattern first is what makes the craft land."""
    llm = _LLM(lambda sent: {k: f"JA::{v}" for k, v in sent.items()})
    await mtr.translate_one(llm, _motif(), user_id=str(uuid4()), target_language="ja",
                            model_source="user_model", model_ref="m-1")
    user_msg = llm.calls[0]["input"]["messages"][-1]["content"]
    assert "The Witness Who Lies" in user_msg.split("{")[0], "the context block is missing"


@pytest.mark.asyncio
async def test_the_spend_is_labelled_for_the_usage_gui():
    """provider-registry's `operation` is quad-overloaded, so the billing label rides
    job_meta.usage_purpose. Without it the user sees this spend as an anonymous 'chat'."""
    llm = _LLM(lambda sent: {k: f"JA::{v}" for k, v in sent.items()})
    await mtr.translate_one(llm, _motif(), user_id=str(uuid4()), target_language="ja",
                            model_source="user_model", model_ref="m-1")
    assert llm.calls[0]["job_meta"]["usage_purpose"] == "motif_translate"
    assert llm.calls[0]["operation"] == "chat"


# ── never blank, never mis-merge ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_a_dropped_key_falls_back_to_source_never_blank():
    out = await _run(_motif(), lambda sent: {k: f"JA::{v}" for k, v in sent.items()
                                             if k != "name"})
    assert out["status"] == "translated"
    assert out["payload"]["name"] == "The Witness Who Lies"
    assert out["fell_back"] == ["name"]


@pytest.mark.asyncio
async def test_an_empty_value_falls_back_rather_than_blanking_the_card():
    out = await _run(_motif(), lambda sent: {**{k: f"JA::{v}" for k, v in sent.items()},
                                             "name": "   "})
    assert out["payload"]["name"] == "The Witness Who Lies"
    assert "name" in out["fell_back"]


@pytest.mark.asyncio
async def test_an_invented_key_is_dropped_not_merged_onto_another_beat():
    """THE mis-merge guard. At runtime a drifted key cannot raise the way it does in the
    dev-time tool (there is nobody to go fix the file, and raising would burn the user's
    money for nothing) — so it is dropped, the beat keeps its own wording, and the drift
    is reported."""
    def respond(sent):
        out = {k: f"JA::{v}" for k, v in sent.items()}
        out.pop("beats.press.label")
        out["beats.typo_key.label"] = "JA::wrong beat"
        return out

    out = await _run(_motif(), respond)
    assert out["dropped"] == ["beats.typo_key.label"]
    press = next(b for b in out["payload"]["beats"] if b["key"] == "press")
    assert press["label"] == "The lie is pressed", "translated wording landed on the wrong beat"


@pytest.mark.asyncio
async def test_translated_values_land_on_the_right_beat():
    out = await _run(_motif(), lambda sent: {k: f"JA::{v}" for k, v in sent.items()})
    by_key = {b["key"]: b for b in out["payload"]["beats"]}
    assert by_key["testify"]["label"] == "JA::The account is given"
    assert by_key["press"]["label"] == "JA::The lie is pressed"
    assert out["payload"]["roles"][0]["constraints"] == ["JA::must have been present"]


@pytest.mark.asyncio
async def test_a_wholly_failed_call_writes_nothing():
    """Writing the English source as a 'translation' would make the row report
    `text_fallback: false` forever — the reader is told this IS Japanese."""
    out = await _run(_motif(), lambda sent: {})
    assert out["status"] == "model_failed"
    assert out["payload"] is None


@pytest.mark.asyncio
async def test_a_motif_with_no_text_refuses_before_spending():
    llm = _LLM(lambda sent: {})
    out = await mtr.translate_one(
        llm, {"id": uuid4(), "code": "x", "name": "", "summary": "",
              "emotion_target": None, "roles": [], "beats": [],
              "preconditions": [], "effects": [], "examples": []},
        user_id=str(uuid4()), target_language="ja",
        model_source="user_model", model_ref="m-1")
    assert out["status"] == "nothing_to_translate"
    assert llm.calls == [], "the user was charged for a call with nothing to say"


# ── echo: reported, never silently re-spent ────────────────────────────────
@pytest.mark.asyncio
async def test_an_english_echo_is_reported_not_retried():
    """The dev-time tool self-heals with --rounds because nobody watches a 17-locale
    batch. Here the user has already paid for one pass; a silent second pass doubles
    their spend. So we say so instead."""
    llm = _LLM(lambda sent: {**{k: f"JA::{v}" for k, v in sent.items()},
                             "summary": sent["summary"]})
    out = await mtr.translate_one(llm, _motif(), user_id=str(uuid4()), target_language="ja",
                                  model_source="user_model", model_ref="m-1")
    assert out["echoed"] == ["summary"]
    assert out["payload"]["summary"] == "a statement contradicts one small checkable thing"
    assert len(llm.calls) == 1, "an echo must not trigger a second, unbilled-for call"


@pytest.mark.asyncio
async def test_a_one_word_echo_IS_flagged_for_a_non_latin_target():
    """`emotion_target: "tension"` handed straight back is not Japanese. The cognate
    defence that justifies ignoring short verbatim labels — `Status` is a German word —
    has no force against a target that does not use the Latin alphabet, so the bar is
    the target's, not the corpus's."""
    out = await _run(_motif(emotion_target="tension"),
                     lambda sent: {**{k: f"JA::{v}" for k, v in sent.items()},
                                   "emotion_target": "tension"})
    assert out["echoed"] == ["emotion_target"]


@pytest.mark.asyncio
async def test_the_same_one_word_echo_is_NOT_flagged_for_a_latin_target():
    """…and the noise the bar was raised to suppress stays suppressed: measured on the
    real locales, raw byte-equality flagged 339 German strings of which exactly one was
    a defect."""
    llm = _LLM(lambda sent: {**{k: f"DE::{v}" for k, v in sent.items()},
                             "emotion_target": "tension"})
    out = await mtr.translate_one(llm, _motif(emotion_target="tension"),
                                  user_id=str(uuid4()), target_language="de",
                                  model_source="user_model", model_ref="m-1")
    assert out["echoed"] == []


# ── structure survives ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_the_written_payload_carries_only_translatable_leaves():
    """`motif_translation` stores text; structure stays on the source row and is merged
    back at read time. A `tension_target` in the translation row would let a stale
    translation silently override live pacing."""
    out = await _run(_motif(), lambda sent: {k: f"JA::{v}" for k, v in sent.items()})
    for beat in out["payload"]["beats"]:
        assert set(beat) <= {"key", "label", "intent"}, beat
    for role in out["payload"]["roles"]:
        assert set(role) <= {"key", "label", "constraints"}, role


@pytest.mark.asyncio
async def test_a_broken_assembly_raises_rather_than_writing():
    """The structural gate. Unknown keys are filtered before this, so what it catches is
    an assembly fault — and it must raise, because a half-built payload written to the
    DB is indistinguishable from a real translation."""
    motif = _motif()
    out = await _run(motif, lambda sent: {k: f"JA::{v}" for k, v in sent.items()})
    # Feed the assembled entry back with an extra beat the source does not have.
    from app.motif_i18n import extract_translatable, parse_translation_entry
    entry = {"name": "x", "beats": {"ghost": {"label": "y"}}}
    with pytest.raises(TranslationFileError, match="unknown key"):
        parse_translation_entry(entry, extract_translatable(motif), where="t")
    assert out["status"] == "translated"


# ── the run-time tenancy gate ──────────────────────────────────────────────
class _Repo:
    def __init__(self, allowed, state=None):
        self._allowed = allowed
        self._state = state or {}
        self.writes: list[tuple] = []

    async def list_translatable(self, caller, ids, *, book_id=None):
        return [m for m in self._allowed if m["id"] in ids]

    async def get_translation_state(self, motif_id, lang):
        return self._state.get((motif_id, lang))

    async def upsert_translation(self, motif_id, lang, payload, *, source_content_hash,
                                 translated_by):
        self.writes.append((motif_id, lang, payload, source_content_hash, translated_by))
        return True


@pytest.fixture
def repo_patch(monkeypatch):
    def _install(repo):
        import app.db.repositories.motif_repo as mr
        monkeypatch.setattr(mr, "MotifRepo", lambda pool: repo)
        return repo
    return _install


async def _run_job(repo_patch, repo, motif_ids, respond=None, **over):
    repo_patch(repo)
    llm = _LLM(respond or (lambda sent: {k: f"JA::{v}" for k, v in sent.items()}))
    inp = {"motif_ids": [str(m) for m in motif_ids], "target_language": "ja",
           "model_ref": "m-1", "model_source": "user_model", **over}
    return await mtr.run_translate_motifs(None, llm, user_id=str(uuid4()), input=inp)


@pytest.mark.asyncio
async def test_a_motif_the_caller_may_not_translate_is_refused_at_run_time(repo_patch):
    """Re-applied HERE and not trusted from the proposal: the sweeper can re-drive this
    job long after the grant that authorized it was revoked. The refusal is uniform —
    it does not distinguish 'system' from 'not yours' from 'does not exist'."""
    stranger = uuid4()
    out = await _run_job(repo_patch, _Repo(allowed=[]), [stranger])
    assert out["results"] == [{"motif_id": str(stranger), "status": "not_translatable"}]
    assert out["written"] == 0


@pytest.mark.asyncio
async def test_asking_for_the_motifs_own_language_costs_nothing(repo_patch):
    m = _motif(original_language="ja")
    repo = _Repo(allowed=[m])
    out = await _run_job(repo_patch, repo, [m["id"]])
    assert out["results"][0]["status"] == "already_original"
    assert repo.writes == []


@pytest.mark.asyncio
async def test_a_fresh_existing_translation_is_not_re_charged(repo_patch):
    m = _motif()
    repo = _Repo(allowed=[m], state={(m["id"], "ja"): {"source": "machine", "stale": False}})
    out = await _run_job(repo_patch, repo, [m["id"]])
    assert out["results"][0]["status"] == "already_translated"
    assert repo.writes == []


@pytest.mark.asyncio
async def test_a_stale_translation_IS_re_translated(repo_patch):
    """The whole point of carrying `source_content_hash`: the user edited the motif, so
    the wording they paid for no longer describes it."""
    m = _motif()
    repo = _Repo(allowed=[m], state={(m["id"], "ja"): {"source": "machine", "stale": True}})
    out = await _run_job(repo_patch, repo, [m["id"]])
    assert out["results"][0]["status"] == "translated"
    assert len(repo.writes) == 1


@pytest.mark.asyncio
async def test_force_re_translates_a_fresh_one(repo_patch):
    m = _motif()
    repo = _Repo(allowed=[m], state={(m["id"], "ja"): {"source": "machine", "stale": False}})
    out = await _run_job(repo_patch, repo, [m["id"]], force=True)
    assert out["results"][0]["status"] == "translated"


@pytest.mark.asyncio
async def test_a_hand_written_translation_is_never_overwritten(repo_patch):
    """The 84 seeded Vietnamese motifs were written by a person. A user idly
    re-translating their library must not be able to machine-overwrite them — the same
    guard the seeder's upsert carries, applied a second time before spending a token."""
    m = _motif()
    repo = _Repo(allowed=[m], state={(m["id"], "ja"): {"source": "authored", "stale": True}})
    out = await _run_job(repo_patch, repo, [m["id"]])
    assert out["results"][0]["status"] == "authored_kept"
    assert repo.writes == []


@pytest.mark.asyncio
async def test_one_bad_motif_does_not_sink_the_batch(repo_patch):
    """The user paid for all of them."""
    good = _motif()
    bad = _motif(code="mystery.other", name="The Alibi That Holds Too Well")
    bad["id"] = uuid4()

    def respond(sent):
        if "Alibi" in sent.get("name", ""):
            raise RuntimeError("provider blew up")
        return {k: f"JA::{v}" for k, v in sent.items()}

    repo = _Repo(allowed=[good, bad])
    out = await _run_job(repo_patch, repo, [good["id"], bad["id"]], respond=respond)
    statuses = {r["motif_id"]: r["status"] for r in out["results"]}
    assert statuses[str(good["id"])] == "translated"
    assert statuses[str(bad["id"])] == "failed"
    assert out["written"] == 1


@pytest.mark.asyncio
async def test_the_written_hash_is_the_source_it_was_made_from(repo_patch):
    """If this drifted, the staleness signal would go on lying in the other direction —
    a translation flagged fresh that was never made from the current text."""
    from app.motif_i18n import source_hash
    m = _motif()
    repo = _Repo(allowed=[m])
    await _run_job(repo_patch, repo, [m["id"]])
    assert repo.writes[0][3] == source_hash(m)


# ── the envelope ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_an_unsupported_language_is_refused_before_any_work(repo_patch):
    repo = _Repo(allowed=[])
    repo_patch(repo)
    with pytest.raises(ValueError, match="unsupported target_language"):
        await mtr.run_translate_motifs(
            None, _LLM(lambda s: {}), user_id=str(uuid4()),
            input={"motif_ids": [str(uuid4())], "target_language": "auto",
                   "model_ref": "m-1"})


@pytest.mark.asyncio
async def test_a_missing_model_ref_fails_closed(repo_patch):
    """Never reach for a platform default: the point of this path is that the USER's
    model spends the USER's money."""
    repo_patch(_Repo(allowed=[]))
    with pytest.raises(ValueError, match="model_ref is required"):
        await mtr.run_translate_motifs(
            None, _LLM(lambda s: {}), user_id=str(uuid4()),
            input={"motif_ids": [str(uuid4())], "target_language": "ja"})


@pytest.mark.asyncio
async def test_the_batch_is_capped(repo_patch):
    """An unbounded batch is an unbounded bill, and it would make the confirm card's
    estimate meaningless."""
    ids = [uuid4() for _ in range(mtr.MAX_MOTIFS_PER_JOB + 10)]
    out = await _run_job(repo_patch, _Repo(allowed=[]), ids)
    assert out["requested"] == mtr.MAX_MOTIFS_PER_JOB


@pytest.mark.asyncio
async def test_cancelling_stops_the_spend_for_motifs_not_yet_started(repo_patch):
    """`call_json` already threads the cancel check into the in-flight request, which
    stops ONE call. A 50-motif batch is minutes of spending, so a user who cancels must
    also stop being charged for the motifs that have not begun. Everything already
    written stays written — a cancel is not a rollback."""
    a, b = _motif(), _motif(code="mystery.other", name="The Alibi")
    b["id"] = uuid4()
    repo = _Repo(allowed=[a, b])
    repo_patch(repo)

    seen = {"n": 0}

    async def cancel_check():
        seen["n"] += 1
        return seen["n"] > 1          # the first motif runs, then the user cancels

    out = await mtr.run_translate_motifs(
        None, _LLM(lambda sent: {k: f"JA::{v}" for k, v in sent.items()}),
        user_id=str(uuid4()),
        input={"motif_ids": [str(a["id"]), str(b["id"])], "target_language": "ja",
               "model_ref": "m-1"},
        cancel_check=cancel_check,
    )
    statuses = [r["status"] for r in out["results"]]
    assert statuses == ["translated", "cancelled"]
    assert out["written"] == 1, "work already paid for must not be discarded"


# ── the shared-tier book grant, re-checked at RUN time ─────────────────────
_BOOK = UUID("00000000-0000-0000-0000-0000000000b1")
@pytest.fixture
def grant_patch(monkeypatch):
    """Swap the worker's grant client for one whose verdict the test controls."""
    def _install(verdict):
        import app.engine.motif_translate as m

        async def _authorize(grant, book_id, caller, need):
            if verdict is not None:
                raise verdict
            return need
        monkeypatch.setattr(m, "get_grant_client", lambda: object())
        monkeypatch.setattr(m, "authorize_book", _authorize)
    return _install


@pytest.mark.asyncio
async def test_a_revoked_book_grant_stops_the_shared_tier_write(repo_patch, grant_patch):
    """`book_shared AND book_id = <signed payload>` proves the row belongs to that book,
    NOT that this caller may still write to it. A `translate_motif` job is
    server-retryable, so a sweeper can re-drive it long after the confirm that authorized
    it — and a grant revoked in between would otherwise let a former collaborator's job
    keep writing translations into the book."""
    from app.packer.pack import OwnershipError

    shared = _motif(code="mystery.shared")
    repo = _Repo(allowed=[shared])
    grant_patch(OwnershipError("grant revoked"))

    # The repo records what scope it was asked for — that is the observable effect.
    seen: dict = {}
    orig = repo.list_translatable

    async def _spy(caller, ids, *, book_id=None):
        seen["book_id"] = book_id
        return await orig(caller, ids, book_id=book_id)
    repo.list_translatable = _spy

    out = await _run_job(repo_patch, repo, [shared["id"]], book_id=str(_BOOK))
    assert seen["book_id"] is None, "the shared-tier arm survived a revoked grant"
    assert out["results"][0]["status"] in {"translated", "not_translatable"}


@pytest.mark.asyncio
async def test_a_live_grant_keeps_the_shared_tier_arm(repo_patch, grant_patch):
    shared = _motif(code="mystery.shared")
    repo = _Repo(allowed=[shared])
    grant_patch(None)

    seen: dict = {}
    orig = repo.list_translatable

    async def _spy(caller, ids, *, book_id=None):
        seen["book_id"] = book_id
        return await orig(caller, ids, book_id=book_id)
    repo.list_translatable = _spy

    await _run_job(repo_patch, repo, [shared["id"]], book_id=str(_BOOK))
    assert seen["book_id"] == _BOOK


@pytest.mark.asyncio
async def test_a_grant_service_outage_narrows_the_batch_it_does_not_fail_it(repo_patch, grant_patch):
    """`authorize_book` resolves an outage to NONE → OwnershipError (fail-closed). The
    caller's OWN motifs need no grant, so an outage must drop only the shared arm — a
    user's own library staying translatable is the whole point of the fail-closed shape."""
    from app.packer.pack import OwnershipError

    mine = _motif()
    repo = _Repo(allowed=[mine])
    grant_patch(OwnershipError("book-service unreachable"))
    out = await _run_job(repo_patch, repo, [mine["id"]], book_id=str(_BOOK))
    assert out["results"][0]["status"] == "translated"
    assert out["written"] == 1
