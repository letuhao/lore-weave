"""Unit tests for the wiki build_inputs fingerprint (wiki-llm M5 / §C7)."""
from __future__ import annotations

from app.wiki.context import ContextSource, EntityBrief, GenerationContext
from app.wiki.fingerprint import compute_build_inputs, stable_hash
from app.wiki.ir import Source


def _ctx(short_desc="封神主角") -> GenerationContext:
    brief = EntityBrief(entity_id="e1", name="姜子牙", kind="character",
                        aliases=["飞熊"], short_description=short_desc)
    items = [
        ContextSource(source=Source(cite_id="G1", kind="glossary", snippet="x"), text="封神主角"),
        ContextSource(source=Source(cite_id="K1", kind="kg", snippet="y"), text="姜子牙 — 师傅 → 元始天尊"),
        ContextSource(source=Source(cite_id="P1", kind="passage", chapter_id="ch1",
                                    block_index=2, chapter_sort_order=3, snippet="z"),
                      text="奉命下山伐纣"),
    ]
    return GenerationContext(brief=brief, items=items)


_PARAMS = dict(model_ref="m1", prompt_version="p1", pipeline_version="v1",
               retrieval_params={"mode": "hybrid", "k": 8})


def test_stable_hash_deterministic_and_order_independent():
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})
    assert stable_hash([1, 2, 3]) == stable_hash([1, 2, 3])
    assert stable_hash("x") != stable_hash("y")


def test_build_inputs_has_all_fields():
    bi = compute_build_inputs(context=_ctx(), **_PARAMS)
    for key in ("schema_version", "entity_id", "entity_content_hash", "attr_set_hash",
                "kg_neighborhood_hash", "cited_blocks", "retrieval_params_hash",
                "model_ref", "prompt_version", "pipeline_version"):
        assert key in bi
    assert bi["entity_id"] == "e1"
    assert bi["model_ref"] == "m1"


def test_cited_blocks_from_passages_only():
    bi = compute_build_inputs(context=_ctx(), **_PARAMS)
    assert len(bi["cited_blocks"]) == 1  # only the one passage
    cb = bi["cited_blocks"][0]
    assert cb["chapter_id"] == "ch1" and cb["block_index"] == 2
    assert "content_hash" in cb


def test_content_edit_changes_entity_hash():
    bi1 = compute_build_inputs(context=_ctx(short_desc="A"), **_PARAMS)
    bi2 = compute_build_inputs(context=_ctx(short_desc="B"), **_PARAMS)
    # short_description is an attr → attr_set_hash changes; entity name/kind same.
    assert bi1["attr_set_hash"] != bi2["attr_set_hash"]
    assert bi1["entity_content_hash"] == bi2["entity_content_hash"]


def test_retrieval_params_hash_changes_with_params():
    bi1 = compute_build_inputs(context=_ctx(), **{**_PARAMS, "retrieval_params": {"k": 8}})
    bi2 = compute_build_inputs(context=_ctx(), **{**_PARAMS, "retrieval_params": {"k": 20}})
    assert bi1["retrieval_params_hash"] != bi2["retrieval_params_hash"]
