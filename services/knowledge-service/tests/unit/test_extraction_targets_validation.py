"""C12 — StartJobRequest target-typed extraction validation (unit, no DB).

The request layer validates + dedupes the target set but DELIBERATELY does
NOT auto-include `entities` — the dependent auto-include (requesting any of
{relations,events,facts} ⇒ entities) is applied at RUNTIME (SDK
normalize_targets + decoupled trio resolver), so the stored array keeps the
user's EXPLICIT intent (load-bearing for the recovery/filter-disable LOCK).
None / empty pass through unchanged (⇒ all passes = back-compat). Also
covers concurrency_level bounds.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.routers.public.extraction import StartJobRequest


def _req(**extra) -> StartJobRequest:
    base = dict(
        scope="chapters",
        llm_model="m",
        embedding_model="e",
    )
    base.update(extra)
    return StartJobRequest(**base)


def test_targets_none_passes_through():
    """targets omitted ⇒ None ⇒ runner treats as all passes (back-compat)."""
    assert _req().targets is None


def test_targets_empty_list_passes_through():
    """Empty list ⇒ unchanged (the runner treats empty as all)."""
    assert _req(targets=[]).targets == []


def test_targets_entities_only_unchanged():
    assert _req(targets=["entities"]).targets == ["entities"]


def test_targets_relations_NOT_baked_with_entities_at_request_layer():
    """{relations} stays {relations} in the STORED array — entities is added
    at runtime, not here (preserves explicit intent for the LOCK gate)."""
    assert _req(targets=["relations"]).targets == ["relations"]


def test_targets_events_NOT_baked_with_entities():
    assert _req(targets=["events"]).targets == ["events"]


def test_targets_summaries_only_unchanged():
    assert _req(targets=["summaries"]).targets == ["summaries"]


def test_targets_dedup_and_canonical_order():
    """Duplicate / out-of-order input is deduped into canonical order
    (without injecting entities)."""
    out = _req(targets=["facts", "facts", "events"]).targets
    assert out == ["events", "facts"]


def test_targets_invalid_token_rejected():
    """A token outside the taxonomy is a 422 (Literal enforcement)."""
    with pytest.raises(ValidationError):
        _req(targets=["lore"])


def test_concurrency_level_bounds():
    assert _req(concurrency_level=4).concurrency_level == 4
    with pytest.raises(ValidationError):
        _req(concurrency_level=0)
    with pytest.raises(ValidationError):
        _req(concurrency_level=65)
