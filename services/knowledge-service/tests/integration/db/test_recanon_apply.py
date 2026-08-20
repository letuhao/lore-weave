"""T35f — the recanon backfill's APPLY path, executed against a real Neo4j.

🔴 **WHY THIS EXISTS.** `plan_recanon` is a pure function with ten unit rules. `run_recanon_backfill`
— the half that WRITES — is marked `# pragma: no cover (real I/O)` and had never been executed by
anything. T35 owes an operator a command that re-keys **1819 nodes and merges 1** on the shared dev
graph, and the only evidence it works was that the plan it produces looks right.

That is the exact split this session has now found three times (T35e's collision guard the loader
never fed, T39's invalidation no test invoked, T51's compatibility that WAS pinned and is why it
is a no-op). A planner is not an apply path.

⚠️ Uses a THROWAWAY database — the fixture refuses the dev ports. These tests CREATE, RE-KEY and
DELETE nodes.
"""
from __future__ import annotations

import uuid

import pytest

from app.db.migrations.recanon_honorifics import run_recanon_backfill

pytestmark = pytest.mark.asyncio

# The live shape, exactly: a name whose stored canonical was produced by an older
# canonicaliser (partial simplified/traditional conversion). 1826 nodes look like this.
_NAME = "規則之力"
_STALE_CN = "规則之力"          # what the OLD canonicaliser produced
_KIND = "concept"


async def _seed(session, *, uid, pid, eid, name=_NAME, cn=_STALE_CN, anchor=None):
    await session.run(
        "CREATE (e:Entity {id:$id, user_id:$u, project_id:$p, name:$n, canonical_name:$cn, "
        "kind:$k, canonical_version:1, source_types:['chapter'], confidence:0.9, "
        "glossary_entity_id:$a, created_at:datetime(), updated_at:datetime()})",
        id=eid, u=uid, p=pid, n=name, cn=cn, k=_KIND, a=anchor)


async def test_the_APPLY_path_repairs_a_stale_canonical_name(neo4j_driver):
    """The 1819-node case. After apply, the node must resolve by its CURRENT name — which is
    the whole point: today it forks, because neither the stale canonical_name nor the stale
    derived id matches what `merge_entity` computes."""
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    eid = f"stale-{uuid.uuid4().hex[:10]}"
    async with neo4j_driver.session() as s:
        await _seed(s, uid=uid, pid=pid, eid=eid)
        plan = await run_recanon_backfill(s, apply=True)
        assert plan.rekeyed >= 1, plan

        r = await s.run(
            "MATCH (e:Entity {user_id:$u, project_id:$p}) "
            "RETURN count(e) AS c, collect(e.canonical_name)[0] AS cn", u=uid, p=pid)
        rec = await r.single()
        assert rec["c"] == 1, f"the repair duplicated the node instead of re-keying it: {rec}"

        from loreweave_extraction.canonical import canonicalize_entity_name
        assert rec["cn"] == canonicalize_entity_name(_NAME), (
            f"canonical_name is still stale after apply: {rec['cn']!r} — the node keeps forking")

        await s.run("MATCH (e:Entity {user_id:$u}) DETACH DELETE e", u=uid)


