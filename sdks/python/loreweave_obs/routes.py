"""Route introspection that survives FastAPI 0.139 — `app.routes` stopped being a flat list.

The break, measured 2026-08-01 inside the shipped composition image
(fastapi 0.139.2 / starlette 1.3.1)::

    route entry types: {'Route': 4, '_IncludedRouter': 35, 'Mount': 1}

Before 0.139, `include_router()` COPIED each sub-route into `app.routes`, so
``{r.path for r in app.routes}`` enumerated the whole surface. It now appends ONE
`_IncludedRouter` wrapper per include, holding the sub-router and its prefix in
`include_context`. The wrapper has no `.path`.

Two failure shapes came out of that, and the quiet one is worse:

  · ``{r.path for r in app.routes}`` → ``AttributeError: '_IncludedRouter' object has no
    attribute 'path'`` — loud, six tests across knowledge- and composition-service.
  · ``[r.path for r in app.routes if getattr(r, "path", "") in (...)]`` → **silently empty**.
    An ordering assertion over an empty list passes. A contract-parity test read 31 real,
    served routes as "declared but not served" for the same reason.

That second shape is why this lives in the SDK rather than being patched per test: the
enumeration is a shared assumption about FastAPI, it is now wrong, and a `getattr` default
turns "wrong" into "green".
"""
from __future__ import annotations

from typing import Any, Iterator

__all__ = ["iter_routes", "route_paths", "route_ops"]


def _sub(entry: Any) -> tuple[Any, str] | None:
    """(sub_router, prefix) for an include wrapper, else None.

    Duck-typed on purpose. `_IncludedRouter` is a PRIVATE FastAPI name: importing it would
    make this module fail to import on the version it exists to support the other side of,
    and pin us to a spelling upstream never promised to keep.

    Only a shape that carries BOTH the sub-router and its prefix is followed. `_IncludedRouter`
    also exposes `original_router`, and an earlier version fell back to it with `prefix=""` —
    which would have emitted every sub-route at the WRONG path, silently, the moment
    `include_context` was renamed. Losing routes is caught by the parity tests that consume
    this; inventing plausible wrong ones is not.
    """
    ctx = getattr(entry, "include_context", None)
    if ctx is None:
        return None
    sub = getattr(ctx, "included_router", None)
    if sub is None:
        return None
    return sub, str(getattr(ctx, "prefix", "") or "")


def iter_routes(app: Any, *, _depth: int = 0) -> Iterator[Any]:
    """Yield every real route object reachable from `app`, flattening include wrappers.

    Yields the ROUTE OBJECTS, not paths, so a caller that needs `methods`, `endpoint` or
    `name` still has them. Their `.path` is the sub-router's own — see `route_paths` for the
    prefixed, mounted path a client actually calls.

    A router can include a router, so this recurses. `_depth` is a cycle backstop: FastAPI
    does not create cycles, but this walks attributes it does not own, and an infinite
    generator inside a test suite is a hang rather than a failure.
    """
    if _depth > 20:
        return
    for entry in getattr(app, "routes", ()) or ():
        pair = _sub(entry)
        if pair is None:
            yield entry
            continue
        sub, _prefix = pair
        yield from iter_routes(sub, _depth=_depth + 1)


def route_paths(app: Any) -> set[str]:
    """The set of full paths the app serves, prefixes applied.

    The drop-in replacement for ``{r.path for r in app.routes}``. A route object with no
    `path` (a `Mount`, a websocket route) contributes nothing rather than raising — the
    caller asked for paths.
    """
    out: set[str] = set()
    _collect(app, "", out, 0)
    return out


def _collect(app: Any, prefix: str, out: set[str], depth: int) -> None:
    if depth > 20:
        return
    for entry in getattr(app, "routes", ()) or ():
        pair = _sub(entry)
        if pair is not None:
            sub, sub_prefix = pair
            _collect(sub, prefix + sub_prefix, out, depth + 1)
            continue
        path = getattr(entry, "path", None)
        if isinstance(path, str):
            out.add(prefix + path)


def route_ops(app: Any) -> set[tuple[str, str]]:
    """``{(METHOD, full_path)}`` for every HTTP operation the app serves.

    What an OpenAPI-parity check compares against: a contract row is a (method, path) pair,
    and a route that answers GET but not POST is a real difference. `HEAD` rides along with
    `GET` in Starlette's own `methods` set and is passed through unfiltered — a contract does
    not usually declare it, so a caller doing forward parity (is every DECLARED row served?)
    is unaffected, while reverse parity should filter.
    """
    out: set[tuple[str, str]] = set()
    _collect_ops(app, "", out, 0)
    return out


def _collect_ops(app: Any, prefix: str, out: set[tuple[str, str]], depth: int) -> None:
    if depth > 20:
        return
    for entry in getattr(app, "routes", ()) or ():
        pair = _sub(entry)
        if pair is not None:
            sub, sub_prefix = pair
            _collect_ops(sub, prefix + sub_prefix, out, depth + 1)
            continue
        path = getattr(entry, "path", None)
        if not isinstance(path, str):
            continue
        for method in (getattr(entry, "methods", None) or ()):
            out.add((str(method).upper(), prefix + path))
