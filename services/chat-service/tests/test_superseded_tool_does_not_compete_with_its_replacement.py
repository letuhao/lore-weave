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


class TestCapabilityIsNeverLost:
    """The boundary. A drop is only safe because the replacement is right there."""

    def test_a_legacy_tool_with_no_successor_is_kept(self):
        """book_create is one of 31. Dropping it would remove reach with nothing to redirect to."""
        kept, dropped = drop_superseded_tools(CATALOG)
        assert "book_create" not in dropped
        assert "book_create" in {t["function"]["name"] for t in kept}

    def test_a_dangling_superseded_by_is_kept(self):
        """If the named replacement is NOT on this wire, dropping would strand the caller."""
        kept, dropped = drop_superseded_tools(CATALOG)
        assert "composition_orphan" not in dropped
        assert "composition_orphan" in {t["function"]["name"] for t in kept}

    def test_a_non_legacy_tool_is_never_touched(self):
        kept, dropped = drop_superseded_tools([_t("plain_tool", tier="R")])
        assert dropped == []
        assert len(kept) == 1


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
