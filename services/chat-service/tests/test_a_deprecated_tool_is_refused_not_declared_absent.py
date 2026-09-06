"""`tool_load` on a deprecated tool names its successor — it must never say `not_found`.

🔴 THE DEFECT, MEASURED 2026-09-03 against the live catalogue. Since the 2026-08-25 widening,
`drop_superseded_tools` removes EVERY legacy tool from the turn catalogue, so a legacy name reaches
`tool_load_result` as simply absent and fell through to `not_found`:

    tool_load("book_get")  ->  {"not_found": ["book_get"]}

`book_get` exists, is federated, and carries `superseded_by: book_read` in its own meta. The
function's own docstring already warns about this exact lie in the other direction — a live tool
called non-existent because its provider was down, which cost the 2026-07-23 incident: *"the model
reasoned correctly from that false premise and gave up on a tool that exists."* Deprecation
produced the same false premise by a different route, and nothing caught it because `not_found` is
a perfectly ordinary-looking answer.

A model told "no such tool" stops looking. Told "deprecated, use `book_read`" it calls `book_read`
— which is the entire point of dropping the predecessor.

🔴 PINNED LEGACY TOOLS ARE UNAFFECTED, ON PURPOSE (DQ-V3). A pin keeps the tool IN the catalogue,
so it loads normally and comes back labelled `deprecated: True` + `superseded_by`. An explicit
per-session user pin is not the model reaching a dead tool, and closing it would remove a
capability from users to satisfy a slogan.
"""
from __future__ import annotations

import contextvars
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.tool_discovery import (  # noqa: E402
    drop_superseded_tools, is_legacy_tool, tool_load_result, tool_name, tool_superseded_by,
)

CATALOG = pathlib.Path(__file__).resolve().parents[3] / "contracts" / "tool-catalog-cache.json"


def _dropped(catalogue: list[dict], pinned: set[str]) -> list[dict]:
    """`drop_superseded_tools` in a THROWAWAY context, because it WRITES to the instrument.

    🔴 THIS TEST FILE POLLUTED ITS NEIGHBOURS AND THE FULL SUITE CAUGHT IT. `drop_superseded_tools`
    calls `record_surface_withheld` once per dropped tool (tool_discovery.py:670) into a
    contextvar sink. Calling it from a module-scoped fixture wrote 117 rows into the AMBIENT
    context, and `TestU2ACatalogueOutageIsRegistered` builds its own sink with
    `contextvars.copy_context()` — which inherits whatever is already there. It then saw two
    catalogue rows where it asserts exactly one, and went red four ways.

    Alone: 43 passed. After an unrelated file: 163 passed. After this file: 5 red. The suite was
    right and the test was wrong — a test that leaks shared state is a defect in the test.
    """
    return contextvars.copy_context().run(drop_superseded_tools, catalogue, pinned)


def _openai_shape() -> list[dict]:
    """The cache is MCP-shaped (`meta`); discovery reads the OpenAI shape (`function._meta`)."""
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    return [{"type": "function",
             "function": {"name": n, "description": r.get("description", ""),
                          "parameters": r.get("inputSchema", {}), "_meta": r.get("meta") or {}}}
            for n, r in raw.items()]


@pytest.fixture(scope="module")
def catalogue() -> list[dict]:
    if not CATALOG.is_file():
        pytest.skip(f"{CATALOG} not present")
    return _openai_shape()


@pytest.fixture(scope="module")
def legacy_index(catalogue) -> dict[str, str | None]:
    ix = {tool_name(t): tool_superseded_by(t) for t in catalogue
          if is_legacy_tool(t) and tool_name(t)}
    assert ix, ("no legacy tool in the catalogue — this whole module would pass vacuously. "
                "Refresh the cache (scripts/refresh_tool_catalog_cache.py) before trusting it.")
    return ix


@pytest.fixture(scope="module")
def victim(legacy_index) -> str:
    """A legacy tool that HAS a successor — the case with something to say."""
    named = sorted(n for n, s in legacy_index.items() if s)
    assert named, "no legacy tool declares superseded_by; the successor half is untestable"
    return named[0]


