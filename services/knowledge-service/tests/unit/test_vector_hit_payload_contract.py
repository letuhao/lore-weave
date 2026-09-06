"""The `VectorHit` payload contract — `include_vectors`, and key parity across backends (T24b).

WHY THIS FILE EXISTS
--------------------
`VectorHit.vector` has been on the port since T14 and **no adapter could ever populate it**.
`search()` had no `include_vectors`, so the Neo4j adapter called `find_passages_by_vector`
without it, the repo default `False` won, and `vector=h.vector` assigned `None` on every hit
forever. A promised field that no caller can obtain is the same class of defect as the
provider that nothing constructed: it reads as built.

It is not cosmetic. The L3 selector's MMR diversity pass computes hit-to-hit cosine from
`hit.vector`; without vectors it silently degrades to "no diversity re-rank at all", and
`select_l3_passages` is the main context path. That is why the selector could not be migrated
onto the port — not effort, a missing capability.

WHAT IS ENFORCED
----------------
  * `include_vectors=False` returns NO vector, and `True` returns the stored one
  * the two real backends agree on which attribute KEYS a passage hit carries

The second is the one that would rot. The Neo4j adapter builds its attributes as a dict
literal and the Postgres adapter from a column tuple, in two files, with nothing relating
them — the exact shape of the seven-names-in-a-Go-const-block problem this repo has a gate
for. A reader migrated onto the port reads ONE shape; two adapters that disagree about which
keys exist turn the cutover into a per-backend bug hunt.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.adapters.fake_vector_store import FakeVectorStore
from app.ports.vector_store import PassageVectorRecord, VectorFilter

_ADAPTERS = pathlib.Path(__file__).resolve().parents[2] / "app" / "adapters"


def _a_passage(**kw) -> PassageVectorRecord:
    base = dict(
        user_id="u1", project_id="p1", source_type="chapter", source_id="ch-1",
        chunk_index=0, text="the frost blade", embedding=[0.1, 0.2, 0.3, 0.4],
        embedding_dim=4, embedding_model="m1",
    )
    base.update(kw)
    return PassageVectorRecord(**base)


@pytest.mark.asyncio
async def test_include_vectors_OFF_returns_no_vector_and_ON_returns_the_stored_one():
    """Both directions. Asserting only the ON case would pass on a store that always
    returns the vector — which is the more expensive failure, since every caller that
    never asked would start paying `k × dim` floats per search."""
    store = FakeVectorStore()
    await store.upsert(_a_passage())

    off = await store.search(scope="passage", user_id="u1", embedding=[0.1, 0.2, 0.3, 0.4],
                             dim=4, k=5)
    assert off and off[0].vector is None, (
        "a search that did not ask for vectors got one — every caller now pays the payload")

    on = await store.search(scope="passage", user_id="u1", embedding=[0.1, 0.2, 0.3, 0.4],
                            dim=4, k=5, include_vectors=True)
    assert on and on[0].vector == [0.1, 0.2, 0.3, 0.4], (
        "include_vectors=True returned no vector — MMR diversity silently degrades to none")


@pytest.mark.asyncio
async def test_a_passage_hit_carries_the_fields_the_DRAWER_READ_publishes():
    """`project_id` and `created_at` are on the public `DrawerSearchHit` response. A port
    that could not carry them would force the migrated reader to DROP two fields from a
    shipped API — so they are part of the contract, not an adapter's convenience."""
    store = FakeVectorStore()
    await store.upsert(_a_passage())
    hit = (await store.search(scope="passage", user_id="u1",
                              embedding=[0.1, 0.2, 0.3, 0.4], dim=4, k=5))[0]
    for key in ("project_id", "created_at", "block_index"):
        assert key in hit.attributes, (
            f"a passage hit is missing {key!r} — the drawer read cannot be migrated onto "
            f"the port without dropping it from a published response")


def _neo4j_passage_attribute_keys() -> set[str]:
    """The keys the Neo4j adapter's passage branch actually writes, read out of its AST.

    Parsed rather than re-typed, for the reason this whole file exists: a hand-copied list
    agrees with the code on the day it is written and never again. Parsed rather than
    executed because constructing the adapter needs a live Neo4j session, and a drift guard
    that only runs where a database is configured is a drift guard that does not run.
    """
    tree = ast.parse((_ADAPTERS / "neo4j_vector_store.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "VectorHit":
            continue
        scope = next((kw.value for kw in node.keywords if kw.arg == "scope"), None)
        if not isinstance(scope, ast.Constant) or scope.value != "passage":
            continue
        attrs = next((kw.value for kw in node.keywords if kw.arg == "attributes"), None)
        assert isinstance(attrs, ast.Dict), "the passage attributes stopped being a literal"
        return {k.value for k in attrs.keys if isinstance(k, ast.Constant)}
    raise AssertionError("no passage-scope VectorHit construction found in the Neo4j adapter")


def test_the_two_real_backends_agree_on_a_passage_hits_attribute_KEYS():
    """🔴 The drift this is for is silent on both sides. A key added to one adapter and not
    the other produces a hit that is perfectly well formed, passes every test written against
    the backend that has it, and hands the migrated reader a `None` on the other — read as
    *"this passage has no chapter"* rather than *"this backend never sent one"*.

    Compared as SETS with the difference named in the message, because "assert a == b" on two
    literals tells a reader which two files disagree and not which key.
    """
    from app.adapters.pg_vector_store import _PASSAGE_ATTRS

    neo4j_keys = _neo4j_passage_attribute_keys()
    pg_keys = set(_PASSAGE_ATTRS)
    assert neo4j_keys == pg_keys, (
        f"the two adapters disagree about a passage hit's shape — "
        f"only in Neo4j: {sorted(neo4j_keys - pg_keys)}; "
        f"only in Postgres: {sorted(pg_keys - neo4j_keys)}")
