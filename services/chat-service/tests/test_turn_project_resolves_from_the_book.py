"""D-MEMORY-FACT-STORED-UNSCOPED — a turn bound to a book is bound to that book's project.

MEASURED LIVE 2026-08-14, on a book-bound session whose `chat_sessions.project_id` was NULL:

    user:  "Remember this for later: Mira Solene is secretly the Pale Regent's daughter."
    tool:  memory_remember -> {"remembered": true, "fact_id": "790d92aa…", "confidence": 0.7}

The fact IS in Neo4j — verified by querying it directly — with `project_id` NULL. Across the
whole graph 339 of 343 Fact nodes carry a project; that one is among the four that do not. A
fact stored unscoped is invisible to project-scoped recall, so the same session then answered
"I don't have any information about Mira Solene" about the thing it had just been asked to
remember.

ROOT CAUSE — an asymmetry, not a broken line. `project_id` was read from exactly one source,
`session_row.project_id`, while `book_id` beside it has a four-step fallback chain. From there
it is mechanical: no project_id -> no X-Project-Id header -> knowledge-service's ctx.project_id
is None -> merge_fact(project_id=None). Every step locally correct; nothing accountable for
whether the project COULD have been resolved.

BLAST RADIUS: 417 of 503 book-bound sessions (83%) carry a book and no project.

These tests pin the RESOLUTION ORDER and, just as importantly, the cases where it must NOT
fire — a project resolver that guesses is worse than one that returns None, because a
cross-scope write is unrecoverable in a way an empty answer is not.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

SRC = (pathlib.Path(__file__).resolve().parents[1]
       / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
PROBE = (pathlib.Path(__file__).resolve().parents[1]
         / "app" / "services" / "book_state_probe.py").read_text(encoding="utf-8")


def test_the_resolver_exists_and_reads_the_book_s_project():
    """project_for_book uses the SAME kg-state endpoint _connections already calls — the
    response has always carried project_id and the old code read one field off it and dropped
    the rest."""
    assert "async def project_for_book(" in PROBE
    assert "/kg-state" in PROBE
    assert 'd.get("project_id")' in PROBE


def test_a_book_with_no_projection_resolves_to_none():
    """`has_projection: false` is a normal cold-start answer (200, not 404). It must collapse to
    None so every ambient tool fails closed exactly as it does today — never to a guess."""
    assert 'not d.get("has_projection")' in PROBE


def test_the_chain_is_wired_at_the_single_derivation_point():
    """One chokepoint, in the order the proposal states: session row -> studio_context -> the
    book's project -> None."""
    i = SRC.index('project_id = session_row.get("project_id") if session_row else None')
    window = SRC[i:i + 2600]
    assert "if not project_id:" in window
    assert 'project_id = (studio_context or {}).get("project_id")' in window
    assert "project_for_book(str(_pid_book))" in window


def test_it_only_fires_when_the_turn_has_a_book():
    """THE SAFETY PROPERTY. It resolves to the project of the book the turn is ALREADY scoped to,
    so it cannot redirect across scopes — the failure mode _inject_context_ids deliberately
    refuses by leaving a valid-but-unknown UUID alone. A session with no book is untouched."""
    i = SRC.index('project_id = session_row.get("project_id") if session_row else None')
    window = SRC[i:i + 2600]
    assert "if not project_id and _pid_book:" in window, (
        "the book lookup must be guarded on the turn HAVING a book; without that guard a "
        "book-less session could acquire someone's project"
    )


def test_a_probe_failure_leaves_todays_behaviour():
    """A resolver that raises must not break a turn that works today. It falls back to None and
    every ambient tool fails closed, exactly as before the fix."""
    i = SRC.index('project_id = session_row.get("project_id") if session_row else None')
    window = SRC[i:i + 2600]
    assert "except Exception:" in window
    assert "project_id = None" in window


def test_the_session_row_still_wins():
    """An explicitly bound session must keep its own project — the chain only supplies a value
    where there was none, it never overrides one."""
    i = SRC.index('project_id = session_row.get("project_id") if session_row else None')
    window = SRC[i:i + 2600]
    guard = window.index("if not project_id:")
    assert guard > 0, "the whole chain must sit behind `if not project_id`"