def test_a_dropped_legacy_tool_is_NOT_reported_absent(catalogue, legacy_index, victim):
    """🔴 THE FALSIFIER. Remove the `legacy_index` branch from tool_load_result and this reds:
    the payload goes back to `{"not_found": [victim]}`."""
    kept, _ = _dropped(catalogue, set())
    assert victim not in {tool_name(t) for t in kept}, (
        "the fixture is wrong: this tool was not dropped, so the branch under test is not reached")
    payload, _loaded = tool_load_result(kept, name=victim, legacy_index=legacy_index)
    assert victim not in (payload.get("not_found") or []), (
        f"{victim} exists and is deprecated, but tool_load asserted it does not exist. A model "
        f"reasons correctly from that false premise and abandons a capability that is available "
        f"under another name.")
    assert [d["name"] for d in payload.get("deprecated") or []] == [victim]


def test_the_refusal_NAMES_the_successor(catalogue, legacy_index, victim):
    """A bare refusal is only half the fix — the point of dropping the predecessor is that the
    model calls the replacement instead."""
    kept, _ = _dropped(catalogue, set())
    payload, _ = tool_load_result(kept, name=victim, legacy_index=legacy_index)
    entry = (payload.get("deprecated") or [{}])[0]
    assert entry.get("superseded_by") == legacy_index[victim]
    assert legacy_index[victim] in (payload.get("deprecated_note") or "")


def test_a_GENUINELY_absent_name_still_says_not_found(catalogue, legacy_index):
    """The control. Without it, a change that simply deleted `not_found` would pass the two
    assertions above while destroying the ability to say a tool does not exist at all."""
    kept, _ = _dropped(catalogue, set())
    payload, _ = tool_load_result(kept, name="no_such_tool_anywhere", legacy_index=legacy_index)
    assert payload.get("not_found") == ["no_such_tool_anywhere"]
    assert not payload.get("deprecated")


def test_a_MIXED_request_keeps_the_two_answers_apart(catalogue, legacy_index, victim):
    """Both buckets survive one request; the deprecated name does not leak into `not_found`."""
    kept, _ = _dropped(catalogue, set())
    payload, _ = tool_load_result(kept, names=[victim, "no_such_tool_anywhere"],
                                  legacy_index=legacy_index)
    assert [d["name"] for d in payload["deprecated"]] == [victim]
    assert payload["not_found"] == ["no_such_tool_anywhere"]
    assert victim not in payload["not_found"]


def test_the_deprecated_note_does_not_CLOBBER_the_outage_note(catalogue, legacy_index, victim):
    """🔴 THE REASON `deprecated_note` IS A DISTINCT KEY, and it needs a provider OUTAGE to reach.

    `note` is written only on the provider-unavailable branch — a plain `not_found` sets no note
    at all, which my first version of this test got wrong and asserted anyway. So the collision is
    reachable only when a deprecated name and an unresolvable name arrive together DURING an
    outage. Had both written `note`, whichever ran second would have silently erased the other,
    and the surviving message would have been confidently wrong about the missing tool.
    """
    kept, _ = _dropped(catalogue, set())
    payload, _ = tool_load_result(kept, names=[victim, "vanished_with_its_provider"],
                                  legacy_index=legacy_index,
                                  unavailable_providers={"glossary"})
    assert payload.get("deprecated_note"), "the deprecation message was lost"
    assert payload.get("note"), "the outage message was lost"
    assert payload["deprecated_note"] != payload["note"]
    # and the outage branch must still own the unresolvable name, not the deprecated one
    assert payload.get("provider_unavailable") == ["vanished_with_its_provider"]
    assert victim not in (payload.get("provider_unavailable") or [])


def test_a_PINNED_legacy_tool_still_LOADS(catalogue, legacy_index, victim):
    """DQ-V3: the pin is kept. A user who deliberately pinned a legacy tool keeps it, labelled —
    this is the one path by which a legacy tool may still reach the wire, and it is a user choice.
    """
    kept, _ = _dropped(catalogue, {victim})
    payload, loaded = tool_load_result(kept, name=victim, legacy_index=legacy_index)
    assert loaded == [victim], "the pin no longer admits its tool"
    entry = payload["tools"][0]
    assert entry["deprecated"] is True
    assert entry.get("superseded_by") == legacy_index[victim]
    assert not payload.get("deprecated"), "a pinned tool must LOAD, not be refused"
