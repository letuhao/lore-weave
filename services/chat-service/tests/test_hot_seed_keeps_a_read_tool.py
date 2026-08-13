"""D-FJ-23 — an authoring surface must never seed writes only.

🔴 MEASURED 2026-08-13 against the live 315-tool catalogue, per surface:

    editor (glossary+composition+book)  196 candidates → 4 kept, ALL 4 the write reservation
                                        (1986 of the 2000-token budget), READS THAT FIT: ZERO
    book-scoped (glossary)               54 candidates → 8 kept, 2 reserved, 6 reads
    knowledge                            36 candidates → 8 kept, 3 reserved, 5 reads

`ALWAYS_HOT_WRITES` is declared per TOOL but its cost compounds per SURFACE, and the editor is the
only surface carrying glossary + composition + book writes at once. So on the surface built for
authoring the hot seed was 100% writes, and a plain question arrived at a model holding no read
tool at all. Twice, live, it answered from nothing:

    "I checked the consistency rules for this book, and you haven't declared any canon rules yet"
        — the store held one.
    "I checked your current outline, and it is currently empty"
        — the store held seven nodes.

Two independent halves, tuned in the same week and never against each other: the budget was halved
4000→2000 (F12 warm-cache A/B, 2026-07-21) while `book_update_details` was ADDED to the write
allowlist (dogfood 2026-07-21) *because* the budget had starved it. Each rescue ate the seed that
starved the next tool, and nothing reported it — the file's own `budget_names_by_tokens_ex` exists
because "a narrowing the caller cannot see is indistinguishable from a decision the model made",
and this was exactly such a narrowing.

The fix is two changes that only work together, which is why they are tested together:
  * the unconditional allowlists no longer charge the discovery budget (an unconditional
    allowlist competing for a budget is a contradiction — the same call D-RAIL-OWN-BUDGET made);
  * `ALWAYS_HOT_READS` mirrors the writes, because decoupling ALONE still filled the seed with
    `book_scene_get` and `glossary_book_sync_available` while every primary read was dropped.
"""
import pytest

from app.services.tool_surface import (
    ALWAYS_HOT_READS,
    ALWAYS_HOT_WRITES,
    HOT_SEED_TOKEN_BUDGET,
    _budget_names_impl,
)


def _tool(name, params):
    return {"type": "function", "function": {
        "name": name,
        "description": "x" * 200,
        "parameters": {"type": "object", "properties": {
            p: {"type": "string", "description": "y" * 120} for p in params
        }},
        "_meta": {"tier": "W" if name in ALWAYS_HOT_WRITES else "R"},
    }}


# The shape that produced the incident: a handful of big reserved WRITES, one big PRIMARY read,
# and a crowd of tiny peripheral reads that the ascending-size tie-break prefers.
CATALOG = (
    [_tool(n, ["a", "b", "c", "d", "e"]) for n in sorted(ALWAYS_HOT_WRITES)]
    + [_tool("composition_list_outline", ["project_id", "detail", "limit", "include_archived"])]
    + [_tool("book_read", ["book_id", "chapter_id", "detail"])]
    + [_tool(f"peripheral_get_{i}", ["id"]) for i in range(40)]
)
NAMES = {t["function"]["name"] for t in CATALOG}


def _kept(budget=HOT_SEED_TOKEN_BUDGET):
    return _budget_names_impl(CATALOG, NAMES, token_budget=budget)


class TestThePrimaryReadSurvivesTheSeed:
    def test_the_LIVE_defect_the_editor_seed_is_not_writes_only(self):
        """THE FALSIFIER. Before the fix this kept only the write reservation."""
        kept = _kept()
        reads = kept - ALWAYS_HOT_WRITES
        assert reads, "the hot seed kept no read tool at all — a question has nothing to land on"

    @pytest.mark.parametrize("primary", ["composition_list_outline", "book_read"])
    def test_a_primary_read_beats_a_crowd_of_tiny_peripheral_ones(self, primary):
        """Ascending schema size is inversely correlated with centrality: a primary read declares
        filters and documents them, a peripheral one takes a single id. Decoupling the write
        reservation alone did NOT fix this — measured live, the freed budget filled with
        `book_scene_get` and `glossary_entity_get_genres` while every primary read stayed dropped.
        """
        assert primary in _kept()

    def test_the_reservation_alone_can_no_longer_consume_the_whole_budget(self):
        """Even at a budget far smaller than the reservation's own cost, the curated set is intact
        and the fill is simply empty — instead of the reservation silently deleting the reads."""
        kept = _kept(budget=1)
        assert (ALWAYS_HOT_WRITES & NAMES) <= kept
        assert (ALWAYS_HOT_READS & NAMES) <= kept


class TestTheFillStillWorks:
    """Controls. A fix that made everything unconditional would pass every test above while
    quietly deleting the budget — and the budget is what stops a 315-tool catalogue from being
    re-sent on every tool-loop iteration (the 2026-07-06 context explosion: 137K-token turns)."""

    def test_the_size_ordered_fill_still_adds_tools_beyond_the_allowlists(self):
        extra = _kept() - ALWAYS_HOT_WRITES - ALWAYS_HOT_READS
        assert extra, "the discovery fill stopped working"

    def test_the_fill_is_still_BOUNDED_by_its_budget(self):
        assert len(_kept(budget=1) - ALWAYS_HOT_WRITES - ALWAYS_HOT_READS) < len(
            _kept(budget=100_000) - ALWAYS_HOT_WRITES - ALWAYS_HOT_READS
        ), "the budget no longer bounds anything"

    def test_a_tool_outside_the_catalogue_still_passes_through_free(self):
        kept = _budget_names_impl(CATALOG, NAMES | {"tool_load"}, token_budget=HOT_SEED_TOKEN_BUDGET)
        assert "tool_load" in kept


class TestTheRegistryStaysSmallAndDeliberate:
    def test_every_entry_is_a_read_not_a_write(self):
        assert not (ALWAYS_HOT_READS & ALWAYS_HOT_WRITES)

    def test_the_registry_is_small_enough_to_be_a_decision_rather_than_a_default(self):
        """Every entry spends the authoring surface's prefix on every turn. If this ever needs to
        grow past a handful, the answer is a better selection rule, not a longer allowlist."""
        assert len(ALWAYS_HOT_READS) <= 6
