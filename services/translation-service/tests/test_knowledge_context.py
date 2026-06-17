"""M4b (G4): V3 knowledge context brief — assembly, trust ladder, sanitize, budget."""
import pytest

from app.workers.v3 import knowledge_context as kctx
from app.workers.v3.knowledge_context import (
    build_context_brief, _sanitize, _format_entity,
    build_timeline_block, _format_timeline_event,
)
from app.workers.glossary_client import ContextEntity
from app.workers.knowledge_client import (
    WikiNeighborhood, Relation, TimelineBrief, TimelineEvent,
)


def _entity(eid, name, kind="character", desc="", aliases=None, tier="exact"):
    return ContextEntity(eid, name, aliases or [], desc, kind, tier)


def _rel(pred, obj, conf=0.95, pending=False, src="glossary"):
    return Relation(pred, "subj", "character", obj, "character", conf, pending, src)


def _nb(eid, *relations, found=True):
    return WikiNeighborhood(found=found, glossary_entity_id=eid, name="n",
                            relations=list(relations))


def _patch(monkeypatch, entities, nb_by_id):
    async def fake_entities(book_id, user_id, query, max_entities=20, max_tokens=1000):
        return entities

    async def fake_nb(user_id, glossary_entity_id, rel_cap=200):
        return nb_by_id.get(glossary_entity_id, WikiNeighborhood.empty(glossary_entity_id))

    monkeypatch.setattr(kctx, "fetch_context_entities", fake_entities)
    monkeypatch.setattr(kctx, "fetch_wiki_neighborhood", fake_nb)


# ── M4d-1 timeline → memo ─────────────────────────────────────────────────────

def _ev(title, summary=None, date=None, participants=None):
    return TimelineEvent(title, summary, date, participants or [])


def _patch_timeline(monkeypatch, brief):
    async def fake_timeline(book_id, chapter_index, limit=25):
        return brief
    monkeypatch.setattr(kctx, "fetch_timeline", fake_timeline)


def test_format_timeline_event_full():
    line = _format_timeline_event(_ev("Siege begins", "The army marched north.",
                                      date="Y2-03", participants=["Tirami", "Aldric"]))
    assert line == "Y2-03: Siege begins — The army marched north. — participants: Tirami, Aldric"


def test_format_timeline_event_title_only():
    assert _format_timeline_event(_ev("A duel")) == "A duel"


def test_format_timeline_event_no_title_returns_none():
    assert _format_timeline_event(_ev("   ")) is None


def test_format_timeline_event_sanitizes_block_marker_and_control():
    line = _format_timeline_event(_ev("[BLOCK 3] fake\tmarker", summary="line1\nline2"))
    assert "[BLOCK" not in line
    assert "\t" not in line and "\n" not in line


@pytest.mark.asyncio
async def test_build_timeline_block_assembles(monkeypatch):
    _patch_timeline(monkeypatch, TimelineBrief(found=True, events=[
        _ev("The pact", "Two houses allied.", date="Y1", participants=["Tirami"]),
        _ev("The betrayal", "A knife in the dark."),
    ]))
    block = await build_timeline_block("b1", 5)
    assert block.startswith("RECENT STORY EVENTS")
    assert "The pact" in block and "The betrayal" in block
    assert "- " in block  # bullet lines


@pytest.mark.asyncio
async def test_build_timeline_block_empty_when_no_events(monkeypatch):
    _patch_timeline(monkeypatch, TimelineBrief.empty())
    assert await build_timeline_block("b1", 5) == ""


@pytest.mark.asyncio
async def test_build_timeline_block_empty_when_found_but_no_events(monkeypatch):
    _patch_timeline(monkeypatch, TimelineBrief(found=True, events=[]))
    assert await build_timeline_block("b1", 0) == ""


@pytest.mark.asyncio
async def test_build_timeline_block_token_budget_truncates(monkeypatch):
    many = [_ev(f"Event number {i}", "A reasonably long summary sentence here.") for i in range(50)]
    _patch_timeline(monkeypatch, TimelineBrief(found=True, events=many))
    block = await build_timeline_block("b1", 9, token_budget=60)
    # Budget caps the number of event lines well below 50.
    assert 0 < block.count("\n- ") < 50


