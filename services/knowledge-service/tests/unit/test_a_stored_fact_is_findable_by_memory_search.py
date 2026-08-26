"""A fact the platform ACCEPTED must be reachable by the tool built to find it.

    memory_remember  -> {"remembered": true, "fact_id": "...", "confidence": 0.7}
    memory_search    -> {"hits": [], "count": 0, "degraded": {"semantic": "not_indexed"}}

🔴 THE MARKER IS NOT THE CAUSE, and reading it as one cost a cycle. `degraded: not_indexed` is
true and irrelevant: `_handle_memory_search` had exactly two legs — a manuscript leg over the
book's CHAPTERS and a passage leg over `:Passage` nodes — and `memory_remember` writes a `:Fact`.
A Fact is never a Passage, so no amount of indexing would have found one.

CONTROLLED ON ONE PROJECT so the index state was identical for both probes (2026-08-26):

    a nonce in a CHAPTER  -> FOUND,  count 1, degraded {"semantic": "not_indexed"}
    a nonce in a FACT     -> MISSED, count 0, degraded {"semantic": "not_indexed"}

Same project, same marker, opposite outcomes. The legs work; Facts were not among them.

WHY IT MATTERS BEYOND THE EMPTY LIST: memory_remember's `fact_id` is gone by the next turn, so
SEARCH is the only route a later turn has to a stored fact. memory_forget handed the id directly
still works, which is what proves the STORE is sound and the retrieval path is not.
"""
from __future__ import annotations

import inspect
import pathlib
import re

import pytest

from app.db.neo4j_repos.facts import (
    Fact,
    query_tokens,
    rank_facts_by_overlap,
    search_facts_by_text,
)


def _fact(content: str, confidence: float = 0.7) -> Fact:
    return Fact(id=re.sub(r"\W", "", content)[:24] or "x", user_id="u", type="decision",
                content=content, canonical_content=content.lower(), confidence=confidence)


# The corpus the matcher study ran on: the real fact SHAPES plus hand-built near-misses — facts
# sharing exactly one content word with the query. Without the near-misses every candidate scored
# a meaningless precision of 1.00.
TRUE = [
    _fact("Mira Solene is secretly the Pale Regent's daughter."),
    _fact("Mira Solene is the last cartographer of the Obsidian Trench."),
]
NEAR = [
    _fact("Solene Harbour was renamed after the flood."),        # shares 'solene'
    _fact("The Pale Regent's army disbanded a decade ago."),     # shares 'pale', 'regent'
    _fact("Vane Street runs behind the cathedral."),
]


class TestTheMatcherWasChosenByMeasurementNotByTaste:
    @pytest.mark.parametrize("query", [
        "Mira Solene",
        "What do we know about Mira Solene?",
        "what has been established about Mira Solene",
    ])
    def test_a_question_finds_it_not_only_an_exact_phrase(self, query):
        """RECALL. A whole-query substring match scored 0.50 recall — it misses every question
        form, which is the shape `memory_search`'s own argument description promises ("What to
        search for, in natural language")."""
        got = [f.content for _, f in rank_facts_by_overlap(
            TRUE + NEAR, query_tokens(query), limit=10)]
        assert all(t.content in got for t in TRUE), f"{query!r} lost a true fact: {got}"

    def test_a_partial_name_collision_is_DROPPED(self):
        """PRECISION, and the case that killed the two obvious matchers. 'Solene Harbour' shares
        one content word with 'Mira Solene'. Any-token matching scored precision 0.71 on it, and an
        ABSOLUTE floor cannot help: 'Mira Solene' and 'Solene Harbour' both score exactly 0.5."""
        got = [f.content for _, f in rank_facts_by_overlap(
            TRUE + NEAR, query_tokens("Mira Solene"), limit=10)]
        assert not any("Harbour" in g for g in got), got
        assert len(got) == 2

    def test_the_floor_is_RELATIVE_to_the_best_hit(self):
        """The whole reason the previous test can pass. Half of the best score for THIS query —
        not a constant — because the question is not 'is this a good match' but 'is it good
        compared to the best thing this project has'."""
        src = inspect.getsource(rank_facts_by_overlap)
        assert "best / 2" in src and "max(s for s, _ in scored)" in src

    def test_an_unrelated_query_invents_NOTHING(self):
        """The property that matters most for a memory read: it may rank weakly, it must never
        return knowledge the project does not hold. Every candidate matcher passed this one."""
        for q in ("Thessaly Marchpane", "what do we know about dragons"):
            assert rank_facts_by_overlap(TRUE + NEAR, query_tokens(q), limit=10) == []

    def test_a_query_of_pure_function_words_matches_nothing(self):
        assert query_tokens("what do we know about") == []
        assert rank_facts_by_overlap(TRUE + NEAR, query_tokens("what do we know about"),
                                     limit=10) == []

    def test_CJK_survives_tokenisation(self):
        """A CONTAINS needs no tokenizer for CJK, which is why `passage_text_cjk_ft` exists as its
        own index — the substring path is if anything stronger there."""
        assert query_tokens("黒曜の谷") == ["黒曜の谷"]


