"""D-SUPERSEDED-TOOL-COMPETES-WITH-ITS-REPLACEMENT — the third reach-path CAT-4 missed.

CAT-4 states the invariant in tool_discovery's own comment:

    "A legacy tool must never be discoverable: excluded from search_catalog() and from every
     domain hot-seed."

Both of those do exclude it. The TURN CATALOG that is actually advertised to the model did not,
so a superseded tool sat on the wire beside the tool that replaced it.

MEASURED 2026-08-14, batch 17. Of the 54 distinct tools advertised across the batch, 5 were
legacy — and every one was the direct predecessor of a tool under test:

    composition_canon_rule_delete      -> composition_canon_rule_edit
    composition_authoring_run_pause    -> composition_authoring_run_review
    composition_archive_derivative     -> composition_derivative_edit
    composition_divergence_spec_update -> composition_derivative_edit
    book_list_chapters                 -> book_list

That is not coincidence. The answerability matcher pulls the sibling in BECAUSE it shares the
user's vocabulary with its replacement. And the predecessor wins: it is the more specific name
for the exact ask. The model called the legacy tool on 3 of 5 scenarios, so three unified tools
scored 0/5 with nothing wrong with them —

    composition_canon_rule_edit       -> model called composition_canon_rule_delete   (5/5)
    composition_authoring_run_review  -> model called composition_authoring_run_pause (5/5)

🔴 THE RULE IS DELIBERATELY NARROWER THAN "DROP EVERY LEGACY TOOL", and the count is why. Of 117
legacy tools, 31 name NO superseded_by — including book_create, book_chapter_publish and
book_chapter_delete. Dropping those would delete reach with nothing to redirect to. A tool is
dropped only when its named replacement is in the SAME catalog, so the swap is
capability-preserving by construction. (Verified across the live catalog: 0 of the 86 have a
dangling superseded_by.)
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.tool_discovery import drop_superseded_tools  # noqa: E402

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")


def _t(name: str, **meta) -> dict:
    return {"function": {"name": name, "description": "", "_meta": meta}}


#: The five real pairs measured on the wire, plus the two shapes that must survive.
CATALOG = [
    _t("composition_canon_rule_delete", visibility="legacy",
       superseded_by="composition_canon_rule_edit"),
    _t("composition_canon_rule_edit", tier="A"),
    _t("composition_authoring_run_pause", visibility="legacy",
       superseded_by="composition_authoring_run_review"),
    _t("composition_authoring_run_review", tier="A"),
    _t("book_create", visibility="legacy"),                       # 1 of the 31 with no successor
    _t("composition_orphan", visibility="legacy", superseded_by="not_on_this_wire"),
]


class TestTheMeasuredPairsAreSeparated:
    """THE FALSIFIER — these are the exact names that were advertised together."""

    def test_the_predecessor_is_dropped(self):
        _, dropped = drop_superseded_tools(CATALOG)
        assert "composition_canon_rule_delete" in dropped
        assert "composition_authoring_run_pause" in dropped

    def test_the_replacement_stays(self):
        kept, _ = drop_superseded_tools(CATALOG)
        names = {t["function"]["name"] for t in kept}
        assert "composition_canon_rule_edit" in names
        assert "composition_authoring_run_review" in names


class TestEveryLegacyToolIsDroppedRegardlessOfSuccessor:
    """🔴 THE POLICY REVERSED ON 2026-08-25, BY OWNER DECISION, AND THESE TESTS WITH IT.

    This class used to be `TestCapabilityIsNeverLost` and asserted the OPPOSITE of what it
    asserts now: that a legacy tool with no successor, or with a successor absent from the
    wire, must be KEPT — because dropping it "would remove reach with nothing to redirect to".

    That reasoning is recorded here rather than deleted, because it is not silly and someone
    will re-derive it. The owner's standing decision overrides it: **a legacy tool is a DEAD
    tool.** The marking was applied deliberately months ago; traffic to a marked tool is rot,
    not evidence the tool is needed. The narrow rule left 31 legacy tools advertised forever
    (no `superseded_by` to satisfy) and 86 more advertised on any turn their replacement
    happened to miss.

    What that half-retirement costs is not hypothetical. `find_tools` was retired from the
    LLM's view in F17 on 2026-07-20 and last actually ran on 2026-07-15 — and its code kept a
    docstring calling itself "the variant the LIVE call site awaits", the public MCP gateway
    kept advertising it to every key at any scope, and the ai-gateway's server instructions
    kept telling every client to call it. An agent read all that, believed it, and spent a
    session debugging a cache-key bug reachable only through the dead tool.

    If a tool marked legacy turns out to be load-bearing, the fix is to CORRECT THE MARKING,
    not to leave a path open around it.
    """

    def test_a_legacy_tool_with_no_successor_is_dropped_too(self):
        """book_create is one of the 31 that name no successor. It goes anyway."""
        kept, dropped = drop_superseded_tools(CATALOG)
        assert "book_create" in dropped
        assert "book_create" not in {t["function"]["name"] for t in kept}

    def test_a_dangling_superseded_by_is_dropped_too(self):
        """A successor that is not on this wire no longer rescues its predecessor."""
        kept, dropped = drop_superseded_tools(CATALOG)
        assert "composition_orphan" in dropped
        assert "composition_orphan" not in {t["function"]["name"] for t in kept}

    def test_a_non_legacy_tool_is_never_touched(self):
        """The blast radius stays exactly at `visibility: legacy` — nothing else moves."""
        kept, dropped = drop_superseded_tools([_t("plain_tool", tier="R")])
        assert dropped == []
        assert len(kept) == 1

    def test_the_pin_is_still_the_only_way_back(self):
        """Widening the rule must not quietly disable CAT-4 Part D's escape hatch."""
        _, dropped = drop_superseded_tools(CATALOG, pinned={"book_create"})
        assert "book_create" not in dropped


