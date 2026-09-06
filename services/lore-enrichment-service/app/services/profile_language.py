"""Resolve an enrichment :class:`BookProfile`'s effective generation language.

``get_book_profile`` returns ``language="auto"`` (the NEUTRAL default) whenever
a book has no ``enrichment_book_profile`` row — true for any book that hasn't
been through Enrichment -> Profile, including every fresh book. When that
reaches ``generate.py``'s prompt builder, ``"auto"`` becomes the literal phrase
"the book's language" rather than a concrete instruction, relying on the model
to infer the right language from surrounding context.

That inference is not reliable: confirmed live with
``google/gemma-4-26b-a4b-qat``, an English book with no profile produced fully
Chinese enrichment content across every generated dimension from an English
draft. The book's real language IS resolvable — book-service's own
``original_language`` field, already read elsewhere via :class:`BookClient` —
just never threaded into this path. This module closes that gap.
"""

from __future__ import annotations

from uuid import UUID

from app.clients.book import BookClient, BookServiceError
from app.config import settings
from app.db.book_profile import BookProfile

__all__ = ["resolve_effective_language"]


async def resolve_effective_language(profile: BookProfile, *, book_id: str | None) -> BookProfile:
    """Return ``profile`` with ``language`` resolved to the book's real stored
    language when the profile hasn't set one (``""``/``"auto"``).

    Best-effort: a book-service error, or an unset ``original_language``, leaves
    ``profile`` unchanged — generation still runs, falling back to the
    pre-existing vague-phrase/model-inference behavior, rather than failing the
    job over a metadata read. A profile that already declares a real language
    (or a caller with no ``book_id``) is returned untouched.
    """
    if profile.language not in ("", "auto") or book_id is None:
        return profile
    client = BookClient(
        base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
    )
    try:
        projection = await client.get_projection(book_id=UUID(book_id))
    except BookServiceError:
        return profile
    finally:
        await client.aclose()
    if not projection.original_language:
        return profile
    return profile.model_copy(update={"language": projection.original_language})