class TestTheLegCannotBeBornDead:
    def test_the_confidence_floor_matches_what_memory_remember_WRITES(self):
        """🔴 THE ONE MISTAKE THAT WOULD HAVE SHIPPED A PRESENT-BUT-DEAD LEG. Every other reader in
        facts.py defaults to 0.8 (the L2 loader's floor). memory_remember writes at
        TOOL_FACT_CONFIDENCE = 0.7 — verified against a live write returning
        `{"remembered": true, "confidence": 0.7}` — so an 0.8 floor would exclude exactly the facts
        this leg exists to find, and the symptom would be an empty result: the defect itself,
        reproduced by its own fix."""
        from app.tools.executor import TOOL_FACT_CONFIDENCE

        assert TOOL_FACT_CONFIDENCE == 0.7
        sig = inspect.signature(search_facts_by_text)
        assert sig.parameters["min_confidence"].default == 0.7, (
            "the reader's own default must not be the 0.8 its siblings use")
        call = inspect.getsource(_handler_source())
        assert "min_confidence=TOOL_FACT_CONFIDENCE" in call, (
            "the CALL SITE must pass the tool-fact floor, not rely on any default")

    def test_the_leg_is_wired_into_the_search_handler(self):
        src = inspect.getsource(_handler_source())
        assert "search_facts_by_text" in src, "memory_search does not call the fact reader"
        assert 'args.source_type in (None, "fact")' in src
        assert '"source_type": "fact"' in src

    def test_a_fact_leg_failure_cannot_take_the_other_legs_down(self):
        src = inspect.getsource(_handler_source())
        seg = src.split("search_facts_by_text", 1)[1]
        assert "except Exception" in seg and "fact_hits = []" in seg

    def test_facts_get_RESERVED_slots_rather_than_being_appended(self):
        """The manuscript leg runs first and can fill `limit` on its own, and the truncation is
        positional — so appending would find the fact and silently cut it on exactly the projects
        with the most chapter text. 'Reachable unless the book is big' is not the invariant."""
        src = inspect.getsource(_handler_source())
        assert "reserved = max(1, args.limit // 5)" in src
        assert "items[:keep_other] + fact_items" in src

    def test_a_project_scope_is_REQUIRED(self):
        """D16 — a memory read never spans a user's projects, the same posture recall_facts takes.
        A missing project_id returns empty rather than searching everything."""
        src = inspect.getsource(search_facts_by_text)
        assert "if not project_id:" in src and "return []" in src


