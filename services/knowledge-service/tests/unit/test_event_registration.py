"""WS-0.8 — the dispatcher REGISTRATION lock.

Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.7.

A handler that exists but is never registered is invisible. `EventDispatcher.dispatch`
drops an unregistered `event_type` with a **DEBUG** log line and returns False — invisible
in production. So book-service can commit the KG pointer, re-parse the scenes, return 200,
and show the chapter as "indexed", while the event is acked into the void: no
`extraction_pending` row, no passages, nothing in the graph.

That is the entire feature failing silently, and NO unit test of the handler itself can
catch it — the handler is fine; it is simply never called. Hence this test reads the real
`app/main.py` source and asserts the wiring is there.

It also locks the deliberate NON-registration of `chapter.saved` ("so unreviewed draft
prose never canonizes") — the one chapter event that must stay unconsumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_MAIN = Path(__file__).resolve().parents[2] / "app" / "main.py"


@pytest.fixture(scope="module")
def main_src() -> str:
    return _MAIN.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "event_type,handler",
    [
        # WS-0.8 — without these two the feature is a silent no-op.
        ("chapter.kg_indexed", "handle_chapter_kg_indexed"),
        ("chapter.kg_excluded", "handle_chapter_kg_excluded"),
        # Pre-existing chapter wiring — regression lock.
        ("chapter.published", "handle_chapter_published"),
        ("chapter.unpublished", "handle_chapter_unpublished"),
        ("chapter.scenes_reparsed", "handle_chapter_scenes_reparsed"),
        ("chapter.deleted", "handle_chapter_deleted"),
    ],
)
def test_event_is_registered_on_the_dispatcher(main_src: str, event_type: str, handler: str):
    registration = f'dispatcher.register("{event_type}", {handler})'
    assert registration in main_src, (
        f"{event_type} is NOT registered in app/main.py.\n"
        f"An unregistered event_type is DROPPED at DEBUG level and acked into the void — "
        f"invisible in production. For chapter.kg_indexed that means book-service reports "
        f"the chapter as indexed while the knowledge graph receives nothing at all: a "
        f"perfect silent success.\n"
        f"Expected: {registration}"
    )
    assert handler in main_src, f"{handler} is not imported in app/main.py"


def test_chapter_saved_is_deliberately_NOT_registered(main_src: str):
    """The one chapter event that must stay unconsumed.

    `chapter.saved` fires on EVERY autosave. Consuming it would (a) canonize unreviewed
    draft prose and (b) re-pay LLM extraction cost on every keystroke-debounce. Indexing
    is an explicit act (chapter.kg_indexed); autosave is not.
    """
    assert 'dispatcher.register("chapter.saved"' not in main_src, (
        "chapter.saved must NEVER be registered: it fires on every autosave, so consuming "
        "it would canonize unreviewed draft prose and re-pay extraction cost on every "
        "keystroke. WS-0.4 introduced chapter.kg_indexed precisely so that indexing is an "
        "EXPLICIT act."
    )