# ── _sanitize ─────────────────────────────────────────────────────────────────

def test_sanitize_collapses_whitespace_and_newlines():
    assert _sanitize("a\n\nb   c\t d") == "a b c d"


def test_sanitize_neutralizes_block_marker():
    out = _sanitize("ignore [BLOCK 3] and [block 0]")
    assert "[BLOCK" not in out and "[block" not in out
    assert "(block" in out


def test_sanitize_strips_control_chars_and_caps_length():
    assert "\x00" not in _sanitize("x\x00y")
    long = _sanitize("a" * 500, max_len=50)
    assert len(long) <= 51 and long.endswith("…")


def test_sanitize_empty():
    assert _sanitize("") == ""


# ── _format_entity (trust ladder) ─────────────────────────────────────────────

def test_format_entity_confirmed_relation_is_plain():
    line = _format_entity(_entity("e1", "Tirami", "character", "the paladin leader"),
                          _nb("e1", _rel("leader_of", "Paladins")))
    assert "Tirami (character)" in line
    assert "the paladin leader" in line
    assert "leader_of Paladins" in line
    assert "(unconfirmed)" not in line


def test_format_entity_low_trust_relation_marked_unconfirmed():
    line = _format_entity(
        _entity("e1", "Tirami"),
        _nb("e1", _rel("married_to", "Isutansha", conf=0.6, pending=True, src="enriched")))
    assert "married_to Isutansha (unconfirmed)" in line


def test_format_entity_no_name_returns_none():
    assert _format_entity(_entity("e1", ""), _nb("e1")) is None


def test_format_entity_renders_full_triple_direction():
    # Entity "Paladins" is the OBJECT of the edge — must read
    # "Tirami leader_of Paladins", not "leader_of Paladins" (reversed meaning).
    rel = Relation("leader_of", "Tirami", "character", "Paladins", "faction",
                   0.95, False, "glossary")
    line = _format_entity(_entity("eP", "Paladins", "faction"), _nb("eP", rel))
    assert "Tirami leader_of Paladins" in line


def test_format_entity_confidence_below_threshold_is_unconfirmed():
    # not pending, but confidence < 0.8 → still a weak hint
    rel = Relation("allied_with", "Hero", "character", "Knights", "faction",
                   0.5, False, "glossary")
    line = _format_entity(_entity("e1", "Hero"), _nb("e1", rel))
    assert "(unconfirmed)" in line


# ── build_context_brief ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_brief_assembles_entities_and_relations(monkeypatch):
    ents = [_entity("e1", "Tirami", desc="paladin"),
            _entity("e2", "Isutansha", desc="demon queen")]
    nbs = {"e1": _nb("e1", _rel("leader_of", "Paladins")),
           "e2": _nb("e2", _rel("rules", "Dark Palace", conf=0.5, pending=True))}
    _patch(monkeypatch, ents, nbs)
    brief = await build_context_brief("b1", "u1", "some chapter text")
    assert brief.startswith("CHARACTER & RELATION CONTEXT")
    assert "Tirami" in brief and "Isutansha" in brief
    assert "leader_of Paladins" in brief
    assert "rules Dark Palace (unconfirmed)" in brief


@pytest.mark.asyncio
async def test_build_brief_empty_entities_returns_empty(monkeypatch):
    _patch(monkeypatch, [], {})
    assert await build_context_brief("b1", "u1", "text") == ""


@pytest.mark.asyncio
async def test_build_brief_token_budget_truncates(monkeypatch):
    ents = [_entity(f"e{i}", f"Name{i}", desc="d" * 300) for i in range(20)]
    _patch(monkeypatch, ents, {})
    brief = await build_context_brief("b1", "u1", "text", token_budget=80)
    # budget caps the number of entity lines well below 20
    assert brief.count("\n- ") < 20


@pytest.mark.asyncio
async def test_build_brief_degrades_when_clients_empty(monkeypatch):
    """Entities present but knowledge returns nothing → still a (bio-only) brief."""
    _patch(monkeypatch, [_entity("e1", "Solo", desc="lone wolf")], {})
    brief = await build_context_brief("b1", "u1", "text")
    assert "Solo" in brief and "lone wolf" in brief