class TestTheDECLAREDSurfaceMatchesWhatItNowDoes:
    def test_the_args_model_admits_the_new_source(self):
        from app.tools.definitions import MemorySearchArgs

        assert MemorySearchArgs(query="x", source_type="fact").source_type == "fact"

    def test_the_tool_DESCRIPTION_names_the_source_it_searches(self):
        """The description listed chapter text, chat turns and glossary entries. It searched three
        stores and named three, so it was accurate — and a fact was reachable by neither the list
        nor the tool. Adding the leg without the sentence would leave a model no reason to try."""
        srv = pathlib.Path(
            inspect.getfile(__import__("app.mcp.server", fromlist=["x"]))).read_text(
            encoding="utf-8")
        i = srv.index('name="memory_search"')
        block = srv[i:i + 1400]
        assert "memory_remember" in block, (
            "memory_search's description does not say it searches saved facts")


class TestAFindTheCallerCanACTOnFINDIsNotEnough:
    """🔴 THE FIRST HALF OF THIS FIX SHIPPED WITHOUT THIS AND WAS HALF A FIX.

    The fact leg made a stored fact findable. `memory_forget` REQUIRES a fact_id and its own
    description says "only use a fact_id you have seen in an earlier tool result" — and measured
    right after that leg shipped, a hit carried {score, snippet, source_type, text} at BOTH detail
    levels and no id. So a later turn could FIND a fact it still could not forget, which is the
    whole chain: memory_remember's id is gone by the next turn, so search is the only route.

    Same lesson as composition_reference_list, which projects the row's `id` AS `reference_id`
    because its consumer spells it that way: a reader must hand over the id its CONSUMER needs, or
    the chain ends one call short and every part of it looks like it worked.
    """

    def test_the_fact_hit_carries_the_id_memory_forget_requires(self):
        src = inspect.getsource(_handler_source())
        assert '"fact_id": fact.id' in src, "a fact hit does not carry its id"

    def test_the_id_SURVIVES_the_summary_projection(self):
        """`detail="summary"` keeps only MEMORY_SEARCH_REF_FIELDS, and summary is the DEFAULT. An
        id emitted by the handler and dropped by the contract is an id no caller ever sees."""
        from app.tools.executor import MEMORY_SEARCH_REF_FIELDS

        assert "fact_id" in MEMORY_SEARCH_REF_FIELDS

    def test_the_other_hit_types_are_UNTOUCHED(self):
        """Only fact hits carry the key. The contract keeps a ref field `if k in it`, so a
        chapter/chat/glossary hit gains no empty column and no shape change."""
        from loreweave_mcp import apply_response_contract
        from app.tools.executor import MEMORY_SEARCH_REF_FIELDS

        chapter = {"snippet": "s", "text": "t", "source_type": "chapter", "score": 0.5}
        got, _ = apply_response_contract([chapter], ref_fields=MEMORY_SEARCH_REF_FIELDS,
                                         detail="summary")
        assert "fact_id" not in got[0]
        assert sorted(got[0]) == ["score", "snippet", "source_type"]

    def test_the_emitter_is_DECLARED_so_the_refusal_can_name_it(self):
        """The map is what the runtime reads: `_missing_args_message` names an emitter from it and
        R1 answerability is transitive over it. Until memory_search could both reach a fact AND
        return its id, this entry would have been a claim about a tool that could not supply."""
        import json

        reg = json.loads((_repo_root() / "contracts" / "agent-runtime-tool-contracts.json")
                         .read_text(encoding="utf-8"))
        assert reg["argument_emitters"]["memory_forget"]["fact_id"] == "memory_search"

    def test_memory_forget_DESCRIBES_where_the_id_comes_from(self):
        srv = pathlib.Path(
            inspect.getfile(__import__("app.mcp.server", fromlist=["x"]))).read_text(
            encoding="utf-8")
        i = srv.index('name="memory_forget"')
        assert "memory_search" in srv[i:i + 900], (
            "memory_forget still says 'an earlier tool result' without naming which tool")


def _repo_root():
    here = pathlib.Path(__file__).resolve()
    for p in here.parents:
        if (p / "contracts").is_dir():
            return p
    raise RuntimeError("repo root not found")


def _handler_source():
    from app.tools.executor import _handle_memory_search

    return _handle_memory_search
