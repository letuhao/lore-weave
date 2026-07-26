"""W9 — motif_deconstruct orchestration + §12.6 abstraction post-check (fakes only).

Proves, with an injected fake LLM + fake repos (no DB, no real gateway):
  - the deconstruct chunks → maps → reduces → persists an arc_template (source='imported',
    status='draft') + member motifs (source='imported', imported_derived=True);
  - the §12.6 abstraction POST-CHECK SCRUBS near-verbatim source prose so a verbatim
    passage does NOT survive into a motif's beats/examples (the load-bearing copyright test);
  - the handler fails closed on an empty model_ref (provider-gateway invariant).
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.config import settings
from app.db.models import ArcTemplate, Motif
from app.engine import motif_deconstruct as md

USER = str(uuid.uuid4())

# A distinctive long source passage (the "verbatim" the deconstruct must never echo).
VERBATIN = (
    "the crimson lotus blade descended through the shattered moonlight as elder "
    "fang whispered the forbidden cultivation art to his trembling disciple beneath "
    "the ancient withered pine of the eastern cloud sect at the hour of the rat"
)
SOURCE_TEXT = "Chapter 1. " + VERBATIN + ". And then more story happened afterwards."


class _FakeJob:
    def __init__(self, content):
        self.status = "completed"
        self.result = {"messages": [{"content": content}]}


class _FakeLLM:
    """Returns one canned deconstruct frame per call (records the messages it saw)."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.calls: list[dict] = []

    async def submit_and_wait(self, *, user_id, operation, model_source, model_ref,
                              input, job_meta=None, **kw):
        self.calls.append({"model_source": model_source, "model_ref": model_ref,
                           "operation": operation, "input": input})
        return _FakeJob(self._frames.pop(0) if self._frames else "{}")

    async def resolve_context_length(self, model_source, model_ref):
        return None  # unresolved in tests — the SDK's flat default applies


class _FakeArcRepo:
    def __init__(self):
        self.created: list[dict] = []

    async def create(self, user_id, args, *, source="authored", status="active",
                     imported_derived=False):
        self.created.append({"args": args, "source": source, "status": status,
                             "imported_derived": imported_derived})
        return ArcTemplate(id=uuid.uuid4(), owner_user_id=user_id, code=args.code,
                           name=args.name, source=source, status=status,
                           imported_derived=imported_derived)


class _FakeMotifRepo:
    def __init__(self):
        self.created: list[dict] = []

    async def create(self, user_id, args, *, source="authored",
                     imported_derived=False, status="active"):
        self.created.append({"args": args, "source": source,
                             "imported_derived": imported_derived, "status": status})
        return Motif(id=uuid.uuid4(), owner_user_id=user_id, code=args.code,
                     name=args.name, source=source, imported_derived=imported_derived,
                     status=status)


def _frame(*, beat_label, summary="an abstract motif", example=None):
    """One deconstruct frame with a single motif whose beat carries `beat_label`."""
    motif = {
        "code": "imported.motif-a", "name": "Abstract Motif", "kind": "sequence",
        "summary": summary, "thread": "combat", "tension_target": 4,
        "roles": [{"key": "protagonist", "actant": "subject", "label": "the hero"}],
        "beats": [{"key": "b1", "label": beat_label, "intent": "advance", "order": 0}],
        "preconditions": ["the hero is isolated"], "effects": ["the hero gains power"],
    }
    if example is not None:
        motif["examples"] = [{"text": example}]
    return json.dumps({
        "threads": [{"key": "combat", "label": "Combat"}],
        "roster": [{"key": "protagonist", "actant": "subject", "label": "hero"}],
        "motifs": [motif],
        "placements": [{"motif_code": "imported.motif-a", "thread": "combat",
                        "span_start": 1, "span_end": 5, "ord": 0}],
        "pacing": [{"chapter": 1, "tension": 4}],
    })


