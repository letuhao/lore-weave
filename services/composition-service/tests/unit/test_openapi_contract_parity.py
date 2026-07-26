"""W0-C1 — the OpenAPI contract is a GATE, not a document.

CLAUDE.md: *"contract-first — API contract frozen before frontend flow."* Wave 0 adds
two REST routes (`W0-BE1`'s owner-scoped motif-job read, `W0-BE2`'s canon-rule restore)
and Wave 0's own `W0-S7` consumes one of them from the FE. A route that ships with no
contract row is a route the FE has to reverse-engineer from the handler — which is how
this repo already grew three FE-invented URLs that 404 in production.

Three assertions, and the two directions are DELIBERATELY asymmetric:

  * FORWARD (`test_every_declared_path_exists_on_the_app`) — nothing in the contract is
    fictional. A contract row with no handler is a promise the FE will code against and
    the server will 404.
  * The two Wave-0 rows are present (the contract-first assertion itself).
  * `GenerationJob`'s scope keys are nullable — `W0-BE1`'s DDL made `project_id`/`book_id`
    `NULL`-able for an UNBOUND (owner-scoped) job. A contract that still says
    `format: uuid`, non-nullable is a lie the FE will trust and crash on.

  * NOT the REVERSE assertion (*"every app route is in the contract"*). 21 shipped
    composition routes have no contract row today (decision `Q-30-22-NOFE-ROUTES-NOT-ENUMERATED`
    enumerates them); a reverse gate would red on 21 pre-existing rows and this wave would
    spend itself backfilling them. That backfill is Wave 1's `W1-S0` route-coverage register.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app.main import app

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

CONTRACT_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts" / "api" / "composition" / "v1" / "openapi.yaml"
)


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), f"contract not found at {CONTRACT_PATH}"
    with CONTRACT_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _declared_ops(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """(METHOD, path) for every declared operation, path RELATIVE to the server url."""
    return [
        (method.upper(), path)
        for path, ops in spec["paths"].items()
        for method in ops
        if method.lower() in _HTTP_METHODS
    ]


def _live_ops() -> set[tuple[str, str]]:
    """(METHOD, full path) for every route actually mounted on the app."""
    return {
        (method.upper(), route.path)
        for route in app.routes
        for method in (getattr(route, "methods", None) or ())
    }


def test_every_declared_path_exists_on_the_app(spec: dict[str, Any]) -> None:
    """Forward parity: no contract row is fictional.

    `servers: [{url: /v1/composition}]` ⇒ contract paths are RELATIVE; the routers
    carry the prefix themselves (`APIRouter(prefix="/v1/composition")`).
    """
    base = spec["servers"][0]["url"]
    live = _live_ops()
    fictional = [
        f"{method} {base}{path}"
        for method, path in _declared_ops(spec)
        if (method, f"{base}{path}") not in live
    ]
    assert fictional == [], f"contract declares routes the app does not serve: {fictional}"


def test_the_two_wave0_routes_are_in_the_contract(spec: dict[str, Any]) -> None:
    """W0-BE1 + W0-BE2 — the contract-first assertion. It REDS at HEAD."""
    declared = set(_declared_ops(spec))
    assert ("GET", "/motif-jobs/{job_id}") in declared, (
        "W0-BE1's owner-scoped motif-job read is not in the contract — "
        "W0-S7 (the FE poll) must not be written against an unfrozen route"
    )
    assert ("POST", "/canon-rules/{rule_id}/restore") in declared, (
        "W0-BE2's canon-rule restore is not in the contract"
    )


def test_no_response_object_has_a_bogus_key(spec: dict[str, Any]) -> None:
    """The comma-in-a-flow-scalar bug class — caught for real while writing this slice.

    `'404': { description: Not found, not archived, or cross-user }` is VALID YAML: inside a
    FLOW mapping the unquoted commas split the scalar, so `yaml.safe_load` cheerfully returns
    `{'description': 'Not found', 'not archived': None, 'or cross-user': None}`. A parse-only
    lint passes and the emitted contract is silently garbage. An OpenAPI Response Object may
    only carry description/headers/content/links (or be a $ref) — anything else is that bug.
    (openapi-spec-validator finds this too, but it is not in requirements-test.txt; this guard
    needs no dependency, so it runs everywhere the suite runs.)
    """
    legal = {"description", "headers", "content", "links", "$ref"}
    bogus: list[str] = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            for code, response in op.get("responses", {}).items():
                for key in set(response) - legal:
                    bogus.append(f"{method.upper()} {path} → {code} → {key!r}")
    assert bogus == [], (
        "response objects carry keys OpenAPI does not define — almost certainly an unquoted "
        f"comma inside a flow mapping: {bogus}"
    )


def test_generation_job_scope_keys_are_nullable(spec: dict[str, Any]) -> None:
    """W0-BE1's DDL dropped NOT NULL on generation_job.project_id/book_id.

    Catches the DDL⇄contract drift the FE would otherwise eat: an UNBOUND job (a
    corpus/book motif-mine, an arc-import) returns `project_id: null` + `book_id: null`.
    Both-or-neither is enforced by the DB (CHECK generation_job_scope_shape).
    """
    props = spec["components"]["schemas"]["GenerationJob"]["properties"]
    assert props["project_id"].get("nullable") is True, (
        "GenerationJob.project_id must be nullable — an unbound job carries no project"
    )
    assert "book_id" in props, "GenerationJob never declared book_id at all"
    assert props["book_id"].get("nullable") is True, (
        "GenerationJob.book_id must be nullable — an unbound job carries no book"
    )