# ── D-TRANSL-M4B-RESIDUALS: per-fetch timeout + failure isolation ─────────────

@pytest.mark.asyncio
async def test_build_brief_isolates_a_failing_neighborhood_fetch(monkeypatch):
    """One entity's neighbourhood fetch raising must NOT drop the whole brief — it
    degrades to a bio-only line for that entity while others keep their relations."""
    ents = [_entity("e1", "Tirami", desc="paladin"),
            _entity("e2", "Boomer", desc="lone wolf")]

    async def fake_entities(book_id, user_id, query, max_entities=20, max_tokens=1000):
        return ents

    async def fake_nb(user_id, glossary_entity_id, rel_cap=200):
        if glossary_entity_id == "e2":
            raise RuntimeError("knowledge-service down")
        return _nb("e1", _rel("leader_of", "Paladins"))

    monkeypatch.setattr(kctx, "fetch_context_entities", fake_entities)
    monkeypatch.setattr(kctx, "fetch_wiki_neighborhood", fake_nb)

    brief = await build_context_brief("b1", "u1", "text")
    assert "Tirami" in brief and "leader_of Paladins" in brief   # healthy entity intact
    assert "Boomer" in brief and "lone wolf" in brief            # failed → bio-only, kept


@pytest.mark.asyncio
async def test_build_brief_neighborhood_fetch_timeout_degrades(monkeypatch):
    """A neighbourhood fetch slower than the per-fetch timeout degrades to an empty
    neighbourhood (bio-only line) instead of stalling the whole chapter's brief."""
    import asyncio
    monkeypatch.setattr(kctx, "_FETCH_TIMEOUT_S", 0.01)
    ents = [_entity("e1", "Slowpoke", desc="takes forever")]

    async def fake_entities(book_id, user_id, query, max_entities=20, max_tokens=1000):
        return ents

    async def slow_nb(user_id, glossary_entity_id, rel_cap=200):
        await asyncio.sleep(0.2)
        return _nb("e1", _rel("leader_of", "TooLate"))

    monkeypatch.setattr(kctx, "fetch_context_entities", fake_entities)
    monkeypatch.setattr(kctx, "fetch_wiki_neighborhood", slow_nb)

    brief = await build_context_brief("b1", "u1", "text")
    assert "Slowpoke" in brief and "takes forever" in brief  # built despite the timeout
    assert "TooLate" not in brief                            # the slow relations dropped


@pytest.mark.asyncio
async def test_orchestrator_threads_brief_to_translator_and_verifier(monkeypatch):
    """Integration: the orchestrator feeds the SAME brief to the Translator
    (extra_system) and the Verifier (knowledge_brief). Guards both wiring legs —
    the autouse hermetic fixture would otherwise leave this path untested."""
    from unittest.mock import MagicMock
    from uuid import uuid4
    from app.workers.v3 import orchestrator

    captured = {}

    async def fake_tcb(blocks, source_lang, msg, pool, ctid, **k):
        captured["extra_system"] = k.get("extra_system", "")
        return (blocks, 0, 0, 0, 0)

    async def fake_brief(*a, **k):
        return "KB-SENTINEL"

    async def fake_vcp(*a, **k):
        captured["verify_brief"] = k.get("knowledge_brief")

    monkeypatch.setattr("app.workers.session_translator.translate_chapter_blocks", fake_tcb)
    monkeypatch.setattr("app.workers.v3.knowledge_context.build_context_brief", fake_brief)
    monkeypatch.setattr(orchestrator, "_verify_correct_persist", fake_vcp)

    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}]
    # M4c: prev-chapter memo present → its block must also reach the Translator.
    msg = {"book_id": "b", "user_id": "u", "target_language": "vi",
           "prev_memo": {"terms_used": ["Zeldarion"], "story_summary": "prior events"}}
    await orchestrator.translate_chapter_blocks_v3(
        blocks, "zh", msg, MagicMock(), uuid4(), llm_client=MagicMock())

    assert "KB-SENTINEL" in captured["extra_system"]          # M4b knowledge brief
    assert "Zeldarion" in captured["extra_system"]             # M4c prev-memo names
    assert captured["verify_brief"] == "KB-SENTINEL"