async def test_a_RE_KEY_does_not_orphan_an_EntityStatus_that_points_at_the_old_id(neo4j_driver):
    """🔴 The risk the apply path does not check, pinned before an operator runs it.

    `:EntityStatus` carries `entity_id` as a PROPERTY — 35 rows do on the dev graph — and the
    re-key changes `Entity.id`. Nothing in the migration re-points them. Measured 2026-08-14,
    **0 of the 33 resolvable status rows sit on an entity the backfill would re-key**, so the
    real run is safe *by luck, not by design*. This rule states the coupling so the luck is
    visible: if it ever goes red, a status row has been stranded from the entity it describes
    and a canon read would report that character as never having died.
    """
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    eid = f"stale-{uuid.uuid4().hex[:10]}"
    async with neo4j_driver.session() as s:
        await _seed(s, uid=uid, pid=pid, eid=eid)
        await s.run(
            "CREATE (:EntityStatus {user_id:$u, project_id:$p, entity_id:$e, status:'gone', "
            "from_order:1000000, evidence_count:2})", u=uid, p=pid, e=eid)

        await run_recanon_backfill(s, apply=True)

        r = await s.run(
            "MATCH (st:EntityStatus {user_id:$u}) "
            "OPTIONAL MATCH (e:Entity {id: st.entity_id}) "
            "RETURN count(st) AS statuses, count(e) AS resolved", u=uid)
        rec = await r.single()
        assert rec["statuses"] == 1, "the fixture's status row vanished"
        assert rec["resolved"] == 1, (
            "the re-key STRANDED an :EntityStatus row — its entity_id still points at the old "
            "id, so the status describes an entity that no longer exists at that key. A canon "
            "read would report the character as never having died.")

        await s.run("MATCH (n {user_id:$u}) DETACH DELETE n", u=uid)


async def test_the_MERGE_path_preserves_a_relation_PREDICATE(neo4j_driver):
    """🔴 The merge branch re-creates edges with a bare `MERGE (new)-[:RELATES_TO]->(o)` — no
    properties carried. A relation's PREDICATE is its meaning: "betrayed" and "guards" are the
    same edge type and different facts. If the re-point drops it, the merge silently converts
    every relation on the folded node into a typeless link.

    Only ONE merge survives the anchor guard on the real graph, so this affects one node — but
    an operator running `--apply` deserves to know whether that node's edges keep their meaning.
    """
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    survivor, stranded, other = (f"{k}-{uuid.uuid4().hex[:8]}" for k in ("surv", "strand", "oth"))
    async with neo4j_driver.session() as s:
        # ⚠️ `:Entity(user_id, project_id, glossary_entity_id)` is UNIQUE, so two nodes CANNOT
        # share an anchor — the first fixture tried and Neo4j refused it. That is worth
        # recording: the "two stale spellings of one glossary entity" case the planner's merge
        # branch handles can only arise when at least one side is UNANCHORED, which is exactly
        # what the one surviving merge on the real graph looks like.
        await _seed(s, uid=uid, pid=pid, eid=survivor, name="精靈大人", cn="精靈大人", anchor="gl-A")
        await _seed(s, uid=uid, pid=pid, eid=stranded, name="精靈小姐", cn="精靈小姐", anchor=None)
        await _seed(s, uid=uid, pid=pid, eid=other, name="Kai", cn="kai", anchor="gl-B")
        await s.run(
            "MATCH (a:Entity {id:$s}),(b:Entity {id:$o}) "
            "CREATE (a)-[:RELATES_TO {id:'r1', predicate:'betrayed', confidence:0.9, "
            "user_id:$u}]->(b)", s=stranded, o=other, u=uid)

        plan = await run_recanon_backfill(s, apply=True)

        r = await s.run(
            "MATCH ()-[rel:RELATES_TO]->() WHERE rel.user_id = $u OR rel.predicate IS NOT NULL "
            "RETURN count(rel) AS edges, collect(rel.predicate)[0] AS pred", u=uid)
        rec = await r.single()
        await s.run("MATCH (n {user_id:$u}) DETACH DELETE n", u=uid)
        assert rec["edges"] >= 1, f"the merge destroyed the relation entirely: {plan!r}"
        assert rec["pred"] == "betrayed", (
            f"the merge re-created the edge WITHOUT its predicate (got {rec['pred']!r}). "
            "A relation's predicate is its meaning — 'betrayed' and 'guards' are the same edge "
            "type and different facts.")