# ── happy path: persists an imported draft arc + imported_derived motifs ───────────────
async def test_deconstruct_persists_imported_draft_arc_and_motifs():
    llm = _FakeLLM([_frame(beat_label="isolation by disaster")])
    arc_repo, motif_repo = _FakeArcRepo(), _FakeMotifRepo()
    result = await md.deconstruct_reference(
        llm=llm, arc_repo=arc_repo, motif_repo=motif_repo,
        user_id=USER, source_title="Admired Work", source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref",
    )
    # arc persisted as an imported DRAFT, tainted (B-3 — the publish-strip trigger fires).
    assert len(arc_repo.created) == 1
    assert arc_repo.created[0]["source"] == "imported"
    assert arc_repo.created[0]["status"] == "draft"
    assert arc_repo.created[0]["imported_derived"] is True
    # member motif persisted as imported + imported_derived (B-3 taint at birth).
    assert len(motif_repo.created) == 1
    assert motif_repo.created[0]["source"] == "imported"
    assert motif_repo.created[0]["imported_derived"] is True
    # result dict shape for the poll.
    assert result["arc_template_id"]
    assert len(result["motif_ids"]) == 1
    assert "abstraction_check" in result


# ── THE §12.6 load-bearing test: a near-verbatim source beat does NOT survive ──────────
async def test_verbatim_source_beat_is_scrubbed_out_of_motif():
    # the model "leaks" the source passage verbatim into a beat label — the post-check
    # MUST strip it so no source prose survives into the persisted motif.
    llm = _FakeLLM([_frame(beat_label=VERBATIN, summary=VERBATIN,
                           example=VERBATIN)])
    arc_repo, motif_repo = _FakeArcRepo(), _FakeMotifRepo()
    result = await md.deconstruct_reference(
        llm=llm, arc_repo=arc_repo, motif_repo=motif_repo,
        user_id=USER, source_title="Admired Work", source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref",
    )
    args = motif_repo.created[0]["args"]
    # the verbatim passage is gone from the beat label, the summary, AND the examples.
    persisted_blob = json.dumps([b.model_dump() for b in args.beats]) + (args.summary or "")
    persisted_blob += json.dumps(args.examples)
    assert VERBATIN not in persisted_blob
    # the copied example was DROPPED entirely (an imported example must be synthetic).
    assert args.examples == []
    # the scrub was actually recorded (not a vacuous pass).
    assert result["abstraction_check"]["scrubbed_fields"] >= 1


async def test_verbatim_scrubbed_from_ALL_persisted_motif_and_arc_fields():
    """HIGH-1 (/review-impl): the scrub must cover EVERY persisted free-text field, not
    just beats/summary/examples. A model leaking the source passage into motif name /
    role label / precondition / effect, or into an arc thread label / roster label / the
    arc name, must NOT survive to the persisted args — the motif publish-strip trigger
    only strips examples+source_ref, and arc_template has NO trigger at all, so the scrub
    is the sole guard for these fields on a publish."""
    frame = json.dumps({
        "threads": [{"key": "combat", "label": VERBATIN}],
        "roster": [{"key": "protagonist", "actant": "subject", "label": VERBATIN}],
        "motifs": [{
            "code": "imported.motif-a", "name": VERBATIN, "kind": "sequence",
            "summary": "abstract", "thread": "combat", "tension_target": 4,
            "roles": [{"key": "protagonist", "actant": "subject", "label": VERBATIN}],
            "beats": [{"key": "b1", "label": "ok", "intent": "advance", "order": 0}],
            "preconditions": [VERBATIN], "effects": [VERBATIN],
        }],
        "placements": [{"motif_code": "imported.motif-a", "thread": "combat",
                        "span_start": 1, "span_end": 5, "ord": 0}],
        "pacing": [],
    })
    arc_repo, motif_repo = _FakeArcRepo(), _FakeMotifRepo()
    await md.deconstruct_reference(
        llm=_FakeLLM([frame]), arc_repo=arc_repo, motif_repo=motif_repo,
        user_id=USER, source_title=VERBATIN, source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref",
    )
    motif_blob = json.dumps(motif_repo.created[0]["args"].model_dump(mode="json"))
    assert VERBATIN not in motif_blob   # name/roles.label/preconditions/effects all scrubbed
    arc_blob = json.dumps(arc_repo.created[0]["args"].model_dump(mode="json"))
    assert VERBATIN not in arc_blob     # thread/roster labels scrubbed; arc name → "Imported Arc"
    assert arc_repo.created[0]["args"].name == "Imported Arc"


