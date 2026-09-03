"""The turn's ambient book_id, passed as an entity_id, is not an id — it is the wrong one.

🔴 PROVEN BY IDENTITY, 2026-08-23, kg_propose_edge at K=5. In three of three inspected runs the
run's own book_id EQUALS the value the tool refused, passed as BOTH endpoints:

    rep0 book_id 01a02c60-696c-724e-bbc7-46c0d97270f2 == source_entity_id == target_entity_id
    rep1 book_id 01a02c61-12bc-731d-9408-6c2e4b3e07e0 == source_entity_id == target_entity_id
    rep2 book_id 01a02c61-bbfd-7821-ba26-df09189ace2a == source_entity_id == target_entity_id

Every other arm of `_invented_supplier_ids` tests for a value that looks WRONG. A book_id is a
real, current, valid UUIDv7 that the runtime itself injected — the most plausible-looking wrong
answer available, and what the model reaches for when it needs an id it does not have.

PRECISION MEASURED BEFORE THIS SHIPPED, over 16,080 recorded calls: 180 firings across 15 tools,
every one a wrong argument (entity_id=71, chapter_id=38, book_chapter_delete.chapter_id=15,
run_id=13). The one candidate false positive — project_id — is not one: knowledge_projects has
zero rows where project_id equals book_id.
"""
from app.services.stream_service import _invented_supplier_ids

BOOK = "01a02c60-696c-724e-bbc7-46c0d97270f2"
OTHER = "01a02c61-12bc-731d-9408-6c2e4b3e07e0"


def test_the_book_id_passed_as_both_endpoints_is_dropped():
    args = {"book_id": BOOK, "source_entity_id": BOOK, "target_entity_id": BOOK}
    assert sorted(_invented_supplier_ids(args, None)) == [
        "source_entity_id", "target_entity_id",
    ]


def test_a_chapter_id_equal_to_the_book_id_is_dropped():
    """book_chapter_delete.chapter_id=book_id fired 15 times in the corpus — and it deletes."""
    assert _invented_supplier_ids({"book_id": BOOK, "chapter_id": BOOK}, None) == []
    # chapter_id IS a runtime context id, so it is exempt by name — the guard must not fight the
    # runtime for a value the runtime itself supplies. The real catch is a DOMAIN id:
    assert _invented_supplier_ids({"book_id": BOOK, "entity_id": BOOK}, None) == ["entity_id"]


def test_a_real_distinct_id_is_untouched():
    args = {"book_id": BOOK, "source_entity_id": OTHER, "target_entity_id": "019ff497-e068-77db-89f7-9d8c298fe8cd"}
    assert _invented_supplier_ids(args, None) == []


def test_no_context_id_in_the_call_means_nothing_to_compare():
    assert _invented_supplier_ids({"source_entity_id": BOOK}, None) == []


def test_the_context_ids_themselves_are_never_dropped():
    """D-FJ-2's standing invariant: a context id is injected by the runtime, not invented."""
    assert _invented_supplier_ids({"book_id": BOOK, "project_id": BOOK}, None) == []
