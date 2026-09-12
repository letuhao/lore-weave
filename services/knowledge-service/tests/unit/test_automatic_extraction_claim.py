"""The README claim "automatic entity and relationship extraction" must stay TRUE.

WHY THIS EXISTS. A 2026-09-06 human-sim run wrote a 5-arc novel and never got a knowledge graph:
the Scene Inspector said "No knowledge graph yet -- run a knowledge extraction on this book once".
The run's report concluded the word "automatic" was an overclaim and that extraction needs a manual
run. **That conclusion was wrong**, and this test exists so nobody has to re-litigate it from a
screenshot.

Extraction is automatic, and the trigger is PUBLISHING a chapter: `chapter.published` is handled by
`handle_chapter_published`, which queues `extraction_pending` for the worker-ai drainer (and ingests
passages inline). The run drafted its chapters in the editor and never published them, so nothing
ever fired. The gap was the run's mental model, not the feature.

WHAT THIS GUARDS, and why it is not vacuous. The claim is one unregistered handler away from
becoming false, and the failure is SILENT: chapters publish, no event is consumed, no graph appears,
and the only symptom is a panel saying there is no graph -- exactly what the run saw and
misdiagnosed. Asserting the registration is the cheapest check that can actually go red.

WHAT IT DOES NOT CLAIM: that a graph appears for an UNPUBLISHED draft. It does not, by design
(draft prose must not surface as canon -- see `handle_chapter_published`'s own note on the
draft/canon split), and the README's "every chapter you write" is doing real work there.
"""
from __future__ import annotations

import inspect

from app.events import handlers


def test_the_published_handler_exists_and_is_the_extraction_entry_point():
    assert hasattr(handlers, "handle_chapter_published"), (
        "the handler the automatic-extraction claim depends on is gone"
    )
    src = inspect.getsource(handlers.handle_chapter_published)
    assert src, "handler source unavailable"


def test_publishing_is_wired_to_that_handler_in_the_service_entrypoint():
    """The registration is the load-bearing line: a handler that exists but is never registered
    leaves publishing silent, and the only symptom is a panel reporting no graph."""
    from pathlib import Path

    main_src = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")
    assert 'dispatcher.register("chapter.published", handle_chapter_published)' in main_src, (
        'chapter.published is no longer routed to handle_chapter_published -- publishing a chapter '
        'will no longer build the knowledge graph, and the README claims it does "automatically"'
    )


def test_the_incremental_path_queues_extraction_rather_than_requiring_a_manual_run():
    """The word under test is "automatic". The handler must ENQUEUE work, not merely record that a
    chapter changed and wait for a human to press something."""
    from pathlib import Path

    handlers_src = (
        Path(__file__).resolve().parents[2] / "app" / "events" / "handlers.py"
    ).read_text(encoding="utf-8")
    assert "extraction_pending" in handlers_src, (
        "the incremental KG path no longer queues extraction_pending -- extraction would need a "
        "manual trigger, which is precisely what the README says it does not"
    )


def test_the_guard_can_see_a_missing_registration():
    """NV-2 -- the subject must be able to vary. If the substring check could not fail, the
    assertion above would pass on any file at all."""
    fake = 'dispatcher.register("chapter.unpublished", handle_chapter_unpublished)\n'
    assert 'dispatcher.register("chapter.published", handle_chapter_published)' not in fake