async def test_imported_motif_and_arc_carry_the_request_language():
    """M3 (/review-impl): the `language` axis (R1.1.3) threads from the envelope through
    to BOTH the persisted arc_template AND every member motif — tagging an imported zh
    work 'en' would be a dedup/embed re-key migration later."""
    arc_repo, motif_repo = _FakeArcRepo(), _FakeMotifRepo()
    result = await md.deconstruct_reference(
        llm=_FakeLLM([_frame(beat_label="isolation by disaster")]),
        arc_repo=arc_repo, motif_repo=motif_repo,
        user_id=USER, source_title="Work", source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref", language="zh",
    )
    assert result["language"] == "zh"
    assert motif_repo.created[0]["args"].language == "zh"
    assert arc_repo.created[0]["args"].language == "zh"


def test_scrub_verbatim_unit_drops_copied_example_and_blanks_beat():
    motifs = [{
        "summary": VERBATIN,
        "beats": [{"key": "b", "label": VERBATIN, "intent": "x"}],
        "examples": [{"text": VERBATIN}, {"text": "an original synthetic line"}],
    }]
    out, n = md.scrub_verbatim(motifs, source_text=SOURCE_TEXT)
    assert out[0]["summary"] == ""
    assert out[0]["beats"][0]["label"] == ""
    # the copied example dropped; the synthetic one kept.
    assert {"text": VERBATIN} not in out[0]["examples"]
    assert {"text": "an original synthetic line"} in out[0]["examples"]
    assert n >= 2


def test_scrub_verbatim_keeps_short_generic_beat_labels():
    # a short generic abstract label shares no long source shingle → survives untouched.
    motifs = [{"summary": "isolation by disaster",
               "beats": [{"key": "b", "label": "betrayal reveal", "intent": ""}],
               "examples": []}]
    out, n = md.scrub_verbatim(motifs, source_text=SOURCE_TEXT)
    assert out[0]["summary"] == "isolation by disaster"
    assert out[0]["beats"][0]["label"] == "betrayal reveal"
    assert n == 0


# ── provider-gateway invariant: fail closed on an empty model_ref ─────────────────────
async def test_deconstruct_fails_closed_on_empty_model_ref():
    llm = _FakeLLM([_frame(beat_label="x")])
    with pytest.raises(ValueError, match="model_ref"):
        await md.deconstruct_reference(
            llm=llm, arc_repo=_FakeArcRepo(), motif_repo=_FakeMotifRepo(),
            user_id=USER, source_title="T", source_content=SOURCE_TEXT,
            model_source="platform_model", model_ref="",
        )


async def test_deconstruct_raises_on_empty_content():
    llm = _FakeLLM([])
    with pytest.raises(ValueError, match="empty"):
        await md.deconstruct_reference(
            llm=llm, arc_repo=_FakeArcRepo(), motif_repo=_FakeMotifRepo(),
            user_id=USER, source_title="T", source_content="   ",
            model_source="platform_model", model_ref="m-ref",
        )


# ── chunking rides the P1 rail ────────────────────────────────────────────────────────
def test_chunk_content_splits_on_paragraphs():
    text = "\n\n".join(["para " + "x" * 50 for _ in range(10)])
    chunks = md.chunk_content(text, chunk_chars=120)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_content_empty_is_empty():
    assert md.chunk_content("   ", chunk_chars=100) == []


# ── the deconstruct prompt carries the §12.6 abstraction instruction ──────────────────
def test_prompt_instructs_abstraction_and_no_proper_nouns():
    system, user = md.build_deconstruct_messages(
        "some passage", arc_hint=None, use_web=False, total_chunks=1, chunk_index=0)
    low = system.lower()
    assert "role slot" in low or "role_slot" in low.replace(" ", "_")
    assert "proper noun" in low
    assert "no verbatim" in low or "no source" in low


# ── D-W9-WEBSEARCH — the public arc-convention augment ────────────────────────────────
from app.clients.web_search_client import WebSearchHit, WebSearchResult  # noqa: E402