async def _doomed_and_kept(session, seeded: list[str]) -> tuple[str, str]:
    """Return (node the merge DELETES, node that survives), read off a DRY-RUN.

    🔴 **The first version of the three tests below was GREEN BY CONSTRUCTION and this
    helper is why they no longer are.** They named the unanchored node "stranded", hung the
    evidence on it, and asserted it survived — but `plan_recanon` RE-KEYS the unanchored node
    and folds the ANCHORED one into it. A re-key only rewrites the `id` property, so every
    edge on it survives no matter what the merge branch does: those assertions could not
    fail, and two of them passed against the UN-fixed code.

    So the doomed node is derived from the plan instead of assumed, which also keeps these
    tests meaningful if the planner's tie-break ever changes rather than letting them go
    quietly vacuous again.
    """
    plan = await run_recanon_backfill(session, apply=False)
    merges = [a for a in plan.actions if a.op == "merge"]
    assert len(merges) == 1, f"fixture did not produce exactly one merge: {plan!r}"
    doomed = merges[0].from_id
    kept = next(e for e in seeded if e != doomed)
    return doomed, kept


async def test_the_MERGE_path_carries_the_folded_node_s_EVIDENCE_to_the_survivor(neo4j_driver):
    """🔴 The merge branch moved `RELATES_TO` and nothing else, then `DETACH DELETE`d the
    folded node — taking its `EVIDENCED_BY` edges with it.

    Found by EXECUTING `--apply` against a faithful clone of the dev graph (T35g), not by
    reading it: the Entity subgraph's `EVIDENCED_BY` count fell 1275 → 1274 across the single
    merge. On that graph the dropped edge happened to be a DUPLICATE the survivor already
    held, so nothing was actually lost — which is exactly why a test derived from the live
    data would have proved nothing.

    This seeds the case the dev graph does NOT contain: a folded node citing a source the
    survivor does **not** already have. That is where the deletion destroys evidence.
    """
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    a_id, b_id = (f"n-{uuid.uuid4().hex[:8]}" for _ in range(2))
    src_shared, src_only_doomed = (f"src-{uuid.uuid4().hex[:8]}" for _ in range(2))
    async with neo4j_driver.session() as s:
        try:
            await _seed(s, uid=uid, pid=pid, eid=a_id, name="精靈大人", cn="精靈大人", anchor="gl-EV")
            await _seed(s, uid=uid, pid=pid, eid=b_id, name="精靈小姐", cn="精靈小姐", anchor=None)
            doomed, kept = await _doomed_and_kept(s, [a_id, b_id])

            for sid in (src_shared, src_only_doomed):
                await s.run("CREATE (x:ExtractionSource {id:$i, user_id:$u})", i=sid, u=uid)
            # The survivor already cites the shared source, so a bare "the count went down"
            # check could not tell dedup from loss. The assertion names the source instead.
            await s.run("MATCH (e:Entity {id:$e}),(x:ExtractionSource {id:$x}) "
                        "CREATE (e)-[:EVIDENCED_BY]->(x)", e=kept, x=src_shared)
            for sid in (src_shared, src_only_doomed):
                await s.run("MATCH (e:Entity {id:$e}),(x:ExtractionSource {id:$x}) "
                            "CREATE (e)-[:EVIDENCED_BY]->(x)", e=doomed, x=sid)

            plan = await run_recanon_backfill(s, apply=True)

            r = await s.run(
                "MATCH (e:Entity)-[:EVIDENCED_BY]->(x:ExtractionSource) WHERE e.user_id = $u "
                "RETURN collect(DISTINCT x.id) AS sources", u=uid)
            sources = set((await r.single())["sources"] or [])
            assert plan.merged == 1, f"the fixture stopped producing a merge: {plan!r}"
            assert src_only_doomed in sources, (
                f"the merge DELETED the folded node's evidence: source {src_only_doomed} was "
                f"cited only by that node and is now gone (survivor cites {sorted(sources)}). "
                "A `DETACH DELETE` after re-pointing only RELATES_TO destroys every other edge.")
            assert src_shared in sources, "the survivor lost its own pre-existing evidence"
        finally:
            await s.run("MATCH (n) WHERE n.user_id = $u DETACH DELETE n", u=uid)


