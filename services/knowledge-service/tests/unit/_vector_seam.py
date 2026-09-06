"""Test shim for the T25a vector-store seam.

The write sites used to call `upsert_passage(session, **kwargs)` / `set_entity_embedding(...)`
directly, and their tests patched those names on the calling module and asserted on
`call.kwargs[...]`. T25a moved the write behind `VectorStore.upsert(record)`.

Patching the new seam naively would have meant rewriting ~32 assertions from
`call.kwargs["canon"]` to `record.canon` — churn that risks quietly weakening a check while
"just updating a test". So this forwards the record's fields to the SAME mock as keyword
arguments, and every existing assertion keeps testing exactly what it tested before.

That is faithful, not a trick: `PassageVectorRecord`'s fields are one-for-one the kwargs
`upsert_passage` took, and `EntityVectorRecord`'s are `set_entity_embedding`'s. If those
ever drift apart, the field names stop matching and the assertions fail — which is the
behaviour you want from a shim, rather than one that silently absorbs the difference.
"""

from __future__ import annotations

import dataclasses


class RecordingStore:
    """A `VectorStore` whose `upsert` calls `mock(**record_fields)`."""

    def __init__(self, mock) -> None:
        self._mock = mock

    async def upsert(self, record):
        fields = {f.name: getattr(record, f.name) for f in dataclasses.fields(record)}
        # `scope` is the port's discriminator, not one of the repo call's parameters.
        fields.pop("scope", None)
        return await self._mock(**fields)


def patch_vector_store(monkeypatch, module: str, mock) -> None:
    """Point `<module>.get_vector_store` at a store that records into `mock`."""

    async def _get(session):
        return RecordingStore(mock)

    monkeypatch.setattr(f"{module}.get_vector_store", _get)


def patch_vector_seam(module: str):
    """Decorator form, for tests that stack `@patch(...)` rather than take monkeypatch.

    Place it INNERMOST (directly above the function). `unittest.mock.patch` appends its
    mock to the arguments it passes down, so an innermost decorator's mock arrives LAST —
    which is exactly where the `set_entity_embedding` mock used to land, leaving existing
    test signatures untouched.
    """
    import functools
    from unittest.mock import AsyncMock, patch as _patch

    import inspect

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            mock = AsyncMock()

            async def _get(session):
                return RecordingStore(mock)

            with _patch(f"{module}.get_vector_store", _get):
                return await fn(*args, mock, **kwargs)

        # Drop the LAST parameter from the advertised signature — the one this decorator
        # supplies. `functools.wraps` copies `__wrapped__`, and pytest follows it to decide
        # what to inject, so without this pytest sees a parameter nobody fills and reports
        # "fixture 'mock_set' not found". Same reason `unittest.mock.patch` maintains its
        # own signature bookkeeping.
        params = list(inspect.signature(fn).parameters.values())
        wrapper.__signature__ = inspect.Signature(params[:-1])
        del wrapper.__wrapped__
        return wrapper

    return deco
