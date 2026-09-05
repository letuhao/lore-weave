"""An optional argument that silently switches modes must not refuse opaquely.

`book_id` on the motif tools selects between two incompatible rules:

    book_id OMITTED    the motif / both endpoints must be ones the caller OWNS
    book_id SUPPLIED   they must be `book_shared` in THAT book

Measured 2026-08-24 (batch c-motiflink5): the model resolved both motifs to their real seeded
ids, passed the correct direction and kind, AND passed the ambient book_id — because every other
composition tool takes the ambient book. Its own private motifs are not book_shared, so the call
was refused with "not found or not accessible" about motifs it had just listed by id. There was
no path from that message back to the working call and both runs stopped.

🔴 THE FIX EXISTED FOR create_link AND WAS NEVER CARRIED ACROSS. `EndpointsOwnedNotShared` and its
actionable message shipped for the LINK path; `composition_motif_archive` and
`composition_motif_restore` have the identical shape — an optional book_id switching to a
shared-tier requirement — and both still raised the bare uniform refusal. One cause, three names.

WHY NAMING THE REMEDY DOES NOT WEAKEN H13: the uniform refusal exists so a message is not an
existence oracle for objects the caller does not own. These branches fire ONLY when the caller
owns the row and already holds its id, so they disclose nothing it did not supply. Every other
miss keeps the uniform refusal.
"""
from __future__ import annotations

import inspect

from app.mcp import server


def _src(fn):
    return inspect.getsource(fn)


class TestTheRecoverableMissNamesItsRemedy:
    def test_archive_tells_the_caller_to_DROP_book_id(self):
        s = _src(server.composition_motif_archive)
        assert "owns_motif(" in s, "archive cannot tell the recoverable miss from any other"
        assert "WITHOUT book_id" in s, "the refusal does not name the remedy"

    def test_restore_tells_the_caller_to_DROP_book_id(self):
        s = _src(server.composition_motif_restore)
        assert "owns_motif(" in s
        assert "WITHOUT book_id" in s

    def test_the_link_path_that_was_already_fixed_still_names_it(self):
        """The instance the row was written from — pinned so the class cannot regress at the end
        it was first repaired."""
        src = inspect.getsource(server)
        assert "except EndpointsOwnedNotShared:" in src
        assert "again WITHOUT book_id to link two " in src


class TestEveryOtherMissKeepsTheUniformRefusal:
    def test_the_remedy_is_gated_on_OWNERSHIP(self):
        """If the branch fired for any failed lookup it WOULD be an existence oracle. It must be
        reachable only when the caller owns the row."""
        for fn in (server.composition_motif_archive, server.composition_motif_restore):
            s = _src(fn)
            i = s.index("owns_motif(")
            head = s[max(0, i - 120):i]
            assert "if " in head, f"{fn.__name__}: the remedy is not conditional on ownership"
            assert "uniform_not_accessible()" in s[i:], (
                f"{fn.__name__}: the uniform refusal no longer backstops the other misses")

    def test_restore_only_offers_it_in_the_BOOK_scoped_mode(self):
        """Without book_id there is no mode confusion to explain — offering the remedy there
        would be noise on a plain miss."""
        s = _src(server.composition_motif_restore)
        i = s.index("owns_motif(")
        assert "book_id is not None and" in s[max(0, i - 80):i]


class TestTheOpDispatchSurfaceCarriesTheSameWarning:
    def test_the_superset_book_id_is_DESCRIBED(self):
        """composition_motif_edit is a flat-superset op tool: a model reads ITS schema, not the
        sub-tools'. A bare annotation there hands the model nothing, which is how the ambient
        book_id got passed in the first place."""
        src = inspect.getsource(server)
        i = src.index("class _MotifEditArgs")
        block = src[i:i + 2600]
        assert "book_id: str | None = None" not in block, "the superset's book_id is still bare"
        assert "OMIT THIS" in block and "SHARED" in block