async def test_the_MERGE_path_carries_a_FACT_that_was_about_the_folded_node(neo4j_driver):
    """`ABOUT` runs Fact → Entity, i.e. INTO the node being folded, and the merge path only
    re-pointed incoming `RELATES_TO`. On the dev-graph clone `ABOUT` held at 248 across the
    apply — but only because that one folded node had no fact attached, the same
    safe-by-luck shape as the `EntityStatus` re-point two branches up.

    A fact whose subject loses its link survives as a fact about nobody, so it stops being
    retrievable for the character it describes.
    """
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    a_id, b_id = (f"n-{uuid.uuid4().hex[:8]}" for _ in range(2))
    fact = f"fact-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as s:
        try:
            await _seed(s, uid=uid, pid=pid, eid=a_id, name="精靈大人", cn="精靈大人", anchor="gl-AB")
            await _seed(s, uid=uid, pid=pid, eid=b_id, name="精靈小姐", cn="精靈小姐", anchor=None)
            doomed, _kept = await _doomed_and_kept(s, [a_id, b_id])

            await s.run("CREATE (f:Fact {id:$i, user_id:$u, content:'she kept the gate'})",
                        i=fact, u=uid)
            await s.run("MATCH (f:Fact {id:$f}),(e:Entity {id:$e}) CREATE (f)-[:ABOUT]->(e)",
                        f=fact, e=doomed)

            plan = await run_recanon_backfill(s, apply=True)

            r = await s.run("MATCH (f:Fact {id:$f})-[:ABOUT]->(e:Entity) "
                            "RETURN collect(e.id) AS targets", f=fact)
            targets = (await r.single())["targets"] or []
            assert plan.merged == 1, f"the fixture stopped producing a merge: {plan!r}"
            assert targets, (
                "the merge DELETED the fact's ABOUT edge — the fact survives but is no longer "
                "about anybody, so it stops being retrievable for that character")
        finally:
            await s.run("MATCH (n) WHERE n.user_id = $u DETACH DELETE n", u=uid)


async def test_the_MERGE_path_REFUSES_to_delete_a_node_carrying_an_edge_it_cannot_move(neo4j_driver):
    """The fix above is an ENUMERATION of edge types, and the bug it fixes was that
    enumeration being incomplete. So it must fail loudly when it is incomplete again, rather
    than quietly repeating the same deletion under a different label.

    Seeds a relationship type the merge path does not know (`:MENTIONS`) and asserts the
    backfill raises naming it, and that it raises BEFORE the delete rather than after.
    """
    uid, pid = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    a_id, b_id = (f"n-{uuid.uuid4().hex[:8]}" for _ in range(2))
    other = f"psg-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as s:
        try:
            await _seed(s, uid=uid, pid=pid, eid=a_id, name="精靈大人", cn="精靈大人", anchor="gl-UN")
            await _seed(s, uid=uid, pid=pid, eid=b_id, name="精靈小姐", cn="精靈小姐", anchor=None)
            doomed, _kept = await _doomed_and_kept(s, [a_id, b_id])

            await s.run("CREATE (p:Passage {id:$i, user_id:$u})", i=other, u=uid)
            await s.run("MATCH (e:Entity {id:$e}),(p:Passage {id:$p}) "
                        "CREATE (e)-[:MENTIONS]->(p)", e=doomed, p=other)

            with pytest.raises(RuntimeError, match="MENTIONS"):
                await run_recanon_backfill(s, apply=True)

            r = await s.run("MATCH (e:Entity {id:$e}) RETURN count(e) AS n", e=doomed)
            assert (await r.single())["n"] == 1, (
                "the backfill raised but had already deleted the node — the guard must run "
                "BEFORE the delete, not after")
        finally:
            await s.run("MATCH (n) WHERE n.user_id = $u DETACH DELETE n", u=uid)
