"""TOOLV2 LOOP #248 — the wiki cost card counted every entity and called them "active".

Measured live on a throwaway book:

    GET /v1/kg/actions/preview -> {"label": "entities", "value": "3",
                                   "note": "all active glossary entities"}

Those 3 entities are 1 active and 2 draft. The NUMBER is right — this is not a miscount.
`preview_build_wiki` reads glossary's `/internal/books/{id}/entity-count`, whose predicate is
`WHERE book_id = $1 AND deleted_at IS NULL`, and `_resolve_entity_ids` (what the job actually
enumerates) calls known-entities with `status_filter=None, min_frequency=0`, whose only extra
condition is `e.alive = true`. Nothing in the service ever writes `alive = false` (the single
match is a test fixture), and the largest book holds 3187 entities against a 500x40 page
ceiling, so the two predicates return the same set on all current data.

What is wrong is the LABEL, and it is wrong on a cost card. Measured across the instance:

    draft 6393 | active 925 | rejected 10

A human reading "all active glossary entities" beside a count from a book with thousands of
drafts is being told they are paying for roughly an eighth of what will actually be generated.
The word is not a harmless imprecision — on this card it is the difference between a small bill
and a large one, and the card is the only place the bill is shown before the money is spent.

The job is RIGHT to include drafts; `_resolve_entity_ids` says so in its own comment (both entity
creation paths insert status='draft', so an active-only filter would empty the wiki). Only the
description drifted — the same shape as #247's benchmark row, one card over.
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
EFFECT = APP / "ontology" / "build_wiki_effect.py"


def _body() -> str:
    return EFFECT.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_card_does_not_call_the_whole_glossary_active():
    body = _body()
    assert '"all active glossary entities"' not in body, (
        "the card labels its count 'active' again; measured, it counts draft + active + "
        "rejected alike (6393/925/10 across the instance)"
    )
    assert "whatever its triage status" in body, (
        "dropping the false word is not enough — the row must say which set is counted, or a "
        "human still has no way to size the bill"
    )
    assert "draft included" in body


def test_the_docstring_agrees_with_the_resolver():
    """The module docstring described the same set as 'active glossary entities' while the
    resolver three functions below passes status_filter=None on purpose."""
    body = _body()
    assert "active glossary entities" not in body
    assert "regardless of triage status" in body


def test_the_resolver_still_passes_no_status_filter():
    """If the resolver is ever changed to filter on status, the card's new wording becomes the
    false one and every assertion above would be pinning a fresh lie. Anchor to the code."""
    body = _body()
    assert "status_filter=None" in body, (
        "the wiki resolver now filters by status — the card wording shipped with #248 must be "
        "re-decided against whatever it filters to, not left to drift"
    )
    assert "min_frequency=0" in body, (
        "min_frequency is the other half of 'every entity': at the client default of 2 the job "
        "would silently drop hand-authored entities, which have no chapter links at all"
    )


def test_the_explicit_subset_branch_keeps_its_honest_label():
    """When the caller names entity_ids the note says 'selected', which was always true — the
    fix must not sweep the correct branch along with the incorrect one."""
    assert '"selected"' in _body()
