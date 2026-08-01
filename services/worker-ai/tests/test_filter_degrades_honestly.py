"""D-FILTER-DECOUPLED-COVERAGE-DISCARDED — a total judge outage read as "approved everything".

Three pieces had to line up, and they did:

1. an item with no verdict is ``"unjudged"``;
2. ``_apply_verdict`` resolves unjudged through ``partial_policy``, which defaults to
   **``"keep"``**;
3. ``finalize_filter`` threw coverage away (``kept, _coverage = ...``) and never wrote
   ``filter_status``.

So when the judge was unreachable, every candidate survived and the run recorded nothing
about it — **indistinguishable from a run where the judge read every item and approved it**.

The SYNC path in `pass2_filter.py` has always set ``filter_status="degraded"`` with zeroed
coverage on the same failure, and knowledge-service already consumes both (a Prometheus
gauge plus a log line). The vocabulary, the consumer and the metric all existed. The
decoupled path — the one that actually runs — simply never fed them.

Also pins D-FILTER-KEPT-EMPTY-CATEGORY: ``compute_filter_kept`` was extracted from
``_filter_one_category``'s *tail*, and the empty-category guard lives in its *head*, so the
extracted function divided by zero on a chapter that produced no events.
"""
from __future__ import annotations

import pytest

import app.decoupled_extract as dx


def _runstate(*, n_input: int, judged: dict[int, str], categories=("entity",)) -> dict:
    """A fan-in-complete run-state with `n_input` candidates and only `judged` verdicts.

    Candidate shape comes from the sibling suite's `_entity` helper, not from memory of the
    model — a hand-written dict fails Pydantic validation for its own reason and proves
    nothing about the property under test.
    """
    from tests.test_decoupled_extract import _entity

    rs = dx.new_extract_state(chunk_text="text", known_entities=[],
                              has_recovery=False, has_filter=True)
    rs.update(user_id="u", project_id="p", model_source="user_model", model_ref="m",
              stage=dx.FILTER)
    rs["_filter_cfg"] = {
        "model_ref": "flt-model", "model_source": "user_model",
        "partial_policy": "keep", "categories": list(categories),
        "max_items_per_batch": 3, "transient_retry_budget": 1,
    }
    rs["entities"] = [_entity(f"E{i}", f"e-{i}") for i in range(n_input)]
    rs["relations"] = []
    rs["events"] = []
    rs["filter_n_input"] = {"entity": n_input}
    rs["filter_verdicts"] = {"entity": {str(k): v for k, v in judged.items()}}
    return rs


class TestATotalOutageCannotReadAsApproval:
    def test_no_verdicts_at_all_is_recorded_as_degraded(self):
        """The exact shape of the outage: every batch failed to parse, so `local = {}`
        upstream and nothing was folded. Items still survive (partial_policy='keep' is a
        deliberate choice — dropping real candidates on an outage would be worse), but the
        run must SAY so."""
        rs = dx.finalize_filter(_runstate(n_input=5, judged={}))
        assert rs["filter_status"] == "degraded"
        assert rs["filter_coverage"]["entity"] == 0.0
        assert len(rs["entities"]) == 5, (
            "keep-on-unjudged is intended; the defect was never recording that it happened"
        )

    def test_a_partial_outage_is_recorded_as_degraded(self):
        """One batch of three landed, the rest did not. The kept set looks reasonable,
        which is precisely why the coverage number has to survive."""
        rs = dx.finalize_filter(_runstate(
            n_input=6, judged={0: "supported", 1: "unsupported", 2: "supported"}))
        assert rs["filter_status"] == "degraded"
        assert rs["filter_coverage"]["entity"] == pytest.approx(0.5)

    def test_a_fully_judged_run_is_applied(self):
        """The other half of the honesty contract: a real judged run must NOT be labelled
        degraded, or the label becomes noise and gets ignored — the failure mode the whole
        de-rot cycle is about."""
        rs = dx.finalize_filter(_runstate(
            n_input=3, judged={0: "supported", 1: "unsupported", 2: "supported"}))
        assert rs["filter_status"] == "applied"
        assert rs["filter_coverage"]["entity"] == pytest.approx(1.0)
        assert len(rs["entities"]) == 2, "the unsupported candidate should have been dropped"

    def test_the_status_vocabulary_matches_the_sync_path(self):
        """A consumer must not be able to tell which path produced the result. Same
        Literal, same words."""
        from loreweave_extraction.pass2 import FilterStatus  # noqa: F401  (typing import)

        for judged, expected in (({}, "degraded"), ({0: "supported"}, "applied")):
            rs = dx.finalize_filter(_runstate(n_input=1, judged=judged))
            assert rs["filter_status"] in ("applied", "degraded", "skipped")
            assert rs["filter_status"] == expected


def test_an_empty_category_does_not_crash_the_finalize():
    """D-FILTER-KEPT-EMPTY-CATEGORY. `compute_filter_kept` is documented as "identical to
    `_filter_one_category`'s tail" — and that was the bug: the `n_input == 0` guard lives
    in the HEAD. A chapter that yields no events is ordinary input, not an edge case, and
    it raised ZeroDivisionError inside the finalize."""
    rs = dx.finalize_filter(_runstate(n_input=0, judged={}))
    assert rs["filter_coverage"]["entity"] == 1.0, "an empty set is vacuously fully covered"
    assert rs["filter_status"] == "applied"
    assert rs["entities"] == []


def test_compute_filter_kept_matches_its_extraction_source_on_the_empty_case():
    """Pinned at the SDK boundary too, because both paths call it and only one of them
    carried the guard."""
    from loreweave_extraction.pass2_filter import PrecisionFilterConfig, compute_filter_kept

    kept, coverage = compute_filter_kept(
        "entity", 0, {}, PrecisionFilterConfig(model_ref="m"), None)
    assert kept == []
    assert coverage == 1.0