class _FakeWebSearch:
    """Records the query it saw + returns a canned WebSearchResult (or raises)."""

    def __init__(self, result=None, *, raises=False):
        self._result = result
        self._raises = raises
        self.calls: list[dict] = []

    async def search(self, *, user_id, query, max_results=5):
        self.calls.append({"user_id": user_id, "query": query, "max_results": max_results})
        if self._raises:
            raise RuntimeError("web boom")
        return self._result


def test_build_web_query_uses_title_and_hint():
    assert md.build_web_query("", None) == ""
    q = md.build_web_query("Renegade Immortal", None)
    assert "Renegade Immortal" in q and "arc" in q.lower()
    q2 = md.build_web_query("Renegade Immortal", "revenge cultivation")
    assert "revenge cultivation" in q2


def test_format_web_context_joins_and_caps():
    res = WebSearchResult(
        answer="A revenge cultivation arc.",
        hits=[WebSearchHit(title="t1", url="https://x", snippet="the hero is cast out"),
              WebSearchHit(title="t2", url="https://y", snippet="he returns stronger")],
    )
    ctx = md.format_web_context(res)
    assert "revenge cultivation arc" in ctx
    assert "cast out" in ctx and "returns stronger" in ctx
    assert len(md.format_web_context(res, cap=10)) == 10


async def test_use_web_injects_neutralized_context_on_chunk0():
    res = WebSearchResult(
        answer="public arc summary",
        hits=[WebSearchHit(title="wiki", url="https://w", snippet="isolation then return")],
    )
    web = _FakeWebSearch(res)
    llm = _FakeLLM([_frame(beat_label="isolation by disaster")])
    result = await md.deconstruct_reference(
        llm=llm, arc_repo=_FakeArcRepo(), motif_repo=_FakeMotifRepo(),
        user_id=USER, source_title="Admired Work", source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref",
        use_web=True, web_search=web,
    )
    # the search ran once for the work's arc conventions.
    assert len(web.calls) == 1 and "Admired Work" in web.calls[0]["query"]
    # chunk-0's user message carries the PUBLIC REFERENCE block (untrusted DATA).
    chunk0_user = llm.calls[0]["input"]["messages"][1]["content"]
    assert "PUBLIC REFERENCE" in chunk0_user and "isolation then return" in chunk0_user
    assert result["websearch_status"] == "ok:1"


async def test_use_web_not_configured_degrades_but_deconstruct_succeeds():
    web = _FakeWebSearch(WebSearchResult(error="not_configured"))
    llm = _FakeLLM([_frame(beat_label="isolation by disaster")])
    result = await md.deconstruct_reference(
        llm=llm, arc_repo=_FakeArcRepo(), motif_repo=_FakeMotifRepo(),
        user_id=USER, source_title="Work", source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref",
        use_web=True, web_search=web,
    )
    # NO reference block leaked into the prompt; the job still produced motifs.
    assert "PUBLIC REFERENCE" not in llm.calls[0]["input"]["messages"][1]["content"]
    assert result["websearch_status"] == "not_configured"
    assert len(result["motif_ids"]) == 1


async def test_use_web_outage_never_fails_the_job():
    web = _FakeWebSearch(raises=True)
    result = await md.deconstruct_reference(
        llm=_FakeLLM([_frame(beat_label="isolation by disaster")]),
        arc_repo=_FakeArcRepo(), motif_repo=_FakeMotifRepo(),
        user_id=USER, source_title="Work", source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref",
        use_web=True, web_search=web,
    )
    assert result["websearch_status"] == "unavailable"
    assert len(result["motif_ids"]) == 1


async def test_no_web_does_not_call_search():
    web = _FakeWebSearch(WebSearchResult())
    result = await md.deconstruct_reference(
        llm=_FakeLLM([_frame(beat_label="isolation by disaster")]),
        arc_repo=_FakeArcRepo(), motif_repo=_FakeMotifRepo(),
        user_id=USER, source_title="Work", source_content=SOURCE_TEXT,
        model_source="platform_model", model_ref="m-ref",
        use_web=False, web_search=web,
    )
    assert web.calls == []
    assert result["websearch_status"] == "off"