class TestThePinEscapeHatchWorks:
    """CAT-4 Part D. The column, its closed-set validator and its picker feed existed with no
    consumer on the turn path — because nothing filtered these out for it to re-admit."""

    def test_a_pinned_legacy_tool_survives(self):
        _, dropped = drop_superseded_tools(
            CATALOG, pinned={"composition_canon_rule_delete"})
        assert "composition_canon_rule_delete" not in dropped

    def test_pinning_one_does_not_rescue_the_others(self):
        _, dropped = drop_superseded_tools(
            CATALOG, pinned={"composition_canon_rule_delete"})
        assert "composition_authoring_run_pause" in dropped


class TestTheCallSiteIsWired:
    """🔴 CALL-SITE GUARD. The helper is inert unless the advertised catalog runs through it —
    which is exactly the state the defect had: the filter existed for search_catalog and the
    hot-seed, and the wire was a third path nobody routed through them."""

    def test_the_turn_catalog_is_filtered(self):
        assert re.search(
            r"discovery_catalog,\s*_superseded\s*=\s*drop_superseded_tools\(", SRC), (
            "the advertised turn catalog no longer runs through drop_superseded_tools")

    def test_it_runs_after_the_intent_gate_not_instead_of_it(self):
        assert SRC.index("filter_intent_gated_setup_tools(") < SRC.index("drop_superseded_tools(")

    def test_the_session_pin_is_actually_read(self):
        """Passing an empty set would silently disable the escape hatch while looking wired."""
        i = SRC.index("drop_superseded_tools(")
        assert 'pinned_legacy_tools' in SRC[i:i + 300]

    def test_the_column_is_selected(self):
        """The pin cannot be read if the SELECT never fetched it — it would be None forever."""
        assert '"pinned_legacy_tools, "' in SRC


class TestTheWithholdingIsRecorded:
    def test_the_helper_registers_each_drop(self):
        td = (pathlib.Path(__file__).resolve().parents[1]
              / "app" / "services" / "tool_discovery.py").read_text(encoding="utf-8")
        i = td.index("def drop_superseded_tools(")
        body = td[i:i + 4500]
        assert "record_surface_withheld(" in body, (
            "a narrowed surface that is not registered reads as 'this tool does not exist'")
        assert 'stage="superseded"' in body
