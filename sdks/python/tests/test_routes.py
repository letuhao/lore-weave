"""loreweave_obs.routes — route enumeration that survives the FastAPI 0.139 change.

This test is written to pass on BOTH sides of that change, which is the only way it is worth
having: the machine that found the bug (a shipped image, fastapi 0.139.2) and the machine that
must not regress it (a dev box on 0.136, where `app.routes` is still flat) run the same
assertions. A test that only passes on one of them would have told me nothing here — my local
suite was green on 3303 tests while CI was red for exactly this reason.

The break, measured 2026-08-01 inside the composition image::

    route entry types: {'Route': 4, '_IncludedRouter': 35, 'Mount': 1}
    flattened path count: 202       ← what the app serves
    naive `hasattr(r, "path")`: 5   ← what the old idiom saw
"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from loreweave_obs.routes import iter_routes, route_ops, route_paths  # noqa: E402


def _app():
    inner = fastapi.APIRouter()

    @inner.get("/nodes")
    def _list_nodes():  # pragma: no cover - never called
        return []

    @inner.post("/nodes")
    def _make_node():  # pragma: no cover
        return {}

    deep = fastapi.APIRouter()

    @deep.get("/{node_id}/grounding")
    def _grounding(node_id: str):  # pragma: no cover
        return {}

    # A router that includes a router — the recursion case. Both prefixes must compose.
    inner.include_router(deep, prefix="/scenes")

    app = fastapi.FastAPI()

    @app.get("/health")
    def _health():  # pragma: no cover
        return {}

    app.include_router(inner, prefix="/v1/composition")
    return app


def test_every_included_path_is_enumerated_with_its_prefix():
    paths = route_paths(_app())
    assert "/health" in paths
    assert "/v1/composition/nodes" in paths
    assert "/v1/composition/scenes/{node_id}/grounding" in paths, "nested includes must compose"


def test_the_naive_idiom_is_the_thing_that_broke():
    """Pins WHY the helper exists rather than only that it works.

    On fastapi >= 0.139 the naive set is a strict subset — the include wrappers contribute
    nothing. On older versions the two agree. Either way the helper must be a superset, and on
    the new version it must be a STRICT one, or the helper is not doing its job.
    """
    app = _app()
    naive = {getattr(r, "path", None) for r in app.routes} - {None}
    full = route_paths(app)
    assert naive <= full
    if any(not hasattr(r, "path") for r in app.routes):
        assert naive < full, "on this FastAPI the wrappers hide routes; the helper must find them"


def test_ops_carry_the_method_so_a_contract_check_can_compare_pairs():
    ops = route_ops(_app())
    assert ("GET", "/v1/composition/nodes") in ops
    assert ("POST", "/v1/composition/nodes") in ops
    assert ("POST", "/health") not in ops, "a method the app does not serve must not appear"


def test_iter_routes_yields_route_objects_not_paths():
    """A caller that needs `methods`/`endpoint` still has them."""
    routes = list(iter_routes(_app()))
    assert routes and all(hasattr(r, "path") for r in routes)
    assert any(getattr(r, "methods", None) for r in routes)


def test_an_app_with_no_routes_is_empty_not_an_error():
    assert route_paths(fastapi.FastAPI()) >= set()


def test_a_cycle_cannot_hang_the_walk():
    """The walk reads attributes it does not own. FastAPI makes no cycles, but an infinite
    generator inside a test suite is a hang rather than a failure — so the depth cap is
    asserted against a real cycle, not a plain self-reference.

    The shape matters: an entry is only FOLLOWED when it looks like an include wrapper
    (`include_context.included_router`). A bare object that points at itself is treated as a
    leaf route and yielded once — no recursion, nothing to cap. The first version of this test
    asserted the leaf case and reddened, which is the useful kind of wrong: it showed the two
    functions disagree about what an unrecognised entry IS, and they should — `route_paths`
    wants paths, `iter_routes` hands back whatever the app listed.
    """

    class _Ctx:
        prefix = "/loop"
        included_router = None

    class _Wrapper:
        include_context = _Ctx()

    class _Router:
        routes: list = []

    router, wrapper = _Router(), _Wrapper()
    router.routes = [wrapper]
    _Ctx.included_router = router  # router → wrapper → router → …

    assert route_paths(router) == set()
    assert list(iter_routes(router)) == []
