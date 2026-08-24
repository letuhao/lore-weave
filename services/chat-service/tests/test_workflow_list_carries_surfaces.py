"""D-WORKFLOW-LIST-DROPS-THE-FIELD-THAT-MAKES-ITS-ANSWER-TRUE.

Measured 2026-08-24: asked "What workflows are available on the studio surface?", the model
answered from workflow_list on 4 of 5 runs and named NINE workflows as studio-available. Five of
them are not — the studio has six. The rows arrive carrying `surfaces`; the L1 projection threw
it away, so the model could not have known.
"""
from app.services.workflow_runner import workflow_list_result

ROWS = [
    {"slug": "kg-build", "title": "Build the graph", "description": "…", "tier": "system",
     "surfaces": ["book", "editor"], "steps": [{"tool": "x"}], "notes_md": "long prose"},
    {"slug": "autonomous-drafting", "title": "Draft chapters", "description": "…",
     "tier": "system", "surfaces": ["book", "editor", "studio"]},
    {"slug": "no-surfaces-declared", "title": "Odd one", "description": "…", "tier": "user"},
]


class TestTheFieldSurvivesTheProjection:
    def test_surfaces_is_returned_per_row(self):
        out = workflow_list_result(ROWS)
        got = {w["slug"]: w.get("surfaces") for w in out["workflows"]}
        assert got["kg-build"] == ["book", "editor"]
        assert got["autonomous-drafting"] == ["book", "editor", "studio"]

    def test_a_studio_question_is_answerable_from_the_result_alone(self):
        """The whole point: the caller can now narrow without a second tool. Before the fix this
        assertion was unsatisfiable from this result at any effort."""
        out = workflow_list_result(ROWS)
        studio = [w["slug"] for w in out["workflows"] if "studio" in (w.get("surfaces") or [])]
        assert studio == ["autonomous-drafting"], studio

    def test_a_row_with_no_surfaces_yields_an_empty_list_not_a_missing_key(self):
        """A missing key reads to the agent as 'unknown'; [] reads as 'declared none'. Neither
        should be a KeyError, and the shape must be uniform across rows."""
        out = workflow_list_result(ROWS)
        odd = [w for w in out["workflows"] if w["slug"] == "no-surfaces-declared"][0]
        assert odd["surfaces"] == []
        assert all("surfaces" in w for w in out["workflows"])


class TestItStaysAnL1Listing:
    def test_the_heavy_fields_are_still_dropped(self):
        """🔴 THE GUARD ON THE GUARD. `steps` and `notes_md` are what make the full workflow
        expensive — notes_md is prose measured in kilobytes. Carrying `surfaces` must not become
        a licence to widen the reference shape; OUT-1 is why this listing is small."""
        out = workflow_list_result(ROWS)
        for w in out["workflows"]:
            assert "steps" not in w
            assert "notes_md" not in w
            assert set(w) == {"slug", "title", "description", "tier", "surfaces"}

    def test_count_and_ordering_are_unchanged(self):
        out = workflow_list_result(ROWS)
        assert out["count"] == 3
        assert [w["slug"] for w in out["workflows"]] == sorted(w["slug"] for w in ROWS)

    def test_the_empty_case_still_reports_a_reason(self):
        out = workflow_list_result([])
        assert out["count"] == 0 and out.get("reason") == "no workflows"
